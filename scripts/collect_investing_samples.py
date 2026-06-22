from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.collectors.investing import (  # noqa: E402
    DEFAULT_INVESTING_SAMPLES_DIR,
    collect_investing_sample_signals,
)
from src.utils.db import DEFAULT_DB_PATH, connect, create_schema  # noqa: E402
from src.utils.logging import configure_logging  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Collect Investing.com sample signals from saved HTML files. "
            "This does not make live HTTP requests or modify Random Baseline rows."
        )
    )
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--samples-dir", type=Path, default=DEFAULT_INVESTING_SAMPLES_DIR)
    parser.add_argument(
        "--date",
        default=None,
        help="Signal date to store. Defaults to the technical sample update date.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    configure_logging()

    with connect(args.db) as conn:
        create_schema(conn)
        result = collect_investing_sample_signals(
            conn,
            samples_dir=args.samples_dir,
            signal_date=args.date,
        )

    print(
        "Stored Investing sample signals: "
        f"attempted={result['attempted']} "
        f"succeeded={result['succeeded']} "
        f"failed={result['failed']} "
        f"stored={result['stored']}"
    )


if __name__ == "__main__":
    main()
