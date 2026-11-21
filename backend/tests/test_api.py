import json
import sys
import time
from pathlib import Path

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from check_contract import validate_schedule_response  # noqa: E402

from app.main import app  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
EXAMPLES = ROOT / "examples"


def test_plans_are_listed():
    response = TestClient(app).get("/api/plans")
    assert response.status_code == 200
    assert {plan["id"] for plan in response.json()} == {"spring-market", "lantern-festival", "harbour-run"}


def test_post_valid_request_returns_optimal_schedule():
    request = json.loads((EXAMPLES / "schedule-request.json").read_text())
    response = TestClient(app).post("/api/schedule", json=request)
    assert response.status_code == 200
    body = response.json()
    assert body["end_day"] == 9
    assert validate_schedule_response(request, body) == []


def test_post_cycle_returns_200_with_cycle_shape():
    request = {
        "tasks": [
            {"id": "A", "name": "A", "owner": None, "duration_days": 1, "depends_on": ["B"]},
            {"id": "B", "name": "B", "owner": None, "duration_days": 1, "depends_on": ["A"]},
        ],
        "deadline_day": 10,
    }
    response = TestClient(app).post("/api/schedule", json=request)
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "cycle"
    assert set(body["cycle"]) == {"A", "B"}
    assert validate_schedule_response(request, body) == []


def test_post_invalid_bodies_are_refused():
    bad_bodies = [
        {},
        {"tasks": [], "deadline_day": 10.0},
        {"tasks": [], "deadline_day": True},
        {"tasks": "nope", "deadline_day": 10},
    ]
    for body in bad_bodies:
        response = TestClient(app).post("/api/schedule", json=body)
        assert 400 <= response.status_code < 500, body
        assert response.json() is not None


def test_post_61_tasks_is_refused():
    tasks = [
        {"id": f"T{i}", "name": f"Task {i}", "owner": None, "duration_days": 1, "depends_on": []}
        for i in range(61)
    ]
    response = TestClient(app).post("/api/schedule", json={"tasks": tasks, "deadline_day": 10})
    assert 400 <= response.status_code < 500


def test_post_duplicate_id_is_refused():
    request = {
        "tasks": [
            {"id": "A", "name": "A", "owner": None, "duration_days": 1, "depends_on": []},
            {"id": "A", "name": "A again", "owner": None, "duration_days": 1, "depends_on": []},
        ],
        "deadline_day": 10,
    }
    response = TestClient(app).post("/api/schedule", json=request)
    assert 400 <= response.status_code < 500
    assert any("duplicate" in str(error) for error in response.json()["detail"])


def test_post_unknown_dependency_is_refused():
    request = {
        "tasks": [{"id": "A", "name": "A", "owner": None, "duration_days": 1, "depends_on": ["Z"]}],
        "deadline_day": 10,
    }
    response = TestClient(app).post("/api/schedule", json=request)
    assert 400 <= response.status_code < 500


def test_post_zero_duration_is_refused():
    request = {
        "tasks": [{"id": "A", "name": "A", "owner": None, "duration_days": 0, "depends_on": []}],
        "deadline_day": 10,
    }
    response = TestClient(app).post("/api/schedule", json=request)
    assert 400 <= response.status_code < 500


def test_post_boolean_duration_is_refused():
    request = {
        "tasks": [{"id": "A", "name": "A", "owner": None, "duration_days": True, "depends_on": []}],
        "deadline_day": 10,
    }
    response = TestClient(app).post("/api/schedule", json=request)
    assert 400 <= response.status_code < 500


def test_post_empty_task_list_is_valid():
    response = TestClient(app).post("/api/schedule", json={"tasks": [], "deadline_day": 10})
    assert response.status_code == 200
    body = response.json()
    assert body["end_day"] == 0
    assert body["meets_deadline"] is True
    assert body["days_late"] == 0
    assert validate_schedule_response({"tasks": [], "deadline_day": 10}, body) == []


def test_get_plan_serves_a_schedule_block():
    response = TestClient(app).get("/api/plans/harbour-run")
    assert response.status_code == 200
    body = response.json()
    assert "schedule" in body


def test_post_60_task_benchmark_stays_under_eight_seconds():
    tasks = []
    for layer in range(5):
        for slot in range(12):
            index = layer * 12 + slot
            depends_on = []
            if layer > 0:
                depends_on = [f"T{(layer - 1) * 12 + slot}"]
            tasks.append(
                {
                    "id": f"T{index}",
                    "name": f"Task {index}",
                    "owner": f"Owner {index % 6}",
                    "duration_days": 1 + (index % 4),
                    "depends_on": depends_on,
                }
            )
    request = {"tasks": tasks, "deadline_day": 1000}
    start = time.time()
    response = TestClient(app).post("/api/schedule", json=request)
    wall = time.time() - start
    assert response.status_code == 200
    assert wall < 8
    assert validate_schedule_response(request, response.json()) == []
