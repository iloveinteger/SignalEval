from __future__ import annotations

from pathlib import Path

from src.collectors.investing import (
    INVESTING_FINANCIAL_SOURCE,
    INVESTING_TECHNICAL_SOURCE,
    collect_investing_sample_signals,
)
from src.utils.db import (
    connect,
    initialize_database,
    upsert_price,
    upsert_signal,
    utc_now_iso,
)

SAMPLES_DIR = Path(__file__).resolve().parents[1] / "samples" / "investing"


def test_collect_investing_sample_signals_inserts_investing_rows_and_keeps_baseline(
    tmp_path,
):
    db_path = tmp_path / "signal_league.sqlite"
    initialize_database(db_path)
    collected_at = utc_now_iso()

    with connect(db_path) as conn:
        with conn:
            upsert_price(
                conn,
                {
                    "date": "2026-06-18",
                    "ticker": "AAPL",
                    "adjusted_close": 298.01,
                },
            )
            upsert_signal(
                conn,
                {
                    "date": "2026-06-18",
                    "ticker": "AAPL",
                    "source": "Random Baseline",
                    "category": "random_baseline",
                    "raw_signal": "Neutral",
                    "normalized_signal": "Neutral",
                    "score": 0,
                    "price_at_signal": 298.01,
                    "collected_at": collected_at,
                    "success": 1,
                    "error_message": None,
                },
            )

        result = collect_investing_sample_signals(conn, samples_dir=SAMPLES_DIR)
        rows = conn.execute(
            """
            SELECT date, ticker, source, category, raw_signal, normalized_signal,
                   score, price_at_signal, metadata_json, success
            FROM signals
            ORDER BY source
            """
        ).fetchall()
        runs = conn.execute(
            """
            SELECT source, attempted, succeeded, failed
            FROM collection_runs
            ORDER BY source
            """
        ).fetchall()

    assert result == {"attempted": 2, "succeeded": 2, "failed": 0, "stored": 2}
    assert {row["source"] for row in rows} == {
        INVESTING_FINANCIAL_SOURCE,
        INVESTING_TECHNICAL_SOURCE,
        "Random Baseline",
    }

    technical = next(row for row in rows if row["source"] == INVESTING_TECHNICAL_SOURCE)
    assert technical["date"] == "2026-06-18"
    assert technical["ticker"] == "AAPL"
    assert technical["category"] == "technical"
    assert technical["raw_signal"] == "Neutral"
    assert technical["normalized_signal"] == "Neutral"
    assert technical["score"] == 0
    assert technical["price_at_signal"] == 298.01
    assert '"selected_signal": "Buy"' in technical["metadata_json"]
    assert '"daily_signal": "Neutral"' in technical["metadata_json"]
    assert technical["success"] == 1

    financial = next(row for row in rows if row["source"] == INVESTING_FINANCIAL_SOURCE)
    assert financial["date"] == "2026-06-18"
    assert financial["ticker"] == "AAPL"
    assert financial["category"] == "analyst_consensus"
    assert financial["raw_signal"] == "Buy"
    assert financial["normalized_signal"] == "Buy"
    assert financial["score"] == 1
    assert financial["price_at_signal"] == 298.01
    assert '"analyst_total_count": 47' in financial["metadata_json"]
    assert '"analyst_score_raw": 0.5531914893617021' in financial["metadata_json"]
    assert financial["success"] == 1

    baseline = next(row for row in rows if row["source"] == "Random Baseline")
    assert baseline["category"] == "random_baseline"
    assert baseline["raw_signal"] == "Neutral"

    assert {run["source"] for run in runs} == {
        INVESTING_FINANCIAL_SOURCE,
        INVESTING_TECHNICAL_SOURCE,
    }
    assert all(run["attempted"] == 1 for run in runs)
    assert all(run["succeeded"] == 1 for run in runs)
    assert all(run["failed"] == 0 for run in runs)
