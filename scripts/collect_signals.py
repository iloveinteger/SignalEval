from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.collectors.mock import (  # noqa: E402
    MOCK_SIGNAL_DATE,
    MOCK_SOURCE_BY_CATEGORY,
    collect_mock_signals,
)
from src.collectors.yahoo import (  # noqa: E402
    DEFAULT_YAHOO_LIMIT,
    collect_yahoo_analyst_signals,
)
from src.utils.db import DEFAULT_DB_PATH, connect, create_schema  # noqa: E402
from src.utils.logging import configure_logging  # noqa: E402
from src.utils.universe import DEFAULT_UNIVERSE_PATH, sync_universe  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Collect Signal League signals.")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--universe", type=Path, default=DEFAULT_UNIVERSE_PATH)
    parser.add_argument(
        "--collector",
        choices=("mock", "yahoo-analyst"),
        default="mock",
        help="Use mock data or the real Yahoo analyst collector.",
    )
    parser.add_argument("--date", default=None)
    parser.add_argument("--limit", type=int, default=DEFAULT_YAHOO_LIMIT)
    parser.add_argument("--retries", type=int, default=2)
    parser.add_argument("--sleep-seconds", type=float, default=1.0)
    parser.add_argument(
        "--category",
        choices=tuple(MOCK_SOURCE_BY_CATEGORY),
        action="append",
        help="Mock collector only: collect a subset of mock categories.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    configure_logging()

    with connect(args.db) as conn:
        create_schema(conn)
        sync_universe(conn, args.universe)

        if args.collector == "mock":
            count = collect_mock_signals(
                conn,
                universe_path=args.universe,
                signal_date=args.date or MOCK_SIGNAL_DATE,
                categories=args.category,
            )
            print(f"Stored mock signals: {count}")
            return

        result = collect_yahoo_analyst_signals(
            conn,
            universe_path=args.universe,
            signal_date=args.date,
            limit=args.limit,
            retries=args.retries,
            sleep_seconds=args.sleep_seconds,
        )
        print(
            "Stored Yahoo analyst signals: "
            f"attempted={result['attempted']} "
            f"succeeded={result['succeeded']} "
            f"failed={result['failed']}"
        )


if __name__ == "__main__":
    main()
