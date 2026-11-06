# ##############################################################################################################
# ARCHIVED PRE-OPTIMIZATION COPY -- runScenarioFiles.py
# ##############################################################################################################
#
# This is runScenarioFiles.py as it stood BEFORE the August 2026 optimization pass, reconstructed by
# reverse-applying every change and then VERIFIED: running this copy reproduces the original
# 6-scenario benchmark timing and results that are bit-identical to the pre-change baseline
# across 16 pickled Results objects and four 55-column summary CSVs.
#
# It is kept for review only. It is NOT imported by anything and must not be.
#
# Annotations are inserted directly above the code they describe, tagged:
#     [T1-nn]   APPLIED   -- runtime work, already live in the root module
#     [T1.9-nn] PROPOSED  -- collection scheduling
#     [T2-nn]   PROPOSED  -- results storage
#     [T3-nn]   PROPOSED  -- correctness fixes (these change outputs)
#     [T4-nn]   PROPOSED  -- conventions, typing, dead code
#
# Measured effect of the APPLIED work: 3.13 -> 1.44 s per scenario (2.17x), outputs unchanged.
# Full write-up: PROPOSED_CHANGES.md and ARCHITECTURE.md in the repository root.
# ##############################################################################################################

# ================================================================================================================
# [T4-01] PROPOSED -- Dead duplicate module
# LOCATION: whole file
# ----------------------------------------------------------------------------------------------------------------
# This file duplicates twelve functions from Simulation.py: make_ev, make_timekeep, rows_match,
# get_reset_dict, make_city, make_tariff, make_house, make_grid, make_pv, make_fleet, get_baseline
# and check_resolution.
# 
# NOTHING IMPORTS IT. The live entry point is main.py -> Simulation.run_model. The README still
# describes this as "the script that must be executed", which is no longer true.
# 
# Its copies have already drifted from the originals, and it carries the same rows_match bug
# described in T3-02 -- so fixing Simulation.py leaves a second broken copy behind. That is exactly
# the failure mode duplicate code produces.
# 
# AGREED PLAN: this annotated copy is the archive; the original at the repository root is cleaned
# up in place, and the README corrected.
# ================================================================================================================
import Parameters as pm
from Components import *
import numpy as np
import pandas as pd
import Setup as sp
import DataProcessing as dp
import Simulation as sm
import copy
import time
import pickle
import os
import warnings

warnings.simplefilter(action='ignore', category=FutureWarning)
save_loads = False

overwrite_scenarios = False  # Set to True if you wish to overwrite runs.

ev_model_frame = pd.read_csv('Model Data/EVs.csv')
pv_model_frame = pd.read_excel('Model Data/PVs.xlsx')
match_city_frame = pd.read_csv('Model Data/city_list.csv')
zip_frame = pd.read_csv('Model Data/zip_directory.csv', dtype={'Zip Code': str})

scenario_input_file = input('Please input scenario input file:  ')

collection_name = input('What is the title of these runs?:   ')

# we check if necessary directories exist, if not we make them
if not os.path.isdir('Outputs/' + collection_name):
    os.mkdir('Outputs/' + collection_name)

if not os.path.isdir('Outputs/' + collection_name + '/Results'):
    os.mkdir('Outputs/' + collection_name + '/Results')

# Load scenario list file
scenario_frame = pd.read_excel('InputFiles/' + scenario_input_file + '.xlsx', header=2,
                               dtype={'Zip Code': str, 'Discharge Limit': float},
                               parse_dates=['Start Date', 'End Date'])

# Make list of summary file columns
summary_columns = ['ID', 'City', 'State', 'Reference City', 'Reference State', 'Utility', 'Tariff', 'Solar Model',
                   'Solar Size (kW)', 'HES Size', 'HES Optimization', 'EV Models', 'EV Discharge Limit',
                   'Total Bill ($)', 'Total CO2 (kg)', 'PV Avoided Cost ($)', 'PV Avoided CO2 (kg)',
                   'HES Avoided Cost ($)', 'HES Avoided CO2 (kg)', 'Fleet Avoided Cost ($)', 'Fleet Avoided CO2 (kg)',
                   'Time Elapsed (s)']

summary_frame = pd.DataFrame(columns=summary_columns)


# define function to make ev from ev file or given info

def make_ev(new_year, new_make, new_model, new_trim, new_ev_pattern, new_ev_limit):
    ev_ind = ev_model_frame.index[(ev_model_frame['Year'] == new_year) & (ev_model_frame['Model'] == new_model) &
                                  (ev_model_frame['Trim'] == new_trim) & (ev_model_frame['Make'] == new_make)]
    new_ev = EV(ev_model_frame.loc[ev_ind, 'Battery Size (kWh)'].values[0],
                ev_model_frame.loc[ev_ind, 'Lvl2 Charge Rate (kW)'].values[0],
                True,
                1,  # EV ID
                ev_model_frame.loc[ev_ind, 'Year'].values[0],
                ev_model_frame.loc[ev_ind, 'Make'].values[0],
                ev_model_frame.loc[ev_ind, 'Model'].values[0],
                ev_model_frame.loc[ev_ind, 'Trim'].values[0],
                ev_model_frame.loc[ev_ind, 'MSRP'].values[0],
                ev_model_frame.loc[ev_ind, 'MPGe Hwy'].values[0],
                ev_model_frame.loc[ev_ind, 'MPGe City'].values[0],
                ev_model_frame.loc[ev_ind, 'MPGe Comb'].values[0],
                driving_pattern=new_ev_pattern,
                discharge_limit=new_ev_limit)

    return new_ev


def check_resolution(resolution):
    options = [1, 5, 10, 15, 20, 30, 60]
    if resolution not in options:
        if (type(resolution) not in [int, float]) or np.isnan(resolution):
            resolution = 5
        else:  # resolution is a number, but just not a supported one, so we find the closest option
            resolution = min(options, key=lambda x: abs(x - resolution))

    return resolution


def make_timekeep(time_dict: dict, resolution=5):
    #  this takes the time-related scenario variables and makes a timekeep object

    if not pd.isna(time_dict['Start Date']):  # we check if start date is provided
        if not pd.isna(time_dict['End Date']):
            time_keeper = pm.TimeKeep(from_date=True, start_date=time_dict['Start Date'],
                                      end_date=time_dict['End Date'], timestep=resolution)
        elif not pd.isna(time_dict['Sim Days']):
            time_dict['End Date'] = time_dict['Start Date'] + pd.Timedelta(str(time_dict['Sim Days']))
            time_keeper = pm.TimeKeep(from_date=True, start_date=time_dict['Start Date'],
                                      end_date=time_dict['End Date'], timestep=resolution)
        else:  # we assume that sim runs until end of year
            time_dict['End Date'] = pd.Timestamp('12/31/' + str(time_dict['Start Date'].year))
            time_keeper = pm.TimeKeep(from_date=True, start_date=time_dict['Start Date'],
                                      end_date=time_dict['End Date'], timestep=resolution)
    else:  # start date is not given
        if not pd.isna(time_dict['End Date']):  # but end date is given somehow
            if not pd.isna(time_dict['Start Day']):  # we see if starting DOY is given
                time_dict['Start Date'] = time_dict['End Date'] - pd.Timedelta(str(time_dict['End Date'].day_of_year -
                                                                                   time_dict['Start Day']) + ' days')
                if time_dict['End Date'] < time_dict['Start Date']:  # we correct if start DOY is later than end date
                    time_dict['Start Date'] = pd.Timestamp('1/1/' + str(time_dict['End Date'].year))  # correct to 1/1
                time_keeper = pm.TimeKeep(from_date=True, start_date=time_dict['Start Date'],
                                          end_date=time_dict['End Date'], timestep=resolution)
            elif not pd.isna(time_dict['Sim Days']):  # we see if simulation days are given and we count backwards
                time_dict['Start Date'] = time_dict['End Date'] - pd.Timedelta(str(time_dict['Sim Days'] - 1) + 'days')
                time_keeper = pm.TimeKeep(from_date=True, start_date=time_dict['Start Date'],
                                          end_date=time_dict['End Date'], timestep=resolution)
            else:  # in absence of other information, we assume that start date is Jan 1st of same year.
                time_dict['Start Date'] = pd.Timestamp('1/1/' + str(time_dict['End Date'].year))
                time_keeper = pm.TimeKeep(from_date=True, start_date=time_dict['Start Date'],
                                          end_date=time_dict['End Date'], timestep=resolution)
        else:  # neither date is given
            if pd.isna(time_dict['Year']) | (type(time_dict['Year']) not in [int, float]):
                time_dict['Year'] = 2018  # we default year to 2018
            if pd.isna(time_dict['Start Day']) | (type(time_dict['Start Day']) not in [int, float]):
                time_dict['Start Day'] = 1
            if pd.isna(time_dict['Sim Days']) | (type(time_dict['Sim Days']) not in [int, float]):
                time_dict['Sim Days'] = 365
            time_keeper = pm.TimeKeep(from_date=False, starting_day=time_dict['Start Day'],
                                      simu_days=time_dict['Sim Days'], year=time_dict['Year'], timestep=resolution)
    return time_keeper


def rows_match(old_row: (pd.Series, None), new_row: pd.Series, options: list):
    # This function returns whether the given columns (options) in the rows given match.
    boolean = True
    for col in options:
        try:
            boolean *= (new_row[col] == old_row[col]) or (np.isnan(new_row[col]) and np.isnan(new_row[col]))
        except TypeError:
            boolean *= (new_row[col] == old_row[col]) or (pd.isna(new_row[col]) and pd.isna(new_row[col]))
    return boolean


def get_reset_dict(old_row: (pd.Series, None), new_row: pd.Series):
    # this function returns a dictionary full of booleans which tells the model to use the same components as the
    # previous scenario or to load new ones

    reset_dict = {'New Timekeep': True,
                  'New City': True,
                  'New House': True,
                  'New Tariff': True,
                  'New Grid': True,
                  'New PV': True,
                  'New HES': True,
                  'New Fleet': True}

    if old_row is not None:  # we pass none on the very first scenario
        # first we see if we need new timekeep variable, if so we reset every component which relies on it.
        if new_row['User File'] == old_row['User File']:
            reset_dict['New Timekeep'] = False  # user provided file is same so no need to change
            reset_dict['New House'] = False
        elif (new_row['Start Date'] == old_row['Start Date']) and (new_row['End Date'] == old_row['End Date']):
            reset_dict['New Timekeep'] = False  # dates match so no need to change
        else:
            opt = ['Start Date', 'End Date', 'Year', 'Simulation Days', 'Start Day']
            reset_dict['New Timekeep'] = not rows_match(old_row=old_row, new_row=new_row, options=opt)

        # We check if we have to make new city object
        if new_row['Zip Code'] == old_row['Zip Code']:
            reset_dict['New City'] = False
        elif (new_row['State'] == old_row['State']) and (new_row['City'] == old_row['City']):
            reset_dict['New City'] = False

        # We check other components should we not have to change timekeep object
        # (otherwise we change the rest by default)
        if not reset_dict['New Timekeep']:
            # check Tariff object
            opt = ['Utility Name', 'Utility File', 'Tariff ID']
            reset_dict['New Tariff'] = not rows_match(old_row=old_row, new_row=new_row, options=opt)

            # Check grid object
            opt = ['Use Cambium', 'Other File']
            opt += [c for c in ('Use WattTime', 'WattTime Year') if c in new_row.index and c in old_row.index]
            reset_dict['New Grid'] = not rows_match(old_row=old_row, new_row=new_row, options=opt)

            # Check PV Object
            if old_row['Other Solar File'] == new_row['Other Solar File']:
                reset_dict['New PV'] = False
            else:
                opt = ['System Size (kW)', 'PV Brand', 'PV Model']
                reset_dict['New PV'] = not rows_match(old_row=old_row, new_row=new_row, options=opt)

            # Check HES Object
            opt = ['Size (kWh)', 'HES Min SoC', 'HES Max SoC', 'Optimization']
            reset_dict['New HES'] = not rows_match(old_row=old_row, new_row=new_row, options=opt)

            # Check EV/Fleet

            if old_row['EV File'] == new_row['EV File']:
                reset_dict['New Fleet'] = False
            else:
                opt = ['Discharge Limit', 'EV Min SoC', 'EV Max SoC', 'EV Year', 'Make', 'Model', 'Trim', 'Pattern',
                       'Qty']
                reset_dict['New Fleet'] = not rows_match(old_row=old_row, new_row=new_row, options=opt)
    return reset_dict


def make_city(new_row: pd.Series):
    # pass row to make a new city object
    zipcode = new_row['Zip Code']
    if not np.isnan(int(zipcode)):  # file is given a zip code, which overrides city and state entry.
        new_city = sp.create_city(zipcode=zipcode)
    else:  # file is given by city and state entry, which must match a city in reference list
        city_name = new_row['City']
        state_name = new_row['State']
        new_city = sp.create_city(name=city_name, st_abr=state_name, from_zip=False)
    return new_city


def make_tariff(new_row: pd.Series, ref_city: pm.City, tk: pm.TimeKeep):
    # pass current row and city object to make tariff object
    util_file = new_row['Utility File']
    util_name = new_row['Utility Name']
    tariff_id = new_row['Tariff ID']
    if not pd.isnull(util_file):  # util file is provided
        util_name = util_file.split('_')[0]
        if util_name in (ref_city.utilities + ['Custom']):  # we make sure the utility one available in city or Custom
            if not pd.isnull(tariff_id):  # tariff id is provided
                new_tariff = sp.create_tariff(util_file=util_file, tariff_name=tariff_id)
            else:  # tariff id is not provided
                new_tariff = sp.create_tariff(util_file=util_file)
        else:  # util is not in list, so we resort to first utility listed in city
            util_name = ref_city.utilities[0]
            new_tariff = sp.create_tariff(util_name=util_name)
    elif not pd.isnull(util_name):  # without util file we fall back to util name being listed
        if util_name in ref_city.utilities:  # we make sure the utility one available in city
            if not pd.isnull(tariff_id):  # tariff id is provided
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


def make_house(new_row: pd.Series, ref_city: pm.City, op: pm.Operation, user_dataframe: (None, pd.DataFrame)):
    load_file = new_row['Load File']
    load_amount = new_row['Load Amount']

    if op.user_profile:
        summary = dp.monthly_load_summary(user_dataframe)
        load_profile = dp.load_match_monthly(state=ref_city.matched_state, city=ref_city.matched_city, summary=summary)
        load_profile = dp.normalize_profile_hourly(original=load_profile,
                                                   normalizer=user_dataframe['Usage (kWh)'].to_numpy())
        new_house = House(load_profile=load_profile)
    elif not pd.isnull(load_file) and os.path.exists('City Data/Load Profiles/Custom Loads/' + load_file + '.csv'):
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
                                                  usage=load_amount, save_profile=save_loads))
    else:  # we assume basic US average usage
        new_house = House(load_profile=dp.load_match_yearly(state=ref_city.matched_state, city=ref_city.matched_city,
                                                            usage=11000, save_profile=save_loads))
    return new_house


def make_grid(new_row: pd.Series, ref_city: pm.City, tk: pm.TimeKeep):
    # provide current row and reference city to create grid object
    use_cambium = new_row['Use Cambium']
    use_wattime = ('Use WattTime' in new_row.index and not pd.isnull(new_row['Use WattTime'])
                   and bool(new_row['Use WattTime']))
    other_emissions_file = new_row['Other File']
    wattime_year = sm.WATTTIME_DEFAULT_YEAR

    if use_cambium:
        emissions_file = ref_city.matched_state + '_Cambium_2022.csv'
        new_grid = Grid(emission_file='City Data/CO2 Profiles/Cambium 2021/Processed/' + emissions_file)
    elif use_wattime:
        if not ref_city.matched_wattime_region:
            raise Exception(f"'Use WattTime' is set for {ref_city.matched_city}, {ref_city.matched_state} but it "
                            f"has no resolved WattTime region -- run 'Resolve All Regions' (or a Single City "
                            f"fetch) for it in the Data Import Wizard's WattTime tab first.")
        if 'WattTime Year' in new_row.index and not pd.isnull(new_row['WattTime Year']):
            wattime_year = int(new_row['WattTime Year'])
        emissions_file = f'{ref_city.matched_wattime_region}_{ref_city.time_zone}_WattTime_{wattime_year}.csv'
        new_grid = Grid(emission_file='City Data/CO2 Profiles/WattTime/Processed/' + emissions_file)
    elif not pd.isnull(other_emissions_file):
        custom_path = 'City Data/CO2 Profiles/Custom/' + other_emissions_file
        wattime_path = 'City Data/CO2 Profiles/WattTime/Processed/' + other_emissions_file
        if os.path.exists(custom_path):
            new_grid = Grid(emission_file=custom_path)
        elif os.path.exists(wattime_path):
            new_grid = Grid(emission_file=wattime_path)
        else:  # file doesn't exist. default to city flat rate
            new_grid = Grid(flat_emission_rate=ref_city.carbon_intensity)
    else:
        new_grid = Grid(flat_emission_rate=ref_city.carbon_intensity)

    if use_wattime:
        new_grid.change_dates(start_date=tk.start_date, end_date=tk.end_date, cambium=False, file_year=wattime_year)
    else:
        new_grid.change_dates(start_date=tk.start_date, end_date=tk.end_date, cambium=use_cambium)

    return new_grid


def make_pv(new_row: pd.Series, ref_city: pm.City, tk: pm.TimeKeep):
    # Provide current row and reference city to make PV object
    pv_brand = new_row['PV Brand']
    pv_model = new_row['PV Model']
    pv_size = new_row['System Size (kW)']
    if np.isnan(pv_size):
        pv_size = 0
    else:
        pv_size = min(max(pv_size, 0), 10)

    if pd.isnull(pv_brand) or pd.isnull(pv_model):
        new_pv = PV(system_size=pv_size)
    else:
        new_pv = PV(system_size=pv_size, brand=pv_brand, model=pv_model)

    other_solar_file = new_row['Other Solar File']
    if pd.isnull(other_solar_file):  # we default to NREL 2018 for reference city
        ghi_file = ref_city.matched_state + '_' + ref_city.matched_city + '_GHI_2018_5min.csv'
        ghi_dir = 'City Data/Solar Data/' + ref_city.matched_state + '/'
        new_pv.load_solar(solar_file=ghi_dir + ghi_file, start_date=tk.start_date, end_date=tk.end_date)
    else:  # we use other file
        new_pv.load_solar(solar_file='City Data/Solar Data/Custom/' + other_solar_file, start_date=tk.start_date,
                          end_date=tk.end_date)
    return new_pv


def make_fleet(new_row: pd.Series, tk: pm.TimeKeep):
    # provide current row to make new fleet object
    ev_list = []

    #  We check for EV file, if not there we default to the ones listed.
    ev_file = new_row['EV File']
    if not pd.isnull(ev_file):
        ev_list_frame = pd.read_excel('InputFiles/EV Files/' + ev_file)
        for ev_index, ev_row in ev_list_frame.iterrows():
            ev_limit = new_row['Discharge Limit']
            if pd.isnull(ev_limit):
                ev_limit = ev_row['Discharge Limit']
            ev_year = ev_row['Year']
            ev_model = ev_row['Model']
            ev_make = ev_row['Make']
            ev_trim = ev_row['Trim']
            ev_pattern_file = ev_row['Pattern']
            if pd.isnull(ev_pattern_file):
                ev_pattern = sp.driving_pattern_from_calendar(timekeep=tk, filename='basic_commute.csv')
            else:
                ev_pattern = sp.driving_pattern_from_calendar(timekeep=tk, filename=ev_pattern_file + '.csv')
            ev_qty = ev_row['Qty']
            add_ev = make_ev(new_year=ev_year, new_model=ev_model, new_make=ev_make, new_trim=ev_trim,
                             new_ev_pattern=ev_pattern, new_ev_limit=ev_limit)
            if np.isnan(ev_qty):
                ev_qty = 1
            for j in range(ev_qty):
                ev_list.append(copy.deepcopy(add_ev))
    else:
        ev1_limit = new_row['Discharge Limit']
        ev1_year = new_row['EV Year']
        ev1_make = new_row['Make']
        ev1_model = new_row['Model']
        ev1_trim = new_row['Trim']
        ev1_pattern_file = new_row['Pattern']
        if pd.isnull(ev1_pattern_file):
            ev1_pattern = sp.create_driving_pattern(from_file=True, filename='basic_commute.csv')
        else:
            ev1_pattern = sp.create_driving_pattern(from_file=True, filename=ev1_pattern_file + '.csv')

        ev1_qty = new_row['Qty']
        if np.isnan(ev1_qty):
            ev1_qty = 1
        if not np.isnan(ev1_year):
            add_ev = make_ev(new_year=ev1_year, new_make=ev1_make, new_model=ev1_model, new_trim=ev1_trim,
                             new_ev_pattern=ev1_pattern, new_ev_limit=ev1_limit)
            for j in range(ev1_qty):
                ev_list.append(copy.deepcopy(add_ev))

    new_fleet = Fleet(ev_list)
    return new_fleet


def get_baseline(baseline_frame: pd.DataFrame, line: pd.Series):
    # this function finds the baseline scenario for comparison given a current row in a summary frame
    sub_frame = baseline_frame[(baseline_frame['City'] == line['City']) &
                               (baseline_frame['State'] == line['State']) &
                               (baseline_frame['Start Date'] == line['Start Date']) &
                               (baseline_frame['End Date'] == line['End Date']) &
                               (baseline_frame['Utility'] == line['Utility']) &
                               (baseline_frame['Tariff'] == line['Tariff']) &
                               (baseline_frame['EV Models'] == line['EV Models']) &
                               (baseline_frame['Solar Model'] == line['Solar Model']) &
                               (baseline_frame['House Load'] == line['House Load']) &
                               (baseline_frame['HES Optimization'] == line['HES Optimization']) &
                               (baseline_frame['Net Meter Policy'] == line['Net Meter Policy'])]
    return sub_frame


#  We iterate through rows of scenario file
timekeep = None
house = None
city = None
grid = None
pv = None
fleet = Fleet([])
hes = None
tariff = None
i = 0
prev_row = None
for index, row in scenario_frame.iterrows():
    t0 = time.time()

    reset_comps = get_reset_dict(old_row=prev_row, new_row=row)
    # Get file ID
    scen_id = row['ScenarioID']
    scenario_filename = collection_name + '_Run_' + str(scen_id) + '.pkl'

    # Check for User Load File
    # if a user profile is provided, its dates will define the time limits of the simulation
    user_file = row['User File']

    if pd.isna(user_file):
        user_profile_given = False
    else:
        if os.path.exists('City Data/Load Profiles/User Profiles/' + user_file + '.csv'):
            user_profile_given = True
        else:
            user_profile_given = False

    if user_profile_given:
        user_frame = pd.read_csv('City Data/Load Profiles/User Profiles/' + user_file + '.csv', parse_dates=['Time'],
                                 dtype={'Usage (kWh)': float})
        load_start = user_frame.iloc[0, 0]
        delT = (user_frame.iloc[1, 0] - user_frame.iloc[0, 0])
        load_res = delT.components.hours * 60 + delT.components.minutes
        load_end = user_frame.iloc[-1, 0]
    else:
        user_frame = None
        load_start = pd.Timestamp('1/1/2018')
        load_end = pd.Timestamp('12/31/2018 23:55')
        load_res = 5

    # Create Operation object  (this will change for every run, since every run has different ID)

    opt_method = row['Optimization']
    net_meter_method = row['Net Meter Type']
    operation = pm.Operation(ev_discharge_limit=row['Discharge Limit'], simu_name=collection_name, simu_id=str(scen_id),
                             hes_optimization=opt_method, net_meter_scheme=net_meter_method,
                             user_profile=user_profile_given)

    # Create Timekeep object
    if reset_comps['New Timekeep']:
        time_resolution = check_resolution(row['TimeStep'])
        year = row['Year']
        simulation_days = row['Simulation Days']
        simu_start_day = row['Start Day']
        start_date = row['Start Date']
        end_date = row['End Date']

        if user_profile_given:
            start_date = load_start
            end_date = load_end

        timekeep_dict = {'Sim Days': simulation_days, 'Start Day': simu_start_day, 'Start Date': start_date,
                         'End Date': end_date, 'Year': year}

        timekeep = make_timekeep(time_dict=timekeep_dict, resolution=time_resolution)
    else:
        timekeep.reset()

    # timekeep = pm.TimeKeep(year=year, starting_day=simu_start_day, simu_days=simulation_days)

    # Create City object
    if reset_comps['New City']:
        city = make_city(new_row=row)

    # Create Tariff Object

    if reset_comps['New Tariff']:
        tariff = make_tariff(new_row=row, ref_city=city, tk=timekeep)
    else:
        tariff.reset()

    # Create House Object

    if reset_comps['New House']:
        house = make_house(new_row=row, ref_city=city, op=operation, user_dataframe=user_frame)
    else:
        house.reset()

    # Create Grid object
    if reset_comps['New Grid']:
        grid = make_grid(new_row=row, ref_city=city, tk=timekeep)
    else:
        grid.reset()

    # create Solar Object
    if reset_comps['New PV']:
        pv = make_pv(new_row=row, ref_city=city, tk=timekeep)

    # create HES object
    if reset_comps['New HES']:
        hes = HES(battery_size=row['Size (kWh)'], lvl2_max_rate=10, max_discharge=7, use_curve=True)
    else:
        hes.reset()

    #  Create Fleet/EV Objects
    if reset_comps['New Fleet']:
        fleet = make_fleet(new_row=row, tk=timekeep)
    else:
        fleet.reset_evs(new_limit=row['Discharge Limit'])

    # load ICE for comparison
    ice = ICE()

    # We run the simulation now

    result = sm.run_simulation(operation=operation, timekeep=timekeep, city=city, grid=grid, tariff=tariff,
                               house=house, pv=pv, hes=hes, fleet=fleet, ice=ice)

    with open('Outputs/' + collection_name + '/Results/' + scenario_filename, 'wb') as f:
        pickle.dump(result, f)

    t1 = time.time()
    t_tot = t1 - t0

    # Retrieve data for summary file
    data = {'ID': scen_id,
            'File Name': scenario_filename,
            'Time Elapsed (s)': np.round(t_tot, 3),
            'Start Date': result.timekeep.start_date,
            'End Date': result.timekeep.end_date,
            'City': city.name,
            'State': city.state,
            'Reference City': city.matched_city,
            'Reference State': city.matched_state,
            'House Load': np.round(result.house.usage, 1),
            'Utility': result.tariff.utility,
            'Tariff': result.tariff.name,
            'Net Meter Policy': result.operation.net_meter_scheme,
            'Solar Model': result.pv.model,
            'Solar Size (kW)': result.pv.system_size,
            'Solar Cost ($)': np.round(result.pv_cost, 2),
            'HES Size': result.hes.batterySize,
            'HES Cost ($)': np.round(result.hes_cost, 2),
            'HES Optimization': result.operation.hes_optimization,
            'HES Avg SoC Target': 0,
            'EV Models': result.fleet.get_ev_list(),
            'EV Discharge Limit': result.operation.ev_discharge_limit,
            'Fleet Cost ($)': np.round(result.fleet.fleet_cost(), 2),
            'Total Bill ($)': np.round(result.bill.total_bill, 2),
            'Total CO2 (kg)': np.round(result.bill.co2_emissions, 2),
            'PV Avoided Cost ($)': np.round(result.solar_avoidance, 2),
            'PV Avoided CO2 (kg)': np.round(result.solar_co2_savings, 2),
            'HES Avoided Cost ($)': np.round(result.hes_avoidance, 2),
            'HES Avoided CO2 (kg)': np.round(result.hes_co2_savings, 2),
            'Fleet Avoided Cost ($)': np.round(result.fleet_avoidance, 2),
            'Fleet Avoided CO2 (kg)': np.round(result.fleet_co2_savings, 2),
            'Fleet Sim Miles (mi)': np.round(result.fleet.fleet_sim_miles(), 2),
            'Fleet Driven Miles (mi)': np.round(result.fleet.fleet_driven_miles(), 2),
            'EV Degradation ($)': np.round(result.ev_degradations[0]),
            'EV Breakeven Mileage (mi)': np.round(result.ev_breakeven_miles[0]),
            'EV Breakeven Cost ($/kWh)': np.round(result.ev_breakeven_cost[0]),
            'System Loss (kWh)': np.round(np.sum(result.energy.loss), 2),
            'Cost of Loss ($)': np.round(np.sum(result.energy.cost_of_loss), 2),
            'Emissions from Loss (kg)': np.round(np.sum(result.energy.loss_emissions), 2),
            'Fleet Driving Cost ($)': np.round(result.fleet_driving_costs, 2),
            'Gas Savings ($)': np.round(result.gas_savings, 2),
            'Total Avoidance($)': np.round(result.total_avoidance, 2),
            'Total Savings($)': np.round(result.total_system_savings, 2),
            'System Cost ($)': np.round(result.hes_pv_cost, 2),
            'Baseline Savings ($)': 0,
            'Net Value ($)': 0,
            'Baseline Savings (kg CO2)': 0,
            'System Payback Period': 0,
            'System Cost Efficiency': 0,
            'System Total Peak Shaving Efficiency': np.round(result.peak_shaving_effectiveness, 2),
            'System High Peak Shaving Efficiency': np.round(result.high_peak_shaving_effectiveness, 2),
            'Is Baseline': bool(result.is_baseline)
            }
    to_add = pd.DataFrame(data=data, index=[i])
    to_add['Is Baseline'] = to_add['Is Baseline'].astype('boolean')
    summary_frame = pd.concat([summary_frame, to_add], ignore_index=True, axis=0)

    i += 1
    prev_row = row.copy()
    print('Scenario ' + str(i) + ' done in ' + str(round(t_tot, 3)) + ' seconds')

# Once we're done going through rows we write the summary file

base_frame = summary_frame[summary_frame['Is Baseline']]

for index, row in summary_frame.iterrows():
    if not row['Is Baseline']:
        red_frame = get_baseline(baseline_frame=base_frame, line=row)
        if len(red_frame) == 0:
            summary_frame.loc[index, 'Baseline Savings ($)'] = np.nan
            summary_frame.loc[index, 'Baseline Savings (kg CO2)'] = np.nan
            summary_frame.loc[index, 'Net Value ($)'] = np.nan
            summary_frame.loc[index, 'System Payback Period'] = np.nan
            summary_frame.loc[index, 'System Cost Efficiency'] = np.nan
        else:
            summary_frame.loc[index, 'Baseline Savings ($)'] = \
                np.round(red_frame['Total Bill ($)'].values[0] - row['Total Bill ($)'], 2)
            summary_frame.loc[index, 'Baseline Savings (kg CO2)'] = \
                np.round(red_frame['Total CO2 (kg)'].values[0] - row['Total CO2 (kg)'], 2)
            summary_frame.loc[index, 'Net Value ($)'] = \
                summary_frame.loc[index, 'Baseline Savings ($)'] - summary_frame.loc[index, 'EV Degradation ($)']
            summary_frame.loc[index, 'System Payback Period'] = \
                np.round(summary_frame.loc[index, 'System Cost ($)'] /
                         summary_frame.loc[index, 'Net Value ($)'], 2)
            if summary_frame.loc[index, 'System Cost ($)'] == 0:
                summary_frame.loc[index, 'System Cost Efficiency'] = 0
            else:
                summary_frame.loc[index, 'System Cost Efficiency'] = \
                    np.round(summary_frame.loc[index, 'Net Value ($)'] /
                             summary_frame.loc[index, 'System Cost ($)'], 4)

summary_frame.to_csv('Outputs/' + collection_name + '/' + collection_name + '_summary.csv')
