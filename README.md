# Expense App

A local personal finance dashboard for tracking day-to-day spending, categorizing transactions, importing CSV/bank data, and reviewing trends from a single SQLite-backed app.

## Overview

Expense App is a lightweight Streamlit application designed for single-user local use. It helps you:

- import your monthly bank statement in a guided, reviewable flow
- record, search, and edit expenses
- organize spending into types and categories, with keyword rules that categorize automatically
- see where your money goes this month and over longer periods
- keep everything in a local SQLite database without external infrastructure

Built with Python 3.12+, Streamlit, Pandas, and Plotly, with a dark theme.

## Pages

- **Home**: this month at a glance. Total spent (compared with last month), transaction count, top category, days since the last bank import, spend by type and top 5 categories, and recent transactions.
- **Import**
  - *Bank statement*: a four-step wizard (Upload → Map columns → Review → Done). The encoding, delimiter, and decimal separator are detected automatically. Only outgoing transactions are kept. Keyword rules preselect each row's category, and rows that match an existing expense (same date and amount) are flagged as possible duplicates. Column settings can be saved as a bank profile, and a finished import can be undone in one click.
  - *Historical CSV*: map the columns of a spreadsheet export (e.g. Google Sheets), check the validation issues, and import. Rule matches are only suggestions, so you pick a category for each row.
- **Expenses**: add expenses manually and browse every transaction with date, type/category, text, and source filters. Edit rows inline (changes save automatically), delete selected rows, or download the filtered rows as CSV.
- **Dashboard**: choose a period (3M, 6M, 12M, This year, All time, or a custom range) and filter by type and category in the sidebar. KPI cards sit above a monthly spending trend, a "where your money goes" breakdown, a table of typical spending per category, and a quarterly heatmap. Use **Customize** to show or hide each chart.
- **Settings**: manage types and categories, keyword rules, and saved bank profiles. A type or category that is still in use can't be deleted.

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

- `app.py` — app entry point; registers the pages with `st.navigation`
- `pages/` — Home (month overview), Import (bank statement stepper and historical CSV), Expenses, Dashboard, and Settings
- `ui/` — shared theme, chart colours, cards, and toast feedback helpers
- `.streamlit/config.toml` — the dark theme
- `db.py` — database schema, seed data, and local SQLite helpers
- `services/` — import, analytics, and categorization logic
- `tests/` — automated checks for the database, importer, analytics, and categorization rules
- `data/` — local runtime data, including the SQLite database

## Data and persistence

The database is created automatically on first launch at:

```text
data/expenses.db
```

It is seeded with a starter set of types and categories. Amounts are stored as whole cents, and only spending (outgoing money) is recorded. Each imported row gets a hash of its date, amount, description, and reference, so importing the same statement twice skips rows that are already there.

This project is intended for a single-user local workflow. There is no remote database or cloud sync layer.

## Keyword rules

Category and ignore rules match keywords anywhere in a transaction description without case sensitivity. Matching behavior works as follows:

- when multiple category rules match, the longest keyword wins
- if the keyword lengths are equal, the rule with the higher priority wins
- an ignore rule wins over any category rule, regardless of priority

During imports:

- Google Sheets CSV imports show matching category rules as suggestions and require a selection per row
- bank statement imports preselect the matching category for review, while still allowing edits
- ignore rules exclude matching rows from either import workflow

## Testing

Run the project tests with:

```bash
uv run pytest
```

## License

This project is for local personal use and is not currently configured with a formal public license.
