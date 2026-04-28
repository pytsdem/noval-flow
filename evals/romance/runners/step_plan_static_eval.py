from __future__ import annotations

import argparse
import json

from evals.romance.step_plan_evals import StepPlanEvalRunner


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run lightweight static Step1-8 evals on romance case step fixtures.")
    parser.add_argument("--cases-dir", default="evals/romance/cases", help="Directory containing case JSON files and <case_id>/steps.json assets.")
    parser.add_argument("--label", default="", help="Run label used for the output directory.")
    parser.add_argument("--case-ids", nargs="*", default=None, help="Optional case ids to evaluate.")
    parser.add_argument("--reports-root", default="evals/romance/reports", help="Directory where reports are written.")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    summary = StepPlanEvalRunner(reports_root=args.reports_root).run(
        cases_dir=args.cases_dir,
        label=args.label,
        case_ids=args.case_ids,
    )
    print(
        json.dumps(
            {
                "label": summary.label,
                "report_json": summary.report_json,
                "report_markdown": summary.report_markdown,
                "average_score": summary.average_score,
                "verdict_counts": summary.verdict_counts,
                "case_ids": summary.case_ids,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
