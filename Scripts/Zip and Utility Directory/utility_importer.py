import os
import sys
import warnings
import time

import pandas as pd

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))  # repo root, for usurdb_read
import usurdb_read as usr

"""
The purpose of this script was to generate and update utility files by pulling from the USURDB database.

NOTE: Ensure this script and the tariff file are both in the main directory before running.
Also if you want to update all utility files, be sure to change eia_start variable to 0.
 
"""

update_current = True  # update utility files already present. Set to True if you wish to redo all files.
overwrite_files = True #overwrite all utility files
# new_utility_path = 'Utilities New/'
new_utility_path ='Utilities/'
eia_start = 20885  # adding eia start value in case you only want to redo some of the files.
warnings.filterwarnings("ignore", category=FutureWarning)

master_util = pd.read_csv('Model Data/util_to_zip_fixed.csv')

base_url = 'https://apps.openei.org/USURDB/rate/view/'
base_url2 = 'https://apps.openei.org/IURDB/rate/view/'

cols = ['Name', 'OpenEI Id', 'Utility', 'Verified', 'Start Date', 'End Date', 'Supersedes', 'Net Meter Policy',
        'TimeOfUse', 'Tiered', 'Demand', 'Monthly Charge', 'Minimum Charge', 'Time-of-Use Rates', 'Max Difference',
        'Weekday Schedule - Energy', 'Weekend Schedule - Energy', 'Demand Rates', 'Weekday Schedule - Power',
        'Weekend Schedule - Power']
i = 0
for index, row in master_util.iterrows():
    util_name = row['Utility Name']
    eia = row['EIA Code']
    new_file = f'{util_name}_{eia}_tariffs.csv'
    if int(eia) >= eia_start:
        if (os.path.exists(new_utility_path + new_file)) and not overwrite_files:  # file exists
            util_frame = pd.read_csv(new_utility_path + new_file)
            already_exists = True
        else:  # file does not exist, and needs fresh creation
            util_frame = pd.DataFrame(columns=cols)
            already_exists = False

        if not already_exists or update_current:
            initial_frame = usr.api_read(str(eia))

            timeout = 'label' not in initial_frame.columns
            if timeout:
                cooldown = 120
                while timeout:
                    print(f'Timed Out, Waiting {cooldown} seconds.....')
                    time.sleep(cooldown)
                    initial_frame = usr.api_read(str(eia))
                    timeout = 'label' not in initial_frame.columns
                    if timeout:
                        cooldown += 60
                    if cooldown > 6000:
                        print('just try again later')
                        Exception('Cooldown got too big. Try again later')
            for tariff_id in initial_frame['label'].values:
                if tariff_id not in util_frame['OpenEI Id'].values:
                    try:
                        tariff_data = usr.read_tariff(base_url + tariff_id)
                    except AttributeError:
                        tariff_data = usr.read_tariff(base_url2 + tariff_id, default_url=False)
                    tariff_data['OpenEI Id'] = tariff_id
                    new_frame = pd.DataFrame(data=tariff_data, index=[0])
                    util_frame = pd.concat([util_frame, new_frame], ignore_index=True)
            util_frame.to_csv(new_utility_path + new_file, index=False)
        print(i, util_name, eia)
        time.sleep(.1)
    i += 1



