# Long Arc Step8 Eval: long_arc_step8_case01_10ch

- source_case_dir: `evals/romance/cases`
- cases: `1`
- generated: `True`
- target_chapters: `10`
- batch_size: `2`
- average_score: `9.42`
- verdict_counts: pass=1, warn=0, blocked=0

## romance_case_01_court_return

- source: `evals/romance/cases/romance_case_01_court_return/steps.json`
- generated_step8_path: `evals/romance/reports/long_arc_step8_case01_10ch/romance_case_01_court_return/generated_steps.json`
- chapter_count: `10`
- verdict: `pass`
- average_score: `9.42`
- warning_metrics: None
- blocking_metrics: None

| metric | score | reason |
| --- | ---: | --- |
| story_spine_alignment | 10.00 | aligned_chapters=10/10, functional_briefs=10/10 |
| genre_tone_consistency | 9.58 | style=克制、压迫、潜台词强的古言言情 克制、压迫、潜台词强的古言言情; relation_hits=6, pressure_hits=11 |
| chapter_chain_causality | 10.00 | incoming_hooks=9/9, ending_to_incoming_overlap=9/9 |
| escalation_curve | 9.60 | early_intensity=3.0, late_intensity=3.33, scene_engines=4, turn_chapters=10/10 |
| character_arc_alignment | 9.50 | known_focus=10/10, arc_ready=10/10, premature_closure=0 |
| twist_seed_payoff | 9.60 | active_twists=Counter({'twist_false_testimony': 10, 'twist_marriage_as_shield': 10}), clue_chapters=10/10, guarded=10/10 |
| line_interlock | 8.90 | line_spread=2/2, multi_line_chapters=10/10, dominant_ratio=0.50 |
| reader_retention_curve | 9.00 | ch3:strong_endings=3/3; ch10:strong_endings=3/3 |
| information_budget_control | 9.00 | controlled=10/10, overloaded=0 |
| repetition_plateau | 9.00 | repeated_pairs=0/9, repeated_scene_engine=0/9 |
