from __future__ import annotations

from src.analysis.portfolio import build_portfolio_report
from src.utils.db import connect, initialize_database, upsert_price, upsert_signal


def test_build_portfolio_report_applies_long_only_weight_rules(tmp_path):
    db_path = tmp_path / "signal_league.sqlite"
    initialize_database(db_path)

    with connect(db_path) as conn:
        with conn:
            for row in (
                {"date": "2026-01-02", "ticker": "AAPL", "adjusted_close": 100.0},
                {"date": "2026-01-05", "ticker": "AAPL", "adjusted_close": 110.0},
                {"date": "2026-01-06", "ticker": "AAPL", "adjusted_close": 121.0},
                {"date": "2026-01-02", "ticker": "MSFT", "adjusted_close": 100.0},
                {"date": "2026-01-05", "ticker": "MSFT", "adjusted_close": 90.0},
                {"date": "2026-01-06", "ticker": "MSFT", "adjusted_close": 99.0},
                {"date": "2026-01-02", "ticker": "SPY", "adjusted_close": 100.0},
                {"date": "2026-01-05", "ticker": "SPY", "adjusted_close": 102.0},
                {"date": "2026-01-06", "ticker": "SPY", "adjusted_close": 101.0},
            ):
                upsert_price(conn, row)

            for row in (
                {
                    "date": "2026-01-02",
                    "ticker": "AAPL",
                    "source": "Investing.com Technical Analysis",
                    "category": "technical",
                    "raw_signal": "Strong Buy",
                    "normalized_signal": "Strong Buy",
                    "score": 2,
                    "collected_at": "2026-01-02T00:00:00+00:00",
                },
                {
                    "date": "2026-01-02",
                    "ticker": "MSFT",
                    "source": "Investing.com Technical Analysis",
                    "category": "technical",
                    "raw_signal": "Buy",
                    "normalized_signal": "Buy",
                    "score": 1,
                    "collected_at": "2026-01-02T00:00:00+00:00",
                },
                {
                    "date": "2026-01-05",
                    "ticker": "AAPL",
                    "source": "Investing.com Technical Analysis",
                    "category": "technical",
                    "raw_signal": "Buy",
                    "normalized_signal": "Buy",
                    "score": 1,
                    "collected_at": "2026-01-05T00:00:00+00:00",
                },
                {
                    "date": "2026-01-02",
                    "ticker": "AAPL",
                    "source": "Random Baseline",
                    "category": "random_baseline",
                    "raw_signal": "Neutral",
                    "normalized_signal": "Neutral",
                    "score": 0,
                    "collected_at": "2026-01-02T00:00:00+00:00",
                },
                {
                    "date": "2026-01-02",
                    "ticker": "MSFT",
                    "source": "Random Baseline",
                    "category": "random_baseline",
                    "raw_signal": "Sell",
                    "normalized_signal": "Sell",
                    "score": -1,
                    "collected_at": "2026-01-02T00:00:00+00:00",
                },
                {
                    "date": "2026-01-05",
                    "ticker": "MSFT",
                    "source": "Random Baseline",
                    "category": "random_baseline",
                    "raw_signal": "Strong Buy",
                    "normalized_signal": "Strong Buy",
                    "score": 2,
                    "collected_at": "2026-01-05T00:00:00+00:00",
                },
            ):
                upsert_signal(conn, row)

        report = build_portfolio_report(conn)

    sources = {row["source"]: row for row in report["sources"]}
    investing = sources["Investing.com Technical Analysis"]
    baseline = sources["Random Baseline"]

    assert investing["rebalance_days"] == 2
    assert round(investing["series"][0]["daily_return"], 6) == 0.033333
    assert round(investing["series"][0]["weights"]["AAPL"], 6) == 0.666667
    assert round(investing["series"][0]["weights"]["MSFT"], 6) == 0.333333
    assert round(investing["latest_nav"], 4) == 113.6667
    assert round(investing["spy_latest_nav"], 4) == 101.0

    assert baseline["rebalance_days"] == 2
    assert baseline["series"][0]["weights"] == {}
    assert baseline["series"][0]["cash_weight"] == 1.0
    assert round(baseline["series"][0]["daily_return"], 6) == 0.0
    assert round(baseline["latest_nav"], 4) == 110.0
