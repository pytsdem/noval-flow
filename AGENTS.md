# AGENTS Guide

## Project Goal

`noval-flow` is a Chinese serialized-romance generation framework. When making changes, optimize for these outcomes in roughly this order:

1. `romance_tension_score`
2. `relationship_progression_score`
3. `emotional_resonance_score`
4. `hook_score`
5. `character_attraction_score`
6. `continuity_score`
7. `mind_state_consistency_score`
8. lower `redundancy_score`
9. lower cost and fewer unnecessary full rewrites
10. better front-end usability, operator feedback, and debugging clarity in the local web console

## Important Directories

- `src/novel_flow/agents/`: core blueprint, writer, critic, director, memory agents
- `src/novel_flow/tools/`: writer/planner/review/rewrite tools used by the chapter workflow
- `src/novel_flow/storage/`: SQLite persistence and run history access
- `src/novel_flow/server.py`: embedded web console UI, API wiring, and operator workflow
- `prompts/`: prompt templates for writer, critic, director, and knowledge generation
- `evals/romance/`: romance eval harness, historical diagnostics, aggregate analysis, comparison tools
- `tools/`: foundational exporter, seeding, and optional helper scripts
- `skills/novel_self_improve/`: Codex runbook for framework self-optimization
- `tests/`: regression tests
- `data/`: local databases and runtime artifacts; do not treat as committed fixtures

## Repo Boundary

The repo should provide stable primitives, not the whole optimization brain.

- Repo responsibilities: fixed self-improve cases, fixed `book_id` bindings, test-db visibility, book creation, step-generation entrypoints, chapter-generation entrypoints, run history, and reusable eval primitives.
- Codex responsibilities: inspect evidence, decide whether to reuse or regenerate, diagnose root cause, choose one optimization target, compare baseline vs candidate, and decide whether to keep a change.
- Optional helper scripts may gather evidence faster, but they do not replace Codex analysis or decision-making.

## Historical Case Workflow

Use real chapter history as the primary optimization signal. Export standardized cases before diagnosing workflow problems:

```powershell
python -m tools.export_eval_cases --db data/novel_flow.db --output-dir evals/romance/exported_cases/latest --limit 20 --sample-mode low_score
```

Supported sampling strategies:

- `latest`
- `low_score`
- `high_cost`
- `tagged --tags high_tension_romance opening_hook`

Then run workflow diagnostics on the exported cases:

```powershell
python -m evals.romance.run_workflow_diagnostics --cases evals/romance/exported_cases/latest --label latest_diagnostics
```

Run upstream step gate checks before trusting the exported cases for chapter generation:

```powershell
python -m evals.romance.run_step_evals --cases evals/romance/exported_cases/latest --label latest_step_eval
```

## Replay Eval Workflow

Use two validation sets:

1. Historical exported cases from the database
2. Hand-maintained requirement cases in `evals/romance/cases/`

The self-improve requirement cases are fixed "new novel input" fixtures that seed deterministic test books in `data/novel_flow_test.db`:

- `evals/romance/cases/romance_case_01_court_return.json` -> `test_self_improve_court_return`
- `evals/romance/cases/romance_case_02_sickbed_truce.json` -> `test_self_improve_sickbed_truce`
- `evals/romance/cases/romance_case_03_betrothal_banquet.json` -> `test_self_improve_betrothal_banquet`

Seed or reseed them with:

```powershell
python -m tools.seed_self_improve_cases --db data/novel_flow_test.db --cases-dir evals/romance/cases
```

When using the `novel_self_improve` skill, prefer these fixed `book_id` bindings over title matching.

Run fixture requirement cases:

```powershell
python -m evals.romance.run_romance_evals --cases-dir evals/romance/cases --label fixture_baseline
```

Replay exported historical cases:

```powershell
python -m evals.romance.run_romance_evals --cases-dir evals/romance/exported_cases/latest --label historical_baseline
```

Compare baseline vs candidate:

```powershell
python -m evals.romance.run_case_comparison --baseline evals/romance/reports/historical_baseline/summary.json --candidate evals/romance/reports/historical_candidate/summary.json
```

## Manual Baseline Commands

If you want to prepare a manual baseline snapshot, run the foundational commands directly instead of a bundled self-improve script:

```powershell
python -m tools.export_eval_cases --db data/novel_flow.db --output-dir evals/romance/exported_cases/latest --limit 10 --sample-mode low_score
python -m evals.romance.run_step_evals --cases evals/romance/exported_cases/latest --label latest_step_eval
python -m evals.romance.run_workflow_diagnostics --cases evals/romance/exported_cases/latest --label latest_diagnostics
python -m evals.romance.run_romance_evals --cases-dir evals/romance/cases --label fixture_baseline
```

## Development Rules

- Diagnose workflow failures with intermediate artifacts, not only final prose.
- Use step eval as the upstream gate: if brief/state/writing-pack/block-plan quality is blocked, fix upstream artifacts before spending cost on chapter generation.
- Optimize one primary workflow layer or one failure family per iteration.
- Do not game the judge prompt to inflate scores.
- Do not accept improvements that materially hurt continuity, mind-state consistency, or cost efficiency.
- Treat the web console and operator UX as part of the framework. If a change affects authoring, monitoring, debugging, or artifact inspection, validate the front-end behavior too.
- If the change touches `src/novel_flow/server.py` or browser-visible workflow, check the UI path directly, not only backend tests.
- Clean up temporary files created during optimization work. Do not leave ad-hoc scratch files, one-off dumps, or obsolete debug outputs in the repo after the task is done.
- Prefer dedicated temporary locations under `data/` while working, and delete throwaway artifacts before finishing. Keep only reusable fixtures, stable reports, or intentionally committed examples.
- If a new helper script or report directory is needed, make it part of the repo structure intentionally; otherwise remove it after verification.
- Prefer patch-oriented fixes over broadening full-rewrite behavior.
- Keep historical cases and fixture cases both green enough before keeping a change.

## Minimum Verification

Before keeping a change, run:

```powershell
python -m py_compile evals/romance/*.py tools/*.py
python -m unittest tests.test_eval_case_exporter tests.test_workflow_diagnostics tests.test_step_evals tests.test_case_comparison tests.test_novel_self_improve_skill tests.test_requirement_cases
```

If the change touches the existing writer workflow, also run relevant repo tests:

```powershell
python -m unittest tests.test_romance_eval_harness tests.test_writing_chapter_agent tests.test_schema_and_context
```

## Done Criteria

Keep a candidate change only when all of these are true:

- core romance metrics improve on average
- continuity, mind-state consistency, and redundancy do not regress materially
- cost is lower or not meaningfully worse
- tests pass
- diagnostics do not show a worse dominant root layer than baseline
