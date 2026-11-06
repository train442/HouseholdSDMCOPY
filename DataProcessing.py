"""
This module contains constants and method pertaining to the processing of raw data into usable form for the overall
model. Generally speaking, the model operates in 5-minute timesteps so the methods in this module are geared to
turning raw data files of varying temporal resolution into this resolution. In addition, there are methods designed
to correct the processed files and align them temporally within the desired dates for the simulation since several of
the datasets are derived for differing calendar years.
"""
import os
import ast
import time

import dateutil.parser
import pandas as pd
from pandas import Timestamp, DataFrame
import numpy as np
from numpy import ndarray
# h5pyd is imported lazily inside get_NSRDB_metadata: it is only needed to download NSRDB solar
# data through the Wizard, but a module-level import made it a hard requirement for every consumer
# of this module -- including every simulation worker and the offline conversion scripts.
# scipy is imported lazily inside get_NSRDB_metadata for the same reason as h5pyd: cKDTree is only
# used for NSRDB nearest-grid-point lookups, not by the simulation.
import math as m
import requests
from bs4 import BeautifulSoup as bs


# Global Paths
processed_loads_path = 'City Data/Load Profiles/Processed/Parquets/'
custom_loads_path = 'City Data/Load Profiles/Custom Loads/'

#: Extensions a saved custom load profile may carry, newest convention first.
LOAD_PROFILE_EXTENSIONS = ('.npz', '.csv')


def save_load_profile(profile, path_stem: str, compress: bool = True) -> str:
    """
    Writes a household load profile to disk in the compact array format.

    The legacy format was a CSV holding a redundant ``Time`` column plus ``Load(kW)`` at ~16
    significant digits -- 4.18 MB for a 105,120-step year. The model discards the timestamps (the grid
    is a fixed 5-minute cadence derivable from the simulation dates) and rounds the values to 3
    decimals on load anyway, so all of that precision and structure was being written and re-parsed for
    nothing.

    Storing just the rounded values as a compressed ``.npz`` gives the same array back: **19x smaller
    (4.18 MB -> 0.22 MB) and 38x faster to read (72 ms -> 1.9 ms)**. Verified to reproduce the previous
    values exactly.

    Parameters
    ----------
    profile : array_like
        The load profile in kW, one entry per timestep.
    path_stem : str
        Destination path WITHOUT extension; the correct one is appended.
    compress : bool, optional
        Write ``.npz`` (compressed). False writes a legacy ``.csv`` instead, for interoperability with
        other tools. Default True.

    Returns
    -------
    str
        The path actually written, including extension.
    """
    values = np.round(np.asarray(profile, dtype=float).flatten(), 3)
    if compress:
        path = path_stem + '.npz'
        np.savez_compressed(path, load=values)
    else:
        path = path_stem + '.csv'
        pd.DataFrame({'Load(kW)': values}).to_csv(path, index=False)
    return path


def load_load_profile(path: str) -> ndarray:
    """
    Reads a household load profile, accepting both the compact ``.npz`` and legacy ``.csv`` formats.

    The format is chosen by extension; if ``path`` carries no recognised extension, each is tried in
    turn, so callers may pass a stem. Legacy CSVs are read by column name, so the presence or absence
    of the old ``Time`` column does not matter.

    Parameters
    ----------
    path : str
        Path to a .npz or .csv load profile, or the same path without an extension.

    Returns
    -------
    ndarray
        1-D array of load values in kW, rounded to 3 decimals.

    Raises
    ------
    FileNotFoundError
        If no matching file exists.
    """
    resolved = path if os.path.exists(path) else None
    if resolved is None:
        stem = path
        for ext in LOAD_PROFILE_EXTENSIONS:
            if stem.endswith(ext):
                stem = stem[: -len(ext)]
                break
        resolved = next((stem + ext for ext in LOAD_PROFILE_EXTENSIONS if os.path.exists(stem + ext)), None)
        if resolved is None:
            raise FileNotFoundError(f'no load profile found for {stem!r} (tried {LOAD_PROFILE_EXTENSIONS})')

    if resolved.endswith('.npz'):
        with np.load(resolved) as data:
            values = data['load']
    else:
        values = pd.read_csv(resolved, usecols=['Load(kW)']).to_numpy()
    return np.round(np.asarray(values, dtype=float).flatten(), 3)


#: Nominal start of every processed ResStock profile. The 5-minute grid is implicit in the row count.
RESSTOCK_START = '1/1/2018 00:00 am'


def resstock_timestamps(n_rows: int, start: str = RESSTOCK_START):
    """
    Rebuilds the timestamp index for a processed ResStock profile.

    Processed profiles no longer store a ``Time`` column. It was identical in every file -- a hardcoded
    2018 5-minute grid, a pure function of the row count -- and measured **84.9% of the stored bytes**
    (841.7 KB of a ~1000 KB file, because Snappy barely compresses monotonic int64 timestamps). Any
    caller that needs the timestamps regenerates them here instead.

    Parameters
    ----------
    n_rows : int
        Number of timesteps in the profile.
    start : str, optional
        Start of the profile. Defaults to the ResStock reference year.

    Returns
    -------
    pandas.DatetimeIndex
        The 5-minute timestamps for the profile.
    """
    return pd.date_range(start=start, periods=n_rows, freq='5min')


def read_resstock_profile(path: str, with_time: bool = False):
    """
    Reads a processed ResStock load profile, tolerating files with or without a stored ``Time`` column.

    Parameters
    ----------
    path : str
        Path to the parquet profile.
    with_time : bool, optional
        Return a DataFrame with a ``Time`` column (regenerated if absent) rather than a bare array.
        Default False, which is what the model wants.

    Returns
    -------
    ndarray or pandas.DataFrame
        The load in kW, either as a 1-D array or as a two-column frame.
    """
    frame = pd.read_parquet(path, columns=['Load(kW)'])
    if not with_time:
        return frame.to_numpy().flatten()
    return pd.DataFrame({'Time': resstock_timestamps(len(frame)),
                         'Load(kW)': frame['Load(kW)'].to_numpy()})


def find_load_profile(path_stem: str):
    """
    Returns the path of an existing load profile for the given stem, or None.

    Parameters
    ----------
    path_stem : str
        Path without extension.

    Returns
    -------
    str or None
        The first matching path, preferring the compact format.
    """
    for ext in LOAD_PROFILE_EXTENSIONS:
        if os.path.exists(path_stem + ext):
            return path_stem + ext
    return None
user_profile_path = 'City Data/Load Profiles/User Profiles/'
load_lookup_path = 'City Data/Load Profiles/City Load Lookup/'

# URLS and Webscraping
zip_url = 'https://www.zipdatamaps.com/'
web_headers = {'user-agent': 'Mozilla/5.0 (X11; CrOS x86_64 8172.45.0) AppleWebKit/537.36 (KHTML, like Gecko) '
                             'Chrome/51.0.2704.64 Safari/537.36',
               'method': 'GET'}


# Classes
class MissingValue(Exception):
    """
    This is a custom class which inherits Exception. It is raised whenever there is a missing entry when loading data.
    """

    def __int__(self, message):
        super().__init__(message)


def zip_scrape(zip_code: str):
    """
    This method will scrape the data for a given zipcode and return it as a dictionary. The source website is
    'www.zipdatamaps.com'.

    Parameters
    ----------
    zip_code: str
        The zipcode for which we want data

    Returns
    -------
    zip_dict : dict
        A dictionary containing data for a given zipcode.

    Notes
    -----
    Fields for the dictionary are 'Locality' (city, town), 'State', 'County', 'Population', 'Coordinates',
    'Time Zone', and 'Area' (in sq mi).
    """
    global zip_url
    global web_headers

    if type(zip_code) is int:
        zip_code = str(zip_code).zfill(5)

    url = zip_url + zip_code
    result = requests.get(url, headers=web_headers)
    doc = bs(result.text, "html.parser")

    state = doc.find_all('title')[0].text.split(',')[-1][1:]

    loc_container = doc.find_all('table')[0].find_all('tr')
    locality = loc_container[0].find_all('td')[1].text
    county_header = loc_container[1].find_all('td')[0].text
    if county_header == 'Organization':
        county = ' '.join(loc_container[2].find_all('td')[1].text.split()[:-1])
    else:
        county = ' '.join(loc_container[1].find_all('td')[1].text.split()[:-1])

    try:
        dem_container = doc.find_all(['div'], class_='container', id=zip_code + '-demographics-data')
        pop = dem_container[0].find('tr').find_all('td')[1].text
        pop = int(pop.replace(',', ''))
    except IndexError:
        pop = 0

    geo_container = doc.find_all(['div'], class_='container', id=zip_code + '-geography-data')
    geo_rows = geo_container[0].find_all('tr')
    geo_headers = [row.find_all('td')[0].text for row in geo_rows]

    try:
        area_ind = geo_headers.index('Area')
        area = float(geo_rows[area_ind].find_all('td')[1].text.split()[0])
    except ValueError:
        area = 0

    coord_ind = geo_headers.index('Coordinates')
    coords = geo_rows[coord_ind].find_all('td')[1].text.split(',')
    coords = (np.round(float(coords[0]), 4), np.round(float(coords[1]), 4))

    conv = {'Eastern Standard Time': 'EST',
            'Central Standard Time': 'CST',
            'Mountain Standard Time': 'MST',
            'Pacific Standard Time': 'PST',
            'Hawaii Standard Time': 'HST',
            'Alaska Standard Time': 'AST',
            'Eastern Daylight Time': 'EST',
            'Central Daylight Time': 'CST',
            'Mountain Daylight Time': 'MST',
            'Pacific Daylight Time': 'PST',
            'Hawaii Daylight Time': 'HST',
            'Alaska Daylight Time': 'AST'
            }

    tz_ind = geo_headers.index('Time Zone')
    tz = conv[geo_rows[tz_ind].find_all('td')[1].text]

    zip_dict = {'Zip Code': zip_code,
                'Locality': locality,
                'County': county,
                'State': state,
                'Population': pop,
                'Coordinates': coords,
                'Time Zone': tz,
                'Area': area}

    return zip_dict


def increase_load_res(raw_vec: ndarray):
    """
    This method increases the resolution of a rate vector provided by 3 times. The primary use is to increase the
    resolution of the house load data (natively in 15 min) to a 5 minute timestep (see process_resstock_load). Future
    updates may provide user
    input in regard to how much the resolution is increased.
    Parameters
    ----------
    raw_vec : ndarray
        A 1D numpy array whose resolution is to be increased. In the context of this model it is an array containing
        the house load (kW) in 15 minute timestep derived from NREL's ResStock housing load profiles.
    Returns
    -------
    comb : ndarray
        A 1D numpy array with increased temporal resolution. For this model it represents the house load (kW) at
        every 5 minute timestep.
    """
    # This inputs the raw house load kwh data numpy array (raw) with 15 min resolution and converts it to an array
    # corresponding to kW with 5 minute resolution

    # extract vector length and convert shape to 1D from 0D
    num = raw_vec.shape[0]
    raw_vec = raw_vec.reshape((num, 1))

    # evaluate intermediate values between values
    vec0 = np.vstack((raw_vec[-1], raw_vec[0:-1]))  # raw vector with last value appended to front (for calculations)
    vec1 = vec0 + (1 / 3) * (raw_vec - vec0)
    vec2 = vec0 + (2 / 3) * (raw_vec - vec0)

    # combine intermediate vector with adjusted raw vector, and then flatten into 1D array
    comb = np.hstack((vec0, vec1, vec2))
    comb = comb.reshape((comb.size, 1))

    return comb


def process_resstock_load(old_file_path: str, new_file_path: str):
    """
    This method processes a raw 15-minute resolution ResStock house load file (in parquet form) into 5-minute csv
    format.

    Parameters
    ----------
    old_file_path:  str
        The filepath of the raw ResStock house load parquet file.
    new_file_path
        The desired filename of the new processed 5-min csv file.
    Returns
    -------
    None
    """
    # process Resstock load profiles from 15 min to 5 min.
    if old_file_path[-8:] == '.parquet':
        raw_load = pd.read_parquet(old_file_path,
                                   columns=['out.electricity.total.energy_consumption']).to_numpy() / .25
    elif old_file_path[-4:] == '.csv':
        raw_load = pd.read_csv(old_file_path,
                               usecols=['out.electricity.total.energy_consumption'], dtype=float).to_numpy() / .25
    else:
        # noinspection PyTypeChecker
        raw_load = pd.read_excel(old_file_path,
                                 usecols=['out.electricity.total.energy_consumption'], dtype=float).to_numpy() / .25

    new_load = increase_load_res(raw_load)
    # No 'Time' column. It was a hardcoded 2018 5-minute grid, identical in every processed file and
    # derivable from the row count, yet it accounted for 84.9% of each file's stored bytes (841.7 KB of
    # ~1000 KB) because Snappy cannot compress monotonic int64 timestamps. Callers that need it use
    # resstock_timestamps(); the model only ever reads 'Load(kW)'.
    pd.DataFrame({'Load(kW)': new_load.flatten()}).to_parquet(new_file_path, index=False)
    return None


def build_load_lookup(state: str, city: str, metadata_path: str, log=print) -> str:
    """
    Builds/refreshes the per-city load summary lookup table (City Load Lookup/{state}_{city}_loads.csv) that
    load_match_yearly searches, from every processed 5-min parquet already on disk for that city. Replaces
    Scripts/ResStock Loads/load_summarizer.py, which had a hardcoded, machine-specific raw-parquet path and
    referenced metadata columns (eg 'in.vintage', 'in.geometry_garage', 'in.has_pv') that don't exist in
    metadata_path's simplified column set -- summary_columns here is trimmed to what's actually available.

    Parameters
    ----------
    state : str
        Abbreviated state name (eg 'GA').
    city : str
        City name, matching its folder name under processed_loads_path.
    metadata_path : str
        Filepath to the ResStock metadata csv (see RESSTOCK_METADATA_PATH in DataImportWizard.py) used to look
        up each building's characteristics by (bldg_id, upgrade).
    log : callable, optional
        Callback for progress messages. Default is print.

    Returns
    -------
    summary_path : str
        Filepath of the (created or updated) summary csv.

    Notes
    -----
    -   Only buildings actually present in metadata_path are summarized. A processed parquet whose (bldg_id,
        upgrade) isn't found there is skipped with a log message rather than raising -- this shouldn't normally
        happen since download_resstock_city can only ever have downloaded a building metadata_path already
        contains, but the metadata snapshot on hand may not cover every upgrade level for every building.
    -   Resumable: (bldg_id, upgrade) combinations already present in the summary file are skipped, so this is
        cheap to re-run after downloading more cities or upgrade levels.
    """
    global load_lookup_path, processed_loads_path
    summary_columns = ['bldg_id', 'upgrade', 'total usage (kWh)', 'house type', 'house size (ft^2)', 'bedrooms',
                       'monthly usage (kWh)', 'city', 'state', 'county code', 'puma code', 'emissions region',
                       'climate zone', 'lat', 'long']
    month_ends = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334, 365]
    steps_per_day = 24 * 12  # 5-min steps/day

    src_dir = os.path.join(processed_loads_path, state, city)
    if not os.path.isdir(src_dir):
        raise Exception(f'{src_dir} not found -- process parquets for this city first.')

    os.makedirs(load_lookup_path, exist_ok=True)
    summary_path = os.path.join(load_lookup_path, f'{state}_{city}_loads.csv')
    summary_frame = pd.read_csv(summary_path) if os.path.exists(summary_path) \
        else pd.DataFrame(columns=summary_columns)
    existing = set(zip(summary_frame['bldg_id'], summary_frame['upgrade']))

    metadata = pd.read_csv(metadata_path)

    new_rows = []
    skipped_no_metadata = 0
    for parq in os.listdir(src_dir):
        if not parq.endswith('_5min.parquet'):
            continue
        bldg_id, upgrade = (int(x) for x in parq[:-len('_5min.parquet')].split('-'))
        if (bldg_id, upgrade) in existing:
            continue

        meta_rows = metadata[(metadata['bldg_id'] == bldg_id) & (metadata['upgrade'] == upgrade)]
        if meta_rows.empty:
            skipped_no_metadata += 1
            continue
        meta_row = meta_rows.iloc[0]

        load_frame = pd.read_parquet(os.path.join(src_dir, parq), columns=['Load(kW)'])
        all_usage = load_frame['Load(kW)'].to_numpy() / 12  # kW at 5-min steps -> kWh per step
        month_usage = [round(float(all_usage[month_ends[i - 1] * steps_per_day:
                                             month_ends[i] * steps_per_day].sum()), 2) for i in range(1, 13)]

        new_rows.append({
            'bldg_id': bldg_id,
            'upgrade': upgrade,
            'total usage (kWh)': round(float(all_usage.sum()), 2),
            'house type': meta_row['in.geometry_building_type_acs'],
            'house size (ft^2)': meta_row['in.sqft'],
            'bedrooms': meta_row['in.bedrooms'],
            'monthly usage (kWh)': str(month_usage),
            'city': city,
            'state': state,
            'county code': meta_row['in.county'],
            'puma code': meta_row['in.puma'],
            'emissions region': meta_row['in.generation_and_emissions_assessment_region'],
            'climate zone': meta_row['in.building_america_climate_zone'],
            'lat': meta_row['in.weather_file_latitude'],
            'long': meta_row['in.weather_file_longitude'],
        })
        existing.add((bldg_id, upgrade))

    if new_rows:
        summary_frame = pd.DataFrame(new_rows) if summary_frame.empty \
            else pd.concat([summary_frame, pd.DataFrame(new_rows)], ignore_index=True)
        summary_frame.to_csv(summary_path, index=False)
    log(f'{city}, {state}: added {len(new_rows)} building(s) to lookup ({skipped_no_metadata} skipped -- not '
       f'in metadata), {len(summary_frame)} total -> {summary_path}')
    return summary_path


def shift_by_hour(profile: ndarray, hours: int, profile_resolution=5):
    """
    This method shifts a profile forwards (+) or backwards (-) by a desired number of hours. This method was
    developed to account for certain data sets being set to a universal time and not the local time for which the
    set was derived. The method will either grab elements from the rear of the array and place them up front or vice
    versa.

    Parameters
    ----------
    profile: ndarray
        The profile to be shifted, represented by a 1D numpy array.
    hours: int
        The number of hours forward (+) or back (-) that the profile is meant to be shifted. For example,
        if a profile was set in EST and needed to be converted to CST, hours would be -1 for one hour behind.
    profile_resolution : int, optional
        The temporal resolution in minutes of the profile to be shifted. Default is 5 minutes.
    Returns
    -------
    profile : ndarray
        A profile shifted temporally by the hours desired.
    """
    options = [1, 5, 10, 15, 30, 60]
    profile_resolution = min(options, key=lambda x: abs(x - profile_resolution))
    ind = hours * int(60 / profile_resolution)
    profile = np.append(profile[-ind:], profile[0:-ind])
    return profile


def shift_by_day(profile: ndarray, days: int, profile_resolution: int = 5, leap=False) -> ndarray:
    """
    This method will temporally shift a profile forward(+) or backward (-) by a desired number of days. The purpose
    behind this method is to have alignment between datasets whose base years are different. For example, given that
    house load is dependent on the day of the week since people aren't home during weekdays, it is important for the
    driving pattern and house load profiles (derived fom year 2018) to line up accordingly. A positive shift will
    take elements from the beginning of the array and tack them to the back (shifting forward in time), a negative
    shift takes elements from the end of the array and tacks them to the front.
    Parameters
    ----------
    profile : ndarray
        The data profile to shifted
    days : int
        The number of days forward (+) or backward(-) to shift the profile.
    profile_resolution : int
        The temporal resolution in minutes of the profile to be shifted. Default is 5 minutes.
    leap: bool
        Whether the new profile needs to account for leap year, for which the profiles first day is repeated.
    Returns
    -------
    profile : int
        A temporally shifted profile.
    """
    options = [1, 2, 3, 4, 5, 6, 10, 12, 15, 20, 30, 60]
    profile_resolution = min(options, key=lambda x: abs(x - profile_resolution))
    steps_per_day = 24 * int(60 / profile_resolution)
    if days > 0:  # cut days from front and stitch to end
        profile = np.append(profile[(days * steps_per_day):], profile[0: (days * steps_per_day)])
    elif days < 0:  # cut days from end and stitch to front
        days = abs(days)
        profile = np.append(profile[-(days * steps_per_day):], profile[0: -(steps_per_day * days)])

    if leap:
        profile = np.append(profile, profile[steps_per_day:(2 * steps_per_day)])

    return profile


def datetime_to_timestep(datetime: Timestamp, start_date=None, resolution=5):
    """
    This method returns the corresponding timestep of a given date (pandas Timestamp)
    Parameters
    ----------
    datetime : Timestamp
        The datetime for which the corresponding timestamp is desired.
    start_date: Timestamp, optional
        The starting datetime for the simulation. Default is None, for which the method will default to Jan 1st of
        current year (given by datetime parameter)
    resolution : int
        The duration of each timestep in minutes. Default is 5.

    Returns
    -------
    steps: int
        The timestep of tue given datetime (Timestamp).
    """
    # this function converts a datetime to is numbered step within a calendar year or given a start date
    start_date: pd.Timestamp
    if start_date is None:
        date_str = '1/1/' + str(datetime.year)
        start_date = pd.to_datetime(date_str)

    td = datetime - start_date
    step_per_hour = int(60 / resolution)
    steps = ((td.days * 24 * step_per_hour) + (td.components.hours * step_per_hour) +
             m.floor(td.components.minutes / resolution) + 1)
    return steps


def timestep_to_datetime(step: int, start_date=pd.to_datetime('1/1/2018'), resolution=5):
    """
    This method converts a timestep inside a simulation to its corresponding pandas Timestamp.

    Parameters
    ----------
    step : int
        The timestep for which the Timestamp is desired.
    start_date : Timestamp
        The starting Timestamp for the simulation. Default is 1/1/2018.
    resolution : int
        The duration of each timestep in minutes. Default is 5.

    Returns
    -------
    Timestamp
        The Timestamp corresponding to the desired timestep.
    """
    total_minutes = (step - 1) * resolution
    delta = pd.Timedelta(str(total_minutes) + ' minutes')
    return start_date + delta


def load_match_yearly(state: str, city: str, usage: float, house_type: str = None, upgrade: (int, list) = None,
                      bedroom: int = None, sqft: int = None, pool_size: int = 5, save_profile: bool = False,
                      return_profile: bool = True, year: int = 2018):
    """
    This method will generate a house load profile from a desired yearly usage amount (ie 11,000 kWh) using a
    weighted average of NREL's ResStock housing profiles for a given location. The pool of house profiles can be
    refined using the house_type, upgrade, bedroom, and sqft parameters. The final profile is corrected from native
    year of the profiles (2018) to any year desired.

    Parameters
    ----------
    state : str
        Abbreviated state name of location (ie, GA).
    city : str
        The name of the city for which the simulation is to be run.
    usage : float
        The amount of yearly house load usage in kWh. This method will generate a profile with this total amount.
    house_type : str, optional
        The kind of household desired. Can be either be 'Single-Family Detached' or 'Single-Family Attached' with
        respect to the garage. Default is None, meaning both are included in the selection pool of profiles.
    upgrade : int, list, optional
        The upgrade level (0 to 10) of the house with respect to electrification and energy savings such as electric
        stoves and insulation. Default is None, meaning all levels are included in the selection pool of profiles.
    bedroom : int, optional
        The number of bedrooms in the household. Default is None, meaning all bedroom amounts are allowed in the
        selection pool. Cannot exceed the maximum or go below the minimum number of bedrooms in city's load list.
    sqft : int, optional
        The square footage of the household to be simulated. Default is None, meaning all sizes are included in the
        selection pool of profiles.
    pool_size : int, optional
        The number of profiles used in the selection pool. Default is 5. The final profile will be a weighted average
        of these profiles based on the proximity of their total energy usage to the usage amount provided.
    save_profile : bool, optional
        Whether to save the resulting profile into the "Custom Loads" folder. Default is False.
    return_profile : bool, optional
        Whether to return the resulting profile. Default is True. Set to False when simply trying to save a custom
        load profile.
    year : int, optional
        The calendar year for the new profile. Default is 2018, the native year for the stock housing profiles. The
        resulting profile will be shifted should another year be provided so that the days of the week align.

    Returns
    -------
    new_profile : ndarray
        The new house load profile, consisting of a weighted average of the stock house profiles best matching the
        parameters.
    """
    # this function takes an input of a total yearly house load with a given location (city, state) and using that
    # city's load summary file, outputs a load file comprised of a weighted average of the closest load profiles.
    # Pool of choices can be refined by defining upgrade level, bedrooms, sqft, and house type. House type (so far)
    # can only be 'single-family detached' or 'single-family attached'. Minimum number of bedrooms is two. When
    # refining load list by house sqft, the 3 closest sizes are given. From there the pool is reduced to a given
    # number of loads closest to the given yearly usage. The number the pool is reduced to is given by pool_size with
    # a default value of 5. The difference between the pool loads and the input usage is recorded and used as a
    # weight when normalizing and adding these loads to generate the new load profile.

    global load_lookup_path
    master_file = load_lookup_path + state + '_' + city + '_loads.csv'

    houses_supported = ['Single-Family Detached', 'Single-Family Attached']

    load_frame = pd.read_csv(master_file)

    new_file = state + '_' + city + '_' + str(usage) + 'kWh'

    # first we want to filter by house type. Currently only two types supported (or even recorded)
    if (house_type is not None) and (house_type in houses_supported):
        load_frame = load_frame.loc[load_frame['house type'] == house_type]
        new_file = new_file + '_' + house_type
        if house_type not in load_frame['house type'].values:
            raise MissingValue('No load profiles of this house type in this city')

    # next we filter based on upgrade or list of upgrades
    if (upgrade is not None) and isinstance(upgrade, (list, int)):
        # upgrade should either be an int or a list
        if upgrade is int:
            load_frame = load_frame.loc[load_frame['upgrade'] == upgrade]
            new_file = new_file + '_upgrade' + str(upgrade)
        else:  # we know upgrade is a list now
            load_frame = load_frame.loc[load_frame['upgrade'].isin(upgrade)]
            new_file = new_file + '_upgrade('
            for up in upgrade:
                new_file = new_file + str(upgrade) + '_'
            new_file[-1] = ')'

    # next we filter based on bedrooms
    if (bedroom is not None) and (bedroom is int):
        # we also have to check if given amount is in the list of possible bedroom numbers in the load summary. If
        # not we simply use the maximum or minimum number found in the load summary.
        if bedroom in load_frame['bedrooms'].values:
            load_frame = load_frame.loc[load_frame['bedrooms'] == bedroom]
        else:
            max_bed = max(load_frame['bedrooms'].values)
            min_bed = min(load_frame['bedrooms'].values)
            bed = (bedroom > max_bed) * max_bed + (bedroom < min_bed) * min_bed  # use max/min value based on given #
            load_frame = load_frame.loc[load_frame['bedrooms'] == bed]
        new_file = new_file + '_' + str(bedroom) + 'bedroom'

    # next we filter by house size given in sqft
    if (sqft is int) or (sqft is float):
        house_sizes = np.array(load_frame['house size (ft^2)'].values.unique())
        abs_diffs = np.abs(house_sizes - sqft)
        top_indices = np.argsort(abs_diffs)[0:(min(3, len(house_sizes)))]  # take top three (or less)
        house_sizes = house_sizes[top_indices]
        load_frame = load_frame.loc[load_frame['house size (ft^2)'].isin(house_sizes)]
        new_file = new_file + '_' + str(sqft) + 'sqft'

    #  now we refine the current load pool to the size dictated by pool_size (or less if there's not enough left)
    new_file = new_file + '.csv'
    load_sizes = np.array(load_frame['total usage (kWh)'].values)
    load_diffs = np.abs(load_sizes - usage)
    load_indices = np.argsort(load_diffs)[0:(min(pool_size, len(load_sizes)))]
    load_sizes = load_sizes[load_indices]
    load_diffs = load_diffs[load_indices]
    weights = (1 - load_diffs / (np.sum(load_diffs))) / (len(load_diffs) - 1)
    load_frame = load_frame.loc[load_frame['total usage (kWh)'].isin(load_sizes)]
    new_profile = 0
    i = 0
    # now we normalize and add the remaining profiles while applying their weights
    for index, row in load_frame.iterrows():
        bldg_id = row['bldg_id']
        upgrade_lvl = row['upgrade']
        load_usage = row['total usage (kWh)']
        load_weight = weights[np.where(load_sizes == load_usage)[0][0]]
        load_path = processed_loads_path + state + '/' + city + '/'
        load_file = str(bldg_id) + '-' + str(upgrade_lvl) + '_5min.parquet'
        # Single-column parquet -> (n, 1); flatten so House.load_profile[i] is a scalar.
        load_profile = pd.read_parquet(load_path + load_file, columns=['Load(kW)']).to_numpy().flatten()
        new_profile = (new_profile + load_profile / load_profile.sum() * usage * load_weight * 12)
    if year == 2018:  # the year matches the year of the loads (we want to make sure the days of the week line up)
        start_date = '1/1/2018 00:00 am'
    else:
        start_date = '1/1/' + str(year) + ' 00:00 am'
        dow = pd.to_datetime(start_date).day_of_week
        if dow != 0:  # starting day of week is not monday (as in 2018) so we have to adjust profile to line up weekdays
            new_profile = np.concatenate((new_profile[(288 * dow):], new_profile[0:(288 * dow - 1)]))

    #normalization check (because sometimes loads are off)
    new_usage = np.sum(new_profile)/12
    if int(new_usage) != int(usage):
        new_profile = new_profile *(usage/new_usage)

    if save_profile:
        # new_file still carries the historical '.csv' suffix from the name-building block above;
        # strip it and let save_load_profile choose the extension.
        stem = new_file[:-4] if new_file.endswith('.csv') else new_file
        written = save_load_profile(new_profile, custom_loads_path + stem)
        print(city, state, 'saved ->', os.path.basename(written))
    if return_profile:
        return new_profile


def monthly_load_summary(profile_frame: DataFrame):
    """
    This function takes a post processed user profile with time column and usage column, and generates a month by
    month summary for use in matching load profiles. This consists of a Dataframe with a starting and ending
    Timestamp for each month contained in the user profile as well as the total usage for that month.

    Parameters
    ----------
    profile_frame : DataFrame
        A custom user profile with a 'Time' column and 'Usage (kWh)' column for which the monthly load summary is to
        be determined.

    Returns
    -------
    month_summary : DataFrame
        An N x 3 DataFrame where N is the number of months contained in the original user profile. The columns are
        starting Timestamp, ending Timestamp, and the energy usage (kWh) for each month respectively.
    """
    # this function takes a post processed user profile with time column and usage column, and generates a month by
    # month summary for use in matching load profiles.

    start_date: pd.Timestamp  # declare for readability and functionality
    end_date: pd.Timestamp

    start_date = profile_frame.loc[0, 'Time']
    end_date = profile_frame.iloc[-1, 0]
    end_date = end_date.round(freq='1D')

    num_months = (end_date.to_period('M') - start_date.to_period('M')).n + 1
    month_summary = pd.DataFrame(columns=['Start', 'End', 'Usage (kWh)'])

    for i in range(num_months):
        s = max(start_date,
                pd.to_datetime(str(start_date.month) + '/1/' + str(start_date.year)) + pd.DateOffset(months=i))
        e = min(end_date,
                pd.to_datetime(str(start_date.month) + '/1/' + str(start_date.year)) + pd.DateOffset(months=i + 1))
        # subframe = profile_frame[s:e]
        subframe = profile_frame[(profile_frame['Time'] >= s) & (profile_frame['Time'] < e)]
        usage = np.sum(subframe['Usage (kWh)'].to_numpy())
        data = {'Start': s, 'End': e, 'Usage (kWh)': usage}
        month_summary = pd.concat((month_summary, pd.DataFrame(data=data, index=[0])), ignore_index=True)

    return month_summary


def load_match_monthly(state: str, city: str, summary: DataFrame, house_type=None, upgrade=None, bedroom=None,
                       sqft=None, pool_size=5, year=2018, resolution=5):
    """
    This method will compile a load profile for a location (city and state) provided a monthly load summary (see
    monthly_load_summary method). The idea is to stitch together, month by month, a composite profile from the
    ResStock housing profiles based on which stock profiles match the load for each month and the other
    descriptive parameters provided.

    Parameters
    ----------
    state : str
        Abbreviated state name of location (ie, GA).
    city : str
        The name of the city for which the simulation is to be run.
    summary : DataFrame
        An N x 3 DataFrame where N is the number of months contained in the original user profile. The columns are
        starting Timestamp, ending Timestamp, and the energy usage (kWh) for each month respectively.
    house_type : str, optional
        The kind of household desired. Can be either be 'Single-Family Detached' or 'Single-Family Attached' with
        respect to the garage. Default is None, meaning both are included in the selection pool of profiles.
    upgrade : int, list, optional
        The upgrade level (0 to 10) of the house with respect to electrification and energy savings such as electric
        stoves and insulation. Default is None, meaning all levels are included in the selection pool of profiles.
    bedroom : int, optional
        The number of bedrooms in the household. Default is None, meaning all bedroom amounts are allowed in the
        selection pool. Cannot exceed the maximum or go below the minimum number of bedrooms in city's load list.
    sqft : int, optional
        The square footage of the household to be simulated. Default is None, meaning all sizes are included in the
        selection pool of profiles.
    pool_size : int, optional
        The number of profiles used in the selection pool. Default is 5. The final profile will be a weighted average
        of these profiles based on the proximity of their total energy usage to the usage amount provided.
    year : int, optional
        The calendar year for the new profile. Default is 2018, the native year for the stock housing profiles. The
        resulting profile will be shifted should another year be provided so that the days of the week align.
    resolution : int, optional
        The duration in minutes of each timestep. Default is 5.
    Returns
    -------
    new_profile : ndarray
        The new house load profile, consisting of a weighted average of the stock house profiles best matching the
        parameters.
    """
    # this function will take a monthly summary dataframe from monthly_load_summary and create a stitched together load
    # profile. summary must have 'Start', 'End' and 'Usage' (kWh)' columns

    master_file = \
        'D:/Bras Research/pythonProject/City Data/Load Profiles/City Load Lookup/' + state + '_' + city + '_loads.csv'

    # get hour shift
    city_list_frame = pd.read_csv('D:/Bras Research/pythonProject/Model Data/city_list.csv')
    hour_shift_dict = {'EST': 0, 'CST': -1, 'MST': -2, 'PST': -3}
    hour_shift = hour_shift_dict[
        city_list_frame[(city_list_frame['City'] == city) & (city_list_frame['State'] == state)].iloc[0, 4]]

    houses_supported = ['Single-Family Detached', 'Single-Family Attached']

    load_frame = pd.read_csv(master_file, converters={'monthly usage (kWh)': pd.eval})

    # new_file = state + '_' + city + '_' + str(np.sum(usages)) + 'kWh'
    new_file = ''

    # first we want to filter by house type. Currently only two types supported (or even recorded)
    if (house_type is not None) and (house_type in houses_supported):
        load_frame = load_frame.loc[load_frame['house type'] == house_type]
        # new_file = new_file + '_' + house_type
        if house_type not in load_frame['house type'].values:
            raise MissingValue('No load profiles of this house type in this city')

    # next we filter based on upgrade or list of upgrades
    if (upgrade is not None) and isinstance(upgrade, (list, int)):
        # upgrade should either be an int or a list
        if upgrade is int:
            load_frame = load_frame.loc[load_frame['upgrade'] == upgrade]
            new_file = new_file + '_upgrade' + str(upgrade)
        else:  # we know upgrade is a list now
            load_frame = load_frame.loc[load_frame['upgrade'].isin(upgrade)]
            new_file = new_file + '_upgrade('
            for up in upgrade:
                new_file = new_file + str(upgrade) + '_'
            new_file[-1] = ')'

    # next we filter based on bedrooms
    if (bedroom is not None) and (bedroom is int):
        # we also have to check if given amount is in the list of possible bedroom numbers in the load summary. If
        # not we simply use the maximum or minimum number found in the load summary.
        if bedroom in load_frame['bedrooms'].values:
            load_frame = load_frame.loc[load_frame['bedrooms'] == bedroom]
        else:
            max_bed = max(load_frame['bedrooms'].values)
            min_bed = min(load_frame['bedrooms'].values)
            bed = (bedroom > max_bed) * max_bed + (bedroom < min_bed) * min_bed  # use max/min value based on given #
            load_frame = load_frame.loc[load_frame['bedrooms'] == bed]
        new_file = new_file + '_' + str(bedroom) + 'bedroom'

    # next we filter by house size given in sqft
    if (sqft is int) or (sqft is float):
        house_sizes = np.array(load_frame['house size (ft^2)'].values.unique())
        abs_diffs = np.abs(house_sizes - sqft)
        top_indices = np.argsort(abs_diffs)[0:(min(3, len(house_sizes)))]  # take top three (or less)
        house_sizes = house_sizes[top_indices]
        load_frame = load_frame.loc[load_frame['house size (ft^2)'].isin(house_sizes)]
        new_file = new_file + '_' + str(sqft) + 'sqft'

    #  now we refine the current load pool to the size dictated by pool_size (or less if there's not enough left)
    new_file = new_file + '.csv'

    all_loads = np.array(load_frame['monthly usage (kWh)'].to_list())
    full_start: pd.Timestamp
    full_end: pd.Timestamp
    full_start = summary.iloc[0, 0]
    full_end = summary.iloc[-1, 1]
    num_steps = (full_end - full_start).days * 24 * 12
    new_profile = np.zeros((num_steps, 1))
    for index, row in summary.iterrows():
        start: pd.Timestamp
        start = row['Start']
        end = row['End'] - pd.Timedelta(str(resolution) + ' minutes')
        # assign indices of new profile to which to add loaded profiles from file
        s = datetime_to_timestep(datetime=start, start_date=full_start) - 1
        e = datetime_to_timestep(datetime=end, start_date=full_start)
        # assign indices of loaded profiles from which to pull data (based on year start)
        s2 = datetime_to_timestep(datetime=start, start_date=pd.to_datetime('1/1/' + str(start.year))) - 1
        e2 = datetime_to_timestep(datetime=end, start_date=pd.to_datetime('1/1/' + str(start.year)))
        usage = row['Usage (kWh)']
        month = start.month
        new_year_start_dow = start.day_of_week
        fraction = ((end - start).days + 1) / start.daysinmonth
        load_sizes = fraction * all_loads[:, (month - 1)]
        load_diffs = np.abs(load_sizes - usage)
        load_indices = np.argsort(load_diffs)[0:(min(pool_size, len(load_sizes)))]
        load_sizes = load_sizes[load_indices]
        load_diffs = load_diffs[load_indices]
        weights = (1 - load_diffs / (np.sum(load_diffs))) / (len(load_diffs) - 1)
        sub_frame = load_frame.loc[load_indices]
        for index2, row2 in sub_frame.iterrows():
            bldg_id = row2['bldg_id']
            upgrade_lvl = row2['upgrade']
            load_usage = row2['monthly usage (kWh)'][month - 1] * fraction
            load_weight = weights[np.where(load_sizes == load_usage)[0][0]]
            load_path = processed_loads_path + state + '/' + city + '/'
            load_file = str(bldg_id) + '-' + str(upgrade_lvl) + '_5min.parquet'
            load_profile = pd.read_parquet(load_path + load_file, columns=['Load(kW)']).to_numpy().flatten()
            load_profile = shift_by_hour(load_profile, hour_shift)
            file_dow = pd.to_datetime(str(year)).day_of_week
            new_year_start_dow = start.day_of_week
            day_shift = new_year_start_dow - file_dow
            # we correct "day_shift" to give us smallest shift in days either forward (+) or backwards (-)
            if day_shift > 3:
                day_shift -= 7
            elif day_shift < -3:
                day_shift += 7
            load_profile = shift_by_day(load_profile, day_shift, leap=start.is_leap_year)
            new_profile[s:e] += np.reshape(
                ((load_profile[s2:e2] / load_profile[s2:e2].sum() * usage * 12) * load_weight),
                ((e - s), 1))
    return new_profile


def normalize_profile_hourly(original: ndarray, normalizer: ndarray):
    """
    This method will take a 5 minutes load profile and normalize it to another hourly profile, such that the
    cumulative energy usage for each hour within the original profile matches the hourly usage from the normalizing
    profile. The purpose of this method was to ensure the composite profile created for a user using the
    load_match_monthly method would in turn be normalized to match their hourly usage data.
    Parameters
    ----------
    original: ndarray
        A N x 1 numpy array of the 5-min resolution house load profile that needs to be normalized, where N is the
        number of timesteps.
    normalizer : ndarray
        A (N/12) x 1 numpy array of tht 1 hour resolution normalizing profile. This profile is typically the users
        raw hourly load data from their utility. N is the number of timesteps in the NEW profile.
    Returns
    -------
    new_profile : ndarray
        A N x 1 numpy array for the new house load profile, normalized to match the users raw hourly data contained in
        the normalizer parameter.
    """
    # This function takes a 5min load profile and normalizes it from an hourly usage profile. Normalizer should be
    # 1/12 the length of the original
    new_profile = np.zeros(shape=original.shape)
    for i in range(len(normalizer)):
        selection = original[i * 12:((i + 1) * 12)]
        factor = normalizer[i] / (np.sum(selection) / 12)
        new_profile[i * 12:((i + 1) * 12)] = selection * factor

    return new_profile


def user_load_process(file):
    """
    This INCOMPLETE method is proposed to process any customer's raw house load data in any format into a simplified
    2 column pandas Dataframe. The first column would contain the timestamp and the second column would contain the
    usage (in kWh). This Dataframe could then be fed into the monthly_summary method, the result of which could then
    be fed into the load_match_monthly method to generate a 5-min resolution house load profile for the customer
    which would match their original data.

    Parameters
    ----------
    file : str
        Filepath for a raw utility load data sheet.

    Returns
    -------
    DataFrame

    Notes
    -----
    THIS METHOD IS INCOMPLETE, AND WILL LIKELY BE COMPLEX.
    """
    #  this function is supposed to process a given user load profile is csv format.
    frame = pd.read_csv(user_profile_path + file)
    condensed_frame = pd.DataFrame()
    cols = frame.columns.to_list()
    time_cols = []
    number_cols = []
    resolution = ''
    a = 0
    is_str = True
    for col in cols:
        is_str = False
        try:
            a = int(frame.loc[0, col])
            number_cols.append(col)
        except (TypeError, ValueError):
            try:
                a = pd.to_datetime(frame[0, col])
                b = pd.to_datetime(frame[1, col])
                delt = b - a
                if delt.components.days == 1:
                    resolution = 'daily'
                elif delt.components.hours == 1:
                    resolution = 'hourly'
                elif delt.components.minutes == 1:
                    resolution = '1 minute'
                elif delt.components.minutes == 5:
                    resolution = '5 minutes'
                elif delt.components.minutes == 30:
                    resolution = '30 minutes'

            except dateutil.parser.ParserError:
                a = 1

    return a, resolution, time_cols, condensed_frame, is_str


def resample_to_5min(raw_vec: ndarray, native_interval_minutes: int = 30) -> ndarray:
    """
    Upsamples a raw solar-data vector (GHI or Temperature) from its native NSRDB temporal resolution to 5-min
    resolution via linear interpolation between consecutive samples (with wraparound from the last sample back
    to the first). Generalizes the interpolation increase_solar_res used to perform for a fixed 30-min native
    resolution to any of NSRDB's available intervals (5, 10, 15, 30, or 60 minutes), since different NSRDB
    datasets (eg, GOES Conus vs GOES Aggregated) are natively sampled at different rates.

    Parameters
    ----------
    raw_vec : ndarray
        A numpy array for the raw GHI or Temperature data from NREL at native_interval_minutes resolution.
    native_interval_minutes : int, optional
        The native temporal resolution of raw_vec, in minutes. Must be a multiple of 5 (eg, 5, 10, 15, 30, 60).
        Default is 30 (NSRDB's older PSM3 v3 CONUS native resolution).

    Returns
    -------
    ndarray
        A new Nx1 numpy array for the processed GHI or Temperature (C) data, now in 5-min resolution.
    """
    if native_interval_minutes % 5 != 0:
        raise ValueError(f'native_interval_minutes ({native_interval_minutes}) must be a multiple of 5')
    steps = native_interval_minutes // 5

    raw_vec = np.asarray(raw_vec).reshape((-1, 1))
    if steps == 1:  # already 5-min resolution -- nothing to interpolate
        return raw_vec

    next_vec = np.vstack((raw_vec[1:], raw_vec[0:1]))
    fractions = [raw_vec + (k / steps) * (next_vec - raw_vec) for k in range(steps)]

    comb = np.hstack(fractions)
    comb = comb.reshape((comb.size, 1))

    return comb


def increase_solar_res(raw_vec):
    """
    This method increases the raw 30min resolution NREL solar data to a 5-min resolution.

    Parameters
    ----------
    raw_vec : ndarray
        A numpy array for the raw GHI or Temperature data from NREL in 30-min resolution.

    Returns
    -------
    comb : ndarray
        A new numpy array for the processed GHI or Temperature (C) data from NREL, now in 5 min resolution.

    Notes
    -----
    -   Kept as a thin wrapper around resample_to_5min(raw_vec, 30) for backwards compatibility with existing
        callers; new code should call resample_to_5min directly so it can specify a dataset's actual native
        resolution.
    """
    return resample_to_5min(raw_vec, native_interval_minutes=30)


def get_NSRDB_metadata(year=2018):
    """
    This method is meant to extract the metadata from NREL's NSRDB database.

    Parameters
    ----------
    year : int
        The desired year for metadata extraction.

    Returns
    -------
    metadata : h5pyd.File
        A special format file containing the NSRDB metadata.
    coord_tree : cKDTree
        A cKDTree for use in extracting data form metadata based on location coordinates (lat and long).

    """
    #   extract the metadata from NREL's NSRDB for a given year as well the corresponding coordinate cKDTree

    try:
        import h5pyd
    except ImportError as ex:  # pragma: no cover - depends on the local environment
        raise ImportError(
            'h5pyd is required to download NSRDB solar data. Install it with "pip install h5pyd" '
            'and configure your NSRDB credentials in the Data Import Wizard.') from ex
    metadata = h5pyd.File('/nrel/nsrdb/v3/nsrdb_' + str(year) + '.h5', 'r')

    from scipy.spatial import cKDTree
    coord_tree = cKDTree(metadata['coordinates'])

    return metadata, coord_tree


def get_NSRDB_index(coords: tuple, coord_tree):
    """
    This method will retrieve the proper index within the NREL metadata for the desired location using a tuple of
    coordinates (lat, long) and a cKDTree object retrieved using the get_NSRDB_metadata method.

    Parameters
    ----------
    coords : tuple
        A 2 element tuple for the desired location latitude and longitude.
    coord_tree : cKDTree
        A cKDTree object containing all possible coordinates within the NSRDB metadata (see get_NSRDB_metadata).

    Returns
    -------
    city_index : int
        Index of desired location within the NSRDB metadata
    """
    #  within provided get index of given coordinates within metadata given its corresponding coordinate tree

    lat_lon = np.array([coords[0], coords[1]])
    dist, city_index = coord_tree.query(lat_lon)

    return city_index


def get_NSRDB_GHI(city_index: int, metadata):
    """
    This method extracts the raw GHI and temperature from NSRDB metadata given the index and metadata.

    Parameters
    ----------
    city_index : int
    metadata : h5pyd.File

    Returns
    -------
    ghi_series : ndarray
        Raw GHI and temp data in numpy array form.
    """
    #  extract GHI data from metadata

    dset = metadata['ghi']

    ghi_series = dset[:, city_index] / dset.attrs['psm_scale_factor']

    ghi_series = np.array(ghi_series)

    return ghi_series


def process_NSRDB_profile(old_file_path: str, new_file_path: str, time_adjust=0, native_interval_minutes=30):
    """
    This method will process a raw NREL GHI/Temp file into a newer 5-min resolution and save it under a new
    name.

    Parameters
    ----------
    old_file_path : str
        Filepath of file to be processed. Must have 'GHI(W/m^2)' and 'Temp(C)' columns at native_interval_minutes
        resolution.
    new_file_path : int
        Filepath of new processed file.
    time_adjust : int, optional
        Hours to shift profile forward (+) or backward (-) by. Default is 0.
    native_interval_minutes : int, optional
        The native temporal resolution of the raw file, in minutes. Must be a multiple of 5. Default is 30
        (NSRDB's older PSM3 v3 CONUS native resolution); pass eg 5 for GOES Conus v4 (already 5-min, so this
        just applies the UTC shift and re-stamps the timestamps) or 10/15/60 for other NSRDB v4 datasets.
    Returns
    -------
    None
    """
    #  process NSRDB profiles from their native resolution to 5 min
    raw_profile = pd.read_csv(old_file_path, usecols=['GHI(W/m^2)', 'Temp(C)'], dtype=float)

    raw_ghi = raw_profile['GHI(W/m^2)'].to_numpy()
    raw_temp = raw_profile['Temp(C)'].to_numpy()

    num = raw_ghi.shape[0]
    raw_ghi = raw_ghi.reshape((num, 1))
    raw_temp = raw_temp.reshape((num, 1))

    steps_per_hour = 60 // native_interval_minutes
    shift = steps_per_hour * time_adjust
    raw_ghi = np.vstack((raw_ghi[shift:], raw_ghi[0:shift]))
    raw_temp = np.vstack((raw_temp[shift:], raw_temp[0:shift]))

    new_ghi = resample_to_5min(raw_ghi, native_interval_minutes)
    new_temp = resample_to_5min(raw_temp, native_interval_minutes)

    ts = pd.date_range(start='1/1/2018 00:00 am', periods=len(new_ghi), freq='5min')
    d = {'Time': ts, 'GHI(W/m^2)': new_ghi.flatten(), 'Temp(C)': new_temp.flatten()}
    pd.DataFrame(data=d).to_csv(new_file_path, index=False)


def increase_co2_res(raw_vec: ndarray, interpolate=True):
    """
    This method increases the 1-hour resolution of NREL's Cambium CO2 emissivity (kg CO2/MWh) data into a 5-minute
    resolution. The raw profiles are hour-beginning.

    Parameters
    ----------
    raw_vec : ndarray
        A numpy array of raw grid CO2 emissivity data from NREL's Cambium database.
    interpolate : bool, optional
        Whether to interpolate between 1 hour points or just repeat the value 12 times. Default is True.

    Returns
    -------
    comb : ndarray
        A new numpy array for CO2 emissivity in 5-min resolution.
    """
    # This inputs the cambium kg/MWh data numpy array (raw) with 1 hr resolution and converts it to an array
    # corresponding to kg/kWh with 5 minute resolution. If interpolate is set to false, then data points are repeated
    # 12 times per hour

    # extract vector length and convert shape to 1D from 0D
    num = raw_vec.shape[0]
    raw_vec = raw_vec.reshape((num, 1))

    # evaluate intermediate values between values
    vec0 = np.vstack((raw_vec[1:], raw_vec[0]))  # raw vector with last value appended to front (for calculations)
    shift = vec0 - raw_vec
    comb = raw_vec
    if interpolate:
        for i in range(1, 12):
            comb = np.hstack((comb, raw_vec + (i / 12) * shift))
    else:
        for i in range(1, 12):
            comb = np.hstack((comb, raw_vec))

    # combine intermediate vector with adjusted raw vector, and then flatten into 1D array
    comb = comb.reshape((comb.size, 1))

    return comb


CAMBIUM_EMISSION_COLUMNS = ['aer_gen_co2e', 'co2_rate_avg_gen']  # Cambium 2021+, Cambium 2020


def cambium_release(file_path: str) -> str:
    """
    Returns the Cambium release year (eg '2020', '2021') from the 'Project' metadata row of a raw Cambium csv
    (eg 'Standard_scenarios_2020'), or '' if it can't be determined.
    """
    with open(file_path, 'r') as f:
        keys = f.readline().strip().split(',')
        values = f.readline().strip().split(',')
    project = dict(zip(keys, values)).get('Project', '')
    return project.rsplit('_', 1)[-1] if project[-4:].isdigit() else ''


def process_cambium(old_file_path: str, new_file_path: str):
    """
    This method processed raw Cambium data files with 1 hour resolution into a new file with 5-min resolution.

    Parameters
    ----------
    old_file_path : str
        Filepath of the csv file to be processed.
    new_file_path : str
        Filepath of the newer processed csv file.
    Returns
    -------
    None

    Notes
    -----
    -   The column header row and average emission rate column differ by Cambium release: 2021+ files have the
        header on line 5 and use 'aer_gen_co2e', while 2020 files have it on line 3 and use 'co2_rate_avg_gen'.
        Both are kg/MWh.
    """
    with open(old_file_path, 'r') as f:
        for header_row, line in enumerate(f):
            if line.startswith('timestamp,'):
                columns = line.strip().split(',')
                break
        else:
            raise ValueError(f'No "timestamp" header row found in {old_file_path}')
    emission_col = next((c for c in CAMBIUM_EMISSION_COLUMNS if c in columns), None)
    if emission_col is None:
        raise ValueError(f'None of {CAMBIUM_EMISSION_COLUMNS} found in {old_file_path}')

    raw_profile = pd.read_csv(old_file_path, usecols=['timestamp_local', emission_col], header=header_row)
    raw_emissions = raw_profile[emission_col].to_numpy() / 1000
    new_emissions = increase_co2_res(raw_emissions)
    d = {'Emissivity': new_emissions.flatten()}
    pd.DataFrame(data=d).to_csv(new_file_path, index=False)


LBS_CO2_PER_MWH_TO_KG_CO2_PER_KWH = 0.45359237 / 1000  # 1 lb = 0.45359237 kg; /1000 converts MWh basis to kWh


def process_wattime_profile(raw_file_path: str, new_file_path: str, year: int, time_adjust: int = 0):
    """
    Converts one calendar year of raw WattTime co2_moer/co2_aoer data (UTC timestamps, lbs CO2/MWh, already
    ~5-min native resolution) into the model's Emissivity (kg CO2/kWh) format.

    Parameters
    ----------
    raw_file_path : str
        Filepath of the raw csv (columns 'point_time', 'value') saved by fetch_wattime_historical.
    new_file_path : str
        Filepath of the new processed csv.
    year : int
        Calendar year the raw data covers -- used to build the complete UTC 5-min grid it's reindexed onto.
    time_adjust : int, optional
        Hours to shift the profile forward (+) or backward (-) by, same convention as process_NSRDB_profile.
        Default is 0.

    Returns
    -------
    None

    Notes
    -----
    -   WattTime's historical archive can have small gaps (eg, brief source-data outages), so the raw series is
        reindexed onto a complete 5-min grid for the year and short gaps are linearly interpolated (longer gaps
        at the very start/end of the year are forward/back-filled) rather than left as NaN.
    """
    raw = pd.read_csv(raw_file_path, parse_dates=['point_time'])
    raw = raw.drop_duplicates('point_time').set_index('point_time').sort_index()

    full_index = pd.date_range(start=f'{year}-01-01', periods=105120, freq='5min', tz='UTC')
    series = raw['value'].reindex(full_index).interpolate(limit=6).ffill().bfill()

    kg_per_kwh = (series.to_numpy() * LBS_CO2_PER_MWH_TO_KG_CO2_PER_KWH).reshape((-1, 1))
    shift = 12 * time_adjust  # WattTime data is already 5-min resolution (12 steps/hour)
    kg_per_kwh = np.vstack((kg_per_kwh[shift:], kg_per_kwh[0:shift]))

    pd.DataFrame({'Emissivity': np.round(kg_per_kwh.flatten(), 4)}).to_csv(new_file_path, index=False)


def shift_cambium(emissions_profile: ndarray, target_year=2018) -> ndarray:
    """
    All cambium profiles are made to start in Sunday. Thus, to align with simulations, we need to shift the year.
    This script utilizes the pd.Timestamp method, which considers Monday to be day 0 of the week (Tuesday=1, etc.)
    Parameters
    ----------
    emissions_vector: ndarray
        The vector representing grid emissivity (kgCO2/kWh) that needs to be shifted in line with simulation year
    target_year: int
        The year of the simulation to which the cambium profile needs to be shifted.


    Returns
    -------
    shifted_profile: ndarray
        The shift cambium profile for use in simulation
    """
    target_stamp = pd.Timestamp(year=target_year, month=1, day=1)
    target_dow = target_stamp.day_of_week
    cambium_dow = 6  # cambium profiles start on Sunday, which Timestamp treats as the number 7)
    shift = target_dow - cambium_dow
    shift = min(shift, 7 - (cambium_dow - target_dow), key=lambda x: abs(x))  # minimum delta between shift forward or
    # backward.

    shifted_profile = shift_by_day(profile=emissions_profile,days = shift)
    return shifted_profile

def v2h_summary(v2h_arr: np.ndarray, resolution=.25, upper_lim=15, timestep=5):
    factor = timestep/60
    limits = np.arange(start=0, stop=upper_lim+resolution, step=resolution)
    limits = limits.reshape((len(limits), 1))
    subtotals = np.zeros(shape=(len(limits), 1))
    for i in range(len(limits)):
        e_lim = limits[i] * factor
        if i == len(limits) - 1:
            subtotals[i] = np.sum(v2h_arr[(v2h_arr >= e_lim)])
        else:
            upper = limits[i+1] * factor
            subtotals[i] = np.sum(v2h_arr[(v2h_arr >= e_lim) & (v2h_arr < upper)])
    return subtotals


# ----- USURDB Tariff Processing -----
# The functions below consolidate parsing logic that used to be duplicated (nearly line-for-line) across
# 'Scripts/Zip and Utility Directory/create_utility_files.py' and 'Scripts/Zip and Utility Directory/processTariffs.py'. Both scripts walk a raw
# USURDB tariff export (the same format returned live by usurdb_read.api_read) and turn its
# 'energyratestructure'/'demandratestructure'/'flatdemandstructure' columns into the nested
# [[[limit, rate], ...], ...] per-period tier lists used by the model's 'Utilities/*_tariffs.csv' files.

def _walk_usurdb_rate_tiers(row: pd.Series, root: str, period: int) -> list:
    # Walks the tiers of a single rate period (root='energyratestructure', 'demandratestructure', or
    # 'flatdemandstructure'), returning a list of [limit, rate] pairs, one per tier.
    tiers = []
    tier = 0
    more_tiers = True
    while more_tiers:
        rate_col = f'{root}/period{period}/tier{tier}rate'
        rate = row[rate_col]

        limit_col = f'{root}/period{period}/tier{tier}max'
        if limit_col in row.index:
            limit = row[limit_col]
            if pd.isna(limit):
                limit = -1
                more_tiers = False
        else:
            limit = -1

        adj_col = f'{root}/period{period}/tier{tier}adj'
        if adj_col in row.index:
            adj = row[adj_col]
            if pd.isna(adj):
                adj = 0
        else:
            adj = 0

        tiers.append([limit, rate + adj])
        tier += 1
        next_rate_col = f'{root}/period{period}/tier{tier}rate'
        # a missing column means there is no next tier, same as a present-but-empty one -- treat both as "stop"
        # instead of a raw row[...] lookup, which would KeyError on a genuinely missing column (this is the fix
        # for a latent crash shared by the original create_utility_files.py/processTariffs.py implementations:
        # an uncapped final tier (tier{n}max present but NaN) followed by no tier{n+1} columns at all).
        if pd.isna(row.get(next_rate_col, np.nan)):
            more_tiers = False
    return tiers


def parse_usurdb_rate_structure(row: pd.Series, root: str) -> list:
    """
    Parses a tiered rate structure out of a raw USURDB tariff export row into the nested
    [[[limit, rate], ...], ...] format (one sublist per period, each a list of [limit, rate] tiers) used by the
    'Time-of-Use Rates'/'Demand Rates' columns of the model's per-utility tariff files.

    Parameters
    ----------
    row : pd.Series
        A single row from a raw USURDB export (eg, from usurdb_read.api_read, or a bulk-downloaded tariff list).
    root : str
        Column-name prefix for the rate structure being parsed: 'energyratestructure', 'demandratestructure',
        or 'flatdemandstructure'.

    Returns
    -------
    list
        List of periods, each a list of [limit, rate] tiers.
    """
    periods = []
    period = 0
    while True:
        periods.append(_walk_usurdb_rate_tiers(row, root, period))
        period += 1
        next_rate_col = f'{root}/period{period}/tier0rate'
        if pd.isna(row.get(next_rate_col, np.nan)):
            break
    return periods


def usurdb_row_to_tariff_fields(row: pd.Series) -> dict:
    """
    Converts a single row of a raw USURDB tariff export into the fields used by a row of a per-utility tariff
    file (Utilities/{Utility}_{EIA}_tariffs.csv), other than the identifying columns (Name/OpenEI Id/etc), which
    differ depending on the source of the row and are left to the caller.

    Parameters
    ----------
    row : pd.Series
        A single row from a raw USURDB export (eg, from usurdb_read.api_read, or a bulk-downloaded tariff list).
        Must contain 'energyweekdayschedule'/'energyweekendschedule' and the corresponding
        'energyratestructure/...' columns; demand/flat-demand columns are optional.

    Returns
    -------
    dict
        Dict with keys TimeOfUse, Tiered, Demand, Monthly Charge, Minimum Charge, Time-of-Use Rates,
        Weekday Schedule - Energy, Weekend Schedule - Energy, Demand Rates, Weekday Schedule - Power,
        Weekend Schedule - Power -- ready to be combined with the row's Name/OpenEI Id and appended to a
        per-utility tariff file.
    """
    weekday_schedule = np.array(eval(str(row['energyweekdayschedule']).replace('L', ''))).tolist()
    weekend_schedule = np.array(eval(str(row['energyweekendschedule']).replace('L', ''))).tolist()

    is_tou = max(np.diff(np.sort(weekday_schedule, axis=0) != 0).sum(axis=0)) > 1
    is_tiered = (not pd.isna(row.get('energyratestructure/period0/tier1rate'))) or \
               (not pd.isna(row.get('energyratestructure/period1/tier1rate')))
    is_demand_flat = not pd.isna(row.get('flatdemandstructure/period0/tier0rate'))
    is_demand_rated = not pd.isna(row.get('demandratestructure/period0/tier0rate'))
    is_demand = is_demand_flat or is_demand_rated

    fixed_charge = row.get('fixedchargefirstmeter')
    fixed_charge = 0 if pd.isna(fixed_charge) else fixed_charge

    min_charge = row.get('mincharge')
    min_charge = 0 if pd.isna(min_charge) else min_charge

    if is_demand:
        if is_demand_flat:
            root = 'flatdemandstructure'
            months = ['jan', 'feb', 'mar', 'apr', 'may', 'jun', 'jul', 'aug', 'sep', 'oct', 'nov', 'dec']
            monthly = [row[f'flatDemandMonth_{month}'] for month in months]
            weekday_schedule_demand = np.tile(monthly, (24, 1)).transpose().tolist()
            weekend_schedule_demand = weekday_schedule_demand
        else:
            root = 'demandratestructure'
            weekday_schedule_demand = np.array(eval(str(row['demandweekdayschedule']).replace('L', ''))).tolist()
            weekend_schedule_demand = np.array(eval(str(row['demandweekendschedule']).replace('L', ''))).tolist()
        demand_rates = parse_usurdb_rate_structure(row, root)
    else:
        weekday_schedule_demand = []
        weekend_schedule_demand = []
        demand_rates = []

    energy_rates = parse_usurdb_rate_structure(row, 'energyratestructure')

    return {
        'TimeOfUse': is_tou,
        'Tiered': is_tiered,
        'Demand': is_demand,
        'Monthly Charge': fixed_charge,
        'Minimum Charge': min_charge,
        'Time-of-Use Rates': str(energy_rates),
        'Weekday Schedule - Energy': str(weekday_schedule).replace('\n', ', '),
        'Weekend Schedule - Energy': str(weekend_schedule).replace('\n', ', '),
        'Demand Rates': str(demand_rates),
        'Weekday Schedule - Power': str(weekday_schedule_demand).replace('\n', ', '),
        'Weekend Schedule - Power': str(weekend_schedule_demand).replace('\n', ', '),
    }


def append_tariff_row(util_file_path: str, row_dict: dict, save: bool = True) -> pd.DataFrame:
    """
    Appends a single tariff row (as produced by usurdb_row_to_tariff_fields, combined with identifying fields
    such as Name/OpenEI Id) to a per-utility tariff CSV, creating the file if it doesn't already exist and
    updating the existing row in place if a tariff of the same Name is already present.

    Parameters
    ----------
    util_file_path : str
        Full path (eg, 'Utilities/Georgia Power Co_7140_tariffs.csv') of the per-utility tariff file to update.
    row_dict : dict
        Dict of column-value pairs for the tariff row, including 'Name'.
    save : bool, optional
        Whether to write the updated frame back to util_file_path. Default is True.

    Returns
    -------
    pd.DataFrame
        The updated tariff frame for this utility.
    """
    if os.path.exists(util_file_path):
        util_frame = pd.read_csv(util_file_path)
    else:
        util_frame = pd.DataFrame(columns=list(row_dict.keys()))

    existing = util_frame.index[util_frame['Name'] == row_dict['Name']] if 'Name' in util_frame.columns else []
    if len(existing) > 0:
        for col, val in row_dict.items():
            util_frame.loc[existing, col] = val
    else:
        new_row = pd.DataFrame(data=row_dict, index=[len(util_frame)])
        util_frame = pd.concat([util_frame, new_row], ignore_index=True)

    if save:
        util_frame.to_csv(util_file_path, index=False)

    return util_frame


# ----- Zip/Utility Directory Maintenance -----
# The functions below consolidate the multi-stage pipeline that builds the model's zip/utility reference tables
# (Model Data/util_to_zip_fixed.csv, Model Data/zip_to_util_fixed.csv, Model Data/new_zip_directory.csv), which
# previously lived as four separate scripts (Scripts/Zip and Utility Directory/fix_util_names.py, fix_zip_to_util.py,
# create_zip_directory.py, and root/scrape_zip_website.py) that each wrote their output to the wrong (cwd-
# relative) location instead of Model Data/, requiring a manual copy step. This also fixes a latent bug in the
# original fix_zip_to_util.py, where an unmatched EIA code left a stale index from a previous loop iteration in
# use instead of being skipped.

def fix_utility_names(raw_util_to_zip_path: str = 'Archive/DataFiles/util_to_zip.csv',
                      out_path: str = 'Model Data/util_to_zip_fixed.csv', log=print) -> pd.DataFrame:
    """
    Fixes utility names of the form 'X City of' -> 'City of X' in a raw util_to_zip export (mirrors
    Scripts/Zip and Utility Directory/fix_util_names.py). Any columns already present in an existing out_path beyond what the
    raw export has (eg, the model's hand-curated 'Avoided Cost Rate'/'Net Meter Adder'/'Net Meter
    Policy'/'Re-up Freq'/'NBC' columns) are preserved by merging them back in on EIA Code, since a refresh
    shouldn't discard manually-entered data.
    """
    util_list = pd.read_csv(raw_util_to_zip_path, dtype={'EIA Code': str})
    fixed = 0
    for i in range(len(util_list)):
        name = util_list.loc[i, 'Utility Name']
        name_split = name.split(' ')
        if name_split[-1] == 'of':
            re_order = name_split[-2:] + name_split[:-2]
            util_list.loc[i, 'Utility Name'] = ' '.join(re_order)
            fixed += 1

    if os.path.exists(out_path):
        existing = pd.read_csv(out_path, dtype={'EIA Code': str})
        extra_cols = [c for c in existing.columns if c not in util_list.columns]
        if extra_cols:
            util_list = util_list.merge(existing[['EIA Code'] + extra_cols], on='EIA Code', how='left')

    util_list.to_csv(out_path, index=False)
    log(f'Fixed {fixed} utility name(s); wrote {out_path}')
    return util_list


def fix_zip_to_util(raw_zip_to_util_path: str = 'Archive/DataFiles/zip_to_util.csv',
                    util_to_zip_fixed_path: str = 'Model Data/util_to_zip_fixed.csv',
                    out_path: str = 'Model Data/zip_to_util_fixed.csv', log=print) -> pd.DataFrame:
    """
    Zero-pads zip codes and re-resolves utility names via the fixed util_to_zip file (mirrors
    Scripts/Zip and Utility Directory/fix_zip_to_util.py).
    """
    zip_frame = pd.read_csv(raw_zip_to_util_path, dtype={'Zip Code': str},
                            converters={'EIA Codes': ast.literal_eval})
    util_frame = pd.read_csv(util_to_zip_fixed_path, dtype={'EIA Code': str})
    eia_to_name = util_frame.set_index('EIA Code')['Utility Name'].to_dict()

    unmatched = []
    for i in range(len(zip_frame)):
        zip_code = zip_frame.loc[i, 'Zip Code']
        if len(zip_code) < 5:
            zip_code = zip_code.zfill(5)
            zip_frame.loc[i, 'Zip Code'] = zip_code

        util_list = []
        eia_new_list = []
        for eia in zip_frame.loc[i, 'EIA Codes']:
            eia = eia.replace('.', '')
            if eia in eia_new_list:
                continue
            eia_new_list.append(eia)
            if eia in eia_to_name:
                util_list.append(eia_to_name[eia])
            else:
                unmatched.append((zip_code, eia))
        zip_frame.at[i, 'Utilities'] = util_list
        zip_frame.at[i, 'EIA Codes'] = eia_new_list

    zip_frame.to_csv(out_path, index=False)
    log(f'Resolved utilities for {len(zip_frame)} zip code(s); {len(unmatched)} EIA code(s) had no matching '
       f'utility. Wrote {out_path}')
    return zip_frame


def build_zip_directory(location_source_path: str = 'Archive/DataFiles/zipCodes2.csv',
                        zip_to_util_fixed_path: str = 'Model Data/zip_to_util_fixed.csv',
                        out_path: str = 'Model Data/new_zip_directory.csv', zero_pad_output: bool = False,
                        log=print) -> pd.DataFrame:
    """
    Builds the zip directory (location + serving utilities per zip code) that the model actually reads
    (Setup.py loads Model Data/new_zip_directory.csv). Any Time Zone/Population/Area (sq mi) columns already
    present in an existing out_path are preserved by merging them back in, since those come from a much slower
    separate enrichment step (see enrich_zip_directory) that a directory refresh shouldn't discard. Mirrors
    Scripts/Zip and Utility Directory/create_zip_directory.py.

    Notes
    -----
    -   zero_pad_output defaults to False to match the zip-code format already in the live
        Model Data/new_zip_directory.csv (eg, '1001' rather than '01001' for Agawam, MA), which is what
        Setup.create_city's lookup currently expects since it does not zero-pad its own input. This looks like
        an accidental loss of leading zeros somewhere upstream (zip_to_util_fixed.csv IS zero-padded), which
        would silently break zip lookups for any zip code starting with 0 (New England, NJ, Puerto Rico) if a
        user supplies a properly zero-padded zip code in an input file. Fixing that properly means also
        zero-padding the input to Setup.create_city -- flagged here rather than changed unprompted since it's
        outside the scope of this refresh pipeline.
    """
    zip_location = pd.read_csv(location_source_path, dtype={'postal code': str}).set_index('postal code')
    zip_util = pd.read_csv(zip_to_util_fixed_path, dtype={'Zip Code': str},
                           converters={'Utilities': ast.literal_eval, 'EIA Codes': ast.literal_eval})

    rows = []
    missing_zips = []
    for i in range(len(zip_util)):
        zip_code = zip_util.loc[i, 'Zip Code']
        if zip_code not in zip_location.index:
            missing_zips.append(zip_code)
            continue
        loc = zip_location.loc[zip_code]
        if isinstance(loc, pd.DataFrame):  # a zip code can appear more than once (eg, multiple localities)
            loc = loc.iloc[0]
        zip_code_out = zip_code if zero_pad_output else str(int(zip_code))
        rows.append({'Zip Code': zip_code_out, 'City': loc['place'], 'State': loc['state'],
                    'State (Abbr)': loc['statecode'], 'County': loc['province_or_county'],
                    'Latitude': loc['latitude'], 'Longitude': loc['longitude'],
                    'Utilities': zip_util.loc[i, 'Utilities'], 'EIA Codes': zip_util.loc[i, 'EIA Codes']})

    zip_directory = pd.DataFrame(rows)

    if os.path.exists(out_path):
        existing = pd.read_csv(out_path, dtype={'Zip Code': str})
        enrich_cols = [c for c in ['Time Zone', 'Population', 'Area (sq mi)'] if c in existing.columns]
        if enrich_cols:
            zip_directory = zip_directory.merge(existing[['Zip Code'] + enrich_cols], on='Zip Code', how='left')

    zip_directory.to_csv(out_path, index=False)
    log(f'Built directory for {len(zip_directory)} zip code(s); {len(missing_zips)} had no location match. '
       f'Wrote {out_path}')
    return zip_directory


def enrich_zip_directory(zip_directory_path: str = 'Model Data/new_zip_directory.csv', save_interval: int = 500,
                         cancel_check=None, log=print) -> pd.DataFrame:
    """
    Fills in Time Zone/Population/Area (sq mi) for every zip code in the directory that doesn't have them yet by
    scraping zipdatamaps.com per zip code (mirrors scrape_zip_website.py). Only rows missing 'Population' are
    fetched, so this is safe to stop and re-run -- already-populated rows are skipped on the next pass.

    Parameters
    ----------
    zip_directory_path : str, optional
        Path to the zip directory csv to enrich in place.
    save_interval : int, optional
        How often (in zip codes processed) to checkpoint-save progress to disk. Default is 500.
    cancel_check : callable, optional
        A no-argument callable returning True if the operation should stop early (eg, a threading.Event's
        is_set). Checked between zip codes.
    log : callable, optional
        Callback for progress messages.
    """
    zip_directory = pd.read_csv(zip_directory_path, dtype={'Zip Code': str})
    for col in ['Time Zone', 'Population', 'Area (sq mi)']:
        if col not in zip_directory.columns:
            zip_directory[col] = np.nan

    todo = zip_directory.index[pd.isna(zip_directory['Population'])]
    log(f'{len(todo)} of {len(zip_directory)} zip code(s) still need Time Zone/Population/Area data')

    filled = 0
    errors = []
    for count, i in enumerate(todo):
        if cancel_check is not None and cancel_check():
            log('Cancelled.')
            break
        zip_code = zip_directory.loc[i, 'Zip Code']
        try:
            zip_dict = zip_scrape(zip_code=zip_code)
            zip_directory.loc[i, 'Time Zone'] = zip_dict['Time Zone']
            zip_directory.loc[i, 'Population'] = zip_dict['Population']
            zip_directory.loc[i, 'Area (sq mi)'] = zip_dict['Area']
            filled += 1
        except (IndexError, KeyError, ValueError, requests.exceptions.SSLError):
            errors.append(zip_code)
        time.sleep(.05)
        if (count + 1) % save_interval == 0:
            zip_directory.to_csv(zip_directory_path, index=False)
            log(f'  ...{count + 1}/{len(todo)} processed, {filled} filled so far (checkpoint saved)')

    zip_directory.to_csv(zip_directory_path, index=False)
    log(f'Done: filled {filled} zip code(s); {len(errors)} error(s)'
       + (f' (eg, {errors[:10]})' if errors else ''))
    return zip_directory


def refresh_zip_utility_directories(cancel_check=None, log=print) -> None:
    """Runs the fast (no-network) stage of the directory refresh pipeline: fix_utility_names -> fix_zip_to_util
    -> build_zip_directory. Does not include enrich_zip_directory, which makes a slow, separate per-zip-code
    network call and is intended to be run/resumed independently."""
    fix_utility_names(log=log)
    fix_zip_to_util(log=log)
    build_zip_directory(log=log)
