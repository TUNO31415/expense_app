from datetime import date

import pandas as pd

from services.analytics import (
    average_by_period,
    average_metrics,
    month_summary,
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


def test_calendar_quarter_grouping_and_totals():
    df = pd.DataFrame(
        [
            {"date": "2024-01-10", "type": "Food", "category": "Groceries", "amount_eur": 20.00},
            {"date": "2024-03-15", "type": "Food", "category": "Restaurants", "amount_eur": 30.00},
            {"date": "2024-04-05", "type": "Transport", "category": "Fuel", "amount_eur": 40.00},
            {"date": "2024-06-20", "type": "Transport", "category": "Public transport", "amount_eur": 15.00},
        ]
    )
    prepared = prepare_expense_df(df)

    type_totals = spend_by_type(prepared)
    category_totals = spend_by_category(prepared)

    assert sorted(type_totals["type"].tolist()) == ["Food", "Transport"]
    assert total_spend(prepared) == 105.0
    assert transaction_count(prepared) == 4
    assert category_totals["amount_eur"].sum() == 105.0


def test_averages_include_empty_months_in_range():
    df = pd.DataFrame(
        [
            {"date": "2024-01-10", "type": "Food", "category": "Groceries", "amount_eur": 100.0},
            {"date": "2024-03-15", "type": "Food", "category": "Groceries", "amount_eur": 50.0},
        ]
    )
    result = average_by_period(prepare_expense_df(df), "month")
    assert len(result) == 3
    assert result["total"].sum() == 150.0
    assert set(result["period"].tolist()) == {"2024-01", "2024-02", "2024-03"}
    assert result.loc[result["period"] == "2024-02", "total"].iloc[0] == 0.0


def test_average_metrics_include_months_without_spending():
    df = pd.DataFrame(
        [
            {"date": "2024-01-10", "type": "Food", "category": "Groceries", "amount_eur": 100.0},
            {"date": "2024-03-15", "type": "Food", "category": "Groceries", "amount_eur": 50.0},
        ]
    )

    result = average_metrics(prepare_expense_df(df), "month")

    assert result["period"].tolist() == ["2024-01", "2024-02", "2024-03"]
    assert result["total"].tolist() == [100.0, 0.0, 50.0]


def test_average_metrics_heatmap_and_pivots():
    df = pd.DataFrame(
        [
            {"date": "2024-01-10", "type": "Food", "category": "Groceries", "amount_eur": 100.0},
            {"date": "2024-04-10", "type": "Food", "category": "Groceries", "amount_eur": 200.0},
            {"date": "2024-02-12", "type": "Transport", "category": "Fuel", "amount_eur": 50.0},
        ]
    )
    pivot = average_metrics(prepare_expense_df(df), "quarter")
    heatmap = quarter_average_heatmap(prepare_expense_df(df))

    assert pivot["total"].sum() == 350.0
    assert set(heatmap.columns) >= {"2024-Q1", "2024-Q2"}


def test_month_summary_compares_with_previous_month():
    df = pd.DataFrame(
        [
            {"date": "2024-01-10", "type": "Food", "category": "Groceries", "amount_eur": 20.00},
            {"date": "2024-02-03", "type": "Food", "category": "Groceries", "amount_eur": 10.00},
            {"date": "2024-02-15", "type": "Fun", "category": "Cinema", "amount_eur": 25.00},
        ]
    )

    summary = month_summary(df, "2024-02")

    assert summary["total"] == 35.0
    assert summary["count"] == 2
    assert summary["top_category"] == "Cinema"
    assert summary["previous_total"] == 20.0
    assert month_summary(df, "2024-01")["previous_total"] == 0.0


def test_period_bounds_use_whole_months_anchored_on_latest_expense():
    data_min, data_max = date(2024, 1, 15), date(2025, 3, 10)

    assert period_bounds("3M", data_min, data_max) == (date(2025, 1, 1), data_max)
    assert period_bounds("12M", data_min, data_max) == (date(2024, 4, 1), data_max)
    assert period_bounds("This year", data_min, data_max) == (date(2025, 1, 1), data_max)
    assert period_bounds("All time", data_min, data_max) == (data_min, data_max)


def test_period_bounds_clamp_to_first_expense():
    data_min, data_max = date(2025, 2, 20), date(2025, 3, 10)

    assert period_bounds("12M", data_min, data_max) == (data_min, data_max)
    assert period_bounds("This year", data_min, data_max) == (data_min, data_max)


def test_monthly_totals_and_typical_month_count_empty_months():
    df = prepare_expense_df(
        pd.DataFrame(
            [
                {"date": "2024-01-10", "type": "Food", "category": "Groceries", "amount_eur": 100.0},
                {"date": "2024-01-20", "type": "Food", "category": "Groceries", "amount_eur": 20.0},
                {"date": "2024-03-15", "type": "Food", "category": "Groceries", "amount_eur": 60.0},
            ]
        )
    )

    totals = monthly_totals(df, date(2024, 1, 1), date(2024, 4, 30))

    assert totals.to_dict() == {"2024-01": 120.0, "2024-02": 0.0, "2024-03": 60.0, "2024-04": 0.0}
    assert typical_month(df, date(2024, 1, 1), date(2024, 4, 30)) == {"mean": 45.0, "median": 30.0}
    assert typical_month(df.iloc[0:0], date(2024, 1, 1), date(2024, 2, 29)) == {"mean": 0.0, "median": 0.0}


def test_top_share_returns_largest_group_and_share():
    df = pd.DataFrame(
        [
            {"type": "Fixed", "category": "Rent", "amount_eur": 75.0},
            {"type": "Variable", "category": "Food", "amount_eur": 25.0},
        ]
    )

    assert top_share(df, "category") == ("Rent", 0.75)
    assert top_share(df.iloc[0:0], "type") == ("", 0.0)


def test_top_share_tie_picks_first_alphabetically():
    df = pd.DataFrame(
        [
            {"type": "B", "category": "x", "amount_eur": 50.0},
            {"type": "A", "category": "y", "amount_eur": 50.0},
        ]
    )

    assert top_share(df, "type") == ("A", 0.5)


def test_top_n_with_other_folds_tail():
    totals = pd.DataFrame({"category": ["a", "b", "c", "d"], "amount_eur": [40.0, 30.0, 20.0, 10.0]})

    folded = top_n_with_other(totals, 2)

    assert folded["category"].tolist() == ["a", "b", "Everything else"]
    assert folded["amount_eur"].tolist() == [40.0, 30.0, 30.0]
    assert top_n_with_other(totals, 10)["category"].tolist() == ["a", "b", "c", "d"]


def test_period_display_labels():
    assert period_display("2026-Q1") == "Q1 2026"
    assert period_display("2026-03") == "Mar 2026"
    assert period_display("2026") == "2026"
