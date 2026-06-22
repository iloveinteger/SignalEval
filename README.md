# Signal League

Signal League evaluates public Investing.com signals in two ways:

1. Signal accuracy leaderboard
2. Daily portfolio simulation

The current MVP question is:

```text
Do Investing.com public signals outperform a random baseline?
```

## MVP Sources

1. Investing.com Technical Analysis
2. Investing.com Analyst / Financial Consensus
3. Random Baseline control group

Yahoo Finance analyst consensus and Zacks Rank are future extensions, not MVP
sources.

Signal League is not financial advice. It evaluates historical public signals,
and past performance does not imply future performance.

## Current Investing Parser Coverage

The offline Investing.com parser works from saved HTML samples. Offline sample
mode remains supported. Live crawling is limited to the existing AAPL-only
debug path.

- Technical parser:
  - uses the `Daily` timeframe as the official score-bearing signal
  - still extracts the selected overall technical signal
  - stores other timeframes as metadata only: `30 Min`, `Hourly`, `5 Hours`,
    `Weekly`, `Monthly`
- Financial / analyst parser:
  - parses Buy / Hold / Sell analyst counts
  - computes the consensus score from `(buy_count - sell_count) / total_count`
  - extracts analyst consensus, analyst count, price target average, upside,
    and financial ratios
- Valuation fields may be locked or unavailable in saved pages.

## Portfolio Rules

- Initial NAV = `100.0`
- Long-only
- No leverage
- No shorting
- Fractional weights
- Score-to-weight inputs:
  - `2 -> 2`
  - `1 -> 1`
  - `0/-1/-2 -> 0`
- Positive weights are normalized to 100%
- If no positive signals exist, the portfolio holds cash and daily return is `0`
- Rebalance every trading day after signal collection
- Compare each source portfolio against `SPY`

## Setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

## Run Tests

```powershell
python -m pytest
```

## Example Offline MVP Run

```powershell
python scripts/init_db.py
python scripts/seed_mock_prices.py --periods 260
python scripts/collect_investing_samples.py
python scripts/collect_random_baseline.py --date 2026-06-18
python scripts/compute_returns.py
python scripts/simulate_portfolio.py
python scripts/build_site.py
```
