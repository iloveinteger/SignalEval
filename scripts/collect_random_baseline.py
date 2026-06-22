from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.collectors.random_baseline import collect_random_baseline_signals  # noqa: E402
from src.utils.db import DEFAULT_DB_PATH, connect, create_schema  # noqa: E402
from src.utils.logging import configure_logging  # noqa: E402
from src.utils.universe import DEFAULT_UNIVERSE_PATH, sync_universe  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Collect deterministic random-baseline control signals."
    )
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--universe", type=Path, default=DEFAULT_UNIVERSE_PATH)
    parser.add_argument("--date", required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    configure_logging()

    with connect(args.db) as conn:
        create_schema(conn)
        sync_universe(conn, args.universe)
        count = collect_random_baseline_signals(
            conn,
            universe_path=args.universe,
            signal_date=args.date,
        )

    print(f"Stored random baseline signals: {count}")


if __name__ == "__main__":
    main()
