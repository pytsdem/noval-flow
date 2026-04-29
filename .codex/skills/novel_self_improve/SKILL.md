---
name: novel_self_improve
description: Use when the user explicitly asks to run `novel_self_improve` or optimize the novel-generation framework through the repo's requirement-first self-improve workflow. This local skill is only the visible entrypoint; the canonical instructions live in `skills/novel_self_improve/SKILL.md` inside the repo and must be opened and followed each time.
---

# novel_self_improve

This is the local visible entrypoint for the repo's self-improve workflow.

## Source of truth

Always open and follow:

- `skills/novel_self_improve/SKILL.md`

That repo file is the canonical runbook and may be updated over time. Do not treat this local wrapper as the full protocol.

## Required behavior

When this skill is invoked:

1. Read `skills/novel_self_improve/SKILL.md` from the current repo.
2. Follow the repo runbook as the authoritative workflow.
3. Also obey the repo's `AGENTS.md` and any current developer instructions.

## Fallback

If the repo runbook is missing, unavailable, or corrupted, report that briefly and fall back to the best available local evidence-driven optimization workflow. Do not silently continue as if this wrapper were the full runbook.
