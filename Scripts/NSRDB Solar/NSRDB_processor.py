import DataProcessing as dp
import os
import pandas as pd

city_frame = pd.read_csv('../../Model Data/city_list.csv')

raw_path = 'E:/Solar Profiles/Unprocessed/'
processed_path = '../../City Data/Solar Data/'
year = 2018


state_list = [state for state in os.listdir(raw_path) if os.path.isdir(os.path.join(raw_path, state))]

for state in state_list:
    if not os.path.exists(processed_path + state):
        os.makedirs(processed_path + state)
    file_list = os.listdir(raw_path + '/' + state)
    for file in file_list:
        old_solar_path = raw_path + state + '/' + file
        new_solar_path = processed_path + state + '/' + file[0:-4] + '_5min.csv'
        city = file.split('_')[1]
        sub_state = city_frame[city_frame['State'] == state]
        sub_city = sub_state[sub_state['City'] == city]
        time_adjust = -1 * int(sub_city['Off UTC'].values[0])
        print(time_adjust)
        if not os.path.exists(new_solar_path):
            dp.process_NSRDB_profile(old_solar_path, new_solar_path, time_adjust)



