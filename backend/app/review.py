import difflib
import json
import os
import sys
import time

import anthropic
from dotenv import load_dotenv

DEFAULT_MODEL = "nvidia/nemotron-3.5-super-vl:free"
OPENROUTER_BASE_URL = "https://openrouter.ai/api"
MAX_TOKENS = 16000
REQUEST_TIMEOUT_S = 60
MAX_ATTEMPTS = 3
RETRY_BACKOFF_S = 5
TIME_BUDGET_S = 270
ANCHOR_THRESHOLD = 0.9

PROMPT = """You extract a task review from a community event plan for a town council events officer.

Read the WHOLE document. A task, an owner, a duration, or a dependency may be stated in the task table OR in prose; both count equally. The prose often holds facts the table lacks, and vice versa.

Return ONE JSON object and nothing else:
{"deadline_day": <integer or null>,
 "tasks": [{"id", "name", "owner", "duration_days", "depends_on", "quote"}, ...],
 "findings": [{"title", "detail", "severity", "quote"}, ...]}

Field rules:
- id: short stable ids T1, T2, ... The graph must be consistent: no duplicate ids, and every depends_on id must identify a task you returned.
- owner: the person responsible, or null if none is named anywhere in the document.
- duration_days: integer days, at least 1. A stated week means 7 days; convert weeks to days.
- depends_on: ids of tasks that must finish first. When the plan states dependencies by task name (in the table or in prose), resolve the names to your ids.
- deadline_day: the day number the plan must be finished by, counted in days from kickoff, stated anywhere in the document. Use null when the plan does not clearly state one. Never guess; a wrong deadline is worse than null.
- quote: copy the exact line from the plan that states this task's key facts (who, how long, waits for). ONE line only, verbatim: character for character, preserve capitalization and punctuation, never merge or fix text. For a task stated in the table, quote that task's table row.
- findings: risks that threaten the plan - missing owners, missing durations, missing or contradictory deadlines, dependencies on work that is not planned as a task, unrealistic timing. severity: "high", "medium", or "low".
- Each finding's quote follows the same verbatim rule; use null when no single line in the plan supports the finding."""


def build_client():
    load_dotenv()
    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        raise RuntimeError(
            "OPENROUTER_API_KEY is not set; copy .env.example to .env and add your key from openrouter.ai"
        )
    return anthropic.Anthropic(
        base_url=OPENROUTER_BASE_URL,
        auth_token=key,
        timeout=REQUEST_TIMEOUT_S,
        max_retries=2,
    )


def review_plan(text, client=None, corrective=""):
    """One model attempt; returns the raw reply text."""
    client = client or build_client()
    prompt = PROMPT + "\n\n" + text
    if corrective:
        prompt += "\n\nYour previous reply had these problems, fix them:\n" + corrective
    reply = client.messages.create(
        model=os.environ.get("REVIEW_MODEL", DEFAULT_MODEL),
        max_tokens=MAX_TOKENS,
        messages=[{"role": "user", "content": prompt}],
    )
    return "".join(block.text for block in reply.content if block.type == "text")


def extract_json(reply_text):
    """Parse the JSON object out of a model reply, tolerating fences and prose."""
    text = reply_text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end <= start:
        raise ValueError("model reply contains no JSON object")
    try:
        return json.loads(text[start:end + 1])
    except json.JSONDecodeError as error:
        raise ValueError(f"model reply is not valid JSON: {error}") from error


def _collapse(text):
    """The contract's own normalization: every whitespace run to one space."""
    return " ".join(text.split())


def _candidates(plan_text):
    """Quote candidates: single stripped lines, plus adjacent-line pairs.

    The line is the contract's natural atom — a quote may cross a line
    break but never a table row, because the markdown pipe is not
    whitespace. No sentence tokenizer, no wider windows.
    """
    lines = [line.strip() for line in plan_text.splitlines()]
    singles = [line for line in lines if line]
    pairs = [
        f"{lines[i]} {lines[i + 1]}"
        for i in range(len(lines) - 1)
        if lines[i] and lines[i + 1]
    ]
    return singles + pairs


def anchor_quotes(review, plan_text):
    """Ground every non-null quote in the plan, in place; return problems left.

    Threshold asymmetry: set too high, honest quotes fail loudly into the
    retry ladder; set too low, a WRONG line gets anchored silently and the
    officer quotes something the committee never wrote. Never lower it
    without a failing example in hand.
    """
    collapsed_plan = _collapse(plan_text)
    candidates = _candidates(plan_text)
    problems = []
    for collection in ("tasks", "findings"):
        for index, item in enumerate(review.get(collection, [])):
            quote = item.get("quote")
            if quote is None:
                continue
            if _collapse(quote) in collapsed_plan:
                continue
            best, best_ratio = None, 0.0
            for candidate in candidates:
                ratio = difflib.SequenceMatcher(
                    None, _collapse(quote), _collapse(candidate)
                ).ratio()
                if ratio > best_ratio:
                    best, best_ratio = candidate, ratio
            if best is not None and best_ratio >= ANCHOR_THRESHOLD:
                item["quote"] = best
            elif collection == "findings":
                item["quote"] = None
            else:
                problems.append(
                    f"tasks[{index}] quote does not match any line of the plan"
                )
    return problems


def validate_review(review):
    """Return every problem with a model review; [] when it is usable.

    Mirrors the checker's validate_review_shape semantics with strict
    typing (bools and numeric strings are not integers) and collects all
    errors at once, so one corrective retry sees every problem. Extra
    fields such as severity are never rejected. Cycles are not an error
    here; the downstream scheduler answers them.
    """
    if not isinstance(review, dict):
        return ["review must be an object"]

    errors = []
    if "deadline_day" not in review:
        errors.append("missing deadline_day")
    elif review["deadline_day"] is not None and type(review["deadline_day"]) is not int:
        errors.append("deadline_day must be an integer or null")

    task_ids = set()
    tasks = review.get("tasks")
    if "tasks" not in review:
        errors.append("missing tasks")
    elif not isinstance(tasks, list):
        errors.append("tasks must be a list")
    else:
        seen_ids = set()
        for index, task in enumerate(tasks):
            prefix = f"tasks[{index}]"
            if not isinstance(task, dict):
                errors.append(f"{prefix} must be an object")
                continue
            for field in ("id", "name", "owner", "duration_days", "depends_on", "quote"):
                if field not in task:
                    errors.append(f"{prefix} missing {field}")
            task_id = task.get("id")
            if "id" in task and not isinstance(task_id, str):
                errors.append(f"{prefix} id must be a string")
            elif isinstance(task_id, str):
                if task_id in seen_ids:
                    errors.append(f"{prefix} duplicate id {task_id}")
                seen_ids.add(task_id)
                task_ids.add(task_id)
            if "name" in task and not isinstance(task["name"], str):
                errors.append(f"{prefix} name must be a string")
            if "owner" in task and task["owner"] is not None and not isinstance(task["owner"], str):
                errors.append(f"{prefix} owner must be a string or null")
            duration = task.get("duration_days")
            if "duration_days" in task and (type(duration) is not int or duration < 1):
                errors.append(f"{prefix} duration_days must be an integer of at least 1")
            depends_on = task.get("depends_on")
            if "depends_on" in task and (
                not isinstance(depends_on, list) or any(not isinstance(d, str) for d in depends_on)
            ):
                errors.append(f"{prefix} depends_on must be a list of ids")
            if "quote" in task and not isinstance(task["quote"], str):
                errors.append(f"{prefix} quote must be a string")

    findings = review.get("findings")
    if "findings" not in review:
        errors.append("missing findings")
    elif not isinstance(findings, list):
        errors.append("findings must be a list")
    else:
        for index, finding in enumerate(findings):
            prefix = f"findings[{index}]"
            if not isinstance(finding, dict):
                errors.append(f"{prefix} must be an object")
                continue
            for field in ("title", "detail"):
                if field not in finding:
                    errors.append(f"{prefix} missing {field}")
                elif not isinstance(finding[field], str):
                    errors.append(f"{prefix} {field} must be a string")
            if "quote" in finding and finding["quote"] is not None and not isinstance(finding["quote"], str):
                errors.append(f"{prefix} quote must be a string or null")

    if not isinstance(tasks, list):
        return errors
    for index, task in enumerate(tasks):
        if not isinstance(task, dict):
            continue
        depends_on = task.get("depends_on")
        if not isinstance(depends_on, list):
            continue
        unknown = set(depends_on) - task_ids
        if unknown:
            errors.append(f"tasks[{index}] depends on unknown id {sorted(unknown)[0]}")
    return errors


def run_review(plan_text, client):
    """Extract, validate and anchor, retrying with corrective feedback.

    Problems accumulate across attempts so the final failure lists
    everything the model got wrong, and each follow-up attempt sees them
    in its prompt. The wall-clock guard stops before an attempt that
    could not finish inside the contract's time budget.
    """
    started = time.monotonic()
    seen_problems = []
    for attempt in range(MAX_ATTEMPTS):
        if time.monotonic() - started + REQUEST_TIMEOUT_S > TIME_BUDGET_S:
            raise RuntimeError(
                f"time budget exhausted before attempt {attempt + 1} of {MAX_ATTEMPTS}"
            )
        reply = review_plan(plan_text, client, "\n".join(seen_problems))
        try:
            review = extract_json(reply)
            problems = validate_review(review)
            if not problems:
                problems = anchor_quotes(review, plan_text)
        except ValueError as error:
            review, problems = None, [str(error)]
        if not problems:
            return review
        seen_problems.extend(problems)
        if attempt + 1 < MAX_ATTEMPTS:
            time.sleep(RETRY_BACKOFF_S)
    raise RuntimeError(
        f"review failed after {MAX_ATTEMPTS} attempts:\n" + "\n".join(seen_problems)
    )


def main(argv):
    """CLI entry: 0 on a written review, 1 with a reason and no file otherwise."""
    load_dotenv()
    if len(argv) != 2:
        print("Usage: ./review <plan.md> <out.json>", file=sys.stderr)
        return 1
    plan_path, out_path = argv
    try:
        with open(plan_path, encoding="utf-8") as source:
            plan_text = source.read()
    except OSError as error:
        print(error, file=sys.stderr)
        return 1
    try:
        review = run_review(plan_text, build_client())
    except (RuntimeError, OSError) as error:
        print(error, file=sys.stderr)
        return 1
    with open(out_path, "w", encoding="utf-8") as sink:
        json.dump(review, sink, indent=2)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
