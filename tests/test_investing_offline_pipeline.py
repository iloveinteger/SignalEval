from __future__ import annotations

from pathlib import Path

from src.analysis.returns import compute_available_forward_returns
from src.collectors.investing import collect_investing_sample_signals
from src.collectors.random_baseline import collect_random_baseline_signals
from src.prices.mock_prices import MOCK_PRICE_START_DATE, seed_mock_prices
from src.site.build_static import build_static_site
from src.utils.db import connect, initialize_database
from src.utils.universe import sync_universe

SAMPLES_DIR = Path(__file__).resolve().parents[1] / "samples" / "investing"


def test_offline_investing_pipeline_builds_site_with_sample_and_control_sources(
    tmp_path,
):
    db_path = tmp_path / "signal_league.sqlite"
    docs_dir = tmp_path / "docs"
    export_dir = tmp_path / "exports"
    initialize_database(db_path)

    with connect(db_path) as conn:
        sync_universe(conn)
        seed_mock_prices(conn, start_date=MOCK_PRICE_START_DATE, periods=260)
        investing_result = collect_investing_sample_signals(conn, samples_dir=SAMPLES_DIR)
        baseline_count = collect_random_baseline_signals(
            conn,
            signal_date="2026-06-18",
        )
        stored_returns = compute_available_forward_returns(conn)

    assert investing_result == {"attempted": 2, "succeeded": 2, "failed": 0, "stored": 2}
    assert baseline_count > 0
    assert stored_returns > 0

    build_static_site(db_path=db_path, docs_dir=docs_dir, export_dir=export_dir)

    leaderboard_html = (docs_dir / "leaderboard.html").read_text(encoding="utf-8")
    aapl_html = (docs_dir / "stocks" / "AAPL.html").read_text(encoding="utf-8")

    assert "Investing.com Technical Analysis (Sample)" in leaderboard_html
    assert "Investing.com Financial / Analyst Summary (Sample)" in leaderboard_html
    assert "Random Baseline (Control)" in leaderboard_html
    assert "Investing.com Technical Analysis (Sample)" in aapl_html
    assert "Investing.com Financial / Analyst Summary (Sample)" in aapl_html
    assert "Random Baseline (Control)" in aapl_html
