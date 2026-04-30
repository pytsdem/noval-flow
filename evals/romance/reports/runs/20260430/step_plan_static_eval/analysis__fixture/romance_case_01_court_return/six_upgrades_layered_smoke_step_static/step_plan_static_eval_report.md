# Step Plan Eval: six_upgrades_layered_smoke_step_static

- source_case_dir: `evals\romance\cases`
- cases: `1`
- average_score: `6.97`
- verdict_counts: pass=0, warn=1, blocked=0

## romance_case_01_court_return

- source: `evals\romance\cases\romance_case_01_court_return\steps.json`
- verdict: `warn`
- average_step_score: `6.97`
- warning_steps: step_4, step_5, step_6, step_7, step_8
- blocking_steps: None

| step | score | warnings |
| --- | ---: | --- |
| step_1 premise | 7.76 | None |
| step_2 story_engine | 7.79 | pressure_system |
| step_3 characters | 7.50 | None |
| step_4 event_timeline | 6.74 | relationship_impact, hook_density |
| step_5 character_milestones | 6.61 | cost_alignment |
| step_6 twists | 6.55 | relationship_reprice |
| step_7 story_lines | 6.65 | line_separation |
| step_8 chapter_briefs | 6.13 | opening_hook, ending_pull |
