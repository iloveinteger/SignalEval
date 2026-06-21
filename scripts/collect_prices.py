from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.prices.yahoo_prices import (  # noqa: E402
    collect_and_store_prices,
    default_end_date,
    default_start_date,
    load_price_tickers,
)
from src.utils.db import DEFAULT_DB_PATH, connect, create_schema  # noqa: E402
from src.utils.logging import configure_logging  # noqa: E402
from src.utils.universe import DEFAULT_UNIVERSE_PATH  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Collect Yahoo Finance adjusted-close prices."
    )
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--universe", type=Path, default=DEFAULT_UNIVERSE_PATH)
    parser.add_argument(
        "--start",
        default=default_start_date().isoformat(),
        help="Start date, inclusive, as YYYY-MM-DD.",
    )
    parser.add_argument(
        "--end",
        default=default_end_date().isoformat(),
        help="End date, exclusive, as YYYY-MM-DD.",
    )
    parser.add_argument("--retries", type=int, default=3)
    parser.add_argument("--sleep-seconds", type=float, default=1.0)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    configure_logging()

    tickers = load_price_tickers(args.universe)
    with connect(args.db) as conn:
        create_schema(conn)
        result = collect_and_store_prices(
            conn,
            tickers,
            start=args.start,
            end=args.end,
            retries=args.retries,
            sleep_seconds=args.sleep_seconds,
        )

    print(f"Requested tickers: {len(result.requested_tickers)}")
    print(f"Stored price rows: {len(result.prices)}")
    print(f"Missing tickers: {len(result.missing_tickers)}")
    if result.missing_tickers:
        print("Missing: " + ", ".join(result.missing_tickers))


if __name__ == "__main__":
    main()
