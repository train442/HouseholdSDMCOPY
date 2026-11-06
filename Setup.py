"""
This module was created to contain methods designed to facilitate the instantiation of the various components and
parameters classes required to run the model.

Methods
-------
haversine(coord1: tuple, coord2: tuple):
    This method find the distance (in km) between two geographic coordinates (in degrees). This method is used
    primarily to find the closest reference city to a certain zipcode.
closest_index(coord, coord_array: ndarray):
    This method returns the index of the closest coordinate within the coordinate array provided (coord_array). The
    purpose of this method is to isolate the closest city in the reference city list (see city_list.csv) to a desired
    coordinate (usually for a zip code). Each city in that list has a latitude on longitude listed which is then
    processed into a numpy array and passed as the coord_array parameter here.
create_city(zipcode=30303, name='Atlanta', st_abr='GA', from_zip=True):
    This method is used to facilitate the instantiation of the City object (see Parameters.py) using the model data
    and a zipcode. Using the zipcode provided, the method will cross-reference it with the master zipcode file
    (zip_directory.csv) in the "Model Data" folder in order to obtain the necessary location data and then
    create a City object. If zipcode is set to None and from_zip is False, the method will cross-reference the
    provided name and state in the master zipcode file and the reference city file (city_list.csv) to gather the
    information needed to instantiate a City object.
read_util(util_name, eia):
    The purpose of this method is, given the name of the utility and its eia code, to read that specific utility's
    csv file (contained in Utilities folder) and return a list of the names of the tariff schedules provided by the
    utility.
create_tariff(util_name=None, util_file=None, tariff_name=None, choose_tariff=False):
    This method is used to facilitate the instantiation of the Tariff object (see Parameters.py) given the desired
    utility and tariff schedule. Either the utility name or the name of its file can be fed into this method. Should
    the tariff schedule name not be provided and the choose_tariff parameter be given as true, then this method will
    prompt the user to select.
zip_read(zipcode: (int, str) = None):
    This method generates a Tariff, and City object given a zipcode, but requires user input to clarify what utility
    and tariff is desired. The method will prompt user for zipcode if not provided. This method is for use in a user
    interface version of this model.
create_driving_pattern(from_file=True, filename='default.csv', year=2018, start_day=1, days_to_compute=365,
                           min_resolution=30):
    This method generates an N x 3 driving pattern array for use by the EVS in the simulation, where N is the number
    of timesteps and the 3 columns are the step number, EV presence (1=present, 0=not present), and miles driven
    respectively. The method can either read the driving schedule from a file (from_file = TRUE) given the filename,
    or it can prompt the user to input events. These files can be found in the DrivingPatterns folder.
driving_pattern_from_calendar(timekeep: TimeKeep, filename='basic_commute.csv'):
    This method creates an N x 3 numpy array representing a driving pattern for use by the EVS in the simulation,
    where N is the number of timesteps and the 3 columns are the step number, EV presence (1=present,
    0=not present), and miles driven respectively. A Timekeep object (see Parameters.py) provides the necessary
    temporal limits and resolution for the driving pattern, whereas a driving schedule file (in DrivingPatterns
    folder) provides the EV behavior and miles driven.
create_ev(menu_selection=False, ev_id=1, year=2022, make='Ford', model='F-150 Lightning', trim='Pro 4WD SuperCrew',
              driving_pattern=create_driving_pattern(), discharge_limit: float = .7):
    This method generates an EV object from either user input or from EV data provided via the method parameters. It
    cross-references the inputs in the EVs.xlsx file in the "Model Data" folder and generates the EV object.
"""

from numpy import ndarray
import math
import os
from Components import EV
from Parameters import City, Tariff, TimeKeep
import TimeManage as tm
import numpy as np
import pandas as pd
from pandas import Series
import warnings
import openpyxl
from openpyxl.styles.borders import Border, Side

warnings.filterwarnings(action='ignore', category=UserWarning)
zip_file = 'Model Data/new_zip_directory.csv'
ev_file = 'Model Data/EVs.xlsx'
curve_path = 'Model Data/Battery Charge Curves/'
pv_file = 'Model Data/PVs.xlsx'
state_file = 'Model Data/states.csv'
city_file = 'Model Data/city_list_refined.csv'
util_eia_file = 'Model Data/util_to_zip_fixed.csv'


def haversine(coord1: tuple, coord2: tuple):
    """
    This method find the distance (in km) between two geographic coordinates (in degrees). This method is used
    primarily to find the closest reference city to a certain zipcode.
    Parameters
    ----------
    coord1: tuple
         A 2 element tuple with the elements being the latitude on longitude of the first location respectively.
    coord2
        A 2 element tuple with the elements being the latitude on longitude of the second location respectively.
    Returns
    -------
    float
        The distance in km between the two geographic locations.
    """
    # finds distance between two coordinates on earth
    radius = 6371  # radius of earth (km)
    lat1 = math.radians(coord1[0])
    long1 = math.radians(coord1[1])
    lat2 = math.radians(coord2[0])
    long2 = math.radians(coord2[1])

    a = math.sin((lat1 - lat2) / 2) ** 2
    b = math.cos(lat1) * math.cos(lat2) * (math.sin((long2 - long1) / 2) ** 2)

    dist = 2 * radius * math.asin(math.sqrt(a + b))

    return round(dist, 3)


def angle_distance_delta(coords: tuple[int, int] | tuple[float, float],
                         distance: int | float,
                         distance_units: str = 'miles'):
    """
    This function will give the change in latitude and longitude for a given distance away from a given coordinate.
    Parameters
    ----------
    coords
    distance
    distance_units

    Returns
    -------

    """
    if distance_units.lower() in ['miles', 'mile', 'mi']:
        r = 3958.8  # radius of earth
    elif distance_units.lower() in ['kilometers', 'kilometer', 'km']:
        r = 6378
    else:  # assume miles
        r = 3958.8

    lat = coords[0] * np.pi / 360

    del_lat = (distance / r) * (360 / np.pi)
    del_long = (distance / (r * np.cos(lat))) * (360 / np.pi)

    del_angle = (del_lat, del_long)
    return del_angle


def closest_index(coord, coord_array: ndarray):
    """
    This method returns the index of the closest coordinate within the coordinate array provided (coord_array). The
    purpose of this method is to isolate the closest city in the reference city list (see city_list.csv) to a desired
    coordinate (usually for a zip code). Each city in that list has a latitude on longitude listed which is then
    processed into a numpy array and passed as the coord_array parameter here.

    Parameters
    ----------
    coord : tuple
        A coordinate pair for which the distance for every coordinate of the coordinate list is calculated.
    coord_array : ndarray
        An N x 2 numpy array with the columns being the latitudes and longitudes of various locations. For this
        model, these locations are the cities listed in the city_list.csv file in Model Data.

    Returns
    -------
    index : int
        The index of the coordinate row in coord_array closest to the provided index.
    """
    # find index of coord within coord_array that is closest to given coord (lat,long)
    index = 0
    min_dist = np.inf  # absurdly high to start
    for i in range(coord_array.shape[0]):
        dist = haversine(coord, (coord_array[i, 0], coord_array[i, 1]))
        if dist < min_dist:
            min_dist = dist
            index = i
    return index


def create_city(zipcode=30303, name='Atlanta', st_abr='GA', from_zip=True) -> City:
    """
    This method is used to facilitate the instantiation of the City object (see Parameters.py) using the model data
    and a zipcode. Using the zipcode provided, the method will cross-reference it with the master zipcode file
    (zip_directory.csv) in the "Model Data" folder in order to obtain the necessary location data and then
    create a City object. If zipcode is set to None and from_zip is False, the method will cross-reference the
    provided name and state in the master zipcode file and the reference city file (city_list.csv) to gather the
    information needed to instantiate a City object.

    Parameters
    ----------
    zipcode : int, optional
        Zipcode for the desired location. Default is 30303 (Atlanta).
    name : str, optional
        Name of locality (city, town, etc.) in question. Default is Atlanta.
    st_abr : str, optional
        Abbreviated state name of desired location. Default is GA.
    from_zip : bool
        Whether to use provided zipcode to create City object.

    Returns
    -------
    city : City
        A City object for use in a simulation.
    """
    if zipcode is not None:
        zipcode = str(zipcode)

    state_master = pd.read_csv(state_file)
    city_master = pd.read_csv(city_file)
    zip_master = pd.read_csv(zip_file, dtype={'Zip Code': str})  # read in zipcode csv
    city_coords = city_master[['Latitude', 'Longitude']].to_numpy()
    if from_zip:  # given the zip code we can figure out everything we need from reading the zip file
        zip_inds = zip_master.index[zip_master['Zip Code'] == zipcode].values
        if zip_inds.size == 0:
            raise Exception('Zip code not in list, choose another.')
        zip_ind = zip_inds[0]  # find row index for given zip
        name = zip_master.loc[zip_ind, 'City']

        st_abr = zip_master.loc[zip_ind, 'State (Abbr)']
        lat = zip_master.loc[zip_ind, 'Latitude']
        long = zip_master.loc[zip_ind, 'Longitude']
        county = zip_master.loc[zip_ind, 'County']
        utilities = eval(zip_master.loc[zip_ind, 'Utilities'])
        eias = eval(zip_master.loc[zip_ind, 'EIA Codes'])
        ind_city = closest_index((lat, long), city_coords)
    else:  # we instead choose to manually input the city information
        sub_city = city_master[city_master['State'] == st_abr]
        sub_zip = zip_master[zip_master['State'] == st_abr]
        zip_cities = sub_zip['City'].unique()
        # check if city is already in matching city list
        if name in sub_city['City'].unique():
            ind_city = city_master[(city_master['State'] == st_abr) &
                                   (city_master['City'] == name)].index.values[0]
            lat = city_master.loc[ind_city, 'Latitude']
            long = city_master.loc[ind_city, 'Longitude']
            if name in zip_cities:
                sub_zip = sub_zip[sub_zip['City'] == name].reset_index(drop=True)
                zipcode = sub_zip.loc[0, 'Zip Code']
                county = sub_zip.loc[0, 'County']
                utilities = eval(sub_zip.loc[0, 'Utilities'])
                eias = eval(sub_zip.loc[0, 'EIA Codes'])
            else:  # locality name doesn't exist in list of zips so we default to closest zipcode by lat, long
                sub_zip = sub_zip.reset_index(drop=True)
                zip_ind = closest_index((lat, long), sub_zip[['Latitude', 'Longitude']].to_numpy())
                zipcode = sub_zip.loc[zip_ind, 'Zip Code']
                county = sub_zip.loc[zip_ind, 'County']
                utilities = eval(sub_zip.loc[zip_ind, 'Utilities'])
                eias = eval(sub_zip.loc[zip_ind, 'EIA Codes'])
        else:  # desired city is not already in the matching city list, so we search in the zip file
            if name in zip_cities:  # given name is in filtered list of city names in zip file
                sub_zip = sub_zip[sub_zip['City'] == name].reset_index(drop=True)
                lat = sub_zip.loc[0, 'Latitude']
                long = sub_zip.loc[0, 'Longitude']
                zipcode = sub_zip.loc[0, 'Zip Code']
                county = sub_zip.loc[0, 'County']
                utilities = eval(sub_zip.loc[0, 'Utilities'])
                eias = eval(sub_zip.loc[0, 'EIA Codes'])
                ind_city = closest_index((lat, long), city_coords)
            else:  # cannot find city name verbatim in filtered zip list
                raise Exception('City provided not found, try searching by zip code')

    matched_city = city_master.loc[ind_city, 'City']
    matched_state = city_master.loc[ind_city, 'State']
    time_zone = city_master.loc[ind_city, 'Time Zone']
    if 'WattTime Region' in city_master.columns:
        matched_wattime_region = city_master.loc[ind_city, 'WattTime Region']
        if pd.isnull(matched_wattime_region):
            matched_wattime_region = None
    else:
        matched_wattime_region = None

    #  Now we get state specific data
    ind_state = state_master[state_master['Abbreviation'] == st_abr].index.values[0]
    state_full = state_master.loc[ind_state, 'State']
    carbon_intensity = state_master.loc[ind_state, 'Grid Carbon Intensity(kg/kwh)']
    sst = float(state_master.loc[ind_state, 'State Sales Tax'].strip('%')) / 100
    alst = float(state_master.loc[ind_state, 'Avg Local Sales Tax'].strip('%')) / 100
    # tax_rate = state_master.loc[ind_state, 'State Sales Tax'] + state_master.loc[ind_state, 'Avg Local Sales Tax']
    tax_rate = sst + alst
    follows_dst = state_master.loc[ind_state, 'DST']
    solar_unit_cost = state_master.loc[ind_state, 'Solar Cost $/W']

    if pd.isnull(solar_unit_cost):
        solar_unit_cost = 2.86

    city = City(name, st_abr, state_full, county, zipcode, lat, long, time_zone, carbon_intensity, tax_rate, utilities,
                eias, follows_dst, matched_city, matched_state, solar_unit_cost,
                matched_wattime_region=matched_wattime_region)
    return city


def get_eia(util_name: str):
    """
    This method returns the EIA code for a given utility. Utility must match value in 'util_to_zip_fixed.csv'.
    Parameters
    ----------
    util_name : str
        Name of utility for which EIA code is desired

    Returns
    -------
    eia: str
        The EIA code for the utility.
    """
    util_list = pd.read_csv(util_eia_file, dtype={'EIA Code': str})
    ind = util_list.index[util_list['Utility Name'] == util_name][0]
    eia = util_list.loc[ind, 'EIA Code']
    return eia


def read_util(util_name, eia) -> list:
    """
    The purpose of this method is, given the name of the utility and its eia code, to read that specific utility's
    csv file (contained in Utilities folder) and return a list of the names of the tariff schedules provided by the
    utility.


    Parameters
    ----------
    util_name : str
        The name of the utility.
    eia : int
        The EIA code of the utility

    Returns
    -------
    list
        A list of the names of the tariff schedules provided by the utility.
    """
    # simple function reads the tariff names of a given utility and eia and returns a list
    file_to_read = 'Utilities/' + util_name + '_' + str(eia) + '_tariffs.csv'
    frame = pd.read_csv(file_to_read, usecols=['Name'])
    return frame['Name'].tolist()


def utils_from_zip(zip_code: str):
    """
    This method returns the possible utilities as long as the eia codes for a given zip_code.
    Parameters
    ----------
    zip_code

    Returns
    -------

    """
    if type(zip_code) is int:
        zip_code = str(zip_code).zfill(5)
    zip_frame = pd.read_csv(zip_file, dtype={'Zip Code': str})
    zip_ind = zip_frame.index[zip_frame['Zip Code'] == zip_code].values[0]
    utils = eval(zip_frame.loc[zip_ind, 'Utilities'])
    eias = eval(zip_frame.loc[zip_ind, 'EIA Codes'])
    return utils, eias


def get_best_tariff(util: str, eia: int = None) -> Series | None:
    """
    This method, given a utility name and its eia code, will return a pandas series derived from the utility's csv
    file for the
    Parameters
    ----------
    util: str
        The name of the utility (see util_to_zip_fixed.csv for proper names)
    eia: int
        The EIA code for the utility.

    Returns
    -------
    best: Series

    """
    if eia is None:
        eia = get_eia(util)
    file_to_read = 'Utilities/' + util + '_' + str(eia) + '_tariffs.csv'
    util_frame = pd.read_csv(file_to_read)
    util_frame = util_frame[pd.isna(util_frame['End Date'])]  # remove expired tariffs
    if len(util_frame) == 0:
        return None
    util_frame = util_frame[util_frame['TimeOfUse']]  # extract TimeOfUse rates
    if len(util_frame) == 0:
        return None
    best = util_frame.loc[util_frame['Max Difference'].idxmax()]
    return best


def get_best_utility(utils: list[str], eias: list[int]) -> dict:
    """
    Returns a dictionary containing utility and tariff information of the best TOU utility/tariff combo given a list
    of utilities. The best TOU tariff is that which has the highest price difference between peak and off-peak (Max
    Difference.)

    Parameters
    ----------
    utils: list[str]
        A list of utility names.
    eias: list [int]
        A list of EIA codes for the utilities

    Returns
    -------
    best_util_dict: dict
        A dictionary containing utility and tariff information of the best TOU utility/tariff combo.
    """
    i = 0
    max_diff = 0
    best_util = None
    best_eia = None
    best_tariff = None
    is_tou = False
    for util in utils:
        eia = eias[i]
        tariff_series = get_best_tariff(util=util, eia=eia)
        if tariff_series is not None:
            is_tou = True
            if tariff_series['Max Difference'] > max_diff:
                max_diff = tariff_series['Max Difference']
                best_tariff = tariff_series.copy()
                best_util = util
                best_eia = eia
        i += 1

    if best_tariff is None:
        best_tariff_name = None
        net_met_policy = None
        best_file = None
    else:
        best_tariff_name = best_tariff['Name']
        net_met_policy = best_tariff['Net Meter Policy']
        best_file = best_util + '_' + str(best_eia) + '_tariffs.csv'

    best_util_dict = {'Utility': best_util,
                      'EIA': best_eia,
                      'Tariff': best_tariff_name,
                      'File': best_file,
                      'Net Metering Policy': net_met_policy,
                      'Max Difference': max_diff,
                      'TOU': is_tou}
    return best_util_dict


def get_best_util_for_zip(zip_code: str):
    """
    This method returns the utility dictionary (See get_best_utility method) for a given zipcode.
    Parameters
    ----------
    zip_code : str
        Zipcode of desired location (as string)
    Returns
    -------
    util_dict
        The utility dictionary of the best utility/tariff combination for the zipcode.
    """
    if type(zip_code) is int:
        zip_code = str(zip_code).zfill(5)
    utils, eias = utils_from_zip(zip_code=zip_code)
    util_dict = get_best_utility(utils=utils, eias=eias)
    return util_dict


def create_tariff(util_name=None, util_file=None, tariff_name=None, choose_tariff=False) -> Tariff:
    """
    This method is used to facilitate the instantiation of the Tariff object (see Parameters.py) given the desired
    utility and tariff schedule. Either the utility name or the name of its file can be fed into this method. Should
    the tariff schedule name not be provided and the choose_tariff parameter be given as true, then this method will
    prompt the user to select.


    Parameters
    ----------
    util_name : str, optional
        The name of the utility. Default is None.
    util_file : str, optional
        The filename of the desired utility (contained in Utilities folder). Default is None.
    tariff_name : str, optional
        The name of the desired tariff schedule provided by the utility. Default is None.
    choose_tariff : bool, optional
        Whether to let user select tariff schedule or not. Default is False.

    Returns
    -------
    utility :
    """
    # if util_name is None, the file itself must be provided, or else there will be an error
    # util_list = pd.read_csv(util_eia_file, dtype={'EIA Code': str})
    # if util_name is not None:
    #     # read util_to_zip file to get eia code
    #     ind = util_list.index[util_list['Utility Name'] == util_name][0]
    #     eia = util_list.loc[ind, 'EIA Code']
    #     util_file = util_name + '_' + eia + '_tariffs.csv'
    # else:  # util_name wasn't given, must be inferred from util_file given
    #     util_name = util_file.split('_')[0]

    util_list = pd.read_csv(util_eia_file, dtype={'EIA Code': str})

    if util_name is None:
        util_split = util_file.split('_')
        util_name = util_split[0]

    ind = util_list.index[util_list['Utility Name'] == util_name][0]
    eia = util_list.loc[ind, 'EIA Code']
    avoided_cost = util_list.loc[ind, 'Avoided Cost Rate']
    net_met_adder = util_list.loc[ind, 'Net Meter Adder']  # additional compensation over wholesale rate (Avoided cost)
    net_meter_policy = util_list.loc[ind, 'Net Meter Policy']
    re_up_freq = util_list.loc[ind, 'Re-up Freq']
    non_bypassable_charges = util_list.loc[ind, 'NBC']
    if pd.isna(avoided_cost):
        avoided_cost = .03
    if pd.isna(net_met_adder):
        net_met_adder = 0
    sellback = avoided_cost + net_met_adder
    if pd.isna(non_bypassable_charges):
        non_bypassable_charges = 0
    if pd.isna(net_meter_policy):
        net_meter_policy = 'wholesale'
    if pd.isna(re_up_freq):
        re_up_freq = 'monthly'

    if util_file is None:
        util_file = f'{util_name}_{eia}_tariffs.csv'

    util_file = 'Utilities/' + util_file
    if not os.path.exists(util_file):
        raise Exception('File not found')
    else:
        util_sheet = pd.read_csv(util_file)

    # if tariff name provided, we go ahead and read information. Else, we choose from the tariffs in the utility's file
    if tariff_name is not None:
        try:
            ind = util_sheet.index[(util_sheet['Name'] == tariff_name) & (pd.isna(util_sheet['End Date']))][0]
        except IndexError:
            Exception('No tariff by this name for this utility')
            ind = 0
    elif choose_tariff:  # we provide choice of tariffs to user
        print('The following are the possible tariff schedules available for your chosen utility:')

        i = 1
        for tariff_name in util_sheet.Name:
            print('Option ' + str(i) + ': ' + tariff_name)
            i += 1

        ind = int(input('Please choose your tariff: ')) - 1
    else:  # if we cant choose which tariff, we simply pick the first TOU tariff
        sub_frame = util_sheet[~util_sheet['Demand']]
        ind = sub_frame.index[sub_frame['TimeOfUse']][0]

    name = util_sheet.loc[ind, 'Name']
    monthly_charge = util_sheet.loc[ind, 'Monthly Charge']
    minimum_charge = util_sheet.loc[ind, 'Minimum Charge']

    periods_energy = eval(util_sheet.loc[ind, 'Time-of-Use Rates'])

    weekday_schedule = np.array(eval(util_sheet.loc[ind, 'Weekday Schedule - Energy']))
    weekend_schedule = np.array(eval(util_sheet.loc[ind, 'Weekend Schedule - Energy']))
    try:
        periods_demand = eval(util_sheet.loc[ind, 'Demand Rates'])
        weekday_schedule_power = np.array(eval(util_sheet.loc[ind, 'Weekday Schedule - Power'])).astype(int)
        weekend_schedule_power = np.array(eval(util_sheet.loc[ind, 'Weekend Schedule - Power'])).astype(int)
    except (ValueError, SyntaxError, TypeError):
        periods_demand = []
        weekday_schedule_power = np.zeros((12, 24))
        weekend_schedule_power = np.zeros((12, 24))
    is_tou = util_sheet.loc[ind, 'TimeOfUse']
    is_tiered = util_sheet.loc[ind, 'Tiered']
    is_demand = util_sheet.loc[ind, 'Demand']

    utility = Tariff(name=name,
                     utility=util_name,
                     eia=eia,
                     monthly_charge=monthly_charge,
                     minimum_charge=minimum_charge,
                     sellback=sellback,
                     periods_energy=periods_energy,
                     weekday_schedule=weekday_schedule,
                     weekend_schedule=weekend_schedule,
                     periods_demand=periods_demand,
                     weekday_schedule_power=weekday_schedule_power,
                     weekend_schedule_power=weekend_schedule_power,
                     is_tou=is_tou,
                     is_tiered=is_tiered,
                     is_demand=is_demand,
                     net_met_policy=net_meter_policy,
                     re_up_freq=re_up_freq,
                     nbc=non_bypassable_charges)

    return utility


def create_best_tariff(zip_code: str):
    zip_code = str(zip_code)
    util_dict = get_best_util_for_zip(zip_code=zip_code)
    if util_dict['Utility'] is None:
        best_tariff = None
    else:
        best_tariff = create_tariff(util_file=util_dict['File'], tariff_name=util_dict['Tariff'])
    return best_tariff


def zip_read(zipcode: (int, str) = None):
    """
    This method generates a Tariff, and City object given a zipcode, but requires user input to clarify what utility
    and tariff is desired. The method will prompt user for zipcode if not provided. This method is for use in a user
    interface version of this model.

    Parameters
    ----------
    zipcode: int, str, optional
        Zipcode for which the City and Tariff objects are to be created. Default is None. If None, this method will
        prompt user to provide value.
    Returns
    -------
    utility : Tariff
        A Tariff object containing the utility and tariff schedule for use in simulation.
    city : City
        A City object or use in simulation.
    """
    if zipcode is None:
        zipcode = input("Please enter zip code: ")

    if isinstance(zipcode, str):
        try:
            zipcode = int(zipcode)
        except ValueError:
            print('Invalid Zip Code')
            return

    city = create_city(zipcode)
    num_util = len(list(city.utilities))

    if num_util > 1:
        print('The following are the available utilities in your area')
        i = 0  # index for eia code
        for util in city.utilities:
            print('Option ' + str(i + 1) + ': ' + util + '\n')
            i += 1

        choice = int(input('Please choose your utility: '))
        util = city.utilities[choice - 1]
        eia = city.eias[choice - 1]
    else:
        util = city.utilities[0]
        eia = city.eias[0]
        print('Your utility is: ' + city.utilities[0])
        input('Press <Enter> to continue')

    util_file = 'Utilities/' + util + '_' + str(eia) + '_tariffs.csv'

    utility = create_tariff(util_file=util_file)

    return utility, city


def create_driving_pattern(from_file=True, filename='default.csv', year=2018, start_day=1, days_to_compute=365,
                           min_resolution=30):
    """
    This method generates an N x 3 driving pattern array for use by the EVS in the simulation, where N is the number
    of timesteps and the 3 columns are the step number, EV presence (1=present, 0=not present), and miles driven
    respectively. The method can either read the driving schedule from a file (from_file = TRUE) given the filename,
    or it can prompt the user to input events. These files can be found in the DrivingPatterns folder.

    Parameters
    ----------
    from_file : bool, optional
        Whether to pull the driving schedule from a file provided and use that to create the pattern array.
    filename : str, optional
        The file from which to pull the driving schedule
    year : int, optional
        The calendar year for which pattern is to be made. Default is 2018.
    start_day : int, optional
        The starting day of the year (out of 365) for the simulation. Default is 1
    days_to_compute : int
        The number of days in the simulation. Default is 365.
    min_resolution : int
        The duration of each timestep in minutes. Default is 5.
    Returns
    -------
    driving_pattern : ndarray
        an N x 3 numpy array for use by the EVS in the simulation, where N is the number of timesteps and the 3
        columns are the step number, EV presence (1=present, 0=not present), and miles driven respectively.
    """
    day_dict = {'1': 'Monday', '2': 'Tuesday', '3': 'Wednesday', '4': 'Thursday', '5': 'Friday', '6': 'Saturday',
                '7': 'Sunday', '8': 'Holiday'}
    day_cols = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday', 'Holiday']
    miles_col = ['Monday Miles', 'Tuesday Miles', 'Wednesday Miles', 'Thursday Miles', 'Friday Miles', 'Saturday Miles',
                 'Sunday Miles', 'Holiday Miles']

    if from_file:
        # pattern_frame = pd.read_csv('DrivingPatterns/' + filename, parse_dates=['Time'], index_col='Time')
        pattern_frame = pd.read_csv('DrivingPatterns/' + filename, parse_dates=['Time'])
    else:
        # pattern_frame = pd.read_csv('DrivingPatterns/empty_pattern.csv', parse_dates=['Time'], index_col='Time')
        pattern_frame = pd.read_csv('DrivingPatterns/empty_pattern.csv', parse_dates=['Time'])
        backup = pattern_frame  # back-up of original frame
        display_frame = pattern_frame.replace(1, 'Home')
        event_list = []  # list of events created in the frame
        add_more = True
        while add_more:
            print(display_frame)
            print('\n \n Do you wish to add an event?\n')
            print('1: Yes \n', '2: No \n', '3: Remove Event\n', '4: Reset Schedule')
            choice = input('Please choose a response: ')
            if choice in ['Yes', 'YES', '1']:
                event_name = input('What is this event called? : ')
                start_time = pd.to_datetime(input('What time does this event start? (hr:min am/pm) : '))
                end_time = pd.to_datetime(input('What time does this event end? (hr:min am/pm): '))
                days_of_week = input('What days of the week does this event occur? (ex: 1 = Monday, 135 = MWF, '
                                     '8 = Holidays) : ')
                day_list = []
                for d in days_of_week:
                    if day_dict[d] not in day_list:
                        day_list.append(day_dict[d])

                miles = input('How many miles driven to and from this event? : ')

                print('To summarize:\n', 'Event Name:' + event_name + '\n', 'From: ' + str(start_time.time()) + '\n',
                      'To: ' + str(end_time.time()) + '\n', 'Days of Week: ' + str(day_list) + '\n',
                      'Miles Driven: ' + miles)
                print('\n Do you wish to add this event?')
                print('1:  Yes \n', '2: No \n')
                choice = input('Please choose a response: \n')
                if choice in ['Yes', 'YES', '1']:
                    si = display_frame.index[display_frame['Time'] == start_time][0]
                    ei = display_frame.index[display_frame['Time'] == end_time][0] - 1
                    # display_frame.loc[start_time:end_time - timedelta(minutes=30), day_list] = event_name
                    # pattern_frame.loc[start_time:end_time - timedelta(minutes=30), day_list] = 0
                    display_frame.loc[si:ei, day_list] = event_name
                    pattern_frame.loc[si:ei, day_list] = 0
                    event_list.append(event_name)
                    for day in day_list:
                        pattern_frame.loc[si, day + ' Miles'] = miles
                        display_frame.loc[si, day + ' Miles'] = miles

            elif choice in ['3', 'Remove', 'REMOVE', 'Remove Event']:
                if len(event_list) == 0:
                    print('There are no events in the schedule, please add events./n')
                else:
                    print('Which event would you like to remove?: ')
                    i = 1
                    num_list = []
                    for event in event_list:
                        print(str(i) + ': ' + event)
                        num_list.append(str(i))
                        i += 1

                    print(str(i) + ': Cancel')

                    choice = input('Please make a choice: ')

                    if choice in num_list or choice in event_list:
                        removed_event = event_list[int(choice) - 1]
                        event_list.remove(removed_event)
                        for d in day_cols:
                            indices = display_frame.index[display_frame[d] == removed_event]
                            display_frame.loc[indices, d] = 'Home'
                            display_frame.loc[indices, d + ' Miles'] = 0
                            pattern_frame.loc[indices, d] = 1
                            pattern_frame.loc[indices, d + ' Miles'] = 0

            elif choice in ['4', 'Reset', 'reset', 'RESET', 'Reset Schedule']:
                pattern_frame = backup

            else:
                add_more = False
                print('\n Do you wish to save current schedule? \n')
                print('1:  Yes \n', '2: No \n')
                choice = input('Please choose a response: ')
                if choice in ['Yes', 'YES', '1']:
                    file_name = input('What would you like to call the new schedule? : ')
                    pattern_frame.to_csv('DrivingPatterns/' + file_name + '.csv')

    step_frame = pd.DataFrame(columns=pattern_frame.columns)
    for index, row in pattern_frame.iterrows():
        new_row = row.copy()
        base_min = row['Time'].minute
        for step in range(0, int(min_resolution / 5)):
            new_row['Time'] = new_row['Time'].replace(minute=(base_min + step * 5) % 60)
            if step != 0:
                new_row[miles_col] = 0

            step_frame.loc[len(step_frame), :] = new_row

    end_day = min(365, start_day + days_to_compute - 1)
    driving_pattern = np.empty((0, 3))
    dow = tm.get_start_day_of_week(year=year, simu_start_day=start_day)[0]  # day of week in number form

    for d in range(start_day, end_day + 1):
        day_of_week = day_dict[str(dow)]  # day of week in string form
        s = (d - 1) * 12 * 24
        e = d * 12 * 24 - 1
        steps = np.array(range(s, e + 1)).reshape((-1, 1))
        from_frame = step_frame.loc[:, [day_of_week, day_of_week + ' Miles']].to_numpy()
        to_add = np.hstack((steps, from_frame))
        driving_pattern = np.vstack((driving_pattern, to_add))
        dow += 1
        if dow == 8:
            dow = 1

    return driving_pattern


def create_driving_pattern_from_dates(filename='basic_commute.csv', start_date=pd.to_datetime('1/1/2018'),
                                      end_date=pd.to_datetime('12/31/2018')):
    """
    A stub method yet to be completed. The intent is to generate a driving pattern from a file (in DrivingPatterns
    folder) using two pandas Timestamps as the starting and ending points.
    Parameters
    ----------
    filename
    start_date
    end_date

    Returns
    -------

    """
    return filename, start_date, end_date


def driving_pattern_from_calendar(timekeep: TimeKeep, filename='basic_commute.csv') -> ndarray:
    """
    This method creates an N x 3 numpy array representing a driving pattern for use by the EVS in the simulation,
    where N is the number of timesteps and the 3 columns are the step number, EV presence (1=present,
    0=not present), and miles driven respectively. A Timekeep object (see Parameters.py) provides the necessary
    temporal limits and resolution for the driving pattern, whereas a driving schedule file (in DrivingPatterns
    folder) provides the EV behavior and miles driven.

    Parameters
    ----------
    timekeep : Timekeep
        A Timekeep object containing the temporal limits (start and finish dates) and the minute resolution for the
        driving pattern array.
    filename : str, optional
        A driving schedule file describing when the EV arrives or departs, and how many miles it drives.
    Returns
    -------
    driving_pattern : ndarray
        an N x 3 numpy array for use by the EVS in the simulation, where N is the number of timesteps and the 3
        columns are the step number, EV presence (1=present, 0=not present), and miles driven respectively.
    """
    day_dict = {'0': 'Monday', '1': 'Tuesday', '2': 'Wednesday', '3': 'Thursday', '4': 'Friday', '5': 'Saturday',
                '6': 'Sunday', '7': 'Holiday'}
    miles_col = ['Monday Miles', 'Tuesday Miles', 'Wednesday Miles', 'Thursday Miles', 'Friday Miles', 'Saturday Miles',
                 'Sunday Miles', 'Holiday Miles']

    pattern_frame = pd.read_csv('DrivingPatterns/' + filename, parse_dates=['Time'])
    frame_del = (pattern_frame.iloc[1, 0] - pattern_frame.iloc[0, 0])
    frame_res = frame_del.components.minutes + frame_del.components.hours * 60
    step_frame = pd.DataFrame(columns=pattern_frame.columns)
    driving_pattern = np.zeros((timekeep.num_steps, 3)).astype(int)
    for index, row in pattern_frame.iterrows():
        new_row = row.copy()
        for step in range(int(frame_res / timekeep.timestep)):
            if step != 0:
                new_row['Time'] = new_row['Time'] + pd.Timedelta(str(timekeep.timestep) + ' min')
                new_row[miles_col] = 0
            step_frame.loc[len(step_frame), :] = new_row

    for d in range(timekeep.simu_days):
        dow = (timekeep.start_date + pd.Timedelta(str(d) + ' days')).day_of_week
        dow = day_dict[str(dow)]
        s = d * 24 * int(60 / timekeep.timestep)
        e = (d + 1) * 24 * int(60 / timekeep.timestep)
        steps = np.array(range(s, e)).reshape((-1, 1))
        driving_pattern[s:e, :] = np.hstack((steps, step_frame.loc[:, [dow, dow + ' Miles']].to_numpy()))

    return driving_pattern


def create_ev(menu_selection=False, ev_id=1, year=2022, make='Ford', model='F-150 Lightning', trim='Pro 4WD SuperCrew',
              driving_pattern=create_driving_pattern(), discharge_limit: float = .7):
    """
    This method generates an EV object from either user input or from EV data provided via the method parameters. It
    cross-references the inputs in the EVs.xlsx file in the "Model Data" folder and generates the EV object.
    Parameters
    ----------
    menu_selection: bool
        Whether to prompt user to manually input EV data.
    ev_id : int, optional
        The EV serial iD within the Fleet object. Default is 1.
    year : int, optional
        The model year of the EV. Default is 2022.
    make : str, optional
        The make (brand) of the EV (ie, Ford). Default is 'Ford'.
    model : str
        The model of the EV (ie, Mach-E). Default is 'F-150 Lightning'.
    trim : str
        The trim level of the EV (ie, Mach-E GT). Default is 'Pro 4WD SuperCrew'.
    driving_pattern : ndarray
        an N x 3 numpy array for use by the EVS in the simulation, where N is the number of timesteps and the 3
        columns are the step number, EV presence (1=present, 0=not present), and miles driven respectively. Default
        is the default output of the create_driving_pattern method.
    discharge_limit : float
        The state of charge of the EV battery below which V2H discharge is disallowed. Default is 70%.
    Returns
    -------
    ev : EV
        An EV object to be used in the simulation.
    """
    # Creates EV object from provided arguments or from live menu selection
    ev_frame = pd.read_excel(ev_file)
    if menu_selection:
        years_available = ev_frame['Year'].unique()
        print('Years Available: \n')
        for yr in years_available:
            print(yr, '\n')
        year = int(input('What model year is your electric vehicle? '))
        sub_frame = ev_frame[ev_frame['Year'] == year]
        makes_available = sub_frame['Make'].unique()
        print('Makes Available: \n')
        for mk in makes_available:
            print(mk)
        make = input('What make is your electric vehicle? ')
        sub_frame = sub_frame[sub_frame['Make'] == make]
        models_available = sub_frame['Model'].unique()
        print('Models Available: \n')
        for md in models_available:
            print(md)
        model = input('What model is your electric vehicle? ')
        sub_frame = sub_frame[sub_frame['Model'] == model]
        trims_available = sub_frame['Trim'].unique()
        if len(trims_available) == 1:
            trim = trims_available[1]
        else:
            print('Trims Available: \n')
            for tr in trims_available:
                print(tr)
            trim = input('What trim is your electric vehicle? ')
            sub_frame = sub_frame[sub_frame['Trim'] == trim]
            print(sub_frame)

    else:  # We do not want to do menu selection. We already know our EV model from the arguments
        sub_frame = ev_frame.loc[
            (ev_frame['Year'] == year) & (ev_frame['Make'] == make) & (ev_frame['Model'] == model) & (
                    ev_frame['Trim'] == trim)]

    msrp = sub_frame['MSRP'].values[0]
    mpge_hwy = sub_frame['MPGe Hwy'].values[0]
    mpge_city = sub_frame['MPGe City'].values[0]
    mpge_comb = sub_frame['MPGe Comb'].values[0]
    battery_size = sub_frame['Battery Size (kWh)'].values[0]
    lvl2_max_rate = sub_frame['Lvl2 Charge Rate (kW)'].values[0]
    curve_file = make + '_' + model + '_' + trim + '_' + str(year) + '_curve.csv'  # curve is unique to trim
    if not os.path.exists(curve_path + curve_file):
        curve_file = make + '_' + model + '_' + str(year) + '_curve.csv'  # curve is same for all trim

    use_curve = os.path.exists(curve_path + curve_file)

    return EV(battery_size=battery_size, lvl2_max_rate=lvl2_max_rate, use_curve=use_curve, ev_id=ev_id, year=year,
              make=make, model=model, trim=trim, msrp=msrp, mpge_hwy=mpge_hwy, mpge_city=mpge_city,
              mpge_comb=mpge_comb, driving_pattern=driving_pattern, discharge_limit=discharge_limit)


def create_pv(menu_selection=False, brand='Custom', model='Custom'):
    """
    This method is currently a stub. Functionality TBD.
    Parameters
    ----------
    menu_selection
    brand
    model

    Returns
    -------

    """
    return menu_selection, brand, model


def create_load_profile():
    """
    This method is currently a stub. Functionality TBD.
    Returns
    -------

    """
    return 1


# noinspection PyTypeChecker
def generate_input_file(title: str,
                        years: list[int] = None,
                        zip_codes: list[str] = None,
                        utilities: list[str] = None,
                        util_files: list[str] = None,
                        tariffs: list[str] = None,
                        net_met_policies: list[str] = None,
                        house_loads: list = None,
                        pv_sizes: list[int] = None,
                        hes_sizes: list[int] = None,
                        hes_opt_styles: list = None,
                        v2h_limits: list[float] = None,
                        commutes: list = None,
                        charge_schemes: list[str] = None,
                        condensed_util_frame: pd.DataFrame = None) -> None:
    # Check inputs are implement defaults

    if years is None:
        years = [2018]
    if zip_codes is None:
        zip_codes = ['30332']
    if net_met_policies is None:
        net_met_policies = ['wholesale', 'one-to-one']
    if house_loads is None:
        house_loads = [6000, 11000, 15000]
    if pv_sizes is None:
        pv_sizes = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
    if hes_sizes is None:
        hes_sizes = [0, 3, 5, 7, 10, 15, 20, 30, 40]
    if hes_opt_styles is None:
        hes_opt_styles = ['simple', 'flat']
    if v2h_limits is None:
        v2h_limits = [1, .7, .5]
    if commutes is None:
        commutes = ['basic_commute']
    if charge_schemes is None:
        charge_schemes = ['Front End']

    if hes_sizes == [0]:  # if theres no HES, we just set method to flat
        hes_opt_styles = ['flat']

    if pv_sizes == [0]:  #there's no pv, so we just set netmet to default
        net_met_policies = ['default']

    if condensed_util_frame is None:
        util_frame = pd.read_csv(util_eia_file)
    else:
        util_frame = condensed_util_frame

    # open empty input Excel file
    empty_path = 'InputFiles/Empty.xlsx'
    new_path = 'InputFiles/' + title + '.xlsx'
    wb = openpyxl.load_workbook(filename=empty_path)
    sheet = wb.active
    headers = 3

    # check util inputs
    if (util_files is None) and (tariffs is None) and (utilities is None):  # nothing was given, so we go with best
        util_dicts = [get_best_util_for_zip(zip_code) for zip_code in zip_codes]
        utilities = [util_dict['Utility'] for util_dict in util_dicts]
        tariffs = [util_dict['Tariff'] for util_dict in util_dicts]
        util_files = [util_dict['File'] for util_dict in util_dicts]
    elif util_files is not None:
        utilities = [util_file.split('_')[0] for util_file in util_files]
        eias = [util_file.split('_')[1] for util_file in util_files]
        if tariffs is None:
            tariffs = [get_best_tariff(util=util)['Name'] for util in utilities]
    elif utilities is not None:
        util_files = [util + '_' + get_eia(util_name=util) + '_tariffs.csv' for util in utilities]
        if tariffs is None:
            tariffs = [get_best_tariff(util=util)['Name'] for util in utilities]

    #  Find scenario Input combinations
    scen_inputs = []
    for year in years:
        new_row = [None, None, year, 365, 1, 5]
        scen_inputs.append(new_row)

    # Find City Input Combinations
    city_inputs = []
    for zip_code in zip_codes:
        new_row = [zip_code, None, None]
        city_inputs.append(new_row)

    # Check commutes for "best" entries

    # Find utility combinations
    util_inputs = []
    for util_file, utility_name in zip(util_files, utilities):
        for tariff in tariffs:
            net_ind = util_frame[util_frame['Utility Name'] == utility_name].index[0]
            default_net_met = util_frame.loc[net_ind, 'Net Meter Policy']
            if pd.isna(default_net_met):
                default_net_met = 'wholesale'
            if 'default' in net_met_policies:

                red_net_met = [pol for pol in net_met_policies if pol != 'default']
                if default_net_met not in net_met_policies:
                    red_net_met.append(default_net_met)
            else:
                red_net_met = net_met_policies
            for net_meter_policy in red_net_met:
                new_row = [utility_name, util_file, tariff, net_meter_policy]
                util_inputs.append(new_row)

    # Find house load combinations
    house_inputs = []
    for house_load in house_loads:
        new_row = [house_load, None, None]
        house_inputs.append(new_row)

    grid_inputs = [[True, None]]

    solar_inputs = []
    for pv in pv_sizes:
        new_row = [pv, None, None, None]
        solar_inputs.append(new_row)

    hes_inputs = []
    for size in hes_sizes:
        for opt in hes_opt_styles:
            new_row = [size, .2, 1, opt]
            hes_inputs.append(new_row)

    ev_inputs = []
    for commute in commutes:
        for charge_scheme in charge_schemes:
            for v2h_level in v2h_limits:
                new_row = [None, v2h_level, .2, 1, 2023,
                           'Ford', 'F-150 Lightning', 'Pro 4WD SuperCrew',
                           commute, 1, charge_scheme]
                ev_inputs.append(new_row)

    data = []
    i = 1
    for scen_input in scen_inputs:
        for city_input in city_inputs:
            for util_input in util_inputs:
                for house_input in house_inputs:
                    for grid_input in grid_inputs:
                        for ev_input in ev_inputs:
                            for hes_input in hes_inputs:
                                for solar_input in solar_inputs:
                                    new_row = [i] + scen_input + city_input + util_input + house_input + grid_input + \
                                              solar_input + hes_input + ev_input
                                    data.append(new_row)
                                    i += 1

    i = 1
    for row in data:
        j = 1
        for value in row:
            sheet.cell(row=i + headers, column=j).value = value
            j += 1
        i += 1

    border_cols = [7, 10, 14, 17, 19, 23, 27]

    # Place borders
    thin_border = Border(right=Side(style='thin'))
    for r in range(1, len(data) + 3):
        for col in border_cols:
            sheet.cell(row=r + 1, column=col).border = thin_border

    # change title cell
    sheet.cell(row=1, column=2).value = title

    wb.save(new_path)

    pass


def check_commutes(commute_list: list[str], best_commute: str):
    if best_commute in ['basic_commute']:
        best_time = '9to5'
    else:
        best_time = best_commute.split('_')[1]
    ref_coms = []
    for commute in commute_list:
        if '_' in commute:
            com_spl = commute.split('_')
            if com_spl[1].lower() in ['best']:
                commute = f'{com_spl[0]}_{best_time}'
        if commute not in ref_coms:
            ref_coms.append(commute)

    return ref_coms


def generate_input_collection(collection_title: str,
                              pool_file: str = 'refined_pools.csv',
                              years: list[int] = None,
                              net_met_policies: list[str] = None,
                              house_loads: list = None,
                              pv_sizes: list[int] = None,
                              hes_sizes: list[int] = None,
                              hes_opt_styles: list = None,
                              v2h_limits: list[float] = None,
                              commutes: list[str] | str = None,
                              charge_schemes: list[str] = None,
                              sort_by_pop=True,
                              number: int = None) -> None:
    collection_path = f'InputFiles/{collection_title}'

    if not os.path.isdir(collection_path):
        os.mkdir(collection_path)

    if commutes in ['all', 'All']:
        commutes = ['20mi_7to3', '20mi_8to4', '20mi_9to5', '20mi_10to6',
                    '35mi_7to3', '35mi_8to4', '35mi_9to5', '35mi_10to6',
                    '50mi_7to3', '50mi_8to4', '50mi_9to5', '50mi_10to6',
                    '100mi_7to3', '100mi_8to4', '100mi_9to5', '100mi_10to6',
                    'stay_at_home']

    pool_frame = pd.read_csv(pool_file)
    if sort_by_pop:
        pool_frame.sort_values('Population', inplace=True, ascending=False)
        print('sorted')

    if number is not None:
        pool_frame = pool_frame[:number]

    util_frame = pd.read_csv(util_eia_file)
    util_frame = util_frame[util_frame['Utility Name'].isin(pool_frame['Utility'].unique())]

    i = 1
    for index, row in pool_frame.iterrows():
        state = row['State']
        ref_state = row['Reference State']
        ref_city = row['Reference City']
        zip_code = row['Largest Zip']
        util = row['Utility']
        tariff = row['Tariff']
        tz = row['Time Zone']
        best_commute = row['Best Commute']
        file_name = f'F{i}_{state}_{zip_code}_{tz}_{ref_city}_{ref_state}'

        ref_commutes = check_commutes(commute_list=commutes, best_commute=best_commute)

        generate_input_file(title=f'{collection_title}/{file_name}',
                            zip_codes=[zip_code],
                            years=years,
                            net_met_policies=net_met_policies,
                            house_loads=house_loads,
                            pv_sizes=pv_sizes,
                            hes_sizes=hes_sizes,
                            hes_opt_styles=hes_opt_styles,
                            v2h_limits=v2h_limits,
                            utilities=[util],
                            tariffs=[tariff],
                            commutes=ref_commutes,
                            charge_schemes=charge_schemes,
                            condensed_util_frame=util_frame)

        print(f'{file_name} completed')
        i += 1


def get_best_commute(tariff: Tariff, distance: int = 35):
    """
    This method returns the best commute schedule for a given TOU Tariff. This is determined by the number of peak 
    hours the vehicle would ostensibly be present for.
    Parameters
    ----------
    tariff: Tariff
        A tariff object for which to get the best commute

    Returns
    -------

    """
    if tariff is None:
        proceed = False
    elif not tariff.is_tou:
        proceed = False
    else:
        proceed = True

    if proceed:
        if distance not in [20, 35, 50, 100]:
            distance = 35

        mask = tariff.weekday_rates
        # for mon in mask:
        #     mon[mon == np.min(mon)] = 0
        #     mon[mon == np.max(mon)] = 1
        #     mon[(mon != 1) & (mon != 0)] = .5

        hour_sum = 0
        times = [(7, 15), (8, 16), (9, 17), (10, 18)]
        best_time = times[0]
        ev_zeros = np.zeros((12, 8))
        for comm in times:
            s1 = (12, comm[0])
            s2 = (12, 24 - comm[1])
            ev_mask = np.hstack((np.ones(s1), ev_zeros, np.ones(s2)))
            new_sum = np.sum(np.multiply(mask, ev_mask))
            if new_sum > hour_sum:
                hour_sum = new_sum
                best_time = comm
        start_hr = best_time[0]
        end_hr = best_time[1] - 12
        best_commute = f'{distance}mi_{start_hr}to{end_hr}'
    else:  # best commute only applies to
        best_commute = 'basic_commute'

    return best_commute
