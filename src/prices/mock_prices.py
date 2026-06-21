from __future__ import annotations

import sqlite3
from collections.abc import Iterable
from datetime import date, timedelta
from pathlib import Path

from src.utils.benchmarks import BENCHMARK_TICKERS
from src.utils.db import upsert_prices
from src.utils.universe import DEFAULT_UNIVERSE_PATH, load_sp500_csv

MOCK_PRICE_START_DATE = date(2026, 1, 2)
MOCK_PRICE_PERIODS = 130

BASE_PRICES = {
    "AAPL": 185.00,
    "MSFT": 420.00,
    "NVDA": 125.00,
    "AMZN": 155.00,
    "GOOGL": 145.00,
    "META": 365.00,
    "TSLA": 240.00,
    "JPM": 175.00,
    "XOM": 103.00,
    "UNH": 525.00,
    "SPY": 480.00,
    "XLK": 205.00,
    "XLF": 39.00,
    "XLV": 134.00,
    "XLE": 86.00,
    "XLI": 112.00,
    "XLY": 174.00,
    "XLP": 72.00,
    "XLU": 63.00,
    "XLB": 80.00,
    "XLRE": 39.00,
    "XLC": 77.00,
}

TOTAL_RETURNS_120D = {
    "AAPL": 0.32,
    "MSFT": 0.26,
    "NVDA": 0.45,
    "AMZN": 0.15,
    "GOOGL": 0.22,
    "META": -0.08,
    "TSLA": -0.30,
    "JPM": 0.10,
    "XOM": 0.04,
    "UNH": -0.06,
    "SPY": 0.08,
    "XLK": 0.18,
    "XLF": 0.07,
    "XLV": 0.03,
    "XLE": 0.02,
    "XLI": 0.06,
    "XLY": 0.09,
    "XLP": 0.025,
    "XLU": 0.015,
    "XLB": 0.05,
    "XLRE": 0.035,
    "XLC": 0.12,
}


def seed_mock_prices(
    conn: sqlite3.Connection,
    *,
    universe_path: str | Path = DEFAULT_UNIVERSE_PATH,
    start_date: date = MOCK_PRICE_START_DATE,
    periods: int = MOCK_PRICE_PERIODS,
) -> int:
    tickers = load_mock_price_tickers(universe_path)
    rows = generate_mock_price_rows(tickers, start_date=start_date, periods=periods)
    return upsert_prices(conn, rows)


def load_mock_price_tickers(
    universe_path: str | Path = DEFAULT_UNIVERSE_PATH,
) -> list[str]:
    universe_tickers = [
        stock["ticker"]
        for stock in load_sp500_csv(universe_path)
        if int(stock.get("active", 1)) == 1
    ]
    return _dedupe([*universe_tickers, *BENCHMARK_TICKERS])


def generate_mock_price_rows(
    tickers: Iterable[str],
    *,
    start_date: date = MOCK_PRICE_START_DATE,
    periods: int = MOCK_PRICE_PERIODS,
) -> list[dict[str, object]]:
    dates = business_dates(start_date, periods)
    rows: list[dict[str, object]] = []

    for ticker in _dedupe(tickers):
        base_price = BASE_PRICES.get(ticker, 100.0)
        total_return = TOTAL_RETURNS_120D.get(ticker, 0.05)
        daily_return = (1 + total_return) ** (1 / 120) - 1
        for index, price_date in enumerate(dates):
            rows.append(
                {
                    "date": price_date.isoformat(),
                    "ticker": ticker,
                    "adjusted_close": round(base_price * ((1 + daily_return) ** index), 4),
                }
            )

    return rows


def business_dates(start_date: date, periods: int) -> list[date]:
    dates: list[date] = []
    current = start_date
    while len(dates) < periods:
        if current.weekday() < 5:
            dates.append(current)
        current += timedelta(days=1)
    return dates


def _dedupe(tickers: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for ticker in tickers:
        normalized = str(ticker).strip().upper()
        if normalized and normalized not in seen:
            seen.add(normalized)
            result.append(normalized)
    return result
