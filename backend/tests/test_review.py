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


def test_extra_severity_field_is_ignored():
    review = example_review()
    review["findings"].append({"title": "T", "detail": "D", "severity": "high", "quote": None})
    assert collect(review) == []


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
