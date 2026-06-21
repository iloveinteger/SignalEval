from __future__ import annotations

import json
import sqlite3
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from statistics import mean, median, stdev
from typing import Any

from src.utils.db import PROJECT_ROOT, utc_now_iso

DEFAULT_LEADERBOARD_PATH = PROJECT_ROOT / "data" / "exports" / "leaderboard.json"


@dataclass(frozen=True)
class LeaderboardRow:
    category: str
    source: str
    horizon: int
    sample_size: int
    hit_rate: float | None
    average_return: float | None
    median_return: float | None
    average_spy_alpha: float | None
    median_spy_alpha: float | None
    average_sector_alpha: float | None
    median_sector_alpha: float | None
    long_short_spread: float | None
    volatility: float | None
    sharpe_like_score: float | None

    def as_dict(self) -> dict[str, Any]:
        return {
            "category": self.category,
            "source": self.source,
            "horizon": self.horizon,
            "sample_size": self.sample_size,
            "hit_rate": self.hit_rate,
            "average_return": self.average_return,
            "median_return": self.median_return,
            "average_spy_alpha": self.average_spy_alpha,
            "median_spy_alpha": self.median_spy_alpha,
            "average_sector_alpha": self.average_sector_alpha,
            "median_sector_alpha": self.median_sector_alpha,
            "long_short_spread": self.long_short_spread,
            "volatility": self.volatility,
            "sharpe_like_score": self.sharpe_like_score,
        }


def build_leaderboard(conn: sqlite3.Connection) -> dict[str, Any]:
    records = _load_return_records(conn)
    grouped: dict[tuple[str, str, int], list[sqlite3.Row]] = defaultdict(list)
    signal_grouped: dict[tuple[str, str, str, int, int | None], list[sqlite3.Row]] = (
        defaultdict(list)
    )

    for record in records:
        category = record["category"] or "unknown"
        source = record["source"] or "unknown"
        horizon = int(record["horizon"])
        grouped[(category, source, horizon)].append(record)
        signal_grouped[
            (
                category,
                source,
                record["normalized_signal"] or "Unknown",
                horizon,
                record["score"],
            )
        ].append(record)

    rows = [
        _aggregate_group(category, source, horizon, values).as_dict()
        for (category, source, horizon), values in sorted(grouped.items())
    ]

    by_signal = [
        _aggregate_signal_group(category, source, signal, horizon, score, values)
        for (category, source, signal, horizon, score), values in sorted(
            signal_grouped.items()
        )
    ]

    return {
        "generated_at": utc_now_iso(),
        "metadata": _metadata(conn),
        "rows": rows,
        "top_level": _top_level_rows(rows),
        "by_signal": by_signal,
    }


def export_leaderboard_json(
    conn: sqlite3.Connection,
    output_path: str | Path = DEFAULT_LEADERBOARD_PATH,
) -> dict[str, Any]:
    payload = build_leaderboard(conn)
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return payload


def _load_return_records(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT
          signals.category,
          signals.source,
          signals.normalized_signal,
          signals.score,
          forward_returns.horizon,
          forward_returns.raw_return,
          forward_returns.spy_alpha,
          forward_returns.sector_alpha
        FROM forward_returns
        JOIN signals ON signals.id = forward_returns.signal_id
        WHERE signals.success = 1
          AND forward_returns.raw_return IS NOT NULL
        """
    ).fetchall()


def _metadata(conn: sqlite3.Connection) -> dict[str, Any]:
    signal_count = _scalar(conn, "SELECT COUNT(*) FROM signals")
    forward_return_count = _scalar(conn, "SELECT COUNT(*) FROM forward_returns")
    price_count = _scalar(conn, "SELECT COUNT(*) FROM prices")
    latest_signal_date = _scalar(conn, "SELECT MAX(date) FROM signals")
    latest_price_date = _scalar(conn, "SELECT MAX(date) FROM prices")

    return {
        "signal_count": signal_count,
        "forward_return_count": forward_return_count,
        "price_count": price_count,
        "latest_signal_date": latest_signal_date,
        "latest_price_date": latest_price_date,
    }


def _aggregate_group(
    category: str,
    source: str,
    horizon: int,
    values: list[sqlite3.Row],
) -> LeaderboardRow:
    raw_returns = _numbers(values, "raw_return")
    spy_alphas = _numbers(values, "spy_alpha")
    sector_alphas = _numbers(values, "sector_alpha")
    volatility = stdev(raw_returns) if len(raw_returns) > 1 else 0.0
    average_return = _mean(raw_returns)

    return LeaderboardRow(
        category=category,
        source=source,
        horizon=horizon,
        sample_size=len(raw_returns),
        hit_rate=_hit_rate(raw_returns),
        average_return=average_return,
        median_return=_median(raw_returns),
        average_spy_alpha=_mean(spy_alphas),
        median_spy_alpha=_median(spy_alphas),
        average_sector_alpha=_mean(sector_alphas),
        median_sector_alpha=_median(sector_alphas),
        long_short_spread=_long_short_spread(values),
        volatility=volatility,
        sharpe_like_score=(
            average_return / volatility
            if average_return is not None and volatility > 0
            else None
        ),
    )


def _aggregate_signal_group(
    category: str,
    source: str,
    signal: str,
    horizon: int,
    score: int | None,
    values: list[sqlite3.Row],
) -> dict[str, Any]:
    row = _aggregate_group(category, source, horizon, values)
    payload = row.as_dict()
    payload["signal"] = signal
    payload["score"] = score
    return payload


def _top_level_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], dict[int, dict[str, Any]]] = defaultdict(dict)
    for row in rows:
        grouped[(row["category"], row["source"])][int(row["horizon"])] = row

    top_rows = []
    for (category, source), by_horizon in grouped.items():
        row_20 = by_horizon.get(20)
        row_60 = by_horizon.get(60)
        display_row = row_60 or row_20 or next(iter(by_horizon.values()))
        top_rows.append(
            {
                "category": category,
                "source": source,
                "return_20d": _metric(row_20, "average_return"),
                "return_60d": _metric(row_60, "average_return"),
                "spy_alpha_60d": _metric(row_60, "average_spy_alpha"),
                "sector_alpha_60d": _metric(row_60, "average_sector_alpha"),
                "hit_rate_60d": _metric(row_60, "hit_rate"),
                "sample_size_60d": _metric(row_60, "sample_size"),
                "available_horizons": sorted(by_horizon),
                "fallback_horizon": display_row["horizon"],
                "fallback_sample_size": display_row["sample_size"],
            }
        )

    return sorted(
        top_rows,
        key=lambda row: (
            row["sector_alpha_60d"] is None,
            -(row["sector_alpha_60d"] or 0),
            row["category"],
            row["source"],
        ),
    )


def _long_short_spread(values: list[sqlite3.Row]) -> float | None:
    strong_buys = [float(row["raw_return"]) for row in values if row["score"] == 2]
    strong_sells = [float(row["raw_return"]) for row in values if row["score"] == -2]
    if not strong_buys or not strong_sells:
        return None
    return mean(strong_buys) - mean(strong_sells)


def _numbers(values: list[sqlite3.Row], field: str) -> list[float]:
    return [float(row[field]) for row in values if row[field] is not None]


def _hit_rate(values: list[float]) -> float | None:
    if not values:
        return None
    return sum(1 for value in values if value > 0) / len(values)


def _mean(values: list[float]) -> float | None:
    return mean(values) if values else None


def _median(values: list[float]) -> float | None:
    return median(values) if values else None


def _metric(row: dict[str, Any] | None, key: str) -> Any:
    if row is None:
        return None
    return row.get(key)


def _scalar(conn: sqlite3.Connection, query: str) -> Any:
    row = conn.execute(query).fetchone()
    return row[0] if row else None
