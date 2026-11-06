import pandas as pd
import warnings
import shutup

# this adds everything from the utility zip code list (''utility companies_zipcodes.csv) and adds it to the
# lat/long zip code list ( zipCodesFixed.csv), and makes a separate csv for the zip codes that are not in the
# lat/long zip codes list ( lostZips.csv). The resulting file is saved to zipCode2.csv. A second csv containing a
# list of zip codes and the csvs they service and their EIA codes is created (utilities.csv)


shutup.please()

warnings.filterwarnings("ignore", category=DeprecationWarning)
zip_codes = pd.read_csv('../ZipCodesFixed.csv', dtype={'postal code': str, 'EIA Code': str})

zip_codes['Utility'] = None
zip_codes['EIA Code'] = None

util_raw = pd.read_csv('../../Archive/DataFiles/utility companies_zipcodes.csv', dtype={'zip': str, 'eiaid': str})
util_names = pd.read_csv('../../Archive/DataFiles/util_with_zip.csv', dtype={'eiaid': str})
unique_util = util_names['utility'].unique()
print(unique_util)

util = pd.DataFrame(columns=['Name', 'EIA Code', 'State Name', 'State Code', 'Total Zips'])  # utility csv
lost = pd.DataFrame(columns=list(zip_codes.columns.values))  # csv for zip codes that fall through cracks
prevZip = None
prevUtil = None
for i in range(util_raw.shape[0]):
    zip_raw = util_raw.loc[i, 'zip']
    eia = util_raw.loc[i, 'eiaid']

    try:
        util_name = util_names.loc[util_names[util_names['eiaid'] == eia].index.values[0], 'utility']
    except IndexError:
        print(eia in unique_util)
        print(eia)
        raise Exception('try again')

    # util_name = util_raw.iloc[i, 2]
    state_code = util_raw.iloc[i, 3]

    ind = zip_codes.index[zip_codes['statecode'] == state_code]
    ind = ind[0]
    state_name = zip_codes.iloc[ind, 2]

    if util_name in util['Name'].values.astype(str):
        if zip_raw != prevZip or prevUtil != util_name:
            ind = util.index[util['Name'] == util_name]
            util.iloc[ind, 4] += 1
    else:
        # util = util.append([util_name, eia, state_code, 1])
        util.loc[len(util), util.columns] = [util_name, eia, state_name, state_code, 1]

    if zip_raw in zip_codes['postal code'].values:
        ind = zip_codes.index[zip_codes['postal code'] == zip_raw][0]
        if zip_codes.loc[ind, 'Utility'] is None:  # if there is currently no utility listed in column
            zip_codes.loc[ind, 'Utility'] = [util_name]
            zip_codes.loc[ind, 'EIA Code'] = [eia]
        else:  # zip code already has utility in value and must be appended
            if util_name not in zip_codes.loc[ind, 'Utility']:
                zip_codes.loc[ind, 'Utility'].append(util_name)
                zip_codes.loc[ind, 'EIA Code'].append(eia)

    else:  # The zip code from utility csv is not in lat/long zip csv, add row to lost csv
        if zip_raw in lost['postal code'].values:
            ind2 = lost.index[lost['postal code'] == zip_raw][0]
            if util_name not in lost.loc[ind2, 'Utility']:
                lost.loc[ind2, 'Utility'].append(util_name)
                lost.loc[ind2, 'EIA Code'].append(eia)

        else:
            lost.loc[len(lost), lost.columns] = \
                [zip_raw, None, state_name, state_code, None, None, None, [util_name], [eia]]
    prevZip = zip_raw
    prevUtil = util_name
zip_codes.to_csv('zipCodes2.csv', index=False)
util.to_csv('Utilities.csv', index=False)
lost.to_csv('LostZips.csv', index=False)
