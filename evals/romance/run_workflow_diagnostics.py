from __future__ import annotations

import argparse
import json

from evals.romance.workflow_diagnostics import WorkflowDiagnosticsRunner


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run workflow diagnostics on exported historical cases.")
    parser.add_argument("--cases", default="evals/romance/exported_cases/latest", help="Directory containing exported historical case JSON files.")
    parser.add_argument("--label", default="", help="Run label used for the output directory.")
    parser.add_argument("--case-ids", nargs="*", default=None, help="Optional case ids to analyze.")
    parser.add_argument("--reports-root", default="evals/romance/reports", help="Directory where diagnostics reports are written.")
    parser.add_argument("--eval-summary", default="", help="Optional romance eval summary.json used to supply final_text_scores.")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    runner = WorkflowDiagnosticsRunner(reports_root=args.reports_root)
    summary = runner.run(
        case_dir=args.cases,
        label=args.label,
        case_ids=args.case_ids,
        eval_summary=args.eval_summary or None,
    )
    print(
        json.dumps(
            {
                "label": summary.label,
                "report_json": summary.report_json,
                "report_markdown": summary.report_markdown,
                "aggregate_findings": summary.aggregate_findings.model_dump(mode="json"),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
