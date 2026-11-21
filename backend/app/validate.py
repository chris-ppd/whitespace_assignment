MAX_TASKS = 60


def validate_request(body):
    """Return every problem with a schedule request body; [] when it is valid.

    Deliberately not checked: self or circular dependencies (the scheduler
    reports them), negative deadlines (the verdict formulas handle them),
    empty-string ids, names or owners (valid strings), huge durations
    (int64 horizon), duplicate entries within one depends_on, extra fields
    (the contracts allow and ignore them).
    """
    errors = []

    if not isinstance(body, dict):
        return ["request body must be a JSON object"]

    tasks = body.get("tasks")
    if "tasks" not in body:
        errors.append("missing tasks")
    elif not isinstance(tasks, list):
        errors.append("tasks must be a list")
    elif len(tasks) > MAX_TASKS:
        errors.append(f"tasks must hold at most {MAX_TASKS} tasks, got {len(tasks)}")

    deadline = body.get("deadline_day")
    if "deadline_day" not in body:
        errors.append("missing deadline_day")
    elif type(deadline) is not int:
        errors.append("deadline_day must be an integer")

    if not isinstance(tasks, list):
        return errors

    ids = set()
    seen_ids = set()
    for index, task in enumerate(tasks):
        prefix = f"tasks[{index}]"
        if not isinstance(task, dict):
            errors.append(f"{prefix} must be an object")
            continue
        for field in ("id", "name", "owner", "duration_days", "depends_on"):
            if field not in task:
                errors.append(f"{prefix} missing {field}")
        task_id = task.get("id")
        if "id" in task and not isinstance(task_id, str):
            errors.append(f"{prefix} id must be a string")
        elif isinstance(task_id, str):
            if task_id in seen_ids:
                errors.append(f"{prefix} duplicate id {task_id}")
            seen_ids.add(task_id)
            ids.add(task_id)
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

    for index, task in enumerate(tasks):
        if not isinstance(task, dict):
            continue
        depends_on = task.get("depends_on")
        if not isinstance(depends_on, list):
            continue
        unknown = set(depends_on) - ids
        if unknown:
            errors.append(f"tasks[{index}] depends on unknown id {sorted(unknown)[0]}")

    return errors
