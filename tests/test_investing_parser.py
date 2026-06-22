from __future__ import annotations

from pathlib import Path

from src.collectors.investing import (
    inspect_investing_financial_summary_file,
    parse_investing_technical_file,
)

SAMPLES_DIR = Path(__file__).resolve().parents[1] / "samples" / "investing"
TECHNICAL_SAMPLE = (
    SAMPLES_DIR
    / "AAPL Technical Analysis, RSI and Moving Averages - Investing.com.html"
)
FINANCIAL_SAMPLE = (
    SAMPLES_DIR
    / "NASDAQ_AAPL Financials _ Apple - Investing.com.html"
)


def test_parse_investing_technical_extracts_overall_signal_from_saved_html():
    signal = parse_investing_technical_file(TECHNICAL_SAMPLE)

    assert signal.ticker == "AAPL"
    assert signal.source == "Investing.com Technical Analysis"
    assert signal.category == "technical"
    assert signal.timeframe == "1h"
    assert signal.raw_signal == "Buy"
    assert signal.normalized_signal == "Buy"
    assert signal.score == 1
    assert signal.last_update_time == "2026-06-18 20:05:03"
    assert signal.moving_average_signal == "Buy"
    assert signal.moving_average_counts == {"buy": 7, "sell": 5}
    assert signal.technical_indicator_signal == "Buy"
    assert signal.technical_indicator_counts == {
        "buy": 3,
        "neutral": 7,
        "sell": 1,
    }


def test_parse_investing_technical_also_exposes_daily_signal_from_saved_html():
    signal = parse_investing_technical_file(TECHNICAL_SAMPLE)

    assert signal.daily_signal == "Neutral"
    assert signal.daily_last_update_time == "2026-06-18 20:05:03"


def test_inspect_financial_summary_extracts_analyst_and_financial_fields():
    inspection = inspect_investing_financial_summary_file(FINANCIAL_SAMPLE)

    assert inspection.ticker == "AAPL"
    assert inspection.contains_analyst_signal_fields
    assert inspection.analyst_fields["overall_consensus"] == "Buy"
    assert inspection.analyst_fields["ratings_total"] == "47 analysts"
    assert inspection.analyst_fields["buy_ratings"] == "29 Buy"
    assert inspection.analyst_fields["hold_ratings"] == "15 Hold"
    assert inspection.analyst_fields["sell_ratings"] == "3 Sell"
    assert inspection.analyst_fields["price_target_average"] == "314.42"
    assert inspection.analyst_fields["price_target_upside"] == "(+5.51% Upside)"

    assert inspection.contains_financial_signal_fields
    assert inspection.financial_fields == {
        "pe_ratio": "36.01",
        "price_book": "40.4",
        "debt_equity": "79.55%",
        "return_on_equity": "141.47%",
        "dividend_yield": "0.36%",
        "ebitda": "144.75B",
    }


def test_inspect_financial_summary_detects_locked_valuation_fields():
    inspection = inspect_investing_financial_summary_file(FINANCIAL_SAMPLE)

    assert inspection.contains_valuation_signal_fields
    assert inspection.valuation_fields == {
        "fair_value": "Unlock",
        "fair_value_upside": "Unlock",
    }
    assert not inspection.contains_unlocked_valuation_values
