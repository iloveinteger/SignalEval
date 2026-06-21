from __future__ import annotations

import math
import time
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pandas as pd
import yfinance as yf

from src.utils.benchmarks import BENCHMARK_TICKERS
from src.utils.db import upsert_prices
from src.utils.logging import get_logger
from src.utils.universe import DEFAULT_UNIVERSE_PATH, load_sp500_csv

logger = get_logger(__name__)


class PriceFetchError(RuntimeError):
    pass


@dataclass(frozen=True)
class PriceRecord:
    date: str
    ticker: str
    adjusted_close: float

    def as_db_row(self) -> dict[str, object]:
        return {
            "date": self.date,
            "ticker": self.ticker,
            "adjusted_close": self.adjusted_close,
        }


@dataclass(frozen=True)
class PriceCollectionResult:
    requested_tickers: tuple[str, ...]
    prices: tuple[PriceRecord, ...]
    missing_tickers: tuple[str, ...]


Downloader = Callable[..., pd.DataFrame]


def default_start_date(days_back: int = 10) -> date:
    return date.today() - timedelta(days=days_back)


def default_end_date() -> date:
    # yfinance treats end dates as exclusive.
    return date.today() + timedelta(days=1)


def load_price_tickers(
    universe_path: str | Path = DEFAULT_UNIVERSE_PATH,
    extra_tickers: Iterable[str] = BENCHMARK_TICKERS,
) -> list[str]:
    universe_tickers = [stock["ticker"] for stock in load_sp500_csv(universe_path)]
    return dedupe_tickers([*universe_tickers, *extra_tickers])


def dedupe_tickers(tickers: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for ticker in tickers:
        normalized = str(ticker).strip().upper()
        if normalized and normalized not in seen:
            seen.add(normalized)
            result.append(normalized)
    return result


def fetch_adjusted_close(
    tickers: Sequence[str],
    *,
    start: str | date,
    end: str | date,
    downloader: Downloader | None = None,
    retries: int = 3,
    sleep_seconds: float = 1.0,
) -> PriceCollectionResult:
    requested_tickers = tuple(dedupe_tickers(tickers))
    if not requested_tickers:
        return PriceCollectionResult((), (), ())

    download = downloader or _download_yfinance
    last_error: Exception | None = None

    for attempt in range(1, retries + 1):
        try:
            logger.info(
                "Fetching Yahoo adjusted closes for %s tickers from %s to %s",
                len(requested_tickers),
                start,
                end,
            )
            frame = download(
                list(requested_tickers),
                start=_date_arg(start),
                end=_date_arg(end),
            )
            return extract_adjusted_close(frame, requested_tickers)
        except Exception as exc:
            last_error = exc
            logger.warning(
                "Yahoo price fetch attempt %s/%s failed: %s",
                attempt,
                retries,
                exc,
            )
            if attempt < retries:
                time.sleep(sleep_seconds)

    raise PriceFetchError(
        f"Failed to fetch Yahoo prices after {retries} attempts"
    ) from last_error


def collect_and_store_prices(
    conn,
    tickers: Sequence[str],
    *,
    start: str | date,
    end: str | date,
    downloader: Downloader | None = None,
    retries: int = 3,
    sleep_seconds: float = 1.0,
) -> PriceCollectionResult:
    result = fetch_adjusted_close(
        tickers,
        start=start,
        end=end,
        downloader=downloader,
        retries=retries,
        sleep_seconds=sleep_seconds,
    )
    inserted = upsert_prices(conn, (record.as_db_row() for record in result.prices))
    logger.info(
        "Stored %s adjusted-close rows; missing tickers: %s",
        inserted,
        ", ".join(result.missing_tickers) or "none",
    )
    return result


def extract_adjusted_close(
    frame: pd.DataFrame,
    requested_tickers: Sequence[str],
) -> PriceCollectionResult:
    requested = tuple(dedupe_tickers(requested_tickers))
    if frame is None or frame.empty:
        return PriceCollectionResult(requested, (), requested)

    prices: list[PriceRecord] = []
    missing: list[str] = []

    for ticker in requested:
        ticker_frame = _frame_for_ticker(frame, ticker, len(requested) == 1)
        if ticker_frame is None or "Adj Close" not in ticker_frame.columns:
            missing.append(ticker)
            continue

        series = ticker_frame["Adj Close"].dropna()
        if series.empty:
            missing.append(ticker)
            continue

        for raw_date, value in series.items():
            adjusted_close = float(value)
            if not math.isfinite(adjusted_close):
                continue
            prices.append(
                PriceRecord(
                    date=_index_date(raw_date),
                    ticker=ticker,
                    adjusted_close=adjusted_close,
                )
            )

    return PriceCollectionResult(requested, tuple(prices), tuple(missing))


def _download_yfinance(tickers: list[str], *, start: str, end: str) -> pd.DataFrame:
    return yf.download(
        tickers=tickers,
        start=start,
        end=end,
        auto_adjust=False,
        actions=False,
        group_by="ticker",
        threads=True,
        progress=False,
    )


def _frame_for_ticker(
    frame: pd.DataFrame, ticker: str, single_ticker: bool
) -> pd.DataFrame | None:
    if isinstance(frame.columns, pd.MultiIndex):
        return _multiindex_ticker_frame(frame, ticker)
    if single_ticker:
        return frame
    return None


def _multiindex_ticker_frame(frame: pd.DataFrame, ticker: str) -> pd.DataFrame | None:
    columns = frame.columns

    for level in range(columns.nlevels):
        labels = list(columns.get_level_values(level))
        for label in labels:
            if str(label).upper() == ticker:
                return frame.xs(label, axis=1, level=level, drop_level=True)

    return None


def _date_arg(value: str | date) -> str:
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


def _index_date(value: Any) -> str:
    if hasattr(value, "date"):
        return value.date().isoformat()
    return str(value)[:10]
