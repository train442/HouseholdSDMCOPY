"""
This script is designed to read zip code information from the website 'zipdatamaps.com'. This resource
provides principal city names, states, counties, coordinates, timezones, and population data for all/most valid
zipcodes in the United States. It will append the timezone and population data to the zip_directory.csv file such
that the pools generated for the simulation can have their respective populations tallied.
"""
import requests.exceptions

import DataProcessing as dp
import pandas as pd
import numpy as np
import time

from_original = False
periodically_save = True  # periodically update csv
save_interval = 2500  # how often you want to save (every XX zipcodes)

if from_original:
    zip_directory = pd.read_csv('Model Data/zip_directory.csv', dtype={'Zip Code': str})

    zip_directory['Time Zone'] = np.nan
    zip_directory['Population'] = np.nan
    zip_directory['Area (sq mi)'] = np.nan
else:
    zip_directory = pd.read_csv('Model Data/new_zip_directory.csv', dtype={'Zip Code': str})

error_list = []

for i in range(len(zip_directory)):
    zip_code = zip_directory.loc[i, 'Zip Code']
    if (pd.isna(zip_directory.loc[i, 'Population'])) | (zip_directory.loc[i, 'Time Zone'] == 'PST'):  # zipcode not
        # loaded
        try:
            zip_dict = dp.zip_scrape(zip_code=zip_code)
            zip_directory.loc[i, 'Time Zone'] = zip_dict['Time Zone']
            zip_directory.loc[i, 'Population'] = zip_dict['Population']
            zip_directory.loc[i, 'Area (sq mi)'] = zip_dict['Area']
            print(zip_dict)
            time.sleep(.05)
        except (IndexError, KeyError, ValueError, requests.exceptions.SSLError):
            print(zip_code, ' ERROR')
            error_list.append(zip_code)
        if ((i % save_interval) == 0) & periodically_save:
            print('--------FILE UPDATED--------------')
            zip_directory.to_csv('new_zip_directory.csv', index=False)
    else:
        zip_code = zip_directory.loc[i, 'Zip Code']
        print(zip_code, 'PASSED')

zip_directory.to_csv('new_zip_directory.csv', index=False)

print(error_list)
a = 1
