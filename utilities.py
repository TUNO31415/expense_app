import numpy as np
from datetime import date, datetime


def check_number(input):
    try:
        float(input)
        return True
    except:
        return False

def format_date(lis):
    try:
        date = datetime(int(lis[2]), int(lis[1]), int(lis[0]))
        return date
    except:
        raise Exception("not correct format of date")


def format_date_discord(lis):
    try:
        date = datetime(int(lis[0]), int(lis[1]), int(lis[2]))
        return date
    except:
        raise Exception("not correct format of date")

def calculate_yearly(data):
    # pick only distinct years
    unique_years = np.unique([date.year for date, amount in data])
    res = []
    for current_year in unique_years:
        yearly_sum = np.sum([amount for date, amount in data if date.year == current_year])
        res.append((current_year, round(yearly_sum, 2)))
    return res

def calculate_monthly(data):
    unique_month = list(set([(date.year, date.month) for date, amount in data]))
    res = []

    for current in unique_month:
        monthly_sum = np.sum([amount for date, amount in data if date.year == current[0] and date.month == current[1]])
        res.append((current[0], current[1], round(monthly_sum,2)))
    return res


def categorize(cat_num):
    cat = {
        0 : "Food",
        1 : "Transportation",
        2 : "Extertainment",
        3 : "Necessities",
        4 : "Housing expense"
    }
    return cat.get(cat_num, "Others")


def categorize_discord(opt):
    cat = {
        'f' : "Food",
        't' : "Transportation",
        'e' : "Extertainment",
        'n' : "Necessities",
        'h' : "Housing expense"
    }
    return cat.get(opt, "Others")


def month_to_name(num):
    cat = {
        1 : "Jan",
        2 : "Feb",
        3 : "Mar",
        4 : "Apr",
        5 : "May",
        6 : "Jun",
        7 : "Jul",
        8 : "Aug",
        9 : "Sep",
        10 : "Oct",
        11 : "Nov",
        12 : "Dec"
    }
    return cat.get(num)