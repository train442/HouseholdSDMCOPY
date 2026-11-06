"""
This script was made to add maximum and minimum coordinates to the state.csv file. It will read the zip directory,
filter for each state, then find the maximum and minimum latitude.
"""

import pandas as pd

state_file = '../../Model Data/states.csv'
zip_file = '../../Model Data/zip_directory.csv'

state_frame = pd.read_csv(state_file)
zip_frame = pd.read_csv(zip_file)

for index, row in state_frame.iterrows():
    st = row['Abbreviation']
    red_frame = zip_frame[zip_frame['State (Abbr)'] == st]

    long_min = min(red_frame['Longitude'])
    long_max = max(red_frame['Longitude'])
    lat_min = min(red_frame['Latitude'])
    lat_max = max(red_frame['Latitude'])

    state_frame.loc[index, 'Max Longitude'] = long_max
    state_frame.loc[index, 'Min Longitude'] = long_min
    state_frame.loc[index, 'Max Latitude'] = lat_max
    state_frame.loc[index, 'Min Latitude'] = lat_min


state_frame.to_csv('Model Data/states.csv', index=False)
