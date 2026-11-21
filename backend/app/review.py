import json
import os
import sys

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
