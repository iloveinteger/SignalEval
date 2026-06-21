from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from src.utils.db import PROJECT_ROOT, upsert_stocks

DEFAULT_UNIVERSE_PATH = PROJECT_ROOT / "config" / "sp500.csv"
REQUIRED_COLUMNS = ("ticker", "name", "sector", "industry", "active")

TRUE_VALUES = {"1", "true", "t", "yes", "y", "active"}
FALSE_VALUES = {"0", "false", "f", "no", "n", "inactive"}


def load_sp500_csv(path: str | Path = DEFAULT_UNIVERSE_PATH) -> list[dict[str, Any]]:
    csv_path = Path(path)
    with csv_path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        fieldnames = reader.fieldnames or []
        missing_columns = [col for col in REQUIRED_COLUMNS if col not in fieldnames]
        if missing_columns:
            joined = ", ".join(missing_columns)
            raise ValueError(f"{csv_path} is missing required columns: {joined}")

        stocks: list[dict[str, Any]] = []
        seen_tickers: set[str] = set()
        for line_number, row in enumerate(reader, start=2):
            ticker = _required_value(row, "ticker", line_number).upper()
            if ticker in seen_tickers:
                raise ValueError(f"Duplicate ticker {ticker!r} on line {line_number}")
            seen_tickers.add(ticker)

            stocks.append(
                {
                    "ticker": ticker,
                    "name": _required_value(row, "name", line_number),
                    "sector": _required_value(row, "sector", line_number),
                    "industry": _required_value(row, "industry", line_number),
                    "active": parse_active(row.get("active")),
                }
            )

    return stocks


def sync_universe(conn, path: str | Path = DEFAULT_UNIVERSE_PATH) -> int:
    stocks = load_sp500_csv(path)
    return upsert_stocks(conn, stocks)


def parse_active(value: object) -> int:
    if value is None:
        return 1

    if isinstance(value, bool):
        return 1 if value else 0

    text = str(value).strip().lower()
    if text == "":
        return 1
    if text in TRUE_VALUES:
        return 1
    if text in FALSE_VALUES:
        return 0

    raise ValueError(f"Invalid active value: {value!r}")


def _required_value(row: dict[str, str | None], field: str, line_number: int) -> str:
    value = row.get(field)
    if value is None or value.strip() == "":
        raise ValueError(f"Missing {field!r} on line {line_number}")
    return value.strip()
