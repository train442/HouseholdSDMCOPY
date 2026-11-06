"""
This script processes raw parquets from ResStock into 5 minute timestep files. This script will also update the
city_list.csv file with any new cities added. Run the load summarizer script after to update the city load lookup
files. Then run the city_list_update script to complete city info for that file.

Note: Ensure that the paths point to the correct locations.
"""
from pyarrow import ArrowInvalid

import DataProcessing as dp
import os
import pandas as pd

city_path = '../../Model Data/city_list.csv'

master_sheet = pd.read_csv('../../Archive/DataFiles/baseline_metadata_and_annual_results_simp.csv')  # from content root

city_frame = pd.read_csv(city_path)  # from content root

raw_path = 'E:/Load Profiles/Unprocessed/Parquets'  # change to match current computer or raw data location
processed_path = 'E:/Load Profiles/Processed/Parquets'  # change to match current computer or raw data location

state_list = [state for state in os.listdir(raw_path) if os.path.isdir(os.path.join(raw_path, state))]

added_new_city = False  #  will flip to True if new city line gets added to city file

for state in state_list:
    city_list = [city for city in os.listdir(raw_path + '/' + state) if os.path.isdir(os.path.join(raw_path + '/' + state, city))]
    # print(state, city_list)
    for city in city_list:
        not_in_city_file = city_frame[(city_frame.City == city) & (city_frame.State == state)].empty
        if not_in_city_file:
            city_frame.loc[len(city_frame.index)] = [state, city, None, None, None, None]
            added_new_city = True

        parq_list = [parq for parq in os.listdir(raw_path + '/' + state + '/' + city) if parq[-8:] == '.parquet']
        print(city)
        for parq in parq_list:
            file_path = os.path.join(raw_path, state, city, parq).replace('\\', '/')
            bld_id = parq.split('.')[0]
            new_parq = bld_id + '_5min.parquet'
            new_folder_path = os.path.join(processed_path, state, city).replace('\\', '/')
            if not os.path.exists(new_folder_path):
                os.makedirs(new_folder_path)
            new_file_path = os.path.join(new_folder_path, new_parq).replace('\\', '/')
            # print(file_path, new_path)
            if not os.path.exists(new_file_path):
                # print(bld_id)
                try:
                    dp.process_resstock_load(file_path, new_file_path)
                except ArrowInvalid:
                    print(bld_id)

if added_new_city:
    city_frame = city_frame.sort_values(['State', 'City'], ascending=[True, True])

city_frame.to_csv(city_path, index=False)
# print(state_list)
# print(city_list)
