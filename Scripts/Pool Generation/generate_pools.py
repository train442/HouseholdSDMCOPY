"""
This script is designed to create a csv called zip_pools.csv, which contains all unique pools of zipcodes that have the
same input information. Namely:
- Same reference city (to match house load and solar data)
- Same state
- Same Utility
- Same Tariff schedule from utility.

It will iterate through zip_directory.csv from Model Data directory, and find the above information. The Utility and
Tariff will be the best utility for TOU, meaning the greatest price differential between peak and off-peak pricing.
IF no TOU schedule is available from any of the utilities servicing a zip code, then the pool is null.

The zip_pools csv will have the following columns:
- State: The actual state of the zipcodes
- Utility: The name of the utility
- EIA: The EIA code for the Utility
- Tariff: The name of the tariff schedule
- Reference City: The name of the reference city for which the load and solar data are pulled
- TOU: Whether there is TOU tariff available. If this field is false, then the pool is not to be used.
- Zips Included: The number of zip codes included in this pool
- Coverage: The percent of the total number of zip codes in the state covered by the pool.

"""
import os
import sys

import numpy as np
import pandas as pd

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))  # repo root
import Setup as sp

# Load zip_directory file
# zip_dir = pd.read_csv('Model Data/zip_directory.csv', dtype={'Zip Code': str})
zip_dir = pd.read_csv('Model Data/new_zip_directory.csv', dtype={'Zip Code': str})
# Load reference_city list

states_unique = zip_dir['State (Abbr)'].unique()
states_population = [np.sum(zip_dir[(zip_dir['State (Abbr)'] == state)]['Population'].to_numpy()) for state in
                     states_unique]
states_num_zips = [len(zip_dir[(zip_dir['State (Abbr)'] == state)]) for state in states_unique]
states_areas = [np.sum(zip_dir[(zip_dir['State (Abbr)'] == state)]['Area (sq mi)'].to_numpy()) for state in
                states_unique]

state_dict = {'State': states_unique,
              'Population': states_population,
              'Area': states_areas,
              'Num Zips': states_num_zips}
state_frame = pd.DataFrame(data=state_dict)

ref_cities = pd.read_csv('Model Data/city_list_refined.csv')

# Instantiate pools dataframe

columns = ['State', 'Time Zone', 'Reference City', 'Reference State', 'Ref Time Zone', 'Utility', 'Tariff', 'TOU',
           'Price Differential ($)', 'Num Zips', 'Zips Included', 'Population', 'Area (sq mi)', 'Largest Zip',
           'Largest Zip Pop', 'Zip Percent', 'Area Percent', 'Pop Percent']
pool_frame = pd.DataFrame(columns=columns)


def get_ref_city(city_name: str, state_abbr: str, coord: tuple[float, float]):
    # check if city is already in reference list
    if ((city_name in ref_cities['City'].unique()) &
            (state_abbr in ref_cities[ref_cities['City'] == city_name].loc[:, 'State'].unique())):
        ind_city = ref_cities[(ref_cities['State'] == state_abbr) & (ref_cities['City'] == city_name)].index.values[0]
    else:
        ind_city = sp.closest_index(coord=coord, coord_array=ref_cities[['Latitude', 'Longitude']].to_numpy())
    ref_dict = {'Reference City': ref_cities.loc[ind_city, 'City'],
                'Reference State': ref_cities.loc[ind_city, 'State'],
                'Reference Time Zone': ref_cities.loc[ind_city, 'Time Zone']}
    return ref_dict


def flatten_list(old_list: list):
    if type(old_list[0]) is str:
        return old_list
    else:
        new_list = [x for xs in old_list for x in xs]
        return new_list


for index, row in zip_dir.iterrows():
    zip_code = row['Zip Code'].zfill(5)
    city = row['City']  # name of locality NOT reference city
    state = row['State (Abbr)']
    lat: float = row['Latitude']
    long: float = row['Longitude']
    area = row['Area (sq mi)']
    pop = row['Population']
    tz = row['Time Zone']
    # We assess reference city
    reference_dict = get_ref_city(city_name=city, state_abbr=state, coord=(lat, long))

    possible_utils = eval(row['Utilities'])
    possible_eias = eval(row['EIA Codes'])

    util_dict = sp.get_best_utility(utils=possible_utils, eias=possible_eias)

    if util_dict['Utility'] is None:
        util_name = 'N/A'
        tariff_name = 'N/A'
        util_file = 'N/A'
        best_commute = 'basic_commute'
    else:
        util_name = util_dict['Utility']
        tariff_name = util_dict['Tariff']
        util_file = util_dict['File']


    # we check if pool is already exists in the pools dataframe
    sub_frame = pool_frame[(pool_frame['State'] == state) &
                           (pool_frame['Time Zone'] == tz) &
                           (pool_frame['Reference City'] == reference_dict['Reference City']) &
                           (pool_frame['Reference State'] == reference_dict['Reference State']) &
                           (pool_frame['Utility'] == util_name)]
    if len(sub_frame) == 0:  # pool not yet added
        if (util_file != 'N/A'):
            try:
                trf = sp.create_tariff(util_file=util_file, tariff_name=tariff_name)
            except SyntaxError:
                print(util_file)
                Exception(f'Error loading tariff for zipcode: {zip_code}')
            if trf is not None:
                best_commute = sp.get_best_commute(trf)
            else:
                best_commute = 'basic_commute'
        zips = [zip_code.zfill(5)]
        data = {'State': state,
                'Time Zone': tz,
                'Reference City': reference_dict['Reference City'],
                'Reference State': reference_dict['Reference State'],
                'Ref Time Zone': reference_dict['Reference Time Zone'],
                'Utility': util_name,
                'Utility File': util_file,
                'Tariff': tariff_name,
                'TOU': util_dict['TOU'],
                'Price Differential ($)': np.round(util_dict['Max Difference'], 5),
                'Best Commute':best_commute,
                'Num Zips': 1,
                'Coverage': 0,
                'Zips Included': zips,
                'Area (sq mi)': area,
                'Population': pop,
                'Largest Zip': zip_code.zfill(5),
                'Largest Zip Pop': pop
                }
        to_add = pd.DataFrame(data=data, index=[len(pool_frame)])
        pool_frame = pd.concat([pool_frame, to_add], ignore_index=True, axis=0)
    else:
        ind = sub_frame.index
        ind2 = ind[0]
        pool_frame.loc[ind, 'Num Zips'] += 1
        pool_frame.loc[ind, 'Area (sq mi)'] += area
        pool_frame.loc[ind, 'Population'] += pop
        zip_list = pool_frame.loc[ind, 'Zips Included'].to_list()
        zip_list = flatten_list(zip_list)
        zip_list.append(zip_code.zfill(5))
        # pool_frame.loc[ind, 'Zips Included'] = zip_list
        # pool_frame.iloc[ind, 10] = zip_list
        pool_frame.at[ind2, 'Zips Included'] = zip_list
        if pop > pool_frame.loc[ind2, 'Largest Zip Pop']:
            pool_frame.loc[ind2, 'Largest Zip Pop'] = pop
            pool_frame.loc[ind2, 'Largest Zip'] = zip_code.zfill(5)

    print(zip_code, reference_dict)

# go back and find percentages

for index, row in pool_frame.iterrows():
    state = row['State']
    state_ind = state_frame[state_frame['State'] == state].index[0]

    pool_frame.loc[index, 'Zip Percent'] = (np.round(row['Num Zips'] / state_frame.loc[state_ind, 'Num Zips'],
                                                     4) * 100)
    pool_frame.loc[index, 'Area Percent'] = np.round(row['Area (sq mi)'] / state_frame.loc[state_ind, 'Area'],
                                                     4) * 100
    pool_frame.loc[index, 'Pop Percent'] = np.round(row['Population'] / state_frame.loc[state_ind, 'Population'],
                                                    4) * 100


pool_frame = pool_frame.round({'Area (sq mi)': 2})

pool_frame.to_csv('pool_test.csv', index=False)
