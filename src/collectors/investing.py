from __future__ import annotations

import html
import json
import re
import sqlite3
import time
from dataclasses import dataclass
from datetime import date
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from src.utils.db import (
    create_collection_run,
    finish_collection_run,
    upsert_signal,
    utc_now_iso,
)
from src.utils.logging import get_logger
from src.utils.normalize import normalize_investing_signal

logger = get_logger(__name__)

INVESTING_TECHNICAL_SOURCE = "Investing.com Technical Analysis"
INVESTING_TECHNICAL_CATEGORY = "technical"
INVESTING_FINANCIAL_SOURCE = "Investing.com Financial / Analyst Summary"
INVESTING_FINANCIAL_CATEGORY = "analyst_consensus"
DEFAULT_INVESTING_SAMPLES_DIR = Path(__file__).resolve().parents[2] / "samples" / "investing"
DEFAULT_INVESTING_LIVE_CACHE_DIR = DEFAULT_INVESTING_SAMPLES_DIR / "live-cache"
TECHNICAL_SAMPLE_FILENAME = "AAPL Technical Analysis, RSI and Moving Averages - Investing.com.html"
FINANCIAL_SAMPLE_FILENAME = "NASDAQ_AAPL Financials _ Apple - Investing.com.html"
LIVE_TECHNICAL_CACHE_FILENAME = "AAPL Technical Analysis, RSI and Moving Averages - Investing.com.live.html"
LIVE_FINANCIAL_CACHE_FILENAME = "NASDAQ_AAPL Financials _ Apple - Investing.com.live.html"
LIVE_SUPPORTED_TICKER = "AAPL"
DEFAULT_FETCH_TIMEOUT_SECONDS = 15.0
DEFAULT_FETCH_RETRIES = 3
DEFAULT_FETCH_SLEEP_SECONDS = 1.0
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/137.0.0.0 Safari/537.36"
)
INVESTING_TECHNICAL_URL_BY_TICKER = {
    "AAPL": "https://www.investing.com/equities/apple-computer-inc-technical",
}
INVESTING_FINANCIAL_URL_BY_TICKER = {
    "AAPL": "https://www.investing.com/equities/apple-computer-inc-financial-summary",
}

_NEXT_DATA_RE = re.compile(
    r"<script\s+id=[\"']__NEXT_DATA__[\"'][^>]*>(.*?)</script>",
    re.IGNORECASE | re.DOTALL,
)
_LOCKED_VALUES = {"unlock", "unlock value", "locked", "n/a", "--", ""}


class InvestingParseError(ValueError):
    pass


class InvestingFetchError(RuntimeError):
    pass


@dataclass(frozen=True)
class InvestingTechnicalSignal:
    ticker: str | None
    timeframe: str | None
    raw_signal: str
    normalized_signal: str
    score: int
    last_update_time: str | None
    moving_average_signal: str | None
    moving_average_counts: dict[str, int]
    technical_indicator_signal: str | None
    technical_indicator_counts: dict[str, int]
    selected_signal: str | None
    selected_normalized_signal: str | None
    selected_score: int | None
    daily_signal: str | None
    daily_last_update_time: str | None
    timeframe_signals: dict[str, str]
    source: str = INVESTING_TECHNICAL_SOURCE
    category: str = INVESTING_TECHNICAL_CATEGORY


@dataclass(frozen=True)
class InvestingStoredSignal:
    date: str
    ticker: str
    source: str
    category: str
    raw_signal: str
    normalized_signal: str
    score: int
    price_at_signal: float | None
    metadata_json: dict[str, Any] | None
    collected_at: str

    def as_db_row(self) -> dict[str, object]:
        return {
            "date": self.date,
            "ticker": self.ticker,
            "source": self.source,
            "category": self.category,
            "raw_signal": self.raw_signal,
            "normalized_signal": self.normalized_signal,
            "score": self.score,
            "price_at_signal": self.price_at_signal,
            "metadata_json": self.metadata_json,
            "collected_at": self.collected_at,
            "success": 1,
            "error_message": None,
        }


@dataclass(frozen=True)
class InvestingFinancialSummaryInspection:
    ticker: str | None
    analyst_fields: dict[str, str]
    financial_fields: dict[str, str]
    valuation_fields: dict[str, str]
    analyst_vote_counts: dict[str, int]
    analyst_total_count: int | None
    analyst_score_raw: float | None
    analyst_consensus_signal: str | None
    analyst_consensus_score: int | None

    @property
    def contains_analyst_signal_fields(self) -> bool:
        return bool(self.analyst_fields)

    @property
    def contains_financial_signal_fields(self) -> bool:
        return bool(self.financial_fields)

    @property
    def contains_valuation_signal_fields(self) -> bool:
        return bool(self.valuation_fields)

    @property
    def contains_unlocked_valuation_values(self) -> bool:
        return any(_is_unlocked_value(value) for value in self.valuation_fields.values())


class _VisibleTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._skip_depth = 0
        self.tokens: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() in {"script", "style", "noscript"}:
            self._skip_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in {"script", "style", "noscript"} and self._skip_depth:
            self._skip_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        token = _clean_text(data)
        if token:
            self.tokens.append(token)


def parse_investing_technical_file(path: str | Path) -> InvestingTechnicalSignal:
    html_text = Path(path).read_text(encoding="utf-8", errors="ignore")
    return parse_investing_technical_html(html_text)


def collect_investing_live_signals(
    conn: sqlite3.Connection,
    *,
    ticker: str = LIVE_SUPPORTED_TICKER,
    cache_dir: str | Path = DEFAULT_INVESTING_LIVE_CACHE_DIR,
    signal_date: str | None = None,
    timeout_seconds: float = DEFAULT_FETCH_TIMEOUT_SECONDS,
    retries: int = DEFAULT_FETCH_RETRIES,
    sleep_seconds: float = DEFAULT_FETCH_SLEEP_SECONDS,
    user_agent: str = DEFAULT_USER_AGENT,
) -> dict[str, int]:
    normalized_ticker = _validate_live_ticker(ticker)
    cache_path = Path(cache_dir)
    collected_at = utc_now_iso()

    attempted = 0
    succeeded = 0
    failed = 0
    stored = 0
    resolved_signal_date = signal_date

    with conn:
        for source, page_kind, build_signal in (
            (
                INVESTING_TECHNICAL_SOURCE,
                "technical",
                lambda html_text, run_date: build_investing_technical_signal_from_html(
                    conn,
                    ticker=normalized_ticker,
                    html_text=html_text,
                    signal_date=run_date,
                    collected_at=collected_at,
                ),
            ),
            (
                INVESTING_FINANCIAL_SOURCE,
                "financial",
                lambda html_text, run_date: build_investing_financial_signal_from_html(
                    conn,
                    ticker=normalized_ticker,
                    html_text=html_text,
                    signal_date=run_date,
                    collected_at=collected_at,
                ),
            ),
        ):
            attempted += 1
            run_id = create_collection_run(
                conn,
                run_date=resolved_signal_date or date.today().isoformat(),
                source=source,
                started_at=collected_at,
            )
            try:
                html_text = fetch_investing_live_html(
                    ticker=normalized_ticker,
                    page_kind=page_kind,
                    timeout_seconds=timeout_seconds,
                    retries=retries,
                    sleep_seconds=sleep_seconds,
                    user_agent=user_agent,
                )
                cache_file = save_investing_live_html(
                    html_text,
                    ticker=normalized_ticker,
                    page_kind=page_kind,
                    cache_dir=cache_path,
                )
                logger.info(
                    "Saved Investing %s HTML for %s to %s",
                    page_kind,
                    normalized_ticker,
                    cache_file,
                )

                if resolved_signal_date is None:
                    resolved_signal_date = (
                        _live_signal_date_from_html(html_text)
                        or date.today().isoformat()
                    )

                signal = build_signal(html_text, resolved_signal_date)
                upsert_signal(conn, signal.as_db_row())
                succeeded += 1
                stored += 1
                source_succeeded = 1
                source_failed = 0
            except Exception as exc:
                failed += 1
                logger.error(
                    "Investing live %s fetch failed for %s: %s",
                    page_kind,
                    normalized_ticker,
                    exc,
                )
                source_succeeded = 0
                source_failed = 1

            finish_collection_run(
                conn,
                run_id=run_id,
                attempted=1,
                succeeded=source_succeeded,
                failed=source_failed,
                finished_at=utc_now_iso(),
            )

    return {
        "attempted": attempted,
        "succeeded": succeeded,
        "failed": failed,
        "stored": stored,
    }


def collect_investing_sample_signals(
    conn: sqlite3.Connection,
    *,
    samples_dir: str | Path = DEFAULT_INVESTING_SAMPLES_DIR,
    signal_date: str | None = None,
) -> dict[str, int]:
    samples_path = Path(samples_dir)
    technical_path = samples_path / TECHNICAL_SAMPLE_FILENAME
    financial_path = samples_path / FINANCIAL_SAMPLE_FILENAME
    collected_at = utc_now_iso()
    run_date = signal_date or _sample_signal_date(technical_path)

    attempted = 0
    succeeded = 0
    failed = 0
    stored = 0

    with conn:
        for source, build_signal in (
            (
                INVESTING_TECHNICAL_SOURCE,
                lambda: build_investing_technical_sample_signal(
                    conn,
                    technical_path=technical_path,
                    signal_date=run_date,
                    collected_at=collected_at,
                ),
            ),
            (
                INVESTING_FINANCIAL_SOURCE,
                lambda: build_investing_financial_sample_signal(
                    conn,
                    financial_path=financial_path,
                    signal_date=run_date,
                    collected_at=collected_at,
                ),
            ),
        ):
            attempted += 1
            run_id = create_collection_run(
                conn,
                run_date=run_date,
                source=source,
                started_at=collected_at,
            )
            try:
                signal = build_signal()
                upsert_signal(conn, signal.as_db_row())
                succeeded += 1
                stored += 1
                source_succeeded = 1
                source_failed = 0
            except Exception:
                failed += 1
                source_succeeded = 0
                source_failed = 1

            finish_collection_run(
                conn,
                run_id=run_id,
                attempted=1,
                succeeded=source_succeeded,
                failed=source_failed,
                finished_at=utc_now_iso(),
            )

    return {
        "attempted": attempted,
        "succeeded": succeeded,
        "failed": failed,
        "stored": stored,
    }


def build_investing_technical_sample_signal(
    conn: sqlite3.Connection,
    *,
    technical_path: str | Path,
    signal_date: str,
    collected_at: str,
) -> InvestingStoredSignal:
    parsed = parse_investing_technical_file(technical_path)
    ticker = _required_ticker(parsed.ticker, technical_path)
    return InvestingStoredSignal(
        date=signal_date,
        ticker=ticker,
        source=INVESTING_TECHNICAL_SOURCE,
        category=INVESTING_TECHNICAL_CATEGORY,
        raw_signal=parsed.raw_signal,
        normalized_signal=parsed.normalized_signal,
        score=parsed.score,
        price_at_signal=_price_at_signal(conn, ticker, signal_date),
        metadata_json=_technical_metadata(parsed),
        collected_at=collected_at,
    )


def build_investing_technical_signal_from_html(
    conn: sqlite3.Connection,
    *,
    ticker: str,
    html_text: str,
    signal_date: str,
    collected_at: str,
) -> InvestingStoredSignal:
    parsed = parse_investing_technical_html(html_text)
    parsed_ticker = _required_ticker(parsed.ticker, f"{ticker} technical HTML")
    if parsed_ticker != ticker.upper():
        raise InvestingParseError(
            f"Fetched technical HTML ticker mismatch: expected {ticker}, got {parsed_ticker}"
        )
    return InvestingStoredSignal(
        date=signal_date,
        ticker=parsed_ticker,
        source=INVESTING_TECHNICAL_SOURCE,
        category=INVESTING_TECHNICAL_CATEGORY,
        raw_signal=parsed.raw_signal,
        normalized_signal=parsed.normalized_signal,
        score=parsed.score,
        price_at_signal=_price_at_signal(conn, parsed_ticker, signal_date),
        metadata_json=_technical_metadata(parsed),
        collected_at=collected_at,
    )


def build_investing_financial_sample_signal(
    conn: sqlite3.Connection,
    *,
    financial_path: str | Path,
    signal_date: str,
    collected_at: str,
) -> InvestingStoredSignal:
    inspection = inspect_investing_financial_summary_file(financial_path)
    ticker = _required_ticker(inspection.ticker, financial_path)
    raw_signal = inspection.analyst_consensus_signal
    if raw_signal is None or inspection.analyst_consensus_score is None:
        raise InvestingParseError("Investing analyst consensus signal was not found")
    return InvestingStoredSignal(
        date=signal_date,
        ticker=ticker,
        source=INVESTING_FINANCIAL_SOURCE,
        category=INVESTING_FINANCIAL_CATEGORY,
        raw_signal=raw_signal,
        normalized_signal=raw_signal,
        score=inspection.analyst_consensus_score,
        price_at_signal=_price_at_signal(conn, ticker, signal_date),
        metadata_json=_financial_metadata(inspection),
        collected_at=collected_at,
    )


def build_investing_financial_signal_from_html(
    conn: sqlite3.Connection,
    *,
    ticker: str,
    html_text: str,
    signal_date: str,
    collected_at: str,
) -> InvestingStoredSignal:
    inspection = inspect_investing_financial_summary_html(html_text)
    parsed_ticker = _required_ticker(inspection.ticker, f"{ticker} financial HTML")
    if parsed_ticker != ticker.upper():
        raise InvestingParseError(
            f"Fetched financial HTML ticker mismatch: expected {ticker}, got {parsed_ticker}"
        )
    raw_signal = inspection.analyst_consensus_signal
    if raw_signal is None or inspection.analyst_consensus_score is None:
        raise InvestingParseError("Investing analyst consensus signal was not found")
    return InvestingStoredSignal(
        date=signal_date,
        ticker=parsed_ticker,
        source=INVESTING_FINANCIAL_SOURCE,
        category=INVESTING_FINANCIAL_CATEGORY,
        raw_signal=raw_signal,
        normalized_signal=raw_signal,
        score=inspection.analyst_consensus_score,
        price_at_signal=_price_at_signal(conn, parsed_ticker, signal_date),
        metadata_json=_financial_metadata(inspection),
        collected_at=collected_at,
    )


def parse_investing_technical_html(html_text: str) -> InvestingTechnicalSignal:
    state = _extract_next_state(html_text)
    technical_store = state.get("technicalStore", {})
    if not isinstance(technical_store, dict):
        technical_store = {}

    technical_data = _dict_or_empty(technical_store.get("technicalData"))
    selected_signal = _signal_label(technical_data.get("summary"))
    tokens: list[str] | None = None
    if selected_signal is None:
        tokens = _visible_text_tokens(html_text)
        selected_signal = _selected_technical_summary_from_tokens(tokens)
    indicators_summary = _dict_or_empty(
        _dict_or_empty(technical_data.get("indicators")).get("summary")
    )
    moving_summary = _dict_or_empty(
        _dict_or_empty(technical_data.get("movingAverages")).get("summary")
    )
    daily_data = _dict_or_empty(technical_store.get("technicalDaily"))
    if not daily_data:
        daily_data = _dict_or_empty(
            _dict_or_empty(technical_store.get("analysisDetails")).get("1d")
        )

    daily_signal = _signal_label(daily_data.get("summary"))
    if daily_signal is None:
        if tokens is None:
            tokens = _visible_text_tokens(html_text)
        daily_signal = _value_after(tokens, "Daily")
    if daily_signal is None:
        raise InvestingParseError("Investing daily technical signal was not found")

    selected_timeframe = _optional_str(technical_data.get("timeframe")) or _optional_str(
        technical_store.get("timeframe")
    )
    timeframe_signals = _extract_timeframe_signals(technical_store)
    timeframe_signals.setdefault("Daily", daily_signal)
    if selected_signal is not None and selected_timeframe:
        timeframe_signals.setdefault(
            _display_timeframe_label(selected_timeframe),
            selected_signal,
        )

    normalized = normalize_investing_signal(daily_signal)
    selected_normalized = (
        normalize_investing_signal(selected_signal) if selected_signal is not None else None
    )

    return InvestingTechnicalSignal(
        ticker=_extract_ticker(html_text),
        timeframe=selected_timeframe,
        raw_signal=daily_signal,
        normalized_signal=normalized.normalized_signal,
        score=normalized.score,
        last_update_time=_optional_str(technical_data.get("lastUpdateTime")),
        moving_average_signal=_signal_label(moving_summary.get("value")),
        moving_average_counts=_summary_counts(moving_summary),
        technical_indicator_signal=_signal_label(indicators_summary.get("value")),
        technical_indicator_counts=_summary_counts(indicators_summary),
        selected_signal=selected_signal,
        selected_normalized_signal=(
            selected_normalized.normalized_signal if selected_normalized else None
        ),
        selected_score=selected_normalized.score if selected_normalized else None,
        daily_signal=daily_signal,
        daily_last_update_time=_optional_str(daily_data.get("lastUpdateTime")),
        timeframe_signals=timeframe_signals,
    )


def inspect_investing_financial_summary_file(
    path: str | Path,
) -> InvestingFinancialSummaryInspection:
    html_text = Path(path).read_text(encoding="utf-8", errors="ignore")
    return inspect_investing_financial_summary_html(html_text)


def inspect_investing_financial_summary_html(
    html_text: str,
) -> InvestingFinancialSummaryInspection:
    tokens = _visible_text_tokens(html_text)
    key_ratios_start = _find_section_start(
        tokens,
        "Key Ratios",
        required_markers=("P/E Ratio", "Price/Book"),
    )
    analyst_start = _find_section_start(
        tokens,
        "Analyst Ratings",
        required_markers=("Overall Consensus", "Analysts 12-Month Price Target:"),
    )

    financial_fields: dict[str, str] = {}
    valuation_fields: dict[str, str] = {}
    if key_ratios_start is not None:
        financial_fields = _extract_key_ratios(tokens, key_ratios_start)
        valuation_fields = _extract_valuation_fields(tokens, key_ratios_start)

    analyst_fields: dict[str, str] = {}
    if analyst_start is not None:
        analyst_fields = _extract_analyst_fields(tokens, analyst_start)
    vote_counts = _analyst_vote_counts(analyst_fields)
    total_count = _analyst_total_count(analyst_fields, vote_counts)
    score_raw = _analyst_score_raw(vote_counts, total_count)
    consensus_signal, consensus_score = _score_to_analyst_label(score_raw)

    return InvestingFinancialSummaryInspection(
        ticker=_extract_ticker(html_text),
        analyst_fields=analyst_fields,
        financial_fields=financial_fields,
        valuation_fields=valuation_fields,
        analyst_vote_counts=vote_counts,
        analyst_total_count=total_count,
        analyst_score_raw=score_raw,
        analyst_consensus_signal=consensus_signal,
        analyst_consensus_score=consensus_score,
    )


def fetch_investing_live_html(
    *,
    ticker: str,
    page_kind: str,
    timeout_seconds: float = DEFAULT_FETCH_TIMEOUT_SECONDS,
    retries: int = DEFAULT_FETCH_RETRIES,
    sleep_seconds: float = DEFAULT_FETCH_SLEEP_SECONDS,
    user_agent: str = DEFAULT_USER_AGENT,
) -> str:
    normalized_ticker = _validate_live_ticker(ticker)
    url = _live_url_for(normalized_ticker, page_kind)
    headers = {
        "User-Agent": user_agent,
        "Accept": (
            "text/html,application/xhtml+xml,application/xml;q=0.9,"
            "image/avif,image/webp,*/*;q=0.8"
        ),
        "Accept-Language": "en-US,en;q=0.9",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
    }

    last_error: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            request = Request(url, headers=headers)
            with urlopen(request, timeout=timeout_seconds) as response:
                status = getattr(response, "status", None)
                if status and int(status) >= 400:
                    raise InvestingFetchError(
                        f"HTTP {status} while fetching {page_kind} page for {normalized_ticker}"
                    )
                payload = response.read()
            html_text = payload.decode("utf-8", errors="ignore")
            if "<html" not in html_text.lower():
                raise InvestingFetchError(
                    f"Unexpected response while fetching {page_kind} page for {normalized_ticker}"
                )
            return html_text
        except (HTTPError, URLError, TimeoutError, InvestingFetchError) as exc:
            last_error = exc
            logger.warning(
                "Investing live fetch attempt %s/%s failed for %s %s page: %s",
                attempt,
                retries,
                normalized_ticker,
                page_kind,
                exc,
            )
            if attempt < retries:
                time.sleep(sleep_seconds)

    raise InvestingFetchError(
        f"Failed to fetch Investing {page_kind} page for {normalized_ticker}"
    ) from last_error


def save_investing_live_html(
    html_text: str,
    *,
    ticker: str,
    page_kind: str,
    cache_dir: str | Path = DEFAULT_INVESTING_LIVE_CACHE_DIR,
) -> Path:
    normalized_ticker = _validate_live_ticker(ticker)
    cache_path = Path(cache_dir)
    cache_path.mkdir(parents=True, exist_ok=True)
    if page_kind == "technical":
        filename = LIVE_TECHNICAL_CACHE_FILENAME
    elif page_kind == "financial":
        filename = LIVE_FINANCIAL_CACHE_FILENAME
    else:
        raise ValueError(f"Unknown Investing page kind: {page_kind}")
    output_path = cache_path / filename
    output_path.write_text(html_text, encoding="utf-8")
    return output_path


def _extract_next_state(html_text: str) -> dict[str, Any]:
    match = _NEXT_DATA_RE.search(html_text)
    if match is None:
        return {}
    try:
        next_data = json.loads(html.unescape(match.group(1)))
    except json.JSONDecodeError as exc:
        raise InvestingParseError("Investing __NEXT_DATA__ JSON is invalid") from exc

    state = (
        next_data.get("props", {})
        .get("pageProps", {})
        .get("state", {})
    )
    return state if isinstance(state, dict) else {}


def _extract_key_ratios(tokens: list[str], start: int) -> dict[str, str]:
    fields = {
        "pe_ratio": "P/E Ratio",
        "price_book": "Price/Book",
        "debt_equity": "Debt / Equity",
        "return_on_equity": "Return on Equity",
        "dividend_yield": "Dividend Yield",
        "ebitda": "EBITDA",
    }
    end = _find_index(tokens, "Statements Highlights", start=start)
    return _extract_labeled_values(tokens, fields, start=start, end=end)


def _extract_valuation_fields(tokens: list[str], start: int) -> dict[str, str]:
    fields = {
        "fair_value": "Fair Value",
        "fair_value_upside": "Fair Value Upside",
    }
    end = _find_index(tokens, "Statements Highlights", start=start)
    return _extract_labeled_values(tokens, fields, start=start, end=end)


def _extract_analyst_fields(tokens: list[str], start: int) -> dict[str, str]:
    end = _find_index(tokens, "Earnings", start=start)
    fields = _extract_labeled_values(
        tokens,
        {
            "ratings_total": "Ratings:",
            "overall_consensus": "Overall Consensus",
        },
        start=start,
        end=end,
    )

    average_index = _find_index(tokens, "Average", start=start, end=end)
    if average_index is not None and average_index + 1 < len(tokens):
        fields["price_target_average"] = tokens[average_index + 1]
        if average_index + 2 < len(tokens) and "Upside" in tokens[average_index + 2]:
            fields["price_target_upside"] = tokens[average_index + 2]

    section = tokens[start : end or min(len(tokens), start + 80)]
    for token in section:
        match = re.fullmatch(r"(\d+)\s+(Strong Buy|Buy|Hold|Sell|Strong Sell)", token)
        if match:
            key = match.group(2).lower().replace(" ", "_") + "_ratings"
            fields[key] = token

    return fields


def _extract_labeled_values(
    tokens: list[str],
    labels: dict[str, str],
    *,
    start: int = 0,
    end: int | None = None,
) -> dict[str, str]:
    values: dict[str, str] = {}
    for key, label in labels.items():
        value = _value_after(tokens, label, start=start, end=end)
        if value is not None:
            values[key] = value
    return values


def _visible_text_tokens(html_text: str) -> list[str]:
    parser = _VisibleTextParser()
    parser.feed(html_text)
    return parser.tokens


def _selected_technical_summary_from_tokens(tokens: list[str]) -> str | None:
    summary_index = _find_index(tokens, "Summary:")
    if summary_index is None:
        return None
    return _signal_label(_value_at(tokens, summary_index + 1))


def _find_section_start(
    tokens: list[str],
    marker: str,
    *,
    required_markers: tuple[str, ...],
    window: int = 80,
) -> int | None:
    start = 0
    while True:
        index = _find_index(tokens, marker, start=start)
        if index is None:
            return None
        section = tokens[index : min(len(tokens), index + window)]
        if all(any(_same_token(token, required) for token in section) for required in required_markers):
            return index
        start = index + 1


def _find_index(
    tokens: list[str],
    label: str,
    *,
    start: int = 0,
    end: int | None = None,
) -> int | None:
    stop = len(tokens) if end is None else min(end, len(tokens))
    for index in range(start, stop):
        if _same_token(tokens[index], label):
            return index
    return None


def _value_after(
    tokens: list[str],
    label: str,
    *,
    start: int = 0,
    end: int | None = None,
) -> str | None:
    index = _find_index(tokens, label, start=start, end=end)
    if index is None:
        return None
    return _value_at(tokens, index + 1, end=end)


def _value_at(tokens: list[str], index: int, *, end: int | None = None) -> str | None:
    if index < 0 or index >= len(tokens):
        return None
    if end is not None and index >= end:
        return None
    value = tokens[index].strip()
    return value or None


def _signal_label(value: Any) -> str | None:
    if value is None:
        return None
    canonical = re.sub(r"[^a-z]+", " ", str(value).strip().lower())
    canonical = re.sub(r"\s+", " ", canonical).strip()
    for key, label in (
        ("strong sell", "Strong Sell"),
        ("strong buy", "Strong Buy"),
        ("neutral", "Neutral"),
        ("sell", "Sell"),
        ("buy", "Buy"),
    ):
        if key in canonical:
            return label
    return None


def _summary_counts(summary: dict[str, Any]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for key in ("buy", "neutral", "sell"):
        if key not in summary:
            continue
        try:
            counts[key] = int(summary[key])
        except (TypeError, ValueError):
            continue
    return counts


def _extract_timeframe_signals(technical_store: dict[str, Any]) -> dict[str, str]:
    timeframe_signals: dict[str, str] = {}
    details = _dict_or_empty(technical_store.get("analysisDetails"))
    for key, label in (
        ("30m", "30 Min"),
        ("1h", "Hourly"),
        ("5h", "5 Hours"),
        ("1d", "Daily"),
        ("1w", "Weekly"),
        ("1m", "Monthly"),
    ):
        summary = _signal_label(_dict_or_empty(details.get(key)).get("summary"))
        if summary is not None:
            timeframe_signals[label] = summary
    return timeframe_signals


def _display_timeframe_label(value: str) -> str:
    return {
        "30m": "30 Min",
        "1h": "Hourly",
        "5h": "5 Hours",
        "1d": "Daily",
        "1w": "Weekly",
        "1m": "Monthly",
    }.get(value, value)


def _sample_signal_date(technical_path: Path) -> str:
    try:
        technical = parse_investing_technical_file(technical_path)
    except Exception:
        return date.today().isoformat()
    if technical.daily_last_update_time:
        return technical.daily_last_update_time[:10]
    if technical.last_update_time:
        return technical.last_update_time[:10]
    return date.today().isoformat()


def _live_signal_date_from_html(html_text: str) -> str | None:
    technical = parse_investing_technical_html(html_text)
    if technical.daily_last_update_time:
        return technical.daily_last_update_time[:10]
    if technical.last_update_time:
        return technical.last_update_time[:10]
    return None


def _required_ticker(ticker: str | None, source_path: str | Path) -> str:
    if ticker is None or str(ticker).strip() == "":
        raise InvestingParseError(f"Ticker was not found in {source_path}")
    return str(ticker).upper()


def _validate_live_ticker(ticker: str) -> str:
    normalized_ticker = str(ticker).strip().upper()
    if normalized_ticker != LIVE_SUPPORTED_TICKER:
        raise InvestingFetchError(
            f"Live Investing fetch currently supports only {LIVE_SUPPORTED_TICKER}"
        )
    return normalized_ticker


def _live_url_for(ticker: str, page_kind: str) -> str:
    if page_kind == "technical":
        try:
            return INVESTING_TECHNICAL_URL_BY_TICKER[ticker]
        except KeyError as exc:
            raise InvestingFetchError(
                f"No Investing technical URL is configured for {ticker}"
            ) from exc
    if page_kind == "financial":
        try:
            return INVESTING_FINANCIAL_URL_BY_TICKER[ticker]
        except KeyError as exc:
            raise InvestingFetchError(
                f"No Investing financial URL is configured for {ticker}"
            ) from exc
    raise InvestingFetchError(f"Unknown Investing page kind: {page_kind}")


def _price_at_signal(
    conn: sqlite3.Connection,
    ticker: str,
    signal_date: str,
) -> float | None:
    row = conn.execute(
        """
        SELECT adjusted_close
        FROM prices
        WHERE ticker = ? AND date = ?
        """,
        (ticker.upper(), signal_date),
    ).fetchone()
    if row is None:
        return None
    return float(row["adjusted_close"])


def _dict_or_empty(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _extract_ticker(html_text: str) -> str | None:
    title_match = re.search(r"<title[^>]*>(.*?)</title>", html_text, re.IGNORECASE | re.DOTALL)
    if title_match is None:
        return None
    title = _clean_text(html.unescape(title_match.group(1)))
    ticker_match = re.search(r"\b(?:NASDAQ:)?([A-Z]{1,6})(?=\s|:)", title)
    if ticker_match:
        return ticker_match.group(1)
    return None


def _same_token(left: str, right: str) -> bool:
    return _clean_text(left).casefold() == _clean_text(right).casefold()


def _clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(str(value))).strip()


def _is_unlocked_value(value: str) -> bool:
    return _clean_text(value).casefold() not in _LOCKED_VALUES


def _parse_int_prefix(value: str | None) -> int | None:
    if value is None:
        return None
    match = re.match(r"(\d+)", _clean_text(value))
    if match is None:
        return None
    return int(match.group(1))


def _analyst_vote_counts(fields: dict[str, str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for label in ("buy", "hold", "sell"):
        count = _parse_int_prefix(fields.get(f"{label}_ratings"))
        if count is not None:
            counts[label] = count
    return counts


def _analyst_total_count(
    fields: dict[str, str],
    vote_counts: dict[str, int],
) -> int | None:
    total_from_votes = sum(vote_counts.values())
    if total_from_votes > 0:
        return total_from_votes
    return _parse_int_prefix(fields.get("ratings_total"))


def _analyst_score_raw(
    vote_counts: dict[str, int],
    total_count: int | None,
) -> float | None:
    if total_count is None or total_count <= 0:
        return None
    return (vote_counts.get("buy", 0) - vote_counts.get("sell", 0)) / total_count


def _score_to_analyst_label(score_raw: float | None) -> tuple[str | None, int | None]:
    if score_raw is None:
        return None, None
    if score_raw >= 0.60:
        return "Strong Buy", 2
    if score_raw >= 0.20:
        return "Buy", 1
    if score_raw > -0.20:
        return "Hold", 0
    if score_raw > -0.60:
        return "Sell", -1
    return "Strong Sell", -2


def _technical_metadata(signal: InvestingTechnicalSignal) -> dict[str, Any]:
    return {
        "selected_timeframe": signal.timeframe,
        "selected_signal": signal.selected_signal,
        "selected_normalized_signal": signal.selected_normalized_signal,
        "selected_score": signal.selected_score,
        "daily_signal": signal.daily_signal,
        "daily_last_update_time": signal.daily_last_update_time,
        "timeframe_signals": signal.timeframe_signals,
        "moving_average_signal": signal.moving_average_signal,
        "moving_average_counts": signal.moving_average_counts,
        "technical_indicator_signal": signal.technical_indicator_signal,
        "technical_indicator_counts": signal.technical_indicator_counts,
    }


def _financial_metadata(
    inspection: InvestingFinancialSummaryInspection,
) -> dict[str, Any]:
    return {
        "analyst_fields": inspection.analyst_fields,
        "financial_fields": inspection.financial_fields,
        "valuation_fields": inspection.valuation_fields,
        "analyst_vote_counts": inspection.analyst_vote_counts,
        "analyst_total_count": inspection.analyst_total_count,
        "analyst_score_raw": inspection.analyst_score_raw,
    }
