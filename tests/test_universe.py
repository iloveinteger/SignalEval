from __future__ import annotations

import pytest

from src.utils.db import connect, initialize_database
from src.utils.universe import load_sp500_csv, parse_active, sync_universe


def test_load_sp500_csv_parses_required_fields(tmp_path):
    csv_path = tmp_path / "sp500.csv"
    csv_path.write_text(
        "\n".join(
            [
                "ticker,name,sector,industry,active",
                "aapl,Apple Inc.,Information Technology,Hardware,true",
                "msft,Microsoft Corp.,Information Technology,Software,0",
            ]
        ),
        encoding="utf-8",
    )

    stocks = load_sp500_csv(csv_path)

    assert stocks == [
        {
            "ticker": "AAPL",
            "name": "Apple Inc.",
            "sector": "Information Technology",
            "industry": "Hardware",
            "active": 1,
        },
        {
            "ticker": "MSFT",
            "name": "Microsoft Corp.",
            "sector": "Information Technology",
            "industry": "Software",
            "active": 0,
        },
    ]


def test_load_sp500_csv_rejects_missing_columns(tmp_path):
    csv_path = tmp_path / "sp500.csv"
    csv_path.write_text("ticker,name\nAAPL,Apple Inc.\n", encoding="utf-8")

    with pytest.raises(ValueError, match="missing required columns"):
        load_sp500_csv(csv_path)


def test_load_sp500_csv_rejects_duplicate_tickers(tmp_path):
    csv_path = tmp_path / "sp500.csv"
    csv_path.write_text(
        "\n".join(
            [
                "ticker,name,sector,industry,active",
                "AAPL,Apple Inc.,Information Technology,Hardware,1",
                "aapl,Apple Duplicate,Information Technology,Hardware,1",
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="Duplicate ticker"):
        load_sp500_csv(csv_path)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("1", 1),
        ("true", 1),
        ("active", 1),
        ("0", 0),
        ("false", 0),
        ("inactive", 0),
        ("", 1),
        (None, 1),
    ],
)
def test_parse_active(value, expected):
    assert parse_active(value) == expected


def test_sync_universe_inserts_rows(tmp_path):
    db_path = tmp_path / "signal_league.sqlite"
    csv_path = tmp_path / "sp500.csv"
    csv_path.write_text(
        "\n".join(
            [
                "ticker,name,sector,industry,active",
                "AAPL,Apple Inc.,Information Technology,Hardware,1",
            ]
        ),
        encoding="utf-8",
    )
    initialize_database(db_path)

    with connect(db_path) as conn:
        inserted = sync_universe(conn, csv_path)
        row = conn.execute("SELECT ticker, name FROM stocks").fetchone()

    assert inserted == 1
    assert row["ticker"] == "AAPL"
    assert row["name"] == "Apple Inc."
