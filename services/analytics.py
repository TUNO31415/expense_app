from __future__ import annotations

from typing import Iterable

import pandas as pd


def _quarter_from_date(date_value: object) -> str:
    """Convert a date-like value into its calendar-quarter label, e.g. 2024-Q1."""
    ts = pd.to_datetime(date_value)
    return f"{ts.year}-Q{((ts.month - 1) // 3) + 1}"


def _month_from_date(date_value: object) -> str:
    """Convert a date-like value into YYYY-MM text."""
    ts = pd.to_datetime(date_value)
    return ts.strftime("%Y-%m")


def _period_label(value: object, period: str) -> str:
    """Create a consistent label for month, quarter, or year period grouping."""
    if period == "month":
        return pd.Period(value, freq="M").strftime("%Y-%m")
    if period == "quarter":
        val = pd.Period(value, freq="Q")
        return f"{val.year}-Q{val.quarter}"
    return str(pd.Period(value, freq="Y").year)


def prepare_expense_df(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize the expense table for aggregation."""
    if df.empty:
        return df.copy()

    working = df.copy()
    working["date"] = pd.to_datetime(working["date"])
    working["amount_eur"] = pd.to_numeric(working["amount_eur"], errors="coerce").fillna(0.0)
    working["type"] = working["type"].fillna("Other")
    working["category"] = working["category"].fillna("Uncategorized")
    working["quarter"] = working["date"].map(_quarter_from_date)
    working["month"] = working["date"].map(_month_from_date)
    return working


def total_spend(df: pd.DataFrame) -> float:
    """Return total spend across all filtered rows."""
    return float(pd.to_numeric(df["amount_eur"], errors="coerce").sum()) if not df.empty else 0.0


def transaction_count(df: pd.DataFrame) -> int:
    """Return the number of transactions in the filtered dataset."""
    return int(len(df))


def average_per_month(df: pd.DataFrame) -> float:
    """Return total spend divided by the number of months in the dataset."""
    if df.empty:
        return 0.0
    months = df["date"].dt.to_period("M").nunique()
    return float(total_spend(df) / max(months, 1))


def top_category(df: pd.DataFrame) -> str:
    """Return the category with the largest spend or an empty string if empty."""
    if df.empty:
        return ""
    category_totals = df.groupby("category")["amount_eur"].sum().sort_values(ascending=False)
    return str(category_totals.index[0])


def spend_by_type(df: pd.DataFrame) -> pd.DataFrame:
    """Return type totals sorted descending."""
    if df.empty:
        return pd.DataFrame(columns=["type", "amount_eur"])
    grouped = df.groupby("type", as_index=False)["amount_eur"].sum().sort_values("amount_eur", ascending=False)
    grouped.columns = ["type", "amount_eur"]
    return grouped.reset_index(drop=True)


def spend_by_category(df: pd.DataFrame) -> pd.DataFrame:
    """Return category totals sorted descending."""
    if df.empty:
        return pd.DataFrame(columns=["category", "amount_eur"])
    grouped = df.groupby("category", as_index=False)["amount_eur"].sum().sort_values("amount_eur", ascending=False)
    grouped.columns = ["category", "amount_eur"]
    return grouped.reset_index(drop=True)


def monthly_spend_by_type(df: pd.DataFrame) -> pd.DataFrame:
    """Aggregate spend by month and type, including zero-filled months in the filtered range."""
    if df.empty:
        return pd.DataFrame(columns=["month", "type", "amount_eur"])

    working = prepare_expense_df(df)
    start = working["date"].min()
    end = working["date"].max()
    months = pd.period_range(start=start, end=end, freq="M")
    types = sorted(working["type"].dropna().unique())

    summary = working.groupby([working["date"].dt.to_period("M"), "type"], as_index=False)["amount_eur"].sum()
    summary.columns = ["month", "type", "amount_eur"]
    summary["month"] = summary["month"].astype(str)

    index = pd.MultiIndex.from_product([sorted([str(item) for item in months]), types], names=["month", "type"])
    full = pd.DataFrame(index=index, columns=["amount_eur"]).fillna(0.0)
    for _, row in summary.iterrows():
        full.loc[(row["month"], row["type"]), "amount_eur"] = row["amount_eur"]

    result = full.reset_index().rename(columns={"amount_eur": "amount_eur"})
    return result[["month", "type", "amount_eur"]].reset_index(drop=True)


def average_by_period(df: pd.DataFrame, period: str = "quarter") -> pd.DataFrame:
    """Return category totals and average spend for a selected period, filling missing periods with zero."""
    if df.empty:
        return pd.DataFrame(columns=["category", "period", "total", "average"])

    working = prepare_expense_df(df)
    start = working["date"].min()
    end = working["date"].max()

    if period == "month":
        periods = pd.period_range(start=start, end=end, freq="M")
        group_key = "month"
    elif period == "quarter":
        periods = pd.period_range(start=start, end=end, freq="Q")
        group_key = "quarter"
    else:
        periods = pd.period_range(start=start, end=end, freq="Y")
        group_key = "year"

    generated = []
    for category in sorted(working["category"].unique()):
        category_df = working[working["category"] == category].copy()
        if period == "month":
            grouped = category_df.groupby("month", as_index=False)["amount_eur"].sum()
        elif period == "quarter":
            grouped = category_df.groupby("quarter", as_index=False)["amount_eur"].sum()
        else:
            grouped = category_df.groupby(category_df["date"].dt.year, as_index=False)["amount_eur"].sum()
            grouped.columns = ["period", "total"]
            grouped["period"] = grouped["period"].astype(str)

        if period in {"month", "quarter"}:
            grouped.columns = ["period", "total"]

        for item in periods:
            current = _period_label(item, period)
            total = float(grouped.loc[grouped["period"].astype(str) == current, "total"].sum()) if not grouped.empty else 0.0
            generated.append({"category": category, "period": current, "total": total, "average": total})

    result = pd.DataFrame(generated)
    if result.empty:
        return pd.DataFrame(columns=["category", "period", "total", "average"])
    return result


def average_metrics(df: pd.DataFrame, period: str = "quarter") -> pd.DataFrame:
    """Return a pivot-like table of category totals and average values across the selected period."""
    if df.empty:
        return pd.DataFrame(columns=["category", "period", "total", "average"])

    working = prepare_expense_df(df)
    start = working["date"].min()
    end = working["date"].max()

    if period == "month":
        period_values = pd.period_range(start=start, end=end, freq="M")
        period_key = "month"
    elif period == "quarter":
        period_values = pd.period_range(start=start, end=end, freq="Q")
        period_key = "quarter"
    else:
        period_values = pd.period_range(start=start, end=end, freq="Y")
        period_key = "year"

    rows = []
    for category in sorted(working["category"].unique()):
        category_df = working[working["category"] == category].copy()
        for item in period_values:
            label = _period_label(item, period)
            if period_key == "month":
                values = category_df[category_df["month"] == label]
            elif period_key == "quarter":
                values = category_df[category_df["quarter"] == label]
            else:
                values = category_df[category_df["date"].dt.year.astype(str) == label]
            total = float(values["amount_eur"].sum()) if not values.empty else 0.0
            rows.append({"category": category, "period": label, "total": total, "average": total})

    return pd.DataFrame(rows)


def quarter_average_heatmap(df: pd.DataFrame) -> pd.DataFrame:
    """Return a category-by-quarter heatmap-ready table with zeros for missing quarters."""
    if df.empty:
        return pd.DataFrame()

    working = prepare_expense_df(df)
    start = working["date"].min()
    end = working["date"].max()
    periods = pd.period_range(start=start, end=end, freq="Q")
    pivot = working.pivot_table(index="category", columns="quarter", values="amount_eur", aggfunc="sum", fill_value=0.0)
    for item in periods:
        quarter = _period_label(item, "quarter")
        if quarter not in pivot.columns:
            pivot[quarter] = 0.0
    return pivot.reindex(sorted(pivot.columns), axis=1)


def type_and_category_totals(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return totals by type and category."""
    return spend_by_type(df), spend_by_category(df)
