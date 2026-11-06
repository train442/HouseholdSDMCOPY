import Parameters
from Components import *
import numpy as np
import pandas as pd
import Setup as sp
import Simulation as sm
import time
import pickle

# Temporary inputs

zip_code = 30269

ev_model = 'F-150 Lightning'
ev_year = 2022
ev_trim = '4WD SuperCrew'

hes_size = 0
hes_lvl2_rate = 10
hes_max_discharge = 7

# Create Operation Variable

timekeep = TimeKeep()

# print(timekeep.day_start_step)

# operation = Parameters.Operation(hes_optimization='full charge')

operation = Parameters.Operation(hes_optimization='full charge', ev_as_source=True, simu_name='atl_test5')

# Load EV/Fleet

driving_pattern = sp.create_driving_pattern(from_file=True, filename='basic_commute.csv')
# print(driving_pattern)
# print(len(driving_pattern))
ev_file = pd.read_csv('../Model Data/EVs.csv', index_col=False)
ev_ind = ev_file.index[(ev_file['Year'] == ev_year) & (ev_file['Model'] == ev_model) & (ev_file['Trim'] == ev_trim)]

# print(ev_file.loc[ev_ind, :])

ev = EV(ev_file.loc[ev_ind, 'Battery Size (kWh)'].values[0],
        ev_file.loc[ev_ind, 'Lvl2 Charge Rate (kW)'].values[0],
        True,
        1,  # EV ID
        ev_file.loc[ev_ind, 'Year'].values[0],
        ev_file.loc[ev_ind, 'Make'].values[0],
        ev_file.loc[ev_ind, 'Model'].values[0],
        ev_file.loc[ev_ind, 'Trim'].values[0],
        ev_file.loc[ev_ind, 'MSRP'].values[0],
        ev_file.loc[ev_ind, 'MPGe Hwy'].values[0],
        ev_file.loc[ev_ind, 'MPGe City'].values[0],
        ev_file.loc[ev_ind, 'MPGe Comb'].values[0],
        driving_pattern=driving_pattern,
        discharge_limit=.7)
# ev2 = EV(ev_file.loc[ev_ind, 'Battery Size (kWh)'].values[0],
#          ev_file.loc[ev_ind, 'Lvl2 Charge Rate (kW)'].values[0],
#          True,
#          2,  # EV ID
#          ev_file.loc[ev_ind, 'Year'].values[0],
#          ev_file.loc[ev_ind, 'Make'].values[0],
#          ev_file.loc[ev_ind, 'Model'].values[0],
#          ev_file.loc[ev_ind, 'Trim'].values[0],
#          ev_file.loc[ev_ind, 'MSRP'].values[0],
#          ev_file.loc[ev_ind, 'MPGe Hwy'].values[0],
#          ev_file.loc[ev_ind, 'MPGe City'].values[0],
#          ev_file.loc[ev_ind, 'MPGe Comb'].values[0],
#          driving_pattern=driving_pattern,
#         discharge_limit=.7))

# print(ev.batterySize)

ev_list = [ev]
# ev_list = [ev, ev2]
fleet = Fleet(ev_list)
fleet.reset_ids()
# Load HES

hes = HES(battery_size=hes_size, lvl2_max_rate=hes_lvl2_rate, use_curve=True, max_discharge=hes_max_discharge)

# Load City

city = sp.create_city(zipcode=zip_code)

# Load Tariff

utility = sp.create_tariff(util_file='Georgia Power Co_7140_tariffs.csv',
                            tariff_name='Schedule TOU-PEV-8 - Plug-in Electric Vehicle')
#utility = sp.create_tariff(util_file='Georgia Power Co_7140_tariffs.csv',
                           # tariff_name='SCHEDULE R-24 RESIDENTIAL SERVICE')




# utility = sp.create_tariff(util_file='Georgia Power Co_7140_tariffs.csv',
#                            tariff_name='SCHEDULE R-24 RESIDENTIAL SERVICE')

utility.create_tou_schedule(timekeep.calendar)
# print(utility.return_periods(1, 287))
# print(utility.get_next_off_peak(1))
# print(utility.weekday_rates)
# print(utility.periods_energy)
# print(utility.unique_tou_rates)
# print(utility.max_tiers)
# print(utility.weekday_schedule)

# print(utility.tou_schedule)


# Make grid

grid = Grid(
    emission_file='D:/Bras Research/pythonProject/City Data/CO2 Profiles/Cambium 2021/Processed/GA_Cambium_2022.csv')

# make house
load_file = 'D:/Bras Research/pythonProject/City Data/Load Profiles/Custom Loads/GA_Atlanta_11000kWh.csv'
house = House(load_file)
# print(np.sum(house.load_profile) / 12)
# make pv

ghi_file = 'D:/Bras Research/pythonProject/City Data/Solar Data/GA/GA_Atlanta_GHI_2018_5min.csv'
# pv = PV(system_size=10)
pv = PV(system_size=0)
pv.load_solar(solar_file=ghi_file)

t0 = time.time()
a = sm.run_simulation(operation=operation, city=city, tariff=utility, fleet=fleet,
                      pv=pv, hes=hes, grid=grid, house=house, timekeep=timekeep)
t1 = time.time()

t_tot = t1 - t0

print(a.bill.summary)
print(a.hes_avoidance)
print(a.fleet_avoidance)
print(a.solar_avoidance)
print(t_tot)

do_dump = False
if do_dump:
    direct = 'D:/Bras Research/pythonProject/Outputs/'
    filename = a.operation.simu_name + '.pkl'

    with open(direct + filename, 'wb') as f:
        pickle.dump(a, f)

# with open(direct + filename, 'rb') as f2:
#     b = pickle.load(f2)
#
# print(b)
