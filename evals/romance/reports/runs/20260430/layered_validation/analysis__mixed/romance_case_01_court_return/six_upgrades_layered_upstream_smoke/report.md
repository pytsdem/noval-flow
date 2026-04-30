# Layered Validation: six_upgrades_layered_upstream_smoke

- generated_at: `2026-04-30T05:59:08.351702+00:00`
- cases: `romance_case_01_court_return`
- fast_case_ids: `romance_case_01_court_return`
- deep_case_ids: `(none)`

## Layers

1. step plan static: `done` score=6.97
   - report: `runs\20260430\step_plan_static_eval\analysis__fixture\romance_case_01_court_return\six_upgrades_layered_upstream_smoke_step_static\step_plan_static_eval_report.md`
2. beat plan eval: `done` score=9.14
   - report: `runs\20260430\beat_plan_eval\deepseek__deepseek-v4-pro\romance_case_01_court_return\six_upgrades_layered_upstream_smoke_beat_plan\beat_plan_eval_report.md`
3. fast prose eval: `done` core={'romance_tension_score': 0.0, 'relationship_progression_score': 0.0, 'emotional_resonance_score': 0.0, 'hook_score': 0.0, 'character_attraction_score': 0.0, 'continuity_score': 0.0, 'mind_state_consistency_score': 0.0, 'redundancy_score': 0.0}
   - report: `runs\20260430\chapter_eval\deepseek__deepseek-v4-pro\romance_case_01_court_return\six_upgrades_layered_upstream_smoke_chapter_fast\chapter_eval_report.md`
4. deep prose eval: `skipped` core={}
   - report: ``

## Notes
- Use this runner before any all-case deep replay. It pushes expensive deep prose validation behind cheaper upstream checks.
- By default only a bounded subset of non-blocked cases escalates to fast/deep prose, which prevents multi-hour all-case deep loops from becoming the first validation pass.
- If fast prose already regresses badly, stop there and fix the writer before paying for more deep cases.
