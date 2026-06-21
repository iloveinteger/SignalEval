# Signal League

Signal League is a public investment signal performance tracker. It records
public stock signals, stores them cleanly, and evaluates them against future
returns.

This repository currently contains the initial infrastructure slice:

- SQLite schema initialization
- S&P 500 universe CSV loading
- Signal normalization utilities
- Focused pytest coverage

Signal League is not financial advice. It evaluates historical public signals,
and past performance does not imply future performance.

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
