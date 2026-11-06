import pandas as pd
import numpy as np


def get_energy_tier_string(frame):
    master_list = []
    for per in frame['Period'].unique():
        sublist = []
        subframe = frame[frame['Period'] == per]
        for tier in subframe['Tier']:
            ind = subframe[(subframe['Period'] == per) & (subframe['Tier'] == tier)].index
            rate = subframe.loc[ind, 'Rate $/kWh'].values[0] + subframe.loc[ind, 'Adjustments $/kWh'].values[0]
            limit = subframe.loc[ind, 'Max Usage'].values[0]
            sublist.append([limit, rate])

        master_list.append(sublist)
        
    return str(master_list)


energy_file = 'test_rate_frame.csv'

e_frame = pd.read_csv(energy_file)

print(e_frame)

etier_str = get_energy_tier_string(e_frame)

print(etier_str)