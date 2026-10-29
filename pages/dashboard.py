from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st

from db import get_expenses_df
from services.analytics import (
    average_metrics,
    monthly_spend_by_type,
    monthly_totals,
    period_bounds,
    period_display,
    prepare_expense_df,
    quarter_average_heatmap,
    spend_by_category,
    spend_by_type,
    top_n_with_other,
    top_share,
    total_spend,
    transaction_count,
    typical_month,
)
from ui.components import empty_state, fmt_eur, fmt_eur_whole, kpi_card, page_header
from ui.theme import ACCENT, MUTED, color_for_type, plotly_layout, type_color_map

PERIODS = ["3M", "6M", "12M", "This year", "All time", "Custom"]
TOP_CATEGORIES = 10
OTHER_LABEL = "Everything else"
AVG_COLUMN = "Avg / period"


@st.cache_data
def load_dashboard_data() -> pd.DataFrame:
    """Load and normalize the full expense table for dashboard use."""
    return prepare_expense_df(get_expenses_df())


def _period_filter(df: pd.DataFrame) -> tuple[pd.DataFrame, object, object]:
    """Filter by the period bar at the top of the page; return the rows and the chosen bounds."""
    data_min = df["date"].min().date()
    data_max = df["date"].max().date()
    preset = st.segmented_control("Period", PERIODS, default="12M", key="dashboard_period", label_visibility="collapsed") or "12M"
    if preset == "Custom":
        date_range = st.date_input("Date range", (data_min, data_max), min_value=data_min, max_value=data_max, format="DD/MM/YYYY")
        start, end = (date_range[0], date_range[-1]) if date_range else (data_min, data_max)
    else:
        start, end = period_bounds(preset, data_min, data_max)
    return df[df["date"].dt.date.between(start, end)], start, end


def _sidebar_filters(df: pd.DataFrame) -> pd.DataFrame:
    """Filter by the type and category multiselects in the sidebar."""
    with st.sidebar.expander("Filters", icon=":material/filter_list:", expanded=True):
        type_options = sorted(df["type"].dropna().unique().tolist())
        selected_types = st.multiselect("Types", options=type_options, default=type_options)
        category_options = sorted(df["category"].dropna().unique().tolist())
        selected_categories = st.multiselect("Categories", options=category_options, default=category_options)
    return df[df["type"].isin(selected_types) & df["category"].isin(selected_categories)]


def _section(title: str, caption: str | None = None) -> None:
    st.markdown(f"**{title}**")
    if caption:
        st.caption(caption)


def _chart(fig) -> None:
    st.plotly_chart(plotly_layout(fig), width="stretch")


def render_kpis(df: pd.DataFrame, start, end) -> None:
    """Render the KPI card row."""
    typical = typical_month(df, start, end)
    biggest_type, type_share = top_share(df, "type")
    biggest_category, category_share = top_share(df, "category")
    cols = st.columns(4)
    with cols[0]:
        kpi_card("Total spent", fmt_eur(total_spend(df)), delta=f"{transaction_count(df):,} transactions", delta_color="off")
    with cols[1]:
        kpi_card(
            "Typical month",
            fmt_eur(typical["mean"]),
            delta=f"median {fmt_eur(typical['median'])}",
            delta_color="off",
            help="Average of every month in the period, including months with no spending.",
        )
    with cols[2]:
        kpi_card("Biggest type", biggest_type or "—", delta=f"{type_share:.0%} of spend", delta_color="off")
    with cols[3]:
        kpi_card("Biggest category", biggest_category or "—", delta=f"{category_share:.0%} of spend", delta_color="off")


def render_monthly_trend(df: pd.DataFrame, start, end) -> None:
    """Stacked monthly bars by type, with a dashed line at the average month."""
    totals = monthly_totals(df, start, end)
    average = float(totals.mean()) if not totals.empty else 0.0
    caption = None
    if totals.any():
        caption = (
            f"Highest: {period_display(totals.idxmax())} ({fmt_eur_whole(totals.max())}) · "
            f"Lowest: {period_display(totals.idxmin())} ({fmt_eur_whole(totals.min())})"
        )
    _section("Monthly spending", caption)

    chart_df = monthly_spend_by_type(df)
    chart_df["month_date"] = pd.to_datetime(chart_df["month"])
    fig = px.bar(chart_df, x="month_date", y="amount_eur", color="type", barmode="stack", color_discrete_map=type_color_map(chart_df["type"].unique()))
    fig.update_traces(hovertemplate="%{x|%b %Y} · %{fullData.name}: €%{y:,.2f}<extra></extra>")
    fig.add_hline(
        y=average,
        line_dash="dash",
        line_color=MUTED,
        annotation_text=f"Avg {fmt_eur_whole(average)}",
        annotation_position="top left",
        annotation_font_color=MUTED,
    )
    fig.update_xaxes(tickformat="%b %Y", dtick="M1" if len(totals) <= 12 else None)
    fig.update_yaxes(tickprefix="€", tickformat=",.0f")
    _chart(fig)


def render_type_donut(df: pd.DataFrame) -> None:
    """Donut of spend by type, with the total in the centre."""
    _section("By type")
    chart_df = spend_by_type(df)
    fig = px.pie(chart_df, names="type", values="amount_eur", hole=0.6, color="type", color_discrete_map=type_color_map(chart_df["type"]))
    fig.update_traces(textinfo="percent+label", textposition="outside", hovertemplate="%{label}: €%{value:,.2f} (%{percent})<extra></extra>")
    fig.update_layout(
        showlegend=False,
        annotations=[dict(text=f"<b>{fmt_eur_whole(total_spend(df))}</b><br>total", showarrow=False, font_size=18)],
    )
    _chart(fig)


def render_category_bars(df: pd.DataFrame) -> None:
    """Ranked category bars, optionally narrowed to one type via pills."""
    _section("By category")
    type_options = spend_by_type(df)["type"].tolist()
    selected = st.pills("Type", ["All", *type_options], default="All", key="dashboard_breakdown_type", label_visibility="collapsed") or "All"
    rows = df if selected == "All" else df[df["type"] == selected]
    if rows.empty:
        st.info("No spending for this type in the selected period.")
        return

    chart_df = top_n_with_other(spend_by_category(rows), TOP_CATEGORIES, OTHER_LABEL)
    grand_total = chart_df["amount_eur"].sum()
    chart_df["label"] = [f"{fmt_eur_whole(value)} · {value / grand_total:.0%}" for value in chart_df["amount_eur"]]
    chart_df = chart_df.iloc[::-1]
    type_of = rows.groupby("category")["type"].first()
    fig = px.bar(chart_df, x="amount_eur", y="category", orientation="h", text="label")
    fig.update_traces(
        marker_color=[MUTED if category == OTHER_LABEL else color_for_type(type_of.get(category)) for category in chart_df["category"]],
        textposition="outside",
        cliponaxis=False,
        hovertemplate="%{y}: €%{x:,.2f}<extra></extra>",
    )
    fig.update_layout(height=max(320, 34 * len(chart_df)))
    fig.update_xaxes(visible=False)
    _chart(fig)


def render_breakdown(df: pd.DataFrame, start, end) -> None:
    """Where the money goes: type donut next to ranked category bars."""
    left, right = st.columns(2)
    with left.container(border=True):
        render_type_donut(df)
    with right.container(border=True):
        render_category_bars(df)


def _highlight_row_max(row: pd.Series) -> list[str]:
    """Tint the highest period cell in a row (ignores the Avg column)."""
    periods = row.drop(labels=[AVG_COLUMN])
    peak = periods.max()
    return [
        f"background-color: {ACCENT}33" if label != AVG_COLUMN and peak > 0 and value == peak else ""
        for label, value in row.items()
    ]



def render_average_table(df: pd.DataFrame, start, end) -> None:
    """Category-by-period totals, sorted by spend, with the average first and the peak highlighted."""
    _section("Typical spending by category", "Each cell is the total for that period; Avg includes periods with no spending.")
    period_label = st.segmented_control("Period", ["Quarter", "Month"], default="Quarter", key="average_period", label_visibility="collapsed")
    period = "month" if period_label == "Month" else "quarter"
    stats = average_metrics(df, period)
    if stats.empty:
        st.info("No data available to summarize.")
        return
    pivot = stats.pivot_table(index="category", columns="period", values="total", aggfunc="sum", fill_value=0.0)
    pivot = pivot.reindex(sorted(pivot.columns), axis=1)
    pivot.columns = [period_display(column) for column in pivot.columns]
    pivot.insert(0, AVG_COLUMN, pivot.mean(axis=1))
    pivot = pivot.loc[pivot.drop(columns=AVG_COLUMN).sum(axis=1).sort_values(ascending=False).index]
    pivot.loc["Total"] = pivot.sum()
    pivot.index.name = "Category"

    body = pd.IndexSlice[pivot.index[:-1], :]
    styled = (
        pivot.style.format(fmt_eur_whole)
        .apply(_highlight_row_max, axis=1, subset=body)
        .set_properties(subset=pd.IndexSlice[:, [AVG_COLUMN]], **{"font-weight": "600"})
        .set_properties(subset=pd.IndexSlice[["Total"], :], **{"font-weight": "600"})
    )
    st.dataframe(styled, width="stretch", height=min(38 * (len(pivot) + 1) + 3, 600))


def render_average_heatmap(df: pd.DataFrame, start, end) -> None:
    """Heatmap of quarterly spend per category, with euro labels in each cell."""
    _section("Quarterly heatmap", "Brighter cells mean more spending in that quarter.")
    heatmap = quarter_average_heatmap(df)
    heatmap = heatmap.loc[heatmap.sum(axis=1).sort_values(ascending=False).index]
    heatmap.columns = [period_display(column) for column in heatmap.columns]
    fig = px.imshow(heatmap, color_continuous_scale=["#1A1D27", ACCENT], aspect="auto", text_auto=",.0f")
    fig.update_traces(hovertemplate="%{y} · %{x}: €%{z:,.0f}<extra></extra>", texttemplate="€%{z:,.0f}")
    fig.update_layout(height=max(320, 36 * len(heatmap)), coloraxis_showscale=False)
    fig.update_xaxes(side="top")
    _chart(fig)


def _bordered(render_fn):
    """Wrap a widget in a bordered card."""
    def wrapped(df: pd.DataFrame, start, end) -> None:
        with st.container(border=True):
            render_fn(df, start, end)
    return wrapped


WIDGETS = [
    {"id": "monthly_trend", "title": "Monthly spending", "render_fn": _bordered(render_monthly_trend)},
    {"id": "breakdown", "title": "Where your money goes", "render_fn": render_breakdown},
    {"id": "averages_table", "title": "Typical spending by category", "render_fn": _bordered(render_average_table)},
    {"id": "average_heatmap", "title": "Quarterly heatmap", "render_fn": _bordered(render_average_heatmap)},
]


def render_dashboard() -> None:
    """Render the dashboard: period bar, KPI cards, then the registered widgets in order."""
    title_col, customize_col = st.columns([5, 1], vertical_alignment="bottom")
    with title_col:
        page_header("Dashboard", "Where your money goes, and what a typical month looks like.")
    with customize_col.popover("Customize", icon=":material/tune:", width="stretch"):
        st.caption("Show or hide charts")
        visible = {
            widget["id"]: st.checkbox(widget["title"], key=f"widget_{widget['id']}", value=True)
            for widget in WIDGETS
        }

    df = load_dashboard_data()
    if df.empty:
        empty_state("📊", "No expenses yet. Import a bank statement to see your trends.", "Import bank statement", "pages/import_data.py")
        return

    in_period, start, end = _period_filter(df)
    filtered = _sidebar_filters(in_period).reset_index(drop=True)
    st.caption(f"{start.day} {start:%b %Y} – {end.day} {end:%b %Y} · {transaction_count(filtered):,} transactions")
    if filtered.empty:
        empty_state("🔍", "No expenses match the current filters. Pick a longer period or broaden the types and categories in the sidebar.")
        return

    render_kpis(filtered, start, end)
    for widget in WIDGETS:
        if visible[widget["id"]]:
            widget["render_fn"](filtered, start, end)


def main() -> None:
    """Entry point for the dashboard page."""
    render_dashboard()


if __name__ == "__main__":
    main()
