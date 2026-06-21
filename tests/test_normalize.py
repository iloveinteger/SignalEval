from __future__ import annotations

import pytest

from src.utils.normalize import (
    UnknownSignalError,
    UnknownSourceError,
    normalize_investing_signal,
    normalize_signal,
    normalize_yahoo_recommendation,
    normalize_zacks_rank,
)


@pytest.mark.parametrize(
    ("raw_signal", "normalized", "score"),
    [
        ("Strong Sell", "Strong Sell", -2),
        ("sell", "Sell", -1),
        (" Neutral ", "Neutral", 0),
        ("BUY", "Buy", 1),
        ("Strong Buy", "Strong Buy", 2),
    ],
)
def test_normalize_investing_signal(raw_signal, normalized, score):
    result = normalize_investing_signal(raw_signal)

    assert result.normalized_signal == normalized
    assert result.score == score


@pytest.mark.parametrize(
    ("raw_signal", "normalized", "score"),
    [
        ("#5 Strong Sell", "Strong Sell", -2),
        ("#4 Sell", "Sell", -1),
        ("#3 Hold", "Hold", 0),
        ("#2 Buy", "Buy", 1),
        ("#1 Strong Buy", "Strong Buy", 2),
        ("Zacks Rank 1", "Strong Buy", 2),
    ],
)
def test_normalize_zacks_rank(raw_signal, normalized, score):
    result = normalize_zacks_rank(raw_signal)

    assert result.normalized_signal == normalized
    assert result.score == score


@pytest.mark.parametrize(
    ("raw_signal", "normalized", "score"),
    [
        ("Strong Sell", "Strong Sell", -2),
        ("Sell", "Sell", -1),
        ("Hold", "Hold", 0),
        ("Buy", "Buy", 1),
        ("Strong Buy", "Strong Buy", 2),
    ],
)
def test_normalize_yahoo_recommendation(raw_signal, normalized, score):
    result = normalize_yahoo_recommendation(raw_signal)

    assert result.normalized_signal == normalized
    assert result.score == score


def test_normalize_signal_accepts_source_aliases():
    result = normalize_signal("Yahoo Finance Analyst Recommendation", "Buy")

    assert result.normalized_signal == "Buy"
    assert result.score == 1


def test_unknown_source_raises_clear_error():
    with pytest.raises(UnknownSourceError):
        normalize_signal("made-up-source", "Buy")


def test_unknown_signal_raises_clear_error():
    with pytest.raises(UnknownSignalError):
        normalize_investing_signal("Outperform")
