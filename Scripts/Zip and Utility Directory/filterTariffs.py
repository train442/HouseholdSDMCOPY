import pandas as pd

# This script filters the master tariff list into residential only rates, sorted by eia number


util_file = '../../Old Utility Scripts/util_list_sorted.csv'

today = pd.to_datetime('today')
print(today)

master_list = pd.read_csv(util_file, parse_dates=['enddate'])

print(master_list.shape)
print(master_list.iloc[7, 5])
print(type(master_list.iloc[7, 5]))

master_list = master_list[master_list.sector == 'Residential']
master_list = master_list.dropna(subset=['energyweekdayschedule'])
ids1 = master_list.index[master_list.enddate < today]
ids2 = master_list.index[master_list.flatdemandunit.isin(['kVA', 'kVA daily', 'hp'])]
ids3 = master_list.index[master_list.demandrateunit.isin(['kVA', 'kVA daily', 'hp'])]
ids = ids1.append(ids2).append(ids3).sort_values()
# ids2 = master_list.index[master_list.flatdemandunit == 'kVA']
# print(ids2.size)
# ids3 = master_list.index[master_list.flatdemandunit == 'kVA daily']
# print(ids3.size)
# ids4 = master_list.index[master_list.flatdemandunit == 'hp']
# print(ids4.size)
# ids = ids1.append(ids2).append(ids3).append(ids4).sort_values()
print(type(ids))
obs_list = master_list.loc[ids]
master_list = master_list.drop(index=ids)
master_list = master_list.sort_values(by='eiaid')

print(master_list.shape)
master_list.replace('', float('NaN'), inplace=True)
master_list.dropna(how='all', axis=1, inplace=True)
print(master_list.shape)


master_list.to_csv('util_list_residential.csv', index=False)
obs_list.to_csv('util_list_obs.csv')