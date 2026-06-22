from __future__ import annotations

from src.collectors.random_baseline import (
    RANDOM_BASELINE_SOURCE,
    build_random_baseline_signal,
    collect_random_baseline_signals,
)
from src.prices.mock_prices import seed_mock_prices
from src.utils.db import connect, initialize_database
from src.utils.universe import sync_universe


def test_build_random_baseline_signal_is_deterministic(tmp_path):
    db_path = tmp_path / "signal_league.sqlite"
    initialize_database(db_path)

    with connect(db_path) as conn:
        sync_universe(conn)
        seed_mock_prices(conn, periods=260)
        first = build_random_baseline_signal(
            conn,
            ticker="AAPL",
            signal_date="2026-06-18",
            collected_at="2026-06-22T00:00:00+00:00",
        )
        second = build_random_baseline_signal(
            conn,
            ticker="AAPL",
            signal_date="2026-06-18",
            collected_at="2026-06-22T00:00:01+00:00",
        )

    assert first.raw_signal == second.raw_signal
    assert first.normalized_signal == second.normalized_signal
    assert first.score == second.score
    assert first.price_at_signal is not None


def test_collect_random_baseline_signals_stores_rows_for_active_universe(tmp_path):
    db_path = tmp_path / "signal_league.sqlite"
    initialize_database(db_path)

    with connect(db_path) as conn:
        sync_universe(conn)
        seed_mock_prices(conn, periods=260)
        count = collect_random_baseline_signals(conn, signal_date="2026-06-18")
        rows = conn.execute(
            """
            SELECT source, category, COUNT(*) AS count
            FROM signals
            GROUP BY source, category
            """
        ).fetchall()

    assert count == 10
    assert len(rows) == 1
    assert rows[0]["source"] == RANDOM_BASELINE_SOURCE
    assert rows[0]["category"] == "random_baseline"
    assert rows[0]["count"] == 10
