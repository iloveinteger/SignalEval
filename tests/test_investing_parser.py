from __future__ import annotations

import re
from pathlib import Path

from src.collectors.investing import (
    inspect_investing_financial_summary_file,
    inspect_investing_financial_summary_html,
    parse_investing_technical_file,
    parse_investing_technical_html,
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
    assert signal.raw_signal == "Neutral"
    assert signal.normalized_signal == "Neutral"
    assert signal.score == 0
    assert signal.last_update_time == "2026-06-18 20:05:03"
    assert signal.moving_average_signal == "Buy"
    assert signal.moving_average_counts == {"buy": 7, "sell": 5}
    assert signal.technical_indicator_signal == "Buy"
    assert signal.technical_indicator_counts == {
        "buy": 3,
        "neutral": 7,
        "sell": 1,
    }
    assert signal.selected_signal == "Buy"
    assert signal.selected_normalized_signal == "Buy"
    assert signal.selected_score == 1


def test_parse_investing_technical_also_exposes_daily_signal_from_saved_html():
    signal = parse_investing_technical_file(TECHNICAL_SAMPLE)

    assert signal.daily_signal == "Neutral"
    assert signal.daily_last_update_time == "2026-06-18 20:05:03"
    assert signal.timeframe_signals["Daily"] == "Neutral"


def test_parse_investing_technical_prefers_next_data_when_present():
    html_text = TECHNICAL_SAMPLE.read_text(encoding="utf-8", errors="ignore")
    next_data = re.search(
        r'(<script\s+id="__NEXT_DATA__"[^>]*>.*?</script>)',
        html_text,
        re.IGNORECASE | re.DOTALL,
    )
    title = re.search(
        r"(<title[^>]*>.*?</title>)",
        html_text,
        re.IGNORECASE | re.DOTALL,
    )
    minimized_html = f"<html><head>{title.group(1)}{next_data.group(1)}</head><body></body></html>"

    signal = parse_investing_technical_html(minimized_html)

    assert signal.daily_signal == "Neutral"
    assert signal.selected_signal == "Buy"
    assert signal.timeframe_signals["Hourly"] == "Buy"


def test_parse_investing_technical_falls_back_when_next_data_is_missing():
    html_text = TECHNICAL_SAMPLE.read_text(encoding="utf-8", errors="ignore")
    fallback_html = re.sub(
        r'<script\s+id="__NEXT_DATA__"[^>]*>.*?</script>',
        "",
        html_text,
        flags=re.IGNORECASE | re.DOTALL,
    )

    signal = parse_investing_technical_html(fallback_html)

    assert signal.daily_signal == "Neutral"
    assert signal.selected_signal == "Buy"


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
    assert inspection.analyst_vote_counts == {"buy": 29, "hold": 15, "sell": 3}
    assert inspection.analyst_total_count == 47
    assert round(inspection.analyst_score_raw or 0.0, 3) == 0.553
    assert inspection.analyst_consensus_signal == "Buy"
    assert inspection.analyst_consensus_score == 1

    assert inspection.contains_financial_signal_fields
    assert inspection.financial_fields == {
        "pe_ratio": "36.01",
        "price_book": "40.4",
        "debt_equity": "79.55%",
        "return_on_equity": "141.47%",
        "dividend_yield": "0.36%",
        "ebitda": "144.75B",
    }


def test_inspect_financial_summary_prefers_next_data_for_ratios_and_price_targets():
    html_text = FINANCIAL_SAMPLE.read_text(encoding="utf-8", errors="ignore")
    next_data = re.search(
        r'(<script\s+id="__NEXT_DATA__"[^>]*>.*?</script>)',
        html_text,
        re.IGNORECASE | re.DOTALL,
    )
    title = re.search(
        r"(<title[^>]*>.*?</title>)",
        html_text,
        re.IGNORECASE | re.DOTALL,
    )
    structured_html = (
        f"<html><head>{title.group(1)}{next_data.group(1)}</head>"
        "<body>"
        "Analyst Ratings Overall Consensus Buy Ratings: 47 analysts "
        "29 Buy 15 Hold 3 Sell Analysts 12-Month Price Target: "
        "</body></html>"
    )

    inspection = inspect_investing_financial_summary_html(structured_html)

    assert inspection.analyst_fields["price_target_average"] == "314.42"
    assert inspection.analyst_fields["price_target_upside"] == "(+5.51% Upside)"
    assert inspection.financial_fields["pe_ratio"] == "36.01"
    assert inspection.financial_fields["price_book"] == "40.4"
    assert inspection.financial_fields["debt_equity"] == "79.55%"
    assert inspection.financial_fields["return_on_equity"] == "141.47%"
    assert inspection.financial_fields["dividend_yield"] == "0.36%"


def test_inspect_financial_summary_still_uses_visible_text_for_vote_counts():
    inspection = inspect_investing_financial_summary_file(FINANCIAL_SAMPLE)

    assert inspection.analyst_vote_counts == {"buy": 29, "hold": 15, "sell": 3}
    assert inspection.analyst_total_count == 47
    assert inspection.analyst_consensus_signal == "Buy"


def test_inspect_financial_summary_detects_locked_valuation_fields():
    inspection = inspect_investing_financial_summary_file(FINANCIAL_SAMPLE)

    assert inspection.contains_valuation_signal_fields
    assert inspection.valuation_fields == {
        "fair_value": "Unlock",
        "fair_value_upside": "Unlock",
    }
    assert not inspection.contains_unlocked_valuation_values
