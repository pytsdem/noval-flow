from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from _example_support import DEFAULT_QUERY, build_blueprint_agent, print_json


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Debug blueprint generation.")
    parser.add_argument("--query", default=DEFAULT_QUERY, help="Research query used to build the blueprint.")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    blueprint_agent = build_blueprint_agent()
    blueprint = blueprint_agent.build_blueprint(research_query=args.query)
    print_json(
        {
            "agent": "BlueprintAgent",
            "mode": "blueprint",
            "query": args.query,
            "blueprint": blueprint.model_dump(mode="json"),
        }
    )


if __name__ == "__main__":
    main()
