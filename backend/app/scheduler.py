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
