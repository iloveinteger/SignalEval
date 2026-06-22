from __future__ import annotations

import json

from src.site.build_static import build_static_site, result_status
from src.utils.db import (
    connect,
    create_collection_run,
    finish_collection_run,
    initialize_database,
    upsert_price,
    upsert_signal,
    upsert_stock,
)


def test_build_static_site_handles_empty_database(tmp_path):
    db_path = tmp_path / "signal_league.sqlite"
    docs_dir = tmp_path / "docs"
    export_dir = tmp_path / "exports"
    initialize_database(db_path)

    pages = build_static_site(
        db_path=db_path,
        docs_dir=docs_dir,
        export_dir=export_dir,
    )

    assert pages["index"].exists()
    assert pages["leaderboard"].exists()
    assert pages["portfolio"].exists()
    assert pages["stocks"].exists()
    assert pages["data_quality"].exists()
    assert (export_dir / "leaderboard.json").exists()
    assert (export_dir / "portfolio.json").exists()
    assert (export_dir / "data_quality.json").exists()

    index_html = pages["index"].read_text(encoding="utf-8")
    leaderboard_html = pages["leaderboard"].read_text(encoding="utf-8")
    portfolio_html = pages["portfolio"].read_text(encoding="utf-8")
    quality_html = pages["data_quality"].read_text(encoding="utf-8")
    stocks_html = pages["stocks"].read_text(encoding="utf-8")

    assert "not financial advice" in index_html
    assert "stocks.html" in index_html
    assert "portfolio.html" in index_html
    assert "No evaluated signals are available yet." in index_html
    assert "No leaderboard rows yet." in leaderboard_html
    assert "No portfolio rows are available yet." in portfolio_html
    assert "stocks.html" in leaderboard_html
    assert "No tracked stocks are available yet." in stocks_html
    assert "No collection runs have been recorded yet." in quality_html


def test_build_static_site_renders_limited_sample_data(tmp_path):
    db_path = tmp_path / "signal_league.sqlite"
    docs_dir = tmp_path / "docs"
    export_dir = tmp_path / "exports"
    initialize_database(db_path)

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
                    "metadata_json": {"daily_signal": "Buy"},
                    "collected_at": "2026-01-02T22:30:00+00:00",
                    "success": 1,
                },
            )
            signal_id = conn.execute("SELECT id FROM signals").fetchone()["id"]
            conn.execute(
                """
                INSERT INTO forward_returns (
                  signal_id,
                  horizon,
                  raw_return,
                  spy_return,
                  spy_alpha,
                  sector_alpha,
                  computed_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    signal_id,
                    20,
                    0.08,
                    0.03,
                    0.05,
                    0.04,
                    "2026-01-05T00:00:00+00:00",
                ),
            )
            upsert_price(
                conn,
                {
                    "date": "2026-01-02",
                    "ticker": "AAPL",
                    "adjusted_close": 100.0,
                },
            )
            run_id = create_collection_run(
                conn,
                run_date="2026-01-02",
                source="investing",
                started_at="2026-01-02T22:30:00+00:00",
            )
            finish_collection_run(
                conn,
                run_id=run_id,
                attempted=1,
                succeeded=1,
                failed=0,
                finished_at="2026-01-02T22:31:00+00:00",
            )

    pages = build_static_site(
        db_path=db_path,
        docs_dir=docs_dir,
        export_dir=export_dir,
    )

    leaderboard = json.loads(
        (export_dir / "leaderboard.json").read_text(encoding="utf-8")
    )
    leaderboard_html = pages["leaderboard"].read_text(encoding="utf-8")
    portfolio_html = pages["portfolio"].read_text(encoding="utf-8")
    quality_html = pages["data_quality"].read_text(encoding="utf-8")
    stocks_html = pages["stocks"].read_text(encoding="utf-8")
    stock_html = pages["stock_AAPL"].read_text(encoding="utf-8")

    assert leaderboard["top_level"][0]["return_20d"] == 0.08
    assert "technical" in leaderboard_html
    assert "8.00%" in leaderboard_html
    assert "investing" in quality_html
    assert 'href="stocks/AAPL.html"' in stocks_html
    assert "Apple Inc." in stock_html
    assert "Information Technology" in stock_html
    assert "Hardware" in stock_html
    assert "Buy" in stock_html
    assert "100.00" in stock_html
    assert "20D" in stock_html
    assert "8.00%" in stock_html
    assert "correct" in stock_html
    assert "pending" in stock_html
    assert "Portfolio" in portfolio_html


def test_result_status_classification():
    assert result_status(1, None) == "pending"
    assert result_status(0, 0.10) == "neutral"
    assert result_status(1, 0.0) == "neutral"
    assert result_status(1, 0.05) == "correct"
    assert result_status(-1, -0.05) == "correct"
    assert result_status(1, -0.05) == "incorrect"
    assert result_status(-1, 0.05) == "incorrect"
