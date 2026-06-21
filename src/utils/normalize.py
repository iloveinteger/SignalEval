from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class NormalizedSignal:
    raw_signal: str
    normalized_signal: str
    score: int


class UnknownSourceError(ValueError):
    pass


class UnknownSignalError(ValueError):
    pass


INVESTING_MAPPING = {
    "strong sell": ("Strong Sell", -2),
    "sell": ("Sell", -1),
    "neutral": ("Neutral", 0),
    "buy": ("Buy", 1),
    "strong buy": ("Strong Buy", 2),
}

YAHOO_MAPPING = {
    "strong sell": ("Strong Sell", -2),
    "sell": ("Sell", -1),
    "hold": ("Hold", 0),
    "buy": ("Buy", 1),
    "strong buy": ("Strong Buy", 2),
}

ZACKS_RANK_MAPPING = {
    "1": ("Strong Buy", 2),
    "2": ("Buy", 1),
    "3": ("Hold", 0),
    "4": ("Sell", -1),
    "5": ("Strong Sell", -2),
}

SOURCE_ALIASES = {
    "investing": "investing",
    "investing.com": "investing",
    "investing technical summary": "investing",
    "investing.com technical summary": "investing",
    "technical": "investing",
    "zacks": "zacks",
    "zacks rank": "zacks",
    "earnings revision": "zacks",
    "earnings_revision": "zacks",
    "yahoo": "yahoo",
    "yahoo finance": "yahoo",
    "yahoo analyst recommendation": "yahoo",
    "yahoo finance analyst recommendation": "yahoo",
    "analyst consensus": "yahoo",
    "analyst_consensus": "yahoo",
}


def normalize_signal(source: str, raw_signal: str) -> NormalizedSignal:
    source_key = normalize_source(source)
    if source_key == "investing":
        return normalize_investing_signal(raw_signal)
    if source_key == "zacks":
        return normalize_zacks_rank(raw_signal)
    if source_key == "yahoo":
        return normalize_yahoo_recommendation(raw_signal)
    raise UnknownSourceError(f"Unknown source: {source!r}")


def normalize_source(source: str) -> str:
    key = _canonical(source)
    try:
        return SOURCE_ALIASES[key]
    except KeyError as exc:
        raise UnknownSourceError(f"Unknown source: {source!r}") from exc


def normalize_investing_signal(raw_signal: str) -> NormalizedSignal:
    return _normalize_label("Investing", raw_signal, INVESTING_MAPPING)


def normalize_yahoo_recommendation(raw_signal: str) -> NormalizedSignal:
    return _normalize_label("Yahoo", raw_signal, YAHOO_MAPPING)


def normalize_zacks_rank(raw_signal: str) -> NormalizedSignal:
    raw_text = _required_raw(raw_signal)
    text = _canonical(raw_text)

    rank_match = re.search(r"(?:#\s*)?\b([1-5])\b", text)
    if rank_match:
        normalized, score = ZACKS_RANK_MAPPING[rank_match.group(1)]
        return NormalizedSignal(raw_text, normalized, score)

    zacks_label_mapping = {
        "strong sell": ("Strong Sell", -2),
        "sell": ("Sell", -1),
        "hold": ("Hold", 0),
        "buy": ("Buy", 1),
        "strong buy": ("Strong Buy", 2),
    }
    return _normalize_label("Zacks", raw_text, zacks_label_mapping)


def _normalize_label(
    source_name: str, raw_signal: str, mapping: dict[str, tuple[str, int]]
) -> NormalizedSignal:
    raw_text = _required_raw(raw_signal)
    key = _canonical(raw_text)
    try:
        normalized, score = mapping[key]
    except KeyError as exc:
        raise UnknownSignalError(
            f"Unknown {source_name} signal: {raw_signal!r}"
        ) from exc

    return NormalizedSignal(raw_text, normalized, score)


def _required_raw(raw_signal: str) -> str:
    if raw_signal is None or str(raw_signal).strip() == "":
        raise UnknownSignalError("Signal value is empty")
    return str(raw_signal).strip()


def _canonical(value: str) -> str:
    text = str(value).strip().lower().replace("_", " ")
    text = re.sub(r"[^a-z0-9#]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()
