from __future__ import annotations

import argparse
import logging
import time
import webbrowser
from pathlib import Path

from novel_flow.config import Settings
from novel_flow.logger import configure_logging
from novel_flow.server import start_server
from novel_flow.storage.sqlite_store import SQLiteStore


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Novel Flow CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_p = subparsers.add_parser("run", help="Start the web console.")
    run_p.add_argument("--db", default="data/novel_flow.db", help="Formal mode SQLite database path.")
    run_p.add_argument("--test-db", default="data/novel_flow_test.db", help="Test mode SQLite database path.")
    run_p.add_argument("--port", type=int, default=8765, help="Web monitor port.")
    run_p.add_argument("--no-browser", action="store_true", help="Do not open browser automatically.")
    return parser


def run_command(db_path: str, test_db_path: str, port: int, no_browser: bool) -> int:
    settings = Settings.from_env(database_path=db_path)
    configure_logging(settings.log_level)
    logger = logging.getLogger("novel_flow.cli")

    formal_store = SQLiteStore(Path(db_path))
    test_store = SQLiteStore(Path(test_db_path))
    server = start_server(formal_store=formal_store, test_store=test_store, settings=settings, port=port)
    url = f"http://127.0.0.1:{port}/"

    print(f"\n  控制台地址: {url}")
    print(f"  正式模式数据库: {Path(db_path).resolve()}")
    print(f"  测试模式数据库: {Path(test_db_path).resolve()}\n")
    if not no_browser:
        webbrowser.open(url)

    logger.info("Novel Flow console started at %s", url)
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        server.shutdown()
    return 0


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    if args.command == "run":
        return run_command(
            db_path=args.db,
            test_db_path=args.test_db,
            port=args.port,
            no_browser=args.no_browser,
        )
    raise ValueError(f"Unsupported command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
