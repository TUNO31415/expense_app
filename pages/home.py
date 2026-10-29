from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd
import plotly.express as px
import streamlit as st

from db import get_expenses_df, get_latest_import_time
from services.analytics import month_summary, prepare_expense_df, spend_by_category, spend_by_type
from ui.components import empty_state, fmt_eur, kpi_card, page_header
from ui.theme import color_for_type, plotly_layout, type_color_map


@st.cache_data
def load_home_data() -> pd.DataFrame:
    """Load and normalize the expense table for the home overview."""
    return prepare_expense_df(get_expenses_df())


def _days_since(timestamp: str | None) -> int | None:
    """Whole days since a SQLite UTC timestamp, or None when there is none."""
    if not timestamp:
        return None
    moment = datetime.fromisoformat(timestamp).replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - moment).days


def _render_kpis(summary: dict, last_import: str | None) -> None:
    total = summary["total"]
    previous = summary["previous_total"]
    delta = f"{fmt_eur(total - previous)} vs last month" if previous else None
    days = _days_since(last_import)

    cols = st.columns(4)
    with cols[0]:
        # Spending more than last month shows red, less shows green.
        kpi_card("Spent", fmt_eur(total), delta=delta, delta_color="inverse")
    with cols[1]:
        kpi_card("Transactions", f"{summary['count']:,}")
    with cols[2]:
        kpi_card("Top category", summary["top_category"] or "—")
    with cols[3]:
        kpi_card(
            "Last bank import",
            "Never" if days is None else ("Today" if days == 0 else f"{days} days ago"),
            help="When you last imported a bank statement.",
        )


def _render_charts(month_rows: pd.DataFrame) -> None:
    left, right = st.columns(2)
    with left.container(border=True):
        st.markdown("**By type**")
        by_type = spend_by_type(month_rows)
        fig = px.pie(
            by_type,
            names="type",
            values="amount_eur",
            hole=0.6,
            color="type",
            color_discrete_map=type_color_map(by_type["type"]),
        )
        fig.update_traces(textinfo="percent", hovertemplate="%{label}: €%{value:,.2f}<extra></extra>")
        st.plotly_chart(plotly_layout(fig), width="stretch")
    with right.container(border=True):
        st.markdown("**Top 5 categories**")
        top = spend_by_category(month_rows).head(5).iloc[::-1]
        type_of = month_rows.groupby("category")["type"].first()
        fig = px.bar(top, x="amount_eur", y="category", orientation="h", text_auto=",.2f")
        fig.update_traces(
            marker_color=[color_for_type(type_of.get(category)) for category in top["category"]],
            hovertemplate="%{y}: €%{x:,.2f}<extra></extra>",
        )
        st.plotly_chart(plotly_layout(fig), width="stretch")


def _render_recent(df: pd.DataFrame) -> None:
    with st.container(border=True):
        header, link = st.columns([3, 1], vertical_alignment="center")
        header.markdown("**Recent expenses**")
        with link:
            st.page_link("pages/expenses.py", label="All expenses", icon=":material/arrow_forward:")
        recent = df.sort_values(["date", "id"], ascending=False).head(10)
        st.dataframe(
            recent[["date", "description", "category", "type", "amount_eur"]],
            hide_index=True,
            width="stretch",
            column_config={
                "date": st.column_config.DateColumn("Date", format="D MMM YYYY"),
                "description": st.column_config.TextColumn("Description", width="large"),
                "category": "Category",
                "type": "Type",
                "amount_eur": st.column_config.NumberColumn("Amount", format="€%.2f"),
            },
        )


def render() -> None:
    """Render the month overview with the shortcut to the monthly bank import."""
    page_header("This month", "Where your money went, and what's next.")
    df = load_home_data()

    if df.empty:
        empty_state(
            "💸",
            "No expenses yet. Import your first bank statement to get started.",
            "Import bank statement",
            "pages/import_data.py",
        )
        return

    months = sorted(df["month"].unique(), reverse=True)
    month_col, button_col = st.columns([3, 1], vertical_alignment="bottom")
    month = month_col.selectbox(
        "Month",
        options=months,
        index=0,
        format_func=lambda value: pd.Period(value, freq="M").strftime("%B %Y"),
    )
    if button_col.button("Import bank statement", type="primary", icon=":material/upload_file:", width="stretch"):
        st.switch_page("pages/import_data.py")

    summary = month_summary(df, month)
    _render_kpis(summary, get_latest_import_time())
    _render_charts(summary["rows"])
    _render_recent(df)


if __name__ == "__main__":
    render()
