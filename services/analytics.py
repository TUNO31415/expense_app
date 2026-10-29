from __future__ import annotations

from datetime import date
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


def month_summary(df: pd.DataFrame, month: str) -> dict[str, object]:
    """Summarize one YYYY-MM month, with the previous month's total for comparison."""
    working = prepare_expense_df(df)
    if working.empty:
        current = working
        previous_total = 0.0
    else:
        current = working[working["month"] == month]
        previous_month = (pd.Period(month, freq="M") - 1).strftime("%Y-%m")
        previous_total = total_spend(working[working["month"] == previous_month])
    return {
        "month": month,
        "rows": current,
        "total": total_spend(current),
        "count": transaction_count(current),
        "top_category": top_category(current),
        "previous_total": previous_total,
    }


def type_and_category_totals(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return totals by type and category."""
    return spend_by_type(df), spend_by_category(df)


PERIOD_PRESETS = {"3M": 3, "6M": 6, "12M": 12}


def period_bounds(preset: str, data_min: date, data_max: date) -> tuple[date, date]:
    """Return the (start, end) dates for a period preset, anchored on the latest expense, not today."""
    if preset in PERIOD_PRESETS:
        first_month = pd.Period(data_max, freq="M") - (PERIOD_PRESETS[preset] - 1)
        start = first_month.start_time.date()
    elif preset == "This year":
        start = date(data_max.year, 1, 1)
    else:
        start = data_min
    return max(start, data_min), data_max


def monthly_totals(df: pd.DataFrame, start: object = None, end: object = None) -> pd.Series:
    """Return total spend per YYYY-MM month, zero-filled across start..end (default: the data's range)."""
    if df.empty and (start is None or end is None):
        return pd.Series(dtype=float)
    start = df["date"].min() if start is None else start
    end = df["date"].max() if end is None else end
    months = [str(item) for item in pd.period_range(start=start, end=end, freq="M")]
    totals = df.groupby(df["date"].dt.to_period("M").astype(str))["amount_eur"].sum() if not df.empty else pd.Series(dtype=float)
    return totals.reindex(months, fill_value=0.0).astype(float)


def typical_month(df: pd.DataFrame, start: object = None, end: object = None) -> dict[str, float]:
    """Return the mean and median monthly spend, counting months without spending as zero."""
    totals = monthly_totals(df, start, end)
    if totals.empty:
        return {"mean": 0.0, "median": 0.0}
    return {"mean": float(totals.mean()), "median": float(totals.median())}


def top_share(df: pd.DataFrame, column: str) -> tuple[str, float]:
    """Return the largest group in `column` and its share of total spend (0..1)."""
    if df.empty:
        return "", 0.0
    totals = df.groupby(column)["amount_eur"].sum().sort_values(ascending=False, kind="stable")
    grand_total = totals.sum()
    return str(totals.index[0]), float(totals.iloc[0] / grand_total) if grand_total else 0.0


def top_n_with_other(totals: pd.DataFrame, n: int, label: str = "Everything else") -> pd.DataFrame:
    """Keep the first n rows of a sorted totals table and fold the rest into one `label` row."""
    if len(totals) <= n:
        return totals.reset_index(drop=True)
    key, value = totals.columns[0], totals.columns[1]
    rest = pd.DataFrame([{key: label, value: float(totals[value].iloc[n:].sum())}])
    return pd.concat([totals.head(n), rest], ignore_index=True)


def period_display(label: str) -> str:
    """Turn a period label into friendly text: 2026-Q1 -> Q1 2026, 2026-03 -> Mar 2026."""
    text = str(label)
    if "-Q" in text:
        year, quarter = text.split("-Q")
        return f"Q{quarter} {year}"
    if len(text) == 7 and text[4] == "-":
        return pd.Period(text, freq="M").strftime("%b %Y")
    return text
