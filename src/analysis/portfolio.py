from __future__ import annotations

import json
import sqlite3
from collections import defaultdict
from pathlib import Path
from typing import Any

from src.collectors.random_baseline import RANDOM_BASELINE_SOURCE
from src.utils.db import PROJECT_ROOT, utc_now_iso

DEFAULT_PORTFOLIO_PATH = PROJECT_ROOT / "data" / "exports" / "portfolio.json"
INITIAL_NAV = 100.0


def build_portfolio_report(conn: sqlite3.Connection) -> dict[str, Any]:
    returns_by_ticker = _load_daily_returns(conn)
    if "SPY" not in returns_by_ticker:
        return {"generated_at": utc_now_iso(), "initial_nav": INITIAL_NAV, "sources": []}

    signals_by_source = _load_signal_inputs(conn)
    sources = []
    for source, dates in sorted(signals_by_source.items()):
        series = _simulate_source(source, dates, returns_by_ticker)
        latest = series[-1] if series else None
        latest_nav = latest["nav"] if latest else INITIAL_NAV
        latest_spy_nav = latest["spy_nav"] if latest else INITIAL_NAV
        sources.append(
            {
                "source": source,
                "is_control": source == RANDOM_BASELINE_SOURCE,
                "initial_nav": INITIAL_NAV,
                "latest_nav": latest_nav,
                "total_return": (latest_nav / INITIAL_NAV) - 1 if series else 0.0,
                "spy_latest_nav": latest_spy_nav,
                "spy_total_return": (latest_spy_nav / INITIAL_NAV) - 1 if series else 0.0,
                "excess_return_vs_spy": (
                    ((latest_nav / INITIAL_NAV) - 1) - ((latest_spy_nav / INITIAL_NAV) - 1)
                    if series
                    else 0.0
                ),
                "rebalance_days": len(series),
                "series": series,
            }
        )

    return {
        "generated_at": utc_now_iso(),
        "initial_nav": INITIAL_NAV,
        "sources": sources,
    }


def export_portfolio_json(
    conn: sqlite3.Connection,
    output_path: str | Path = DEFAULT_PORTFOLIO_PATH,
) -> dict[str, Any]:
    payload = build_portfolio_report(conn)
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return payload


def _simulate_source(
    source: str,
    signals_by_date: dict[str, list[sqlite3.Row]],
    returns_by_ticker: dict[str, dict[str, float]],
) -> list[dict[str, Any]]:
    nav = INITIAL_NAV
    spy_nav = INITIAL_NAV
    spy_returns = returns_by_ticker["SPY"]
    market_dates = sorted(spy_returns)
    series: list[dict[str, Any]] = []

    for signal_date in sorted(signals_by_date):
        next_date = _next_market_date(market_dates, signal_date)
        if next_date is None:
            continue
        weights, cash_weight = _weights_from_signals(signals_by_date[signal_date])
        daily_return = 0.0
        for ticker, weight in weights.items():
            daily_return += weight * returns_by_ticker.get(ticker, {}).get(next_date, 0.0)
        spy_daily_return = spy_returns.get(next_date, 0.0)
        nav *= 1 + daily_return
        spy_nav *= 1 + spy_daily_return
        series.append(
            {
                "signal_date": signal_date,
                "date": next_date,
                "source": source,
                "daily_return": daily_return,
                "nav": nav,
                "spy_daily_return": spy_daily_return,
                "spy_nav": spy_nav,
                "cash_weight": cash_weight,
                "weights": weights,
            }
        )

    return series


def _weights_from_signals(rows: list[sqlite3.Row]) -> tuple[dict[str, float], float]:
    inputs: dict[str, float] = {}
    for row in rows:
        score = int(row["score"] or 0)
        if score == 2:
            inputs[row["ticker"]] = 2.0
        elif score == 1:
            inputs[row["ticker"]] = 1.0
    total = sum(inputs.values())
    if total <= 0:
        return {}, 1.0
    return (
        {ticker: value / total for ticker, value in sorted(inputs.items())},
        0.0,
    )


def _next_market_date(market_dates: list[str], signal_date: str) -> str | None:
    for market_date in market_dates:
        if market_date > signal_date:
            return market_date
    return None


def _load_signal_inputs(
    conn: sqlite3.Connection,
) -> dict[str, dict[str, list[sqlite3.Row]]]:
    rows = conn.execute(
        """
        SELECT date, ticker, source, score
        FROM signals
        WHERE success = 1
          AND score IS NOT NULL
        ORDER BY source, date, ticker
        """
    ).fetchall()

    grouped: dict[str, dict[str, list[sqlite3.Row]]] = defaultdict(lambda: defaultdict(list))
    for row in rows:
        grouped[row["source"]][row["date"]].append(row)
    return grouped


def _load_daily_returns(conn: sqlite3.Connection) -> dict[str, dict[str, float]]:
    rows = conn.execute(
        """
        SELECT date, ticker, adjusted_close
        FROM prices
        ORDER BY ticker, date
        """
    ).fetchall()

    returns_by_ticker: dict[str, dict[str, float]] = defaultdict(dict)
    previous_close_by_ticker: dict[str, float] = {}
    for row in rows:
        ticker = row["ticker"]
        close = float(row["adjusted_close"])
        previous_close = previous_close_by_ticker.get(ticker)
        if previous_close is not None and previous_close != 0:
            returns_by_ticker[ticker][row["date"]] = (close / previous_close) - 1
        previous_close_by_ticker[ticker] = close
    return returns_by_ticker
