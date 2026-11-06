import ast
from types import NoneType
from ast import literal_eval

import bs4
import pandas as pd
import time
from bs4 import BeautifulSoup as bs
import requests
import os


# create dataframes to hold 'zip to util' and 'util to zip' files. The first will list all zip codes by row and the
# next columns will be lists of the utilities in that area and their eia codes. The second file will be a list of
# utilities by row, with columns being a list of all the zip codes its services and the total number of zips.

pd.set_option('display.max_columns', None)


def remove_extra(unfiltered):  # this function removes extra elements from list in place
    filtered = []
    for element in unfiltered:
        if element not in filtered:
            filtered.append(element)
    return filtered


# this function takes a div tag with the eia and util data for a zipcode and returns 3 three lists. One is the
# utilities, the second is their respective EIA codes. The third are any alternate names for the utilities (names which
# share an EIA code).
def process_tags(unfiltered):
    br_tag = unfiltered.find_all('br')
    name_list = []
    code_list = []
    other_list = []  # list of alternate utility names

    for t in range(len(br_tag) - 1):
        if t != 0:
            name = br_tag[t].nextSibling.text
            code = br_tag[t].nextSibling.nextSibling.text.split()[3].replace('#', '').replace('.','')
            if code not in code_list:  # fresh utility needs to be added to list
                code_list.append(code)
                name_list.append(name)
                other_list.append([])  # append empty list in case eia repeats under different util name
            else:  # eia code already accounted for, but need to make sure util name is not a repeat.
                if name not in name_list:  # name is an alternate. thus we add it to
                    ind = code_list.index(code)
                    if name not in other_list[ind]:
                        other_list[ind].append(name)
    return name_list, code_list, other_list


if os.path.exists('../../Archive/DataFiles/util_to_zip.csv'):
    util_to_zip = pd.read_csv('../../Archive/DataFiles/util_to_zip.csv',
                              converters={'Zip Codes': ast.literal_eval, 'Alternate Names': ast.literal_eval},
                              dtype={'EIA Code': str})
    # util_to_zip[['Zip Codes']] = util_to_zip[['Zip Codes']].applymap(literal_eval())
else:
    util_to_zip = pd.DataFrame(
        columns=['Utility Name', 'EIA Code', 'Alternate Names', 'Zip Codes', 'Total Zips Serviced'])

if os.path.exists('../../Archive/DataFiles/zip_to_util.csv'):
    zip_to_util = pd.read_csv('../../Archive/DataFiles/zip_to_util.csv', dtype={'Zip Code': str},
                              converters={'Utilities': ast.literal_eval, 'EIA Codes': ast.literal_eval})
    # zip_to_util[['Utilities', 'EIA Codes']] = zip_to_util[['Utilities', 'EIA Codes']].applymap(literal_eval())
else:
    zip_to_util = pd.DataFrame(columns=['Zip Code', 'Utilities', 'EIA Codes'])

if os.path.exists('none_zips'):
    none_zip = pd.read_csv('none_zip')
else:
    none_zip = pd.DataFrame(columns=['Zip Code'])

if os.path.exists('../../Archive/DataFiles/no_info_zip.csv'):
    no_info_zip = pd.read_csv('../../Archive/DataFiles/no_info_zip.csv', dtype={'Zip Code': str})
else:
    no_info_zip = pd.DataFrame(columns=['Zip Code'])

print(util_to_zip)
print(zip_to_util)

# determine the highest zip code already assessed if zip_to_util.csv already exists
if len(zip_to_util) != 0:
    max_zip = int(zip_to_util.loc[len(zip_to_util) - 1, 'Zip Code'])
    print(max_zip)
else:
    max_zip = 0
# sad_zips = []  # list of zip codes that don't return results in database (more than likely don't exist)
# none_zips = []  # list of zips that don't return any warning of unavailability

for i in range(23800, 100000):
    if i % 100 == 0:
        print(i)
    zip_code = str(i).zfill(5)
    if i > max_zip:
        url = 'https://apps.openei.org/USURDB/?fa-search=&utilRateFindByZip=' + zip_code + '&sectors%5B%5D=Residential&service_type=&is_default='
        res = requests.get(url)
        doc = bs(res.text, 'html.parser')

        util_list = []
        alt_list = []
        info_tag = doc.find('div', {'id': 'urdbUtilityInfoContent'})
        if (info_tag is None) or (info_tag is NoneType):  #
            if zip_code not in none_zip['Zip Code'].values:
                # print(type(zip_code), zip_code)
                to_add = pd.DataFrame(data={'Zip Code': str(zip_code)}, index=[0])
                none_zip = pd.concat([none_zip, to_add], ignore_index=True, axis=0)
        elif info_tag.text == 'Utility information is not currently available for this zipcode search.':
            if zip_code not in no_info_zip['Zip Code'].values:
                # print(type(zip_code), zip_code)
                to_add = pd.DataFrame(data={'Zip Code': str(zip_code)}, index=[0])
                no_info_zip = pd.concat([no_info_zip, to_add], ignore_index=True, axis=0)
        else:  # zip code is returning a result in database
            info_split = info_tag.find_all('br')
            eia_split = info_split[0].previousSibling.text.replace(',', '').split(
                ' ')  # split string to retrieve eia info
            # print(eia_split)
            try:
                num_eia = int(eia_split[1])  # second word is number of eia ids found and thus the number or utilities
                eias = eia_split[-num_eia:]  # last (num_eia) words are the eia codes
                for j in range(len(info_split) - 1):
                    # print(info_split[i].nextSibling)
                    if j != 0:
                        util_list.append(info_split[j].nextSibling.text)
                        alt_list.append([])
            except ValueError:  # this will trip if there's only one utility, since text is different in that case
                eias = [eia_split[4].strip('#')]
                util_list = [info_tag.findNext('a').text]
                alt_list = [[]]

            # Sometimes util list has repeat (if util in database has multiple locations, for example. However, the
            # database will only list each EIA code once, so we have to filter the util_list in place to remove repeats
            # and ensure one to one matching of utils with their proper eia codes

            if len(util_list) != len(eias):  # only need to do this if there is a mismatch
                util_list = remove_extra(util_list)
                # sometimes multiple utilities share the same eia, which is the case when names have changed.
                # However, each eia code represents one distinct utility, meaning it may have various names.
                if len(util_list) != len(eias):
                    util_list, eias, alt_list = process_tags(info_tag)

            # Now we append the zip code to zip code to util data frame
            # to_add = pd.DataFrame(data={'Zip Code': zip_code, 'Utilities': util_list, 'EIA Codes': eias})
            to_add = pd.DataFrame(columns=['Zip Code', 'Utilities', 'EIA Codes'])
            to_add.loc[0, 'Zip Code'] = zip_code
            to_add.loc[0, 'Utilities'] = util_list
            to_add.loc[0, 'EIA Codes'] = eias
            zip_to_util = pd.concat([zip_to_util, to_add], ignore_index=True, axis=0)
            # print(zip_code)
            # print(util_list)
            # print(alt_list[0])
            # Now we check if utilities in zip code are already accounted for in utility to zip dataframe (ie,
            # no repeats)
            for k in range(len(util_list)):
                util = util_list[k]
                try:
                    eia = eias[k]
                except IndexError:
                    print(zip_code)
                    raise Exception('better check this out')
                alt = alt_list[k]
                if eia in util_to_zip['EIA Code'].values:  # utility is already in frame
                    try:
                        ind_util = util_to_zip[util_to_zip['EIA Code'] == eia].index.values[0]  # find index for utility
                    except IndexError:
                        print(zip_code, util, eia)
                        print(util_to_zip[util_to_zip['Utility Name'] == util].index.values[0])
                        print(util_to_zip)

                        raise Exception('Better check this out')
                    util_to_zip.loc[ind_util, 'Zip Codes'].append(zip_code)
                    util_to_zip.loc[ind_util, 'Total Zips Serviced'] += 1

                else:  # utility is not in dataframe
                    to_add = pd.DataFrame(data={'Utility Name': util, 'EIA Code': eia, 'Alternate Names': [alt], 'Zip Codes': [zip_code],
                                                'Total Zips Serviced': 1})
                    to_add.loc[0, 'Zip Codes'] = [to_add.loc[0, 'Zip Codes']]
                    util_to_zip = pd.concat([util_to_zip, to_add], ignore_index=True, axis=0)
            # print(util_to_zip)
        if (i % 100 == 0) & (i != 0):
            util_to_zip.to_csv('util_to_zip.csv', index=False)
            zip_to_util.to_csv('zip_to_util.csv', index=False)
            no_info_zip.to_csv('no_info_zip.csv', index=False)
            none_zip.to_csv('none_zip.csv', index=False)
util_to_zip.to_csv('util_to_zip.csv', index=False)
zip_to_util.to_csv('zip_to_util.csv', index=False)
no_info_zip.to_csv('no_info_zip.csv', index=False)
none_zip.to_csv('none_zip.csv', index=False)
