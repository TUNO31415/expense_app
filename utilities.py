import datetime

def check_number(input):
    try:
        float(input)
        return True
    except:
        return False

def format_date(lis):
    try:
        date = datetime.datetime(int(lis[2]), int(lis[1]), int(lis[0]))
        return date
    except:
        raise Exception("not correct format of date")

