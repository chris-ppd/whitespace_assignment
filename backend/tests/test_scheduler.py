import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from check_contract import validate_schedule_response  # noqa: E402

from app.scheduler import find_cycle, schedule, solve  # noqa: E402

EXAMPLES = Path(__file__).resolve().parents[2] / "examples"


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


def scheduled_response(tasks, deadline_day, entries):
    end_day = max((entry["end_day"] for entry in entries), default=0)
    return {
        "status": "scheduled",
        "schedule": entries,
        "end_day": end_day,
        "deadline_day": deadline_day,
        "meets_deadline": end_day <= deadline_day,
        "days_late": max(0, end_day - deadline_day),
        "cycle": [],
    }


def assert_solve_ok(tasks, deadline_day=10, end_day=None):
    entries = solve(tasks)
    errors = validate_schedule_response(
        {"tasks": tasks, "deadline_day": deadline_day}, scheduled_response(tasks, deadline_day, entries)
    )
    assert errors == []
    if end_day is not None:
        assert max((entry["end_day"] for entry in entries), default=0) == end_day
    return entries


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


def owned(id, owner, duration_days, depends_on=()):
    entry = task(id, duration_days, depends_on)
    entry["owner"] = owner
    return entry


def test_same_owner_tasks_cannot_run_in_parallel():
    tasks = [owned("A", "Ann", 3), owned("B", "Ann", 2)]
    assert_solve_ok(tasks, end_day=5)


def test_contract_example_ends_at_day_nine():
    request = json.loads((EXAMPLES / "schedule-request.json").read_text())
    assert_solve_ok(request["tasks"], request["deadline_day"], end_day=9)


def test_unowned_tasks_all_run_in_parallel():
    tasks = [task(f"T{i}", 1) for i in range(5)]
    assert_solve_ok(tasks, end_day=1)


def test_empty_task_list_solves_to_nothing():
    assert solve([]) == []


def test_single_task_ends_after_its_duration():
    entries = assert_solve_ok([task("A", 3)], end_day=3)
    assert entries == [{"id": "A", "start_day": 0, "end_day": 3}]


def test_touching_intervals_are_legal():
    tasks = [owned("A", "Ann", 3), owned("B", "Ann", 2)]
    entries = assert_solve_ok(tasks, end_day=5)
    by_id = {entry["id"]: entry for entry in entries}
    assert by_id["B"]["start_day"] == by_id["A"]["end_day"]
