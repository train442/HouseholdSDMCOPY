import numpy as np
import pandas as pd
import Parameters as pm
import Setup as sp
from Components import *
import DataProcessing as dp

zipcode = 97068
load_file_ = np.nan
load_amount_ = 11000
pv_size_ = 5
util_file_ = 'Custom_tariffs.csv'
util_name_ = np.nan
tariff_id_ = '3tierTOU'

timekeep = pm.TimeKeep()

city = sp.create_city(zipcode=zipcode)


def make_house(ref_city: pm.City):
    load_file = load_file_
    load_amount = load_amount_

    if not pd.isnull(load_file) and os.path.exists('City Data/Load Profiles/Custom Loads/' + load_file + '.csv'):
        new_house = House(load_file='City Data/Load Profiles/Custom Loads/' + load_file + '.csv')
    elif not np.isnan(load_amount):
        # check if load file already exists with that usage amount
        direct = 'City Data/Load Profiles/Custom Loads/'
        potential_file = ref_city.matched_state + '_' + ref_city.matched_city + '_' + str(load_amount) + 'kWh.csv'
        if os.path.exists(direct + potential_file):
            new_house = House(load_file=direct + potential_file)
        else:
            new_house = House(
                load_profile=dp.load_match_yearly(state=ref_city.matched_state, city=ref_city.matched_city,
                                                  usage=load_amount, save_profile=False))
    else:  # we assume basic US average usage
        new_house = House(load_profile=dp.load_match_yearly(state=ref_city.matched_state, city=ref_city.matched_city,
                                                            usage=11000, save_profile=False))
    return new_house


def make_pv(ref_city: pm.City, tk: pm.TimeKeep):
    # Provide current row and reference city to make PV object

    new_pv = PV(system_size=pv_size_)

    ghi_file = city.matched_state + '_' + ref_city.matched_city + '_GHI_2018_5min.csv'
    ghi_dir = 'City Data/Solar Data/' + ref_city.matched_state + '/'
    new_pv.load_solar(solar_file=ghi_dir + ghi_file, start_date=tk.start_date, end_date=tk.end_date)

    return new_pv


def make_tariff(ref_city: pm.City, tk: pm.TimeKeep):
    # pass current row and city object to make tariff object
    util_file = util_file_
    util_name = util_name_
    tariff_id = tariff_id_
    if not pd.isnull(util_file):  # util file is provided
        util_name = util_file.split('_')[0]
        if (util_name in ref_city.utilities) or (util_name == 'Custom'):  # we make sure the utility one available in city
            if not pd.isnull(tariff_id):  # tariff id is provided
                new_tariff = sp.create_tariff(util_file=util_file, tariff_name=tariff_id)
            else:  # tariff id is not provided
                new_tariff = sp.create_tariff(util_file=util_file)
        else:  # util is not in list, so we resort to first utility listed in city
            util_name = ref_city.utilities[0]
            new_tariff = sp.create_tariff(util_name=util_name)
    elif not np.pd.isnull(util_name):  # without util file we fall back to util name being listed
        if util_name in ref_city.utilities:  # we make sure the utility one available in city
            if not np.pd.isnull(tariff_id):  # tariff id is provided
                new_tariff = sp.create_tariff(util_file=util_file, tariff_name=tariff_id)
            else:  # tariff id is not provided
                new_tariff = sp.create_tariff(util_file=util_file)
        else:  # util is not in list, so we resort to first utility listed in city
            util_name = ref_city.utilities[0]
            new_tariff = sp.create_tariff(util_name=util_name)
    else:  # neither util file nor name have been provided, default to city list
        new_tariff = sp.create_tariff(util_name=ref_city.utilities[0])

    new_tariff.create_tou_schedule(tk.calendar)
    return new_tariff


house = make_house(ref_city=city)

pv = make_pv(ref_city=city, tk=timekeep)

tariff = make_tariff(ref_city=city, tk=timekeep)

per_arr = np.empty(shape=(0, 6))
i = 0
more_periods = True
while more_periods:
    e = tariff.get_end_of_period(step=i+1) - 1
    house_load = np.round(np.sum(house.load_profile[i:e+1])/12, 3)
    solar_input = np.round(np.sum(pv.power[i:e+1])/12, 3)
    arr = np.array([i+1, e+1, tariff.tou_schedule[i, 1], solar_input, house_load, np.round(solar_input-house_load, 3)])
    per_arr = np.vstack((per_arr, arr))
    if e == tariff.end - 1:
        more_periods = False
    i = e+1

print('lol')