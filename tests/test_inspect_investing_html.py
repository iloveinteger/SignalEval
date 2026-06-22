from __future__ import annotations

from pathlib import Path

from scripts.inspect_investing_html import (
    detect_possible_api_endpoints,
    extract_embedded_json_blocks,
    inspect_investing_html,
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


def test_extract_embedded_json_blocks_detects_next_data_in_technical_sample():
    html_text = TECHNICAL_SAMPLE.read_text(encoding="utf-8", errors="ignore")

    blocks = extract_embedded_json_blocks(html_text)

    next_data = next(block for block in blocks if block["kind"] == "__NEXT_DATA__")
    assert next_data["id"] == "__NEXT_DATA__"
    assert "props" in next_data["top_level_keys"]


def test_detect_possible_api_endpoints_finds_interesting_structured_urls():
    html_text = FINANCIAL_SAMPLE.read_text(encoding="utf-8", errors="ignore")

    endpoints = detect_possible_api_endpoints(html_text)

    assert any("api.investing.com/api/financialdata" in endpoint for endpoint in endpoints)
    assert any("/_next/" in endpoint for endpoint in endpoints)


def test_inspect_investing_html_reports_structured_technical_signals():
    result = inspect_investing_html(TECHNICAL_SAMPLE)

    assert result["technical_selected_signal"] == "Buy"
    assert result["technical_daily_signal"] == "Neutral"
    assert result["technical_timeframe_signals"]["Daily"] == "Neutral"
    assert any(block["kind"] == "__NEXT_DATA__" for block in result["embedded_json_blocks"])


def test_inspect_investing_html_reports_analyst_vote_counts():
    result = inspect_investing_html(FINANCIAL_SAMPLE)

    assert result["analyst_vote_counts"] == {"buy": 29, "hold": 15, "sell": 3}
    assert result["analyst_total_count"] == 47
    assert result["analyst_consensus_signal"] == "Buy"
    assert any(block["kind"] == "__NEXT_DATA__" for block in result["embedded_json_blocks"])
