from __future__ import annotations

import pandas as pd
import pytest

from src.prices.yahoo_prices import (
    PriceFetchError,
    collect_and_store_prices,
    extract_adjusted_close,
    fetch_adjusted_close,
    load_price_tickers,
)
from src.utils.benchmarks import BENCHMARK_TICKERS
from src.utils.db import connect, initialize_database


def test_load_price_tickers_adds_spy_and_sector_etfs(tmp_path):
    csv_path = tmp_path / "sp500.csv"
    csv_path.write_text(
        "\n".join(
            [
                "ticker,name,sector,industry,active",
                "AAPL,Apple Inc.,Information Technology,Hardware,1",
                "SPY,Existing SPY,ETF,ETF,1",
            ]
        ),
        encoding="utf-8",
    )

    tickers = load_price_tickers(csv_path)

    assert tickers[:2] == ["AAPL", "SPY"]
    for benchmark in BENCHMARK_TICKERS:
        assert benchmark in tickers
    assert tickers.count("SPY") == 1


def test_extract_adjusted_close_from_yfinance_multiindex_frame():
    dates = pd.to_datetime(["2026-01-02", "2026-01-05"])
    columns = pd.MultiIndex.from_tuples(
        [
            ("AAPL", "Adj Close"),
            ("AAPL", "Close"),
            ("MSFT", "Adj Close"),
        ]
    )
    frame = pd.DataFrame(
        [[100.0, 101.0, 200.0], [110.0, 111.0, 220.0]],
        index=dates,
        columns=columns,
    )

    result = extract_adjusted_close(frame, ["AAPL", "MSFT"])

    assert result.missing_tickers == ()
    assert [record.as_db_row() for record in result.prices] == [
        {"date": "2026-01-02", "ticker": "AAPL", "adjusted_close": 100.0},
        {"date": "2026-01-05", "ticker": "AAPL", "adjusted_close": 110.0},
        {"date": "2026-01-02", "ticker": "MSFT", "adjusted_close": 200.0},
        {"date": "2026-01-05", "ticker": "MSFT", "adjusted_close": 220.0},
    ]


def test_extract_adjusted_close_tracks_missing_tickers():
    dates = pd.to_datetime(["2026-01-02"])
    frame = pd.DataFrame(
        [[100.0]],
        index=dates,
        columns=pd.MultiIndex.from_tuples([("AAPL", "Adj Close")]),
    )

    result = extract_adjusted_close(frame, ["AAPL", "MSFT"])

    assert result.missing_tickers == ("MSFT",)
    assert len(result.prices) == 1


def test_fetch_adjusted_close_retries_then_succeeds():
    calls = {"count": 0}
    dates = pd.to_datetime(["2026-01-02"])
    frame = pd.DataFrame(
        [[100.0]],
        index=dates,
        columns=pd.MultiIndex.from_tuples([("AAPL", "Adj Close")]),
    )

    def flaky_downloader(*args, **kwargs):
        calls["count"] += 1
        if calls["count"] == 1:
            raise RuntimeError("temporary failure")
        return frame

    result = fetch_adjusted_close(
        ["AAPL"],
        start="2026-01-01",
        end="2026-01-03",
        downloader=flaky_downloader,
        retries=2,
        sleep_seconds=0,
    )

    assert calls["count"] == 2
    assert len(result.prices) == 1


def test_fetch_adjusted_close_raises_after_retries():
    def failing_downloader(*args, **kwargs):
        raise RuntimeError("network unavailable")

    with pytest.raises(PriceFetchError):
        fetch_adjusted_close(
            ["AAPL"],
            start="2026-01-01",
            end="2026-01-03",
            downloader=failing_downloader,
            retries=2,
            sleep_seconds=0,
        )


def test_collect_and_store_prices_writes_sqlite_rows(tmp_path):
    db_path = tmp_path / "signal_league.sqlite"
    initialize_database(db_path)

    dates = pd.to_datetime(["2026-01-02", "2026-01-05"])
    frame = pd.DataFrame(
        [[100.0], [110.0]],
        index=dates,
        columns=pd.MultiIndex.from_tuples([("AAPL", "Adj Close")]),
    )

    def downloader(*args, **kwargs):
        return frame

    with connect(db_path) as conn:
        collect_and_store_prices(
            conn,
            ["AAPL"],
            start="2026-01-01",
            end="2026-01-06",
            downloader=downloader,
        )
        rows = conn.execute(
            "SELECT date, ticker, adjusted_close FROM prices ORDER BY date"
        ).fetchall()

    assert [dict(row) for row in rows] == [
        {"date": "2026-01-02", "ticker": "AAPL", "adjusted_close": 100.0},
        {"date": "2026-01-05", "ticker": "AAPL", "adjusted_close": 110.0},
    ]
