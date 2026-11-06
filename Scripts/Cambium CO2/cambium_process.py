import pandas as pd
import DataProcessing as dp
import os



state_file = '/Model Data/states.csv'
file_path = '/City Data/CO2 Profiles/Cambium 2021/Raw Data'
new_path = '/City Data/CO2 Profiles/Cambium 2021/Processed'

file_list = [file for file in os.listdir(file_path)]

for file in file_list:
    file_split = file.split('_')
    state = file_split[-2]
    year = file_split[-1]
    old_file_path = file_path + '/' + file + '/' + file + '.csv'
    new_file_path = new_path + '/' + state + '_Cambium_' + year + '.csv'
    dp.process_cambium(old_file_path, new_file_path)