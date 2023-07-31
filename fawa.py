# helper funtions.
from openpyxl import load_workbook
import sqlite3

# check format of string is DDMMMYYYY
def isfawasheet(sheetname):
    if len(sheetname) != 9:
        return False
    day = sheetname[:2]
    month = sheetname[2:5]
    year = sheetname[5:]
    try:
        day = int(day)
        year = int(year)
    except:
        return False
    
    if month not in ['JAN', 'FEB', 'MAR', 'APR', 'MAY', 'JUN', 'JUL', 'AUG', 'SEP', 'OCT', 'NOV', 'DEC']:
        return False

    if year < 2023:
        return False

    return True


# given the excel file - read the sheets and insert data from the sheets into the database.
# sheets are of the format, DDMMMYYYY where DD = Day, MMM = Month, YYYY = Year.
# if the month/year combination already exists in the database, do not import it.
# returns:
#   None = failed to import
#   Integer = number of rows imported.
def importdata(filename):
    try:
        wb = load_workbook(filename, data_only=True)
    except:
        return None

    rows_imported = 0
    sheet_names = wb.sheetnames
    # for each sheet, if the sheet has the format MMYYYY, then this is a FAWA Statement sheet.
    # read the sheet.
    for sheet in sheet_names:
        if not isfawasheet(sheet):
            return False
        
        # start at row=1 and go to about 100.
        # if col=1 has an integer, then this is a member
        cur_row = 1