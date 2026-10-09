from __future__ import annotations

import streamlit as st

from db import (
    add_category,
    add_rule,
    add_type,
    delete_category,
    list_categories,
    list_rules,
    list_types,
    update_category,
)


def render() -> None:
    """Manage expense types, categories, and keyword rules."""
    st.title("Categories")

    st.subheader("Types")
    with st.form("add_type_form"):
        type_name = st.text_input("New type name")
        submitted = st.form_submit_button("Add type")
        if submitted and type_name.strip():
            add_type(type_name)
            st.rerun()

    types = list_types()
    if types:
        type_table = [{"id": item["id"], "name": item["name"]} for item in types]
        st.dataframe(type_table, use_container_width=True, hide_index=True)

    st.subheader("Categories")
    with st.form("add_category_form"):
        selected_type = st.selectbox("Type", options=list_types(), format_func=lambda item: item["name"])
        category_name = st.text_input("Category name")
        submitted = st.form_submit_button("Add category")
        if submitted and category_name.strip() and selected_type:
            add_category(category_name, selected_type["id"])
            st.rerun()

    categories = list_categories()
    for category in categories:
        with st.container():
            col_name, col_move, col_delete = st.columns([2, 2, 1])
            with col_name:
                st.write(f"{category['type_name']} / {category['name']}")
            with col_move:
                if st.button("Move", key=f"move_cat_{category['id']}"):
                    new_type = st.selectbox(
                        "Select target type",
                        options=list_types(),
                        format_func=lambda item: item["name"],
                        key=f"move_type_{category['id']}",
                    )
                    if new_type:
                        update_category(category["id"], type_id=new_type["id"])
                        st.rerun()
            with col_delete:
                if st.button("Delete", key=f"delete_cat_{category['id']}"):
                    if delete_category(category["id"]):
                        st.rerun()
                    else:
                        st.warning("This category is still in use and cannot be deleted.")

    st.subheader("Keyword rules")
    st.caption(
        "Keywords match anywhere in the description, without case sensitivity. "
        "The longest matching keyword wins; a higher priority number only breaks ties "
        "between matches of equal length. Any matching ignore rule excludes the transaction."
    )
    with st.form("add_rule_form"):
        rule_keyword = st.text_input("Keyword")
        rule_category = st.selectbox("Target category", options=[{"id": None, "name": "Ignore"}, *list_categories()], format_func=lambda item: item["name"] if item else "Ignore")
        action = st.selectbox("Action", options=["categorize", "ignore"])
        priority = st.number_input(
            "Priority",
            min_value=0,
            step=1,
            help="Only used when matching keywords have the same length; larger numbers win.",
        )
        if st.form_submit_button("Add rule"):
            if rule_keyword.strip():
                category_id = rule_category["id"] if rule_category and rule_category.get("id") is not None else None
                if action == "ignore":
                    category_id = None
                add_rule(rule_keyword, category_id=category_id, action=action, priority=priority)
                st.rerun()

    rules = list_rules()
    if rules:
        st.dataframe(rules, use_container_width=True, hide_index=True)


if __name__ == "__main__":
    render()
