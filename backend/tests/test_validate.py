from app.validate import validate_request


def body(**overrides):
    request = {
        "tasks": [
            {"id": "A", "name": "Book the hall", "owner": "Ann", "duration_days": 3, "depends_on": []},
            {"id": "B", "name": "Sign the contract", "owner": None, "duration_days": 2, "depends_on": ["A"]},
        ],
        "deadline_day": 10,
    }
    request.update(overrides)
    return request


def test_valid_body_has_no_errors():
    assert validate_request(body()) == []


def test_extra_fields_are_ignored():
    request = body()
    request["tasks"][0]["quote"] = "Ann books the hall."
    request["note"] = "hello"
    assert validate_request(request) == []


def test_boolean_duration_is_rejected():
    request = body()
    request["tasks"][0]["duration_days"] = True
    assert validate_request(request) != []


def test_boolean_deadline_is_rejected():
    assert validate_request(body(deadline_day=False)) != []


def test_float_deadline_is_rejected():
    assert validate_request(body(deadline_day=10.0)) != []


def test_more_than_60_tasks_is_rejected():
    tasks = [
        {"id": f"T{i}", "name": f"Task {i}", "owner": None, "duration_days": 1, "depends_on": []}
        for i in range(61)
    ]
    assert validate_request(body(tasks=tasks)) != []


def test_exactly_60_tasks_is_accepted():
    tasks = [
        {"id": f"T{i}", "name": f"Task {i}", "owner": None, "duration_days": 1, "depends_on": []}
        for i in range(60)
    ]
    assert validate_request(body(tasks=tasks)) == []


def test_duplicate_id_is_rejected():
    request = body()
    request["tasks"][1]["id"] = "A"
    errors = validate_request(request)
    assert any("duplicate" in error for error in errors)


def test_unknown_dependency_is_rejected():
    request = body()
    request["tasks"][0]["depends_on"] = ["Z"]
    assert validate_request(request) != []


def test_forward_reference_is_accepted():
    request = body()
    request["tasks"][0]["depends_on"] = ["B"]
    assert validate_request(request) == []


def test_self_dependency_is_accepted_here():
    request = body()
    request["tasks"][0]["depends_on"] = ["A"]
    assert validate_request(request) == []


def test_missing_name_is_rejected():
    request = body()
    del request["tasks"][0]["name"]
    assert validate_request(request) != []


def test_missing_owner_is_rejected():
    request = body()
    del request["tasks"][0]["owner"]
    assert validate_request(request) != []


def test_depends_on_not_a_list_is_rejected():
    request = body()
    request["tasks"][0]["depends_on"] = "A"
    assert validate_request(request) != []


def test_zero_duration_is_rejected():
    request = body()
    request["tasks"][0]["duration_days"] = 0
    assert validate_request(request) != []


def test_missing_tasks_is_rejected():
    request = body()
    del request["tasks"]
    assert validate_request(request) != []


def test_missing_deadline_is_rejected():
    request = body()
    del request["deadline_day"]
    assert validate_request(request) != []


def test_all_errors_are_collected_at_once():
    request = body()
    request["tasks"][0]["duration_days"] = 0
    del request["tasks"][0]["name"]
    request["deadline_day"] = None
    errors = validate_request(request)
    assert len(errors) == 3
