import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from check_contract import validate_schedule_response  # noqa: E402

from app.scheduler import find_cycle, schedule  # noqa: E402


def task(id, duration_days, depends_on=()):
    return {"id": id, "name": id, "owner": None, "duration_days": duration_days, "depends_on": list(depends_on)}


def cycle_response(cycle, deadline_day=10):
    return {
        "status": "cycle",
        "schedule": [],
        "end_day": None,
        "deadline_day": deadline_day,
        "meets_deadline": None,
        "days_late": None,
        "cycle": list(cycle),
    }


def assert_cycle_ok(tasks, deadline_day=10):
    cycle = find_cycle(tasks)
    assert cycle, "expected a cycle"
    errors = validate_schedule_response(
        {"tasks": tasks, "deadline_day": deadline_day}, cycle_response(cycle, deadline_day)
    )
    assert errors == []
    return cycle


def test_single_task_ends_after_its_duration():
    result = schedule([task("A", 3)], 10)
    assert result["schedule"] == [{"id": "A", "start_day": 0, "end_day": 3}]
    assert result["end_day"] == 3


def test_dependent_task_starts_after_its_dependency():
    result = schedule([task("A", 3), task("B", 2, ["A"])], 10)
    by_id = {item["id"]: item for item in result["schedule"]}
    assert by_id["B"]["start_day"] == 3
    assert result["end_day"] == 5


def test_acyclic_tasks_have_no_cycle():
    assert find_cycle([task("A", 3), task("B", 2, ["A"])]) is None


def test_self_dependency_is_a_cycle():
    assert assert_cycle_ok([task("A", 3, ["A"])]) == ["A"]


def test_two_task_loop_is_a_cycle():
    tasks = [task("A", 3, ["B"]), task("B", 2, ["A"])]
    cycle = assert_cycle_ok(tasks)
    assert set(cycle) == {"A", "B"}


def test_three_task_loop_is_a_cycle():
    tasks = [task("A", 1, ["C"]), task("B", 1, ["A"]), task("C", 1, ["B"])]
    cycle = assert_cycle_ok(tasks)
    assert set(cycle) == {"A", "B", "C"}


def test_figure_eight_reports_one_loop():
    tasks = [
        task("A", 1, ["B", "C"]),
        task("B", 1, ["A"]),
        task("C", 1, ["A"]),
    ]
    cycle = assert_cycle_ok(tasks)
    # Both loops pass through A; whatever is reported must be one simple loop.
    assert "A" in cycle
    assert len(cycle) == len(set(cycle))


def test_tail_leading_into_a_loop_reports_only_the_loop():
    tasks = [
        task("D", 1, ["A"]),
        task("A", 1, ["B"]),
        task("B", 1, ["A"]),
    ]
    cycle = assert_cycle_ok(tasks)
    assert set(cycle) == {"A", "B"}
