from ortools.sat.python import cp_model


def solve(tasks):
    """Return the earliest-finish legal schedule as [{id, start_day, end_day}].

    A CP-SAT model with one interval per task, one precedence constraint per
    dependency edge and one NoOverlap per owner, minimizing the makespan.
    The horizon (sum of all durations) always admits the fully serial
    schedule, so the model is satisfiable whenever the graph is acyclic —
    which find_cycle guarantees before solve is called.
    """
    if not tasks:
        return []

    duration = {t["id"]: t["duration_days"] for t in tasks}
    horizon = sum(duration.values())

    model = cp_model.CpModel()
    starts = {}
    intervals = {}
    for t in tasks:
        task_id = t["id"]
        start = model.NewIntVar(0, horizon - duration[task_id], f"start_{task_id}")
        starts[task_id] = start
        intervals[task_id] = model.NewFixedSizeIntervalVar(
            start, duration[task_id], f"interval_{task_id}"
        )

    for t in tasks:
        for dep in dict.fromkeys(t["depends_on"]):
            if dep in starts:
                model.Add(starts[t["id"]] >= starts[dep] + duration[dep])

    by_owner = {}
    for t in tasks:
        if t["owner"] is not None:
            by_owner.setdefault(t["owner"], []).append(intervals[t["id"]])
    for group in by_owner.values():
        model.AddNoOverlap(group)

    makespan = model.NewIntVar(0, horizon, "makespan")
    model.AddMaxEquality(makespan, [starts[t["id"]] + duration[t["id"]] for t in tasks])
    model.Minimize(makespan)

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 7.5
    status = solver.Solve(model)
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        raise RuntimeError(f"scheduling failed with status {solver.StatusName(status)}")

    entries = [
        {"id": t["id"], "start_day": int(solver.Value(starts[t["id"]])), "end_day": int(solver.Value(starts[t["id"]])) + duration[t["id"]]}
        for t in tasks
    ]
    entries.sort(key=lambda entry: (entry["start_day"], entry["id"]))
    return entries


def find_cycle(tasks):
    """Return the ids of one real dependency loop, in loop order, or None.

    Depth-first search with an on-path set (gray) and a done set (black).
    Hitting an on-path node means the path from that node down to here is
    the loop. Self-dependencies fall out of the same rule.
    """
    depends_on = {t["id"]: list(t.get("depends_on", [])) for t in tasks}
    done = set()
    on_path = set()
    path = []

    def visit(node):
        on_path.add(node)
        path.append(node)
        for dep in depends_on.get(node, []):
            if dep not in depends_on:
                continue
            if dep in on_path:
                return path[path.index(dep):]
            if dep not in done:
                cycle = visit(dep)
                if cycle:
                    return cycle
        path.pop()
        on_path.discard(node)
        done.add(node)
        return None

    for task_id in depends_on:
        if task_id not in done:
            cycle = visit(task_id)
            if cycle:
                return cycle
    return None


def schedule(tasks, deadline_day):
    by_id = {t["id"]: t for t in tasks}

    def end_of(task):
        start = max([end_of(by_id[d]) for d in task["depends_on"]], default=0)
        return start + task["duration_days"]

    items = []
    for t in tasks:
        end = end_of(t)
        items.append({"id": t["id"], "start_day": end - t["duration_days"], "end_day": end})

    end_day = max([i["end_day"] for i in items], default=0)
    return {
        "status": "scheduled",
        "schedule": items,
        "end_day": end_day,
        "deadline_day": deadline_day,
        "meets_deadline": end_day <= deadline_day,
        "days_late": max(0, end_day - deadline_day),
        "cycle": [],
    }
