import ast

import pandas as pd

# This script corrects the zip_to_util file by adding leading zeros to zip codes where necessary. Also corrects
# utility names by referring to the fixed util_to_zip file

zip_frame = pd.read_csv('../../Archive/DataFiles/zip_to_util.csv', dtype={'Zip Code': str}, converters={'EIA Codes': ast.literal_eval})

# read in corrected util_to_zip

util_frame = pd.read_csv('../../Model Data/util_to_zip_fixed.csv',
                         converters={'Zip Codes': ast.literal_eval, 'Alternate Names': ast.literal_eval},
                         dtype={'EIA Code': str})

for i in range(len(zip_frame)):
    zip_code = zip_frame.loc[i, 'Zip Code']
    eia_list = zip_frame.loc[i, 'EIA Codes']

    if len(zip_code) < 5:
        zip_code = zip_code.zfill(5)
        zip_frame.loc[i, 'Zip Code'] = zip_code
    util_list = []
    eia_new_list = []
    j = 0  # counter for index in case of removal
    for eia in eia_list:
        eia = eia.replace('.', '')  # removal of period from some eia codes. Caused repeats
        if eia not in eia_new_list:
            eia_new_list.append(eia)

            try:
                ind = util_frame.index[util_frame['EIA Code'] == eia].values[0]
            except IndexError:
                print(i, eia)
            util_name = util_frame.loc[ind, 'Utility Name']
            util_list.append(util_name)
    zip_frame.loc[i, 'Utilities'] = util_list
    zip_frame.loc[i, 'EIA Codes'] = eia_new_list

zip_frame.to_csv('zip_to_util_fixed.csv', index=False)
