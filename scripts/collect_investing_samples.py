from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.collectors.investing import (  # noqa: E402
    DEFAULT_INVESTING_SAMPLES_DIR,
    DEFAULT_INVESTING_LIVE_CACHE_DIR,
    DEFAULT_FETCH_RETRIES,
    DEFAULT_FETCH_TIMEOUT_SECONDS,
    DEFAULT_USER_AGENT,
    LIVE_SUPPORTED_TICKER,
    InvestingFetchError,
    collect_investing_live_signals,
    collect_investing_sample_signals,
)
from src.utils.db import DEFAULT_DB_PATH, connect, create_schema  # noqa: E402
from src.utils.logging import configure_logging  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Collect Investing.com signals either from saved HTML samples or, "
            "when requested explicitly, from a live AAPL fetch."
        )
    )
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--samples-dir", type=Path, default=DEFAULT_INVESTING_SAMPLES_DIR)
    parser.add_argument("--live-cache-dir", type=Path, default=DEFAULT_INVESTING_LIVE_CACHE_DIR)
    parser.add_argument(
        "--date",
        default=None,
        help="Signal date to store. Defaults to the technical sample update date.",
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="Fetch live Investing HTML for AAPL only, then parse it with the existing parser.",
    )
    parser.add_argument(
        "--ticker",
        default=LIVE_SUPPORTED_TICKER,
        help=f"Ticker for live mode. Only {LIVE_SUPPORTED_TICKER} is supported.",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=float,
        default=DEFAULT_FETCH_TIMEOUT_SECONDS,
        help="Live mode only: HTTP timeout per request.",
    )
    parser.add_argument(
        "--retries",
        type=int,
        default=DEFAULT_FETCH_RETRIES,
        help="Live mode only: number of HTTP fetch attempts per page.",
    )
    parser.add_argument(
        "--user-agent",
        default=DEFAULT_USER_AGENT,
        help="Live mode only: HTTP User-Agent header.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    configure_logging()

    with connect(args.db) as conn:
        create_schema(conn)
        if args.live:
            try:
                result = collect_investing_live_signals(
                    conn,
                    ticker=args.ticker,
                    cache_dir=args.live_cache_dir,
                    signal_date=args.date,
                    timeout_seconds=args.timeout_seconds,
                    retries=args.retries,
                    user_agent=args.user_agent,
                )
            except InvestingFetchError as exc:
                print(f"Investing live fetch failed gracefully: {exc}")
                return
        else:
            result = collect_investing_sample_signals(
                conn,
                samples_dir=args.samples_dir,
                signal_date=args.date,
            )

    print(
        "Stored Investing signals: "
        f"attempted={result['attempted']} "
        f"succeeded={result['succeeded']} "
        f"failed={result['failed']} "
        f"stored={result['stored']}"
    )


if __name__ == "__main__":
    main()
