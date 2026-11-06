"""
This script is meant to refine the raw pools file given by the generate_pools.py script. IT removes any N/A utility
rows (not TOU) and can apply criteria to remove insignificant pools (ie, population, area, etc.)
"""

import pandas as pd
import numpy as np

raw_file = 'pool_test.csv'
save_file = True
# Refining Criteria
remove_states = ['AK', 'HI', 'DC']  # we are not considering Alaska or Hawaii at this point

by_pop = True
take_top = False #take only the top by a given metric (population)
take_range = False # take range of values
top_num = 50  # number of pools selected from the top
range = [16, 61]

area_crit = 0  # greater than 10% of state area
pop_crit = 0  # greater than 10% of state population
zip_crit = 0  # greater than 10% of state zip codes
differential_crit = 0  # price differential greater than given price.

orig_frame = pd.read_csv(raw_file, dtype={'Largest Zip': str, 'Population': int})

base_frame = orig_frame[~orig_frame['State'].isin(remove_states)]  # remove ineligible states


included_states = base_frame['State'].unique()
total_pop = np.sum(base_frame['Population'].to_numpy())
total_zip = np.sum(base_frame['Num Zips'].to_numpy())
total_area = np.sum(base_frame['Area (sq mi)'].to_numpy())

not_tou_frame = orig_frame[pd.isna(orig_frame['Utility'])]
not_tou_pop = np.sum(not_tou_frame['Population'].to_numpy())
not_tou_zip = np.sum(not_tou_frame['Num Zips'].to_numpy())
not_tou_area = np.sum(not_tou_frame['Area (sq mi)'].to_numpy())

tou_pop = total_pop - not_tou_pop
tou_zip = total_zip - not_tou_zip
tou_area = total_area - not_tou_area

loss_frame = base_frame[(base_frame['Zip Percent'] < zip_crit) &
                        (base_frame['Area Percent'] < area_crit) &
                        (base_frame['Pop Percent'] < pop_crit) &
                        (base_frame['Price Differential ($)'] < differential_crit)]

# remove based on criteria
base_frame = base_frame[(base_frame['Zip Percent'] >= zip_crit) |
                        (base_frame['Area Percent'] >= area_crit) |
                        (base_frame['Pop Percent'] >= pop_crit) |
                        (base_frame['Price Differential ($)'] >= differential_crit)]

#remove stray pools with zero population
base_frame = base_frame[base_frame['Population'] > 50000]

base_frame = base_frame[~pd.isna(base_frame['Utility'])]

base_frame = base_frame.sort_values(by=['State']).reset_index(drop=True)

remain_pop = np.sum(base_frame['Population'].to_numpy())
remain_zip = np.sum(base_frame['Num Zips'].to_numpy())
remain_area = np.sum(base_frame['Area (sq mi)'].to_numpy())

a = 1

base_frame = base_frame.round({'Zip Percent': 2,
                               'Area Percent': 2,
                               'Pop Percent': 2})

if by_pop:
    base_frame = base_frame.sort_values(by='Population', ascending=False)

    if take_top:
        top_num = min(top_num, len(base_frame))
        base_frame = base_frame[0:top_num]
        file_name = f'top{top_num}_pools_by_population.csv'
    elif take_range:
        top = max(0, range[0])
        bot = min(len(base_frame), range[1])
        base_frame = base_frame[top:bot]
        file_name = f'top{top}_to_{bot-1}_pools_by_population.csv'
    else:
        file_name = 'refined_pools.csv'
else:
    file_name = 'refined_pools.csv'

if save_file:
    base_frame.to_csv(file_name, index=False)

remain_states = base_frame['State'].unique()

lost_states = [state for state in included_states if (state not in remain_states)]

print(lost_states)
