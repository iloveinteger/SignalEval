from __future__ import annotations

from src.utils.db import (
    connect,
    create_collection_run,
    finish_collection_run,
    initialize_database,
    upsert_price,
    upsert_signal,
    upsert_stock,
)


def test_initialize_database_creates_expected_tables(tmp_path):
    db_path = tmp_path / "signal_league.sqlite"

    initialize_database(db_path)

    with connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'table'
            """
        ).fetchall()

    table_names = {row["name"] for row in rows}
    assert {
        "stocks",
        "signals",
        "prices",
        "forward_returns",
        "collection_runs",
    }.issubset(table_names)


def test_upsert_stock_updates_existing_row(tmp_path):
    db_path = tmp_path / "signal_league.sqlite"
    initialize_database(db_path)

    with connect(db_path) as conn:
        with conn:
            upsert_stock(
                conn,
                {
                    "ticker": "aapl",
                    "name": "Apple Inc.",
                    "sector": "Information Technology",
                    "industry": "Hardware",
                    "active": 1,
                },
            )
            upsert_stock(
                conn,
                {
                    "ticker": "AAPL",
                    "name": "Apple Incorporated",
                    "sector": "Information Technology",
                    "industry": "Hardware",
                    "active": 0,
                },
            )

        rows = conn.execute("SELECT * FROM stocks WHERE ticker = 'AAPL'").fetchall()

    assert len(rows) == 1
    assert rows[0]["name"] == "Apple Incorporated"
    assert rows[0]["active"] == 0


def test_upsert_price_updates_existing_row(tmp_path):
    db_path = tmp_path / "signal_league.sqlite"
    initialize_database(db_path)

    with connect(db_path) as conn:
        with conn:
            upsert_price(
                conn,
                {"date": "2026-06-19", "ticker": "spy", "adjusted_close": 500.0},
            )
            upsert_price(
                conn,
                {"date": "2026-06-19", "ticker": "SPY", "adjusted_close": 501.25},
            )

        row = conn.execute(
            "SELECT adjusted_close FROM prices WHERE date = ? AND ticker = ?",
            ("2026-06-19", "SPY"),
        ).fetchone()

    assert row["adjusted_close"] == 501.25


def test_upsert_signal_respects_daily_source_uniqueness(tmp_path):
    db_path = tmp_path / "signal_league.sqlite"
    initialize_database(db_path)

    base_signal = {
        "date": "2026-06-19",
        "ticker": "MSFT",
        "source": "investing",
        "category": "technical",
        "raw_signal": "Buy",
        "normalized_signal": "Buy",
        "score": 1,
        "price_at_signal": 410.0,
        "metadata_json": {"timeframe": "Daily"},
        "collected_at": "2026-06-19T22:30:00+00:00",
        "success": 1,
    }

    with connect(db_path) as conn:
        with conn:
            upsert_signal(conn, base_signal)
            updated_signal = {**base_signal, "raw_signal": "Strong Buy", "score": 2}
            upsert_signal(conn, updated_signal)

        rows = conn.execute(
            """
            SELECT raw_signal, score, metadata_json
            FROM signals
            WHERE date = ? AND ticker = ? AND source = ?
            """,
            ("2026-06-19", "MSFT", "investing"),
        ).fetchall()

    assert len(rows) == 1
    assert rows[0]["raw_signal"] == "Strong Buy"
    assert rows[0]["score"] == 2
    assert rows[0]["metadata_json"] is not None


def test_collection_run_tracking(tmp_path):
    db_path = tmp_path / "signal_league.sqlite"
    initialize_database(db_path)

    with connect(db_path) as conn:
        with conn:
            run_id = create_collection_run(
                conn,
                run_date="2026-06-19",
                source="investing",
                started_at="2026-06-19T22:30:00+00:00",
            )
            finish_collection_run(
                conn,
                run_id=run_id,
                attempted=10,
                succeeded=8,
                failed=2,
                finished_at="2026-06-19T22:31:00+00:00",
            )

        row = conn.execute(
            "SELECT attempted, succeeded, failed, finished_at FROM collection_runs"
        ).fetchone()

    assert row["attempted"] == 10
    assert row["succeeded"] == 8
    assert row["failed"] == 2
    assert row["finished_at"] == "2026-06-19T22:31:00+00:00"
