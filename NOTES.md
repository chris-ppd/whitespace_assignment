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

## Review rulings

- Model: OpenRouter's free `nvidia/nemotron-3.5-super-vl:free` via the Anthropic-compatible endpoint; the pipeline is model-agnostic — `REVIEW_MODEL` upgrades it with zero code change.
- Quotes are grounded by code, not trusted from the model: collapse → substring fast path, else difflib line-window repair, threshold 0.9 (start high — lowering trades loud failures for silent wrong anchors).
- Findings quote `null` is the contract's honest escape hatch; an unanchorable TASK quote fails the run loudly (exit 1) — silently dropping a task would cascade through `depends_on` and change the verdict.
- Validation is hand-written to mirror the checker's strict typing (bools and numeric strings rejected), collect-all, so one corrective retry sees every problem at once.
- Env vars: `OPENROUTER_API_KEY` required, `REVIEW_MODEL` optional; the deployed app runs keyless from the stored reviews in `data/reviews/`.
