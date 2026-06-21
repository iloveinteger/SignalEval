from __future__ import annotations

import json

import pytest

from src.analysis.leaderboard import build_leaderboard, export_leaderboard_json
from src.utils.db import (
    connect,
    initialize_database,
    upsert_forward_return,
    upsert_signal,
)


def test_build_leaderboard_handles_empty_database(tmp_path):
    db_path = tmp_path / "signal_league.sqlite"
    initialize_database(db_path)

    with connect(db_path) as conn:
        leaderboard = build_leaderboard(conn)

    assert leaderboard["rows"] == []
    assert leaderboard["top_level"] == []
    assert leaderboard["metadata"]["signal_count"] == 0


def test_export_leaderboard_json_aggregates_forward_returns(tmp_path):
    db_path = tmp_path / "signal_league.sqlite"
    output_path = tmp_path / "leaderboard.json"
    initialize_database(db_path)

    with connect(db_path) as conn:
        with conn:
            upsert_signal(
                conn,
                {
                    "date": "2026-01-02",
                    "ticker": "AAPL",
                    "source": "investing",
                    "category": "technical",
                    "raw_signal": "Strong Buy",
                    "normalized_signal": "Strong Buy",
                    "score": 2,
                    "price_at_signal": 100.0,
                    "collected_at": "2026-01-02T22:30:00+00:00",
                    "success": 1,
                },
            )
            upsert_signal(
                conn,
                {
                    "date": "2026-01-02",
                    "ticker": "MSFT",
                    "source": "investing",
                    "category": "technical",
                    "raw_signal": "Strong Sell",
                    "normalized_signal": "Strong Sell",
                    "score": -2,
                    "price_at_signal": 100.0,
                    "collected_at": "2026-01-02T22:30:00+00:00",
                    "success": 1,
                },
            )
            signal_rows = conn.execute(
                "SELECT id, ticker FROM signals ORDER BY ticker"
            ).fetchall()
            signal_ids = {row["ticker"]: row["id"] for row in signal_rows}
            upsert_forward_return(
                conn,
                {
                    "signal_id": signal_ids["AAPL"],
                    "horizon": 60,
                    "raw_return": 0.12,
                    "spy_return": 0.04,
                    "spy_alpha": 0.08,
                    "sector_alpha": 0.05,
                    "computed_at": "2026-01-05T00:00:00+00:00",
                },
            )
            upsert_forward_return(
                conn,
                {
                    "signal_id": signal_ids["MSFT"],
                    "horizon": 60,
                    "raw_return": -0.02,
                    "spy_return": 0.04,
                    "spy_alpha": -0.06,
                    "sector_alpha": -0.03,
                    "computed_at": "2026-01-05T00:00:00+00:00",
                },
            )

        payload = export_leaderboard_json(conn, output_path)

    assert output_path.exists()
    saved = json.loads(output_path.read_text(encoding="utf-8"))
    assert saved["rows"] == payload["rows"]
    assert len(payload["rows"]) == 1

    row = payload["rows"][0]
    assert row["category"] == "technical"
    assert row["source"] == "investing"
    assert row["horizon"] == 60
    assert row["sample_size"] == 2
    assert row["hit_rate"] == pytest.approx(0.5)
    assert row["average_return"] == pytest.approx(0.05)
    assert row["average_spy_alpha"] == pytest.approx(0.01)
    assert row["average_sector_alpha"] == pytest.approx(0.01)
    assert row["long_short_spread"] == pytest.approx(0.14)

    top_row = payload["top_level"][0]
    assert top_row["return_60d"] == pytest.approx(0.05)
    assert top_row["sample_size_60d"] == 2
