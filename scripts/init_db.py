from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.utils.db import DEFAULT_DB_PATH, connect, initialize_database
from src.utils.universe import DEFAULT_UNIVERSE_PATH, sync_universe


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Initialize the Signal League DB.")
    parser.add_argument(
        "--db",
        type=Path,
        default=DEFAULT_DB_PATH,
        help="SQLite database path.",
    )
    parser.add_argument(
        "--universe",
        type=Path,
        default=DEFAULT_UNIVERSE_PATH,
        help="S&P 500 universe CSV path.",
    )
    parser.add_argument(
        "--skip-universe",
        action="store_true",
        help="Create schema without loading config/sp500.csv.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    db_path = initialize_database(args.db)

    loaded_count = None
    if not args.skip_universe:
        with connect(db_path) as conn:
            loaded_count = sync_universe(conn, args.universe)

    print(f"Initialized database: {db_path}")
    if loaded_count is not None:
        print(f"Loaded universe rows: {loaded_count}")


if __name__ == "__main__":
    main()
