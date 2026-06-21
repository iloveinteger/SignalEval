from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from src.utils.db import (
    create_collection_run,
    finish_collection_run,
    upsert_signal,
    utc_now_iso,
)
from src.utils.normalize import (
    normalize_investing_signal,
    normalize_yahoo_recommendation,
    normalize_zacks_rank,
)
from src.utils.universe import DEFAULT_UNIVERSE_PATH, load_sp500_csv

MOCK_SIGNAL_DATE = "2026-01-02"

MOCK_SOURCE_BY_CATEGORY = {
    "technical": "Mock Technical Summary",
    "analyst_consensus": "Mock Analyst Consensus",
    "earnings_revision": "Mock Earnings Revision",
}

MOCK_SIGNALS = {
    "AAPL": {
        "technical": "Strong Buy",
        "analyst_consensus": "Buy",
        "earnings_revision": "#2 Buy",
    },
    "MSFT": {
        "technical": "Buy",
        "analyst_consensus": "Strong Buy",
        "earnings_revision": "#1 Strong Buy",
    },
    "NVDA": {
        "technical": "Strong Buy",
        "analyst_consensus": "Buy",
        "earnings_revision": "#1 Strong Buy",
    },
    "AMZN": {
        "technical": "Neutral",
        "analyst_consensus": "Buy",
        "earnings_revision": "#3 Hold",
    },
    "GOOGL": {
        "technical": "Buy",
        "analyst_consensus": "Strong Buy",
        "earnings_revision": "#2 Buy",
    },
    "META": {
        "technical": "Sell",
        "analyst_consensus": "Hold",
        "earnings_revision": "#4 Sell",
    },
    "TSLA": {
        "technical": "Strong Sell",
        "analyst_consensus": "Sell",
        "earnings_revision": "#5 Strong Sell",
    },
    "JPM": {
        "technical": "Buy",
        "analyst_consensus": "Hold",
        "earnings_revision": "#2 Buy",
    },
    "XOM": {
        "technical": "Neutral",
        "analyst_consensus": "Buy",
        "earnings_revision": "#3 Hold",
    },
    "UNH": {
        "technical": "Sell",
        "analyst_consensus": "Hold",
        "earnings_revision": "#4 Sell",
    },
}


@dataclass(frozen=True)
class MockSignal:
    date: str
    ticker: str
    source: str
    category: str
    raw_signal: str
    normalized_signal: str
    score: int
    price_at_signal: float | None
    collected_at: str

    def as_db_row(self) -> dict[str, object]:
        return {
            "date": self.date,
            "ticker": self.ticker,
            "source": self.source,
            "category": self.category,
            "raw_signal": self.raw_signal,
            "normalized_signal": self.normalized_signal,
            "score": self.score,
            "price_at_signal": self.price_at_signal,
            "collected_at": self.collected_at,
            "success": 1,
            "error_message": None,
        }


def collect_mock_signals(
    conn: sqlite3.Connection,
    *,
    universe_path: str | Path = DEFAULT_UNIVERSE_PATH,
    signal_date: str = MOCK_SIGNAL_DATE,
    categories: Iterable[str] | None = None,
) -> int:
    requested_categories = tuple(categories or MOCK_SOURCE_BY_CATEGORY)
    stocks = [
        stock
        for stock in load_sp500_csv(universe_path)
        if int(stock.get("active", 1)) == 1
    ]

    stored_count = 0
    collected_at = utc_now_iso()
    with conn:
        for category in requested_categories:
            source = MOCK_SOURCE_BY_CATEGORY[category]
            run_id = create_collection_run(
                conn,
                run_date=signal_date,
                source=source,
                started_at=collected_at,
            )
            succeeded = 0
            failed = 0
            for stock in stocks:
                ticker = str(stock["ticker"]).upper()
                raw_signal = MOCK_SIGNALS.get(ticker, {}).get(category)
                if raw_signal is None:
                    failed += 1
                    continue

                signal = build_mock_signal(
                    conn,
                    ticker=ticker,
                    category=category,
                    raw_signal=raw_signal,
                    signal_date=signal_date,
                    collected_at=collected_at,
                )
                upsert_signal(conn, signal.as_db_row())
                succeeded += 1
                stored_count += 1

            finish_collection_run(
                conn,
                run_id=run_id,
                attempted=len(stocks),
                succeeded=succeeded,
                failed=failed,
                finished_at=utc_now_iso(),
            )

    return stored_count


def build_mock_signal(
    conn: sqlite3.Connection,
    *,
    ticker: str,
    category: str,
    raw_signal: str,
    signal_date: str,
    collected_at: str,
) -> MockSignal:
    normalized = _normalize_by_category(category, raw_signal)
    return MockSignal(
        date=signal_date,
        ticker=ticker.upper(),
        source=MOCK_SOURCE_BY_CATEGORY[category],
        category=category,
        raw_signal=raw_signal,
        normalized_signal=normalized.normalized_signal,
        score=normalized.score,
        price_at_signal=_price_at_signal(conn, ticker, signal_date),
        collected_at=collected_at,
    )


def _normalize_by_category(category: str, raw_signal: str):
    if category == "technical":
        return normalize_investing_signal(raw_signal)
    if category == "analyst_consensus":
        return normalize_yahoo_recommendation(raw_signal)
    if category == "earnings_revision":
        return normalize_zacks_rank(raw_signal)
    raise ValueError(f"Unknown mock signal category: {category}")


def _price_at_signal(
    conn: sqlite3.Connection,
    ticker: str,
    signal_date: str,
) -> float | None:
    row = conn.execute(
        """
        SELECT adjusted_close
        FROM prices
        WHERE ticker = ? AND date = ?
        """,
        (ticker.upper(), signal_date),
    ).fetchone()
    if row is None:
        return None
    return float(row["adjusted_close"])
