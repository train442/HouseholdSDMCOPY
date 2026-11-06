import pandas as pd

#This script fixes utility names in util_to_zip.csv. Some of them, when acquired had mixed up names where they end in 'city of' or village of' instead of starting with it. This script remedies that.


util_list = pd.read_csv('../../Archive/DataFiles/util_to_zip.csv', dtype={'EIA Code': str})
count = 0
ids = []

for i in range(len(util_list)):
    name = util_list.loc[i, 'Utility Name']
    name_split = name.split(' ')
    if name_split[-1] == 'of':
        re_order = name_split[-2:] + name_split[:-2]
        util_list.loc[i, 'Utility Name'] = str.join(' ', re_order)
        count +=1
        ids.append(i)

print(count)
print(ids)
util_list.to_csv('util_to_zip_fixed.csv', index=False)
