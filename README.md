# Expense App

A local personal finance dashboard for tracking day-to-day spending, categorizing transactions, importing CSV/bank data, and reviewing trends from a single SQLite-backed app.

## Overview

Expense App is a lightweight Streamlit application designed for single-user local use. It helps you:

- record and edit expenses manually
- manage expense types and categories
- apply keyword-based categorization rules
- review imported CSV and bank data before committing it
- see dashboard summaries and simple trend views
- keep everything in a local SQLite database without external infrastructure

## Features

- Manual expense entry, editing, and deletion
- Type and category management
- Keyword-based category matching and ignore rules
- CSV import review for historical data
- Bank statement import review with editable mapping
- Dashboard summaries and simple trend analysis
- Local persistence in `data/expenses.db`
- built with Python 3.12+, Streamlit, Pandas, and Plotly

## Requirements

- Python 3.12 or newer
- `uv` for dependency management and running the app

## Quick start

From the project root, install dependencies:

```bash
uv sync
```

Then start the app:

```bash
uv run streamlit run app.py
```

### Windows PowerShell

```powershell
# Run these commands from the repository directory.
uv sync
uv run streamlit run app.py
```

### macOS / Linux / Git Bash

```bash
cd expense_app
uv sync
uv run streamlit run app.py
```

The repository also includes a helper script:

```bash
bash ./run.sh
```

This script creates a local `.venv` if needed and then launches the app. On PowerShell, `uv run streamlit run app.py` is usually the simplest option.

## Project structure

- `app.py` — app entry point and landing page
- `pages/` — Streamlit pages for Dashboard, Expenses, Import, and Categories
- `db.py` — database schema, seed data, and local SQLite helpers
- `services/` — import, analytics, and categorization logic
- `src/` — supporting application logic and helpers
- `tests/` — automated checks for the database, importer, and categorization rules
- `data/` — local runtime data, including the SQLite database

## Data and persistence

The database is created automatically on first launch at:

```text
data/expenses.db
```

This project is intended for a single-user local workflow. There is no remote database or cloud sync layer.

## Keyword rules

Category and ignore rules match keywords anywhere in a transaction description without case sensitivity. Matching behavior works as follows:

- when multiple category rules match, the longest keyword wins
- if the keyword lengths are equal, the rule with the higher priority wins
- an ignore rule suppresses the transaction regardless of category priority

During imports:

- Google Sheets CSV imports show matching category rules as suggestions and require a selection per row
- bank statement imports preselect the matching type and category for review, while still allowing edits
- ignore rules exclude matching rows from either import workflow

## Testing

Run the project tests with:

```bash
uv run pytest
```

## License

This project is for local personal use and is not currently configured with a formal public license.
