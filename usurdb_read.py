import json
import os
import tempfile
import time

import bs4
from bs4 import BeautifulSoup as bs
import pandas as pd
import requests
import numpy as np
from dateutil.parser import ParserError
import requests as rq
from pandas._libs.tslibs.parsing import DateParseError
# global variables

OPENEI_CREDENTIALS_PATH = 'openei_credentials.json'  # gitignored -- {"api_key": ...}, get one at openei.org


def load_openei_api_key() -> str:
    """Returns the OpenEI API key from the OPENEI_API_KEY env var, else OPENEI_CREDENTIALS_PATH, else ''."""
    if os.environ.get('OPENEI_API_KEY'):
        return os.environ['OPENEI_API_KEY']
    if os.path.exists(OPENEI_CREDENTIALS_PATH):
        try:
            with open(OPENEI_CREDENTIALS_PATH) as f:
                return json.load(f).get('api_key', '')
        except (json.JSONDecodeError, OSError):
            return ''
    return ''


api_key = load_openei_api_key()
base_url = 'https://api.openei.org/utility_rates?version=8&format=csv&sector=Residential&'


# Helping Functions
def get_info_dict(basic_tags: list, default=True):
    util = basic_tags[0].text

    if default:
        name = basic_tags[2].text
        verified = basic_tags[3].text == 'Yes'
        supersedes = basic_tags[7].text
        source = basic_tags[11].text
        net_meter = basic_tags[13].text
        try:
            end_date = pd.to_datetime(basic_tags[6].text)
        except ParserError:
            end_date = np.nan
        except DateParseError:
            end_date = np.nan

        try:
            start_date = pd.to_datetime(basic_tags[5].text)
        except ParserError:
            start_date = np.nan
        except DateParseError:
            start_date = np.nan

    else:
        name = basic_tags[4].text
        verified = basic_tags[5].text == 'Yes'
        supersedes = basic_tags[9].text
        source = basic_tags[13].text
        net_meter = basic_tags[15].text
        try:
            end_date = pd.to_datetime(basic_tags[8].text)
        except ParserError:
            end_date = np.nan
        except DateParseError:
            end_date = np.nan

        try:
            start_date = pd.to_datetime(basic_tags[7].text)
        except ParserError:
            start_date = np.nan
        except DateParseError:
            start_date = np.nan

    info_dict = {'Utility': util,
                 'Name': name,
                 'Verified': verified,
                 'Start Date': start_date,
                 'End Date': end_date,
                 'Supersedes': supersedes,
                 'Source': source,
                 'Net Meter Policy': net_meter}
    for key in info_dict.keys():
        if info_dict[key] == '\xa0':
            info_dict[key] = ''

    return info_dict


def get_demand_frame(table_tag: bs4.Tag):
    demand_cols = ['Period', 'Tier', 'Max kW Usage', 'Rate $/kW', 'Adjustments $/kW']
    rows = []
    row_tags = table_tag.find_all('div', class_=["strux_view_row tier_bottom", "strux_view_row"])
    prev_per = 1
    for tag in row_tags:
        demand_cell_tags = tag.find_all('div', class_="strux_view_cell")

        try:
            period = int(demand_cell_tags[-17].text)
            prev_per = period
        except IndexError:
            period = prev_per
        except ValueError:
            period = prev_per

        try:
            max_usage = int(demand_cell_tags[-15].text)
        except IndexError:
            max_usage = -1
        except ValueError:
            max_usage = -1

        try:
            rate = int(demand_cell_tags[-14].text)
        except IndexError:
            rate = 0
        except ValueError:
            rate = 0

        try:
            adj = int(demand_cell_tags[-13].text)
        except IndexError:
            adj = 0
        except ValueError:
            adj = 0

        row_dict = {'Period': period,
                    'Tier': int(demand_cell_tags[-16].text),
                    'Max kW Usage': max_usage,
                    'Rate $/kW': rate,
                    'Adjustments $/kW': adj}

        rows.append(row_dict)
    return pd.DataFrame(data=rows, columns=demand_cols)


def get_energy_frame(table_tag: bs4.Tag):
    energy_cols = ['Period', 'Tier', 'Max Usage', 'Max Energy Units', 'Rate $/kWh', 'Adjustments $/kWh', 'Sell $/kWh']
    rows = []
    row_tags = table_tag.find_all('div', class_=["strux_view_row tier_bottom", "strux_view_row"])
    prev_per = 1
    for tag in row_tags:
        energy_cell_tags = tag.find_all('div', class_="strux_view_cell")
        try:
            period = int(energy_cell_tags[-7].text)
            prev_per = period
        except IndexError:
            period = prev_per
        except ValueError:
            period = prev_per

        try:
            max_usage = int(energy_cell_tags[-5].text)
        except IndexError:
            max_usage = -1
        except ValueError:
            max_usage = -1

        try:
            rate = float(energy_cell_tags[-3].text)
        except IndexError:
            rate = 0
        except ValueError:
            rate = 0

        try:
            adj = float(energy_cell_tags[-2].text)
        except IndexError:
            adj = 0
        except ValueError:
            adj = 0

        try:
            sell = float(energy_cell_tags[-1].text)
        except IndexError:
            sell = 0
        except ValueError:
            sell = 0

        row_dict = {'Period': period,
                    'Tier': int(energy_cell_tags[-6].text),
                    'Max Usage': max_usage,
                    'Max Energy Units': energy_cell_tags[-4].text,
                    'Rate $/kWh': rate,
                    'Adjustments $/kWh': adj,
                    'Sell $/kWh': sell}
        rows.append(row_dict)
    return pd.DataFrame(data=rows, columns=energy_cols)


def get_schedule_array(schedule_tag: bs4.Tag):
    schedule_array = np.zeros((12, 24))
    num_string = schedule_tag.text
    for i in range(12):
        try:
            schedule_array[i] = np.array([int(num) for num in list(num_string[24 * i:(24 * (i + 1))])], dtype=int)
        except ValueError:
            j = 0
            for num in list(num_string[24 * i:(24 * (i + 1))]):
                if num == 'A':
                    num = 10
                elif num == 'B':
                    num = 11
                elif num == 'C':
                    num = 12
                elif num == 'D':
                    num = 13
                elif num == 'E':
                    num = 14
                elif num == 'F':
                    num = 15
                schedule_array[i, j] = int(num)

    return schedule_array


def get_charges_dict(charge_tags: list):
    charge_units = charge_tags[0].text
    try:
        fixed_charge = round(float(charge_tags[1].text), 4)
    except ValueError:
        fixed_charge = 0
    if charge_units == '$/day':
        monthly_charge = 365 * fixed_charge / 12
    else:
        monthly_charge = fixed_charge

    try:
        minimum_charge = round(float(charge_tags[3].text))
    except ValueError:
        minimum_charge = 0

    min_charge_units = charge_tags[4].text
    if min_charge_units == '$/day':
        minimum_charge = 365 * minimum_charge / 12

    new_dict = {'Monthly Charge': round(monthly_charge, 2),
                'Minimum Charge': minimum_charge}
    return new_dict


def get_energy_tier_list(frame):
    master_list = []
    for per in frame['Period'].unique():
        sublist = []
        subframe = frame[frame['Period'] == per]
        subframe = subframe.reset_index(drop=True)
        for tier in subframe['Tier'].unique():
            ind = subframe[(subframe['Period'] == per) & (subframe['Tier'] == tier)].index
            rate = round(subframe.loc[ind, 'Rate $/kWh'].values[0], 5)
            rate += round(subframe.loc[ind, 'Adjustments $/kWh'].values[0], 5)
            limit = subframe.loc[ind, 'Max Usage'].values[0]
            sublist.append([limit, rate])

        master_list.append(sublist)

    return master_list


def get_demand_tier_list(frame):
    master_list = []
    for per in frame['Period'].unique():
        sublist = []
        subframe = frame[frame['Period'] == per]
        subframe = subframe.reset_index(drop=True)
        for tier in subframe['Tier']:
            ind = subframe[(subframe['Period'] == per) & (subframe['Tier'] == tier)].index
            rate = np.round(subframe.loc[ind, 'Rate $/kW'].values[0], 5)
            rate += np.round(subframe.loc[ind, 'Adjustments $/kW'].values[0], 5)
            limit = subframe.loc[ind, 'Max kW Usage'].values[0]
            sublist.append([limit, rate])

        master_list.append(sublist)

    return master_list


def get_max_difference(arr: np.ndarray, periods: list):
    num = len(periods)
    rates = np.array([per[0][1] for per in periods])
    rate_arr = arr.astype(float)
    for i in range(num):
        rate_arr[rate_arr == (i + 1)] = rates[i]

    diff = 0
    for j in range(12):
        diff = max(diff, np.max(rate_arr[j, :]) - np.min(rate_arr[j, :]))

    return diff


def read_tariff(url: str, default_url=True):
    try:
        result = requests.get(url=url)
    except requests.exceptions.ReadTimeout:
        do_loop = True
        loop_count = 0
        while do_loop and loop_count<10:
            try:
                result = requests.get(url=url)
            except requests.exceptions.ReadTimeout:
                time.sleep(5)
                loop_count += 1
                if loop_count > 9:
                    Exception('loop limit maxed for read_tariff')
            else:
                do_loop = False
    doc = bs(result.text, "html.parser")

    # columns for each new utility file. Each tariff will have these values

    #  Reading Basic Information
    basic_info = doc.find('div', id="1__Basic_Information")

    info_tags = basic_info.find_next('dl', class_="dl-horizontal")
    info_tags = info_tags.find_all('dd')
    if default_url:
        tariff_info_dict = get_info_dict(info_tags)
    else:
        tariff_info_dict = get_info_dict(info_tags, default=False)

    # Reading Demand Information
    demand_info = doc.find('div', id="2__Demand")
    demand_table_container = demand_info.find('section', class_="strux_view_table", id="flat_demand_strux_table")
    demand_frame = get_demand_frame(demand_table_container)
    demand_weekday_arr = get_schedule_array(demand_info.find('div', id="data-demandWeekdaySched"))
    demand_weekend_arr = get_schedule_array(demand_info.find('div', id="data-demandWeekendSched"))
    demand_tier_list = get_demand_tier_list(demand_frame)

    # Reading Energy Information
    energy_info = doc.find('div', id="3__Energy")
    energy_table_container = energy_info.find('section', class_="strux_view_table", id="energy_rate_strux_table")
    # energy_row_tags = energy_table_container.find_all('div', class_="strux_view_row tier_bottom")
    energy_frame = get_energy_frame(energy_table_container)
    energy_weekday_arr = get_schedule_array(energy_info.find('div', id="data-energyWeekdaySched"))
    energy_weekend_arr = get_schedule_array(energy_info.find('div', id="data-energyWeekendSched"))
    energy_tier_list = get_energy_tier_list(energy_frame)

    # Reading Fixed Charges
    charges_info = doc.find('div', id="4__Fixed_Charges")
    charges_dict = get_charges_dict(charges_info.find_next('dl', class_="dl-horizontal").find_all('dd'))

    # Determine Attributes
    is_tiered = len(energy_frame['Tier'].unique()) > 1
    is_tou = not np.all(energy_weekend_arr[:, 0] == np.reshape(np.sum(energy_weekday_arr, axis=1) / 24, (12,)))
    is_demand = np.sum(demand_frame['Rate $/kW'].to_numpy()) != 0

    attr_dict = {'TimeOfUse': is_tou,
                 'Tiered': is_tiered,
                 'Demand': is_demand}

    if is_tou:
        max_diff = get_max_difference(energy_weekday_arr, energy_tier_list)
    else:
        max_diff = 0

    if not is_demand:
        demand_weekday_arr = np.nan
        demand_weekend_arr = np.nan
        demand_tier_list = np.nan

    # Make Rate Dictionary

    rate_dict = {'Time-of-Use Rates': str(energy_tier_list),
                 'Max Difference': max_diff,
                 'Weekday Schedule - Energy': str(energy_weekday_arr).replace('.', ',').replace('\n', ','),
                 'Weekend Schedule - Energy': str(energy_weekend_arr).replace('.', ',').replace('\n', ','),
                 'Demand Rates': str(demand_tier_list),
                 'Weekday Schedule - Power': str(demand_weekday_arr).replace('.', ',').replace('\n', ','),
                 'Weekend Schedule - Power': str(demand_weekend_arr).replace('.', ',').replace('\n', ',')}

    # Combine Dictionaries

    data_dict = tariff_info_dict | charges_dict | attr_dict | rate_dict

    return data_dict


def api_read(eia_code):
    global api_key
    global base_url
    url_call = base_url + 'eia=' + eia_code + '&api_key=' + api_key
    new_csv = rq.get(url_call)
    temp_path = os.path.join(tempfile.gettempdir(), 'usurdb_api_read.csv')
    with open(file=temp_path, mode='wb') as file:
        file.write(new_csv.content)

    return pd.read_csv(temp_path)

# # url = 'https://apps.openei.org/USURDB/rate/view/62d70f2d146c525e2b34ab96'
#
# page_url = 'https://apps.openei.org/USURDB/rate/view/62d7034296022b27a11abb76'
#
# data = read_tariff(page_url)
