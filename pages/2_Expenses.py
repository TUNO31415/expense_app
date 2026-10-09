from __future__ import annotations

import pandas as pd
import streamlit as st

from db import (
    add_expense,
    delete_expense,
    get_expenses_df,
    list_categories,
    list_types,
    update_expense,
)


@st.cache_data
def load_expenses() -> pd.DataFrame:
    """Load and cache the current expense table."""
    return get_expenses_df()


def _category_options() -> list[str]:
    """Return the category names in a stable display order."""
    categories = list_categories()
    return [item["name"] for item in categories]


def _sync_edit_changes(original: pd.DataFrame, edited: pd.DataFrame) -> None:
    """Persist any user edits or deletions made via the data editor."""
    original_by_id = {int(row["id"]): row for _, row in original.iterrows() if pd.notna(row["id"]) }
    edited_by_id = {int(row["id"]): row for _, row in edited.iterrows() if pd.notna(row["id"]) }

    for expense_id in sorted(set(original_by_id) - set(edited_by_id)):
        delete_expense(expense_id)

    for expense_id in sorted(set(edited_by_id) & set(original_by_id)):
        old_row = original_by_id[expense_id]
        new_row = edited_by_id[expense_id]
        category_name = str(new_row["category"]).strip()
        category = next((item for item in list_categories() if item["name"] == category_name), None)
        category_id = category["id"] if category is not None else int(old_row["category_id"]) if "category_id" in old_row else None

        if category_id is None:
            continue

        amount_cents = int(round(float(new_row["amount_eur"]) * 100))
        source = str(new_row["source"]).strip() or "manual"
        expense_date = pd.to_datetime(new_row["date"]).date().isoformat()

        if (
            expense_date != str(old_row["date"])
            or int(category_id) != int(old_row.get("category_id", category_id))
            or amount_cents != int(old_row.get("amount_cents", amount_cents))
            or str(new_row["description"]) != str(old_row["description"])
            or str(new_row["comments"]) != str(old_row["comments"])
            or source != str(old_row["source"])
        ):
            update_expense(
                expense_id,
                date=expense_date,
                category_id=category_id,
                amount_cents=amount_cents,
                description=str(new_row["description"]) if pd.notna(new_row["description"]) else None,
                comments=str(new_row["comments"]) if pd.notna(new_row["comments"]) else None,
                source=source,
            )

    st.cache_data.clear()
    st.rerun()


def render() -> None:
    """Render the expense management page with filters, add form, and data editor."""
    st.title("Expenses")

    types = list_types()
    if not types:
        st.info("Create a type and category before adding expenses.")
        return

    with st.form("add_expense_form"):
        date_col, type_col, category_col = st.columns(3)
        with date_col:
            expense_date = st.date_input("Date")
        with type_col:
            selected_type = st.selectbox(
                "Type",
                options=[item["name"] for item in types],
                index=0,
            )
        with category_col:
            category_rows = [item for item in list_categories() if item["type_name"] == selected_type]
            category = st.selectbox(
                "Category",
                options=[item["name"] for item in category_rows],
                index=0 if category_rows else None,
            )

        amount_eur = st.number_input("Amount (EUR)", min_value=0.01, step=0.01, format="%.2f")
        description = st.text_input("Description")
        comments = st.text_area("Comments")
        source = st.selectbox("Source", options=["manual", "sheet", "bank"])

        if st.form_submit_button("Add expense"):
            if amount_eur <= 0:
                st.error("Amount must be greater than zero.")
            else:
                category_row = next((item for item in list_categories() if item["name"] == category), None)
                if category_row is None:
                    st.error("Please choose a valid category.")
                else:
                    add_expense(
                        date=str(expense_date),
                        category_id=category_row["id"],
                        amount_cents=int(round(amount_eur * 100)),
                        description=description or None,
                        comments=comments or None,
                        source=source,
                    )
                    st.success("Expense added.")
                    st.rerun()

    df = load_expenses().copy()
    if df.empty:
        st.info("No expenses yet. Add your first expense above or import a batch from the Import page.")
        return

    df["amount_eur"] = (df["amount_eur"] * 100).round(0) / 100

    with st.expander("Filters", expanded=True):
        filter_cols = st.columns(3)
        with filter_cols[0]:
            start_date = st.date_input("Start date", value=pd.to_datetime(df["date"].min()).date())
        with filter_cols[1]:
            end_date = st.date_input("End date", value=pd.to_datetime(df["date"].max()).date())
        with filter_cols[2]:
            selected_sources = st.multiselect("Source", options=sorted(df["source"].dropna().unique().tolist()))

        type_options = sorted(df["type"].dropna().unique().tolist())
        category_options = sorted(df["category"].dropna().unique().tolist())
        filter_cols_2 = st.columns(2)
        with filter_cols_2[0]:
            selected_types = st.multiselect("Type", options=type_options)
        with filter_cols_2[1]:
            selected_categories = st.multiselect("Category", options=category_options)

        amount_min = st.number_input("Amount min (€)", min_value=0.0, step=0.01, value=0.0)
        amount_max = st.number_input("Amount max (€)", min_value=0.0, step=0.01, value=float(df["amount_eur"].max()))
        description_filter = st.text_input("Description contains")
        comments_filter = st.text_input("Comments contains")

    mask = pd.Series(True, index=df.index)
    mask &= df["date"].between(str(start_date), str(end_date))
    if selected_types:
        mask &= df["type"].isin(selected_types)
    if selected_categories:
        mask &= df["category"].isin(selected_categories)
    if selected_sources:
        mask &= df["source"].isin(selected_sources)
    if description_filter:
        mask &= df["description"].fillna("").str.contains(description_filter, case=False, na=False)
    if comments_filter:
        mask &= df["comments"].fillna("").str.contains(comments_filter, case=False, na=False)
    mask &= df["amount_eur"].between(amount_min, amount_max)

    filtered_df = df.loc[mask].copy()
    if "category_id" not in filtered_df.columns:
        filtered_df["category_id"] = filtered_df["category"].map(
            {item["name"]: item["id"] for item in list_categories()}
        )

    filtered_df = filtered_df.sort_values(["date", "id"], ascending=[False, False]).reset_index(drop=True)
    filtered_df["amount_eur"] = filtered_df["amount_eur"].round(2)
    editor_df = filtered_df.copy()
    editor_df["date"] = pd.to_datetime(editor_df["date"])

    editor_columns = {
        "id": st.column_config.NumberColumn("ID", disabled=True),
        "date": st.column_config.DateColumn("Date"),
        "type": st.column_config.TextColumn("Type", disabled=True),
        "category": st.column_config.SelectboxColumn("Category", options=_category_options()),
        "amount_eur": st.column_config.NumberColumn("Amount (€)", format="%.2f"),
        "description": st.column_config.TextColumn("Description"),
        "comments": st.column_config.TextColumn("Comments"),
        "source": st.column_config.SelectboxColumn("Source", options=["manual", "sheet", "bank"]),
    }

    edited_df = st.data_editor(
        editor_df,
        key="expense_editor",
        hide_index=True,
        disabled=["id", "type"],
        column_config=editor_columns,
        use_container_width=True,
        num_rows="dynamic",
    )

    if not edited_df.equals(editor_df):
        _sync_edit_changes(filtered_df, edited_df)

    total_spent = float(filtered_df["amount_eur"].sum()) if not filtered_df.empty else 0.0
    st.caption(f"Rows: {len(filtered_df)}")
    st.caption(f"Filtered total: €{total_spent:,.2f}")

    csv_bytes = filtered_df.to_csv(index=False).encode("utf-8")
    st.download_button(
        "Download filtered view as CSV",
        data=csv_bytes,
        file_name="filtered_expenses.csv",
        mime="text/csv",
    )


if __name__ == "__main__":
    render()
