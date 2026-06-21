from __future__ import annotations

from datetime import date

from src.prices.mock_prices import (
    business_dates,
    generate_mock_price_rows,
    seed_mock_prices,
)
from src.utils.db import connect, initialize_database


def test_business_dates_skips_weekends():
    assert business_dates(date(2026, 1, 2), 3) == [
        date(2026, 1, 2),
        date(2026, 1, 5),
        date(2026, 1, 6),
    ]


def test_generate_mock_price_rows_is_deterministic():
    rows = generate_mock_price_rows(["AAPL", "SPY"], start_date=date(2026, 1, 2), periods=2)

    assert rows == [
        {"date": "2026-01-02", "ticker": "AAPL", "adjusted_close": 185.0},
        {"date": "2026-01-05", "ticker": "AAPL", "adjusted_close": 185.4285},
        {"date": "2026-01-02", "ticker": "SPY", "adjusted_close": 480.0},
        {"date": "2026-01-05", "ticker": "SPY", "adjusted_close": 480.3079},
    ]


def test_seed_mock_prices_writes_universe_and_benchmarks(tmp_path):
    db_path = tmp_path / "signal_league.sqlite"
    initialize_database(db_path)

    with connect(db_path) as conn:
        count = seed_mock_prices(conn, periods=2)
        stored = conn.execute("SELECT COUNT(*) FROM prices").fetchone()[0]

    assert count == 44
    assert stored == 44
