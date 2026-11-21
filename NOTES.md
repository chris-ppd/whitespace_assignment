# Notes

## Time spent

## What I did

## What I cut and why

## What is not ready

## What I would do next and a rough estimate

## How I used AI tools

## Environment variables my review command needs

## Scheduler rulings

- `""` is a real serialized owner; `null` is the unlimited one (the checker treats them differently).
- Duplicate `depends_on` entries: accepted upstream, deduped inside the solver; never rejected.
- Reference check = set-difference in a second pass (forward references are legal).
- Considered and cut: CPM lower-bound redundant constraint (unnecessary at n <= 60).
- Solver determinism: defaults untouched — end_day is unique, layout is free.
