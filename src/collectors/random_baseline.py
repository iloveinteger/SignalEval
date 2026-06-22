from __future__ import annotations

import hashlib
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
from src.utils.universe import DEFAULT_UNIVERSE_PATH, load_sp500_csv

RANDOM_BASELINE_SOURCE = "Random Baseline"
RANDOM_BASELINE_CATEGORY = "random_baseline"
RANDOM_BASELINE_LABELS = (
    ("Strong Sell", -2),
    ("Sell", -1),
    ("Neutral", 0),
    ("Buy", 1),
    ("Strong Buy", 2),
)


@dataclass(frozen=True)
class RandomBaselineSignal:
    date: str
    ticker: str
    raw_signal: str
    normalized_signal: str
    score: int
    price_at_signal: float | None
    collected_at: str

    def as_db_row(self) -> dict[str, object]:
        return {
            "date": self.date,
            "ticker": self.ticker,
            "source": RANDOM_BASELINE_SOURCE,
            "category": RANDOM_BASELINE_CATEGORY,
            "raw_signal": self.raw_signal,
            "normalized_signal": self.normalized_signal,
            "score": self.score,
            "price_at_signal": self.price_at_signal,
            "collected_at": self.collected_at,
            "success": 1,
            "error_message": None,
        }


def collect_random_baseline_signals(
    conn: sqlite3.Connection,
    *,
    universe_path: str | Path = DEFAULT_UNIVERSE_PATH,
    signal_date: str,
    tickers: Iterable[str] | None = None,
) -> int:
    if tickers is None:
        target_tickers = [
            str(stock["ticker"]).upper()
            for stock in load_sp500_csv(universe_path)
            if int(stock.get("active", 1)) == 1
        ]
    else:
        target_tickers = _dedupe_tickers(tickers)

    collected_at = utc_now_iso()
    stored_count = 0

    with conn:
        run_id = create_collection_run(
            conn,
            run_date=signal_date,
            source=RANDOM_BASELINE_SOURCE,
            started_at=collected_at,
        )
        succeeded = 0
        failed = 0

        for ticker in target_tickers:
            signal = build_random_baseline_signal(
                conn,
                ticker=ticker,
                signal_date=signal_date,
                collected_at=collected_at,
            )
            upsert_signal(conn, signal.as_db_row())
            succeeded += 1
            stored_count += 1

        finish_collection_run(
            conn,
            run_id=run_id,
            attempted=len(target_tickers),
            succeeded=succeeded,
            failed=failed,
            finished_at=utc_now_iso(),
        )

    return stored_count


def build_random_baseline_signal(
    conn: sqlite3.Connection,
    *,
    ticker: str,
    signal_date: str,
    collected_at: str,
) -> RandomBaselineSignal:
    raw_signal, score = _baseline_label_for(ticker=ticker, signal_date=signal_date)
    return RandomBaselineSignal(
        date=signal_date,
        ticker=ticker.upper(),
        raw_signal=raw_signal,
        normalized_signal=raw_signal,
        score=score,
        price_at_signal=_price_at_signal(conn, ticker, signal_date),
        collected_at=collected_at,
    )


def _baseline_label_for(*, ticker: str, signal_date: str) -> tuple[str, int]:
    seed = f"{RANDOM_BASELINE_SOURCE}|{signal_date}|{ticker.upper()}".encode("utf-8")
    index = int(hashlib.sha256(seed).hexdigest()[:8], 16) % len(RANDOM_BASELINE_LABELS)
    return RANDOM_BASELINE_LABELS[index]


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


def _dedupe_tickers(tickers: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for ticker in tickers:
        normalized = str(ticker).strip().upper()
        if normalized and normalized not in seen:
            seen.add(normalized)
            result.append(normalized)
    return result
