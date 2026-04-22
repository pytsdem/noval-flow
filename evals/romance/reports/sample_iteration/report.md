# Novel Self-Improve Iteration Report

## 1. Iteration Goal

Improve `writing_pack_layer` so relationship-state and chapter-object constraints survive compression into the writer context.

## 2. Observed Problems

- common low scores: `relationship_progression_score`, `continuity_score`
- common root layer: `writing_pack_layer`
- common root step: `writing_pack_quality_score`
- recurring behavior: exported historical cases trigger rewrite rounds without materially improving the blocking reasons

## 3. Changes

- tighten how `relationship_state_text`, `chapter_payload_text`, and world-rule packets are preserved in the exported case and replay inputs
- keep the change scoped to writing-pack preservation instead of modifying the judge prompt

## 4. Results

- target gains: better relationship movement and fewer chapter-object logic misses
- guard checks: no new continuity regression, no broader full-rewrite default
- validation sets:
  - exported historical cases from the database
  - hand-maintained requirement cases in `evals/romance/cases`

## 5. Conclusion

- keep the change only if baseline vs candidate comparison shows positive core romance deltas
- reject the change if continuity, mind-state consistency, or cost efficiency regress
