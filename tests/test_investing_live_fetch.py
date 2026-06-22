from __future__ import annotations

from pathlib import Path

from src.collectors.investing import (
    InvestingFetchError,
    LIVE_FINANCIAL_CACHE_FILENAME,
    LIVE_TECHNICAL_CACHE_FILENAME,
    collect_investing_live_signals,
    fetch_investing_live_html,
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


def test_fetch_investing_live_html_uses_urlopen(monkeypatch):
    html_text = TECHNICAL_SAMPLE.read_text(encoding="utf-8", errors="ignore")

    def fake_urlopen(request, timeout):
        assert timeout == 7
        assert request.headers["User-agent"]
        return _FakeResponse(html_text.encode("utf-8"))

    monkeypatch.setattr("src.collectors.investing.urlopen", fake_urlopen)

    result = fetch_investing_live_html(
        ticker="AAPL",
        page_kind="technical",
        timeout_seconds=7,
        retries=1,
    )

    assert "AAPL Technical Analysis" in result


def test_collect_investing_live_signals_saves_cache_and_stores_rows(tmp_path, monkeypatch):
    db_path = tmp_path / "signal_league.sqlite"
    cache_dir = tmp_path / "live-cache"
    initialize_database(db_path)

    technical_html = TECHNICAL_SAMPLE.read_text(encoding="utf-8", errors="ignore")
    financial_html = FINANCIAL_SAMPLE.read_text(encoding="utf-8", errors="ignore")

    def fake_fetch(*, page_kind, **_kwargs):
        if page_kind == "technical":
            return technical_html
        if page_kind == "financial":
            return financial_html
        raise AssertionError(f"unexpected page kind: {page_kind}")

    monkeypatch.setattr("src.collectors.investing.fetch_investing_live_html", fake_fetch)

    with connect(db_path) as conn:
        sync_universe(conn)
        seed_mock_prices(conn, periods=260)
        result = collect_investing_live_signals(
            conn,
            ticker="AAPL",
            cache_dir=cache_dir,
        )
        rows = conn.execute(
            """
            SELECT source, category, raw_signal, normalized_signal, score
            FROM signals
            ORDER BY source
            """
        ).fetchall()

    assert result == {"attempted": 2, "succeeded": 2, "failed": 0, "stored": 2}
    assert [row["source"] for row in rows] == [
        "Investing.com Financial / Analyst Summary",
        "Investing.com Technical Analysis",
    ]
    assert (cache_dir / LIVE_TECHNICAL_CACHE_FILENAME).exists()
    assert (cache_dir / LIVE_FINANCIAL_CACHE_FILENAME).exists()


def test_collect_investing_live_signals_fails_gracefully_when_blocked(tmp_path, monkeypatch):
    db_path = tmp_path / "signal_league.sqlite"
    initialize_database(db_path)

    def fake_fetch(**_kwargs):
        raise InvestingFetchError("blocked by remote site")

    monkeypatch.setattr("src.collectors.investing.fetch_investing_live_html", fake_fetch)

    with connect(db_path) as conn:
        sync_universe(conn)
        seed_mock_prices(conn, periods=260)
        result = collect_investing_live_signals(conn, ticker="AAPL")
        signal_count = conn.execute("SELECT COUNT(*) FROM signals").fetchone()[0]
        runs = conn.execute(
            "SELECT source, attempted, succeeded, failed FROM collection_runs ORDER BY source"
        ).fetchall()

    assert result == {"attempted": 2, "succeeded": 0, "failed": 2, "stored": 0}
    assert signal_count == 0
    assert len(runs) == 2
    assert all(run["attempted"] == 1 for run in runs)
    assert all(run["succeeded"] == 0 for run in runs)
    assert all(run["failed"] == 1 for run in runs)
