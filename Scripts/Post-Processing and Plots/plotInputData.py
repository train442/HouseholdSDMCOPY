import pandas as pd
from matplotlib import pyplot as plt
import numpy as np
from numpy import ndarray
import DataProcessing as dp
import Setup as sp
import Parameters as pm
"""
This script was made to plot pieces of data for the IDETC paper.
"""
do_solar = False
by_month = True

do_loads = False
usage = 11000

do_emissivity = False
date_of_day = '7/1/2018'
num_days = 1

do_tou_rates=  True

# Turn on/off cities

do_ATL = True
do_LA = True
do_POR = True
do_PHX = True

# correct usage
if usage not in [6000, 11000, 15000]:
    usage = 11000


def sum_days(profile: ndarray, input_type: str = None) -> ndarray:
    if input_type is None:
        input_type = 'solar'
    elif input_type not in ['solar', 'load', 'tou']:
        input_type = 'solar'

    i = 0
    day_profile = np.array([])
    for d in range(365):
        if input_type == 'solar':
            day_profile = np.append(day_profile, np.sum(profile[i * (12 * 24):(i + 1) * (12 * 24)] / 12 / 1000))
        elif input_type == 'tou':
            day_profile = np.append(day_profile, np.max(profile[i * (12 * 24):(i + 1) * (12 * 24)]))
        else:
            day_profile = np.append(day_profile, np.sum(profile[i * (12 * 24):(i + 1) * (12 * 24)] / 12))
        i += 1
    return day_profile


def sum_months(profile: ndarray):
    days_in_months = [0, 31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    month_profile = []
    s = 0
    e = 0
    for m in range(12):
        s += days_in_months[m]
        e += days_in_months[m + 1] + 1
        month_profile.append(np.sum(profile[s:e]))
    return month_profile


# filepath = 'City Data/Solar Data/GA/GA_Atlanta_GHI_2018_5min.csv'
if do_solar:
    if do_POR:
        filepath = 'City Data/Solar Data/OR/OR_Portland_GHI_2018_5min.csv'
        solar_frame = pd.read_csv(filepath)
        y1 = solar_frame['GHI(W/m^2)'].to_numpy()
        y1 = sum_days(y1)
        if by_month:
            y1 = sum_months(y1)

        plt.plot(y1, label='Portland, Oregon')

    if do_PHX:
        filepath2 = 'City Data/Solar Data/AZ/AZ_Phoenix_GHI_2018_5min.csv'
        solar_frame2 = pd.read_csv(filepath2)
        y2 = solar_frame2['GHI(W/m^2)'].to_numpy()
        y2 = sum_days(y2)
        if by_month:
            y2 = sum_months(y2)
        plt.plot(y2, label='Phoenix, Arizona')

    if do_LA:
        filepath3 = 'City Data/Solar Data/CA/CA_Los Angeles_GHI_2018_5min.csv'
        solar_frame3 = pd.read_csv(filepath3)
        y3 = solar_frame3['GHI(W/m^2)'].to_numpy()
        y3 = sum_days(y3)
        if by_month:
            y3 = sum_months(y3)
        plt.plot(y3, label='Los Angeles, California')

    if do_ATL:
        filepath4 = 'City Data/Solar Data/GA/GA_Atlanta_GHI_2018_5min.csv'
        solar_frame4 = pd.read_csv(filepath4)
        y4 = solar_frame4['GHI(W/m^2)'].to_numpy()
        y4 = sum_days(y4)
        if by_month:
            y4 = sum_months(y4)
        plt.plot(y4, label='Atlanta, Georgia')

    if by_month:
        plt.title('Solar Energy (kWh/m^2) vs Month')
        plt.xlabel('Month of Year')
        plt.ylabel('Solar Energy (kWh/m^2)')
    else:
        plt.title('GHI (kWh/m^2/day) vs Day')
        plt.xlabel('Day of Year')
        plt.ylabel('Solar Energy (kWh/m^2/day)')

    plt.legend()
    plt.show()

if do_loads:
    if do_POR:
        filepath = f'City Data/Load Profiles/Custom Loads/OR_Portland_{usage}kWh.csv'
        load_frame = pd.read_csv(filepath)
        y1 = load_frame['Load(kW)'].to_numpy()
        y1 = sum_days(y1, input_type='load')
        if by_month:
            y1 = sum_months(y1)

        plt.plot(y1, label='Portland, Oregon')

    if do_PHX:
        filepath2 = f'City Data/Load Profiles/Custom Loads/AZ_Phoenix_{usage}kWh.csv'
        load_frame2 = pd.read_csv(filepath2)
        y2 = load_frame2['Load(kW)'].to_numpy()
        y2 = sum_days(y2, input_type='load')
        if by_month:
            y2 = sum_months(y2)
        plt.plot(y2, label='Phoenix, Arizona')

    if do_LA:
        filepath3 = f'City Data/Load Profiles/Custom Loads/CA_Los Angeles_{usage}kWh.csv'
        load_frame3 = pd.read_csv(filepath3)
        y3 = load_frame3['Load(kW)'].to_numpy()
        y3 = sum_days(y3, input_type='load')
        if by_month:
            y3 = sum_months(y3)
        plt.plot(y3, label='Los Angeles, California')

    if do_ATL:
        filepath4 = f'City Data/Load Profiles/Custom Loads/GA_Atlanta_{usage}kWh.csv'
        load_frame4 = pd.read_csv(filepath4)
        y4 = load_frame4['Load(kW)'].to_numpy()
        y4 = sum_days(y4, input_type='load')
        if by_month:
            y4 = sum_months(y4)
        plt.plot(y4, label='Atlanta, Georgia')

    if by_month:
        plt.title('House Load (kWh) vs Month')
        plt.xlabel('Month of Year')
        plt.ylabel('House Load (kWh)')
    else:
        plt.title('House Load (kWH) vs Day')
        plt.xlabel('Day of Year')
        plt.ylabel('House Load (kWh)')

    plt.legend()
    plt.show()

if do_emissivity:
    start_date = pd.to_datetime(date_of_day)
    s = dp.datetime_to_timestep(datetime=pd.to_datetime(date_of_day))
    end_date = start_date + pd.Timedelta(f'{num_days} days')
    e = dp.datetime_to_timestep(datetime=end_date)

    x = np.linspace(start=0,stop=24,num=24*12)

    if do_POR:
        filepath = 'City Data/CO2 Profiles/Cambium 2021/Processed/OR_Cambium_2022.csv'
        co2_frame = pd.read_csv(filepath)
        y1 = co2_frame['Emissivity'].to_numpy()
        y1 = y1[s:e]
        plt.plot(x, y1, label='Portland, Oregon')

    if do_PHX:
        filepath2 = 'City Data/CO2 Profiles/Cambium 2021/Processed/AZ_Cambium_2022.csv'
        co2_frame2 = pd.read_csv(filepath2)
        y2 = co2_frame2['Emissivity'].to_numpy()
        y2 = y2[s:e]
        plt.plot(x, y2, label='Phoenix, Arizona')

    if do_LA:
        filepath3 = 'City Data/CO2 Profiles/Cambium 2021/Processed/CA_Cambium_2022.csv'
        co2_frame3 = pd.read_csv(filepath3)
        y3 = co2_frame3['Emissivity'].to_numpy()
        y3 = y3[s:e]
        plt.plot(x, y3, label='Los Angeles, California')

    if do_ATL:
        filepath4 = 'City Data/CO2 Profiles/Cambium 2021/Processed/GA_Cambium_2022.csv'
        co2_frame4 = pd.read_csv(filepath4)
        y4 = co2_frame4['Emissivity'].to_numpy()
        y4 = y4[s:e]
        plt.plot(x, y4, label='Atlanta, Georgia')

    plt.title('Grid Emissivity (kgCO2/kWh) vs Time for Summer Day')
    plt.xlabel('Hour')
    plt.ylabel('Grid Emissivity (kgCO2/kWh)')

    plt.legend()
    plt.show()


if do_tou_rates:
    cal = pm.TimeKeep().calendar
    if do_POR:
        util_file = 'Portland General Electric Co_15248_tariffs.csv'
        tariff = 'Residential Time-Of-Use Service (Rate 7-TOU of EV)'
        util = sp.create_tariff(util_file=util_file, tariff_name=tariff)
        util.create_tou_schedule(calendar=cal)
        y1 = util.tou_schedule[:,0]
        y1 = sum_days(profile=y1, input_type='tou')
        plt.plot(y1, label='Portland, Oregon')

    if do_PHX:
        util_file = 'Arizona Public Service Co_803_tariffs.csv'
        tariff = 'Time-of-Use 4pm-7pm Weekdays (R-TOU-E)'
        util = sp.create_tariff(util_file=util_file, tariff_name=tariff)
        util.create_tou_schedule(calendar=cal)
        y2 = util.tou_schedule[:,0]
        y2 = sum_days(profile=y2, input_type='tou')
        plt.plot(y2, label='Phoenix, Arizona')

    if do_LA:
        util_file = 'Southern California Edison Co_17609_tariffs.csv'
        tariff = 'Time-of-use Tiered Domestic (NEM 2.0): TOU-D-B'
        util = sp.create_tariff(util_file=util_file, tariff_name=tariff)
        util.create_tou_schedule(calendar=cal)
        y3 = util.tou_schedule[:, 0]
        y3 = sum_days(profile=y3, input_type='tou')
        plt.plot(y3, label='Los Angeles, California')

    if do_ATL:
        util_file = 'Georgia Power Co_7140_tariffs.csv'
        tariff = 'Schedule TOU-PEV-11- Plug-in Electric Vehicle'
        util = sp.create_tariff(util_file=util_file, tariff_name=tariff)
        util.create_tou_schedule(calendar=cal)
        y4 = util.tou_schedule[:,0]
        y4 = sum_days(profile=y4, input_type='tou')
        plt.plot(y4, label='Atlanta, Georgia')

    plt.title('Peak Rate ($/kWh) vs Time')
    plt.xlabel('Day of Year')
    plt.ylabel('Peak Rate ($/kWh)')

    plt.legend()
    plt.show()
    pass
