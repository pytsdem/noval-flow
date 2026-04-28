# Implementation Summary

## Current Change
- Rebuilt the cross-tone smoke suite with higher-concept case hooks instead of plain subgenre labels.
- `romance_case_02_xianxia_rival_trial`: xianxia + book-entry + inner-voice + rule-trial + same-life contract.
- `romance_case_03_urban_reunion_comedy`: urban workplace + livestream crisis + exes reunion + sabotage pressure.
- Kept `romance_case_01_court_return` as the active historical anchor.
- Moved the older unused `romance_case_02_sickbed_truce` and `romance_case_03_betrothal_banquet` fixtures to `evals/romance/cases_legacy/` so default runs do not spend cost on them.
- Colocated offline Step1-8 assets under `evals/romance/cases/<case_id>/steps.json`; removed the standalone `evals/romance/step_fixtures/` tree.
- Thickened each static Step1-8 asset with planning objective, story engine, relationship network, event timeline, milestone grid, 2 twist designs, 2 story lines, and Step8 first-three retention context.
- Further strengthened the test set world/character layer: each active case now has 8 functional world rules, 5 worldbuilding detail sections, 4 character cards, and deep character cards for Step fixtures.
- Added fixture assertions so future test assets must keep non-trivial world rules, worldbuilding detail, developed character axes, twist designs, story lines, and first-three chapter briefs.
- Added a single lightweight Step1-8 static eval runner: `evals.romance.runners.step_plan_static_eval`.
- Removed the redundant standalone Step8 eval runner/tests after folding Step8 checks into the unified Step1-8 static eval.
- Moved eval CLI entrypoints into `evals/romance/runners/` with purpose-first names: `chapter_quality_eval`, `step_plan_static_eval`, `historical_step_gate_eval`, `workflow_diagnostics_eval`, and `eval_run_comparison`.

## Trend Review Notes
- The new smoke cases are built around mechanism hooks: book-entry / inner voice / rules, and livestream workplace crisis / exes / sabotage.
- Avoid judging light cases as worse just because they are less angsty.

## Scope Guard
- No generation chain changes.
- No writer fields added.
- No generation pass added.
- No beat strategy changes.
- No large eval architecture rewrite.
- No LLM eval run in this round.
