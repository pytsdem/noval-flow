# Long Arc Step8 Eval: long_arc_step8_static_smoke

- source_case_dir: `evals/romance/cases`
- cases: `3`
- generated: `False`
- target_chapters: `0`
- batch_size: `0`
- average_score: `7.93`
- verdict_counts: pass=0, warn=0, blocked=3

## romance_case_01_court_return

- source: `evals/romance/cases/romance_case_01_court_return/steps.json`
- generated_step8_path: `None`
- chapter_count: `3`
- verdict: `blocked`
- average_score: `8.04`
- warning_metrics: None
- blocking_metrics: line_interlock, reader_retention_curve

| metric | score | reason |
| --- | ---: | --- |
| story_spine_alignment | 10.00 | aligned_chapters=3/3, functional_briefs=3/3 |
| genre_tone_consistency | 8.53 | style=克制、压迫、潜台词强的古言言情 克制、压迫、潜台词强的古言言情; relation_hits=3, pressure_hits=11 |
| chapter_chain_causality | 10.00 | incoming_hooks=2/2, ending_to_incoming_overlap=2/2 |
| escalation_curve | 6.87 | early_intensity=3.0, late_intensity=1.0, scene_engines=3, turn_chapters=2/3 |
| character_arc_alignment | 9.50 | known_focus=3/3, arc_ready=3/3, premature_closure=0 |
| twist_seed_payoff | 8.80 | active_twists=Counter({'twist_false_testimony': 3}), clue_chapters=3/3, guarded=3/3 |
| line_interlock | 4.70 | line_spread=1/2, multi_line_chapters=0/3, dominant_ratio=1.00 |
| reader_retention_curve | 4.00 | ch3:strong_endings=0/3 |
| information_budget_control | 9.00 | controlled=3/3, overloaded=0 |
| repetition_plateau | 9.00 | repeated_pairs=0/2, repeated_scene_engine=0/2 |

## romance_case_02_xianxia_rival_trial

- source: `evals/romance/cases/romance_case_02_xianxia_rival_trial/steps.json`
- generated_step8_path: `None`
- chapter_count: `3`
- verdict: `blocked`
- average_score: `7.89`
- warning_metrics: genre_tone_consistency
- blocking_metrics: line_interlock, reader_retention_curve

| metric | score | reason |
| --- | ---: | --- |
| story_spine_alignment | 10.00 | aligned_chapters=3/3, functional_briefs=3/3 |
| genre_tone_consistency | 6.74 | style=轻快、有奇幻画面感、斗嘴中带心动 ; relation_hits=2, pressure_hits=3 |
| chapter_chain_causality | 8.75 | incoming_hooks=2/2, ending_to_incoming_overlap=1/2 |
| escalation_curve | 8.37 | early_intensity=2.0, late_intensity=2.0, scene_engines=3, turn_chapters=2/3 |
| character_arc_alignment | 9.50 | known_focus=3/3, arc_ready=3/3, premature_closure=0 |
| twist_seed_payoff | 8.80 | active_twists=Counter({'twist_inner_voice': 3}), clue_chapters=3/3, guarded=3/3 |
| line_interlock | 4.70 | line_spread=1/2, multi_line_chapters=0/3, dominant_ratio=1.00 |
| reader_retention_curve | 4.00 | ch3:strong_endings=1/3 |
| information_budget_control | 9.00 | controlled=3/3, overloaded=0 |
| repetition_plateau | 9.00 | repeated_pairs=0/2, repeated_scene_engine=0/2 |

## romance_case_03_urban_reunion_comedy

- source: `evals/romance/cases/romance_case_03_urban_reunion_comedy/steps.json`
- generated_step8_path: `None`
- chapter_count: `3`
- verdict: `blocked`
- average_score: `7.86`
- warning_metrics: None
- blocking_metrics: line_interlock, reader_retention_curve

| metric | score | reason |
| --- | ---: | --- |
| story_spine_alignment | 10.00 | aligned_chapters=3/3, functional_briefs=3/3 |
| genre_tone_consistency | 6.92 | style=现代、轻快、对白有节奏，现实事件推动暧昧 ; relation_hits=2, pressure_hits=4 |
| chapter_chain_causality | 7.50 | incoming_hooks=2/2, ending_to_incoming_overlap=0/2 |
| escalation_curve | 9.20 | early_intensity=1.0, late_intensity=2.0, scene_engines=3, turn_chapters=3/3 |
| character_arc_alignment | 9.50 | known_focus=3/3, arc_ready=3/3, premature_closure=0 |
| twist_seed_payoff | 8.80 | active_twists=Counter({'twist_old_breakup': 3}), clue_chapters=3/3, guarded=3/3 |
| line_interlock | 4.70 | line_spread=1/2, multi_line_chapters=0/3, dominant_ratio=1.00 |
| reader_retention_curve | 4.00 | ch3:strong_endings=1/3 |
| information_budget_control | 9.00 | controlled=3/3, overloaded=0 |
| repetition_plateau | 9.00 | repeated_pairs=0/2, repeated_scene_engine=0/2 |
