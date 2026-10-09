from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st

from db import get_expenses_df
from services.analytics import (
    average_by_period,
    average_metrics,
    average_per_month,
    monthly_spend_by_type,
    prepare_expense_df,
    quarter_average_heatmap,
    spend_by_category,
    spend_by_type,
    top_category,
    total_spend,
    transaction_count,
)

TYPE_COLORS = {
    "Housing": "#1f77b4",
    "Food": "#ff7f0e",
    "Transport": "#2ca02c",
    "Leisure": "#d62728",
    "Health": "#9467bd",
    "Other": "#8c564b",
}


@st.cache_data
def load_dashboard_data() -> pd.DataFrame:
    """Load and normalize the full expense table for dashboard use."""
    return prepare_expense_df(get_expenses_df())


def _apply_sidebar_filters(df: pd.DataFrame) -> pd.DataFrame:
    """Filter the dashboard dataset using the shared sidebar controls."""
    if df.empty:
        return df

    min_date = df["date"].min().date()
    max_date = df["date"].max().date()
    date_range = st.sidebar.date_input("Date range", (min_date, max_date), min_value=min_date, max_value=max_date)
    start_date, end_date = date_range

    years = sorted(df["date"].dt.year.unique().tolist())
    selected_years = st.sidebar.multiselect("Years", options=years, default=years)
    type_options = sorted(df["type"].dropna().unique().tolist())
    selected_types = st.sidebar.multiselect("Types", options=type_options, default=type_options)
    category_options = sorted(df["category"].dropna().unique().tolist())
    selected_categories = st.sidebar.multiselect("Categories", options=category_options, default=category_options)

    filtered = df.copy()
    filtered = filtered[filtered["date"].dt.date.between(start_date, end_date)]
    filtered = filtered[filtered["date"].dt.year.isin(selected_years)]
    filtered = filtered[filtered["type"].isin(selected_types)]
    filtered = filtered[filtered["category"].isin(selected_categories)]
    return filtered.reset_index(drop=True)


def render_total_spend(df: pd.DataFrame) -> None:
    """Render the total spend KPI card."""
    st.metric("Total spent", f"€{total_spend(df):,.2f}")


def render_transaction_count(df: pd.DataFrame) -> None:
    """Render the transaction count KPI card."""
    st.metric("Transactions", f"{transaction_count(df):,}")


def render_average_per_month(df: pd.DataFrame) -> None:
    """Render the average-per-month KPI card."""
    st.metric("Avg / month", f"€{average_per_month(df):,.2f}")


def render_top_category(df: pd.DataFrame) -> None:
    """Render the top category KPI card."""
    top = top_category(df)
    st.metric("Top category", top if top else "—")


def render_type_donut(df: pd.DataFrame) -> None:
    """Render a donut chart of spend by type."""
    if df.empty:
        st.info("No data for the selected filters. Add or import transactions to populate this chart.")
        return
    chart_df = spend_by_type(df)
    fig = px.pie(chart_df, names="type", values="amount_eur", hole=0.45, color="type", color_discrete_map=TYPE_COLORS)
    fig.update_layout(margin=dict(t=0, b=0, l=0, r=0))
    st.plotly_chart(fig, use_container_width=True)


def render_type_bar(df: pd.DataFrame) -> None:
    """Render a bar chart of spend by type."""
    if df.empty:
        return
    chart_df = spend_by_type(df)
    fig = px.bar(chart_df, x="type", y="amount_eur", color="type", color_discrete_map=TYPE_COLORS)
    st.plotly_chart(fig, use_container_width=True)


def render_category_bar(df: pd.DataFrame) -> None:
    """Render a horizontal bar chart of spend by category."""
    if df.empty:
        return
    chart_df = spend_by_category(df).copy()
    type_lookup = df.groupby("category")["type"].first().to_dict()
    chart_df["type"] = chart_df["category"].map(type_lookup)
    color_map = {category: TYPE_COLORS.get(category_type, "#636363") for category, category_type in type_lookup.items()}
    fig = px.bar(chart_df, x="amount_eur", y="category", orientation="h", color="category", color_discrete_map=color_map)
    st.plotly_chart(fig, use_container_width=True)


def render_type_category_sunburst(df: pd.DataFrame) -> None:
    """Render a sunburst of type-to-category spending."""
    if df.empty:
        return
    fig = px.sunburst(df, path=["type", "category"], values="amount_eur", color="type", color_discrete_map=TYPE_COLORS)
    st.plotly_chart(fig, use_container_width=True)


def render_monthly_trends(df: pd.DataFrame) -> None:
    """Render a monthly stacked bar chart by type."""
    if df.empty:
        return
    chart_df = monthly_spend_by_type(df)
    fig = px.bar(chart_df, x="month", y="amount_eur", color="type", barmode="stack", color_discrete_map=TYPE_COLORS)
    st.plotly_chart(fig, use_container_width=True)


def render_average_table(df: pd.DataFrame) -> None:
    """Display the average-by-period pivot table for a selected period."""
    if df.empty:
        st.info("No data available to summarize.")
        return
    period_label = st.segmented_control("Period", ["Quarter", "Month"], default="Quarter", key="average_period")
    period = "month" if period_label == "Month" else "quarter"
    stats = average_metrics(df, period)
    if stats.empty:
        st.info("No data available to summarize.")
        return
    pivot = stats.pivot_table(index="category", columns="period", values="total", aggfunc="sum", fill_value=0.0)
    pivot["Average"] = pivot.mean(axis=1)
    st.dataframe(pivot.style.format("{:.2f}"), use_container_width=True)


def render_average_heatmap(df: pd.DataFrame) -> None:
    """Render a quarter heatmap of average spend per category."""
    if df.empty:
        return
    heatmap = quarter_average_heatmap(df)
    fig = px.imshow(heatmap)
    st.plotly_chart(fig, use_container_width=True)


WIDGETS = [
    {"id": "type_overview", "title": "Type spending", "tab": "Overview", "render_fn": lambda df: (render_type_donut(df), render_type_bar(df))},
    {"id": "category_breakdown", "title": "Category spending", "tab": "Categories", "render_fn": lambda df: (render_category_bar(df), render_type_category_sunburst(df))},
    {"id": "trends_monthly", "title": "Monthly trend", "tab": "Trends", "render_fn": lambda df: render_monthly_trends(df)},
    {"id": "averages_table", "title": "Average table", "tab": "Averages", "render_fn": lambda df: render_average_table(df)},
    {"id": "average_heatmap", "title": "Average heatmap", "tab": "Averages", "render_fn": lambda df: render_average_heatmap(df)},
]


def render_dashboard() -> None:
    """Render the main dashboard using a registry of widgets and shared sidebar filters."""
    st.title("Dashboard")
    df = load_dashboard_data()
    filtered = _apply_sidebar_filters(df)

    if df.empty:
        st.info("No expenses yet. Head to the Import page to add your first batch.")
        return

    if filtered.empty:
        st.info("No expenses match the current filters. Adjust the sidebar to broaden the date or category selection.")
        return

    st.markdown("### Summary")
    kpi_cols = st.columns(4)
    with kpi_cols[0]:
        render_total_spend(filtered)
    with kpi_cols[1]:
        render_transaction_count(filtered)
    with kpi_cols[2]:
        render_average_per_month(filtered)
    with kpi_cols[3]:
        render_top_category(filtered)

    tabs = st.tabs(["Overview", "Categories", "Trends", "Averages"])
    tab_lookup = {tab_name: idx for idx, tab_name in enumerate(["Overview", "Categories", "Trends", "Averages"]) }

    for widget in WIDGETS:
        visible = st.sidebar.checkbox(widget["title"], key=f"widget_{widget['id']}", value=True)
        if not visible:
            continue
        idx = tab_lookup[widget["tab"]]
        with tabs[idx]:
            widget["render_fn"](filtered)


def main() -> None:
    """Entry point for the dashboard page."""
    render_dashboard()


if __name__ == "__main__":
    main()
