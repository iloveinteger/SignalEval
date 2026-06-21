from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.prices.mock_prices import (  # noqa: E402
    MOCK_PRICE_PERIODS,
    MOCK_PRICE_START_DATE,
    seed_mock_prices,
)
from src.utils.db import DEFAULT_DB_PATH, connect, create_schema  # noqa: E402
from src.utils.logging import configure_logging  # noqa: E402
from src.utils.universe import DEFAULT_UNIVERSE_PATH, sync_universe  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Seed deterministic mock prices.")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--universe", type=Path, default=DEFAULT_UNIVERSE_PATH)
    parser.add_argument("--start-date", default=MOCK_PRICE_START_DATE.isoformat())
    parser.add_argument("--periods", type=int, default=MOCK_PRICE_PERIODS)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    configure_logging()

    with connect(args.db) as conn:
        create_schema(conn)
        sync_universe(conn, args.universe)
        count = seed_mock_prices(
            conn,
            universe_path=args.universe,
            start_date=date.fromisoformat(args.start_date),
            periods=args.periods,
        )

    print(f"Stored mock price rows: {count}")


if __name__ == "__main__":
    main()
