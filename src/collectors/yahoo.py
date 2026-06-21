from __future__ import annotations

import sqlite3
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd
import yfinance as yf

from src.utils.db import (
    create_collection_run,
    finish_collection_run,
    upsert_signal,
    utc_now_iso,
)
from src.utils.logging import get_logger
from src.utils.normalize import normalize_yahoo_recommendation
from src.utils.universe import DEFAULT_UNIVERSE_PATH, load_sp500_csv

logger = get_logger(__name__)

YAHOO_ANALYST_SOURCE = "Yahoo Finance Analyst Recommendation"
YAHOO_ANALYST_CATEGORY = "analyst_consensus"
DEFAULT_YAHOO_LIMIT = 10

TickerFactory = Callable[[str], Any]

RECOMMENDATION_KEY_LABELS = {
    "strongbuy": "Strong Buy",
    "strong buy": "Strong Buy",
    "strong_buy": "Strong Buy",
    "buy": "Buy",
    "hold": "Hold",
    "neutral": "Hold",
    "sell": "Sell",
    "strongsell": "Strong Sell",
    "strong sell": "Strong Sell",
    "strong_sell": "Strong Sell",
}

SUMMARY_COLUMNS = (
    ("strongBuy", "Strong Buy"),
    ("buy", "Buy"),
    ("hold", "Hold"),
    ("sell", "Sell"),
    ("strongSell", "Strong Sell"),
)


class YahooAnalystError(RuntimeError):
    pass


@dataclass(frozen=True)
class YahooAnalystSignal:
    date: str
    ticker: str
    raw_signal: str | None
    normalized_signal: str | None
    score: int | None
    price_at_signal: float | None
    collected_at: str
    success: int
    error_message: str | None

    def as_db_row(self) -> dict[str, object]:
        return {
            "date": self.date,
            "ticker": self.ticker,
            "source": YAHOO_ANALYST_SOURCE,
            "category": YAHOO_ANALYST_CATEGORY,
            "raw_signal": self.raw_signal,
            "normalized_signal": self.normalized_signal,
            "score": self.score,
            "price_at_signal": self.price_at_signal,
            "collected_at": self.collected_at,
            "success": self.success,
            "error_message": self.error_message,
        }


def collect_yahoo_analyst_signals(
    conn: sqlite3.Connection,
    *,
    universe_path: str | Path = DEFAULT_UNIVERSE_PATH,
    signal_date: str | None = None,
    limit: int = DEFAULT_YAHOO_LIMIT,
    ticker_factory: TickerFactory = yf.Ticker,
    retries: int = 2,
    sleep_seconds: float = 1.0,
) -> dict[str, int]:
    run_date = signal_date or date.today().isoformat()
    tickers = _load_limited_universe(universe_path, limit)
    collected_at = utc_now_iso()

    attempted = len(tickers)
    succeeded = 0
    failed = 0

    with conn:
        run_id = create_collection_run(
            conn,
            run_date=run_date,
            source=YAHOO_ANALYST_SOURCE,
            started_at=collected_at,
        )

        for ticker in tickers:
            signal = build_yahoo_analyst_signal(
                conn,
                ticker=ticker,
                signal_date=run_date,
                collected_at=collected_at,
                ticker_factory=ticker_factory,
                retries=retries,
                sleep_seconds=sleep_seconds,
            )
            upsert_signal(conn, signal.as_db_row())
            if signal.success:
                succeeded += 1
            else:
                failed += 1

        finish_collection_run(
            conn,
            run_id=run_id,
            attempted=attempted,
            succeeded=succeeded,
            failed=failed,
            finished_at=utc_now_iso(),
        )

    logger.info(
        "Stored Yahoo analyst signals: attempted=%s succeeded=%s failed=%s",
        attempted,
        succeeded,
        failed,
    )
    return {"attempted": attempted, "succeeded": succeeded, "failed": failed}


def build_yahoo_analyst_signal(
    conn: sqlite3.Connection,
    *,
    ticker: str,
    signal_date: str,
    collected_at: str,
    ticker_factory: TickerFactory = yf.Ticker,
    retries: int = 2,
    sleep_seconds: float = 1.0,
) -> YahooAnalystSignal:
    try:
        raw_signal = fetch_yahoo_analyst_recommendation(
            ticker,
            ticker_factory=ticker_factory,
            retries=retries,
            sleep_seconds=sleep_seconds,
        )
        normalized = normalize_yahoo_recommendation(raw_signal)
        return YahooAnalystSignal(
            date=signal_date,
            ticker=ticker.upper(),
            raw_signal=raw_signal,
            normalized_signal=normalized.normalized_signal,
            score=normalized.score,
            price_at_signal=_price_at_signal(conn, ticker, signal_date),
            collected_at=collected_at,
            success=1,
            error_message=None,
        )
    except Exception as exc:
        logger.warning("Yahoo analyst collection failed for %s: %s", ticker, exc)
        return YahooAnalystSignal(
            date=signal_date,
            ticker=ticker.upper(),
            raw_signal=None,
            normalized_signal=None,
            score=None,
            price_at_signal=_price_at_signal(conn, ticker, signal_date),
            collected_at=collected_at,
            success=0,
            error_message=str(exc),
        )


def fetch_yahoo_analyst_recommendation(
    ticker: str,
    *,
    ticker_factory: TickerFactory = yf.Ticker,
    retries: int = 2,
    sleep_seconds: float = 1.0,
) -> str:
    last_error: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            ticker_obj = ticker_factory(ticker)
            raw_signal = recommendation_from_info(ticker_obj)
            if raw_signal is None:
                raw_signal = recommendation_from_summary(ticker_obj)
            if raw_signal is None:
                raise YahooAnalystError("No analyst recommendation found")
            return raw_signal
        except Exception as exc:
            last_error = exc
            logger.warning(
                "Yahoo analyst fetch attempt %s/%s failed for %s: %s",
                attempt,
                retries,
                ticker,
                exc,
            )
            if attempt < retries:
                time.sleep(sleep_seconds)

    raise YahooAnalystError(
        f"Failed to fetch Yahoo analyst recommendation for {ticker}"
    ) from last_error


def recommendation_from_info(ticker_obj: Any) -> str | None:
    info = _call_or_value(ticker_obj, "get_info")
    if not info:
        info = _call_or_value(ticker_obj, "info")
    if not isinstance(info, dict):
        return None

    key = info.get("recommendationKey")
    if key is None:
        return None
    return _label_from_recommendation_key(str(key))


def recommendation_from_summary(ticker_obj: Any) -> str | None:
    summary = _call_or_value(ticker_obj, "get_recommendations_summary")
    if summary is None:
        summary = _call_or_value(ticker_obj, "recommendations_summary")
    if summary is None:
        return None

    rows = _summary_rows(summary)
    if not rows:
        return None

    current_row = _current_summary_row(rows)
    counts = []
    for column, label in SUMMARY_COLUMNS:
        value = current_row.get(column)
        if value is not None:
            counts.append((int(value), label))

    if not counts or max(count for count, _label in counts) <= 0:
        return None

    # Prefer the strongest populated bucket unless Hold is tied, which is
    # conservative for mixed analyst counts.
    top_count = max(count for count, _label in counts)
    tied_labels = [label for count, label in counts if count == top_count]
    if "Hold" in tied_labels:
        return "Hold"
    return tied_labels[0]


def _summary_rows(summary: Any) -> list[dict[str, Any]]:
    if isinstance(summary, pd.DataFrame):
        return [dict(row) for row in summary.to_dict("records")]
    if isinstance(summary, dict):
        return [summary]
    if isinstance(summary, list):
        return [row for row in summary if isinstance(row, dict)]
    return []


def _current_summary_row(rows: list[dict[str, Any]]) -> dict[str, Any]:
    for row in rows:
        if str(row.get("period", "")).lower() in {"0m", "current"}:
            return row
    return rows[0]


def _label_from_recommendation_key(key: str) -> str | None:
    normalized = key.strip().lower().replace("-", "_")
    return RECOMMENDATION_KEY_LABELS.get(normalized)


def _call_or_value(obj: Any, name: str) -> Any:
    value = getattr(obj, name, None)
    if callable(value):
        return value()
    return value


def _load_limited_universe(universe_path: str | Path, limit: int) -> list[str]:
    stocks = [
        stock
        for stock in load_sp500_csv(universe_path)
        if int(stock.get("active", 1)) == 1
    ]
    if limit <= 0:
        raise ValueError("limit must be greater than zero")
    return [str(stock["ticker"]).upper() for stock in stocks[:limit]]


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
