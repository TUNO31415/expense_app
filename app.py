from __future__ import annotations

import streamlit as st

from db import init_db


st.set_page_config(page_title="Expense Tracker", page_icon="💸", layout="wide")


def main() -> None:
    """Initialize the app and show the landing page."""
    init_db()
    st.title("Expense Tracker")
    st.markdown(
        """
        Manage expenses, imports, categories, and spending trends from the pages in the sidebar.
        """
    )
    st.info("Use the sidebar to navigate to the app pages.")


if __name__ == "__main__":
    main()
