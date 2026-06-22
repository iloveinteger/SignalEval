from __future__ import annotations

import argparse
import html
import json
import re
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.collectors.investing import (  # noqa: E402
    inspect_investing_financial_summary_file,
    parse_investing_technical_file,
)

DEFAULT_SAMPLES_DIR = PROJECT_ROOT / "samples" / "investing"
DEFAULT_TECHNICAL_SAMPLE = (
    DEFAULT_SAMPLES_DIR
    / "AAPL Technical Analysis, RSI and Moving Averages - Investing.com.html"
)
DEFAULT_FINANCIAL_SAMPLE = (
    DEFAULT_SAMPLES_DIR
    / "NASDAQ_AAPL Financials _ Apple - Investing.com.html"
)

SCRIPT_BLOCK_RE = re.compile(
    r"<script(?P<attrs>[^>]*)>(?P<body>.*?)</script>",
    re.IGNORECASE | re.DOTALL,
)
SCRIPT_ATTR_RE = re.compile(r'(\w+(?:-\w+)*)=(["\'])(.*?)\2', re.IGNORECASE | re.DOTALL)
JSON_LIKE_ASSIGNMENT_RE = re.compile(
    r"(window\.[A-Za-z0-9_$.]+)\s*=\s*(\{.*?\}|\[.*?\])(?:;|\s|$)",
    re.DOTALL,
)
URL_RE = re.compile(r"https?://[^\s\"'<>]+", re.IGNORECASE)
PATH_RE = re.compile(r"/(?:api|graphql|_next)[A-Za-z0-9._~:/?#[\]@!$&'()*+,;=%-]*", re.IGNORECASE)


def extract_embedded_json_blocks(html_text: str) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    for match in SCRIPT_BLOCK_RE.finditer(html_text):
        attrs = _script_attrs(match.group("attrs") or "")
        body = (match.group("body") or "").strip()
        block_type = attrs.get("type", "").strip().lower()
        block_id = attrs.get("id")

        if block_id == "__NEXT_DATA__":
            parsed = _safe_json_loads(html.unescape(body))
            if parsed is not None:
                blocks.append(
                    {
                        "kind": "__NEXT_DATA__",
                        "id": block_id,
                        "type": block_type or "application/json",
                        "top_level_keys": sorted(parsed.keys()) if isinstance(parsed, dict) else [],
                    }
                )
            continue

        if block_type == "application/ld+json":
            parsed = _safe_json_loads(html.unescape(body))
            if parsed is not None:
                blocks.append(
                    {
                        "kind": "json-ld",
                        "id": block_id,
                        "type": block_type,
                        "top_level_keys": sorted(parsed.keys()) if isinstance(parsed, dict) else [],
                    }
                )
            continue

        assignment_match = JSON_LIKE_ASSIGNMENT_RE.search(body)
        if assignment_match is None:
            continue
        parsed = _safe_json_loads(assignment_match.group(2))
        if parsed is None:
            continue
        blocks.append(
            {
                "kind": "js-assignment",
                "id": block_id,
                "type": block_type or "text/javascript",
                "variable": assignment_match.group(1),
                "top_level_keys": sorted(parsed.keys()) if isinstance(parsed, dict) else [],
            }
        )

    return blocks


def detect_possible_api_endpoints(html_text: str) -> list[str]:
    candidates: set[str] = set()
    for match in URL_RE.finditer(html_text):
        url = html.unescape(match.group(0))
        lowered = url.lower()
        if any(token in lowered for token in ("api.", "/api/", "graphql", "/_next/", ".svc.cluster.local")):
            candidates.add(url)
    for match in PATH_RE.finditer(html_text):
        path = html.unescape(match.group(0))
        if any(token in path.lower() for token in ("/api", "graphql", "/_next/")):
            candidates.add(path)
    return sorted(candidates)


def inspect_investing_html(path: str | Path) -> dict[str, Any]:
    html_path = Path(path)
    html_text = html_path.read_text(encoding="utf-8", errors="ignore")
    result: dict[str, Any] = {
        "path": str(html_path),
        "embedded_json_blocks": extract_embedded_json_blocks(html_text),
        "possible_api_endpoints": detect_possible_api_endpoints(html_text),
    }

    lower_name = html_path.name.lower()
    if "technical" in lower_name:
        technical = parse_investing_technical_file(html_path)
        result["technical_timeframe_signals"] = technical.timeframe_signals
        result["technical_selected_signal"] = technical.selected_signal
        result["technical_daily_signal"] = technical.daily_signal
    if "financial" in lower_name:
        financial = inspect_investing_financial_summary_file(html_path)
        result["analyst_vote_counts"] = financial.analyst_vote_counts
        result["analyst_total_count"] = financial.analyst_total_count
        result["analyst_consensus_signal"] = financial.analyst_consensus_signal
        result["analyst_score_raw"] = financial.analyst_score_raw
    return result


def print_inspection(result: dict[str, Any]) -> None:
    print(f"FILE: {result['path']}")
    print("Embedded JSON blocks:")
    if result["embedded_json_blocks"]:
        for block in result["embedded_json_blocks"]:
            summary = {
                key: value
                for key, value in block.items()
                if key in {"kind", "id", "type", "variable", "top_level_keys"}
            }
            print("  - " + json.dumps(summary, ensure_ascii=True))
    else:
        print("  - none")

    print("Detected technical timeframe signals:")
    timeframe_signals = result.get("technical_timeframe_signals") or {}
    if timeframe_signals:
        for timeframe, signal in timeframe_signals.items():
            print(f"  - {timeframe}: {signal}")
    else:
        print("  - none")

    print("Detected analyst vote counts:")
    vote_counts = result.get("analyst_vote_counts") or {}
    if vote_counts:
        print("  - " + json.dumps(vote_counts, sort_keys=True))
        print(f"  - total_count: {result.get('analyst_total_count')}")
        print(f"  - consensus_signal: {result.get('analyst_consensus_signal')}")
        print(f"  - score_raw: {result.get('analyst_score_raw')}")
    else:
        print("  - none")

    print("Possible API endpoints found in scripts/text:")
    if result["possible_api_endpoints"]:
        for endpoint in result["possible_api_endpoints"]:
            print(f"  - {endpoint}")
    else:
        print("  - none")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Inspect saved Investing.com HTML for embedded data.")
    parser.add_argument(
        "html_file",
        nargs="*",
        type=Path,
        default=[DEFAULT_TECHNICAL_SAMPLE, DEFAULT_FINANCIAL_SAMPLE],
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    for index, html_file in enumerate(args.html_file):
        if index:
            print()
        print_inspection(inspect_investing_html(html_file))


def _script_attrs(raw_attrs: str) -> dict[str, str]:
    return {
        match.group(1).lower(): html.unescape(match.group(3))
        for match in SCRIPT_ATTR_RE.finditer(raw_attrs or "")
    }


def _safe_json_loads(value: str) -> Any | None:
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return None


if __name__ == "__main__":
    main()
