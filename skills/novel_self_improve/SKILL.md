# novel_self_improve

Purpose: optimize the novel-generation framework itself through a requirement-first, cache-aware evaluation loop.

Manual invocation only: use this runbook only when the user explicitly asks for `novel_self_improve`, `$novel_self_improve`, or the equivalent global skill by name.

Do not treat broad requests like "optimize the project" or "improve the novel system" as permission to auto-activate this runbook.

When explicitly invoked, use this skill when the goal is to improve the framework, not to hand-edit one chapter.

This is a Codex execution protocol. It does not require the repo's production architecture to be rewritten into the same loop unless the user explicitly asks for that.

## Boundary

- The repo should provide foundational capabilities only: fixed test cases, fixed `book_id` bindings, DB persistence, step-generation entrypoints, chapter-generation entrypoints, run history, and front-end visibility.
- Codex owns the actual self-improvement work: evidence gathering, root-cause analysis, choosing what to optimize, deciding whether to reuse or regenerate, running comparisons, and deciding whether to keep a change.
- Repo helper scripts may assist with evidence collection, but they do not replace Codex judgment.

## Core Positioning

- Input is `3` requirement cases.
- Each requirement case is the raw user string that would be entered when creating a new novel.
- A requirement case is not a frozen chapter case, not a prebuilt chapter brief, and not a hand-written writing pack.
- Codex should use those requirement strings as the primary optimization surface.
- Historical real cases remain useful as supporting evidence, but they do not replace the requirement-first loop.

## Capability Rule

Treat the repo commands below as preferred shortcuts, not as the limit of what Codex is allowed to do.

If a needed capability is missing, stale, or incomplete, Codex should directly do the work by using local evidence sources such as:

- source code
- prompt files
- schemas and workflow wiring
- frontend code and browser-visible operator flows
- SQLite databases
- run logs, stage logs, and saved JSON artifacts
- tests, reports, and diffs

Absence of a wrapper script is not a blocker. Codex should read the repo, query the DB, inspect artifacts, add a small helper script if needed for the current iteration, and continue the loop.

Do not block the loop waiting for a perfect test-book matching system. If the current repo and DB already make it practical to find the intended test novel and its latest step or chapter artifacts, use that evidence and continue.

If the repo does not yet maintain a formal accepted-snapshot registry, Codex may infer reusable step or chapter artifacts from practical local evidence such as `books`, `workflow_states`, `run_outputs`, `chapter_blocks`, and related saved metadata.

The front-end is part of the optimization surface. If the repo exposes a web console, embedded UI, or browser workflow, Codex should treat usability, debugging clarity, artifact visibility, and operator feedback as framework quality concerns rather than out-of-scope polish.

Temporary file hygiene is part of the optimization standard. Use temporary artifacts only when they help diagnosis or verification, keep them in predictable locations while working, and delete throwaway files before finishing so the repo does not accumulate clutter.

Iteration traceability is part of the optimization standard. After each keep/reject decision, update both:

- `evals/romance/reports/self_improve_live/report.md`
- `evals/romance/reports/self_improve_live/iteration_log.md`

Code quality and codebase shape are part of the optimization standard. Novel optimization is not permission to only add more prompts, fields, branches, or helper layers. When a change introduces a new control surface, also inspect what can be removed, merged, or simplified:

- delete stale or superseded prompt text, payload fields, helper scripts, note files, and dead branches
- merge overlapping concepts instead of keeping two names for the same idea
- prefer replacement and simplification over additive branching when both can achieve the same quality gain
- keep ownership boundaries clear so each layer has one reason to exist
- reject "improvements" that rely on piling up redundant configuration or duplicated logic without consolidation

In short: every novel optimization pass should consider both addition and subtraction, and should leave the repo clearer than before whenever practical.

## Practical Optimization Heuristics

Use these as default, reusable heuristics when improving long-form novel quality. They are intentionally generic and should outlive any single experiment.

### Optimize the highest-leverage layer first

- If the chapter contract is weak, do not expect downstream block prompts or polish rules to rescue the chapter consistently.
- Prefer fixing the earliest layer that can prevent the failure, instead of repeatedly patching the latest visible symptom.
- Typical order of leverage is:
  - chapter contract / brief
  - block or beat planning
  - draft execution
  - patch or review behavior
  - final polish

### Treat chapter planning as an execution contract, not a summary

- A good chapter brief should specify what must change, what must be paid, and what must not repeat.
- Prefer concrete contract fields over vague mood labels:
  - relationship movement
  - plot movement
  - cost or consequence
  - hook type
  - forbidden repetition
- If the plan cannot tell later layers what the chapter must accomplish, improve the plan before tuning prose.

### Keep each beat or scene unit responsible for one unique change

- Repetition often comes from adjacent beats carrying the same dramatic job under different wording.
- Each beat should deliver one non-redundant value turn.
- Require clear boundaries between beats:
  - what this beat adds
  - what this beat must not restate
  - what consequence it hands to the next beat

### Prefer action-carried revelation over explanation-carried revelation

- Strong prose usually reveals emotion, relationship shift, and clues through action, props, body reaction, dialogue timing, and consequence.
- Explanatory summary lines are usually lower value than observable dramatic evidence.
- When optimizing prompts, prefer rules that force information to appear through scene behavior before adding interpretation.

### Isolate style variance instead of forking the whole workflow

- If different tone families need different flavor, isolate that variance in a dedicated style layer whenever possible.
- Keep the planning, drafting, patching, and evaluation pipeline shared unless there is strong evidence that the architecture itself must split.
- Tone-specific behavior should usually live in one clear control surface, not be scattered across many prompts.

### Reduce payload duplication before adding stronger instructions

- Repeated or overlapping input fields can cause the model to restate the same meaning in prose.
- Before adding more prompt rules, inspect whether the current payload repeats the same idea through multiple fields.
- Prefer a smaller, sharper execution payload over parallel context blocks that all describe the same state.

### Use explicit length and pacing controls

- Long-form quality degrades when beats overrun their dramatic job and start re-narrating completed material.
- Make length targets, stop conditions, and pacing shape explicit instead of assuming the model will self-regulate.
- Prefer preserving opening pressure, relationship turns, and end hooks over spending excess length on repeated explanation.

### Validate generalization before promoting a default

- A change that helps one tone family or one case may still be a bad default.
- Before keeping a framework-level behavior, test at least one contrasting representative case whenever feasible.
- Do not confuse a strong specialized result with a safe shared default.

### Keep evidence legible and comparable

- Save artifacts in a naming scheme that makes time, model, case, and purpose obvious.
- Keep live reports focused on operator-facing summaries; archive frozen run outputs separately.
- Make it easy to compare baseline vs candidate without reconstructing context from memory.

## Fixed Workflow

### Step 1: Read the active requirement case and its bound test book

- Read the active fixed requirement-case file under `evals/romance/cases/`.
- Treat each case file's `user_input` block as the source-of-truth "new novel" input.
- Use the fixed test-book bindings below instead of guessing by title:
  - `evals/romance/cases/romance_case_01_court_return.json` -> `test_self_improve_court_return`
- The registry file at `evals/romance/self_improve_registry.json` is the quick lookup source for these bindings.
- The seeded novel lives in `data/novel_flow_test.db` and should be visible from the front-end in `test` mode.
- Legacy requirement cases live under `evals/romance/cases_legacy/` and are not part of the default active eval directory.

### Step 2: Inspect the bound test books in the test DB before regenerating

For each fixed `book_id`, inspect `data/novel_flow_test.db` plus repo artifacts for:

- the latest accepted step snapshot
- the latest accepted chapter checkpoints for chapters `1` through `5`

If the current optimization target is mainly chapter prose, patching, review behavior, or frontend visibility, and the accepted step snapshot is still valid, reuse it.

If there is no usable step snapshot, or the current changes touched upstream step behavior, regenerate the steps.

### Step 3: Generate or reuse real steps 1-7

- Use the project's real generation logic.
- Do not fake the step outputs by hardcoding a frozen writing pack.
- If the repo lacks a unified "run steps" command, Codex may call the local agents and services directly or add a temporary helper script for the current iteration.
- Temporary orchestration is allowed, but do not turn the repo's production architecture into this skill loop unless the user explicitly asks for that refactor.

### Step 4: Run the step gate

Evaluate at least these upstream artifacts:

- `brief`
- `relationship_state`
- `mind_state`
- `writing_pack`
- `block_plan`

If the step gate says the upstream artifacts are materially bad, optimize the upstream framework first and do not spend cost on chapter generation yet.

### Step 5: Write chapter 1 only after the step gate clears

- Run the full chapter workflow for chapter `1`.
- Evaluate the resulting prose, workflow diagnostics, and cost behavior.

### Step 6: Use chapter 1 to select the next optimization target

If chapter `1` fails, identify whether the main cause is:

- upstream step quality
- writer behavior
- patch or review behavior
- frontend or observability quality

Choose one main target only for the iteration.

### Step 7: Continue through chapters 2-5 only when the current chapter is acceptable

- If chapter `1` is acceptable, update the accepted chapter `1` checkpoint.
- Then continue to chapter `2`, then `3`, then `4`, then `5`.
- The goal is not only a good opening chapter. The goal is stable quality across `5` chapters.

### Step 8: Compare baseline vs candidate at multiple levels

Compare:

- step-gate deltas
- chapter-level deltas
- aggregated chapter `1..5` deltas
- historical real-case non-regression

### Step 9: Keep or reject

Keep the change only if the candidate improves the overall `1..5 chapter` result without unacceptable regressions in:

- continuity
- mind-state consistency
- redundancy
- cost
- frontend or operator workflow, when affected

If the candidate is worse, reject it and write down the next-best hypothesis instead of keeping the change.

## Cache And Reuse Rules

- Keep only the latest accepted step snapshot for each requirement case.
- Keep only the latest accepted checkpoint for each of chapters `1` through `5` for each requirement case.
- Do not store every attempt.
- Failed attempts may exist as temporary working artifacts only and should be deleted before finishing.
- When optimizing chapter prose, reuse the accepted step snapshot whenever it is still valid.
- Do not rerun upstream work if the current target does not require it.

## Step Snapshot Invalidation

Invalidate the accepted step snapshot if the current changes touch:

- brief generation
- relationship-state generation
- mind-state generation
- writing-pack construction
- block planning
- upstream schema
- upstream prompts

Keep the accepted step snapshot reusable if the current changes touch only:

- chapter prose
- patch behavior
- review behavior
- judge behavior
- frontend display, observability, or operator UX

If uncertain, inspect the changed files and choose targeted invalidation instead of rerunning everything by default.

## Hard Constraints

1. This is a skill-level workflow for Codex, not a demand that the repo's production architecture be rewritten the same way.
2. Do not optimize multiple workflow layers in one iteration.
3. Do not game judge prompts for score inflation.
4. Do not trade away continuity, mind-state consistency, or cost efficiency for one narrow score gain.
5. Do not expand full rewrite by default; prefer patch-oriented repair.
6. Do not diagnose from final text alone; always inspect intermediates.
7. Do not rebuild steps when a valid accepted step snapshot can be reused for the current target.
8. Do not keep all attempts; only accepted snapshots and checkpoints should persist.
9. Do not treat frontend regressions as acceptable collateral damage if they block authors or hide debugging information.
10. Do not leave behind one-off temporary files, debug dumps, or scratch directories when the task is complete.
11. Do not convert one-off helper orchestration into a permanent repo control path unless the user explicitly asks for it.
12. Do not treat additive complexity as free; whenever you add a new prompt rule, field, branch, or helper, check whether an older layer can be removed, merged, or renamed away.

## Foundational Commands

These are foundational repo capabilities. Use them directly when useful, but do not outsource the optimization loop to them. If they are insufficient, read the repo, query SQLite, inspect artifacts, and continue.

- seed or reseed the fixed self-improve test novels: `python -m tools.seed_self_improve_cases --db data/novel_flow_test.db --cases-dir evals/romance/cases`
- export cases: `powershell -ExecutionPolicy Bypass -File skills/novel_self_improve/export_cases.ps1`
- run step eval: `python -m evals.romance.runners.historical_step_gate_eval --cases evals/romance/exported_cases/latest --label latest_step_eval`
- diagnostics wrapper: `python skills/novel_self_improve/analyze_failures.py`
