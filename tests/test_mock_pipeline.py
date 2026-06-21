from __future__ import annotations

from src.analysis.returns import compute_available_forward_returns
from src.collectors.mock import collect_mock_signals
from src.prices.mock_prices import seed_mock_prices
from src.site.build_static import build_static_site
from src.utils.db import connect, initialize_database
from src.utils.universe import sync_universe


def test_mock_pipeline_produces_non_empty_leaderboard_site(tmp_path):
    db_path = tmp_path / "signal_league.sqlite"
    docs_dir = tmp_path / "docs"
    export_dir = tmp_path / "exports"
    initialize_database(db_path)

    with connect(db_path) as conn:
        sync_universe(conn)
        seed_mock_prices(conn)
        collect_mock_signals(conn)
        stored_returns = compute_available_forward_returns(conn)

    assert stored_returns == 150

    build_static_site(db_path=db_path, docs_dir=docs_dir, export_dir=export_dir)

    leaderboard_html = (docs_dir / "leaderboard.html").read_text(encoding="utf-8")
    index_html = (docs_dir / "index.html").read_text(encoding="utf-8")

    assert "Mock Technical Summary" in leaderboard_html
    assert "Mock Analyst Consensus" in leaderboard_html
    assert "Mock Earnings Revision" in leaderboard_html
    assert "No leaderboard rows yet." not in leaderboard_html
    assert "Latest Leaderboard" in index_html
