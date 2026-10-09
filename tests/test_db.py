import sqlite3
from pathlib import Path

import pandas as pd
import pytest

import db


@pytest.fixture
def temp_db(monkeypatch, tmp_path):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "expenses.db")
    db.init_db()
    return tmp_path / "expenses.db"


def test_init_db_creates_seed_data_and_schema(temp_db):
    with sqlite3.connect(temp_db) as conn:
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()
    table_names = {name for (name,) in tables}
    assert {"types", "categories", "expenses", "import_batches", "category_rules", "bank_profiles"}.issubset(table_names)

    types = db.list_types()
    categories = db.list_categories()
    assert any(item["name"] == "Fixed Costs" for item in types)
    assert any(item["name"] == "Eating Out / Coffee" for item in categories)


def test_expense_crud_and_df(temp_db):
    category = db.get_category_by_name("Rent")
    assert category is not None

    expense_id = db.add_expense(
        date="2026-10-02",
        category_id=category["id"],
        amount_cents=1234,
        description="Apartment rent",
        comments="Monthly",
        source="manual",
    )
    assert expense_id is not None

    df = db.get_expenses_df()
    assert len(df) == 1
    assert df.iloc[0]["date"] == "2026-10-02"
    assert df.iloc[0]["amount_eur"] == 12.34
    assert df.iloc[0]["category"] == "Rent"

    db.update_expense(
        expense_id,
        date="2026-10-03",
        category_id=category["id"],
        amount_cents=1500,
        description="Updated rent",
        comments="Updated",
        source="manual",
    )
    updated = db.get_expenses_df()
    assert updated.iloc[0]["date"] == "2026-10-03"
    assert updated.iloc[0]["amount_eur"] == 15.0
    assert updated.iloc[0]["description"] == "Updated rent"

    db.delete_expense(expense_id)
    assert db.get_expenses_df().empty


def test_insert_many_skips_duplicates_and_delete_batch(temp_db):
    category = db.get_category_by_name("Groceries")
    rows = [
        {
            "date": "2026-10-01",
            "category_id": category["id"],
            "amount_cents": 1250,
            "description": "Fresh market",
            "comments": "Weekend",
            "source": "sheet",
            "reference": "ref-1",
        },
        {
            "date": "2026-10-01",
            "category_id": category["id"],
            "amount_cents": 1250,
            "description": "Fresh market",
            "comments": "Weekend",
            "source": "sheet",
            "reference": "ref-1",
        },
    ]

    inserted, skipped = db.insert_many(rows)
    assert inserted == 1
    assert skipped == 1

    batch_id = db.get_latest_batch_id()
    assert batch_id is not None
    db.delete_batch(batch_id)
    assert db.get_expenses_df().empty


def test_bank_import_stores_statement_fields_only(temp_db):
    category = db.get_category_by_name("Groceries")
    assert category is not None

    inserted, skipped = db.insert_many(
        [
            {
                "date": "2026-10-01",
                "category_id": category["id"],
                "amount_cents": 50000,
                "description": "Statement memo",
                "source": "bank",
            }
        ],
        source="bank",
    )

    assert (inserted, skipped) == (1, 0)
    with sqlite3.connect(temp_db) as conn:
        row = conn.execute(
            "SELECT date, category_id, amount_cents, description, comments, source "
            "FROM expenses"
        ).fetchone()

    assert row == ("2026-10-01", category["id"], 50000, "Statement memo", None, "bank")


def test_find_existing_expense_matches_legacy_bank_reference(temp_db):
    category = db.get_category_by_name("Groceries")
    assert category is not None
    db.insert_many(
        [
            {
                "date": "2026-10-01",
                "category_id": category["id"],
                "amount_cents": 50000,
                "description": "Previous Mededelingen description",
                "source": "bank",
                "reference": "legacy-reference",
            }
        ],
        source="bank",
    )

    matches = db.find_existing_expense_matches(
        [
            {
                "date": "2026-10-01",
                "amount_cents": 50000,
                "description": "Merchant name",
            }
        ]
    )

    records = matches[("2026-10-01", 50000)]
    assert len(records) == 1
    assert records[0]["description"] == "Previous Mededelingen description"
    assert records[0]["type"] == category["type_name"]
    assert records[0]["category"] == category["name"]


def test_type_and_category_crud(temp_db):
    new_type = db.add_type("Travel")
    new_category = db.add_category("Flights", new_type["id"])

    assert any(item["name"] == "Travel" for item in db.list_types())
    assert any(item["name"] == "Flights" for item in db.list_categories())

    db.update_category(new_category["id"], name="Air Travel", type_id=new_type["id"])
    updated = db.get_category_by_name("Air Travel")
    assert updated is not None

    db.delete_category(updated["id"])
    assert db.get_category_by_name("Air Travel") is None


def test_rules_and_bank_profiles(temp_db):
    category = db.get_category_by_name("Eating Out / Coffee")
    assert category is not None
    rule_id = db.add_rule(keyword="pizza", category_id=category["id"], action="categorize", priority=10)
    assert rule_id is not None
    rules = db.list_rules()
    assert any(r["keyword"] == "pizza" for r in rules)

    profile_id = db.add_bank_profile(
        name="Demo bank",
        delimiter=";",
        decimal_sep=",",
        date_format="%d/%m/%Y",
        column_mapping={"date": "Date", "amount": "Amount", "description": "Description"},
    )
    assert profile_id is not None
    assert any(item["name"] == "Demo bank" for item in db.list_bank_profiles())
