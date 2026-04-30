# Beat Plan Eval: six_upgrades_beat_plan

- provider: `deepseek`
- model: `deepseek-v4-pro`
- generated_at: `2026-04-30T03:07:25.694266+00:00`
- cases: `3`
- average_score: `8.46`
- verdict_counts: pass=2, warn=0, blocked=1

## Average Scores

| metric | score |
| --- | ---: |
| adjacent_separation_score | 6.90 |
| beat_count_fit | 9.20 |
| beat_uniqueness_score | 7.60 |
| contract_coverage_score | 9.67 |
| dramatic_pressure_flow_score | 10.00 |
| must_not_repeat_quality | 9.21 |
| progression_clarity_score | 6.61 |

## romance_case_01_court_return

- title: `围宫请婚的旧案重逢`
- verdict: `blocked`
- beat_count: `4` (target `4`)
- average_score: `7.09`
- llm_calls: `3` (context=1, planning=2)
- planning_prompt_chars: `21763`
- warnings: beat_uniqueness_score is blocking-level weak (4.00).; adjacent_separation_score is blocking-level weak (2.10).; progression_clarity_score is blocking-level weak (5.60).

| metric | score | reason |
| --- | ---: | --- |
| adjacent_separation_score | 2.10 | Adjacent beats should hand off consequence, not restate the same job with different wording. |
| beat_count_fit | 9.20 | Beat count fits best when it stays near the pace contract target and the scene-engine range. |
| beat_uniqueness_score | 4.00 | Each beat should add a non-redundant value turn instead of rephrasing the same dramatic job. |
| contract_coverage_score | 9.00 | A strong beat plan visibly cashes the chapter contract instead of inventing a parallel mini-outline. |
| dramatic_pressure_flow_score | 10.00 | Dramatic pressure rises when beats carry action, human reaction, cost, and hook instead of summary-only movement. |
| must_not_repeat_quality | 9.72 | Per-beat anti-repeat guards work best when they are present, specific, and clearly inherit chapter-level repeat bans. |
| progression_clarity_score | 5.60 | A clear plan opens sharply, changes in the middle, and cuts forward at the end. |

### Overlap Alerts

- `ch_002.sc_001.b002` vs `ch_002.sc_001.b003`: overall=0.30, new_value=0.12, relationship=1.00, clue=0.00, end_state=0.00
- `ch_002.sc_001.b001` vs `ch_002.sc_001.b003`: overall=0.30, new_value=0.12, relationship=1.00, clue=0.00, end_state=0.00
- `ch_002.sc_001.b003` vs `ch_002.sc_001.b004`: overall=0.29, new_value=0.10, relationship=1.00, clue=0.00, end_state=0.00
- `ch_002.sc_001.b001` vs `ch_002.sc_001.b002`: overall=0.28, new_value=0.09, relationship=1.00, clue=0.00, end_state=0.00

## romance_case_02_xianxia_rival_trial

- title: `心声同生契的规则秘境`
- verdict: `pass`
- beat_count: `4` (target `4`)
- average_score: `9.14`
- llm_calls: `4` (context=1, planning=3)
- planning_prompt_chars: `34635`
- warnings: None

| metric | score | reason |
| --- | ---: | --- |
| adjacent_separation_score | 9.30 | Adjacent beats should hand off consequence, not restate the same job with different wording. |
| beat_count_fit | 9.20 | Beat count fits best when it stays near the pace contract target and the scene-engine range. |
| beat_uniqueness_score | 9.40 | Each beat should add a non-redundant value turn instead of rephrasing the same dramatic job. |
| contract_coverage_score | 10.00 | A strong beat plan visibly cashes the chapter contract instead of inventing a parallel mini-outline. |
| dramatic_pressure_flow_score | 10.00 | Dramatic pressure rises when beats carry action, human reaction, cost, and hook instead of summary-only movement. |
| must_not_repeat_quality | 8.90 | Per-beat anti-repeat guards work best when they are present, specific, and clearly inherit chapter-level repeat bans. |
| progression_clarity_score | 7.20 | A clear plan opens sharply, changes in the middle, and cuts forward at the end. |

## romance_case_03_urban_reunion_comedy

- title: `全网直播事故里的前任救场`
- verdict: `pass`
- beat_count: `3` (target `3`)
- average_score: `9.14`
- llm_calls: `4` (context=1, planning=3)
- planning_prompt_chars: `35358`
- warnings: None

| metric | score | reason |
| --- | ---: | --- |
| adjacent_separation_score | 9.30 | Adjacent beats should hand off consequence, not restate the same job with different wording. |
| beat_count_fit | 9.20 | Beat count fits best when it stays near the pace contract target and the scene-engine range. |
| beat_uniqueness_score | 9.40 | Each beat should add a non-redundant value turn instead of rephrasing the same dramatic job. |
| contract_coverage_score | 10.00 | A strong beat plan visibly cashes the chapter contract instead of inventing a parallel mini-outline. |
| dramatic_pressure_flow_score | 10.00 | Dramatic pressure rises when beats carry action, human reaction, cost, and hook instead of summary-only movement. |
| must_not_repeat_quality | 9.02 | Per-beat anti-repeat guards work best when they are present, specific, and clearly inherit chapter-level repeat bans. |
| progression_clarity_score | 7.03 | A clear plan opens sharply, changes in the middle, and cuts forward at the end. |
