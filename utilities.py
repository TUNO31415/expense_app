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

def calculate_yearly(data):
    # pick only distinct years
    unique_years = np.unique([date.year for date, amount in data])
    res = []
    for current_year in unique_years:
        yearly_sum = np.sum([amount for date, amount in data if date.year == current_year])
        res.append(yearly_sum)
    return res

def calculate_monthly(data):
    return