# Signal League Project Spec

## Product Direction

Signal League evaluates public Investing.com signals in two ways:

1. Signal accuracy leaderboard
2. Daily portfolio simulation

This is not a recommendation product. It is a historical measurement product.

## Core MVP Question

```text
Do Investing.com public signals outperform a random baseline?
```

## MVP Sources

1. Investing.com Technical Analysis
2. Investing.com Analyst / Financial Consensus
3. Random Baseline control group

Yahoo Finance analyst consensus and Zacks Rank move to Future Extensions.

## Universe

Track the configured S&P 500 universe from:

```text
config/sp500.csv
```

Each row should keep ticker, company name, sector, industry, and active status.

## Source Rules

### Investing.com Technical Analysis

Official score-bearing signal:

```text
Daily timeframe only
```

Other extracted timeframes are metadata only:

- 30 Min
- Hourly
- 5 Hours
- Weekly
- Monthly

Normalization:

```text
Strong Sell = -2
Sell        = -1
Neutral     = 0
Buy         = 1
Strong Buy  = 2
```

Example:

```text
Daily Neutral -> score 0
```

Current parser behavior:

- extracts the selected overall technical signal
- extracts the daily signal
- stores non-daily timeframes as metadata
- does not remove offline sample mode
- does not expand live crawling beyond the existing AAPL-only path

### Investing.com Analyst / Financial Consensus

Required analyst fields:

- Buy count
- Hold count
- Sell count
- analyst total count
- price target average
- price target upside
- supporting financial ratios

Consensus formula:

```text
score_raw = (buy_count - sell_count) / total_count
```

Mapped label and score:

```text
score_raw >= 0.60  -> Strong Buy / 2
score_raw >= 0.20  -> Buy / 1
score_raw > -0.20  -> Hold / 0
score_raw > -0.60  -> Sell / -1
else               -> Strong Sell / -2
```

Example:

```text
29 Buy, 15 Hold, 3 Sell
(29 - 3) / 47 = 0.553
-> Buy / score 1
```

Current parser behavior:

- extracts analyst consensus fields from saved HTML
- parses Buy / Hold / Sell vote counts
- extracts analyst count, price target average, upside, and financial ratios
- valuation fields may be present but locked or unavailable

Locked valuation fields are metadata quality information, not score-bearing
signals.

### Random Baseline

Source name:

```text
Random Baseline
```

Purpose:

- control group for the MVP question
- not a real prediction source
- deterministic and reproducible

## Portfolio Simulation

### Rules

- Initial NAV = `100.0`
- Long-only
- No leverage
- No shorting
- Fractional weights, no share rounding
- Rebalance every trading day after signal collection
- Compare every source portfolio against `SPY`

### Score-to-Weight Mapping

```text
score 2 -> weight input 2
score 1 -> weight input 1
score 0 -> weight input 0
score -1 -> weight input 0
score -2 -> weight input 0
```

Normalize positive weights to 100%.

If no positive signals exist for a source on a day, the source holds cash and
that day returns `0`.

Daily portfolio return:

```text
sum(previous day target weight * ticker daily return)
```

## Data Pipeline

```text
1. Initialize database and sync universe
2. Seed or collect prices
3. Collect Investing.com technical signals
4. Collect Investing.com analyst / financial consensus signals
5. Collect Random Baseline control signals
6. Compute forward returns
7. Simulate source portfolios
8. Export leaderboard, portfolio, and data quality JSON
9. Build static site
```

Offline sample mode remains part of the MVP.

## Repository Shape

Key MVP modules:

```text
src/
  collectors/
    investing.py
    random_baseline.py
  analysis/
    returns.py
    leaderboard.py
    portfolio.py
  site/
    build_static.py
  utils/
    db.py

scripts/
  init_db.py
  seed_mock_prices.py
  collect_investing_samples.py
  collect_random_baseline.py
  compute_returns.py
  simulate_portfolio.py
  build_site.py
```

Expected artifacts:

```text
data/exports/leaderboard.json
data/exports/portfolio.json
data/exports/data_quality.json
docs/leaderboard.html
docs/portfolio.html
docs/stocks/*.html
```

## Database Notes

The `signals` table remains the core storage surface, with one row per
`date/ticker/source`.

Required stored fields:

- raw signal
- normalized signal
- score
- price at signal
- structured metadata JSON for parser details

## Site Navigation

Top-level navigation:

```text
Home / Leaderboard / Portfolio / Stocks / Data Quality
```

Labeling requirements:

- saved Investing.com rows must read as saved samples
- Random Baseline must read as a control group

## Acceptance Criteria

The current MVP step is complete when:

1. Technical parsing uses `Daily` as the official stored score-bearing signal
2. Analyst parsing uses the Buy/Hold/Sell vote-count formula
3. Portfolio simulation exports daily NAV series per source
4. `portfolio.json` and `portfolio.html` are generated
5. Leaderboard and stock pages remain intact
6. Random Baseline is clearly labeled as a control group
7. Offline sample mode still works
8. Existing live fetch scope stays limited to AAPL

## Future Extensions

- Yahoo Finance analyst consensus
- Zacks Rank
- richer valuation models
- more source pages
- sector-balanced portfolio variants
- charts and richer static-site interactivity
