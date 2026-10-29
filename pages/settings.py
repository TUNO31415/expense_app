from __future__ import annotations

import sqlite3

import pandas as pd
import streamlit as st

from db import (
    add_category,
    add_rule,
    add_type,
    delete_bank_profile,
    delete_category,
    delete_rule,
    delete_type,
    list_bank_profiles,
    list_categories,
    list_rules,
    list_types,
    update_category,
    update_type,
)
from ui.components import category_label_map, empty_state, page_header
from ui.feedback import after_write, flash


def _render_type_block(type_row: dict, categories: list[dict], type_names: dict[str, int]) -> None:
    """One expander per type with an editable table of its categories."""
    with st.expander(f"{type_row['name']}  ·  {len(categories)} categories", expanded=False):
        rename_col, delete_col = st.columns([4, 1], vertical_alignment="bottom")
        new_name = rename_col.text_input("Type name", value=type_row["name"], key=f"type_name_{type_row['id']}")
        if new_name.strip() and new_name.strip() != type_row["name"]:
            try:
                update_type(type_row["id"], new_name)
            except sqlite3.IntegrityError:
                st.warning(f"A type called '{new_name.strip()}' already exists.")
            else:
                after_write(f"Renamed type to '{new_name.strip()}'.")
        if delete_col.button("Delete type", key=f"delete_type_{type_row['id']}", icon=":material/delete:", disabled=bool(categories), help="Only empty types can be deleted." if categories else None):
            delete_type(type_row["id"])
            after_write(f"Deleted type '{type_row['name']}'.", icon=":material/delete:")

        if not categories:
            st.caption("No categories yet.")
            return

        original = pd.DataFrame(
            {"delete": False, "name": [c["name"] for c in categories], "type": type_row["name"]},
            index=[c["id"] for c in categories],
        )
        edited = st.data_editor(
            original,
            key=f"categories_editor_{type_row['id']}_{st.session_state.get('settings_nonce', 0)}",
            hide_index=True,
            width="stretch",
            column_config={
                "delete": st.column_config.CheckboxColumn("🗑", width="small"),
                "name": st.column_config.TextColumn("Category", required=True),
                "type": st.column_config.SelectboxColumn("Type", options=list(type_names), required=True, help="Pick another type to move the category."),
            },
        )

        to_delete = edited.index[edited["delete"].fillna(False).astype(bool)].tolist()
        if st.button(f"Delete {len(to_delete)} selected" if to_delete else "Delete selected", key=f"delete_categories_{type_row['id']}", icon=":material/delete:", disabled=not to_delete):
            in_use = []
            for category_id in to_delete:
                if not delete_category(int(category_id)):
                    in_use.append(str(original.loc[category_id, "name"]))
            if in_use:
                flash(f"Not deleted, still used by expenses: {', '.join(in_use)}.", icon=":material/warning:")
            deleted = len(to_delete) - len(in_use)
            _bump_nonce()
            after_write(f"Deleted {deleted} category(ies)." if deleted else None, icon=":material/delete:")

        changes = failed = 0
        for category_id, row in edited.iterrows():
            old = original.loc[category_id]
            name = str(row["name"] or "").strip()
            new_type_id = type_names.get(row["type"])
            if name and (name != old["name"] or row["type"] != old["type"]) and new_type_id is not None:
                try:
                    update_category(int(category_id), name=name, type_id=new_type_id)
                except sqlite3.IntegrityError:
                    flash(f"A category called '{name}' already exists.", icon=":material/warning:")
                    failed += 1
                    continue
                changes += 1
        if changes or failed:
            _bump_nonce()
            after_write(f"Saved {changes} category change(s)." if changes else None)


def _bump_nonce() -> None:
    st.session_state["settings_nonce"] = st.session_state.get("settings_nonce", 0) + 1


def render_categories_tab() -> None:
    types = list_types()
    categories = list_categories()
    type_names = {item["name"]: item["id"] for item in types}

    with st.container(border=True):
        st.markdown("**Add**")
        type_form_col, category_form_col = st.columns(2)
        with type_form_col.form("add_type_form", clear_on_submit=True, border=False):
            type_name = st.text_input("New type", placeholder="e.g. Kids")
            if st.form_submit_button("Add type", icon=":material/add:") and type_name.strip():
                add_type(type_name)
                after_write(f"Added type '{type_name.strip()}'.")
        with category_form_col.form("add_category_form", clear_on_submit=True, border=False):
            name_col, type_col = st.columns(2)
            category_name = name_col.text_input("New category", placeholder="e.g. Childcare")
            parent = type_col.selectbox("In type", options=list(type_names), index=None, placeholder="Choose a type")
            if st.form_submit_button("Add category", icon=":material/add:") and category_name.strip() and parent:
                add_category(category_name, type_names[parent])
                after_write(f"Added category '{category_name.strip()}' to {parent}.")

    if not types:
        empty_state("🗂️", "No types yet. Add one above to start organizing your expenses.")
        return
    st.caption("Edit a category's name or pick another type to move it. Changes save automatically.")
    for type_row in types:
        _render_type_block(type_row, [c for c in categories if c["type_id"] == type_row["id"]], type_names)


def render_rules_tab() -> None:
    st.caption(
        "Keywords match anywhere in a transaction description, ignoring case. The longest matching keyword wins; "
        "priority only breaks ties between keywords of equal length. Any matching ignore rule skips the transaction."
    )
    labels = category_label_map(list_categories())
    # Bumping the nonce after adding a rule gives empty widgets for the next one.
    form_id = st.session_state.get("rule_form_nonce", 0)
    with st.container(border=True):
        keyword_col, action_col, category_col, priority_col, button_col = st.columns([3, 2, 3, 1, 1.4], vertical_alignment="bottom")
        keyword = keyword_col.text_input("Keyword", key=f"rule_keyword_{form_id}", placeholder="e.g. albert heijn")
        action = action_col.segmented_control(
            "Action",
            options=["categorize", "ignore"],
            default="categorize",
            key=f"rule_action_{form_id}",
            format_func=str.capitalize,
        )
        category = category_col.selectbox(
            "Category",
            options=list(labels),
            index=None,
            placeholder="Not used for ignore rules" if action == "ignore" else "Choose a category",
            disabled=action == "ignore",
            key=f"rule_category_{form_id}",
        )
        priority = priority_col.number_input("Priority", min_value=0, step=1, key=f"rule_priority_{form_id}")
        can_add = bool(keyword.strip()) and (action == "ignore" or category is not None)
        if button_col.button("Add rule", type="primary", icon=":material/add:", disabled=not can_add, width="stretch"):
            add_rule(
                keyword,
                category_id=None if action == "ignore" else labels[category]["id"],
                action=action or "categorize",
                priority=int(priority),
            )
            st.session_state["rule_form_nonce"] = form_id + 1
            after_write(f"Added rule '{keyword.strip()}'.")

    rules = list_rules()
    if not rules:
        empty_state("🔎", "No rules yet. Rules pre-fill categories when you import a bank statement.")
        return
    table = pd.DataFrame(
        {
            "delete": False,
            "keyword": [r["keyword"] for r in rules],
            "action": [r["action"].capitalize() for r in rules],
            "category": [r["category_name"] or "—" for r in rules],
            "priority": [r["priority"] for r in rules],
        },
        index=[r["id"] for r in rules],
    )
    edited = st.data_editor(
        table,
        key=f"rules_editor_{st.session_state.get('settings_nonce', 0)}",
        hide_index=True,
        width="stretch",
        disabled=["keyword", "action", "category", "priority"],
        column_config={
            "delete": st.column_config.CheckboxColumn("🗑", width="small"),
            "keyword": "Keyword",
            "action": "Action",
            "category": "Category",
            "priority": st.column_config.NumberColumn("Priority", width="small"),
        },
    )
    to_delete = edited.index[edited["delete"].fillna(False).astype(bool)].tolist()
    if st.button(f"Delete {len(to_delete)} selected" if to_delete else "Delete selected", key="delete_rules", icon=":material/delete:", disabled=not to_delete):
        for rule_id in to_delete:
            delete_rule(int(rule_id))
        _bump_nonce()
        after_write(f"Deleted {len(to_delete)} rule(s).", icon=":material/delete:")


def render_profiles_tab() -> None:
    profiles = list_bank_profiles()
    if not profiles:
        empty_state("🏦", "No bank profiles yet. Save one from step 2 of the bank import to reuse your column mapping.")
        return
    for profile in profiles:
        mapping = profile["column_mapping"]
        with st.container(border=True):
            info_col, delete_col = st.columns([5, 1], vertical_alignment="center")
            info_col.markdown(f"**{profile['name']}**")
            info_col.caption(
                f"Date: {mapping.get('date')} ({profile['date_format']}) · Amount: {mapping.get('amount')} · "
                f"Description: {mapping.get('description')} · Debit/credit: {mapping.get('direction') or '—'} · "
                f"Delimiter '{profile['delimiter']}', decimal '{profile['decimal_sep']}'"
            )
            if delete_col.button("Delete", key=f"delete_profile_{profile['id']}", icon=":material/delete:"):
                delete_bank_profile(profile["id"])
                after_write(f"Deleted profile '{profile['name']}'.", icon=":material/delete:")


def render() -> None:
    """Manage types, categories, keyword rules and bank profiles."""
    page_header("Settings", "Organize categories, automate categorization, and manage saved bank formats.")
    categories_tab, rules_tab, profiles_tab = st.tabs(
        [":material/category: Types & categories", ":material/rule: Keyword rules", ":material/account_balance: Bank profiles"]
    )
    with categories_tab:
        render_categories_tab()
    with rules_tab:
        render_rules_tab()
    with profiles_tab:
        render_profiles_tab()


if __name__ == "__main__":
    render()
