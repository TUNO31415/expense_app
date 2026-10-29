from __future__ import annotations

from datetime import date
from typing import Any

import pandas as pd
import streamlit as st

from db import (
    add_expense,
    delete_expense,
    get_expenses_df,
    list_categories,
    update_expense,
)
from ui.components import category_label_map, empty_state, fmt_eur, page_header
from ui.feedback import after_write

TYPE_PREFIX = "Type: "


@st.cache_data
def load_expenses() -> pd.DataFrame:
    """Load and cache the current expense table."""
    return get_expenses_df()


def _clean_text(value: Any) -> str:
    """Normalize optional text so None, NaN and '' compare equal."""
    return "" if value is None or (not isinstance(value, str) and pd.isna(value)) else str(value).strip()


def _reset_editor() -> None:
    """Give the table a fresh key so stale positional edits are never re-applied to other rows."""
    st.session_state["expense_editor_nonce"] = st.session_state.get("expense_editor_nonce", 0) + 1


@st.dialog("Add expense", width="medium")
def add_expense_dialog() -> None:
    """Quick manual entry: the required fields first, comments tucked away."""
    labels = category_label_map(list_categories())
    if not labels:
        st.info("Create a type and a category in Settings before adding expenses.")
        return

    with st.form("add_expense_form", border=False):
        date_col, amount_col = st.columns(2)
        expense_date = date_col.date_input("Date", value=date.today(), format="DD/MM/YYYY")
        amount_eur = amount_col.number_input("Amount (€)", min_value=0.0, step=0.01, format="%.2f", value=None, placeholder="0.00")
        category = st.selectbox("Category", options=list(labels), index=None, placeholder="Choose a category")
        description = st.text_input("Description", placeholder="e.g. Albert Heijn")
        with st.expander("Comments"):
            comments = st.text_area("Comments", label_visibility="collapsed")

        if st.form_submit_button("Add expense", type="primary", width="stretch"):
            if not amount_eur or amount_eur <= 0:
                st.error("Enter an amount above zero.")
            elif category is None:
                st.error("Choose a category.")
            else:
                add_expense(
                    date=expense_date.isoformat(),
                    category_id=labels[category]["id"],
                    amount_cents=int(round(amount_eur * 100)),
                    description=description.strip() or None,
                    comments=comments.strip() or None,
                    source="manual",
                )
                _reset_editor()
                after_write(f"Added {fmt_eur(amount_eur)} to {category}.")


def _render_filters(df: pd.DataFrame, labels: dict[str, dict]) -> pd.DataFrame:
    """Compact filter bar; returns the filtered rows."""
    dates = pd.to_datetime(df["date"])
    min_date, max_date = dates.min().date(), dates.max().date()

    with st.container(border=True):
        date_col, group_col, search_col = st.columns([2, 3, 3])
        date_range = date_col.date_input(
            "Date range",
            value=(min_date, max_date),
            min_value=min_date,
            max_value=max_date,
            format="DD/MM/YYYY",
        )
        type_names = sorted(df["type"].dropna().unique().tolist())
        groups = group_col.multiselect(
            "Type or category",
            options=[f"{TYPE_PREFIX}{name}" for name in type_names] + list(labels),
            placeholder="All types and categories",
        )
        search = search_col.text_input("Search", placeholder="Description or comments", icon=":material/search:")

        with st.expander("More filters"):
            min_col, max_col, source_col = st.columns(3)
            amount_min = min_col.number_input("Min amount (€)", min_value=0.0, step=1.0, value=0.0)
            amount_max = max_col.number_input("Max amount (€)", min_value=0.0, step=1.0, value=float(df["amount_eur"].max()))
            sources = source_col.multiselect("Source", options=sorted(df["source"].dropna().unique().tolist()), placeholder="All sources")

    start, end = (date_range[0], date_range[-1]) if date_range else (min_date, max_date)
    mask = dates.dt.date.between(start, end)
    if groups:
        selected_types = {item.removeprefix(TYPE_PREFIX) for item in groups if item.startswith(TYPE_PREFIX)}
        selected_labels = {item for item in groups if not item.startswith(TYPE_PREFIX)}
        row_labels = df["type"].fillna("") + " / " + df["category"].fillna("")
        mask &= df["type"].isin(selected_types) | row_labels.isin(selected_labels)
    if search:
        text = df["description"].fillna("") + " " + df["comments"].fillna("")
        mask &= text.str.contains(search, case=False, regex=False)
    if sources:
        mask &= df["source"].isin(sources)
    mask &= df["amount_eur"].between(amount_min, amount_max)

    # Changing filters changes which rows sit at which position, so start a fresh editor.
    filter_state = (start, end, tuple(groups), search, amount_min, amount_max, tuple(sources))
    if st.session_state.get("expense_filter_state") != filter_state:
        st.session_state["expense_filter_state"] = filter_state
        _reset_editor()

    return df.loc[mask]


def _save_edits(original: pd.DataFrame, edited: pd.DataFrame, labels: dict[str, dict]) -> int:
    """Persist changed rows; both frames are indexed by expense id. Returns the number saved."""
    saved = 0
    for expense_id, new_row in edited.iterrows():
        old_row = original.loc[expense_id]
        category = labels.get(new_row["category"])
        if category is None or pd.isna(new_row["amount_eur"]) or pd.isna(new_row["date"]):
            continue

        expense_date = pd.to_datetime(new_row["date"]).date().isoformat()
        amount_cents = int(round(float(new_row["amount_eur"]) * 100))
        description = _clean_text(new_row["description"])
        comments = _clean_text(new_row["comments"])
        if (
            expense_date != old_row["date"]
            or int(category["id"]) != int(old_row["category_id"])
            or amount_cents != int(old_row["amount_cents"])
            or description != _clean_text(old_row["description"])
            or comments != _clean_text(old_row["comments"])
        ):
            update_expense(
                int(expense_id),
                date=expense_date,
                category_id=int(category["id"]),
                amount_cents=amount_cents,
                description=description,
                comments=comments,
            )
            saved += 1
    return saved


def render() -> None:
    """Render the expense list: add dialog, filter bar and an editable table."""
    title_col, add_col = st.columns([4, 1], vertical_alignment="bottom")
    with title_col:
        page_header("Expenses", "Every transaction, searchable and editable. Changes save automatically.")
    if add_col.button("Add expense", type="primary", icon=":material/add:", width="stretch"):
        add_expense_dialog()

    df = load_expenses()
    if df.empty:
        empty_state("🧾", "No expenses yet. Add one above or import a bank statement.", "Import bank statement", "pages/import_data.py")
        return

    labels = category_label_map(list_categories())
    filtered = _render_filters(df, labels)

    total_col, actions_col = st.columns([3, 2], vertical_alignment="center")
    total_col.markdown(f"**{len(filtered):,} expenses** · {fmt_eur(float(filtered['amount_eur'].sum()))}")

    original = filtered.set_index("id")
    editor_df = pd.DataFrame(
        {
            "delete": False,
            "date": pd.to_datetime(original["date"]),
            "description": original["description"],
            "category": original["type"].fillna("") + " / " + original["category"].fillna(""),
            "amount_eur": original["amount_eur"].round(2),
            "comments": original["comments"],
            "type": original["type"],
            "source": original["source"],
        },
        index=original.index,
    )
    edited = st.data_editor(
        editor_df,
        key=f"expense_editor_{st.session_state.get('expense_editor_nonce', 0)}",
        hide_index=True,
        width="stretch",
        height=min(35 * (len(editor_df) + 1) + 3, 700),
        disabled=["type", "source"],
        column_config={
            "delete": st.column_config.CheckboxColumn("🗑", help="Tick rows, then press 'Delete selected'.", width="small"),
            "date": st.column_config.DateColumn("Date", format="DD/MM/YYYY", required=True, width="small"),
            "description": st.column_config.TextColumn("Description", width="large"),
            "category": st.column_config.SelectboxColumn("Category", options=list(labels), required=True, width="medium"),
            "amount_eur": st.column_config.NumberColumn("Amount", format="€%.2f", min_value=0.01, step=0.01, required=True),
            "comments": st.column_config.TextColumn("Comments"),
            "type": st.column_config.TextColumn("Type", width="small"),
            "source": st.column_config.TextColumn("Source", width="small"),
        },
    )

    to_delete = edited.index[edited["delete"].fillna(False).astype(bool)].tolist()
    with actions_col.container(horizontal=True, horizontal_alignment="right"):
        if st.button(
            f"Delete {len(to_delete)} selected" if to_delete else "Delete selected",
            icon=":material/delete:",
            disabled=not to_delete,
        ):
            for expense_id in to_delete:
                delete_expense(int(expense_id))
            _reset_editor()
            after_write(f"Deleted {len(to_delete)} expense(s).", icon=":material/delete:")
        st.download_button(
            "CSV",
            data=filtered.drop(columns=["category_id", "amount_cents"]).to_csv(index=False).encode("utf-8"),
            file_name="filtered_expenses.csv",
            mime="text/csv",
            icon=":material/download:",
            help="Download the filtered rows as CSV",
        )

    saved = _save_edits(original, edited.drop(columns=["delete"]), labels)
    if saved:
        _reset_editor()
        after_write(f"Saved {saved} change(s).")


if __name__ == "__main__":
    render()
