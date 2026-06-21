from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.analysis.returns import HORIZONS, compute_available_forward_returns  # noqa: E402
from src.utils.db import DEFAULT_DB_PATH, connect, create_schema  # noqa: E402
from src.utils.logging import configure_logging  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compute available forward returns.")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument(
        "--horizon",
        type=int,
        action="append",
        help="Trading-day horizon to compute. Can be passed more than once.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    configure_logging()
    horizons = tuple(args.horizon) if args.horizon else HORIZONS

    with connect(args.db) as conn:
        create_schema(conn)
        count = compute_available_forward_returns(conn, horizons=horizons)

    print(f"Stored forward-return rows: {count}")


if __name__ == "__main__":
    main()
