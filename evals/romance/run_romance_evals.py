from __future__ import annotations

import argparse
import json

from evals.romance.harness import RomanceEvalHarness


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run romance-focused chapter evals.")
    parser.add_argument("--label", default="", help="Run label used for the output directory.")
    parser.add_argument("--mode", default="fast", choices=["fast", "deep"], help="WritingChapterAgent mode.")
    parser.add_argument("--cases", nargs="*", default=None, help="Optional case ids to run.")
    parser.add_argument(
        "--cases-dir",
        default="",
        help="Optional directory containing replayable romance cases or exported historical cases.",
    )
    parser.add_argument(
        "--reports-root",
        default="evals/romance/reports",
        help="Directory where eval run reports are written.",
    )
    parser.add_argument(
        "--compare-to",
        default="",
        help="Existing summary.json path or run directory to diff against after this run.",
    )
    parser.add_argument(
        "--assemble-run-dir",
        default="",
        help="Assemble summary and optional diff from an existing run directory with per-case result.json files.",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    harness = RomanceEvalHarness(
        mode=args.mode,
        case_dir=args.cases_dir or None,
        reports_root=args.reports_root,
    )
    if args.assemble_run_dir:
        summary, diff = harness.assemble_existing_run(
            run_dir=args.assemble_run_dir,
            label=args.label,
            compare_to=args.compare_to or None,
        )
    else:
        summary, diff = harness.run(
            label=args.label,
            case_ids=args.cases,
            compare_to=args.compare_to or None,
        )
    payload = {
        "label": summary.label,
        "run_dir": summary.run_dir,
        "report_json": summary.report_json,
        "report_markdown": summary.report_markdown,
        "average_scores": summary.average_scores,
    }
    if diff is not None:
        payload["diff_vs"] = diff.baseline_label
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
