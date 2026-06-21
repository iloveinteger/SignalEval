from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from src.utils.benchmarks import SECTOR_ETFS, SPY_TICKER
from src.utils.db import upsert_forward_return, utc_now_iso
from src.utils.logging import get_logger

logger = get_logger(__name__)

HORIZONS = (1, 5, 20, 60, 120)


@dataclass(frozen=True)
class ForwardReturn:
    signal_id: int
    horizon: int
    raw_return: float
    spy_return: float | None
    spy_alpha: float | None
    sector_alpha: float | None
    computed_at: str

    def as_db_row(self) -> dict[str, object]:
        return {
            "signal_id": self.signal_id,
            "horizon": self.horizon,
            "raw_return": self.raw_return,
            "spy_return": self.spy_return,
            "spy_alpha": self.spy_alpha,
            "sector_alpha": self.sector_alpha,
            "computed_at": self.computed_at,
        }


def calculate_return(start_price: float, end_price: float) -> float:
    if start_price <= 0:
        raise ValueError("start_price must be greater than zero")
    return (end_price / start_price) - 1.0


def compute_available_forward_returns(
    conn: sqlite3.Connection,
    *,
    horizons: tuple[int, ...] = HORIZONS,
) -> int:
    signals = conn.execute(
        """
        SELECT
          signals.id,
          signals.date,
          signals.ticker,
          stocks.sector
        FROM signals
        LEFT JOIN stocks ON stocks.ticker = signals.ticker
        WHERE signals.success = 1
          AND signals.score IS NOT NULL
        ORDER BY signals.date, signals.ticker, signals.source
        """
    ).fetchall()

    stored_count = 0
    with conn:
        for signal in signals:
            for horizon in horizons:
                forward_return = compute_forward_return_for_signal(
                    conn,
                    signal_id=int(signal["id"]),
                    signal_date=str(signal["date"]),
                    ticker=str(signal["ticker"]),
                    sector=signal["sector"],
                    horizon=horizon,
                )
                if forward_return is None:
                    continue
                upsert_forward_return(conn, forward_return.as_db_row())
                stored_count += 1

    logger.info("Stored %s forward-return rows", stored_count)
    return stored_count


def compute_forward_return_for_signal(
    conn: sqlite3.Connection,
    *,
    signal_id: int,
    signal_date: str,
    ticker: str,
    sector: str | None,
    horizon: int,
) -> ForwardReturn | None:
    stock_return = _ticker_forward_return(conn, ticker, signal_date, horizon)
    if stock_return is None:
        return None

    spy_return = _ticker_forward_return(conn, SPY_TICKER, signal_date, horizon)
    sector_return = None
    if sector:
        sector_ticker = SECTOR_ETFS.get(sector)
        if sector_ticker:
            sector_return = _ticker_forward_return(
                conn,
                sector_ticker,
                signal_date,
                horizon,
            )

    return ForwardReturn(
        signal_id=signal_id,
        horizon=horizon,
        raw_return=stock_return,
        spy_return=spy_return,
        spy_alpha=_subtract_optional(stock_return, spy_return),
        sector_alpha=_subtract_optional(stock_return, sector_return),
        computed_at=utc_now_iso(),
    )


def _ticker_forward_return(
    conn: sqlite3.Connection,
    ticker: str,
    signal_date: str,
    horizon: int,
) -> float | None:
    rows = conn.execute(
        """
        SELECT date, adjusted_close
        FROM prices
        WHERE ticker = ?
        ORDER BY date
        """,
        (ticker.upper(),),
    ).fetchall()
    if not rows:
        return None

    dates = [str(row["date"]) for row in rows]
    try:
        start_index = dates.index(signal_date)
    except ValueError:
        return None

    end_index = start_index + horizon
    if end_index >= len(rows):
        return None

    return calculate_return(
        float(rows[start_index]["adjusted_close"]),
        float(rows[end_index]["adjusted_close"]),
    )


def _subtract_optional(value: float, benchmark: float | None) -> float | None:
    if benchmark is None:
        return None
    return value - benchmark
