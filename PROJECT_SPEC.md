Below is a **Codex-ready project brief + TODO** you can paste into your repo as `PROJECT_SPEC.md`.

---

# Signal League

## Project Summary

Signal League is a public investment signal performance tracker.

Most finance websites show current ratings such as **Buy**, **Sell**, **Strong Buy**, or **Hold**. Signal League asks a different question:

> Were those signals actually right?

Every trading day, Signal League records public stock signals across the S&P 500 from multiple signal categories:

* Technical analysis
* Analyst consensus
* Earnings-revision models

As time passes, each signal is evaluated against future stock returns, SPY-adjusted alpha, and sector-adjusted alpha.

This is **not** a stock recommendation service.
It is a scoreboard for forecasters.

---

# Core Question

> Who predicts better: chartists, analysts, or earnings-revision models?

---

# MVP Scope

## Universe

Track all S&P 500 companies.

Each stock should include:

* ticker
* company name
* sector
* industry
* active status

The initial universe can be stored in:

```text
config/sp500.csv
```

---

# Initial Signal Sources

## 1. Technical Analysis

Source:

```text
Investing.com Technical Summary
```

Category:

```text
technical
```

Normalized signal scale:

```text
Strong Sell = -2
Sell        = -1
Neutral     = 0
Buy         = 1
Strong Buy  = 2
```

---

## 2. Earnings Revision

Source:

```text
Zacks Rank
```

Category:

```text
earnings_revision
```

Normalized signal scale:

```text
#5 Strong Sell = -2
#4 Sell        = -1
#3 Hold        = 0
#2 Buy         = 1
#1 Strong Buy  = 2
```

---

## 3. Analyst Consensus

Source:

```text
Yahoo Finance Analyst Recommendation
```

Category:

```text
analyst_consensus
```

Normalized signal scale:

```text
Strong Sell = -2
Sell        = -1
Hold        = 0
Buy         = 1
Strong Buy  = 2
```

---

# Core Data Pipeline

Every trading day:

```text
1. Load S&P 500 universe
2. Fetch latest adjusted close prices
3. Collect Investing technical signals
4. Collect Zacks Rank signals
5. Collect Yahoo analyst consensus signals
6. Normalize all signals to score -2 to +2
7. Store signals with price_at_signal
8. Compute available forward returns for older signals
9. Generate leaderboard data
10. Build static website
11. Commit updated data/site to GitHub
```

---

# Repository Structure

```text
signal-league/
  README.md
  PROJECT_SPEC.md
  requirements.txt

  config/
    sp500.csv
    sources.yaml

  data/
    signal_league.sqlite
    exports/
      leaderboard.json
      source_reports.json
      data_quality.json

  src/
    collectors/
      investing.py
      zacks.py
      yahoo.py

    prices/
      yahoo_prices.py

    analysis/
      returns.py
      leaderboard.py
      balanced.py
      conflicts.py

    site/
      build_static.py
      templates/

    utils/
      db.py
      universe.py
      normalize.py
      logging.py
      dates.py

  scripts/
    init_db.py
    collect_daily.py
    compute_returns.py
    build_site.py

  tests/
    test_normalize.py
    test_returns.py
    test_db.py

  docs/
    index.html
    leaderboard.html
    source.html
    sectors.html
    conflicts.html
    data-quality.html

  .github/
    workflows/
      daily.yml
```

---

# Database Schema

Use SQLite for MVP.

## stocks

```sql
CREATE TABLE IF NOT EXISTS stocks (
  ticker TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  sector TEXT,
  industry TEXT,
  active INTEGER DEFAULT 1
);
```

## signals

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

## prices

```sql
CREATE TABLE IF NOT EXISTS prices (
  date TEXT NOT NULL,
  ticker TEXT NOT NULL,
  adjusted_close REAL NOT NULL,
  PRIMARY KEY(date, ticker)
);
```

## forward_returns

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

## collection_runs

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

---

# Evaluation Horizons

Calculate forward returns for:

```text
1D
5D
20D
60D
120D
```

Use trading days, not calendar days.

---

# Main Metrics

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

---

# Bias Control

The site should show two modes.

## Raw Mode

Simple average across all collected S&P 500 signals.

## Balanced Mode

Sector-neutral result.

Calculation:

```text
1. Compute metric separately for each GICS sector
2. Average sector results equally
3. Ignore sectors with insufficient sample size
```

This prevents Technology or mega-cap stocks from dominating the results.

---

# Sector Benchmarks

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

---

# Static Site Pages

## Home

Purpose:

```text
Explain the project.
Show latest top-level leaderboard.
Show last updated date.
```

Headline:

```text
Who predicts better: chartists, analysts, or earnings-revision models?
```

---

## Leaderboard

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
```

Default sorting:

```text
60D sector-neutral SPY alpha
```

---

## Source Report

For each source:

```text
Investing Technical Summary
Zacks Rank
Yahoo Analyst Consensus
```

Show performance by signal:

```text
Strong Buy
Buy
Neutral / Hold
Sell
Strong Sell
```

---

## Sector View

Show performance by sector.

Key question:

```text
Does a signal work across sectors, or only in specific sectors?
```

---

## Signal Conflicts

Track cases where sources disagree.

Examples:

```text
Technical Buy + Analyst Sell
Zacks Strong Buy + Technical Strong Sell
Analyst Buy + Zacks Sell
```

Show which source was more correct after 20D, 60D, and 120D.

---

## Data Quality

Show:

```text
last collection time
source success rate
missing tickers
failed tickers
number of signals collected
number of prices collected
```

This page is important because data quality is part of the product.

---

# GitHub Actions Workflow

Run once per US trading day after market close.

File:

```text
.github/workflows/daily.yml
```

Workflow:

```yaml
name: Daily Signal Collection

on:
  schedule:
    - cron: "30 22 * * 1-5"
  workflow_dispatch:

jobs:
  collect:
    runs-on: ubuntu-latest

    permissions:
      contents: write

    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      - name: Install dependencies
        run: pip install -r requirements.txt

      - name: Initialize database
        run: python scripts/init_db.py

      - name: Collect daily signals
        run: python scripts/collect_daily.py

      - name: Compute returns
        run: python scripts/compute_returns.py

      - name: Build static site
        run: python scripts/build_site.py

      - name: Commit updates
        run: |
          git config user.name "signal-league-bot"
          git config user.email "bot@example.com"
          git add data/ docs/
          git commit -m "Daily signal update" || echo "No changes"
          git push
```

---

# Implementation TODO

## Phase 0 — Repo Setup

* [ ] Create GitHub repo
* [ ] Add `README.md`
* [ ] Add `PROJECT_SPEC.md`
* [ ] Add Python project structure
* [ ] Add `requirements.txt`
* [ ] Add `.gitignore`
* [ ] Add `config/sp500.csv`
* [ ] Add basic logging utility

---

## Phase 1 — Database

* [ ] Implement `src/utils/db.py`
* [ ] Implement `scripts/init_db.py`
* [ ] Create SQLite schema
* [ ] Add insert/upsert helpers for stocks
* [ ] Add insert/upsert helpers for prices
* [ ] Add insert/upsert helpers for signals
* [ ] Add collection run tracking
* [ ] Add tests for DB writes

---

## Phase 2 — Universe

* [ ] Implement `src/utils/universe.py`
* [ ] Load S&P 500 CSV
* [ ] Validate required columns
* [ ] Insert stocks into database
* [ ] Add active/inactive flag support
* [ ] Add tests for universe loading

---

## Phase 3 — Normalization

* [ ] Implement `src/utils/normalize.py`
* [ ] Normalize Investing signals
* [ ] Normalize Zacks Rank signals
* [ ] Normalize Yahoo analyst consensus
* [ ] Convert all signals to score `-2` to `2`
* [ ] Add tests for all signal mappings

---

## Phase 4 — Price Data

* [ ] Implement `src/prices/yahoo_prices.py`
* [ ] Fetch adjusted close for S&P 500 tickers
* [ ] Fetch adjusted close for SPY
* [ ] Fetch adjusted close for sector ETFs
* [ ] Store prices in SQLite
* [ ] Handle missing prices
* [ ] Add retry logic
* [ ] Add tests for return calculation using mock prices

---

## Phase 5 — Collectors

Start with 10 tickers:

```text
AAPL
MSFT
NVDA
AMZN
GOOGL
META
TSLA
JPM
XOM
UNH
```

### Investing Collector

* [ ] Implement `src/collectors/investing.py`
* [ ] Fetch technical summary for one ticker
* [ ] Parse raw signal
* [ ] Normalize signal
* [ ] Return structured result
* [ ] Handle request failure
* [ ] Handle missing signal
* [ ] Test on 10 tickers

### Zacks Collector

* [ ] Implement `src/collectors/zacks.py`
* [ ] Fetch Zacks Rank for one ticker
* [ ] Parse rank
* [ ] Normalize rank
* [ ] Return structured result
* [ ] Handle request failure
* [ ] Handle missing rank
* [ ] Test on 10 tickers

### Yahoo Analyst Collector

* [ ] Implement `src/collectors/yahoo.py`
* [ ] Fetch analyst recommendation for one ticker
* [ ] Parse consensus recommendation
* [ ] Normalize recommendation
* [ ] Return structured result
* [ ] Handle missing analyst data
* [ ] Test on 10 tickers

---

## Phase 6 — Daily Collection Script

* [ ] Implement `scripts/collect_daily.py`
* [ ] Load universe
* [ ] Fetch prices
* [ ] Run all collectors
* [ ] Store successful signals
* [ ] Store failures with error messages
* [ ] Record collection run stats
* [ ] Add CLI option: `--limit 10`
* [ ] Add CLI option: `--source investing`
* [ ] Add CLI option: `--date YYYY-MM-DD`

---

## Phase 7 — Forward Return Engine

* [ ] Implement `src/analysis/returns.py`
* [ ] Calculate 1D forward return
* [ ] Calculate 5D forward return
* [ ] Calculate 20D forward return
* [ ] Calculate 60D forward return
* [ ] Calculate 120D forward return
* [ ] Calculate SPY alpha
* [ ] Calculate sector ETF alpha
* [ ] Skip signals without enough future data
* [ ] Store results in `forward_returns`
* [ ] Add tests using fixture price data

---

## Phase 8 — Leaderboard

* [ ] Implement `src/analysis/leaderboard.py`
* [ ] Aggregate by source
* [ ] Aggregate by category
* [ ] Aggregate by signal score
* [ ] Compute hit rate
* [ ] Compute average return
* [ ] Compute median return
* [ ] Compute average alpha
* [ ] Compute sample size
* [ ] Export `data/exports/leaderboard.json`

---

## Phase 9 — Balanced Mode

* [ ] Implement `src/analysis/balanced.py`
* [ ] Aggregate returns by sector first
* [ ] Equal-weight sector results
* [ ] Exclude sectors below minimum sample size
* [ ] Export raw and balanced results separately
* [ ] Add balanced leaderboard JSON

---

## Phase 10 — Conflict Analysis

* [ ] Implement `src/analysis/conflicts.py`
* [ ] Identify same-day ticker signals from multiple sources
* [ ] Find source disagreements
* [ ] Define conflict types
* [ ] Compute which source was directionally correct
* [ ] Export conflict results JSON

---

## Phase 11 — Static Site

* [ ] Implement `src/site/build_static.py`
* [ ] Generate `docs/index.html`
* [ ] Generate `docs/leaderboard.html`
* [ ] Generate `docs/source.html`
* [ ] Generate `docs/sectors.html`
* [ ] Generate `docs/conflicts.html`
* [ ] Generate `docs/data-quality.html`
* [ ] Use simple HTML/CSS first
* [ ] Add table sorting later
* [ ] Add charts later

---

## Phase 12 — GitHub Actions

* [ ] Add `.github/workflows/daily.yml`
* [ ] Run pipeline manually with `workflow_dispatch`
* [ ] Confirm DB updates are committed
* [ ] Confirm `docs/` updates are committed
* [ ] Enable GitHub Pages from `docs/`
* [ ] Add failure logging
* [ ] Add collection success rate to site

---

# MVP Acceptance Criteria

The MVP is complete when:

```text
1. S&P 500 universe loads successfully
2. Prices are stored daily
3. At least one signal source works for 80%+ of S&P 500 tickers
4. Signals are stored with date, ticker, source, score, and price
5. Forward returns are calculated for available horizons
6. Leaderboard JSON is generated
7. Static website is built
8. GitHub Actions runs the full pipeline
9. GitHub Pages displays the latest results
```

---

# Important Implementation Notes

## Do not optimize too early

First priority:

```text
collect reliably
store cleanly
evaluate correctly
```

UI comes later.

## Store raw signals

Always store the raw signal before normalization.

Example:

```text
raw_signal = "#1 Strong Buy"
normalized_signal = "Strong Buy"
score = 2
```

## Store failures

Do not silently ignore failures.

Failure records are useful for the Data Quality page.

## Avoid daily duplicate noise

Use:

```sql
UNIQUE(date, ticker, source)
```

## Keep the project honest

Add disclaimers:

```text
Signal League is not financial advice.
It evaluates historical public signals.
Past performance does not imply future performance.
```

---

# First Codex Task

Start with this instruction:

```text
Create the initial repository structure for Signal League.

Implement:
1. SQLite schema initialization
2. S&P 500 CSV loader
3. Signal normalization utilities
4. Basic test suite for normalization and DB initialization

Do not implement web scraping yet.
Focus on clean structure, database schema, and testable utilities.
```

Then next task:

```text
Implement price data collection using Yahoo Finance-compatible adjusted close data.

Store prices for:
- all tickers in config/sp500.csv
- SPY
- sector ETFs: XLK, XLF, XLV, XLE, XLI, XLY, XLP, XLU, XLB, XLRE, XLC

Add retry handling and logging.
```

Then:

```text
Implement the first signal collector: Investing.com Technical Summary.

Start with 10 tickers only.
Return structured signal objects.
Store successes and failures.
Add collection run statistics.
```
