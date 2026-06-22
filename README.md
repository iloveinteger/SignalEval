# Signal League

Signal League evaluates public investment signals against future returns.

The MVP question is:

```text
Do Investing.com public signals outperform a random baseline?
```

The current MVP focuses on three signal sources:

1. Investing.com Technical Analysis
2. Investing.com Financial / Analyst Summary
3. Random Baseline control group

Yahoo Finance analyst consensus and Zacks Rank are future extensions, not MVP
sources.

Signal League is not financial advice. It evaluates historical public signals,
and past performance does not imply future performance.

## Current Parser Coverage

The offline Investing.com parser currently works from saved HTML samples only.
It does not make live HTTP requests.

- Technical parser: extracts the selected overall technical signal and the daily
  signal.
- Financial / analyst parser: extracts analyst consensus, analyst count, price
  target average, price target upside, and financial ratios.
- Valuation fields may be locked or unavailable in saved pages.

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

## Initialize Database

```powershell
python scripts/init_db.py
```
