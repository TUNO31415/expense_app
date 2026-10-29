from services.importers import (
    build_bank_review_rows,
    compute_import_hash,
    detect_decimal_separator,
    detect_delimiter,
    detect_encoding,
    dedupe_rows,
    filter_outgoing_transactions,
    parse_amount,
    parse_date,
    read_csv_rows,
    resolve_category,
    suggest_column_mapping,
)


def test_european_number_and_date_formats():
    assert parse_amount("1.234,56", decimal_sep=",") == 1234.56
    assert parse_amount("1,234.56", decimal_sep=".") == 1234.56
    assert parse_date("12/03/2024", "%d/%m/%Y") == "2024-03-12"
    assert parse_date("2024-03-12") == "2024-03-12"


def test_google_form_amount_and_day_first_dates():
    assert int(round(parse_amount("€500.00", decimal_sep=".") * 100)) == 50000
    assert int(round(parse_amount("€1,000.00", decimal_sep=".") * 100)) == 100000
    assert parse_date("02/01/2025") == "2025-01-02"
    assert parse_date("02-01-2025") == "2025-01-02"


def test_dutch_bank_statement_dates_and_direction_markers():
    rows = [
        {"date": "20261001", "amount": "500,00", "description": "Transfer", "debit_credit": "Af"},
        {"date": "20260929", "amount": "29,17", "description": "Payment received", "debit_credit": "Bij"},
        {"date": "20260929", "amount": "22,84", "description": "Direct debit", "debit_credit": "af"},
    ]

    outgoing, ignored = filter_outgoing_transactions(rows)

    assert parse_date("20261001") == "2026-10-01"
    assert len(outgoing) == 2
    assert ignored == 1
    assert [row["amount_cents"] for row in outgoing] == [50000, 2284]
    assert [row["date"] for row in outgoing] == ["2026-10-01", "2026-09-29"]


def test_resolve_category_normalizes_and_scopes_by_type():
    categories = [
        {"id": 1, "name": "Rent", "type_name": "Fixed Costs"},
        {"id": 5, "name": "Car costs", "type_name": "Fixed Costs"},
        {"id": 2, "name": "Hobbies", "type_name": "Variable Costs"},
        {"id": 3, "name": "Savings", "type_name": "Savings"},
        {"id": 4, "name": "Degiro Investment", "type_name": "Savings"},
    ]

    category, suggestion = resolve_category("1. rent", "Fixed Costs", categories)
    assert category is not None and category["id"] == 1
    assert suggestion == "Rent"

    category, _ = resolve_category("1. Car cost (Fixed)", "Fixed Costs", categories)
    assert category is not None and category["id"] == 5

    category, _ = resolve_category("2. Hobbies (incl Kendo travel)", "Variable Costs", categories)
    assert category is not None and category["id"] == 2

    category, _ = resolve_category("4. Degiro", "Savings", categories)
    assert category is not None and category["id"] == 4

    category, suggestion = resolve_category("Rent", "Variable Costs", categories)
    assert category is None
    assert suggestion == "Hobbies"


def test_resolve_category_rejects_weak_or_ambiguous_matches():
    categories = [
        {"id": 1, "name": "Coffee", "type_name": "Variable Costs"},
        {"id": 2, "name": "Shop", "type_name": "Variable Costs"},
        {"id": 3, "name": "Rent", "type_name": "Fixed Costs"},
    ]

    category, suggestion = resolve_category("Coffee Shop", "Variable Costs", categories)
    assert category is None
    assert suggestion is not None

    category, suggestion = resolve_category("Unrelated", "Fixed Costs", categories)
    assert category is None
    assert suggestion == "Rent"


def test_suggest_google_form_columns_and_ignore_timestamp():
    mapping = suggest_column_mapping(
        ["Timestamp", "Date", "Type", "Category", "Amount", "Description", "Note"],
        {
            "date": ("date",),
            "type": ("type",),
            "category": ("category",),
            "amount": ("amount",),
            "description": ("description",),
            "comments": ("note", "comments"),
        },
    )

    assert mapping == {
        "date": "Date",
        "type": "Type",
        "category": "Category",
        "amount": "Amount",
        "description": "Description",
        "comments": "Note",
    }


def test_detect_delimiter_and_decimal_separator():
    csv_text = "date;type;category;amount;description\n2024-01-01;Food;Groceries;12,50;Milk"
    assert detect_delimiter(csv_text) == ";"
    assert detect_decimal_separator("1.234,56") == ","
    assert detect_decimal_separator("1,234.56") == "."


def test_dutch_statement_headers_map_to_requested_fields():
    csv_text = (
        '"Datum";"Naam / Omschrijving";"Af Bij";"Bedrag (EUR)";"Mededelingen"\n'
        '"20261001";"Counterparty";"Af";"500,00";"Statement memo"\n'
    )

    rows, _, delimiter = read_csv_rows(csv_text.encode("utf-8"))
    mapping = suggest_column_mapping(
        rows[0].keys(),
        {
            "date": ("Datum", "Date"),
            "amount": ("Bedrag (EUR)", "Bedrag", "Amount"),
            "description": ("Naam / Omschrijving",),
            "direction": ("Af Bij", "Af/Bij", "Debit/Credit", "Debit Credit"),
        },
    )

    assert delimiter == ";"
    assert mapping == {
        "date": "Datum",
        "amount": "Bedrag (EUR)",
        "description": "Naam / Omschrijving",
        "direction": "Af Bij",
    }
    assert parse_date(rows[0][mapping["date"]]) == "2026-10-01"
    assert parse_amount(rows[0][mapping["amount"]]) == 500.0
    assert rows[0][mapping["description"]] == "Counterparty"


def test_detect_encoding_handles_utf8_and_latin1():
    utf8_bytes = "café".encode("utf-8")
    latin1_bytes = "café".encode("latin-1")
    assert detect_encoding(utf8_bytes) == "utf-8"
    assert detect_encoding(latin1_bytes) == "latin-1"


def test_hash_and_dedupe_rows():
    rows = [
        {"date": "2024-01-15", "amount_cents": 1234, "description": "Groceries", "reference": "A1"},
        {"date": "2024-01-15", "amount_cents": 1234, "description": "Groceries", "reference": "A1"},
        {"date": "2024-01-16", "amount_cents": 500, "description": "Coffee", "reference": "A2"},
    ]
    unique_rows, skipped = dedupe_rows(rows)
    assert len(unique_rows) == 2
    assert skipped == 1
    assert compute_import_hash("2024-01-15", 1234, "Groceries", "A1") == compute_import_hash("2024-01-15", 1234, "Groceries", "A1")


def test_outgoing_only_filtering():
    rows = [
        {"date": "2024-01-02", "amount": "-12.34", "description": "Groceries", "debit_credit": "debit"},
        {"date": "2024-01-03", "amount": "2000.00", "description": "Salary", "debit_credit": "credit"},
        {"date": "2024-01-04", "amount": "-8.50", "description": "Coffee", "debit_credit": "debit"},
        {"date": "2024-01-05", "amount": "7.25", "description": "Refund", "debit_credit": "credit"},
    ]
    outgoing, ignored = filter_outgoing_transactions(rows)
    assert len(outgoing) == 2
    assert ignored == 2
    assert outgoing[0]["amount_cents"] == 1234
    assert outgoing[1]["amount_cents"] == 850


def test_build_bank_review_rows_applies_rules_and_flags_duplicates():
    csv_rows = [
        {"Datum": "20261001", "Naam": "Albert Heijn 123", "Af Bij": "Af", "Bedrag": "12,50"},
        {"Datum": "20261001", "Naam": "Albert Heijn 123", "Af Bij": "Af", "Bedrag": "12,50"},
        {"Datum": "20261002", "Naam": "Salary", "Af Bij": "Bij", "Bedrag": "2000,00"},
        {"Datum": "20261003", "Naam": "Own savings transfer", "Af Bij": "Af", "Bedrag": "100,00"},
        {"Datum": "20261004", "Naam": "Bike shop", "Af Bij": "Af", "Bedrag": "45,00"},
        {"Datum": "not a date", "Naam": "Broken", "Af Bij": "Af", "Bedrag": "1,00"},
    ]
    mapping = {"date": "Datum", "amount": "Bedrag", "description": "Naam", "direction": "Af Bij"}
    rules = [
        {"keyword": "albert heijn", "category_id": 7, "action": "categorize", "priority": 0},
        {"keyword": "savings transfer", "category_id": None, "action": "ignore", "priority": 0},
    ]
    categories = [{"id": 7, "name": "Groceries", "type_name": "Variable Costs"}]
    stored = {
        ("2026-10-04", 4500): [
            {"id": 9, "date": "2026-10-04", "amount_cents": 4500, "type": "Variable Costs", "category": "Hobbies", "description": "Bike"}
        ]
    }

    result = build_bank_review_rows(csv_rows, mapping, "%Y%m%d", rules, categories, lambda rows: stored)

    assert (result["invalid"], result["ignored_incoming"], result["excluded_by_rules"]) == (1, 1, 1)
    rows = result["rows"]
    assert [row["amount_cents"] for row in rows] == [1250, 1250, 4500]
    assert rows[0]["category_id"] == 7 and rows[0]["rule_keyword"] == "albert heijn"
    assert [row["possible_duplicate"] for row in rows] == [False, True, True]
    assert rows[1]["existing_record"] == "Same transaction appears earlier in this file."
    assert rows[2]["existing_record"].startswith("#9 2026-10-04")
    assert rows[2]["category_id"] is None
