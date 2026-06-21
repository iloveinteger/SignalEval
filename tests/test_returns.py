from __future__ import annotations

import pytest

from src.analysis.returns import (
    calculate_return,
    compute_available_forward_returns,
)
from src.utils.db import (
    connect,
    initialize_database,
    upsert_price,
    upsert_signal,
    upsert_stock,
)


def test_calculate_return():
    assert calculate_return(100.0, 112.5) == pytest.approx(0.125)


def test_calculate_return_rejects_zero_start_price():
    with pytest.raises(ValueError):
        calculate_return(0.0, 100.0)


def test_compute_available_forward_returns_uses_trading_day_offsets(tmp_path):
    db_path = tmp_path / "signal_league.sqlite"
    initialize_database(db_path)

    dates = ["2026-01-02", "2026-01-05", "2026-01-06"]
    prices = {
        "AAPL": [100.0, 110.0, 121.0],
        "SPY": [100.0, 104.0, 108.0],
        "XLK": [100.0, 108.0, 116.0],
    }

    with connect(db_path) as conn:
        with conn:
            upsert_stock(
                conn,
                {
                    "ticker": "AAPL",
                    "name": "Apple Inc.",
                    "sector": "Information Technology",
                    "industry": "Hardware",
                    "active": 1,
                },
            )
            upsert_signal(
                conn,
                {
                    "date": "2026-01-02",
                    "ticker": "AAPL",
                    "source": "investing",
                    "category": "technical",
                    "raw_signal": "Buy",
                    "normalized_signal": "Buy",
                    "score": 1,
                    "price_at_signal": 100.0,
                    "collected_at": "2026-01-02T22:30:00+00:00",
                    "success": 1,
                },
            )
            for ticker, closes in prices.items():
                for price_date, adjusted_close in zip(dates, closes):
                    upsert_price(
                        conn,
                        {
                            "date": price_date,
                            "ticker": ticker,
                            "adjusted_close": adjusted_close,
                        },
                    )

        stored_count = compute_available_forward_returns(conn, horizons=(1, 2))
        rows = conn.execute(
            """
            SELECT horizon, raw_return, spy_return, spy_alpha, sector_alpha
            FROM forward_returns
            ORDER BY horizon
            """
        ).fetchall()

    assert stored_count == 2
    assert rows[0]["horizon"] == 1
    assert rows[0]["raw_return"] == pytest.approx(0.10)
    assert rows[0]["spy_return"] == pytest.approx(0.04)
    assert rows[0]["spy_alpha"] == pytest.approx(0.06)
    assert rows[0]["sector_alpha"] == pytest.approx(0.02)

    assert rows[1]["horizon"] == 2
    assert rows[1]["raw_return"] == pytest.approx(0.21)


def test_compute_available_forward_returns_skips_missing_future_prices(tmp_path):
    db_path = tmp_path / "signal_league.sqlite"
    initialize_database(db_path)

    with connect(db_path) as conn:
        with conn:
            upsert_stock(
                conn,
                {
                    "ticker": "MSFT",
                    "name": "Microsoft Corp.",
                    "sector": "Information Technology",
                    "industry": "Software",
                    "active": 1,
                },
            )
            upsert_signal(
                conn,
                {
                    "date": "2026-01-02",
                    "ticker": "MSFT",
                    "source": "zacks",
                    "category": "earnings_revision",
                    "raw_signal": "#1 Strong Buy",
                    "normalized_signal": "Strong Buy",
                    "score": 2,
                    "price_at_signal": 100.0,
                    "collected_at": "2026-01-02T22:30:00+00:00",
                    "success": 1,
                },
            )
            upsert_price(
                conn,
                {
                    "date": "2026-01-02",
                    "ticker": "MSFT",
                    "adjusted_close": 100.0,
                },
            )

        stored_count = compute_available_forward_returns(conn, horizons=(1,))
        rows = conn.execute("SELECT * FROM forward_returns").fetchall()

    assert stored_count == 0
    assert rows == []
