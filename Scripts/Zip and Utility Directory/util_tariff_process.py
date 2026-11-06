import pandas as pd

# This script processes the raw utility tariff list (util_list.csv) and creates the filtered file with obsolete and
# non-residential tariffs removed

# run util_tariff_process.py to create utility files from the resulting file.


master_path = 'F:/Household Sim/HouseholdSim/Archive/DataFiles/util_file.csv'   # change to wherever util_file is.
# master list of all tariffs
master_util_list = pd.read_csv(master_path, parse_dates=['startdate', 'enddate'])

# get today's date
today = pd.to_datetime('today')

# we filter out the tariffs that have a recorded end date (ie, their obsolete) and are non-residential in nature

master_util_list = master_util_list[master_util_list.sector == 'Residential']
master_util_list = master_util_list.dropna(subset=['energyweekdayschedule'])
ids1 = master_util_list.index[master_util_list.enddate < today]
# ids2 = master_util_list.index[master_util_list.flatdemandunit.isin(['kVA', 'kVA daily', 'hp'])]
# ids3 = master_util_list.index[master_util_list.demandrateunit.isin(['kVA', 'kVA daily', 'hp'])]
ids2 = master_util_list.index[master_util_list.flatdemandunit.isin(['kVA', 'kVA daily'])]
ids3 = master_util_list.index[master_util_list.demandrateunit.isin(['kVA', 'kVA daily'])]
ids = ids1.append(ids2).append(ids3).sort_values()
filtered_util_list = master_util_list.drop(index=ids).sort_values(by=['eiaid'])

filtered_util_list.replace('', float('NaN'), inplace=True)
filtered_util_list.dropna(how='all', axis=1, inplace=True)

filtered_util_list.to_csv('util_tariffs_residential.csv', index=False)

# print(filtered_util_list)
