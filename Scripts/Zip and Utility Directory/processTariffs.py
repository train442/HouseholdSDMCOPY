import pandas as pd
import sys

sys.path.append('../..')
import DataProcessing as dp

# process residential utility list into separate csv lists
#
# NOTE: the tier/period-parsing logic previously duplicated here and in create_utility_files.py now lives in
# DataProcessing.usurdb_row_to_tariff_fields / DataProcessing.parse_usurdb_rate_structure.

util_file = 'D:/Bras Research/pythonProject/util_tariffs_residential.csv'

master_list = pd.read_csv(util_file)
util_list = pd.read_csv('D:/Bras Research/pythonProject/Utilities.csv')

for i in range(0, master_list.shape[0]):
    row = master_list.loc[i]
    util_name = row.iloc[5].replace(' ', '_')
    util_eia = row.iloc[1]
    tariff_name = row.iloc[2]
    openei_id = row.iloc[0]

    util_file_path = 'D:/Bras Research/pythonProject/Utilities/' + util_name + '_' + str(util_eia) + '.csv'

    row_dict = dp.usurdb_row_to_tariff_fields(row)
    row_dict['Name'] = tariff_name
    row_dict['OpenEI Id'] = openei_id

    dp.append_tariff_row(util_file_path, row_dict)

    if i % 500 == 0:
        print(str(i / len(master_list) * 100) + '%')
