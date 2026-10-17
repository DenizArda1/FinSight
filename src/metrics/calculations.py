def calculate_margin(income, revenue):
    if revenue <= 0:
        raise ValueError("Revenue must be positive.")
    return income / revenue

def calculate_growth(previous_value, current_value):
    if previous_value <= 0:
        raise ValueError("Previous value cannot be zero or negative")
    elif current_value < 0:
        raise ValueError("Current value cannot be negative")
    
    return (current_value / previous_value) - 1

def calculate_cagr(start_value, end_value, periods):
    if start_value <= 0:
        raise ValueError("Start value cannot be zero or negative")
    elif end_value < 0:
        raise ValueError("End value cannot be negative")
    elif type(periods) is not int or periods <= 0:
        raise ValueError("Periods must be a positive integer value")
    
    return (end_value / start_value) ** (1 / periods) - 1
    


def index_rows_by_period(rows):
    rows_by_period = {}
    for row in rows:
        period = (row["start"], row["end"])
        if period in rows_by_period:
            raise ValueError("Duplicate period found.")
        rows_by_period[period] = row
    return rows_by_period
