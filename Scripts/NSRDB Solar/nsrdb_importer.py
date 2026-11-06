import DataProcessing as dp
import pandas as pd
import numpy as np
import h5pyd
from scipy.spatial import cKDTree
import os

city_frame = pd.read_csv('../../Model Data/city_list.csv')

solar_path = 'E:/Solar Profiles/Unprocessed'
year = 2018
metadata, coord_tree = dp.get_NSRDB_metadata(year)

for ind in city_frame.index:
    city = city_frame.loc[ind, 'City']
    state = city_frame.loc[ind, 'State']
    new_folder_path = os.path.join(solar_path, state).replace('\\', '/')
    if not os.path.exists(new_folder_path):
        os.makedirs(new_folder_path)
    filename = state + '_' + city + '_GHI_' + str(year) + '.csv'
    new_file_path = os.path.join(new_folder_path, filename).replace('\\', '/')
    if not os.path.exists(new_file_path):
        coords = (city_frame.loc[ind, 'Latitude'], city_frame.loc[ind, 'Longitude'])
        city_index = dp.get_NSRDB_index(coords, coord_tree)

        ghi_set = metadata['ghi']
        temp_set = metadata['air_temperature']
        time_index = pd.to_datetime(metadata['time_index'][...].astype(str))

        ghi_series = ghi_set[:, city_index]/ghi_set.attrs['psm_scale_factor']
        temp_series = temp_set[:, city_index] / temp_set.attrs['psm_scale_factor']

        solar_dict = {'Time': time_index, 'GHI(W/m^2)': ghi_series, 'Temp(C)': temp_series}
        solar_frame = pd.DataFrame(data=solar_dict)
        solar_frame.to_csv(new_file_path, index=False)


