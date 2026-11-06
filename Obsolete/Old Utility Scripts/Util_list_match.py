import pandas as pd

# compares 'utility companies_zipcodes.csv'(FORD) with 'util_list_residential.csv' (openei) to see which utilities
# from openei are not matched with a zipcode from Ford

frame1 = pd.read_csv('../../Archive/DataFiles/utility companies_zipcodes.csv', dtype={'zip': str, 'eiaid': str})
unique1 = frame1['eiaid'].unique()
num1 = len(unique1)

frame2 = pd.read_csv('../../Archive/DataFiles/util_list_residential.csv', usecols=['eiaid', 'utility'], dtype={'eiaid': str})
unique2 = frame2['eiaid'].unique()
num2 = len(unique2)

missing_id = []
missing_utility = []

matching_id = []
matching_utility = []

missing_id_zip_to_util = []
missing_utility_zip_to_util = []

for index, row in frame2.iterrows():
    # print(index)
    eiaid = row['eiaid']
    util = row['utility']
    # print(eiaid)
    if (eiaid not in unique1) & (eiaid not in missing_id):
        missing_id.append(eiaid)
        missing_utility.append(util)
    elif (eiaid in unique1) & (eiaid not in matching_id):
        matching_id.append(eiaid)
        matching_utility.append(util)

for index, row in frame1.iterrows():
    # print(index)
    eiaid = row['eiaid']
    util = row['utility_name']
    # print(eiaid)
    if (eiaid not in unique2) & (eiaid not in missing_id_zip_to_util):
        missing_id_zip_to_util.append(eiaid)
        missing_utility_zip_to_util.append(util)



missing_frame = pd.DataFrame(data={'utility': missing_utility, 'eiaid': missing_id})
missing_frame.to_csv('util_without_zip.csv', index=False)

matching_frame = pd.DataFrame(data={'utility': matching_utility, 'eiaid': matching_id})
matching_frame.to_csv('util_with_zip.csv', index=False)

missing_frame_zip_to_util = pd.DataFrame(data={'utility': missing_utility_zip_to_util, 'eiaid': missing_id_zip_to_util})
missing_frame_zip_to_util.to_csv('util_without_zip_zip_to_util.csv', index=False)

print(num1, num2)
