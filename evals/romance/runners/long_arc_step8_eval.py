from __future__ import annotations

import argparse
import json

from evals.romance.long_arc_step8_eval import LongArcStep8EvalRunner


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Evaluate long-form chapter-brief arcs from Step8 fixtures or generated batches.")
    parser.add_argument("--cases-dir", default="evals/romance/cases", help="Directory containing <case_id>/steps.json assets.")
    parser.add_argument("--label", default="", help="Run label used for the output directory.")
    parser.add_argument("--case-ids", nargs="*", default=None, help="Optional case ids to evaluate.")
    parser.add_argument("--reports-root", default="evals/romance/reports", help="Directory where reports are written.")
    parser.add_argument("--generate", action="store_true", help="Generate fresh Step8 chapter briefs from Step1-7 before evaluation.")
    parser.add_argument("--target-chapters", type=int, default=30, help="Number of chapters to generate when --generate is set.")
    parser.add_argument("--batch-size", type=int, default=2, help="Step8 generation batch size when --generate is set.")
    parser.add_argument("--llm-provider", default="", help="Optional provider override for generation, e.g. deepseek or doubao.")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    summary = LongArcStep8EvalRunner(reports_root=args.reports_root).run(
        cases_dir=args.cases_dir,
        label=args.label,
        case_ids=args.case_ids,
        generate=args.generate,
        target_chapters=args.target_chapters,
        batch_size=args.batch_size,
        llm_provider=args.llm_provider or None,
    )
    print(
        json.dumps(
            {
                "label": summary.label,
                "report_json": summary.report_json,
                "report_markdown": summary.report_markdown,
                "generated": summary.generated,
                "target_chapters": summary.target_chapters,
                "batch_size": summary.batch_size,
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
