from __future__ import annotations

import pandas as pd

from src.collectors.yahoo import (
    YAHOO_ANALYST_SOURCE,
    collect_yahoo_analyst_signals,
    fetch_yahoo_analyst_recommendation,
    recommendation_from_info,
    recommendation_from_summary,
)
from src.prices.mock_prices import seed_mock_prices
from src.utils.db import connect, initialize_database
from src.utils.universe import sync_universe


class FakeTicker:
    def __init__(self, info=None, summary=None, error: Exception | None = None):
        self._info = info
        self._summary = summary
        self._error = error

    def get_info(self):
        if self._error:
            raise self._error
        return self._info

    def get_recommendations_summary(self):
        if self._error:
            raise self._error
        return self._summary


def test_recommendation_from_info_uses_recommendation_key():
    ticker = FakeTicker(info={"recommendationKey": "strong_buy"})

    assert recommendation_from_info(ticker) == "Strong Buy"


def test_recommendation_from_summary_uses_current_period_counts():
    ticker = FakeTicker(
        info={},
        summary=pd.DataFrame(
            [
                {
                    "period": "-1m",
                    "strongBuy": 1,
                    "buy": 1,
                    "hold": 5,
                    "sell": 0,
                    "strongSell": 0,
                },
                {
                    "period": "0m",
                    "strongBuy": 4,
                    "buy": 2,
                    "hold": 1,
                    "sell": 0,
                    "strongSell": 0,
                },
            ]
        ),
    )

    assert recommendation_from_summary(ticker) == "Strong Buy"


def test_fetch_yahoo_analyst_recommendation_falls_back_to_summary():
    def ticker_factory(_ticker):
        return FakeTicker(
            info={},
            summary={
                "period": "0m",
                "strongBuy": 0,
                "buy": 2,
                "hold": 4,
                "sell": 1,
                "strongSell": 0,
            },
        )

    assert (
        fetch_yahoo_analyst_recommendation(
            "AAPL",
            ticker_factory=ticker_factory,
            retries=1,
            sleep_seconds=0,
        )
        == "Hold"
    )


def test_collect_yahoo_analyst_signals_stores_successes(tmp_path):
    db_path = tmp_path / "signal_league.sqlite"
    initialize_database(db_path)

    def ticker_factory(ticker):
        signals = {"AAPL": "buy", "MSFT": "hold"}
        return FakeTicker(info={"recommendationKey": signals[ticker]})

    with connect(db_path) as conn:
        sync_universe(conn)
        seed_mock_prices(conn)
        result = collect_yahoo_analyst_signals(
            conn,
            signal_date="2026-01-02",
            limit=2,
            ticker_factory=ticker_factory,
            retries=1,
            sleep_seconds=0,
        )
        rows = conn.execute(
            """
            SELECT ticker, source, category, raw_signal, normalized_signal, score,
                   price_at_signal, success, error_message
            FROM signals
            ORDER BY ticker
            """
        ).fetchall()
        run = conn.execute(
            "SELECT source, attempted, succeeded, failed FROM collection_runs"
        ).fetchone()

    assert result == {"attempted": 2, "succeeded": 2, "failed": 0}
    assert [row["ticker"] for row in rows] == ["AAPL", "MSFT"]
    assert rows[0]["source"] == YAHOO_ANALYST_SOURCE
    assert rows[0]["category"] == "analyst_consensus"
    assert rows[0]["raw_signal"] == "Buy"
    assert rows[0]["normalized_signal"] == "Buy"
    assert rows[0]["score"] == 1
    assert rows[0]["price_at_signal"] == 185.0
    assert rows[0]["success"] == 1
    assert rows[0]["error_message"] is None
    assert run["attempted"] == 2
    assert run["succeeded"] == 2
    assert run["failed"] == 0


def test_collect_yahoo_analyst_signals_stores_failures(tmp_path):
    db_path = tmp_path / "signal_league.sqlite"
    initialize_database(db_path)

    def ticker_factory(ticker):
        if ticker == "AAPL":
            return FakeTicker(info={"recommendationKey": "buy"})
        return FakeTicker(error=RuntimeError("Yahoo unavailable"))

    with connect(db_path) as conn:
        sync_universe(conn)
        result = collect_yahoo_analyst_signals(
            conn,
            signal_date="2026-01-02",
            limit=2,
            ticker_factory=ticker_factory,
            retries=1,
            sleep_seconds=0,
        )
        rows = conn.execute(
            """
            SELECT ticker, success, normalized_signal, score, error_message
            FROM signals
            ORDER BY ticker
            """
        ).fetchall()
        run = conn.execute(
            "SELECT attempted, succeeded, failed FROM collection_runs"
        ).fetchone()

    assert result == {"attempted": 2, "succeeded": 1, "failed": 1}
    assert rows[0]["ticker"] == "AAPL"
    assert rows[0]["success"] == 1
    assert rows[1]["ticker"] == "MSFT"
    assert rows[1]["success"] == 0
    assert rows[1]["normalized_signal"] is None
    assert rows[1]["score"] is None
    assert "Failed to fetch Yahoo analyst recommendation" in rows[1]["error_message"]
    assert run["attempted"] == 2
    assert run["succeeded"] == 1
    assert run["failed"] == 1
