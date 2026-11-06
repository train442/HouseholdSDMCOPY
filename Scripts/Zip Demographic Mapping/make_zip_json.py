import os
import sys

import geopandas as gpd
import pandas as pd
import numpy as np

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))  # repo root
import Setup as sp
"""
This file combines the data on the zip directory file with the data from the ZCTA file from the census bureau to make a 
combined zip geopandas frame json.
"""

zip_shp = 'Model Data/Shape Files/cb_2018_us_zcta510_500k.shp'

zip_gpd = gpd.read_file(zip_shp)

zip_dir = pd.read_csv('Model Data/new_zip_directory.csv', dtype={'Zip Code': str})

zip_dir.loc[zip_dir['Area (sq mi)'] < .1, 'Area (sq mi)'] = 0

agi_frame = pd.read_csv('Archive/DataFiles/21incyallagi.csv',
                        encoding="ISO-8859-1",
                        usecols=['STATE', 'COUNTYNAME', 'agi_stub', 'N1', 'A00100'])


def get_avg_agi(county_name):
    global agi_frame
    red_agi = agi_frame[agi_frame['COUNTYNAME'] == county_name]
    if len(red_agi) != 0:
        tot_returns = np.sum(red_agi['N1'].to_numpy())
        tot_agi = np.sum(red_agi['A00100'].to_numpy())
        avg_agi = tot_agi/tot_returns
    else:
        avg_agi = np.nan
    return avg_agi


diffs = []
pop_dens = []
avg_agis = []

for index, row in zip_gpd.iterrows():
    zip_code = row['ZCTA5CE10']
    zip_code = str(int(zip_code))
    dir_row = zip_dir[zip_dir['Zip Code'] == zip_code]

    if len(dir_row) != 0:
        try:
            possible_utils = eval(dir_row['Utilities'].values[0])
            possible_eias = eval(dir_row['EIA Codes'].values[0])

            # Find country data
            county = dir_row['County'].values[0] + ' County'
            avg_agis.append(get_avg_agi(county_name=county))

            util_dict = sp.get_best_utility(utils=possible_utils, eias=possible_eias)

            diffs.append(np.round(util_dict['Max Difference'], 5))
            try:
                dens = np.round(dir_row['Population'].values[0]/dir_row['Area (sq mi)'].values[0])
                dens = np.nan if dens == 0 else dens
            except ZeroDivisionError:
                dens = np.nan
            pop_dens.append(dens)
        except IndexError:
            print(f'Error with zip code: {zip_code}')
            diffs.append(np.nan)
            pop_dens.append(np.nan)
            avg_agis.append(np.nan)
    else:
        diffs.append(np.nan)
        pop_dens.append(np.nan)
        avg_agis.append(np.nan)

zip_gpd['Max Difference'] = diffs
zip_gpd['Density'] = pop_dens
zip_gpd['Avg AGI'] = avg_agis

zip_gpd.to_file(filename='Model Data/master_zip_geo.json', driver='GeoJSON')
