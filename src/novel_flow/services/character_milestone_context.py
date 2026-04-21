from __future__ import annotations

from typing import Any

from novel_flow.models.schemas import ChapterBrief, TwistDesign


def _normalize_text(value: Any) -> str:
    return str(value or "").strip()


class CharacterMilestoneContextBuilder:
    @classmethod
    def build(
        cls,
        *,
        character_milestones: list[dict[str, Any]],
        chapter_brief: ChapterBrief,
        active_twists: list[TwistDesign],
    ) -> str:
        focus_names = list(dict.fromkeys(name for name in chapter_brief.character_focus if _normalize_text(name)))
        for twist in active_twists:
            for name in twist.related_characters:
                clean = _normalize_text(name)
                if clean and clean not in focus_names:
                    focus_names.append(clean)

        lines = ["[Step 5 relevant character milestones]"]
        if not focus_names:
            lines.append("No focused characters for this chapter.")
            return "\n".join(lines).strip()

        matched_any = False
        for name in focus_names:
            item = next(
                (
                    milestone
                    for milestone in character_milestones
                    if _normalize_text(milestone.get("character_name")) == name
                ),
                None,
            )
            if not isinstance(item, dict):
                continue
            matched_any = True
            lines.extend(["", name])
            milestone_list = item.get("milestone_list", [])
            if isinstance(milestone_list, list):
                for milestone in milestone_list:
                    if not isinstance(milestone, dict):
                        continue
                    axis = _normalize_text(milestone.get("axis")) or "未命名发展轴"
                    stages = [
                        _normalize_text(stage)
                        for stage in milestone.get("stages", [])
                        if _normalize_text(stage)
                    ]
                    stage_text = " -> ".join(stages) if stages else "No stage labels."
                    lines.append(f"- {axis}: {stage_text}")

            axes = item.get("axes", [])
            if isinstance(axes, list):
                for axis_item in axes:
                    if not isinstance(axis_item, dict):
                        continue
                    axis_name = _normalize_text(axis_item.get("axis"))
                    if not axis_name:
                        continue
                    phases = axis_item.get("phases", [])
                    if not isinstance(phases, list):
                        continue
                    for phase_item in phases:
                        if not isinstance(phase_item, dict):
                            continue
                        label = _normalize_text(phase_item.get("label")) or _normalize_text(phase_item.get("phase"))
                        if not label:
                            continue
                        lines.append(f"  - {axis_name} / {label}")
                        scenes = phase_item.get("scenes", [])
                        if not isinstance(scenes, list):
                            continue
                        for scene_item in scenes:
                            if not isinstance(scene_item, dict):
                                continue
                            title = _normalize_text(scene_item.get("title"))
                            trigger = _normalize_text(scene_item.get("trigger"))
                            psychology = _normalize_text(scene_item.get("psychology"))
                            outcome = _normalize_text(scene_item.get("outcome"))
                            detail = "；".join(
                                part
                                for part in [
                                    f"title={title}" if title else "",
                                    f"trigger={trigger}" if trigger else "",
                                    f"psychology={psychology}" if psychology else "",
                                    f"outcome={outcome}" if outcome else "",
                                ]
                                if part
                            )
                            if detail:
                                lines.append(f"    - {detail}")

        if not matched_any:
            lines.extend(["", "No relevant character milestones matched current chapter focus."])
        return "\n".join(lines).strip()
