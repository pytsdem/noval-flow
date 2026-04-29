from __future__ import annotations

import argparse
import json

from evals.romance.beat_plan_eval import BeatPlanEvalRunner


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run a low-cost planner-only eval that generates real chapter beats but stops before prose drafting."
    )
    parser.add_argument("--cases-dir", default="evals/romance/cases", help="Directory containing eval case JSON files.")
    parser.add_argument("--label", default="", help="Run label used for the output directory.")
    parser.add_argument("--case-ids", nargs="*", default=None, help="Optional case ids to evaluate.")
    parser.add_argument("--reports-root", default="evals/romance/reports", help="Directory where reports are written.")
    parser.add_argument(
        "--skip-sanitize-context",
        action="store_true",
        help="Skip the context sanitization LLM pass and use the raw writer-context selection output.",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    summary = BeatPlanEvalRunner(reports_root=args.reports_root).run(
        cases_dir=args.cases_dir,
        label=args.label,
        case_ids=args.case_ids,
        sanitize_context=not args.skip_sanitize_context,
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
