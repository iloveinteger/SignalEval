from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.analysis.portfolio import DEFAULT_PORTFOLIO_PATH, export_portfolio_json  # noqa: E402
from src.utils.db import DEFAULT_DB_PATH, connect, create_schema  # noqa: E402
from src.utils.logging import configure_logging  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Simulate daily source portfolios.")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--output", type=Path, default=DEFAULT_PORTFOLIO_PATH)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    configure_logging()

    with connect(args.db) as conn:
        create_schema(conn)
        payload = export_portfolio_json(conn, args.output)

    print(f"Exported portfolio sources: {len(payload['sources'])}")
    print(f"Wrote {args.output}")


if __name__ == "__main__":
    main()
