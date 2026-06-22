# Signal League Project Spec

## Project Summary

Signal League is a public investment signal performance tracker.

Most finance websites show current ratings such as Buy, Sell, Strong Buy, or
Hold. Signal League asks whether those public signals were actually useful
after the fact.

The MVP is intentionally narrow:

```text
Do Investing.com public signals outperform a random baseline?
```

This is not a stock recommendation service. It is a scoreboard for historical
public signals.

## MVP Scope

### Universe

Track S&P 500 companies from:

```text
config/sp500.csv
```

Each stock should include:

- ticker
- company name
- sector
- industry
- active status

### MVP Signal Sources

The MVP has three signal sources.

1. Investing.com Technical Analysis
2. Investing.com Financial / Analyst Summary
3. Random Baseline control group

Yahoo Finance analyst consensus and Zacks Rank are future extensions, not MVP
sources.

## Core MVP Question

```text
Do Investing.com public signals outperform a random baseline?
```

The random baseline is a control group. Its purpose is to show whether the
Investing.com signals add value beyond random directional labels over the same
universe, dates, and evaluation horizons.

## MVP Source Details

### 1. Investing.com Technical Analysis

Source:

```text
Investing.com Technical Analysis
```

Category:

```text
technical
```

Current parser status:

- Parses saved Investing.com HTML offline.
- Extracts the selected overall technical signal.
- Extracts the daily technical signal separately.
- Does not make live HTTP requests yet.
- Does not replace mock collectors yet.

Known sample behavior:

- The saved AAPL technical page exposes a selected overall signal of Buy for
  the selected timeframe.
- The same page exposes a daily signal of Neutral.

Normalized signal scale:

```text
Strong Sell = -2
Sell        = -1
Neutral     = 0
Buy         = 1
Strong Buy  = 2
```

### 2. Investing.com Financial / Analyst Summary

Source:

```text
Investing.com Financial / Analyst Summary
```

Primary MVP fields currently extractable from saved HTML:

- analyst consensus
- analyst count
- analyst rating bucket counts when present
- price target average
- price target upside
- financial ratios

Financial ratios currently extracted from the saved sample include:

- P/E ratio
- Price/Book
- Debt / Equity
- Return on Equity
- Dividend Yield
- EBITDA

Valuation fields:

- Fair Value and Fair Value Upside may appear in the page.
- These fields may be locked or unavailable.
- Locked valuation fields should not be treated as reliable score-bearing
  signals.

Initial score-bearing field:

```text
overall analyst consensus
```

Suggested normalized analyst scale:

```text
Strong Sell = -2
Sell        = -1
Hold        = 0
Neutral     = 0
Buy         = 1
Strong Buy  = 2
```

Financial ratios should initially be stored as supporting fields or source
metadata unless a specific ratio-to-score rule is defined and tested.

### 3. Random Baseline Control Group

Source:

```text
Random Baseline
```

Category:

```text
random_baseline
```

Purpose:

- Generate random labels over the same ticker/date universe as the public
  signals.
- Provide a control group for the MVP question.
- Make it clear whether observed Investing.com performance is meaningfully
  different from random labels.

Recommended baseline labels:

```text
Strong Sell = -2
Sell        = -1
Neutral     = 0
Buy         = 1
Strong Buy  = 2
```

The baseline generator should be deterministic for reproducible tests and
leaderboards, for example by seeding from source name, ticker, and date.

## Core Data Pipeline

Every run:

```text
1. Load S&P 500 universe
2. Fetch latest adjusted close prices
3. Collect Investing.com technical signals
4. Collect Investing.com financial / analyst summary signals
5. Generate random baseline signals for the same scope
6. Normalize score-bearing signals to -2 through +2
7. Store signals with price_at_signal
8. Compute available forward returns for older signals
9. Compare Investing.com sources against the random baseline
10. Generate leaderboard and data-quality exports
11. Build static website
```

Live Investing.com HTTP collection is not part of the current parser milestone.
The first Investing.com parser is offline and sample-backed.

## Repository Structure

Current and intended MVP structure:

```text
signal-league/
  README.md
  PROJECT_SPEC.md
  requirements.txt

  config/
    sp500.csv

  data/
    signal_league.sqlite
    exports/
      leaderboard.json
      data_quality.json

  samples/
    investing/
      AAPL Technical Analysis, RSI and Moving Averages - Investing.com.html
      NASDAQ_AAPL Financials _ Apple - Investing.com.html

  src/
    collectors/
      investing.py
      mock.py
      yahoo.py

    prices/
      yahoo_prices.py
      mock_prices.py

    analysis/
      returns.py
      leaderboard.py

    site/
      build_static.py

    utils/
      db.py
      universe.py
      normalize.py
      logging.py
      benchmarks.py

  scripts/
    init_db.py
    collect_prices.py
    collect_signals.py
    collect_mock_signals.py
    compute_returns.py
    build_site.py

  tests/
```

`src/collectors/investing.py` should remain an offline parser until live
collection is explicitly added.

## Database Schema

Use SQLite for MVP.

### stocks

```sql
CREATE TABLE IF NOT EXISTS stocks (
  ticker TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  sector TEXT,
  industry TEXT,
  active INTEGER DEFAULT 1
);
```

### signals

```sql
CREATE TABLE IF NOT EXISTS signals (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  date TEXT NOT NULL,
  ticker TEXT NOT NULL,
  source TEXT NOT NULL,
  category TEXT NOT NULL,
  raw_signal TEXT,
  normalized_signal TEXT,
  score INTEGER,
  price_at_signal REAL,
  collected_at TEXT NOT NULL,
  success INTEGER DEFAULT 1,
  error_message TEXT,
  UNIQUE(date, ticker, source)
);
```

### prices

```sql
CREATE TABLE IF NOT EXISTS prices (
  date TEXT NOT NULL,
  ticker TEXT NOT NULL,
  adjusted_close REAL NOT NULL,
  PRIMARY KEY(date, ticker)
);
```

### forward_returns

```sql
CREATE TABLE IF NOT EXISTS forward_returns (
  signal_id INTEGER NOT NULL,
  horizon INTEGER NOT NULL,
  raw_return REAL,
  spy_return REAL,
  spy_alpha REAL,
  sector_alpha REAL,
  computed_at TEXT NOT NULL,
  PRIMARY KEY(signal_id, horizon)
);
```

### collection_runs

```sql
CREATE TABLE IF NOT EXISTS collection_runs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  run_date TEXT NOT NULL,
  source TEXT NOT NULL,
  attempted INTEGER,
  succeeded INTEGER,
  failed INTEGER,
  started_at TEXT,
  finished_at TEXT
);
```

## Evaluation Horizons

Calculate forward returns for:

```text
1D
5D
20D
60D
120D
```

Use trading days, not calendar days.

## Main Metrics

For each source, signal, category, sector, and horizon:

```text
sample_size
hit_rate
average_return
median_return
average_spy_alpha
median_spy_alpha
average_sector_alpha
long_short_spread
volatility
sharpe_like_score
```

Definitions:

```text
hit_rate = percentage of signals with positive forward return

spy_alpha = stock_forward_return - SPY_forward_return

sector_alpha = stock_forward_return - sector_etf_forward_return

long_short_spread = average_return(score=2) - average_return(score=-2)

sharpe_like_score = average_return / standard_deviation
```

## Bias Control

The site should show two modes.

### Raw Mode

Simple average across all collected S&P 500 signals.

### Balanced Mode

Sector-neutral result.

Calculation:

```text
1. Compute metric separately for each GICS sector
2. Average sector results equally
3. Ignore sectors with insufficient sample size
```

This prevents Technology or mega-cap stocks from dominating the results.

## Sector Benchmarks

Use these ETF mappings for sector alpha:

```text
Information Technology      -> XLK
Financials                  -> XLF
Health Care                 -> XLV
Energy                      -> XLE
Industrials                 -> XLI
Consumer Discretionary      -> XLY
Consumer Staples            -> XLP
Utilities                   -> XLU
Materials                   -> XLB
Real Estate                 -> XLRE
Communication Services      -> XLC
```

Also always track:

```text
SPY
```

## Static Site Pages

### Home

Purpose:

```text
Explain the project.
Show latest top-level leaderboard.
Show whether Investing.com sources are outperforming the random baseline.
Show last updated date.
```

Headline:

```text
Do Investing.com public signals outperform a random baseline?
```

### Leaderboard

Show:

```text
Category
Source
20D return
60D return
60D SPY alpha
60D sector alpha
Hit rate
Sample size
Random baseline comparison
```

Default sorting:

```text
60D SPY alpha versus random baseline
```

### Source Report

For each MVP source:

```text
Investing.com Technical Analysis
Investing.com Financial / Analyst Summary
Random Baseline
```

Show performance by signal:

```text
Strong Buy
Buy
Neutral / Hold
Sell
Strong Sell
```

### Sector View

Show performance by sector.

Key question:

```text
Does the Investing.com edge, if any, persist across sectors?
```

### Signal Conflicts

Track cases where MVP sources disagree.

Examples:

```text
Technical Buy + Analyst Sell
Technical Strong Sell + Analyst Buy
Investing.com Buy + Random Baseline Sell
```

Show which source was more correct after 20D, 60D, and 120D.

### Data Quality

Show:

```text
last collection time
source success rate
missing tickers
failed tickers
number of signals collected
number of prices collected
locked or unavailable valuation fields
```

This page is important because data quality is part of the product.

## Implementation TODO

### Phase 1 - Foundation

- [x] Add Python project structure
- [x] Add SQLite schema initialization
- [x] Add S&P 500 universe loading
- [x] Add signal normalization utilities
- [x] Add focused pytest coverage

### Phase 2 - Price Data

- [x] Add mock prices for deterministic local tests
- [x] Add Yahoo-compatible adjusted close price collection
- [x] Store prices in SQLite
- [x] Add retry handling and logging

### Phase 3 - Mock Pipeline

- [x] Add mock signal collectors
- [x] Store mock signals and collection run stats
- [x] Compute forward returns
- [x] Build static site output

Mock collectors remain in place until real MVP sources are intentionally wired
into collection.

### Phase 4 - Investing.com Offline Parsers

- [x] Add offline parser for saved Investing.com technical HTML
- [x] Extract selected overall technical signal
- [x] Extract daily technical signal
- [x] Add tests using exact saved technical sample filename
- [x] Inspect saved financial / analyst summary HTML
- [x] Extract analyst consensus, analyst count, price target average, upside,
      and financial ratios
- [x] Detect locked or unavailable valuation fields
- [x] Add tests using exact saved financial sample filename
- [ ] Convert parser outputs into database-ready signal objects
- [ ] Keep parser tests offline and fixture-backed

### Phase 5 - Random Baseline

- [ ] Implement deterministic random baseline generator
- [ ] Generate labels over the same ticker/date scope as MVP sources
- [ ] Store baseline signals with source `Random Baseline`
- [ ] Add tests for deterministic generation

### Phase 6 - MVP Collector Wiring

- [ ] Add live Investing.com collection only after parser behavior is stable
- [ ] Respect rate limits and request failure handling
- [ ] Store successful Investing.com technical signals
- [ ] Store successful Investing.com analyst consensus signals
- [ ] Store failures with error messages
- [ ] Record collection run stats
- [ ] Do not replace mock collectors until the MVP path is verified

### Phase 7 - Leaderboard and Baseline Comparison

- [ ] Compare each Investing.com source against Random Baseline
- [ ] Add source-level baseline deltas
- [ ] Add signal-level baseline deltas
- [ ] Export leaderboard JSON
- [ ] Surface baseline comparison on the static site

### Phase 8 - Balanced Mode

- [ ] Aggregate returns by sector first
- [ ] Equal-weight sector results
- [ ] Exclude sectors below minimum sample size
- [ ] Export raw and balanced results separately

### Phase 9 - GitHub Actions and Publishing

- [ ] Run pipeline manually with `workflow_dispatch`
- [ ] Confirm DB updates are committed
- [ ] Confirm `docs/` updates are committed
- [ ] Enable GitHub Pages from `docs/`
- [ ] Add failure logging
- [ ] Add collection success rate to site

## MVP Acceptance Criteria

The MVP is complete when:

```text
1. S&P 500 universe loads successfully
2. Prices are stored for required tickers and benchmarks
3. Investing.com technical signals are collected or parsed reliably
4. Investing.com analyst summary signals are collected or parsed reliably
5. Random baseline signals are generated for the same scope
6. Score-bearing signals are stored with date, ticker, source, score, and price
7. Forward returns are calculated for available horizons
8. Leaderboard JSON compares Investing.com sources against the random baseline
9. Static website displays the latest baseline comparison
```

## Future Extensions

These are explicitly out of MVP scope:

### Yahoo Finance Analyst Consensus

- Fetch analyst recommendation from Yahoo Finance.
- Normalize recommendation labels to the common score scale.
- Compare against Investing.com analyst consensus after the MVP is stable.

### Zacks Rank

- Fetch Zacks Rank.
- Normalize `#1 Strong Buy` through `#5 Strong Sell`.
- Add as an earnings-revision source after the MVP is stable.

### Additional Extensions

- More signal sources
- More robust valuation models
- Conflict analysis across multiple non-baseline sources
- Charts and richer static-site interactivity

## Important Implementation Notes

### Keep the MVP honest

The first public question is not "which finance site is best." The first public
question is whether Investing.com public signals outperform a random baseline.

### Store raw signals

Always store the raw signal before normalization.

Example:

```text
raw_signal = "Buy"
normalized_signal = "Buy"
score = 1
```

### Store parser context

For Investing.com Financial / Analyst Summary, store supporting context such as
analyst count, price target average, price target upside, and financial ratios
when available.

### Treat locked valuation fields carefully

Valuation fields may be present but locked. Locked fields should be surfaced as
unavailable in data-quality output, not converted into signal scores.

### Store failures

Do not silently ignore failures. Failure records are useful for the Data Quality
page.

### Avoid daily duplicate noise

Use:

```sql
UNIQUE(date, ticker, source)
```

### Disclaimers

Use:

```text
Signal League is not financial advice.
It evaluates historical public signals.
Past performance does not imply future performance.
```
