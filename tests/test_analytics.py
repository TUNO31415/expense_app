import pandas as pd

from services.analytics import (
    average_by_period,
    average_metrics,
    prepare_expense_df,
    quarter_average_heatmap,
    spend_by_category,
    spend_by_type,
    total_spend,
    transaction_count,
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
