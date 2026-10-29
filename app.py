from __future__ import annotations

import streamlit as st

from db import init_db


st.set_page_config(page_title="Expense Tracker", page_icon=":material/account_balance_wallet:", layout="wide")


def main() -> None:
    """Initialize the database and route to the selected page."""
    init_db()
    pages = [
        st.Page("pages/home.py", title="Home", icon=":material/home:", default=True),
        st.Page("pages/import_data.py", title="Import", icon=":material/upload_file:"),
        st.Page("pages/expenses.py", title="Expenses", icon=":material/receipt_long:"),
        st.Page("pages/dashboard.py", title="Dashboard", icon=":material/monitoring:"),
        st.Page("pages/settings.py", title="Settings", icon=":material/tune:"),
    ]
    st.navigation(pages).run()


if __name__ == "__main__":
    main()
