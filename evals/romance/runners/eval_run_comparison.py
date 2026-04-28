from __future__ import annotations

import argparse
import json
from pathlib import Path

from evals.romance.comparison import compare_paths, render_comparison_markdown


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Compare baseline and candidate romance eval or workflow diagnostics runs.")
    parser.add_argument("--baseline", required=True, help="Baseline run directory or summary file.")
    parser.add_argument("--candidate", required=True, help="Candidate run directory or summary file.")
    parser.add_argument("--output-dir", default="", help="Optional output directory. Defaults to the candidate directory.")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    payload = compare_paths(args.baseline, args.candidate)
    output_dir = Path(args.output_dir) if args.output_dir else (Path(args.candidate) if Path(args.candidate).is_dir() else Path(args.candidate).parent)
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "comparison.json"
    md_path = output_dir / "comparison.md"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(render_comparison_markdown(payload), encoding="utf-8")
    print(
        json.dumps(
            {
                "comparison_type": payload.get("comparison_type"),
                "decision": payload.get("decision", {}),
                "comparison_json": str(json_path),
                "comparison_markdown": str(md_path),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
