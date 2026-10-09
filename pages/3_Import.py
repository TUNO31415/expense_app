from __future__ import annotations

import hashlib
import io

import pandas as pd
import streamlit as st

from db import (
    add_bank_profile,
    delete_batch,
    find_existing_expense_matches,
    get_latest_batch_id,
    insert_many,
    list_bank_profiles,
    list_categories,
    list_rules,
    list_types,
)
from services.categorizer import match_rule
from services.importers import (
    detect_decimal_separator,
    detect_delimiter,
    detect_encoding,
    filter_outgoing_transactions,
    parse_amount,
    parse_date,
    read_csv_rows,
    resolve_category,
    suggest_column_mapping,
)


@st.cache_data
def _preview_csv(uploaded_file: bytes) -> tuple[pd.DataFrame, str, str]:
    """Parse a CSV upload into a dataframe preview while detecting encoding and delimiter."""
    enc = detect_encoding(uploaded_file)
    text = uploaded_file.decode(enc)
    delimiter = detect_delimiter(text)
    df = pd.read_csv(io.StringIO(text), sep=delimiter, dtype=str)
    return df, enc, delimiter


def _map_column_options(df: pd.DataFrame) -> list[str]:
    """Return the available CSV column names for mapping."""
    return list(df.columns)


def render_historical_import() -> None:
    """Render the Google Sheets CSV import tab."""
    st.subheader("Historical data (Google Sheets CSV)")
    uploaded = st.file_uploader("Upload a CSV file", type=["csv"])
    if uploaded is None:
        return

    raw = uploaded.getvalue()
    upload_key = hashlib.sha256(raw).hexdigest()[:12]
    preview_df, enc, delimiter = _preview_csv(raw)
    st.caption(f"Detected encoding: {enc} • delimiter: {delimiter}")
    st.dataframe(preview_df.head(10), use_container_width=True)

    columns = _map_column_options(preview_df)
    if not columns:
        st.warning("No columns were detected in the uploaded CSV.")
        return

    column_mapping = suggest_column_mapping(
        columns,
        {
            "date": ("date",),
            "type": ("type",),
            "category": ("category",),
            "amount": ("amount",),
            "description": ("description",),
            "comments": ("note", "comments"),
        },
    )
    date_col = st.selectbox(
        "Date column", options=columns,
        index=columns.index(column_mapping["date"]) if column_mapping["date"] is not None else None,
    )
    type_col = st.selectbox(
        "Type column", options=columns,
        index=columns.index(column_mapping["type"]) if column_mapping["type"] is not None else None,
    )
    category_col = st.selectbox(
        "Category column", options=columns,
        index=columns.index(column_mapping["category"]) if column_mapping["category"] is not None else None,
    )
    amount_col = st.selectbox(
        "Amount column", options=columns,
        index=columns.index(column_mapping["amount"]) if column_mapping["amount"] is not None else None,
    )
    description_col = st.selectbox(
        "Description column", options=columns,
        index=columns.index(column_mapping["description"]) if column_mapping["description"] is not None else None,
    )
    comments_col = st.selectbox(
        "Comments / Note column", options=columns,
        index=columns.index(column_mapping["comments"]) if column_mapping["comments"] is not None else None,
    )

    types_by_name = {item["name"].casefold(): item for item in list_types()}
    categories = list_categories()
    categories_by_id = {int(item["id"]): item for item in categories}
    rules = list_rules()

    validation_rows: list[dict] = []
    issues: list[str] = []
    ignored_by_rules = 0

    for _, row in preview_df.iterrows():
        try:
            parsed_date = parse_date(row.get(date_col))
        except ValueError:
            issues.append(f"Date invalid: {row.get(date_col)}")
            continue

        try:
            parsed_amount = parse_amount(row.get(amount_col), decimal_sep=".")
        except ValueError:
            issues.append(f"Amount invalid: {row.get(amount_col)}")
            continue

        type_name = str(row.get(type_col) or "").strip()
        category_name = str(row.get(category_col) or "").strip()
        description = row.get(description_col)
        rule_match = match_rule(str(description or ""), rules)
        if rule_match is not None and rule_match.action == "ignore":
            ignored_by_rules += 1
            continue

        rule_category = (
            categories_by_id.get(rule_match.category_id)
            if rule_match is not None and rule_match.category_id is not None
            else None
        )
        existing_type = types_by_name.get(type_name.casefold())
        existing_category = None
        suggested_category = None
        if existing_type is not None and category_name:
            existing_category, suggested_category = resolve_category(
                category_name, existing_type["name"], categories
            )

        if rule_category is None and (not type_name or not category_name):
            issues.append(f"Missing type/category for row: {row.to_dict()}")
            continue
        if rule_category is None and existing_type is None:
            issues.append(f"Unknown type: {type_name}")
            continue
        if rule_category is None and existing_category is None:
            if suggested_category:
                issues.append(
                    f"Uncertain category '{category_name}' for {existing_type['name']}; "
                    f"closest match: {suggested_category}"
                )
            else:
                issues.append(f"Unknown category: {category_name} for {existing_type['name']}")
            continue

        validation_rows.append(
            {
                "date": parsed_date,
                "type": existing_type["name"] if existing_type else type_name,
                "category": existing_category["name"] if existing_category else category_name,
                "amount_cents": int(round(parsed_amount * 100)),
                "description": description,
                "comments": row.get(comments_col),
                "category_id": existing_category["id"] if existing_category else None,
                "rule_category_id": rule_category["id"] if rule_category else None,
                "rule_suggestion": (
                    f"{rule_category['type_name']} / {rule_category['name']}"
                    if rule_category else ""
                ),
                "use_rule": False,
            }
        )

    st.caption(f"{ignored_by_rules} row(s) excluded by keyword ignore rules.")
    if issues:
        st.warning("Preview found validation issues. Fix the CSV or map unknown values before importing.")
        st.write(issues[:20])

    if validation_rows:
        preview_rows = [
            {
                "date": item["date"],
                "CSV type": item["type"],
                "CSV category": item["category"],
                "Rule suggestion": item["rule_suggestion"] or "",
                "Use rule suggestion": item["use_rule"],
                "amount_cents": item["amount_cents"],
                "description": item["description"],
                "comments": item["comments"],
            }
            for item in validation_rows
        ]
        edited_preview = st.data_editor(
            pd.DataFrame(preview_rows),
            key=f"historical_rule_review_{upload_key}",
            disabled=[column for column in preview_rows[0] if column != "Use rule suggestion"],
            column_config={
                "Use rule suggestion": st.column_config.CheckboxColumn(
                    "Use rule suggestion",
                    help="Accept the matched keyword rule instead of the CSV category.",
                )
            },
            use_container_width=True,
            hide_index=True,
        )
        if st.button("Commit historical batch"):
            rows = []
            unresolved_rows = []
            for row_index, item in enumerate(validation_rows):
                use_rule = bool(
                    item["rule_category_id"] is not None
                    and edited_preview.iloc[row_index]["Use rule suggestion"]
                )
                category_id = item["rule_category_id"] if use_rule else item["category_id"]
                if category_id is None:
                    unresolved_rows.append(row_index + 1)
                    continue
                rows.append(
                    {
                        "date": item["date"],
                        "category_id": int(category_id),
                        "amount_cents": item["amount_cents"],
                        "description": item["description"],
                        "comments": item["comments"],
                        "source": "sheet",
                    }
                )
            if unresolved_rows:
                st.error(
                    "Accept a rule suggestion or fix the CSV category for row(s): "
                    f"{', '.join(str(index) for index in unresolved_rows)}."
                )
            else:
                inserted, skipped = insert_many(rows, source="sheet")
                st.success(
                    f"Imported {inserted} rows; skipped {skipped} duplicates; "
                    f"excluded {ignored_by_rules} by keyword rules."
                )
                st.cache_data.clear()
                st.rerun()


def render_bank_wizard() -> None:
    """Render the bank statement import wizard."""
    st.subheader("Bank statement")
    uploaded = st.file_uploader("Upload a statement", type=["csv", "txt"], key="bank_upload")
    if uploaded is None:
        return

    file_bytes = uploaded.getvalue()
    upload_key = hashlib.sha256(file_bytes).hexdigest()[:12]
    encoding = detect_encoding(file_bytes)
    text = file_bytes.decode(encoding)
    delimiter = detect_delimiter(text)
    st.caption(f"Detected encoding: {encoding} • delimiter: {delimiter}")

    saved_profiles = list_bank_profiles()
    if saved_profiles:
        selected_profile_name = st.selectbox("Load bank profile", options=[profile["name"] for profile in saved_profiles], index=None, placeholder="Choose a saved profile")
        if selected_profile_name:
            profile = next(item for item in saved_profiles if item["name"] == selected_profile_name)
            st.json(profile)

    csv_rows, _, _ = read_csv_rows(file_bytes)
    columns = list(csv_rows[0].keys()) if csv_rows else []
    if not columns:
        st.warning("No columns could be detected in the uploaded statement.")
        return

    mapping = suggest_column_mapping(
        columns,
        {
            "date": ("Datum", "Date"),
            "amount": ("Bedrag (EUR)", "Bedrag", "Amount"),
            "description": ("Naam / Omschrijving",),
            "direction": ("Af Bij", "Af/Bij", "Debit/Credit", "Debit Credit"),
        },
    )

    date_field = st.selectbox(
        "Date column",
        options=columns,
        index=columns.index(mapping["date"]) if mapping["date"] is not None else None,
    )
    amount_field = st.selectbox(
        "Amount column",
        options=columns,
        index=columns.index(mapping["amount"]) if mapping["amount"] is not None else None,
    )
    direction_options = ["None", *columns]
    direction_field = st.selectbox(
        "Af/Bij or debit/credit column",
        options=direction_options,
        index=direction_options.index(mapping["direction"]) if mapping["direction"] is not None else 0,
    )

    description_field = mapping["description"]
    if date_field is None or amount_field is None or description_field is None:
        st.warning("Choose the date and amount columns, and include a 'Naam / Omschrijving' column.")
        return

    first_date = str(csv_rows[0].get(date_field) or "").strip()
    date_formats = ["%Y%m%d", "%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%m/%d/%Y"]
    default_date_format = "%Y%m%d" if len(first_date) == 8 and first_date.isdigit() else "%Y-%m-%d"
    date_format = st.selectbox(
        "Date format",
        options=date_formats,
        index=date_formats.index(default_date_format),
    )

    profile_name = st.text_input("Bank profile name")
    save_profile = st.checkbox("Save profile")
    if save_profile and profile_name.strip():
        first_amount = csv_rows[0].get(amount_field) or "1.234,56"
        add_bank_profile(
            name=profile_name.strip(),
            delimiter=delimiter,
            decimal_sep=detect_decimal_separator(str(first_amount)),
            date_format=date_format,
            column_mapping={
                "date": date_field,
                "amount": amount_field,
                "description": description_field,
                "direction": None if direction_field == "None" else direction_field,
            },
        )
        st.success("Profile saved.")

    normalized_rows = []
    invalid_rows = 0
    for row in csv_rows:
        try:
            normalized_date = parse_date(row.get(date_field), fmt=date_format)
        except ValueError:
            invalid_rows += 1
            continue
        try:
            amount_value = parse_amount(row.get(amount_field), decimal_sep=detect_decimal_separator(str(row.get(amount_field) or "")))
        except ValueError:
            invalid_rows += 1
            continue
        normalized_rows.append(
            {
                "date": normalized_date,
                "amount": amount_value,
                "description": row.get(description_field, "") or "",
                "debit_credit": row.get(direction_field) if direction_field != "None" else "",
            }
        )

    outgoing, ignored = filter_outgoing_transactions(normalized_rows)
    if not outgoing:
        st.info("No outgoing transactions were detected in this statement.")
        return

    categories = list_categories()
    types = list_types()
    if not categories or not types:
        st.warning("Create a spending type and category before importing expenses.")
        return

    category_by_name = {entry["name"]: entry for entry in categories}
    category_by_id = {int(entry["id"]): entry for entry in categories}
    rules = list_rules()
    type_names = [entry["name"] for entry in types]
    upload_rows = []
    ignored_by_rules = 0
    for row_index, item in enumerate(outgoing):
        rule_match = match_rule(str(item["description"] or ""), rules)
        if rule_match is not None and rule_match.action == "ignore":
            ignored_by_rules += 1
            continue
        rule_category = (
            category_by_id.get(rule_match.category_id)
            if rule_match is not None and rule_match.category_id is not None
            else None
        )
        row_key = f"{upload_key}_{row_index}"
        amount_key = f"bank_amount_{row_key}"
        edited_amount = st.session_state.get(amount_key, item["amount_cents"] / 100)
        amount_cents = int(round(float(edited_amount) * 100))
        upload_rows.append(
            {
                **item,
                "amount_cents": amount_cents,
                "amount_key": amount_key,
                "note_key": f"bank_note_{row_key}",
                "comments_key": f"bank_comments_{row_key}",
                "import_key": f"bank_import_{row_key}",
                "type_key": f"bank_type_{row_key}",
                "category_key": f"bank_category_{row_key}",
                "rule_keyword": rule_match.keyword if rule_category and rule_match else None,
                "rule_type_name": rule_category["type_name"] if rule_category else None,
                "rule_category_name": rule_category["name"] if rule_category else None,
            }
        )

    existing_matches = find_existing_expense_matches(upload_rows)
    review_rows = []
    seen_transactions = set()
    for item in upload_rows:
        match_key = (item["date"], item["amount_cents"])
        stored_matches = existing_matches.get(match_key, [])
        repeated_upload = match_key in seen_transactions
        seen_transactions.add(match_key)
        possible_duplicate = bool(stored_matches) or repeated_upload
        if stored_matches:
            existing_record = "\n".join(
                f"#{match['id']} {match['date']} €{match['amount_cents'] / 100:.2f} "
                f"{match['type']} / {match['category']}: {match['description']}"
                for match in stored_matches
            )
        elif repeated_upload:
            existing_record = "Same transaction appears earlier in this upload."
        else:
            existing_record = ""
        review_rows.append(
            {
                "import": not possible_duplicate,
                "possible_duplicate": possible_duplicate,
                "existing_record": existing_record,
                "reviewed": False,
                "date": item["date"],
                "amount_cents": item["amount_cents"],
                "amount_eur": item["amount_cents"] / 100,
                "description": item["description"],
                "amount_key": item["amount_key"],
                "note_key": item["note_key"],
                "comments_key": item["comments_key"],
                "import_key": item["import_key"],
                "type_key": item["type_key"],
                "category_key": item["category_key"],
                "rule_keyword": item["rule_keyword"],
                "rule_type_name": item["rule_type_name"],
                "rule_category_name": item["rule_category_name"],
                "reviewed_key": f"bank_reviewed_{item['import_key']}_{item['amount_cents']}",
            }
        )

    if not review_rows:
        st.info(
            "No rows remain for review. "
            f"{ignored_by_rules} excluded by keyword rules; {ignored} incoming rows ignored."
        )
        return

    duplicate_count = sum(bool(item["possible_duplicate"]) for item in review_rows)
    if duplicate_count:
        st.warning(
            f"Found {duplicate_count} possible duplicate(s). Compare the existing record, "
            "then mark each match as reviewed before importing it."
        )
    st.caption("Review the suggested spending type and category for each expense before importing.")
    for item in review_rows:
        description = item["description"] or "(no name / description)"
        st.markdown(f"**{item['date']}  |  {description}**")
        if item["rule_keyword"]:
            st.caption(
                f"Rule '{item['rule_keyword']}' suggested "
                f"{item['rule_type_name']} / {item['rule_category_name']}."
            )
        if item["possible_duplicate"]:
            st.warning(f"Possible existing record:\n\n{item['existing_record']}")

        import_col, amount_col, type_col, category_col = st.columns([1, 1.2, 1.5, 1.5])
        with import_col:
            if item["import_key"] not in st.session_state:
                st.session_state[item["import_key"]] = not item["possible_duplicate"]
            st.checkbox("Import?", key=item["import_key"])
        with amount_col:
            if item["amount_key"] not in st.session_state:
                st.session_state[item["amount_key"]] = item["amount_eur"]
            st.number_input(
                "Amount (€)",
                min_value=0.01,
                step=0.01,
                format="%.2f",
                key=item["amount_key"],
            )
        with type_col:
            if item["type_key"] not in st.session_state and item["rule_type_name"]:
                st.session_state[item["type_key"]] = item["rule_type_name"]
            selected_type = st.selectbox(
                "Type",
                options=type_names,
                index=None,
                placeholder="Select a type",
                key=item["type_key"],
            )

        matching_categories = [
            entry["name"] for entry in categories
            if entry["type_name"] == selected_type
        ]
        category_key = item["category_key"]
        if category_key not in st.session_state and item["rule_category_name"]:
            st.session_state[category_key] = item["rule_category_name"]
        if category_key in st.session_state and st.session_state[category_key] not in matching_categories:
            del st.session_state[category_key]
        with category_col:
            st.selectbox(
                "Category",
                options=matching_categories or [""],
                index=None,
                placeholder="Select a type first" if not selected_type else "Select a category",
                disabled=not selected_type or not matching_categories,
                key=category_key,
            )

        note_col, comments_col = st.columns(2)
        with note_col:
            if item["note_key"] not in st.session_state:
                st.session_state[item["note_key"]] = item["description"] or ""
            st.text_input("Note (Naam / Omschrijving)", key=item["note_key"])
        with comments_col:
            if item["comments_key"] not in st.session_state:
                st.session_state[item["comments_key"]] = ""
            st.text_input("Comments", key=item["comments_key"])

        if item["possible_duplicate"]:
            reviewed_key = item["reviewed_key"]
            if reviewed_key not in st.session_state:
                st.session_state[reviewed_key] = False
            st.checkbox("I checked this possible match", key=reviewed_key)
        st.divider()

    selected_count = sum(
        bool(st.session_state.get(item["import_key"], not item["possible_duplicate"]))
        for item in review_rows
    )
    st.caption(
        f"Summary: {selected_count} rows selected, {duplicate_count} possible matches, "
        f"{ignored} incoming ignored, {ignored_by_rules} excluded by keyword rules, "
        f"{invalid_rows} invalid rows skipped"
    )

    if st.button("Confirm and import bank batch"):
        rows_to_insert: list[dict] = []
        invalid_selections = []
        unreviewed_matches = []
        for row_index, item in enumerate(review_rows, start=1):
            if not st.session_state.get(item["import_key"], not item["possible_duplicate"]):
                continue
            if item["possible_duplicate"] and not st.session_state.get(item["reviewed_key"], False):
                unreviewed_matches.append(row_index)
                continue

            selected_type = st.session_state.get(item["type_key"])
            selected_category = st.session_state.get(item["category_key"])
            category = category_by_name.get(str(selected_category))
            if not selected_type or category is None or category["type_name"] != selected_type:
                invalid_selections.append(row_index)
                continue
            rows_to_insert.append(
                {
                    "date": item["date"],
                    "category_id": int(category["id"]),
                    "amount_cents": int(round(float(st.session_state[item["amount_key"]]) * 100)),
                    "description": st.session_state[item["note_key"]] or None,
                    "comments": st.session_state[item["comments_key"]] or None,
                    "source": "bank",
                }
            )

        if unreviewed_matches:
            st.error(
                "Review the existing record for selected possible duplicates first. "
                f"Check row(s): {', '.join(str(index) for index in unreviewed_matches)}."
            )
        elif invalid_selections:
            st.error(
                "Each selected expense needs a type and a category within that type. "
                f"Check row(s): {', '.join(str(index) for index in invalid_selections)}."
            )
        elif rows_to_insert:
            inserted, skipped = insert_many(rows_to_insert, source="bank")
            st.success(
                f"Imported {inserted} rows; skipped {skipped} duplicates; "
                f"ignored {ignored} incoming rows."
            )
            st.cache_data.clear()
            st.rerun()
        else:
            st.info("No rows were selected for import.")

    if st.button("Undo last import"):
        latest_batch = get_latest_batch_id()
        if latest_batch is not None:
            delete_batch(latest_batch)
            st.cache_data.clear()
            st.rerun()


def render() -> None:
    """Render both import tabs."""
    st.title("Import")
    tab1, tab2 = st.tabs(["Historical data (Google Sheets CSV)", "Bank statement"])
    with tab1:
        render_historical_import()
    with tab2:
        render_bank_wizard()


if __name__ == "__main__":
    render()
