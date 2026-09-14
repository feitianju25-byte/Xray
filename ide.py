start = input()
end = input()
def is_leap(year):
    return year % 400 == 0 or (year % 4 == 0 and year % 100 != 0)
def day_in_month(month, year):
    day = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    if month == 2 and is_leap(year):
        return 29
    else:
        return day[month]
start_year = int(start[:4])
end_year = int(end[:4])
count = 0
for year in range(start_year, end_year+1):
    years = str(year)
    month = years[3]+years[2]
    day = years[1]+years[0]
    if (int(month) <= 12) and int(day)<=day_in_month(month, year):
        count +=1
print(count)