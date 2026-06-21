from __future__ import annotations

import sqlite3
from collections.abc import Iterable, Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB_PATH = PROJECT_ROOT / "data" / "signal_league.sqlite"

SCHEMA_STATEMENTS = (
    """
    CREATE TABLE IF NOT EXISTS stocks (
      ticker TEXT PRIMARY KEY,
      name TEXT NOT NULL,
      sector TEXT,
      industry TEXT,
      active INTEGER DEFAULT 1
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS signals (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      date TEXT NOT NULL,
      ticker TEXT NOT NULL,
      source TEXT NOT NULL,
      category TEXT NOT NULL,
      raw_signal TEXT,
      normalized_signal TEXT,
      score INTEGER,
      price_at_signal REAL,
      collected_at TEXT NOT NULL,
      success INTEGER DEFAULT 1,
      error_message TEXT,
      UNIQUE(date, ticker, source)
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS prices (
      date TEXT NOT NULL,
      ticker TEXT NOT NULL,
      adjusted_close REAL NOT NULL,
      PRIMARY KEY(date, ticker)
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS forward_returns (
      signal_id INTEGER NOT NULL,
      horizon INTEGER NOT NULL,
      raw_return REAL,
      spy_return REAL,
      spy_alpha REAL,
      sector_alpha REAL,
      computed_at TEXT NOT NULL,
      PRIMARY KEY(signal_id, horizon)
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS collection_runs (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      run_date TEXT NOT NULL,
      source TEXT NOT NULL,
      attempted INTEGER,
      succeeded INTEGER,
      failed INTEGER,
      started_at TEXT,
      finished_at TEXT
    );
    """,
)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def connect(db_path: str | Path = DEFAULT_DB_PATH) -> sqlite3.Connection:
    path = Path(db_path)
    if path != Path(":memory:"):
        path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def create_schema(conn: sqlite3.Connection) -> None:
    for statement in SCHEMA_STATEMENTS:
        conn.execute(statement)
    conn.commit()


def initialize_database(db_path: str | Path = DEFAULT_DB_PATH) -> Path:
    path = Path(db_path)
    with connect(path) as conn:
        create_schema(conn)
    return path


def upsert_stock(conn: sqlite3.Connection, stock: Mapping[str, Any]) -> None:
    ticker = _required_text(stock, "ticker").upper()
    name = _required_text(stock, "name")
    active = 1 if bool(stock.get("active", 1)) else 0

    conn.execute(
        """
        INSERT INTO stocks (ticker, name, sector, industry, active)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(ticker) DO UPDATE SET
          name = excluded.name,
          sector = excluded.sector,
          industry = excluded.industry,
          active = excluded.active
        """,
        (
            ticker,
            name,
            _optional_text(stock.get("sector")),
            _optional_text(stock.get("industry")),
            active,
        ),
    )


def upsert_stocks(
    conn: sqlite3.Connection, stocks: Iterable[Mapping[str, Any]]
) -> int:
    count = 0
    with conn:
        for stock in stocks:
            upsert_stock(conn, stock)
            count += 1
    return count


def upsert_price(conn: sqlite3.Connection, price: Mapping[str, Any]) -> None:
    conn.execute(
        """
        INSERT INTO prices (date, ticker, adjusted_close)
        VALUES (?, ?, ?)
        ON CONFLICT(date, ticker) DO UPDATE SET
          adjusted_close = excluded.adjusted_close
        """,
        (
            _required_text(price, "date"),
            _required_text(price, "ticker").upper(),
            float(price["adjusted_close"]),
        ),
    )


def upsert_prices(conn: sqlite3.Connection, prices: Iterable[Mapping[str, Any]]) -> int:
    count = 0
    with conn:
        for price in prices:
            upsert_price(conn, price)
            count += 1
    return count


def upsert_signal(conn: sqlite3.Connection, signal: Mapping[str, Any]) -> None:
    collected_at = signal.get("collected_at") or utc_now_iso()

    conn.execute(
        """
        INSERT INTO signals (
          date,
          ticker,
          source,
          category,
          raw_signal,
          normalized_signal,
          score,
          price_at_signal,
          collected_at,
          success,
          error_message
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(date, ticker, source) DO UPDATE SET
          category = excluded.category,
          raw_signal = excluded.raw_signal,
          normalized_signal = excluded.normalized_signal,
          score = excluded.score,
          price_at_signal = excluded.price_at_signal,
          collected_at = excluded.collected_at,
          success = excluded.success,
          error_message = excluded.error_message
        """,
        (
            _required_text(signal, "date"),
            _required_text(signal, "ticker").upper(),
            _required_text(signal, "source"),
            _required_text(signal, "category"),
            _optional_text(signal.get("raw_signal")),
            _optional_text(signal.get("normalized_signal")),
            signal.get("score"),
            signal.get("price_at_signal"),
            collected_at,
            int(signal.get("success", 1)),
            _optional_text(signal.get("error_message")),
        ),
    )


def upsert_forward_return(
    conn: sqlite3.Connection, forward_return: Mapping[str, Any]
) -> None:
    computed_at = forward_return.get("computed_at") or utc_now_iso()

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
        ON CONFLICT(signal_id, horizon) DO UPDATE SET
          raw_return = excluded.raw_return,
          spy_return = excluded.spy_return,
          spy_alpha = excluded.spy_alpha,
          sector_alpha = excluded.sector_alpha,
          computed_at = excluded.computed_at
        """,
        (
            int(forward_return["signal_id"]),
            int(forward_return["horizon"]),
            forward_return.get("raw_return"),
            forward_return.get("spy_return"),
            forward_return.get("spy_alpha"),
            forward_return.get("sector_alpha"),
            computed_at,
        ),
    )


def create_collection_run(
    conn: sqlite3.Connection,
    *,
    run_date: str,
    source: str,
    started_at: str | None = None,
) -> int:
    cursor = conn.execute(
        """
        INSERT INTO collection_runs (run_date, source, started_at)
        VALUES (?, ?, ?)
        """,
        (run_date, source, started_at or utc_now_iso()),
    )
    return int(cursor.lastrowid)


def finish_collection_run(
    conn: sqlite3.Connection,
    *,
    run_id: int,
    attempted: int,
    succeeded: int,
    failed: int,
    finished_at: str | None = None,
) -> None:
    conn.execute(
        """
        UPDATE collection_runs
        SET attempted = ?,
            succeeded = ?,
            failed = ?,
            finished_at = ?
        WHERE id = ?
        """,
        (attempted, succeeded, failed, finished_at or utc_now_iso(), run_id),
    )


def _required_text(row: Mapping[str, Any], field: str) -> str:
    value = row.get(field)
    if value is None or str(value).strip() == "":
        raise ValueError(f"Missing required field: {field}")
    return str(value).strip()


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
