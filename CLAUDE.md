# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

Dependencies are managed with `uv` (Python 3.12+). There is no linter or formatter configured.

```bash
uv sync                                  # install deps (incl. dev group: pytest)
uv run streamlit run app.py              # run the app (or: bash ./run.sh)
uv run pytest                            # all tests
uv run pytest tests/test_db.py           # one file
uv run pytest tests/test_db.py::test_expense_crud_and_df   # one test
```

`pytest.ini` sets `pythonpath = .`, so tests import top-level modules directly (`import db`, `from services import ...`).

## Architecture

Single-user, local Streamlit app backed by SQLite at `data/expenses.db` (gitignored, created on first run by `db.init_db()`, which `app.py` calls). `app.py` is a router: pages are registered explicitly with `st.navigation`/`st.Page` (order, titles and icons live there), so a new file in `pages/` does nothing until it is added. Link between pages with `st.page_link`/`st.switch_page` using the `pages/<file>.py` path. The dark theme is in `.streamlit/config.toml`; `st.set_page_config` is called only in `app.py`.

Layering:
- `db.py` is the only module that touches SQLite. Every helper opens its own short-lived connection via `get_connection()` (foreign keys enabled, `sqlite3.Row` factory) and commits itself; there is no shared connection or ORM. `init_db()` is idempotent (`CREATE TABLE IF NOT EXISTS` + seeding the starter types/categories only when missing).
- `services/` holds logic with no Streamlit dependency: `importers.py` (CSV encoding/delimiter/decimal detection, date and amount parsing, fuzzy category resolution, in-file dedupe), `categorizer.py` (keyword rules), `analytics.py` (pandas aggregations for the dashboard). Keep these UI-free so they stay unit-testable.
- `pages/*.py` are UI: they call `db` for reads/writes and `services` for transformation. Each page starts with `ui.components.page_header(...)`, which also injects the shared CSS and shows queued toasts.
- `ui/` holds the shared UI pieces: `theme.py` (`color_for_type`/`type_color_map` for chart colours keyed by type name, `plotly_layout` for chart styling), `components.py` (`kpi_card`, `empty_state`, `badge_row`, and `category_label_map`, which builds the "Type / Category" labels used by every category dropdown), and `feedback.py`.
- Bank import (`pages/import_data.py`) is a 4-step wizard whose state lives in `st.session_state["bank_*"]` keys; the row building is the pure `services.importers.build_bank_review_rows`.
- `st.data_editor` edits are stored by row position, so tables that save edits (Expenses, Settings) put a nonce in the editor key and bump it after every save or filter change. Otherwise the old edits get applied to whichever rows now sit at those positions.

Data model essentials:
- Two-level taxonomy: `types` → `categories` (each category has one `type_id`); expenses reference only `category_id`. Deleting a type/category is refused if anything still references it.
- Money is stored as integer `amount_cents` (must be > 0; only outgoing spend is stored — bank imports drop incoming transactions and flip signs via `filter_outgoing_transactions`). `get_expenses_df()` converts to float `amount_eur` for display; convert back with `int(round(eur * 100))` on write.
- Dates are stored as ISO `YYYY-MM-DD` text.
- `source` is one of `manual` / `sheet` / `bank` (CHECK constraint).
- Imports: `import_hash` = SHA-256 of `date|amount_cents|description|reference` (UNIQUE). `db.insert_many()` creates an `import_batches` row, skips rows whose hash already exists, and tags inserted rows with `batch_id`, and returns `(inserted, skipped, batch_id)` so a whole import can be undone via `delete_batch()`. The same hash function exists in both `db.py` and `services/importers.py` — keep them identical.
- `bank_profiles` stores saved per-bank CSV settings; `column_mapping` is a JSON string.

Read path: `db.get_expenses_df()` (expenses joined to category + type names) → each page's own `@st.cache_data` loader → on the Dashboard, `analytics.prepare_expense_df()` (parses dates, fills missing type/category, adds `month`/`quarter` columns) → the period bar (`analytics.period_bounds` presets) and the sidebar type/category filters → widgets registered in the `WIDGETS` list in `pages/dashboard.py`, rendered top to bottom in list order (the Customize popover can hide each one).

Caching: the loaders take no arguments, so cached data never invalidates on its own. Finish every DB write with `ui.feedback.after_write(message)`, which queues a toast, calls `st.cache_data.clear()` and reruns. A bare `st.rerun()` leaves pages showing stale data, and an `st.success` right before a rerun is never seen.

Keyword rules (`services/categorizer.match_rule`): case-insensitive substring match on the description. Any matching `ignore` rule wins over categorize rules; among matches of the same kind, the longest keyword wins, then the higher `priority`. During import, ignore matches are excluded. The CSV ("sheet") import only shows rule matches as suggestions and requires a choice per row. The bank wizard pre-selects the matched category and also flags possible duplicates using `find_existing_expense_matches` (same date + amount), which you must review before importing.

Tests in `tests/` point `db.DB_PATH` at a temp file with `monkeypatch` and call `db.init_db()` (see the `temp_db` fixture in `tests/test_db.py`). Use the same pattern for any test that touches the database.
