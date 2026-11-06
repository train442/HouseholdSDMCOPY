import pandas as pd
import os
import sys

sys.path.append('../..')
import DataProcessing as dp

# This script reads the filtered utility tariff list (util_tariffs_residential.csv) and creates files for each
# individual utility with the nomenclature [name]_[eia]_tariffs.csv. These files list all the (not obsolete) tariffs
# provided by that utility.
#
# NOTE: the tier/period-parsing logic previously duplicated here and in processTariffs.py now lives in
# DataProcessing.usurdb_row_to_tariff_fields / DataProcessing.parse_usurdb_rate_structure.

# read in utility list with names and eia codes (util_to_zip_fixed.csv)

util_directory = pd.read_csv('../../Model Data/util_to_zip_fixed.csv', dtype={'EIA Code': str})

# read in filtered utility tariff list with each tariff

tariff_directory = pd.read_csv('../../Archive/DataFiles/util_tariffs_residential.csv', dtype={'eiaid': str})

# new file path -- update this to point at this machine's Utilities directory before running.

new_path = 'D:/Bras Research/pythonProject/Utilities/'

# create list for utils and eias missing from util_directory. Meaning these didn't come up in the zip scrape of the
# util database but are in the list of approved rates downloaded from it. Which is dumb, but par for the course.

missing_utils = []
missing_eias = []
# begin iterating through tariff list
lim = len(tariff_directory)
for i in range(lim):
    row = tariff_directory.loc[i]
    util_eia = row['eiaid']

    # find utility name within util_directory given the eia code
    try:
        ind = util_directory.index[util_directory['EIA Code'] == util_eia].values[0]
        util_name = util_directory.loc[ind, 'Utility Name']
    except IndexError:
        print(i, util_eia)
        util_name = tariff_directory.iloc[i, 5]
        util_name = util_name.replace('/', ' ').replace('.', ' ')
        print(util_name)
        missing_utils.append(util_name)
        missing_eias.append(util_eia)
    tariff_name = tariff_directory.iloc[i, 2]
    openei_id = tariff_directory.iloc[i, 0]  # reference ID in openei database

    util_file = new_path + util_name + '_' + util_eia + '_tariffs.csv'

    row_dict = dp.usurdb_row_to_tariff_fields(row)
    row_dict['Name'] = tariff_name
    row_dict['OpenEI Id'] = openei_id

    try:
        dp.append_tariff_row(util_file, row_dict)
    except OSError:
        print(i, util_file)
    if i % 500 == 0:
        print(str(i / len(tariff_directory) * 100) + '%')

missing_frame = pd.DataFrame(data={'Utility Name': missing_utils, 'EIA Code': missing_eias})
