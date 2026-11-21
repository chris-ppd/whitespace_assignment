# Notes

## Time spent

About eight hours all in: two designing and writing implementation prompts, three running the agent and reviewing what it wrote, one on the UI, and the rest on tests, the stored review outputs and deployment. The take-home is sized for two; I spent the extra on making the AI part trustworthy rather than on more features.

## What I did

- **Scheduler.** CP-SAT (OR-Tools, pinned): one interval per task, a precedence constraint per dependency edge, one NoOverlap per non-null owner — a null owner is unbounded. The objective is the smallest overall end_day; the deadline stays out of the model and is compared afterwards. A DFS names one real simple cycle and answers HTTP 200 with status "cycle".
- **Review pipeline.** `./review` calls OpenRouter's free Nemotron through the Anthropic-compatible endpoint, then code decides: strict collect-all shape validation, quote grounding (whitespace-collapse substring fast path, difflib line-window repair at 0.9), a corrective retry ladder, and a non-zero exit that never writes an unusable file.
- **App and UI.** One FastAPI process serves the API and the built page. The page leads with the verdict (on time / days late / cycle), highlights the exact quoted span of the plan on hover, and styles findings and schedule after BRAND.md with zero new frontend dependencies.
- **Tests and regeneration.** pytest covers solver optimality, cycle shapes, API refusals, and the review pipeline's validation, anchoring and retries. `make reviews` rebuilds all three stored reviews with the contract checker gated after each one.
- **Deployment.** Render free tier, the provided Dockerfile untouched, nothing to configure in production.

## What I cut and why

- **Correcting a review in the page** (Nora's third wish). The endpoint and solver already support it; the UI hour went to verdict-first and quote anchoring, her first two wishes. That was the last requirements she speicified with the least priority, and it's something I would iterate over with her together
- **Frontend unit tests.** The quote matcher is a pure module ready to test; the hour ran out first.
- **AI in the app.** Optional per the README, and the stored reviews already answer her questions.

## What is not ready

- The correction flow above: today she can read the review, not edit it.
- Stable extraction: the free model's findings can shift between runs. The stored reviews are frozen so the deployed page stays consistent; a regeneration is not guaranteed to reproduce them.
- Findings show in model order, not ranked by importance.

## What I would do next and a rough estimate

1. Correction flow — editable task table, POST /api/schedule, verdict updates live; the backend needs nothing. 2–3 hours.
2. UI tests for the quote matcher. 30 minutes.
3. A model-provided severity and ranked findings. About an hour.
4. A keep-alive ping so the free instance stays warm. 10 minutes.

## How I used AI tools

An AI assistant helped me pressure-test the design, then I wrote each pipeline up as an implementation prompt for a Claude Code agent: decisions, function signatures, thresholds and the exact test list. I checked what it wrote by gating every commit on pytest and both contract checkers, feeding it adversarial fixtures (a prose-only plan, a plan full of traps), and reading the load-bearing code myself — validation, anchoring, exit paths, the solver model.

## Environment variables my review command needs

- `OPENROUTER_API_KEY` — required, an OpenRouter key.
- `REVIEW_MODEL` — optional, defaults to `nvidia/nemotron-3.5-super-vl:free`.

The deployed app needs neither; it serves the stored reviews in `data/reviews/`.

## Scheduler rulings

- `""` is a real serialized owner and keeps a person busy; `null` is the unlimited one. The checker treats them differently, so the solver does too.
- Duplicate `depends_on` entries are accepted upstream and deduped inside the model, never rejected.
- Reference checking is a set-difference in a second pass, so forward references stay legal.
- Considered and cut: the CPM lower bound as a redundant constraint — provably unnecessary at n ≤ 60.
- Solver defaults are untouched: the optimal end_day is unique, the day-level layout inside it is free.

## Review rulings

- Model: OpenRouter's free `nvidia/nemotron-3.5-super-vl:free` over the Anthropic-compatible endpoint, which keeps the take-home at zero API cost. The pipeline is model-agnostic — `REVIEW_MODEL` upgrades it with zero code changes.
- Quotes are grounded by code, not trusted from the model: collapse → substring fast path, else difflib line-window repair, threshold 0.9. Starting high is deliberate — lowering it trades loud failures for silent wrong anchors.
- A finding quote that cannot be anchored becomes `null`, the contract's honest escape hatch; an unanchorable task quote fails the run loudly with exit 1, because silently dropping a task would cascade through `depends_on` and change the verdict.
- Validation is hand-written to mirror the checker's strict typing (bools and numeric strings rejected) and collects every error, so one corrective retry sees every problem at once.