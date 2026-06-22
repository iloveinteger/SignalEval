from __future__ import annotations

import re
from pathlib import Path

from src.collectors.investing import (
    InvestingFetchError,
    LIVE_FINANCIAL_CACHE_FILENAME,
    LIVE_TECHNICAL_CACHE_FILENAME,
    collect_investing_browser_signals,
    collect_investing_live_signals,
    fetch_investing_live_html,
    load_investing_slug_map,
)
from src.prices.mock_prices import seed_mock_prices
from src.utils.db import connect, initialize_database
from src.utils.universe import sync_universe

SAMPLES_DIR = Path(__file__).resolve().parents[1] / "samples" / "investing"
TECHNICAL_SAMPLE = (
    SAMPLES_DIR
    / "AAPL Technical Analysis, RSI and Moving Averages - Investing.com.html"
)
FINANCIAL_SAMPLE = (
    SAMPLES_DIR
    / "NASDAQ_AAPL Financials _ Apple - Investing.com.html"
)


class _FakeResponse:
    def __init__(self, payload: bytes, status: int = 200):
        self._payload = payload
        self.status = status

    def read(self) -> bytes:
        return self._payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


def test_load_investing_slug_map_parses_config(tmp_path):
    csv_path = tmp_path / "investing_slugs.csv"
    csv_path.write_text(
        "\n".join(
            [
                "ticker,technical_url,financial_url",
                "aapl,https://example.com/aapl-technical,https://example.com/aapl-financial",
                "msft,https://example.com/msft-technical,https://example.com/msft-financial",
            ]
        ),
        encoding="utf-8",
    )

    slug_map = load_investing_slug_map(csv_path)

    assert slug_map == {
        "AAPL": {
            "technical": "https://example.com/aapl-technical",
            "financial": "https://example.com/aapl-financial",
        },
        "MSFT": {
            "technical": "https://example.com/msft-technical",
            "financial": "https://example.com/msft-financial",
        },
    }


def test_fetch_investing_live_html_uses_urlopen_and_slug_config(tmp_path, monkeypatch):
    slug_path = _write_slug_config(tmp_path, ["AAPL"])
    html_text = TECHNICAL_SAMPLE.read_text(encoding="utf-8", errors="ignore")

    def fake_urlopen(request, timeout):
        assert timeout == 7
        assert request.full_url == "https://example.com/aapl-technical"
        assert request.headers["User-agent"]
        return _FakeResponse(html_text.encode("utf-8"))

    monkeypatch.setattr("src.collectors.investing.urlopen", fake_urlopen)

    result = fetch_investing_live_html(
        ticker="AAPL",
        page_kind="technical",
        slugs_path=slug_path,
        timeout_seconds=7,
        retries=1,
        sleep_seconds=0,
    )

    assert "AAPL Technical Analysis" in result


def test_collect_investing_live_signals_saves_cache_and_stores_rows_for_multiple_tickers(
    tmp_path,
    monkeypatch,
):
    db_path = tmp_path / "signal_league.sqlite"
    cache_dir = tmp_path / "live-cache"
    slug_path = _write_slug_config(tmp_path, ["AAPL", "MSFT"])
    initialize_database(db_path)

    technical_html_by_ticker = {
        "AAPL": TECHNICAL_SAMPLE.read_text(encoding="utf-8", errors="ignore"),
        "MSFT": _retitle_html(
            TECHNICAL_SAMPLE.read_text(encoding="utf-8", errors="ignore"),
            new_title="MSFT Technical Analysis, RSI and Moving Averages - Investing.com",
        ),
    }
    financial_html_by_ticker = {
        "AAPL": FINANCIAL_SAMPLE.read_text(encoding="utf-8", errors="ignore"),
        "MSFT": _retitle_html(
            FINANCIAL_SAMPLE.read_text(encoding="utf-8", errors="ignore"),
            new_title="NASDAQ:MSFT Financials _ Microsoft - Investing.com",
        ),
    }

    def fake_fetch(*, ticker, page_kind, **_kwargs):
        if page_kind == "technical":
            return technical_html_by_ticker[ticker]
        if page_kind == "financial":
            return financial_html_by_ticker[ticker]
        raise AssertionError(f"unexpected page kind: {page_kind}")

    monkeypatch.setattr("src.collectors.investing.fetch_investing_live_html", fake_fetch)

    with connect(db_path) as conn:
        sync_universe(conn)
        seed_mock_prices(conn, periods=260)
        result = collect_investing_live_signals(
            conn,
            tickers=["AAPL", "MSFT"],
            slugs_path=slug_path,
            cache_dir=cache_dir,
            sleep_seconds=0,
        )
        rows = conn.execute(
            """
            SELECT ticker, source, category, raw_signal, normalized_signal, score, success
            FROM signals
            ORDER BY ticker, source
            """
        ).fetchall()

    assert result == {"attempted": 4, "succeeded": 4, "failed": 0, "stored": 4}
    assert [row["ticker"] for row in rows] == ["AAPL", "AAPL", "MSFT", "MSFT"]
    assert all(row["success"] == 1 for row in rows)
    assert (cache_dir / "AAPL" / LIVE_TECHNICAL_CACHE_FILENAME).exists()
    assert (cache_dir / "AAPL" / LIVE_FINANCIAL_CACHE_FILENAME).exists()
    assert (cache_dir / "MSFT" / LIVE_TECHNICAL_CACHE_FILENAME).exists()
    assert (cache_dir / "MSFT" / LIVE_FINANCIAL_CACHE_FILENAME).exists()


def test_collect_investing_live_signals_stores_failure_rows_when_blocked(tmp_path, monkeypatch):
    db_path = tmp_path / "signal_league.sqlite"
    slug_path = _write_slug_config(tmp_path, ["AAPL"])
    initialize_database(db_path)

    def fake_fetch(**_kwargs):
        raise InvestingFetchError("blocked by remote site")

    monkeypatch.setattr("src.collectors.investing.fetch_investing_live_html", fake_fetch)

    with connect(db_path) as conn:
        sync_universe(conn)
        seed_mock_prices(conn, periods=260)
        result = collect_investing_live_signals(
            conn,
            tickers=["AAPL"],
            slugs_path=slug_path,
            sleep_seconds=0,
        )
        rows = conn.execute(
            """
            SELECT ticker, source, success, error_message
            FROM signals
            ORDER BY source
            """
        ).fetchall()
        runs = conn.execute(
            "SELECT source, attempted, succeeded, failed FROM collection_runs ORDER BY source"
        ).fetchall()

    assert result == {"attempted": 2, "succeeded": 0, "failed": 2, "stored": 0}
    assert len(rows) == 2
    assert all(row["ticker"] == "AAPL" for row in rows)
    assert all(row["success"] == 0 for row in rows)
    assert all("blocked by remote site" in row["error_message"] for row in rows)
    assert len(runs) == 2
    assert all(run["attempted"] == 1 for run in runs)
    assert all(run["succeeded"] == 0 for run in runs)
    assert all(run["failed"] == 1 for run in runs)


def test_collect_investing_browser_signals_saves_cache_and_honors_limit(tmp_path):
    db_path = tmp_path / "signal_league.sqlite"
    cache_dir = tmp_path / "live-cache"
    slug_path = _write_slug_config(tmp_path, ["AAPL", "MSFT"])
    initialize_database(db_path)

    technical_html_by_ticker = {
        "AAPL": TECHNICAL_SAMPLE.read_text(encoding="utf-8", errors="ignore"),
        "MSFT": _retitle_html(
            TECHNICAL_SAMPLE.read_text(encoding="utf-8", errors="ignore"),
            new_title="MSFT Technical Analysis, RSI and Moving Averages - Investing.com",
        ),
    }
    financial_html_by_ticker = {
        "AAPL": FINANCIAL_SAMPLE.read_text(encoding="utf-8", errors="ignore"),
        "MSFT": _retitle_html(
            FINANCIAL_SAMPLE.read_text(encoding="utf-8", errors="ignore"),
            new_title="NASDAQ:MSFT Financials _ Microsoft - Investing.com",
        ),
    }

    def fake_browser_fetch(*, ticker, page_kind):
        if page_kind == "technical":
            return technical_html_by_ticker[ticker]
        if page_kind == "financial":
            return financial_html_by_ticker[ticker]
        raise AssertionError(f"unexpected page kind: {page_kind}")

    with connect(db_path) as conn:
        sync_universe(conn)
        seed_mock_prices(conn, periods=260)
        result = collect_investing_browser_signals(
            conn,
            slugs_path=slug_path,
            cache_dir=cache_dir,
            limit=1,
            sleep_seconds=0,
            fetch_html=fake_browser_fetch,
        )
        rows = conn.execute(
            """
            SELECT ticker, source, success
            FROM signals
            ORDER BY ticker, source
            """
        ).fetchall()

    assert result == {"attempted": 2, "succeeded": 2, "failed": 0, "stored": 2}
    assert [row["ticker"] for row in rows] == ["AAPL", "AAPL"]
    assert all(row["success"] == 1 for row in rows)
    assert (cache_dir / "AAPL" / LIVE_TECHNICAL_CACHE_FILENAME).exists()
    assert (cache_dir / "AAPL" / LIVE_FINANCIAL_CACHE_FILENAME).exists()
    assert not (cache_dir / "MSFT").exists()


def test_collect_investing_browser_signals_stores_failure_rows(tmp_path):
    db_path = tmp_path / "signal_league.sqlite"
    slug_path = _write_slug_config(tmp_path, ["AAPL"])
    initialize_database(db_path)

    def fake_browser_fetch(**_kwargs):
        raise InvestingFetchError("browser blocked by remote site")

    with connect(db_path) as conn:
        sync_universe(conn)
        seed_mock_prices(conn, periods=260)
        result = collect_investing_browser_signals(
            conn,
            tickers=["AAPL"],
            slugs_path=slug_path,
            sleep_seconds=0,
            fetch_html=fake_browser_fetch,
        )
        rows = conn.execute(
            """
            SELECT ticker, source, success, error_message
            FROM signals
            ORDER BY source
            """
        ).fetchall()

    assert result == {"attempted": 2, "succeeded": 0, "failed": 2, "stored": 0}
    assert len(rows) == 2
    assert all(row["ticker"] == "AAPL" for row in rows)
    assert all(row["success"] == 0 for row in rows)
    assert all("browser blocked by remote site" in row["error_message"] for row in rows)


def test_collect_investing_browser_signals_detects_cloudflare_challenge_page(tmp_path):
    db_path = tmp_path / "signal_league.sqlite"
    cache_dir = tmp_path / "live-cache"
    slug_path = _write_slug_config(tmp_path, ["AAPL"])
    initialize_database(db_path)
    challenge_html = (
        "<html><head><title>Just a moment...</title></head>"
        "<body>Performing security verification for Cloudflare</body></html>"
    )

    def fake_browser_fetch(*, ticker, page_kind):
        if page_kind == "technical":
            return TECHNICAL_SAMPLE.read_text(encoding="utf-8", errors="ignore")
        return challenge_html

    with connect(db_path) as conn:
        sync_universe(conn)
        seed_mock_prices(conn, periods=260)
        result = collect_investing_browser_signals(
            conn,
            tickers=["AAPL"],
            slugs_path=slug_path,
            cache_dir=cache_dir,
            sleep_seconds=0,
            fetch_html=fake_browser_fetch,
        )
        rows = conn.execute(
            """
            SELECT source, success, error_message
            FROM signals
            ORDER BY source
            """
        ).fetchall()

    assert result == {"attempted": 2, "succeeded": 1, "failed": 1, "stored": 1}
    rows_by_source = {row["source"]: row for row in rows}
    assert rows_by_source["Investing.com Technical Analysis"]["success"] == 1
    assert rows_by_source["Investing.com Financial / Analyst Summary"]["success"] == 0
    assert (
        "Cloudflare challenge page returned instead of Investing content"
        in rows_by_source["Investing.com Financial / Analyst Summary"]["error_message"]
    )
    assert (cache_dir / "AAPL" / LIVE_FINANCIAL_CACHE_FILENAME).exists()


def _write_slug_config(tmp_path: Path, tickers: list[str]) -> Path:
    lines = ["ticker,technical_url,financial_url"]
    for ticker in tickers:
        lines.append(
            f"{ticker},https://example.com/{ticker.lower()}-technical,https://example.com/{ticker.lower()}-financial"
        )
    csv_path = tmp_path / "investing_slugs.csv"
    csv_path.write_text("\n".join(lines), encoding="utf-8")
    return csv_path


def _retitle_html(html_text: str, *, new_title: str) -> str:
    return re.sub(r"(<title[^>]*>)(.*?)(</title>)", rf"\1{new_title}\3", html_text, count=1)
