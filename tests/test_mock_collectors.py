from __future__ import annotations

from src.collectors.mock import (
    MOCK_SIGNAL_DATE,
    MOCK_SOURCE_BY_CATEGORY,
    collect_mock_signals,
)
from src.prices.mock_prices import MOCK_PRICE_START_DATE, seed_mock_prices
from src.utils.db import connect, initialize_database
from src.utils.universe import sync_universe


def test_collect_mock_signals_writes_three_categories_for_starter_tickers(tmp_path):
    db_path = tmp_path / "signal_league.sqlite"
    initialize_database(db_path)

    with connect(db_path) as conn:
        sync_universe(conn)
        seed_mock_prices(conn, start_date=MOCK_PRICE_START_DATE, periods=130)
        count = collect_mock_signals(conn, signal_date=MOCK_SIGNAL_DATE)

        signals = conn.execute(
            """
            SELECT category, source, COUNT(*) AS count
            FROM signals
            GROUP BY category, source
            ORDER BY category
            """
        ).fetchall()
        runs = conn.execute("SELECT source, attempted, succeeded, failed FROM collection_runs").fetchall()

    assert count == 30
    assert len(signals) == 3
    assert {row["category"] for row in signals} == set(MOCK_SOURCE_BY_CATEGORY)
    assert all(row["count"] == 10 for row in signals)
    assert all(row["attempted"] == 10 for row in runs)
    assert all(row["succeeded"] == 10 for row in runs)
    assert all(row["failed"] == 0 for row in runs)


def test_collect_mock_signals_can_limit_to_one_category(tmp_path):
    db_path = tmp_path / "signal_league.sqlite"
    initialize_database(db_path)

    with connect(db_path) as conn:
        sync_universe(conn)
        count = collect_mock_signals(
            conn,
            signal_date=MOCK_SIGNAL_DATE,
            categories=("technical",),
        )
        categories = conn.execute("SELECT DISTINCT category FROM signals").fetchall()

    assert count == 10
    assert [row["category"] for row in categories] == ["technical"]
