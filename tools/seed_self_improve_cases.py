from __future__ import annotations

import argparse
import json
from pathlib import Path

from evals.romance.requirement_cases import seed_requirement_cases


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Seed fixed self-improve requirement cases into the test database.")
    parser.add_argument("--db", default="data/novel_flow_test.db", help="Target SQLite database path.")
    parser.add_argument("--cases-dir", default="evals/romance/cases", help="Directory containing self-improve requirement case JSON files.")
    parser.add_argument("--registry-path", default="evals/romance/self_improve_registry.json", help="Output registry path that records the fixed case-to-book bindings.")
    parser.add_argument("--case-id", dest="case_ids", action="append", default=None, help="Optional case id filter; may be passed multiple times.")
    parser.add_argument("--skip-reset", action="store_true", help="Do not delete an existing bound test book before reseeding.")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    seeded = seed_requirement_cases(
        db_path=args.db,
        case_dir=args.cases_dir,
        case_ids=args.case_ids,
        reset_existing=not args.skip_reset,
    )
    registry_payload = {
        "kind": "novel_self_improve_registry",
        "db_path": args.db.replace("\\", "/"),
        "mode": "test",
        "cases": seeded,
    }
    registry_path = Path(args.registry_path)
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    registry_path.write_text(json.dumps(registry_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(registry_payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
