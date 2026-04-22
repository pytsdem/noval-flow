from __future__ import annotations

import json
from pathlib import Path

from evals.romance.history_models import HistoricalEvalCase
from evals.romance.models import RomanceEvalCase
from evals.romance.requirement_cases import SelfImproveRequirementCase


def load_case(case_path: Path) -> RomanceEvalCase:
    payload = json.loads(case_path.read_text(encoding="utf-8"))
    if isinstance(payload, dict) and {"metadata", "inputs", "outputs"}.issubset(payload):
        historical_case = HistoricalEvalCase.model_validate(payload)
        return historical_case.to_romance_eval_case()
    if isinstance(payload, dict) and {"user_input", "self_improve_binding"}.issubset(payload):
        requirement_case = SelfImproveRequirementCase.model_validate(payload)
        if requirement_case.eval_fixture is None:
            raise ValueError(f"Requirement case {requirement_case.case_id} is missing eval_fixture.")
        return requirement_case.eval_fixture
    return RomanceEvalCase.model_validate(payload)


def load_historical_case(case_path: Path) -> HistoricalEvalCase:
    payload = json.loads(case_path.read_text(encoding="utf-8"))
    return HistoricalEvalCase.model_validate(payload)


def load_cases(case_dir: Path, *, case_ids: list[str] | None = None) -> list[RomanceEvalCase]:
    selected = set(case_ids or [])
    cases: list[RomanceEvalCase] = []
    for case_path in sorted(case_dir.glob("*.json")):
        if case_path.name == "export_summary.json":
            continue
        case = load_case(case_path)
        if selected and case.case_id not in selected:
            continue
        cases.append(case)
    if selected:
        found = {case.case_id for case in cases}
        missing = sorted(selected - found)
        if missing:
            raise FileNotFoundError(f"Missing romance eval cases: {', '.join(missing)}")
    return cases


def load_historical_cases(case_dir: Path, *, case_ids: list[str] | None = None) -> list[HistoricalEvalCase]:
    selected = set(case_ids or [])
    cases: list[HistoricalEvalCase] = []
    for case_path in sorted(case_dir.glob("*.json")):
        if case_path.name == "export_summary.json":
            continue
        case = load_historical_case(case_path)
        if selected and case.case_id not in selected:
            continue
        cases.append(case)
    if selected:
        found = {case.case_id for case in cases}
        missing = sorted(selected - found)
        if missing:
            raise FileNotFoundError(f"Missing historical eval cases: {', '.join(missing)}")
    return cases
