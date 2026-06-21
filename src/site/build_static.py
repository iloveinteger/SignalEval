from __future__ import annotations

import html
import json
import sqlite3
from pathlib import Path
from typing import Any

from src.analysis.leaderboard import export_leaderboard_json
from src.utils.db import DEFAULT_DB_PATH, PROJECT_ROOT, connect, create_schema, utc_now_iso

DEFAULT_DOCS_DIR = PROJECT_ROOT / "docs"
DEFAULT_EXPORT_DIR = PROJECT_ROOT / "data" / "exports"
DISCLAIMER = (
    "Signal League is not financial advice. It evaluates historical public "
    "signals. Past performance does not imply future performance."
)


def build_static_site(
    *,
    db_path: str | Path = DEFAULT_DB_PATH,
    docs_dir: str | Path = DEFAULT_DOCS_DIR,
    export_dir: str | Path = DEFAULT_EXPORT_DIR,
) -> dict[str, Path]:
    docs_path = Path(docs_dir)
    exports_path = Path(export_dir)
    docs_path.mkdir(parents=True, exist_ok=True)
    exports_path.mkdir(parents=True, exist_ok=True)

    with connect(db_path) as conn:
        create_schema(conn)
        leaderboard = export_leaderboard_json(
            conn,
            exports_path / "leaderboard.json",
        )
        data_quality = build_data_quality(conn)

    (exports_path / "data_quality.json").write_text(
        json.dumps(data_quality, indent=2) + "\n",
        encoding="utf-8",
    )

    pages = {
        "index": docs_path / "index.html",
        "leaderboard": docs_path / "leaderboard.html",
        "data_quality": docs_path / "data-quality.html",
    }

    pages["index"].write_text(render_home_page(leaderboard), encoding="utf-8")
    pages["leaderboard"].write_text(
        render_leaderboard_page(leaderboard),
        encoding="utf-8",
    )
    pages["data_quality"].write_text(
        render_data_quality_page(data_quality),
        encoding="utf-8",
    )

    return pages


def build_data_quality(conn: sqlite3.Connection) -> dict[str, Any]:
    source_rows = conn.execute(
        """
        SELECT
          source,
          SUM(COALESCE(attempted, 0)) AS attempted,
          SUM(COALESCE(succeeded, 0)) AS succeeded,
          SUM(COALESCE(failed, 0)) AS failed,
          MAX(COALESCE(finished_at, started_at)) AS last_collection_time
        FROM collection_runs
        GROUP BY source
        ORDER BY source
        """
    ).fetchall()

    failed_rows = conn.execute(
        """
        SELECT date, ticker, source, error_message
        FROM signals
        WHERE success = 0
        ORDER BY date DESC, ticker, source
        LIMIT 100
        """
    ).fetchall()

    missing_price_rows = conn.execute(
        """
        SELECT stocks.ticker
        FROM stocks
        LEFT JOIN prices ON prices.ticker = stocks.ticker
        WHERE stocks.active = 1
        GROUP BY stocks.ticker
        HAVING COUNT(prices.date) = 0
        ORDER BY stocks.ticker
        """
    ).fetchall()

    source_runs = []
    for row in source_rows:
        attempted = int(row["attempted"] or 0)
        succeeded = int(row["succeeded"] or 0)
        source_runs.append(
            {
                "source": row["source"],
                "attempted": attempted,
                "succeeded": succeeded,
                "failed": int(row["failed"] or 0),
                "success_rate": succeeded / attempted if attempted else None,
                "last_collection_time": row["last_collection_time"],
            }
        )

    return {
        "generated_at": utc_now_iso(),
        "last_collection_time": _scalar(
            conn,
            "SELECT MAX(COALESCE(finished_at, started_at)) FROM collection_runs",
        ),
        "stocks_count": _scalar(conn, "SELECT COUNT(*) FROM stocks"),
        "active_stocks_count": _scalar(
            conn,
            "SELECT COUNT(*) FROM stocks WHERE active = 1",
        ),
        "signals_collected": _scalar(
            conn,
            "SELECT COUNT(*) FROM signals WHERE success = 1",
        ),
        "failed_signal_count": _scalar(
            conn,
            "SELECT COUNT(*) FROM signals WHERE success = 0",
        ),
        "prices_collected": _scalar(conn, "SELECT COUNT(*) FROM prices"),
        "forward_returns_count": _scalar(conn, "SELECT COUNT(*) FROM forward_returns"),
        "latest_signal_date": _scalar(conn, "SELECT MAX(date) FROM signals"),
        "latest_price_date": _scalar(conn, "SELECT MAX(date) FROM prices"),
        "source_runs": source_runs,
        "missing_tickers": [row["ticker"] for row in missing_price_rows],
        "failed_tickers": [dict(row) for row in failed_rows],
    }


def render_home_page(leaderboard: dict[str, Any]) -> str:
    top_rows = leaderboard.get("top_level", [])[:5]
    body = [
        """
        <section class="hero">
          <div>
            <p class="eyebrow">Signal League</p>
            <h1>Who predicts better: chartists, analysts, or earnings-revision models?</h1>
            <p class="lede">A public scoreboard for historical investment signals across the S&amp;P 500.</p>
          </div>
          <div class="signal-strip" aria-hidden="true">
            <span></span><span></span><span></span><span></span><span></span>
          </div>
        </section>
        """,
        _summary_grid(leaderboard.get("metadata", {})),
        "<section><h2>Latest Leaderboard</h2>",
    ]

    if top_rows:
        body.append(_leaderboard_table(top_rows, compact=True))
        body.append('<p><a class="button" href="leaderboard.html">View full leaderboard</a></p>')
    else:
        body.append(_empty_state("No evaluated signals are available yet."))

    body.append("</section>")
    return _page("Signal League", "\n".join(body), active="home")


def render_leaderboard_page(leaderboard: dict[str, Any]) -> str:
    top_rows = leaderboard.get("top_level", [])
    body = [
        "<section>",
        "<h1>Leaderboard</h1>",
        "<p>Default view is organized around 20D and 60D forward performance when those horizons are available.</p>",
    ]

    if top_rows:
        body.append(_leaderboard_table(top_rows, compact=False))
    else:
        body.append(_empty_state("No leaderboard rows yet. Collect signals, prices, and forward returns first."))

    body.extend(["</section>", _raw_metric_table(leaderboard.get("rows", []))])
    return _page("Leaderboard - Signal League", "\n".join(body), active="leaderboard")


def render_data_quality_page(data_quality: dict[str, Any]) -> str:
    source_runs = data_quality.get("source_runs", [])
    missing_tickers = data_quality.get("missing_tickers", [])
    failed_tickers = data_quality.get("failed_tickers", [])

    body = [
        "<section>",
        "<h1>Data Quality</h1>",
        _quality_grid(data_quality),
        "</section>",
        "<section><h2>Source Success Rate</h2>",
    ]

    if source_runs:
        body.append(_source_runs_table(source_runs))
    else:
        body.append(_empty_state("No collection runs have been recorded yet."))

    body.append("</section><section><h2>Missing Price Tickers</h2>")
    if missing_tickers:
        body.append("<p>" + ", ".join(_escape(ticker) for ticker in missing_tickers) + "</p>")
    else:
        body.append(_empty_state("No active universe tickers are missing all price rows."))

    body.append("</section><section><h2>Failed Signal Rows</h2>")
    if failed_tickers:
        body.append(_failed_tickers_table(failed_tickers))
    else:
        body.append(_empty_state("No failed signal rows are currently stored."))
    body.append("</section>")

    return _page("Data Quality - Signal League", "\n".join(body), active="quality")


def _page(title: str, body: str, *, active: str) -> str:
    nav = [
        ("home", "Home", "index.html"),
        ("leaderboard", "Leaderboard", "leaderboard.html"),
        ("quality", "Data Quality", "data-quality.html"),
    ]
    nav_links = "\n".join(
        f'<a class="{"active" if key == active else ""}" href="{href}">{label}</a>'
        for key, label, href in nav
    )

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{_escape(title)}</title>
  <style>
    :root {{
      color-scheme: light;
      --ink: #17202a;
      --muted: #5d6b78;
      --line: #d9e0e7;
      --panel: #f7f9fb;
      --accent: #0b6bcb;
      --positive: #147d47;
      --negative: #b42318;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      color: var(--ink);
      font: 15px/1.5 Arial, Helvetica, sans-serif;
      background: #ffffff;
    }}
    header {{
      border-bottom: 1px solid var(--line);
      background: #ffffff;
    }}
    .nav {{
      max-width: 1120px;
      margin: 0 auto;
      padding: 14px 20px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 18px;
    }}
    .brand {{
      font-weight: 700;
      letter-spacing: 0;
    }}
    nav {{
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
    }}
    nav a, .button {{
      color: var(--ink);
      text-decoration: none;
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 7px 10px;
      background: #ffffff;
    }}
    nav a.active, .button {{
      border-color: var(--accent);
      color: var(--accent);
    }}
    main {{
      max-width: 1120px;
      margin: 0 auto;
      padding: 28px 20px 40px;
    }}
    section {{
      margin: 0 0 32px;
    }}
    .hero {{
      min-height: 280px;
      display: grid;
      grid-template-columns: minmax(0, 1.4fr) minmax(220px, .6fr);
      gap: 32px;
      align-items: center;
      border-bottom: 1px solid var(--line);
      padding-bottom: 28px;
    }}
    h1 {{
      margin: 0 0 12px;
      max-width: 820px;
      font-size: 42px;
      line-height: 1.08;
      letter-spacing: 0;
    }}
    h2 {{
      margin: 0 0 12px;
      font-size: 22px;
      letter-spacing: 0;
    }}
    p {{ margin: 0 0 14px; }}
    .eyebrow {{
      margin-bottom: 10px;
      color: var(--accent);
      font-weight: 700;
      text-transform: uppercase;
      font-size: 12px;
      letter-spacing: 0;
    }}
    .lede {{
      color: var(--muted);
      font-size: 18px;
      max-width: 680px;
    }}
    .signal-strip {{
      height: 180px;
      display: grid;
      grid-template-columns: repeat(5, 1fr);
      gap: 8px;
      align-items: end;
      padding: 16px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--panel);
    }}
    .signal-strip span {{
      display: block;
      min-height: 28px;
      border-radius: 4px 4px 0 0;
      background: var(--accent);
    }}
    .signal-strip span:nth-child(1) {{ height: 34%; background: #b42318; }}
    .signal-strip span:nth-child(2) {{ height: 52%; background: #d97706; }}
    .signal-strip span:nth-child(3) {{ height: 42%; background: #64748b; }}
    .signal-strip span:nth-child(4) {{ height: 72%; background: #0b6bcb; }}
    .signal-strip span:nth-child(5) {{ height: 88%; background: #147d47; }}
    .grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
      gap: 12px;
    }}
    .metric {{
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 12px;
      background: var(--panel);
    }}
    .metric span {{
      display: block;
      color: var(--muted);
      font-size: 12px;
    }}
    .metric strong {{
      display: block;
      margin-top: 4px;
      font-size: 20px;
    }}
    .table-wrap {{
      overflow-x: auto;
      border: 1px solid var(--line);
      border-radius: 8px;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      min-width: 760px;
      background: #ffffff;
    }}
    th, td {{
      padding: 10px 12px;
      border-bottom: 1px solid var(--line);
      text-align: left;
      vertical-align: top;
    }}
    th {{
      background: var(--panel);
      font-size: 12px;
      color: var(--muted);
      text-transform: uppercase;
      letter-spacing: 0;
    }}
    tr:last-child td {{ border-bottom: 0; }}
    .num {{ text-align: right; font-variant-numeric: tabular-nums; }}
    .positive {{ color: var(--positive); }}
    .negative {{ color: var(--negative); }}
    .empty {{
      border: 1px dashed var(--line);
      border-radius: 8px;
      padding: 18px;
      color: var(--muted);
      background: var(--panel);
    }}
    footer {{
      border-top: 1px solid var(--line);
      color: var(--muted);
      padding: 18px 20px 28px;
    }}
    footer div {{
      max-width: 1120px;
      margin: 0 auto;
    }}
    @media (max-width: 760px) {{
      .nav {{ align-items: flex-start; flex-direction: column; }}
      .hero {{ grid-template-columns: 1fr; min-height: 0; }}
      h1 {{ font-size: 32px; }}
      .signal-strip {{ height: 120px; }}
    }}
  </style>
</head>
<body>
  <header>
    <div class="nav">
      <div class="brand">Signal League</div>
      <nav>{nav_links}</nav>
    </div>
  </header>
  <main>
    {body}
  </main>
  <footer>
    <div>{_escape(DISCLAIMER)}</div>
  </footer>
</body>
</html>
"""


def _summary_grid(metadata: dict[str, Any]) -> str:
    metrics = [
        ("Signals", metadata.get("signal_count")),
        ("Forward Returns", metadata.get("forward_return_count")),
        ("Price Rows", metadata.get("price_count")),
        ("Latest Price Date", metadata.get("latest_price_date")),
    ]
    return _metric_grid(metrics)


def _quality_grid(data_quality: dict[str, Any]) -> str:
    metrics = [
        ("Last Collection", data_quality.get("last_collection_time")),
        ("Signals Collected", data_quality.get("signals_collected")),
        ("Price Rows", data_quality.get("prices_collected")),
        ("Forward Returns", data_quality.get("forward_returns_count")),
        ("Missing Tickers", len(data_quality.get("missing_tickers", []))),
        ("Failed Signals", data_quality.get("failed_signal_count")),
    ]
    return _metric_grid(metrics)


def _metric_grid(metrics: list[tuple[str, Any]]) -> str:
    items = "\n".join(
        f'<div class="metric"><span>{_escape(label)}</span><strong>{_display(value)}</strong></div>'
        for label, value in metrics
    )
    return f'<div class="grid">{items}</div>'


def _leaderboard_table(rows: list[dict[str, Any]], *, compact: bool) -> str:
    display_rows = rows[:5] if compact else rows
    cells = []
    for row in display_rows:
        cells.append(
            "<tr>"
            f"<td>{_escape(row['category'])}</td>"
            f"<td>{_escape(row['source'])}</td>"
            f"<td class=\"num {_value_class(row.get('return_20d'))}\">{_percent(row.get('return_20d'))}</td>"
            f"<td class=\"num {_value_class(row.get('return_60d'))}\">{_percent(row.get('return_60d'))}</td>"
            f"<td class=\"num {_value_class(row.get('spy_alpha_60d'))}\">{_percent(row.get('spy_alpha_60d'))}</td>"
            f"<td class=\"num {_value_class(row.get('sector_alpha_60d'))}\">{_percent(row.get('sector_alpha_60d'))}</td>"
            f"<td class=\"num\">{_percent(row.get('hit_rate_60d'))}</td>"
            f"<td class=\"num\">{_display(row.get('sample_size_60d'))}</td>"
            "</tr>"
        )

    return f"""
    <div class="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Category</th>
            <th>Source</th>
            <th class="num">20D Return</th>
            <th class="num">60D Return</th>
            <th class="num">60D SPY Alpha</th>
            <th class="num">60D Sector Alpha</th>
            <th class="num">Hit Rate</th>
            <th class="num">Sample</th>
          </tr>
        </thead>
        <tbody>{''.join(cells)}</tbody>
      </table>
    </div>
    """


def _raw_metric_table(rows: list[dict[str, Any]]) -> str:
    body = ["<section><h2>All Horizons</h2>"]
    if not rows:
        body.append(_empty_state("No horizon-level metrics are available yet."))
        body.append("</section>")
        return "\n".join(body)

    cells = []
    for row in rows:
        cells.append(
            "<tr>"
            f"<td>{_escape(row['category'])}</td>"
            f"<td>{_escape(row['source'])}</td>"
            f"<td class=\"num\">{row['horizon']}D</td>"
            f"<td class=\"num\">{_display(row['sample_size'])}</td>"
            f"<td class=\"num\">{_percent(row['hit_rate'])}</td>"
            f"<td class=\"num {_value_class(row.get('average_return'))}\">{_percent(row['average_return'])}</td>"
            f"<td class=\"num {_value_class(row.get('average_spy_alpha'))}\">{_percent(row['average_spy_alpha'])}</td>"
            f"<td class=\"num {_value_class(row.get('average_sector_alpha'))}\">{_percent(row['average_sector_alpha'])}</td>"
            f"<td class=\"num\">{_number(row['sharpe_like_score'])}</td>"
            "</tr>"
        )

    body.append(
        f"""
        <div class="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Category</th>
                <th>Source</th>
                <th class="num">Horizon</th>
                <th class="num">Sample</th>
                <th class="num">Hit Rate</th>
                <th class="num">Avg Return</th>
                <th class="num">Avg SPY Alpha</th>
                <th class="num">Avg Sector Alpha</th>
                <th class="num">Sharpe Like</th>
              </tr>
            </thead>
            <tbody>{''.join(cells)}</tbody>
          </table>
        </div>
        """
    )
    body.append("</section>")
    return "\n".join(body)


def _source_runs_table(rows: list[dict[str, Any]]) -> str:
    cells = []
    for row in rows:
        cells.append(
            "<tr>"
            f"<td>{_escape(row['source'])}</td>"
            f"<td class=\"num\">{_display(row['attempted'])}</td>"
            f"<td class=\"num\">{_display(row['succeeded'])}</td>"
            f"<td class=\"num\">{_display(row['failed'])}</td>"
            f"<td class=\"num\">{_percent(row['success_rate'])}</td>"
            f"<td>{_display(row['last_collection_time'])}</td>"
            "</tr>"
        )

    return f"""
    <div class="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Source</th>
            <th class="num">Attempted</th>
            <th class="num">Succeeded</th>
            <th class="num">Failed</th>
            <th class="num">Success Rate</th>
            <th>Last Collection</th>
          </tr>
        </thead>
        <tbody>{''.join(cells)}</tbody>
      </table>
    </div>
    """


def _failed_tickers_table(rows: list[dict[str, Any]]) -> str:
    cells = []
    for row in rows:
        cells.append(
            "<tr>"
            f"<td>{_escape(row['date'])}</td>"
            f"<td>{_escape(row['ticker'])}</td>"
            f"<td>{_escape(row['source'])}</td>"
            f"<td>{_escape(row.get('error_message') or '')}</td>"
            "</tr>"
        )

    return f"""
    <div class="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Date</th>
            <th>Ticker</th>
            <th>Source</th>
            <th>Error</th>
          </tr>
        </thead>
        <tbody>{''.join(cells)}</tbody>
      </table>
    </div>
    """


def _empty_state(message: str) -> str:
    return f'<div class="empty">{_escape(message)}</div>'


def _display(value: Any) -> str:
    if value is None or value == "":
        return "&mdash;"
    return _escape(str(value))


def _percent(value: Any) -> str:
    if value is None:
        return "&mdash;"
    return f"{float(value) * 100:.2f}%"


def _number(value: Any) -> str:
    if value is None:
        return "&mdash;"
    return f"{float(value):.3f}"


def _value_class(value: Any) -> str:
    if value is None:
        return ""
    numeric = float(value)
    if numeric > 0:
        return "positive"
    if numeric < 0:
        return "negative"
    return ""


def _escape(value: Any) -> str:
    return html.escape(str(value), quote=True)


def _scalar(conn: sqlite3.Connection, query: str) -> Any:
    row = conn.execute(query).fetchone()
    return row[0] if row else None
