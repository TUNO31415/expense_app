# Expense Tracker

A local expense tracker built with Python and Streamlit for managing expenses, imports, category rules, and spending summaries from a single SQLite-backed dashboard.

## Features

- Manual expense entry and editing
- Type and category management
- Keyword-based categorization and ignore rules
- CSV import review for historical data
- Bank statement review flow with editable mapping
- Dashboard summaries and simple trend analysis
- Local SQLite storage in `data/expenses.db`

## Project structure

- `app.py` — app entry point and landing page
- `pages/` — Streamlit pages for Dashboard, Expenses, Import, and Categories
- `db.py` — database schema, seed data, and local SQLite helpers
- `services/` — import, analytics, and categorization logic
- `tests/` — automated checks for the database, imports, and categorizer

## Setup

This project uses `uv` for dependency management and runtime execution.

### Install dependencies

From the project root:

```bash
uv sync
```

If the environment is not already created, `uv sync` will create it automatically.

### Windows PowerShell

```powershell
cd "C:\Users\PC User\Documents\projects\expense_app"
uv sync
uv run streamlit run app.py
```

### macOS / Linux / Git Bash

```bash
cd expense_app
uv sync
uv run streamlit run app.py
```

## Run the app

Start the app with:

```bash
uv run streamlit run app.py
```

The project also includes a launcher script:

```bash
bash ./run.sh
```

This script creates a local `.venv` if needed and then runs the app. It is most convenient in Bash-based shells such as Git Bash or WSL. On PowerShell, prefer `uv run streamlit run app.py` directly.

## Keyword rules

Rules match keywords anywhere in a transaction description, without case sensitivity. When multiple category rules match, the longest keyword wins; the larger priority number wins only when the matching keywords are the same length. A matching ignore rule suppresses the transaction regardless of category rule priority.

During a Google Sheets CSV import, matching category rules appear as suggestions and must be selected per row to replace the CSV category. During a bank statement import, matching category rules preselect the type and category for review; those selections remain editable. Ignore rules exclude matching rows from either import.

## Data and persistence

The database is created automatically on first launch at:

```text
data/expenses.db
```

This is a single-user local project, so there is no external cloud service or database setup required.

## Tests

Run the project tests with:

```bash
uv run pytest
```
