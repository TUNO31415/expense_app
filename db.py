from __future__ import annotations

import hashlib
import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterable

import pandas as pd

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "expenses.db"


def ensure_db_dir() -> None:
    """Ensure the database directory exists."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)


@contextmanager
def get_connection(db_path: str | Path | None = None):
    """Open a SQLite connection and enable foreign keys for every session."""
    target = Path(db_path) if db_path is not None else DB_PATH
    ensure_db_dir()
    conn = sqlite3.connect(target)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
    finally:
        conn.close()


def init_db() -> None:
    """Initialize the SQLite schema and seed data for the first run."""
    ensure_db_dir()
    with get_connection() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS types (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL
            );

            CREATE TABLE IF NOT EXISTS categories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                type_id INTEGER NOT NULL,
                FOREIGN KEY(type_id) REFERENCES types(id)
            );

            CREATE TABLE IF NOT EXISTS expenses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL,
                category_id INTEGER NOT NULL,
                amount_cents INTEGER NOT NULL CHECK(amount_cents > 0),
                description TEXT,
                comments TEXT,
                source TEXT CHECK(source IN ('manual','sheet','bank')) NOT NULL,
                import_hash TEXT UNIQUE,
                batch_id INTEGER,
                FOREIGN KEY(category_id) REFERENCES categories(id),
                FOREIGN KEY(batch_id) REFERENCES import_batches(id)
            );

            CREATE INDEX IF NOT EXISTS idx_expenses_date ON expenses(date);
            CREATE INDEX IF NOT EXISTS idx_expenses_category_id ON expenses(category_id);

            CREATE TABLE IF NOT EXISTS import_batches (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                filename TEXT,
                source TEXT,
                imported_at TEXT DEFAULT CURRENT_TIMESTAMP,
                row_count INTEGER DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS category_rules (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                keyword TEXT NOT NULL,
                category_id INTEGER,
                action TEXT CHECK(action IN ('categorize','ignore')) NOT NULL DEFAULT 'categorize',
                priority INTEGER NOT NULL DEFAULT 0,
                FOREIGN KEY(category_id) REFERENCES categories(id)
            );

            CREATE TABLE IF NOT EXISTS bank_profiles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                delimiter TEXT,
                decimal_sep TEXT,
                date_format TEXT,
                column_mapping TEXT
            );
            """
        )
        _seed_types_and_categories(conn)
        conn.commit()


def _seed_types_and_categories(conn: sqlite3.Connection) -> None:
    """Populate the starter taxonomy only the first time."""
    seed_types = {
        "Fixed Costs": ["Rent", "Utilities", "Insurance", "Car costs", "Healthcare"],
        "Variable Costs": ["Transportation", "Groceries", "Necessities", "Eating Out / Coffee", "Shopping", "Subscription", "Entertainment", "Hobbies"],
        "One time Costs": ["Gifts", "Travel", "Other"],
        "Savings": ["Savings", "Degiro Investment"],
    }

    for type_name, category_names in seed_types.items():
        type_row = conn.execute("SELECT id FROM types WHERE name = ?", (type_name,)).fetchone()
        if type_row is None:
            cursor = conn.execute("INSERT INTO types (name) VALUES (?)", (type_name,))
            type_id = cursor.lastrowid
        else:
            type_id = type_row["id"]

        for category_name in category_names:
            existing = conn.execute(
                "SELECT id FROM categories WHERE name = ?",
                (category_name,),
            ).fetchone()
            if existing is None:
                conn.execute(
                    "INSERT INTO categories (name, type_id) VALUES (?, ?)",
                    (category_name, type_id),
                )


def _row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    return dict(row) if row is not None else None


def add_type(name: str) -> dict[str, Any]:
    """Create a type if it does not already exist."""
    cleaned_name = name.strip()
    with get_connection() as conn:
        existing = conn.execute("SELECT id, name FROM types WHERE name = ?", (cleaned_name,)).fetchone()
        if existing is not None:
            return dict(existing)
        cursor = conn.execute("INSERT INTO types (name) VALUES (?)", (cleaned_name,))
        conn.commit()
        return {"id": cursor.lastrowid, "name": cleaned_name}


def update_type(type_id: int, name: str) -> None:
    """Rename a type."""
    with get_connection() as conn:
        conn.execute("UPDATE types SET name = ? WHERE id = ?", (name.strip(), type_id))
        conn.commit()


def delete_type(type_id: int) -> bool:
    """Delete an unused type."""
    with get_connection() as conn:
        cursor = conn.execute(
            "DELETE FROM types WHERE id = ? AND NOT EXISTS (SELECT 1 FROM categories WHERE type_id = ?)",
            (type_id, type_id),
        )
        conn.commit()
        return cursor.rowcount > 0


def list_types() -> list[dict[str, Any]]:
    """Return all types in name order."""
    with get_connection() as conn:
        rows = conn.execute("SELECT id, name FROM types ORDER BY name").fetchall()
        return [dict(row) for row in rows]


def add_category(name: str, type_id: int) -> dict[str, Any]:
    """Create a category in the given type."""
    cleaned_name = name.strip()
    with get_connection() as conn:
        existing = conn.execute("SELECT id, name, type_id FROM categories WHERE name = ?", (cleaned_name,)).fetchone()
        if existing is not None:
            return dict(existing)
        cursor = conn.execute(
            "INSERT INTO categories (name, type_id) VALUES (?, ?)",
            (cleaned_name, type_id),
        )
        conn.commit()
        return {"id": cursor.lastrowid, "name": cleaned_name, "type_id": type_id}


def update_category(category_id: int, name: str | None = None, type_id: int | None = None) -> None:
    """Update the name and/or parent type for a category."""
    updates: list[str] = []
    params: list[Any] = []
    if name is not None:
        updates.append("name = ?")
        params.append(name.strip())
    if type_id is not None:
        updates.append("type_id = ?")
        params.append(type_id)
    if not updates:
        return
    params.append(category_id)
    with get_connection() as conn:
        conn.execute(f"UPDATE categories SET {', '.join(updates)} WHERE id = ?", tuple(params))
        conn.commit()


def delete_category(category_id: int) -> bool:
    """Delete a category only when it has no expenses assigned."""
    with get_connection() as conn:
        cursor = conn.execute(
            "DELETE FROM categories WHERE id = ? AND NOT EXISTS (SELECT 1 FROM expenses WHERE category_id = ?)",
            (category_id, category_id),
        )
        conn.commit()
        return cursor.rowcount > 0


def list_categories() -> list[dict[str, Any]]:
    """Return category rows joined with the parent type."""
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT c.id, c.name, c.type_id, t.name AS type_name
            FROM categories c
            LEFT JOIN types t ON t.id = c.type_id
            ORDER BY t.name, c.name
            """
        ).fetchall()
        return [dict(row) for row in rows]


def get_category_by_name(category_name: str) -> dict[str, Any] | None:
    """Look up a category by its name."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT c.id, c.name, c.type_id, t.name AS type_name FROM categories c LEFT JOIN types t ON t.id = c.type_id WHERE c.name = ?",
            (category_name,),
        ).fetchone()
        return dict(row) if row is not None else None


def add_rule(keyword: str, category_id: int | None = None, action: str = "categorize", priority: int = 0) -> int:
    """Create a categorization rule."""
    with get_connection() as conn:
        cursor = conn.execute(
            "INSERT INTO category_rules (keyword, category_id, action, priority) VALUES (?, ?, ?, ?)",
            (keyword.strip(), category_id, action, priority),
        )
        conn.commit()
        return int(cursor.lastrowid)


def list_rules() -> list[dict[str, Any]]:
    """Return all rules with their category names."""
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT r.id, r.keyword, r.category_id, r.action, r.priority, c.name AS category_name
            FROM category_rules r
            LEFT JOIN categories c ON c.id = r.category_id
            ORDER BY r.priority DESC, LENGTH(r.keyword) DESC, r.keyword
            """
        ).fetchall()
        return [dict(row) for row in rows]


def add_bank_profile(
    name: str,
    delimiter: str,
    decimal_sep: str,
    date_format: str,
    column_mapping: dict[str, Any],
) -> int:
    """Create or replace a saved bank import profile."""
    with get_connection() as conn:
        cursor = conn.execute(
            "INSERT INTO bank_profiles (name, delimiter, decimal_sep, date_format, column_mapping) VALUES (?, ?, ?, ?, ?) ON CONFLICT(name) DO UPDATE SET delimiter = excluded.delimiter, decimal_sep = excluded.decimal_sep, date_format = excluded.date_format, column_mapping = excluded.column_mapping",
            (name, delimiter, decimal_sep, date_format, json.dumps(column_mapping)),
        )
        conn.commit()
        if cursor.lastrowid:
            return int(cursor.lastrowid)
        existing = conn.execute("SELECT id FROM bank_profiles WHERE name = ?", (name,)).fetchone()
        return int(existing["id"]) if existing is not None else 0


def list_bank_profiles() -> list[dict[str, Any]]:
    """Return saved bank import profiles."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT id, name, delimiter, decimal_sep, date_format, column_mapping FROM bank_profiles ORDER BY name"
        ).fetchall()
        records: list[dict[str, Any]] = []
        for row in rows:
            record = dict(row)
            record["column_mapping"] = json.loads(record["column_mapping"]) if record["column_mapping"] else {}
            records.append(record)
        return records


def get_existing_import_hashes() -> set[str]:
    """Return all import hashes already stored in the database."""
    with get_connection() as conn:
        rows = conn.execute("SELECT import_hash FROM expenses WHERE import_hash IS NOT NULL").fetchall()
        return {row["import_hash"] for row in rows}


def find_existing_expense_matches(
    rows: Iterable[dict[str, Any]],
) -> dict[tuple[str, int], list[dict[str, Any]]]:
    """Find stored expenses matching imported date and amount for user review."""
    match_keys = {
        (
            str(row["date"]),
            int(row["amount_cents"]),
        )
        for row in rows
    }
    matches: dict[tuple[str, int], list[dict[str, Any]]] = {}

    with get_connection() as conn:
        for date, amount_cents in match_keys:
            records = conn.execute(
                """
                SELECT e.id, e.date, e.amount_cents,
                       COALESCE(e.description, '') AS description,
                       c.name AS category, t.name AS type
                FROM expenses e
                LEFT JOIN categories c ON c.id = e.category_id
                LEFT JOIN types t ON t.id = c.type_id
                                WHERE e.date = ? AND e.amount_cents = ?
                ORDER BY e.id
                """,
                                (date, amount_cents),
            ).fetchall()
            if records:
                                matches[(date, amount_cents)] = [dict(record) for record in records]

    return matches


def add_expense(
    *,
    date: str,
    category_id: int,
    amount_cents: int,
    description: str | None = None,
    comments: str | None = None,
    source: str = "manual",
    import_hash: str | None = None,
    batch_id: int | None = None,
) -> int:
    """Insert a single expense."""
    with get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO expenses (date, category_id, amount_cents, description, comments, source, import_hash, batch_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (date, category_id, amount_cents, description, comments, source, import_hash, batch_id),
        )
        conn.commit()
        return int(cursor.lastrowid)


def update_expense(
    expense_id: int,
    *,
    date: str | None = None,
    category_id: int | None = None,
    amount_cents: int | None = None,
    description: str | None = None,
    comments: str | None = None,
    source: str | None = None,
) -> None:
    """Update an existing expense."""
    updates: list[str] = []
    params: list[Any] = []
    if date is not None:
        updates.append("date = ?")
        params.append(date)
    if category_id is not None:
        updates.append("category_id = ?")
        params.append(category_id)
    if amount_cents is not None:
        updates.append("amount_cents = ?")
        params.append(amount_cents)
    if description is not None:
        updates.append("description = ?")
        params.append(description)
    if comments is not None:
        updates.append("comments = ?")
        params.append(comments)
    if source is not None:
        updates.append("source = ?")
        params.append(source)
    if not updates:
        return
    params.append(expense_id)
    with get_connection() as conn:
        conn.execute(f"UPDATE expenses SET {', '.join(updates)} WHERE id = ?", tuple(params))
        conn.commit()


def delete_expense(expense_id: int) -> bool:
    """Delete a single expense by ID."""
    with get_connection() as conn:
        cursor = conn.execute("DELETE FROM expenses WHERE id = ?", (expense_id,))
        conn.commit()
        return cursor.rowcount > 0


def get_expenses_df() -> pd.DataFrame:
    """Fetch expenses joined with category and type names as a DataFrame."""
    with get_connection() as conn:
        query = """
            SELECT e.id, e.date, t.name AS type, c.name AS category,
                   CAST(e.amount_cents AS REAL) / 100.0 AS amount_eur,
                   e.description, e.comments, e.source,
                   e.category_id, e.amount_cents
            FROM expenses e
            LEFT JOIN categories c ON c.id = e.category_id
            LEFT JOIN types t ON t.id = c.type_id
            ORDER BY e.date DESC, e.id DESC
        """
        df = pd.read_sql_query(query, conn)
    return df


def compute_import_hash(date: str, amount_cents: int, description: str | None, reference: str | None = None) -> str:
    """Create a deterministic import hash for deduplication."""
    normalized_description = (description or "").strip()
    payload = f"{date}|{amount_cents}|{normalized_description}|{reference or ''}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def insert_many(rows: Iterable[dict[str, Any]], source: str = "sheet") -> tuple[int, int, int]:
    """Insert rows in a single batch, skipping duplicate hashes; return (inserted, skipped, batch_id)."""
    row_list = list(rows)
    with get_connection() as conn:
        batch_cursor = conn.execute(
            "INSERT INTO import_batches (filename, source, imported_at, row_count) VALUES (?, ?, datetime('now'), 0)",
            (None, source),
        )
        batch_id = int(batch_cursor.lastrowid)
        inserted = 0
        skipped = 0

        for row in row_list:
            category_id = row["category_id"]
            date = row["date"]
            amount_cents = int(row["amount_cents"])
            description = row.get("description")
            comments = row.get("comments")
            row_source = row.get("source", source)
            reference = row.get("reference")
            import_hash = row.get("import_hash") or compute_import_hash(date, amount_cents, description, reference)

            existing = conn.execute(
                "SELECT id FROM expenses WHERE import_hash = ?",
                (import_hash,),
            ).fetchone()
            if existing is not None:
                skipped += 1
                continue

            conn.execute(
                """
                INSERT INTO expenses (date, category_id, amount_cents, description, comments, source, import_hash, batch_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (date, category_id, amount_cents, description, comments, row_source, import_hash, batch_id),
            )
            inserted += 1

        conn.execute("UPDATE import_batches SET row_count = ? WHERE id = ?", (inserted, batch_id))
        conn.commit()
        return inserted, skipped, batch_id


def delete_batch(batch_id: int) -> bool:
    """Delete a full import batch and all associated expenses."""
    with get_connection() as conn:
        cursor = conn.execute("DELETE FROM expenses WHERE batch_id = ?", (batch_id,))
        conn.execute("DELETE FROM import_batches WHERE id = ?", (batch_id,))
        conn.commit()
        return cursor.rowcount >= 0


def get_latest_batch_id() -> int | None:
    """Return the most recent import batch ID."""
    with get_connection() as conn:
        row = conn.execute("SELECT MAX(id) AS latest_id FROM import_batches").fetchone()
        return int(row["latest_id"]) if row and row["latest_id"] is not None else None


def get_latest_import_time(source: str | None = "bank") -> str | None:
    """Return the UTC timestamp of the most recent non-empty import, optionally for one source."""
    query = "SELECT MAX(imported_at) AS latest FROM import_batches WHERE row_count > 0"
    params: tuple[Any, ...] = ()
    if source is not None:
        query += " AND source = ?"
        params = (source,)
    with get_connection() as conn:
        row = conn.execute(query, params).fetchone()
        return row["latest"] if row is not None else None


def delete_rule(rule_id: int) -> bool:
    """Delete a keyword rule."""
    with get_connection() as conn:
        cursor = conn.execute("DELETE FROM category_rules WHERE id = ?", (rule_id,))
        conn.commit()
        return cursor.rowcount > 0


def delete_bank_profile(profile_id: int) -> bool:
    """Delete a saved bank import profile."""
    with get_connection() as conn:
        cursor = conn.execute("DELETE FROM bank_profiles WHERE id = ?", (profile_id,))
        conn.commit()
        return cursor.rowcount > 0
