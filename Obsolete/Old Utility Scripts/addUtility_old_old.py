import pandas as pd
import numpy as np

zip_codes = pd.read_csv('../ZipCodesFixed.csv')

zip_codes['postal code'] = zip_codes['postal code'].astype(str)

zip_codes['Utility'] = ''
zip_codes['EIA Code'] = ''

util_raw = pd.read_csv('../../Archive/DataFiles/utility companies_zipcodes.csv')

util_raw['zip'] = util_raw['zip'].astype(str)

util = pd.DataFrame(columns=['Name', 'EIA Code', 'State Name', 'State Code', 'Total Zips'])
lost = pd.DataFrame(columns=list(zip_codes.columns.values))

print(type(util_raw.iloc[0, 0]))

last_zip = None  # last zip will change to prevent adding same zip twice from raw util-zip csv

for i in range(util_raw.shape[0]):
    zip_raw = str(util_raw.iloc[i, 0]).zfill(5) # zfill to adjust for 3 digit zip codes that are supposed to have leading zeros
    eia = util_raw.iloc[i, 1]
    util_name = util_raw.iloc[i, 2]
    state_code = util_raw.iloc[i, 3]

    ind = zip_codes.index[zip_codes['statecode'] == state_code]
    ind = ind[0]
    state_name = zip_codes.iloc[ind, 2]

    if zip_raw != last_zip:
        # append utility to end of util dataframe, if it is already present, add one to 'Total Zips' column value

        if util_name in util['Name'].values.astype(str):
            ind = util.index[util['Name'] == util_name]
            util.iloc[ind, 4] += 1
        else:
            # util = util.append([util_name, eia, state_code, 1])
            util.loc[len(util), util.columns] = [util_name, eia, state_name, state_code, 1]

        # print(zip_raw in zip_codes['postal code'].values.astype(str))

        # append util name to match zip code, if not present, append to lost dataframe
        if zip_raw in zip_codes['postal code'].values.astype(str):
            ind = zip_codes.index[zip_codes['postal code'] == zip_raw]
            zip_codes.iloc[ind, 7] = util_name
            zip_codes.iloc[ind, 8] = eia
        else:
            # zip_codes = zip_codes.append([zip_raw, None, state_name, state_code, None, None, None])
            # lost = lost.append([zip_raw, None, state_name, state_code, None, None, None])
            zip_codes.loc[len(zip_codes), zip_codes.columns] = \
                [zip_raw, None, state_name, state_code, None, None, None, util_name, eia]
            lost.loc[len(lost), lost.columns] = \
                [zip_raw, None, state_name, state_code, None, None, None, util_name, eia]
        last_zip = zip_raw

zip_codes.to_csv('zipCodes2.csv', index=False)
util.to_csv('Utilities.csv', index=False)
lost.to_csv('LostZips.csv', index=False)

