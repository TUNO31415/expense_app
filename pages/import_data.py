from __future__ import annotations

import hashlib
import io
from datetime import date

import pandas as pd
import streamlit as st

from db import (
    add_bank_profile,
    delete_batch,
    find_existing_expense_matches,
    insert_many,
    list_bank_profiles,
    list_categories,
    list_rules,
    list_types,
)
from services.categorizer import match_rule
from services.importers import (
    build_bank_review_rows,
    detect_decimal_separator,
    detect_delimiter,
    detect_encoding,
    parse_amount,
    parse_date,
    read_csv_rows,
    resolve_category,
    suggest_column_mapping,
)
from ui.components import badge_row, category_label_map, empty_state, fmt_eur, kpi_card, page_header
from ui.feedback import after_write


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
    st.caption("One-off import of older expenses exported from a spreadsheet (date, type, category, amount, …).")
    uploaded = st.file_uploader("Upload a CSV file", type=["csv"])
    if uploaded is None:
        return

    raw = uploaded.getvalue()
    upload_key = hashlib.sha256(raw).hexdigest()[:12]
    preview_df, enc, delimiter = _preview_csv(raw)
    _file_badges(enc, delimiter, len(preview_df))
    with st.expander("File preview", expanded=False):
        st.dataframe(preview_df.head(10), width="stretch")

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
    st.markdown("**Map columns**")
    map_cols = st.columns(3)
    date_col = map_cols[0].selectbox(
        "Date column", options=columns,
        index=columns.index(column_mapping["date"]) if column_mapping["date"] is not None else None,
    )
    type_col = map_cols[1].selectbox(
        "Type column", options=columns,
        index=columns.index(column_mapping["type"]) if column_mapping["type"] is not None else None,
    )
    category_col = map_cols[2].selectbox(
        "Category column", options=columns,
        index=columns.index(column_mapping["category"]) if column_mapping["category"] is not None else None,
    )
    amount_col = map_cols[0].selectbox(
        "Amount column", options=columns,
        index=columns.index(column_mapping["amount"]) if column_mapping["amount"] is not None else None,
    )
    description_col = map_cols[1].selectbox(
        "Description column", options=columns,
        index=columns.index(column_mapping["description"]) if column_mapping["description"] is not None else None,
    )
    comments_col = map_cols[2].selectbox(
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

    st.markdown("**Review**")
    badge_row(
        [
            (f"{len(validation_rows)} ready", ":material/check:", "green"),
            (f"{len(issues)} with issues", ":material/error:", "orange" if issues else "gray"),
            (f"{ignored_by_rules} excluded by rules", ":material/block:", "gray"),
        ]
    )
    if issues:
        with st.expander(f"Validation issues ({len(issues)})", expanded=True):
            st.caption("These rows will not be imported. Fix the CSV or map unknown values, then upload again.")
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
            width="stretch",
            hide_index=True,
        )
        if st.button(f"Import {len(validation_rows)} rows", type="primary", icon=":material/download_done:"):
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
                inserted, skipped, _ = insert_many(rows, source="sheet")
                after_write(
                    f"Imported {inserted} rows; skipped {skipped} duplicates; "
                    f"excluded {ignored_by_rules} by keyword rules."
                )


BANK_STEPS = ["Upload", "Map columns", "Review", "Done"]
DATE_FORMATS = ["%Y%m%d", "%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%m/%d/%Y"]
BANK_COLUMN_ALIASES = {
    "date": ("Datum", "Date"),
    "amount": ("Bedrag (EUR)", "Bedrag", "Amount"),
    "description": ("Naam / Omschrijving", "Description", "Omschrijving", "Name"),
    "direction": ("Af Bij", "Af/Bij", "Debit/Credit", "Debit Credit"),
}
NO_DIRECTION = "(none)"
_BANK_STATE_KEYS = (
    "bank_step",
    "bank_file",
    "bank_file_name",
    "bank_profile",
    "bank_mapping",
    "bank_date_format",
    "bank_review",
    "bank_result",
)


def _file_badges(encoding: str, delimiter: str, row_count: int) -> None:
    """Show what was detected in an uploaded file."""
    badge_row(
        [
            (f"{row_count} rows", ":material/table_rows:", "blue"),
            (f"Encoding {encoding}", None, "gray"),
            (f"Delimiter '{delimiter}'", None, "gray"),
        ]
    )


def _go_to_step(step: int) -> None:
    st.session_state["bank_step"] = step
    st.rerun()


def _reset_bank_wizard() -> None:
    """Forget the current statement so the wizard starts again at step 1."""
    for key in _BANK_STATE_KEYS:
        st.session_state.pop(key, None)
    # A new key gives a fresh, empty file uploader.
    st.session_state["bank_nonce"] = st.session_state.get("bank_nonce", 0) + 1


def _render_stepper(step: int) -> None:
    labels = "  ›  ".join(
        f"**{name}**" if index == step else name for index, name in enumerate(BANK_STEPS, start=1)
    )
    st.progress(step / len(BANK_STEPS), text=f"Step {step} of {len(BANK_STEPS)}  ·  {labels}")


def _bank_step_upload() -> None:
    """Step 1: pick the statement file and, optionally, a saved bank profile."""
    nonce = st.session_state.get("bank_nonce", 0)
    uploaded = st.file_uploader("Bank statement (CSV or TXT)", type=["csv", "txt"], key=f"bank_upload_{nonce}")
    if uploaded is not None:
        file_bytes = uploaded.getvalue()
        if file_bytes != st.session_state.get("bank_file"):
            st.session_state["bank_file"] = file_bytes
            st.session_state["bank_file_name"] = uploaded.name
            st.session_state.pop("bank_review", None)
            if st.session_state.get("bank_profile") is None:
                st.session_state.pop("bank_mapping", None)
                st.session_state.pop("bank_date_format", None)

    file_bytes = st.session_state.get("bank_file")
    if file_bytes is None:
        st.caption("Export last month's transactions from your bank as CSV and drop the file here.")
        return

    if uploaded is None:
        st.caption(f"Using **{st.session_state.get('bank_file_name', 'uploaded file')}**. Upload another file to replace it.")
    csv_rows, encoding, delimiter = read_csv_rows(file_bytes)
    _file_badges(encoding, delimiter, len(csv_rows))

    profiles = list_bank_profiles()
    if profiles:
        names = [profile["name"] for profile in profiles]
        current = st.session_state.get("bank_profile")
        choice = st.selectbox(
            "Bank profile",
            options=names,
            index=names.index(current) if current in names else None,
            placeholder="Use a saved column mapping (optional)",
        )
        if choice != current:
            st.session_state["bank_profile"] = choice
            profile = next((item for item in profiles if item["name"] == choice), None)
            if profile is not None:
                st.session_state["bank_mapping"] = profile["column_mapping"]
                st.session_state["bank_date_format"] = profile["date_format"]
            st.rerun()

    if not csv_rows:
        st.warning("No rows could be read from this file.")
    if st.button("Next: map columns", type="primary", icon=":material/arrow_forward:", disabled=not csv_rows):
        _go_to_step(2)


def _try_parse(parse, *args) -> str:
    try:
        return parse(*args)
    except ValueError:
        return f"⚠ can't read '{args[0]}'"


def _format_amount(value) -> str:
    return f"{parse_amount(value, decimal_sep=detect_decimal_separator(str(value or ''))):.2f}"


def _bank_step_map() -> None:
    """Step 2: confirm which columns hold the date, amount, description and direction."""
    csv_rows, _, delimiter = read_csv_rows(st.session_state["bank_file"])
    columns = list(csv_rows[0].keys()) if csv_rows else []
    if not columns:
        st.warning("No columns could be detected in the uploaded statement.")
        if st.button("Back", icon=":material/arrow_back:"):
            _go_to_step(1)
        return

    saved = st.session_state.get("bank_mapping") or suggest_column_mapping(columns, BANK_COLUMN_ALIASES)

    def _index(field: str) -> int | None:
        value = saved.get(field)
        return columns.index(value) if value in columns else None

    cols = st.columns(4)
    date_field = cols[0].selectbox("Date column", options=columns, index=_index("date"))
    amount_field = cols[1].selectbox("Amount column", options=columns, index=_index("amount"))
    description_field = cols[2].selectbox("Description column", options=columns, index=_index("description"))
    direction_options = [NO_DIRECTION, *columns]
    direction_index = _index("direction")
    direction_field = cols[3].selectbox(
        "Debit/credit column",
        options=direction_options,
        index=direction_index + 1 if direction_index is not None else 0,
        help="A column such as 'Af Bij'. Leave as (none) when outgoing amounts are negative.",
    )

    first_date = str(csv_rows[0].get(date_field) or "").strip() if date_field else ""
    default_format = st.session_state.get("bank_date_format") or (
        "%Y%m%d" if len(first_date) == 8 and first_date.isdigit() else "%Y-%m-%d"
    )
    date_format = st.selectbox(
        "Date format",
        options=DATE_FORMATS,
        index=DATE_FORMATS.index(default_format) if default_format in DATE_FORMATS else 0,
        format_func=lambda fmt: f"{fmt}   (e.g. {date(2026, 10, 29).strftime(fmt)})",
    )

    mapping = {
        "date": date_field,
        "amount": amount_field,
        "description": description_field,
        "direction": None if direction_field == NO_DIRECTION else direction_field,
    }
    ready = all(mapping[field] for field in ("date", "amount", "description"))

    st.markdown("**Preview**")
    if not ready:
        st.info("Choose the date, amount and description columns to continue.")
    else:
        preview = [
            {
                "Date": _try_parse(parse_date, row.get(date_field), date_format),
                "Amount": _try_parse(_format_amount, row.get(amount_field)),
                "Description": row.get(description_field) or "",
                "Debit/credit": (row.get(mapping["direction"]) or "") if mapping["direction"] else "",
            }
            for row in csv_rows[:5]
        ]
        st.dataframe(preview, hide_index=True, width="stretch")

    with st.container(horizontal=True):
        if st.button("Back", icon=":material/arrow_back:"):
            _go_to_step(1)
        with st.popover("Save as bank profile", icon=":material/bookmark_add:", disabled=not ready):
            profile_name = st.text_input("Profile name", value=st.session_state.get("bank_profile") or "")
            if st.button("Save profile", disabled=not profile_name.strip()):
                first_amount = csv_rows[0].get(amount_field) or "1.234,56"
                add_bank_profile(
                    name=profile_name.strip(),
                    delimiter=delimiter,
                    decimal_sep=detect_decimal_separator(str(first_amount)),
                    date_format=date_format,
                    column_mapping=mapping,
                )
                st.session_state["bank_profile"] = profile_name.strip()
                st.session_state["bank_mapping"] = mapping
                st.session_state["bank_date_format"] = date_format
                after_write(f"Saved bank profile '{profile_name.strip()}'.")
        if st.button("Next: review transactions", type="primary", icon=":material/arrow_forward:", disabled=not ready):
            st.session_state["bank_mapping"] = mapping
            st.session_state["bank_date_format"] = date_format
            st.session_state["bank_review"] = build_bank_review_rows(
                csv_rows,
                mapping,
                date_format,
                list_rules(),
                list_categories(),
                find_existing_expense_matches,
            )
            # A fresh editor key so edits from an earlier review don't leak into this one.
            st.session_state["bank_editor_nonce"] = st.session_state.get("bank_editor_nonce", 0) + 1
            _go_to_step(3)


def _bank_step_review() -> None:
    """Step 3: one editable table to tick, categorize and adjust every transaction."""
    review = st.session_state.get("bank_review")
    if review is None:
        _go_to_step(2)
    rows = review["rows"]

    categories = list_categories()
    labels = category_label_map(categories)
    label_by_id = {int(category["id"]): label for label, category in labels.items()}
    if not labels:
        empty_state("🗂️", "Create a type and a category before importing expenses.", "Open Settings", "pages/settings.py")
        return

    if not rows:
        empty_state(
            "📭",
            f"Nothing left to import: {review['ignored_incoming']} incoming rows ignored, "
            f"{review['excluded_by_rules']} excluded by keyword rules, {review['invalid']} unreadable.",
        )
        if st.button("Back", icon=":material/arrow_back:"):
            _go_to_step(2)
        return

    rule_count = sum(row["category_id"] is not None for row in rows)
    st.caption(
        f"{rule_count} of {len(rows)} transactions were categorized by your keyword rules. "
        "Pick a category for the rest, untick anything you don't want to import, and edit amounts or descriptions if needed."
    )
    chips = st.container()

    base_df = pd.DataFrame(
        [
            {
                "import": not row["possible_duplicate"],
                "date": row["date"],
                "description": row["description"],
                "amount_eur": row["amount_cents"] / 100,
                "category": label_by_id.get(row["category_id"]),
                "comments": "",
                "duplicate": "⚠ Possible match" if row["possible_duplicate"] else "",
                "existing_record": row["existing_record"],
            }
            for row in rows
        ]
    )
    edited = st.data_editor(
        base_df,
        key=f"bank_review_editor_{st.session_state.get('bank_editor_nonce', 0)}",
        hide_index=True,
        width="stretch",
        height=min(35 * (len(base_df) + 1) + 3, 640),
        disabled=["date", "duplicate", "existing_record"],
        column_config={
            "import": st.column_config.CheckboxColumn(
                "Import",
                help="Possible duplicates start unticked. Ticking one confirms you checked the existing record.",
                width="small",
            ),
            "date": st.column_config.TextColumn("Date", width="small"),
            "description": st.column_config.TextColumn("Description", width="large"),
            "amount_eur": st.column_config.NumberColumn("Amount", format="€%.2f", min_value=0.01, step=0.01, required=True),
            "category": st.column_config.SelectboxColumn("Category", options=list(labels), width="medium"),
            "comments": st.column_config.TextColumn("Comments"),
            "duplicate": st.column_config.TextColumn("Duplicate?", width="small"),
            "existing_record": st.column_config.TextColumn("Existing match", width="medium"),
        },
    )

    selected = edited[edited["import"].fillna(False).astype(bool)]
    missing_category = ~selected["category"].isin(labels)
    bad_amount = selected["amount_eur"].isna() | (selected["amount_eur"] <= 0)
    duplicate_count = sum(row["possible_duplicate"] for row in rows)
    with chips:
        badge_row(
            [
                (f"{len(selected)} selected", ":material/check_box:", "green"),
                (f"{int(missing_category.sum())} need a category", ":material/label:", "orange" if missing_category.any() else "gray"),
                (f"{duplicate_count} possible duplicates", ":material/content_copy:", "orange" if duplicate_count else "gray"),
                (f"{review['ignored_incoming']} incoming ignored", ":material/south_west:", "gray"),
                (f"{review['excluded_by_rules']} excluded by rules", ":material/block:", "gray"),
                (f"{review['invalid']} unreadable", ":material/error:", "red" if review["invalid"] else "gray"),
            ]
        )

    blocked_reason = None
    if selected.empty:
        blocked_reason = "Tick at least one transaction to import."
    elif missing_category.any():
        blocked_reason = "Every ticked transaction needs a category."
    elif bad_amount.any():
        blocked_reason = "Every ticked transaction needs an amount above zero."

    with st.container(horizontal=True):
        if st.button("Back", icon=":material/arrow_back:"):
            _go_to_step(2)
        import_clicked = st.button(
            f"Import {len(selected)} expenses",
            type="primary",
            icon=":material/download_done:",
            disabled=blocked_reason is not None,
            help=blocked_reason,
        )
    if blocked_reason and not selected.empty:
        st.caption(f":orange[{blocked_reason}]")

    if import_clicked:
        rows_to_insert = [
            {
                "date": row["date"],
                "category_id": int(labels[row["category"]]["id"]),
                "amount_cents": int(round(float(row["amount_eur"]) * 100)),
                "description": (str(row["description"]).strip() or None) if pd.notna(row["description"]) else None,
                "comments": (str(row["comments"]).strip() or None) if pd.notna(row["comments"]) else None,
                "source": "bank",
            }
            for _, row in selected.iterrows()
        ]
        inserted, skipped, batch_id = insert_many(rows_to_insert, source="bank")
        st.session_state["bank_result"] = {
            "inserted": inserted,
            "skipped": skipped,
            "batch_id": batch_id,
            "total_cents": sum(row["amount_cents"] for row in rows_to_insert),
        }
        st.session_state["bank_step"] = 4
        after_write()


def _bank_step_done() -> None:
    """Step 4: show the result, with undo and next steps."""
    result = st.session_state.get("bank_result")
    if result is None:
        _reset_bank_wizard()
        st.rerun()

    with st.container(border=True):
        st.subheader(":material/task_alt: Import complete")
        cols = st.columns(3)
        with cols[0]:
            kpi_card("Imported", f"{result['inserted']:,}")
        with cols[1]:
            kpi_card("Skipped", f"{result['skipped']:,}", help="Already in the database from an earlier import.")
        with cols[2]:
            kpi_card("Selected total", fmt_eur(result["total_cents"] / 100))

    with st.container(horizontal=True, vertical_alignment="center"):
        st.page_link("pages/home.py", label="Go to Home", icon=":material/home:")
        st.page_link("pages/expenses.py", label="View expenses", icon=":material/receipt_long:")
        if st.button("Import another file", icon=":material/upload_file:"):
            _reset_bank_wizard()
            st.rerun()
        if st.button("Undo this import", icon=":material/undo:", type="tertiary"):
            delete_batch(result["batch_id"])
            _reset_bank_wizard()
            after_write(f"Undid the import of {result['inserted']} expenses.", icon=":material/undo:")


def render_bank_wizard() -> None:
    """Render the four-step bank statement import."""
    step = st.session_state.setdefault("bank_step", 1)
    if step > 1 and st.session_state.get("bank_file") is None:
        step = st.session_state["bank_step"] = 1
    _render_stepper(step)
    {1: _bank_step_upload, 2: _bank_step_map, 3: _bank_step_review, 4: _bank_step_done}[step]()


def render() -> None:
    """Render the import page: bank statements first, historical CSV second."""
    page_header("Import", "Bring in your monthly bank statement, review it, and save it in one go.")
    bank_tab, csv_tab = st.tabs([":material/account_balance: Bank statement", ":material/table_view: Historical CSV"])
    with bank_tab:
        render_bank_wizard()
    with csv_tab:
        render_historical_import()


if __name__ == "__main__":
    render()
