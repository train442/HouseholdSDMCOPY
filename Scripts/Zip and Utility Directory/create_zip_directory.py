import pandas as pd

# This script creates a zip directory, which gives the location data (city, county, latitude and longitude) as well
# as the utilities and eia codes of those utilities. With this directory, the user need only give a zip code to all
# get the necessary information for the simulation.

# read in the location source file. For now this is zipCodes2, but will replace this later. Note that this file has
# more zip codes than the zip_to_util file. The zips that are missing have already been put into no_util_zips.csv.
# However, every zip in the zip_to_util.csv file is in the zip location file. This could be remedied later,
# but for now we deal with the fact that some zip codes will not be mapped to a utility.

zip_location = pd.read_csv('../../Archive/DataFiles/zipCodes2.csv', dtype={'postal code': str})

# read in the zip_to_util mapping file.

zip_util = pd.read_csv('../../Model Data/zip_to_util_fixed.csv', dtype={'Zip Code': str})

# establish new dataframe for resulting directory
column_list = ['Zip Code', 'City', 'State', 'State (Abbr)', 'County', 'Latitude', 'Longitude', 'Utilities', 'EIA Codes']
zip_directory = pd.DataFrame(columns=column_list)

#establish catch for zips in util map but not in location map

missing_zips = []

for i in range(len(zip_util)):

    #get data from util map
    zip_code = zip_util.loc[i, 'Zip Code']
    utils = zip_util.loc[i, 'Utilities']
    eias = zip_util.loc[i, 'EIA Codes']

    # get data from location map
    try:
        ind = zip_location.index[zip_location['postal code'] == zip_code].values[0]
        city = zip_location.loc[ind, 'place']
        state = zip_location.loc[ind, 'state']
        st_abr = zip_location.loc[ind, 'statecode']

        county = zip_location.loc[ind, 'province_or_county']
        lat = zip_location.loc[ind, 'latitude']
        long = zip_location.loc[ind, 'longitude']

        new_frame = pd.DataFrame(data={'Zip Code': zip_code, 'City': city, 'State': state, 'State (Abbr)': st_abr,
                                       'County': county, 'Latitude': lat, 'Longitude': long, 'Utilities': utils,
                                       'EIA Codes': eias}, index=[0])

        zip_directory = pd.concat([zip_directory, new_frame], axis=0)
    except IndexError:
        print(zip_code)
        missing_zips.append(zip_code)


zip_directory.to_csv('zip_directory.csv', index=False)

zips_needing_location = pd.DataFrame(data={'Zip Code': missing_zips})
zips_needing_location.to_csv('zips_needing_location.csv', index=False)
