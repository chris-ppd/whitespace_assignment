import json
import sys
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from check_contract import validate_review_shape  # noqa: E402

from app import review as review_module  # noqa: E402


class FakeClient:
    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = []
        self.messages = types.SimpleNamespace(create=self._create)

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        text = self.replies.pop(0) if self.replies else ""
        message = types.SimpleNamespace(type="text", text=text)
        return types.SimpleNamespace(content=[message])


GOOD_REPLY = json.dumps(
    {
        "deadline_day": 21,
        "tasks": [
            {
                "id": "T1",
                "name": "Book the hall",
                "owner": "Ann",
                "duration_days": 3,
                "depends_on": [],
                "quote": "Ann books the hall, which takes three days.",
            }
        ],
        "findings": [],
    }
)


def test_review_plan_returns_scripted_reply_text():
    client = FakeClient([GOOD_REPLY])
    reply = review_module.review_plan("plan text", client=client)
    assert json.loads(reply)["deadline_day"] == 21
    call = client.calls[0]
    assert "plan text" in call["messages"][0]["content"]
    assert call["max_tokens"] == review_module.MAX_TOKENS


def test_review_plan_appends_corrective_text():
    client = FakeClient(["{}"])
    review_module.review_plan("plan text", client=client, corrective="quote was wrong")
    assert "quote was wrong" in client.calls[0]["messages"][0]["content"]


def test_extract_json_bare_object():
    assert review_module.extract_json(GOOD_REPLY)["deadline_day"] == 21


def test_extract_json_fenced():
    fenced = "```json\n" + GOOD_REPLY + "\n```"
    assert review_module.extract_json(fenced)["deadline_day"] == 21


def test_extract_json_wrapped_in_prose():
    wrapped = "Here is the review you asked for:\n\n" + GOOD_REPLY + "\n\nHope this helps!"
    assert review_module.extract_json(wrapped)["deadline_day"] == 21


def test_extract_json_garbage_raises():
    import pytest

    with pytest.raises(ValueError):
        review_module.extract_json("not json at all")


def example_review():
    path = Path(__file__).resolve().parents[2] / "examples" / "review-output.json"
    return json.loads(path.read_text())


def test_example_review_is_valid_by_both_validators():
    review = example_review()
    assert review_module.validate_review(review) == []
    assert validate_review_shape(review) == []


def review_with(**overrides):
    review = example_review()
    review.update(overrides)
    return review


def collect(review):
    return review_module.validate_review(review)


def test_missing_deadline_day_is_an_error():
    review = example_review()
    del review["deadline_day"]
    assert any("deadline_day" in error for error in collect(review))


def test_string_deadline_is_an_error():
    assert any("deadline_day" in error for error in collect(review_with(deadline_day="10")))


def test_boolean_deadline_is_an_error():
    assert any("deadline_day" in error for error in collect(review_with(deadline_day=True)))


def test_null_deadline_is_valid():
    assert collect(review_with(deadline_day=None)) == []


def test_tasks_not_a_list_is_an_error():
    assert any("tasks" in error for error in collect(review_with(tasks="nope")))


def test_task_missing_quote_is_an_error():
    review = example_review()
    del review["tasks"][0]["quote"]
    assert any("quote" in error for error in collect(review))


def test_task_quote_null_is_an_error():
    review = example_review()
    review["tasks"][0]["quote"] = None
    assert any("quote" in error for error in collect(review))


def test_finding_quote_null_is_legal():
    review = example_review()
    review["findings"].append({"title": "T", "detail": "D", "quote": None})
    assert collect(review) == []


def test_string_duration_is_an_error():
    assert any("duration_days" in error for error in collect(review_with_tasks_duration("3")))


def review_with_tasks_duration(duration):
    review = example_review()
    review["tasks"][0]["duration_days"] = duration
    return review


def test_zero_duration_is_an_error():
    assert any("duration_days" in error for error in collect(review_with_tasks_duration(0)))


def test_boolean_duration_is_an_error():
    assert any("duration_days" in error for error in collect(review_with_tasks_duration(True)))


def test_integer_owner_is_an_error():
    review = example_review()
    review["tasks"][0]["owner"] = 42
    assert any("owner" in error for error in collect(review))


def test_depends_on_not_a_list_is_an_error():
    review = example_review()
    review["tasks"][0]["depends_on"] = "T2"
    assert any("depends_on" in error for error in collect(review))


def test_duplicate_task_ids_are_an_error():
    review = example_review()
    review["tasks"].append(dict(review["tasks"][0]))
    assert any("duplicate" in error for error in collect(review))


def test_unknown_depends_on_id_is_an_error():
    review = example_review()
    review["tasks"][0]["depends_on"] = ["T99"]
    assert any("unknown" in error for error in collect(review))


def test_self_dependency_is_not_an_error_here():
    review = example_review()
    review["tasks"][0]["depends_on"] = [review["tasks"][0]["id"]]
    assert collect(review) == []


def test_non_dict_review_is_an_error():
    assert collect([1, 2, 3]) == ["review must be an object"]


def test_run_review_returns_review_on_first_good_reply():
    plan = "Ann books the hall, which takes three days.\n"
    client = FakeClient([GOOD_REPLY])
    review = review_module.run_review(plan, client)
    assert review["deadline_day"] == 21
    assert client.calls[0]["messages"][0]["content"].startswith(review_module.PROMPT)


def test_run_review_succeeds_on_second_attempt_with_corrective():
    plan = "Ann books the hall, which takes three days.\n"
    client = FakeClient(["utter garbage", GOOD_REPLY])
    review = run_quick(plan, client)
    assert review["deadline_day"] == 21
    assert len(client.calls) == 2
    assert "model reply contains no JSON object" in client.calls[1]["messages"][0]["content"]


def run_quick(plan, client):
    from unittest import mock

    with mock.patch.object(review_module.time, "sleep"):
        return review_module.run_review(plan, client)


def test_run_review_raises_after_three_bad_replies():
    plan = "Ann books the hall, which takes three days.\n"
    client = FakeClient(["garbage one", "garbage two", "garbage three"])
    import pytest

    with pytest.raises(RuntimeError) as exc:
        run_quick(plan, client)
    assert "3 attempts" in str(exc.value)
    assert "model reply contains no JSON object" not in client.calls[0]["messages"][0]["content"]
    assert "model reply contains no JSON object" in client.calls[1]["messages"][0]["content"]


def test_run_review_escalates_unanchorable_task_quote():
    plan = "Tiny plan.\n"
    bad = json.dumps(
        {
            "deadline_day": 1,
            "tasks": [
                {
                    "id": "T1", "name": "Impossible", "owner": None,
                    "duration_days": 1, "depends_on": [],
                    "quote": "Zebra quantum jumps over the forever fence.",
                }
            ],
            "findings": [],
        }
    )
    client = FakeClient([bad, bad, bad])
    import pytest

    with pytest.raises(RuntimeError) as exc:
        run_quick(plan, client)
    assert "quote does not match" in str(exc.value)


def test_run_review_respects_time_budget_with_zero_calls():
    import pytest
    from unittest import mock

    client = FakeClient([GOOD_REPLY])
    with mock.patch.object(review_module, "TIME_BUDGET_S", 0):
        with pytest.raises(RuntimeError) as exc:
            review_module.run_review("plan", client)
    assert "time budget" in str(exc.value)
    assert client.calls == []


def test_extra_severity_field_is_ignored():
    review = example_review()
    review["findings"].append({"title": "T", "detail": "D", "severity": "high", "quote": None})
    assert collect(review) == []


FIXTURES = Path(__file__).resolve().parent / "fixtures"


def quote_is_grounded(review, plan_text):
    """Replicate the grader's quote rule: collapse, then case-sensitive substring."""
    collapsed = review_module._collapse(plan_text)
    for collection in ("tasks", "findings"):
        for item in review.get(collection, []):
            quote = item.get("quote")
            if quote is not None and review_module._collapse(quote) not in collapsed:
                return False
    return True


PROSE_ONLY_PLAN = (FIXTURES / "prose-only.md").read_text()
PROSE_ONLY_REPLY = json.dumps(
    {
        "deadline_day": 21,
        "tasks": [
            {
                "id": "T1", "name": "Book the stallholders", "owner": "Priya",
                "duration_days": 4, "depends_on": [],
                "quote": "Priya will book the stallholders, which takes her four days.",
            },
            {
                "id": "T2", "name": "Arrange waste and recycling", "owner": "Tomas",
                "duration_days": 7, "depends_on": ["T1"],
                "quote": "the stalls confirmed, Tomas will arrange the waste and recycling service,",
            },
            {
                "id": "T3", "name": "Apply for the street permit", "owner": "Priya",
                "duration_days": 1, "depends_on": ["T1"],
                "quote": "we have booked the stalls; the application itself is one day of paperwork.",
            },
        ],
        "findings": [
            {
                "title": "Nobody runs first aid",
                "detail": "The fair cannot open without it, but no one has agreed to run it.",
                "severity": "high",
                "quote": "Nobody has yet agreed to run first aid, and the fair cannot open without it.",
            }
        ],
    }
)


def test_prose_only_fixture_pipeline():
    review = run_quick(PROSE_ONLY_PLAN, FakeClient([PROSE_ONLY_REPLY]))
    assert review["deadline_day"] == 21
    assert {task["id"] for task in review["tasks"]} == {"T1", "T2", "T3"}
    waste = next(task for task in review["tasks"] if task["id"] == "T2")
    assert waste["duration_days"] == 7  # one week
    assert waste["depends_on"] == ["T1"]
    assert validate_review_shape(review) == []
    assert quote_is_grounded(review, PROSE_ONLY_PLAN)


TRAPS_PLAN = (FIXTURES / "traps.md").read_text()
TRAPS_REPLY = json.dumps(
    {
        "deadline_day": None,
        "tasks": [
            {
                "id": "T1", "name": "Prepare materials", "owner": "Marco",
                "duration_days": 2, "depends_on": [],
                "quote": "It takes Marco two days to prepare materials.",
            },
            {
                "id": "T2", "name": "Prepare the venue", "owner": None,
                "duration_days": 3, "depends_on": [],
                # Deliberately case-drifted ("Nowhere"); repair anchors it.
                "quote": "PREPARING THE VENUE TAKES THREE DAYS and is listed Nowhere else.",
            },
            {
                "id": "T3", "name": "Teach the classes", "owner": "Dana",
                "duration_days": 1, "depends_on": ["T1"],
                "quote": "Dana will teach the classes after the materials are ready.",
            },
        ],
        "findings": [
            {
                "title": "Venue preparation is stated only in prose",
                "detail": "It is not in any task table and names no owner.",
                "severity": "medium",
                "quote": "PREPARING THE VENUE TAKES THREE DAYS and is listed nowhere else.",
            },
            {
                "title": "No deadline is stated",
                "detail": "The plan never says by which day the work must finish.",
                "severity": "medium",
                "quote": None,
            },
        ],
    }
)


def test_traps_fixture_pipeline_repairs_case_drift():
    review = run_quick(TRAPS_PLAN, FakeClient([TRAPS_REPLY]))
    venue = next(task for task in review["tasks"] if task["id"] == "T2")
    assert venue["quote"] == "PREPARING THE VENUE TAKES THREE DAYS and is listed nowhere else."
    assert review["deadline_day"] is None
    assert validate_review_shape(review) == []
    assert quote_is_grounded(review, TRAPS_PLAN)


def test_main_without_args_prints_usage_and_returns_1(capsys):
    assert review_module.main([]) == 1
    assert "Usage" in capsys.readouterr().err


def test_main_with_missing_plan_file_never_builds_a_client(tmp_path, monkeypatch):
    def explode():
        raise AssertionError("build_client must not be called before the plan is read")

    monkeypatch.setattr(review_module, "build_client", explode)
    assert review_module.main(["/no/such/plan.md", str(tmp_path / "out.json")]) == 1


def test_main_without_key_fails_before_any_call(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    # load_dotenv resolves relative to review.py, not the cwd, so chdir does
    # not isolate it; neuter it instead to simulate a keyless environment.
    monkeypatch.setattr(review_module, "load_dotenv", lambda: None)
    monkeypatch.chdir(tmp_path)
    plan = tmp_path / "plan.md"
    plan.write_text("Ann books the hall, which takes three days.\n")
    assert review_module.main([str(plan), str(tmp_path / "out.json")]) == 1
    assert "OPENROUTER_API_KEY" in capsys.readouterr().err
    assert not (tmp_path / "out.json").exists()


def test_main_success_writes_contract_valid_review(tmp_path, monkeypatch):
    plan = tmp_path / "plan.md"
    plan.write_text("Ann books the hall, which takes three days.\n")
    out = tmp_path / "out.json"
    monkeypatch.setattr(review_module, "build_client", lambda: FakeClient([GOOD_REPLY]))
    assert review_module.main([str(plan), str(out)]) == 0
    review = json.loads(out.read_text())
    assert validate_review_shape(review) == []


def test_main_failing_pipeline_leaves_no_output_file(tmp_path, monkeypatch):
    from unittest import mock

    plan = tmp_path / "plan.md"
    plan.write_text("Ann books the hall, which takes three days.\n")
    out = tmp_path / "out.json"
    client = FakeClient(["garbage"] * 3)
    monkeypatch.setattr(review_module, "build_client", lambda: client)
    monkeypatch.setattr(review_module, "RETRY_BACKOFF_S", 0)
    with mock.patch.object(review_module.time, "sleep"):
        assert review_module.main([str(plan), str(out)]) == 1
    assert not out.exists()


def test_collapse_runs_whitespace_to_single_spaces():
    assert review_module._collapse("a\n  b\tc") == "a b c"


PLAN = """# Fair

Opening line for the pair span.

| Task | Who | Days |
|---|---|---|
| Book the hall | Ann | 3 |

Closing line.
"""


def anchored(review):
    problems = review_module.anchor_quotes(review, PLAN)
    return review, problems


def test_exact_quote_is_untouched():
    review = {"deadline_day": None, "tasks": [], "findings": [
        {"title": "T", "detail": "D", "quote": "| Book the hall | Ann | 3 |"}
    ]}
    review, problems = anchored(review)
    assert problems == []
    assert review["findings"][0]["quote"] == "| Book the hall | Ann | 3 |"


def test_cross_line_span_the_model_copied_faithfully_passes():
    review = {"deadline_day": None, "tasks": [], "findings": [
        {"title": "T", "detail": "D", "quote": "Opening line for the pair span. Closing line."}
    ]}
    review, problems = anchored(review)
    # Not adjacent lines, so this is a plain substring miss; the repair
    # window cannot produce it and a finding quote degrades honestly to null.
    assert review["findings"][0]["quote"] is None


def test_whitespace_drift_passes_the_contract_fast_path_untouched():
    # Whitespace runs collapse to one space by contract law, so any pure
    # spacing drift is already a legal quote; repair must not touch it.
    review = {"deadline_day": None, "tasks": [], "findings": []}
    review["tasks"] = [{
        "id": "T1", "name": "Book the hall", "owner": "Ann",
        "duration_days": 3, "depends_on": [],
        "quote": "Book  the   hall",
    }]
    review, problems = anchored(review)
    assert problems == []
    assert review["tasks"][0]["quote"] == "Book  the   hall"


def test_case_drift_on_one_character_is_repaired_to_true_case():
    review = {"deadline_day": None, "tasks": [], "findings": []}
    review["tasks"] = [{
        "id": "T1", "name": "Book the hall", "owner": "Ann",
        "duration_days": 3, "depends_on": [],
        "quote": "| Book the Hall | Ann | 3 |",  # hall -> Hall
    }]
    review, problems = anchored(review)
    assert problems == []
    assert review["tasks"][0]["quote"] == "| Book the hall | Ann | 3 |"


def test_small_paraphrase_is_repaired_when_close_enough():
    review = {"deadline_day": None, "tasks": [], "findings": []}
    review["tasks"] = [{
        "id": "T1", "name": "Book the hall", "owner": "Ann",
        "duration_days": 3, "depends_on": [],
        "quote": "Opening line for the pair span!",  # period -> exclamation
    }]
    review, problems = anchored(review)
    assert problems == []
    assert review["tasks"][0]["quote"] == "Opening line for the pair span."


def test_wholesale_case_conversion_fails_loudly_at_threshold():
    review = {"deadline_day": None, "tasks": [], "findings": []}
    review["tasks"] = [{
        "id": "T1", "name": "Book the hall", "owner": "Ann",
        "duration_days": 3, "depends_on": [],
        "quote": "book the hall | ann | 3 |",  # ratio 0.885 < 0.9
    }]
    review, problems = anchored(review)
    assert len(problems) == 1


def test_hallucinated_finding_quote_becomes_null():
    review = {"deadline_day": None, "tasks": [], "findings": [
        {"title": "T", "detail": "D", "quote": "No such line exists anywhere here."}
    ]}
    review, problems = anchored(review)
    assert problems == []
    assert review["findings"][0]["quote"] is None


def test_hallucinated_task_quote_is_a_problem():
    review = {"deadline_day": None, "tasks": [], "findings": []}
    review["tasks"] = [{
        "id": "T1", "name": "Book the hall", "owner": "Ann",
        "duration_days": 3, "depends_on": [],
        "quote": "No such line exists anywhere here.",
    }]
    review, problems = anchored(review)
    assert len(problems) == 1
    assert "T1" in problems[0] or "tasks[0]" in problems[0]


def test_exact_table_row_quote_keeps_pipes_intact():
    review = {"deadline_day": row_quote()}
    review["tasks"] = [{
        "id": "T1", "name": "Book the hall", "owner": "Ann",
        "duration_days": 3, "depends_on": [], "quote": row_quote(),
    }]
    review, problems = anchored(review)
    assert problems == []
    assert review["tasks"][0]["quote"] == "| Book the hall | Ann | 3 |"


def row_quote():
    return "| Book the hall | Ann | 3 |"
