import ast
import pandas as pd
import time
from bs4 import BeautifulSoup as bs
import requests

# this file checks the zip codes that were viable from the utility database (zips_to_util) and compares them to the
# previous master zip file (zipcodes2) to see which zip codes are unaccounted for

# zips from utility database
util_zips = pd.read_csv('../../Model Data/zip_to_util_fixed.csv', dtype={'Zip Code': str})

# converters={'Utilities': ast.literal_eval, 'EIA Codes': ast.literal_eval}

# original master zip file
prev_zip = pd.read_csv('../DataFiles/zipCodes2.csv', dtype={'postal code': str})

# converters={'Utility': ast.literal_eval, 'EIA Code': ast.literal_eval}

# list of zip codes in zip_to_util file. We check if zips in master file (zipcodes2.csv) are in this list and record
# the ones that aren't
check_zips = util_zips['Zip Code'].values

missing_zips = []

for i in range(len(prev_zip)):
    zip_to_check = prev_zip.loc[i, 'postal code']
    if zip_to_check not in check_zips:
        missing_zips.append(zip_to_check)

print(missing_zips)

missing_zips_frame = pd.DataFrame(data={'Zip Code': missing_zips})
missing_zips_frame.to_csv('no_util_zips.csv', index=False)

# list of zip_codes in zip_to_util that are not in master

missing_zips_master = []
check_zips_master = prev_zip['postal code'].values

for i in range(len(util_zips)):
    zip_to_check = util_zips.loc[i, 'Zip Code']
    if zip_to_check not in check_zips_master:
        missing_zips_master.append(zip_to_check)

print(missing_zips_master)

missing_zips_frame_master = pd.DataFrame(data={'Zip Code': missing_zips_master})
missing_zips_frame_master.to_csv('no_master_zips.csv', index=False)
