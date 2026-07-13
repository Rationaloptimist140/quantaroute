# QuantaRoute Codex Instructions

## Project Context

You are working on **QuantaRoute** (`quantaroute.co.uk`), a route optimisation
tool for UK gig economy drivers and couriers. The product is live and deployed
on Render.

The owner is the sole owner and developer of QuantaRoute. Codex is the
development assistant. Codex does not have authority to make architectural,
product, or deployment decisions without explicit written approval from the
owner. Every proposed change must be reviewed and approved by the owner before
it goes anywhere near production.

## Golden Rules

1. **Never touch the production route flow.** The live API at
   `quantaroute.co.uk` must continue to behave exactly as it does now. No API
   behaviour changes, no QAOA activation in production, no external solver
   calls, and no Render config changes unless explicitly instructed.

2. **Quantum/QAOA work is offline research only.** Quantum experiments,
   benchmarking, and QAOA-related code must live in `scripts/` and `tests/`,
   never in the production route pipeline. Export route problems to JSON for
   offline analysis. Never call external quantum APIs or solvers from
   production code.

3. **Always commit completed work.** Do not leave files untracked or unstaged
   when finishing a task. Stage and commit new and modified files with a clear,
   descriptive commit message. If unsure whether to commit, ask first.

4. **Always write tests.** Every new script, function, or module should have
   corresponding tests. All tests must pass before committing. Investigate
   pytest warnings; fix them when practical, or document why they remain.

5. **No binary files in git.** PDFs, images, compiled binaries, and other
   non-text files should be gitignored rather than newly tracked. Do not add
   secrets, credentials, generated exports, or local route-sheet PDFs to git.

6. **No secrets, keys, or credentials in code or commits.** API keys, Render
   config, environment variables, and credentials must stay out of tracked
   files. `.env` files must stay gitignored.

7. **Never push without approval.** Local commits are allowed when requested or
   when finishing approved work. Do not run `git push` unless explicitly told.

## Code Standards

- Python 3.10+ compatible code.
- Type hints on new function signatures.
- Docstrings on public functions and classes.
- Follow PEP 8.
- Keep functions small and single-purpose.
- Use descriptive variable and function names.
- Use comments only where the logic is not obvious.

## Git Workflow

- Work on `master` unless told otherwise.
- Use one commit per logical change.
- Commit message format: `type: brief description`, for example:
  - `feat: add nearest-neighbour baseline to export script`
  - `fix: isolate public API geocoding test storage`
  - `docs: update quantum experiments guide`
- Run `git status` before and after every commit.
- Do not stage or commit unrelated user files.

## Testing Standards

- Use `pytest`.
- Tests live in `tests/`.
- Test files use the `test_<module_name>.py` naming pattern.
- New tests should clearly show what behaviour they verify.
- Run `python -m pytest -q` before committing.
- Run `python -m pytest -W all -q` when warning behaviour matters.
- Prefer meaningful coverage over line-count padding.

## Current Production Guardrails

- QuantaRoute is live on Render.
- Postgres is active in production.
- `/health` is lightweight and fast.
- `/health/deep` provides storage diagnostics.
- Production route logic remains:
  - fewer than 8 geocoded stops: exact brute force
  - 8 or more geocoded stops: nearest-neighbour heuristic
- `algorithm_used` appears in API responses and route sheets.
- `backend/services/qaoa.py` exists, but QAOA is not active in production.
- `QUANTUM_EXPERIMENTS.md` documents the Strangeworks/QUBO/QAOA research plan.

## Project Structure Notes

```text
QuantaRoute/
├── .gitignore
├── CODEX_INSTRUCTIONS.md
├── QUANTUM_EXPERIMENTS.md
├── scripts/
│   └── export_route_problem.py
├── tests/
│   └── test_export_route_problem.py
├── exports/
│   └── generated JSON exports, gitignored
└── backend/, frontend/, mcp/
```

Production code lives mainly in `backend/`, `frontend/`, and `mcp/`. Do not
change production route behaviour without explicit approval.

## JSON Export Schema For Quantum Benchmarking

Route problem exports should follow this shape:

```json
{
  "schema_version": "quantaroute.route_problem_export.v1",
  "problem_id": "string",
  "start_address": "string",
  "end_address": "string",
  "input_stops": ["array of address strings"],
  "ordered_stops": ["array of address strings in optimised order"],
  "distance_matrix_km": [[0.0]],
  "baseline_algorithm_used": "exact brute force",
  "original_distance_km": 0.0,
  "optimised_distance_km": 0.0,
  "distance_saved_km": 0.0,
  "estimated_saving_percent": 0.0,
  "notes": ["array of strings"]
}
```

## Autonomous Work Allowed

- Read and explore the codebase.
- Write and run tests.
- Create new offline research scripts in `scripts/` and tests in `tests/`.
- Commit approved work locally with clear messages.
- Run `py_compile`, `pytest`, and warning checks.
- Update `QUANTUM_EXPERIMENTS.md`.
- Suggest improvements, refactors, or new features as proposals.

## Ask First

Ask for explicit approval before:

- changing production route flow or API behaviour
- changing Render deployment config
- adding dependencies
- changing `.env` or environment variables
- running `git push`
- changing the live domain or DNS
- changing user-facing behaviour at `quantaroute.co.uk`
- making architectural decisions or restructures
- integrating external APIs or services
- changing authentication or security

## Start Of Task Checklist

1. Run `git status`.
2. Confirm the branch.
3. State what work is planned and which files will be touched.
4. Wait for confirmation if the work goes beyond the approved task or touches
   production behaviour.
5. After finishing, run `git status` again and report the result.

## Reporting Format

```text
## Done

What I did:
- ...

Files changed:
- ...

Tests:
- ...

Git status:
- ...

Commits made:
- ...

Questions for you:
- None
```
