"""
Data Import Wizard
-------------------
A single Tkinter hub for importing, processing, and examining the raw datasets that feed HouseholdSim: solar
irradiance (NSRDB), house load profiles (NREL ResStock), utility/zip reference directories and tariffs
(USURDB), and grid CO2 intensity (NREL Cambium). Each tab wraps logic that previously only existed as standalone
scripts (under 'Scripts/' and the former repo root) with hardcoded, machine-specific paths, so
imports/processing/examination can happen from one place with normal dropdowns instead of editing script
constants by hand.

Run this file directly (it must be run from the repository root, same as runScenarioFiles.py/ResultsGUI.py).
"""
import os
import ast
import io
import json
import time
import threading
import queue
import traceback
from pathlib import Path
from tkinter import *
from tkinter import ttk, filedialog, messagebox, scrolledtext

import numpy as np
import pandas as pd
import requests

import matplotlib
matplotlib.use('TkAgg')
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

import DataProcessing as dp
import usurdb_read as ur
import pandastable as pdt
import gui_common
from gui_common import FONT_FAMILY, PALETTE, configure_style, CancelToken, ThreadedLog, list_files, list_subdirs

# ----------------------------- Paths & Constants -----------------------------

CITY_LIST_PATH = 'Model Data/city_list.csv'
STATES_PATH = 'Model Data/states.csv'
UTIL_TO_ZIP_PATH = 'Model Data/util_to_zip_fixed.csv'
ZIP_DIRECTORY_PATH = 'Model Data/new_zip_directory.csv'
SOLAR_DIR = 'City Data/Solar Data'
SOLAR_RAW_DIR = 'City Data/Solar Data/Raw'
LOAD_PARQUET_RAW_DIR = 'City Data/Load Profiles/Unprocessed/Parquets'
LOAD_PARQUET_PROCESSED_DIR = 'City Data/Load Profiles/Processed/Parquets'
CAMBIUM_PROCESSED_DIR_TEMPLATE = 'City Data/CO2 Profiles/Cambium {release}/Processed'
CAMBIUM_PROCESSED_DIR = CAMBIUM_PROCESSED_DIR_TEMPLATE.format(release='2021')
WATTTIME_RAW_DIR = 'City Data/CO2 Profiles/WattTime/Raw'
WATTTIME_PROCESSED_DIR = 'City Data/CO2 Profiles/WattTime/Processed'
UTILITIES_DIR = 'Utilities'
RESSTOCK_METADATA_PATH = 'Archive/DataFiles/baseline_metadata_and_annual_results_simp.csv'
RESSTOCK_BASE_URL = ('https://oedi-data-lake.s3.amazonaws.com/nrel-pds-building-stock/'
                      'end-use-load-profiles-for-us-building-stock/2022/resstock_amy2018_release_1/'
                      'timeseries_individual_buildings/by_state/upgrade=')
ACCEPTABLE_HOUSE_TYPES = ['Single-Family Detached', 'Single-Family Attached']
USURDB_TARIFF_URL = 'https://apps.openei.org/USURDB/rate/view/'
IURDB_TARIFF_URL = 'https://apps.openei.org/IURDB/rate/view/'

# NSRDB moved from developer.nrel.gov to developer.nlr.gov; the four datasets below are the current (v4) GOES-
# based ones covering the Americas -- see https://developer.nlr.gov/docs/solar/nsrdb/. NSRDB also publishes
# Himawari (Asia-Pacific), Meteosat (Europe/Africa/Middle East/India), Polar, and SUNY International datasets,
# left out here since this tool's reference cities are all US-based; the same pattern extends to those if
# ever needed.
NSRDB_BASE_URL = 'https://developer.nlr.gov/api/nsrdb/v2/solar/'
NSRDB_DATASETS = {
    'goes_conus_v4': {
        'label': 'GOES Conus (v4) -- 5 min, CONUS, 2018-2024',
        'endpoint': 'nsrdb-GOES-conus-v4-0-0-download',
        'native_interval_minutes': 5,
        'coverage': 'Continental US',
        'names': [str(y) for y in range(2018, 2025)],
    },
    'goes_full_disc_v4': {
        'label': 'GOES Full Disc (v4) -- 10 min, all GOES regions, 2018-2024',
        'endpoint': 'nsrdb-GOES-full-disc-v4-0-0-download',
        'native_interval_minutes': 10,
        'coverage': 'All regions covered by GOES (broader than CONUS)',
        'names': [str(y) for y in range(2018, 2025)],
    },
    'goes_aggregated_v4': {
        'label': 'GOES Aggregated (v4) -- 30 min, GOES East & West, 1998-2024',
        'endpoint': 'nsrdb-GOES-aggregated-v4-0-0-download',
        'native_interval_minutes': 30,
        'coverage': 'GOES East & West',
        'names': [str(y) for y in range(1998, 2025)],
    },
    'goes_tmy_v4': {
        'label': 'GOES TMY (v4) -- hourly, typical-year products',
        'endpoint': 'nsrdb-GOES-tmy-v4-0-0-download',
        'native_interval_minutes': 60,
        'coverage': 'GOES-covered regions',
        'names': ['tmy', 'tmy-2022', 'tdy-2022', 'tgy-2022', 'tmy-2023', 'tdy-2023', 'tgy-2023',
                  'tmy-2024', 'tdy-2024', 'tgy-2024'],
    },
}
DEFAULT_NSRDB_DATASET = 'goes_conus_v4'
DEFAULT_NSRDB_NAME = '2018'  # Simulation.make_pv prefers '..._GHI_2018_5min.csv' (matches the AMY2018 loads) --
                             # see the note on download_and_process_solar_city.
NSRDB_CREDENTIALS_PATH = 'nsrdb_credentials.json'  # gitignored -- holds a personal API key/email, not a secret
                                                   # anyone else should see

# WattTime v3 API (grid CO2 -- see https://www.watttime.org/). co2_moer is the marginal emissions rate (CO2
# impact of a change in load, eg EV charging/DER decisions); co2_aoer is the average emissions rate of the
# whole generation mix, the closer analogue to Cambium's data. Both are reported in lbs CO2/MWh.
WATTTIME_BASE_URL = 'https://api.watttime.org'
WATTTIME_SIGNAL_TYPES = {
    'co2_moer': {'label': 'Marginal (MOER) -- CO2 impact of a change in load, eg EV charging/DER decisions'},
    'co2_aoer': {'label': 'Average (AOER) -- CO2 intensity of the whole generation mix, comparable to Cambium'},
}
DEFAULT_WATTTIME_SIGNAL = 'co2_moer'
WATTTIME_CREDENTIALS_PATH = 'wattime_credentials.json'  # gitignored -- holds a personal username/password, not
                                                        # a secret anyone else should see

# ----------------------------- Look & Feel -----------------------------
# FONT_FAMILY, PALETTE, configure_style now live in gui_common.py (imported above), shared with
# ResultsGUI.py and InputBuilderWizard.py so all three GUIs stay visually consistent.


# ----------------------------- Solar (NSRDB REST API) worker functions -----------------------------
# NSRDB now serves data through developer.nlr.gov's REST API (see NSRDB_DATASETS above) rather than the older
# developer.nrel.gov PSM3 endpoint. For a single point + single year/name, the .csv endpoint responds directly
# and synchronously (no async job/polling), so a single request is enough per city.

def load_nsrdb_credentials_from(path: str) -> dict:
    """Returns {'api_key':..., 'email':...} from an arbitrary credentials json file, or {} if missing/invalid."""
    if os.path.exists(path):
        try:
            with open(path) as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def load_nsrdb_credentials() -> dict:
    """Returns {'api_key':..., 'email':...} from NSRDB_CREDENTIALS_PATH (the default, shared-machine
    credentials file), or {} if none saved yet."""
    return load_nsrdb_credentials_from(NSRDB_CREDENTIALS_PATH)


def save_nsrdb_credentials(api_key: str, email: str) -> None:
    """Saves an NSRDB API key/email locally so future wizard sessions default to it. NSRDB_CREDENTIALS_PATH is
    gitignored -- this is a personal credential, not something to commit."""
    with open(NSRDB_CREDENTIALS_PATH, 'w') as f:
        json.dump({'api_key': api_key, 'email': email}, f)


def fetch_nsrdb_csv(dataset_key: str, name: str, lat: float, lon: float, api_key: str, email: str) -> pd.DataFrame:
    """
    Fetches one point-year (or point-TMY) of raw NSRDB data via the REST API at its native resolution. Returns
    a DataFrame with 'GHI(W/m^2)' and 'Temp(C)' columns.

    Notes
    -----
    -   NSRDB's PSM-format CSV responses carry two metadata rows (field names, then field values) before the
        real column-header row, so those are skipped. Column names are matched case-insensitively/by substring
        ('ghi', 'temp') rather than an exact literal name, since the precise wording isn't guaranteed to be
        identical across dataset versions and this couldn't be verified against a live response while building
        this (no working API key/network access at the time) -- if this ever fails to find a column, the error
        message includes the actual columns seen so it's easy to diagnose.
    """
    dataset = NSRDB_DATASETS[dataset_key]
    url = NSRDB_BASE_URL + dataset['endpoint'] + '.csv'
    params = {
        'wkt': f'POINT({lon} {lat})',
        'attributes': 'ghi,air_temperature',
        'names': name,
        'interval': dataset['native_interval_minutes'],
        'email': email,
        'api_key': api_key,
    }
    response = requests.get(url, params=params)
    if response.status_code != 200:
        raise Exception(f'NSRDB request failed ({response.status_code}): {response.text[:500]}')

    raw = pd.read_csv(io.StringIO(response.text), skiprows=2)
    ghi_col = next((c for c in raw.columns if 'ghi' in c.lower()), None)
    temp_col = next((c for c in raw.columns if 'temp' in c.lower()), None)
    if ghi_col is None or temp_col is None:
        raise Exception(f'Could not find GHI/Temperature columns in the NSRDB response. Columns seen: '
                        f'{list(raw.columns)}')

    return pd.DataFrame({'GHI(W/m^2)': raw[ghi_col].astype(float), 'Temp(C)': raw[temp_col].astype(float)})


def download_and_process_solar_city(state: str, city: str, dataset_key: str, name: str, api_key: str, email: str,
                                    log=print) -> str:
    """
    Pulls raw GHI/temperature for one reference city from the chosen NSRDB dataset, then resamples it to the
    model's 5-min, UTC-adjusted format regardless of that dataset's native resolution.

    Notes
    -----
    -   Simulation.make_pv (via reference_solar_file) auto-loads '{state}_{city}_GHI_2018_5min.csv', the weather
        year behind the AMY2018 house loads, and otherwise falls back to the latest non-leap year on disk. Leap
        years and TMY vintages are never auto-loaded; using them requires the 'Other Solar File' input.
    """
    if not (api_key and email):
        raise Exception('An NSRDB API key and email are required (request a free key at developer.nlr.gov).')

    city_frame = pd.read_csv(CITY_LIST_PATH)
    sub = city_frame[(city_frame['State'] == state) & (city_frame['City'] == city)]
    if sub.empty:
        raise Exception(f'{city}, {state} not found in {CITY_LIST_PATH}.')
    row = sub.iloc[0]
    time_adjust = -1 * int(row['Off UTC'])

    dataset = NSRDB_DATASETS[dataset_key]
    raw_df = fetch_nsrdb_csv(dataset_key, name, row['Latitude'], row['Longitude'], api_key, email)

    raw_dir = os.path.join(SOLAR_RAW_DIR, state)
    os.makedirs(raw_dir, exist_ok=True)
    raw_path = os.path.join(raw_dir, f'{state}_{city}_GHI_{name}_{dataset_key}.csv')
    raw_df.to_csv(raw_path, index=False)

    out_dir = os.path.join(SOLAR_DIR, state)
    os.makedirs(out_dir, exist_ok=True)
    new_path = os.path.join(out_dir, f'{state}_{city}_GHI_{name}_5min.csv')
    if os.path.exists(new_path):
        log(f'  note: overwriting existing {os.path.basename(new_path)} with {dataset["label"]} data')
    dp.process_NSRDB_profile(raw_path, new_path, time_adjust,
                             native_interval_minutes=dataset['native_interval_minutes'])
    log(f'{city}, {state}: wrote {new_path} ({dataset["label"]})')
    return new_path


def bulk_download_solar(dataset_key: str, name: str, api_key: str, email: str, state_filter: str = None,
                        skip_existing: bool = True, cancel_check=None, log=print) -> None:
    """Runs download_and_process_solar_city for every reference city in city_list.csv (optionally scoped to one
    state), skipping cities that already have a processed file for this name by default."""
    city_frame = pd.read_csv(CITY_LIST_PATH)
    if state_filter:
        city_frame = city_frame[city_frame['State'] == state_filter]
    total = len(city_frame)
    done = 0
    skipped = 0
    for _, row in city_frame.iterrows():
        if cancel_check is not None and cancel_check():
            log('Cancelled.')
            break
        state, city = row['State'], row['City']
        out_path = os.path.join(SOLAR_DIR, state, f'{state}_{city}_GHI_{name}_5min.csv')
        if skip_existing and os.path.exists(out_path):
            skipped += 1
            continue
        try:
            download_and_process_solar_city(state, city, dataset_key, name, api_key, email, log=log)
            done += 1
        except Exception as ex:
            log(f'  ERROR for {city}, {state}: {ex}')
    log(f'Bulk solar update: processed {done} of {total} city(s) ({skipped} already up to date).')


# ----------------------------- House Load (ResStock) worker functions -----------------------------

def download_resstock_city(state: str, city: str, upgrade_levels: list, log=print) -> str:
    """Downloads ResStock parquet load profiles for a city at the given upgrade levels (mirrors
    Scripts/ResStock Loads/load_importer.py, parameterized to one city instead of a hardcoded ~100-city list)."""
    if not os.path.exists(RESSTOCK_METADATA_PATH):
        raise Exception(f'{RESSTOCK_METADATA_PATH} not found -- required as the ResStock building index.')
    master_frame = pd.read_csv(RESSTOCK_METADATA_PATH)

    sub = master_frame[(master_frame['in.city'] == city) & (master_frame['in.state'] == state) &
                       (master_frame['in.geometry_building_type_acs'].isin(ACCEPTABLE_HOUSE_TYPES)) &
                       (master_frame['upgrade'].isin(upgrade_levels))]
    log(f'{len(sub)} building/upgrade rows found for {city}, {state}')
    out_dir = os.path.join(LOAD_PARQUET_RAW_DIR, state, city)
    if len(sub) == 0:
        return out_dir

    os.makedirs(out_dir, exist_ok=True)
    downloaded = 0
    for _, row in sub.iterrows():
        load_file = f"{row['bldg_id']}-{row['upgrade']}"
        out_path = os.path.join(out_dir, load_file + '.parquet')
        if os.path.exists(out_path):
            continue
        url = f"{RESSTOCK_BASE_URL}{row['upgrade']}/state={state}/{load_file}.parquet"
        response = requests.get(url)
        response.raise_for_status()
        with open(out_path, 'wb') as f:
            f.write(response.content)
        downloaded += 1
        if downloaded % 10 == 0:
            log(f'  downloaded {downloaded} files so far...')
    log(f'Finished: {downloaded} new parquet file(s) in {out_dir}')
    return out_dir


def process_resstock_city(state: str, city: str, log=print) -> str:
    """Converts every downloaded parquet for a city into the model's 5-min parquet format, registering the city
    in Model Data/city_list.csv if it's new (mirrors Scripts/ResStock Loads/load_processor.py)."""
    from pyarrow import ArrowInvalid

    src_dir = os.path.join(LOAD_PARQUET_RAW_DIR, state, city)
    if not os.path.isdir(src_dir):
        raise Exception(f'{src_dir} not found -- download parquets for this city first.')

    city_frame = pd.read_csv(CITY_LIST_PATH)
    added_new_city = False
    if city_frame[(city_frame.City == city) & (city_frame.State == state)].empty:
        city_frame.loc[len(city_frame.index)] = [state, city, None, None, None, None]
        added_new_city = True

    out_dir = os.path.join(LOAD_PARQUET_PROCESSED_DIR, state, city)
    os.makedirs(out_dir, exist_ok=True)

    parq_list = [f for f in os.listdir(src_dir) if f.endswith('.parquet')]
    processed = 0
    for parq in parq_list:
        new_path = os.path.join(out_dir, parq.split('.')[0] + '_5min.parquet')
        if os.path.exists(new_path):
            continue
        try:
            dp.process_resstock_load(os.path.join(src_dir, parq), new_path)
            processed += 1
        except ArrowInvalid:
            log(f'  could not read {parq} (corrupt/incomplete download?), skipping')

    if added_new_city:
        city_frame = city_frame.sort_values(['State', 'City'])
    city_frame.to_csv(CITY_LIST_PATH, index=False)
    log(f'Processed {processed} of {len(parq_list)} parquet file(s) -> {out_dir}')
    return out_dir


def build_load_lookup_city(state: str, city: str, log=print) -> str:
    """Builds/refreshes this city's load summary lookup table from its processed parquets (mirrors, and
    replaces, Scripts/ResStock Loads/load_summarizer.py -- see dp.build_load_lookup)."""
    if not os.path.exists(RESSTOCK_METADATA_PATH):
        raise Exception(f'{RESSTOCK_METADATA_PATH} not found -- required as the ResStock building index.')
    return dp.build_load_lookup(state, city, RESSTOCK_METADATA_PATH, log=log)


# ----------------------------- CO2 (WattTime API) worker functions -----------------------------

WATTTIME_REGION_COLUMN = 'WattTime Region'  # cached in city_list.csv so repeat fetches skip region-from-loc


def load_wattime_credentials_from(path: str) -> dict:
    """Returns {'username':..., 'password':...} from an arbitrary credentials json file, or {} if
    missing/invalid."""
    if os.path.exists(path):
        try:
            with open(path) as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def load_wattime_credentials() -> dict:
    """Returns {'username':..., 'password':...} from WATTTIME_CREDENTIALS_PATH (the default, shared-machine
    credentials file), or {} if none saved yet."""
    return load_wattime_credentials_from(WATTTIME_CREDENTIALS_PATH)


def save_wattime_credentials(username: str, password: str) -> None:
    """Saves a WattTime username/password locally so future wizard sessions default to it.
    WATTTIME_CREDENTIALS_PATH is gitignored -- this is a personal credential, not something to commit."""
    with open(WATTTIME_CREDENTIALS_PATH, 'w') as f:
        json.dump({'username': username, 'password': password}, f)


def wattime_login(username: str, password: str) -> str:
    """Logs into the WattTime v3 API and returns a bearer token (valid ~30 min)."""
    if not (username and password):
        raise Exception('A WattTime username and password are required (request research access at '
                        'watttime.org).')
    response = requests.get(f'{WATTTIME_BASE_URL}/login', auth=(username, password))
    if response.status_code != 200:
        raise Exception(f'WattTime login failed ({response.status_code}): {response.text[:500]}')
    token = response.json().get('token')
    if not token:
        raise Exception(f'WattTime login did not return a token: {response.text[:500]}')
    return token


def wattime_region_from_loc(token: str, lat: float, lon: float, signal_type: str) -> str:
    """Returns the WattTime grid region (balancing authority) code covering one lat/lon point."""
    response = requests.get(f'{WATTTIME_BASE_URL}/v3/region-from-loc',
                            headers={'Authorization': f'Bearer {token}'},
                            params={'latitude': lat, 'longitude': lon, 'signal_type': signal_type})
    if response.status_code != 200:
        raise Exception(f'WattTime region lookup failed ({response.status_code}): {response.text[:500]}')
    region = response.json().get('region')
    if not region:
        raise Exception(f'WattTime region lookup returned no region: {response.text[:500]}')
    return region


def fetch_wattime_historical(token: str, region: str, year: int, signal_type: str, log=print) -> pd.DataFrame:
    """
    Fetches one calendar year (UTC) of historical WattTime data for a region, paginating across the API's
    30-day-per-request limit on /v3/historical. Returns a DataFrame with 'point_time' (UTC) and 'value' (lbs
    CO2/MWh for co2_moer/co2_aoer) columns.
    """
    start = pd.Timestamp(year=year, month=1, day=1, tz='UTC')
    end = pd.Timestamp(year=year + 1, month=1, day=1, tz='UTC')
    records = []
    chunk_start = start
    while chunk_start < end:
        chunk_end = min(chunk_start + pd.Timedelta(days=30), end)
        response = requests.get(f'{WATTTIME_BASE_URL}/v3/historical',
                                headers={'Authorization': f'Bearer {token}'},
                                params={'region': region, 'signal_type': signal_type,
                                        'start': chunk_start.strftime('%Y-%m-%dT%H:%M:%SZ'),
                                        'end': chunk_end.strftime('%Y-%m-%dT%H:%M:%SZ')})
        if response.status_code != 200:
            raise Exception(f'WattTime historical request failed ({response.status_code}): '
                            f'{response.text[:500]}')
        chunk_data = response.json().get('data', [])
        records.extend(chunk_data)
        log(f'  fetched {chunk_start.date()} to {chunk_end.date()} ({len(chunk_data)} points)')
        chunk_start = chunk_end

    if not records:
        raise Exception(f'WattTime returned no {signal_type} data for {region} in {year}.')
    df = pd.DataFrame.from_records(records)[['point_time', 'value']]
    df['point_time'] = pd.to_datetime(df['point_time'], utc=True)
    return df


def _wattime_region_for_row(city_frame: pd.DataFrame, idx, token: str, signal_type: str) -> str:
    """Returns the WATTTIME_REGION_COLUMN value already saved for one city_list.csv row, or resolves it via
    /v3/region-from-loc and writes it into city_frame (in place -- the caller is responsible for persisting
    city_frame to CITY_LIST_PATH afterward)."""
    if WATTTIME_REGION_COLUMN not in city_frame.columns:
        city_frame[WATTTIME_REGION_COLUMN] = pd.NA
    cached = city_frame.at[idx, WATTTIME_REGION_COLUMN]
    if pd.notna(cached) and cached:
        return cached
    row = city_frame.loc[idx]
    region = wattime_region_from_loc(token, row['Latitude'], row['Longitude'], signal_type)
    city_frame.at[idx, WATTTIME_REGION_COLUMN] = region
    return region


def resolve_wattime_regions(signal_type: str, username: str, password: str, cancel_check=None,
                            log=print) -> None:
    """
    Looks up and saves every reference city's WattTime balancing-authority region into a 'WattTime Region'
    column in city_list.csv (via /v3/region-from-loc), so later single/bulk fetches can skip the lookup.
    Optional -- download_and_process_wattime_city resolves and caches a city's region on first use anyway --
    but useful to front-load before a big bulk run. Safe to stop and resume: cities that already have a
    region saved are skipped.
    """
    city_frame = pd.read_csv(CITY_LIST_PATH)
    if WATTTIME_REGION_COLUMN not in city_frame.columns:
        city_frame[WATTTIME_REGION_COLUMN] = pd.NA

    token = wattime_login(username, password)
    total = len(city_frame)
    resolved = 0
    skipped = 0
    for idx, row in city_frame.iterrows():
        if cancel_check is not None and cancel_check():
            log('Cancelled.')
            break
        if pd.notna(row[WATTTIME_REGION_COLUMN]) and row[WATTTIME_REGION_COLUMN]:
            skipped += 1
            continue
        try:
            region = _wattime_region_for_row(city_frame, idx, token, signal_type)
            city_frame.to_csv(CITY_LIST_PATH, index=False)  # incremental save -- survives a stop/crash mid-run
            resolved += 1
            log(f"{row['City']}, {row['State']}: {region}")
        except Exception as ex:
            log(f"  ERROR for {row['City']}, {row['State']}: {ex}")
    log(f'Resolved {resolved} of {total} region(s) ({skipped} already saved).')


def wattime_processed_path(region: str, time_zone: str, year: int) -> str:
    """Returns the processed-file path for one (region, time zone) pair -- the unit WattTime files are keyed
    by, since a single region can straddle a UTC-offset boundary (eg SOCO covers both Alabama (CST) and
    Georgia (EST)) and each zone needs its own correctly-rotated file."""
    return os.path.join(WATTTIME_PROCESSED_DIR, f'{region}_{time_zone}_WattTime_{year}.csv')


def _wattime_region_zones(region: str) -> list:
    """
    Returns every distinct (time_zone_label, time_adjust) pair among reference cities that resolve to a
    WattTime region -- time_adjust is hours to rotate UTC -> local, same convention as process_NSRDB_profile.
    Usually a single pair, but a handful of regions genuinely straddle a UTC-offset boundary (eg SOCO covers
    both Alabama (CST) and Georgia (EST)), hence a list rather than one value.
    """
    city_frame = pd.read_csv(CITY_LIST_PATH)
    if WATTTIME_REGION_COLUMN not in city_frame.columns:
        matches = city_frame.iloc[0:0]
    else:
        matches = city_frame[city_frame[WATTTIME_REGION_COLUMN] == region]
    if matches.empty:
        raise Exception(f"No reference city resolves to WattTime region '{region}' yet -- fetch by city once, "
                        f"or run 'Resolve All Regions', so its time zone(s) are known.")
    zones = matches[['Time Zone', 'Off UTC']].drop_duplicates()
    return [(tz, -1 * int(off_utc)) for tz, off_utc in zip(zones['Time Zone'], zones['Off UTC'])]


def download_and_process_wattime_region(region: str, year: int, signal_type: str, username: str,
                                        password: str, log=print) -> list:
    """
    Pulls one calendar year of historical grid CO2 data from WattTime for one balancing-authority region (a
    single fetch, since that's the unit WattTime's data actually varies by) and processes it into one Emissivity
    file per time zone the region's reference cities fall in -- usually one file, but eg SOCO produces separate
    CST and EST files since it covers both Alabama and Georgia. Returns the list of processed file paths
    written.
    """
    zones = _wattime_region_zones(region)

    token = wattime_login(username, password)
    raw_df = fetch_wattime_historical(token, region, year, signal_type, log=log)

    os.makedirs(WATTTIME_RAW_DIR, exist_ok=True)
    raw_path = os.path.join(WATTTIME_RAW_DIR, f'{region}_WattTime_{signal_type}_{year}.csv')
    raw_df.to_csv(raw_path, index=False)

    os.makedirs(WATTTIME_PROCESSED_DIR, exist_ok=True)
    new_paths = []
    for time_zone, time_adjust in zones:
        new_path = wattime_processed_path(region, time_zone, year)
        dp.process_wattime_profile(raw_path, new_path, year, time_adjust)
        log(f'{region} ({time_zone}): wrote {new_path} ({signal_type})')
        new_paths.append(new_path)
    return new_paths


def download_and_process_wattime_city(state: str, city: str, year: int, signal_type: str, username: str,
                                      password: str, log=print) -> str:
    """
    Convenience wrapper for picking a city instead of memorizing a region code: resolves (and caches) the
    city's WattTime region, then fetches/processes that region via download_and_process_wattime_region (which
    also covers every other reference city sharing the same region, writing one file per time zone within it).
    Returns the specific file matching this city's own time zone.
    """
    city_frame = pd.read_csv(CITY_LIST_PATH)
    sub = city_frame[(city_frame['State'] == state) & (city_frame['City'] == city)]
    if sub.empty:
        raise Exception(f'{city}, {state} not found in {CITY_LIST_PATH}.')
    idx = sub.index[0]
    time_zone = city_frame.at[idx, 'Time Zone']

    token = wattime_login(username, password)
    region = _wattime_region_for_row(city_frame, idx, token, signal_type)
    city_frame.to_csv(CITY_LIST_PATH, index=False)
    log(f'{city}, {state}: WattTime region {region} ({time_zone})')
    download_and_process_wattime_region(region, year, signal_type, username, password, log=log)
    return wattime_processed_path(region, time_zone, year)


def bulk_download_wattime(year: int, signal_type: str, username: str, password: str, state_filter: str = None,
                          skip_existing: bool = True, cancel_check=None, log=print) -> None:
    """
    Runs download_and_process_wattime_region once per unique WattTime region among reference cities (optionally
    scoped to cities in one state), skipping a region only if every time zone it covers already has a processed
    file for this year. Cities with no cached WattTime Region yet are skipped with a note -- run 'Resolve All
    Regions' first for full coverage.
    """
    city_frame = pd.read_csv(CITY_LIST_PATH)
    if state_filter:
        city_frame = city_frame[city_frame['State'] == state_filter]
    if WATTTIME_REGION_COLUMN not in city_frame.columns:
        city_frame[WATTTIME_REGION_COLUMN] = pd.NA

    unresolved = city_frame[city_frame[WATTTIME_REGION_COLUMN].isna()]
    for _, row in unresolved.iterrows():
        log(f"  skipping {row['City']}, {row['State']} -- no cached WattTime Region (run 'Resolve All Regions' "
           f"first)")

    regions = sorted(city_frame[WATTTIME_REGION_COLUMN].dropna().unique().tolist())
    total = len(regions)
    done = 0
    skipped = 0
    for region in regions:
        if cancel_check is not None and cancel_check():
            log('Cancelled.')
            break
        zones = _wattime_region_zones(region)
        if skip_existing and all(os.path.exists(wattime_processed_path(region, tz, year)) for tz, _ in zones):
            skipped += 1
            continue
        try:
            download_and_process_wattime_region(region, year, signal_type, username, password, log=log)
            done += 1
        except Exception as ex:
            log(f'  ERROR for region {region}: {ex}')
        time.sleep(.1)
    log(f'Bulk WattTime update: processed {done} of {total} region(s) ({skipped} already up to date).')


# ----------------------------- CO2 (Cambium) worker function -----------------------------

def process_cambium_file(raw_path: str, state: str, year: int = 2022, log=print) -> str:
    """Processes one raw hourly Cambium csv into the model's 5-min emissivity format (mirrors
    Scripts/Cambium CO2/cambium_process.py). Output goes to the processed folder for the file's Cambium release
    (eg 'Cambium 2020/Processed'), so other releases never overwrite the 2021 profiles the model reads."""
    release = dp.cambium_release(raw_path)
    out_dir = CAMBIUM_PROCESSED_DIR_TEMPLATE.format(release=release) if release else CAMBIUM_PROCESSED_DIR
    os.makedirs(out_dir, exist_ok=True)
    new_path = os.path.join(out_dir, f'{state}_Cambium_{year}.csv')
    log(f'Processing {raw_path} -> {new_path}')
    dp.process_cambium(raw_path, new_path)
    return new_path


# ----------------------------- Utility directory + tariff worker functions -----------------------------

def refresh_directories(cancel_check=None, log=print) -> None:
    """Fast (no-network) refresh of util_to_zip_fixed.csv, zip_to_util_fixed.csv, and new_zip_directory.csv."""
    dp.refresh_zip_utility_directories(cancel_check=cancel_check, log=log)


def enrich_directory(cancel_check=None, log=print) -> None:
    """Slow, resumable per-zip enrichment of Time Zone/Population/Area for new_zip_directory.csv."""
    dp.enrich_zip_directory(cancel_check=cancel_check, log=log)


def utilities_with_state() -> pd.DataFrame:
    """
    Returns every utility in util_to_zip_fixed.csv along with the set of states its serviced zip codes fall in
    ('States') and a single display state ('State', the most common one). Used to populate/filter the utility
    selection dropdown in the Tariffs subtab.

    Notes
    -----
    -   Many utilities serve zip codes across state lines (eg, Georgia Power Co has at least one zip in North
        Carolina), so a utility can legitimately belong to more than one state. Filtering should check
        membership in 'States', not equality against the single 'State' column, or utilities get excluded from
        every state but the one their zip codes happen to be sorted to first.
    """
    util_df = pd.read_csv(UTIL_TO_ZIP_PATH, dtype={'EIA Code': str}, converters={'Zip Codes': ast.literal_eval})
    zip_dir = pd.read_csv(ZIP_DIRECTORY_PATH, dtype={'Zip Code': str})
    zip_to_state = {}
    for zip_code, state in zip(zip_dir['Zip Code'], zip_dir['State (Abbr)']):
        try:
            zip_to_state[str(int(zip_code))] = state
        except (ValueError, TypeError):
            continue

    def states_served(zips):
        found = []
        for z in zips:
            try:
                key = str(int(str(z)))
            except ValueError:
                continue
            state = zip_to_state.get(key)
            if state is not None:
                found.append(state)
        return found

    served = util_df['Zip Codes'].apply(states_served)
    util_df['States'] = served.apply(set)
    util_df['State'] = served.apply(lambda states: pd.Series(states).mode().iat[0] if states else None)
    return util_df[['Utility Name', 'EIA Code', 'State', 'States']].sort_values(
        'Utility Name').reset_index(drop=True)


def refresh_utility_tariffs(utility_name: str, eia: str, cancel_check=None, log=print) -> str:
    """
    Fetches every tariff USURDB currently has on file for one utility (mirrors utility_importer.py's
    per-utility logic: api_read lists tariff ids for the utility, read_tariff fetches each one's full data),
    then:
    -   adds any tariff id not already saved, and
    -   re-fetches (and updates in place) any already-saved tariff whose End Date is still blank.

    Notes
    -----
    -   USURDB updates a tariff's own record in place once it's superseded (its End Date gets filled in and a
        new tariff record appears, sometimes pointing back via Supersedes) rather than always minting a
        replacement id -- so a saved tariff with no End Date isn't guaranteed to still be current, only that it
        was as of the last refresh. Setup.create_tariff picks the current version of a named tariff by matching
        on a blank End Date, so a stale one left un-refreshed can shadow the real current tariff. A tariff that
        already has an End Date is treated as settled and not re-checked.
    """
    util_file_path = os.path.join(UTILITIES_DIR, f'{utility_name}_{eia}_tariffs.csv')
    if os.path.exists(util_file_path):
        util_frame = pd.read_csv(util_file_path)
    else:
        util_frame = pd.DataFrame(columns=['Name', 'OpenEI Id', 'End Date'])
    if 'OpenEI Id' not in util_frame.columns:
        util_frame['OpenEI Id'] = pd.NA
    if 'End Date' not in util_frame.columns:
        util_frame['End Date'] = pd.NA
    util_frame['OpenEI Id'] = util_frame['OpenEI Id'].astype(str)

    listing = ur.api_read(str(eia))
    cooldown = 120
    while 'label' not in listing.columns:
        log(f'  listing request for EIA {eia} did not return results, waiting {cooldown}s before retry...')
        for _ in range(cooldown):
            if cancel_check is not None and cancel_check():
                return util_file_path
            time.sleep(1)
        listing = ur.api_read(str(eia))
        cooldown = min(cooldown + 60, 600)

    existing_ids = set(util_frame['OpenEI Id'])
    open_ids = set(util_frame.loc[util_frame['End Date'].isna(), 'OpenEI Id'])

    new_rows = []
    added = 0
    updated = 0
    for tariff_id in listing['label'].values:
        if cancel_check is not None and cancel_check():
            log('  cancelled.')
            break
        tariff_id = str(tariff_id)
        is_new = tariff_id not in existing_ids
        if not is_new and tariff_id not in open_ids:
            continue  # already saved and already known to be closed out -- won't change further
        try:
            tariff_data = ur.read_tariff(USURDB_TARIFF_URL + tariff_id)
        except AttributeError:
            tariff_data = ur.read_tariff(IURDB_TARIFF_URL + tariff_id, default_url=False)
        tariff_data['OpenEI Id'] = tariff_id
        if is_new:
            new_rows.append(tariff_data)
            added += 1
        else:
            idx = util_frame.index[util_frame['OpenEI Id'] == tariff_id]
            for col, val in tariff_data.items():
                util_frame.loc[idx, col] = val
            updated += 1

    if new_rows:
        util_frame = pd.concat([util_frame, pd.DataFrame(new_rows)], ignore_index=True)
    if new_rows or updated:
        util_frame.to_csv(util_file_path, index=False)

    log(f'{utility_name} ({eia}): {added} new tariff(s), {updated} re-checked/updated, {len(util_frame)} total '
       f'-> {util_file_path}')
    return util_file_path


def refresh_all_utility_tariffs(state_filter: str = None, cancel_check=None, log=print) -> None:
    """Runs refresh_utility_tariffs for every utility in util_to_zip_fixed.csv (optionally scoped to one
    state)."""
    utils = utilities_with_state()
    if state_filter:
        utils = utils[utils['States'].apply(lambda states: state_filter in states)]
    total = len(utils)
    log(f'Refreshing tariffs for {total} utility(ies)...')
    for i, (utility_name, eia) in enumerate(zip(utils['Utility Name'], utils['EIA Code'])):
        if cancel_check is not None and cancel_check():
            log('Cancelled.')
            break
        log(f'[{i + 1}/{total}] {utility_name} (EIA {eia})')
        try:
            refresh_utility_tariffs(utility_name, eia, cancel_check=cancel_check, log=log)
        except Exception as ex:
            log(f'  ERROR: {ex}')
        time.sleep(.1)
    log('Bulk tariff update finished.')


# ----------------------------- Misc helpers -----------------------------
# list_files, list_subdirs, CancelToken, ThreadedLog now live in gui_common.py (imported above).

def list_states(default_all_label: str = None) -> list:
    states = sorted(pd.read_csv(STATES_PATH)['Abbreviation'].dropna().unique().tolist())
    return ([default_all_label] + states) if default_all_label else states


class DataImportWizard:
    def __init__(self, root: Tk):
        self.root = root
        root.title('HouseholdSim - Data Import Wizard')
        root.geometry('1080x840')
        configure_style(root)

        title_bar = ttk.Frame(root, style='App.TFrame')
        title_bar.pack(fill=X)
        ttk.Label(title_bar, text='  HouseholdSim Data Import Wizard', style='AppTitle.TLabel').pack(
            side=LEFT, pady=10)

        notebook = ttk.Notebook(root)
        notebook.pack(fill=BOTH, expand=True, padx=8, pady=8)

        self.solar_tab = ttk.Frame(notebook)
        self.load_tab = ttk.Frame(notebook)
        self.utility_tab = ttk.Frame(notebook)
        self.co2_tab = ttk.Frame(notebook)

        notebook.add(self.solar_tab, text='Solar (NSRDB)')
        notebook.add(self.load_tab, text='House Load (ResStock)')
        notebook.add(self.utility_tab, text='Utilities')
        notebook.add(self.co2_tab, text='CO2')

        self._active_tokens = {}  # a CancelToken per stoppable action, keyed by name

        self._build_solar_tab()
        self._build_load_tab()
        self._build_utility_tab()
        self._build_co2_tab()

    # ---------- shared helpers ----------
    # Thin wrappers delegating to gui_common, kept under their original names so none of this file's
    # many self._xxx(...) call sites needed to change when the implementations moved out.

    @staticmethod
    def _make_scrollable(parent) -> ttk.Frame:
        return gui_common.make_scrollable(parent)

    @staticmethod
    def _card(parent, title) -> ttk.LabelFrame:
        return gui_common.card(parent, title)

    @staticmethod
    def _make_log_box(parent) -> ThreadedLog:
        return gui_common.make_log_box(parent)

    @staticmethod
    def _bind_combobox_filter(combo: ttk.Combobox, get_full_list):
        return gui_common.bind_combobox_filter(combo, get_full_list)

    def _make_file_picker(self, parent, directory: str, pattern: str = '*.csv'):
        return gui_common.make_file_picker(parent, directory, pattern)

    def _preview_dataframe(self, df: pd.DataFrame, title: str = 'Preview'):
        return gui_common.preview_dataframe(self.root, df, title)

    def _preview_series(self, values, title: str, ylabel: str, max_points: int = 864):
        return gui_common.preview_series(self.root, values, title, ylabel, max_points)

    def _browse_file(self, target_var: StringVar, initialdir='.', filetypes=(('All files', '*.*'),)):
        return gui_common.browse_file(target_var, initialdir, filetypes)

    def _make_stoppable_action(self, parent, token_key: str, start_text: str, start_cmd, style='Accent.TButton'):
        return gui_common.make_stoppable_action(parent, self._active_tokens, token_key, start_text,
                                                start_cmd, style)

    # ---------- Solar (NSRDB) tab ----------

    def _build_solar_tab(self):
        tab = self._make_scrollable(self.solar_tab)
        ttk.Label(tab, text='NSRDB Solar Data', style='Header.TLabel').pack(anchor=W, padx=10, pady=(10, 0))
        ttk.Label(tab, text='Pulled from NREL\'s NSRDB via the developer.nlr.gov REST API (the NSRDB API moved '
                            'from developer.nrel.gov). Simulation.make_pv only auto-loads a file named with '
                            'year "2018" -- other years/TMY vintages are fetched and examinable here, but need '
                            'the "Other Solar File" input to be used in a simulation.', style='Sub.TLabel',
                 wraplength=1000).pack(anchor=W, padx=10)

        saved_creds = load_nsrdb_credentials()

        cred_card = self._card(tab, '1. NSRDB Credentials')
        api_key_var = StringVar(value=saved_creds.get('api_key', ''))
        email_var = StringVar(value=saved_creds.get('email', ''))
        remember_var = BooleanVar(value=True)

        ttk.Label(cred_card, text='API Key:', style='Card.TLabel').grid(row=0, column=0, sticky=W, padx=5, pady=4)
        ttk.Entry(cred_card, textvariable=api_key_var, width=40, show='*').grid(row=0, column=1, padx=5, pady=4)
        ttk.Label(cred_card, text='Email:', style='Card.TLabel').grid(row=0, column=2, sticky=W, padx=5, pady=4)
        ttk.Entry(cred_card, textvariable=email_var, width=30).grid(row=0, column=3, padx=5, pady=4)
        ttk.Checkbutton(cred_card, text='Remember on this machine (overwrites the shared default)',
                       variable=remember_var).grid(row=1, column=0, columnspan=3, sticky=W, padx=5, pady=4)
        ttk.Label(cred_card, text='Free key: developer.nlr.gov', style='Sub.TLabel').grid(
            row=1, column=3, sticky=W, padx=5, pady=4)

        def do_load_from_file():
            path = filedialog.askopenfilename(title='Load NSRDB credentials from...',
                                              filetypes=(('JSON files', '*.json'), ('All files', '*.*')))
            if not path:
                return
            creds = load_nsrdb_credentials_from(path)
            if not creds.get('api_key'):
                messagebox.showwarning('Invalid file', f"Couldn't find an 'api_key' in {os.path.basename(path)}.")
                return
            api_key_var.set(creds.get('api_key', ''))
            email_var.set(creds.get('email', ''))
            remember_var.set(False)  # loading someone else's key shouldn't silently overwrite the shared default

        ttk.Button(cred_card, text='Load From File...', command=do_load_from_file).grid(
            row=2, column=0, sticky=W, padx=5, pady=4)
        ttk.Label(cred_card, text='For other users: load a different key without overwriting the shared '
                                  'default above (leaves "Remember" unchecked).', style='Sub.TLabel').grid(
            row=2, column=1, columnspan=3, sticky=W, padx=5, pady=4)

        def get_credentials():
            if remember_var.get():
                save_nsrdb_credentials(api_key_var.get(), email_var.get())
            return api_key_var.get(), email_var.get()

        dataset_card = self._card(tab, '2. Dataset')
        dataset_labels = [d['label'] for d in NSRDB_DATASETS.values()]
        dataset_by_label = {d['label']: key for key, d in NSRDB_DATASETS.items()}
        dataset_var = StringVar(value=NSRDB_DATASETS[DEFAULT_NSRDB_DATASET]['label'])
        name_var = StringVar(value=DEFAULT_NSRDB_NAME)
        resolution_var = StringVar()
        coverage_var = StringVar()

        ttk.Label(dataset_card, text='Dataset:', style='Card.TLabel').grid(row=0, column=0, sticky=W, padx=5,
                                                                           pady=4)
        dataset_combo = ttk.Combobox(dataset_card, textvariable=dataset_var, values=dataset_labels, width=48,
                                     state='readonly')
        dataset_combo.grid(row=0, column=1, columnspan=3, sticky=W, padx=5, pady=4)

        ttk.Label(dataset_card, text='Year / TMY vintage:', style='Card.TLabel').grid(
            row=1, column=0, sticky=W, padx=5, pady=4)
        name_combo = ttk.Combobox(dataset_card, textvariable=name_var, width=15, state='readonly')
        name_combo.grid(row=1, column=1, sticky=W, padx=5, pady=4)
        ttk.Label(dataset_card, text='Native resolution:', style='Card.TLabel').grid(
            row=1, column=2, sticky=W, padx=5, pady=4)
        ttk.Label(dataset_card, textvariable=resolution_var, style='Card.TLabel').grid(
            row=1, column=3, sticky=W, padx=5, pady=4)
        ttk.Label(dataset_card, text='Coverage:', style='Card.TLabel').grid(row=2, column=0, sticky=W, padx=5,
                                                                            pady=4)
        ttk.Label(dataset_card, textvariable=coverage_var, style='Card.TLabel').grid(
            row=2, column=1, columnspan=3, sticky=W, padx=5, pady=4)

        def current_dataset_key():
            return dataset_by_label[dataset_var.get()]

        def on_dataset_change(event=None):
            dataset = NSRDB_DATASETS[current_dataset_key()]
            resolution_var.set(f"{dataset['native_interval_minutes']} min")
            coverage_var.set(dataset['coverage'])
            name_combo['values'] = dataset['names']
            if name_var.get() not in dataset['names']:
                name_var.set(dataset['names'][0])

        dataset_combo.bind('<<ComboboxSelected>>', on_dataset_change)
        on_dataset_change()

        states = list_states()
        city_frame = pd.read_csv(CITY_LIST_PATH)

        def cities_for(state):
            return sorted(city_frame[city_frame['State'] == state]['City'].tolist())

        single = self._card(tab, '3. Single City')
        state_var = StringVar()
        city_var = StringVar()

        ttk.Label(single, text='State:', style='Card.TLabel').grid(row=0, column=0, sticky=W, padx=5, pady=4)
        state_combo = ttk.Combobox(single, textvariable=state_var, values=states, width=8, state='readonly')
        state_combo.grid(row=0, column=1, sticky=W, padx=5, pady=4)

        ttk.Label(single, text='City:', style='Card.TLabel').grid(row=0, column=2, sticky=W, padx=5, pady=4)
        city_combo = ttk.Combobox(single, textvariable=city_var, width=25, state='readonly')
        city_combo.grid(row=0, column=3, sticky=W, padx=5, pady=4)

        def on_state_change(event=None):
            city_combo['values'] = cities_for(state_var.get())
            city_var.set('')

        state_combo.bind('<<ComboboxSelected>>', on_state_change)

        log = self._make_log_box(tab)

        def do_single():
            if not (state_var.get() and city_var.get()):
                messagebox.showwarning('Missing input', 'State and city are required.')
                return
            api_key, email = get_credentials()
            log.run(download_and_process_solar_city, state_var.get(), city_var.get(), current_dataset_key(),
                   name_var.get(), api_key, email, log=log.log)

        ttk.Button(single, text='Download & Process', style='Accent.TButton', command=do_single).grid(
            row=1, column=0, columnspan=2, sticky=W, padx=5, pady=4)

        bulk = self._card(tab, '4. Bulk Update')
        bulk_state_var = StringVar(value='All States')
        skip_existing_var = BooleanVar(value=True)

        ttk.Label(bulk, text='State:', style='Card.TLabel').grid(row=0, column=0, sticky=W, padx=5, pady=4)
        ttk.Combobox(bulk, textvariable=bulk_state_var, values=list_states('All States'), width=12,
                    state='readonly').grid(row=0, column=1, sticky=W, padx=5, pady=4)
        ttk.Checkbutton(bulk, text='Skip cities that already have a processed file for this year/vintage',
                       variable=skip_existing_var).grid(row=1, column=0, columnspan=4, sticky=W, padx=5, pady=4)

        def start_bulk(cancel_check, on_finally):
            state_filter = None if bulk_state_var.get() == 'All States' else bulk_state_var.get()
            api_key, email = get_credentials()
            log.run(bulk_download_solar, current_dataset_key(), name_var.get(), api_key, email, state_filter,
                   skip_existing_var.get(), cancel_check, log=log.log, on_finally=on_finally)

        self._make_stoppable_action(bulk, 'solar_bulk', 'Run Bulk Update', start_bulk).grid(
            row=2, column=0, columnspan=4, sticky=W, padx=5, pady=(6, 4))

        examine = self._card(tab, '5. Examine')
        ex_var, ex_combo, ex_refresh = self._make_file_picker(examine, SOLAR_DIR, '*.csv')
        ttk.Label(examine, text='File:', style='Card.TLabel').grid(row=0, column=0, sticky=W, padx=5, pady=4)
        ex_combo.grid(row=0, column=1, sticky=W, padx=5, pady=4)
        ttk.Button(examine, text='Refresh List', command=ex_refresh).grid(row=0, column=2, padx=5, pady=4)

        def do_examine():
            if not ex_var.get():
                return
            path = os.path.join(SOLAR_DIR, ex_var.get())
            df = pd.read_csv(path)
            self._preview_dataframe(df, title=ex_var.get())
            if 'GHI(W/m^2)' in df.columns:
                self._preview_series(df['GHI(W/m^2)'].to_numpy(), title=f'GHI - {ex_var.get()} (first 3 days)',
                                    ylabel='W/m^2')

        ttk.Button(examine, text='Preview', style='Accent.TButton', command=do_examine).grid(
            row=0, column=3, padx=5, pady=4)

    # ---------- House Load (ResStock) tab ----------

    def _build_load_tab(self):
        tab = self._make_scrollable(self.load_tab)
        ttk.Label(tab, text='ResStock House Load Profiles', style='Header.TLabel').pack(anchor=W, padx=10,
                                                                                        pady=(10, 0))

        dl = self._card(tab, '1. Download')
        state = StringVar()
        city = StringVar()
        upgrades = StringVar(value='0')

        ttk.Label(dl, text='State:', style='Card.TLabel').grid(row=0, column=0, sticky=W, padx=5, pady=4)
        ttk.Combobox(dl, textvariable=state, values=list_states(), width=8, state='readonly').grid(
            row=0, column=1, sticky=W, padx=5, pady=4)
        ttk.Label(dl, text='City:', style='Card.TLabel').grid(row=0, column=2, sticky=W, padx=5, pady=4)
        ttk.Entry(dl, textvariable=city, width=25).grid(row=0, column=3, sticky=W, padx=5, pady=4)
        ttk.Label(dl, text='Upgrade levels (comma-separated, 0-10):', style='Card.TLabel').grid(
            row=1, column=0, columnspan=2, sticky=W, padx=5, pady=4)
        ttk.Entry(dl, textvariable=upgrades, width=25).grid(row=1, column=2, columnspan=2, sticky=W, padx=5,
                                                            pady=4)

        log = self._make_log_box(tab)

        def do_download():
            if not (state.get() and city.get()):
                messagebox.showwarning('Missing input', 'State and city are required.')
                return
            try:
                levels = [int(u.strip()) for u in upgrades.get().split(',') if u.strip() != '']
            except ValueError:
                messagebox.showwarning('Invalid input', 'Upgrade levels must be integers.')
                return
            log.run(download_resstock_city, state.get(), city.get(), levels, log=log.log)

        ttk.Button(dl, text='Download', style='Accent.TButton', command=do_download).grid(
            row=2, column=0, columnspan=2, sticky=W, padx=5, pady=4)

        proc = self._card(tab, '2. Process (uses State/City above)')

        def do_process():
            if not (state.get() and city.get()):
                messagebox.showwarning('Missing input', 'State and city are required.')
                return

            def on_done(result):
                ex_refresh()

            log.run(process_resstock_city, state.get(), city.get(), on_done=on_done, log=log.log)

        ttk.Button(proc, text='Process', style='Accent.TButton', command=do_process).pack(anchor=W)

        lookup = self._card(tab, '3. Build Load Lookup (uses State/City above)')
        ttk.Label(lookup, text="Summarizes this city's processed parquets (total/monthly kWh, house type, "
                               'bedrooms, sqft) into the lookup table load_match_yearly searches when a '
                               'scenario asks for a profile by target annual usage rather than a load file. '
                               'Safe to re-run after downloading more buildings -- already-summarized ones are '
                               'skipped.', style='Sub.TLabel', wraplength=1000).pack(anchor=W)

        def do_build_lookup():
            if not (state.get() and city.get()):
                messagebox.showwarning('Missing input', 'State and city are required.')
                return
            log.run(build_load_lookup_city, state.get(), city.get(), log=log.log)

        ttk.Button(lookup, text='Build Load Lookup', style='Accent.TButton', command=do_build_lookup).pack(
            anchor=W, pady=(6, 0))

        # Processed parquets number in the hundreds of thousands across all cities, so the file picker cascades
        # State -> City -> File instead of one flat (and unusably large) dropdown.
        examine = self._card(tab, '4. Examine')
        ex_state_var = StringVar()
        ex_city_var = StringVar()
        ex_file_var = StringVar()

        ttk.Label(examine, text='State:', style='Card.TLabel').grid(row=0, column=0, sticky=W, padx=5, pady=4)
        ex_state_combo = ttk.Combobox(examine, textvariable=ex_state_var, width=8, state='readonly')
        ex_state_combo.grid(row=0, column=1, sticky=W, padx=5, pady=4)
        ttk.Label(examine, text='City:', style='Card.TLabel').grid(row=0, column=2, sticky=W, padx=5, pady=4)
        ex_city_combo = ttk.Combobox(examine, textvariable=ex_city_var, width=20, state='readonly')
        ex_city_combo.grid(row=0, column=3, sticky=W, padx=5, pady=4)
        ttk.Label(examine, text='File:', style='Card.TLabel').grid(row=1, column=0, sticky=W, padx=5, pady=4)
        ex_file_combo = ttk.Combobox(examine, textvariable=ex_file_var, width=30)
        ex_file_combo.grid(row=1, column=1, columnspan=3, sticky=W, padx=5, pady=4)
        self._bind_combobox_filter(
            ex_file_combo, lambda: list_files(os.path.join(LOAD_PARQUET_PROCESSED_DIR, ex_state_var.get(),
                                                            ex_city_var.get()), '*.parquet'))

        def ex_refresh():
            ex_state_combo['values'] = list_subdirs(LOAD_PARQUET_PROCESSED_DIR)

        def on_ex_state_change(event=None):
            ex_city_combo['values'] = list_subdirs(os.path.join(LOAD_PARQUET_PROCESSED_DIR, ex_state_var.get()))
            ex_city_var.set('')
            ex_file_var.set('')
            ex_file_combo['values'] = []

        def on_ex_city_change(event=None):
            ex_file_combo['values'] = list_files(
                os.path.join(LOAD_PARQUET_PROCESSED_DIR, ex_state_var.get(), ex_city_var.get()), '*.parquet')
            ex_file_var.set('')

        ex_state_combo.bind('<<ComboboxSelected>>', on_ex_state_change)
        ex_city_combo.bind('<<ComboboxSelected>>', on_ex_city_change)
        ex_refresh()
        ttk.Button(examine, text='Refresh', command=ex_refresh).grid(row=0, column=4, padx=5, pady=4)

        def do_examine():
            if not (ex_state_var.get() and ex_city_var.get() and ex_file_var.get()):
                return
            path = os.path.join(LOAD_PARQUET_PROCESSED_DIR, ex_state_var.get(), ex_city_var.get(),
                                ex_file_var.get())
            # with_time=True regenerates the timestamp column for display. Processed profiles no longer
            # store it -- it was identical in every file and ~85% of their bytes. Files that still have
            # a stored Time column are read the same way.
            df = dp.read_resstock_profile(path, with_time=True)
            self._preview_dataframe(df, title=ex_file_var.get())
            if 'Load(kW)' in df.columns:
                self._preview_series(df['Load(kW)'].to_numpy(),
                                    title=f'Load - {ex_file_var.get()} (first 3 days)', ylabel='kW')

        ttk.Button(examine, text='Preview', style='Accent.TButton', command=do_examine).grid(
            row=1, column=4, padx=5, pady=4)

    # ---------- Utilities tab (Directories + Tariffs subtabs) ----------

    def _build_utility_tab(self):
        tab = self.utility_tab
        sub_notebook = ttk.Notebook(tab)
        sub_notebook.pack(fill=BOTH, expand=True)

        directories_tab = ttk.Frame(sub_notebook)
        tariffs_tab = ttk.Frame(sub_notebook)
        sub_notebook.add(directories_tab, text='Directories')
        sub_notebook.add(tariffs_tab, text='Tariffs')

        self._build_directories_subtab(directories_tab)
        self._build_tariffs_subtab(tariffs_tab)

    def _build_directories_subtab(self, tab):
        tab = self._make_scrollable(tab)
        ttk.Label(tab, text='Zip / Utility Directory Maintenance', style='Header.TLabel').pack(
            anchor=W, padx=10, pady=(10, 0))
        ttk.Label(tab, text='Rebuilds Model Data/util_to_zip_fixed.csv, zip_to_util_fixed.csv, and '
                            'new_zip_directory.csv from the raw scraped data in Archive/DataFiles/. Any '
                            'hand-curated columns (net metering info, Time Zone/Population/Area) are preserved.',
                 style='Sub.TLabel', wraplength=1000).pack(anchor=W, padx=10)

        refresh_card = self._card(tab, '1. Refresh Directories (fast, no network)')
        log = self._make_log_box(tab)

        def do_refresh():
            log.run(refresh_directories, None, log=log.log)

        ttk.Button(refresh_card, text='Refresh Now', style='Accent.TButton', command=do_refresh).pack(anchor=W)

        enrich_card = self._card(tab, '2. Enrich Time Zone / Population / Area')
        ttk.Label(enrich_card, text='Scrapes zipdatamaps.com per zip code -- this can take a long time for a '
                                    'full run. Safe to stop and resume; already-filled zip codes are skipped.',
                 style='Warn.TLabel', wraplength=1000).pack(anchor=W)

        def start_enrich(cancel_check, on_finally):
            log.run(enrich_directory, cancel_check, log=log.log, on_finally=on_finally)

        self._make_stoppable_action(enrich_card, 'zip_enrich', 'Start', start_enrich).pack(anchor=W, pady=(6, 0))

    def _build_tariffs_subtab(self, tab):
        tab = self._make_scrollable(tab)
        ttk.Label(tab, text='USURDB Tariffs', style='Header.TLabel').pack(anchor=W, padx=10, pady=(10, 0))

        self._util_cache = None  # lazily loaded utilities_with_state() result

        def get_utilities():
            if self._util_cache is None:
                self._util_cache = utilities_with_state()
            return self._util_cache

        single = self._card(tab, '1. Single Utility Refresh')
        state_var = StringVar(value='All States')
        util_var = StringVar()
        eia_var = StringVar()

        ttk.Label(single, text='State filter:', style='Card.TLabel').grid(row=0, column=0, sticky=W, padx=5,
                                                                          pady=4)
        state_combo = ttk.Combobox(single, textvariable=state_var, values=list_states('All States'), width=12,
                                   state='readonly')
        state_combo.grid(row=0, column=1, sticky=W, padx=5, pady=4)

        ttk.Label(single, text='Utility:', style='Card.TLabel').grid(row=1, column=0, sticky=W, padx=5, pady=4)
        util_combo = ttk.Combobox(single, textvariable=util_var, width=45)
        util_combo.grid(row=1, column=1, columnspan=3, sticky=W, padx=5, pady=4)

        def current_utility_names():
            df = get_utilities()
            if state_var.get() and state_var.get() != 'All States':
                df = df[df['States'].apply(lambda states: state_var.get() in states)]
            return df['Utility Name'].tolist()

        def refresh_util_list(event=None):
            util_combo['values'] = current_utility_names()
            util_var.set('')
            eia_var.set('')

        self._bind_combobox_filter(util_combo, current_utility_names)
        state_combo.bind('<<ComboboxSelected>>', refresh_util_list)
        refresh_util_list()

        def on_util_selected(event=None):
            df = get_utilities()
            match = df[df['Utility Name'] == util_var.get()]
            if not match.empty:
                eia_var.set(match.iloc[0]['EIA Code'])

        util_combo.bind('<<ComboboxSelected>>', on_util_selected)

        ttk.Label(single, text='EIA Code (or type a utility above):', style='Card.TLabel').grid(
            row=2, column=0, sticky=W, padx=5, pady=4, columnspan=2)
        ttk.Entry(single, textvariable=eia_var, width=15).grid(row=2, column=2, sticky=W, padx=5, pady=4)

        log = self._make_log_box(tab)

        def do_single_refresh():
            if not eia_var.get():
                messagebox.showwarning('Missing input', 'Select a utility or enter an EIA code.')
                return
            name = util_var.get()
            if not name:
                # EIA was typed manually rather than picked from the list -- try to resolve its name anyway.
                match = get_utilities()[get_utilities()['EIA Code'] == eia_var.get()]
                name = match.iloc[0]['Utility Name'] if not match.empty else f'EIA_{eia_var.get()}'
            log.run(refresh_utility_tariffs, name, eia_var.get(), None, log=log.log)

        ttk.Button(single, text='Refresh Tariffs for This Utility', style='Accent.TButton',
                  command=do_single_refresh).grid(row=3, column=0, columnspan=2, sticky=W, padx=5, pady=6)

        bulk = self._card(tab, '2. Bulk Update All Utilities')
        bulk_state_var = StringVar(value='All States')
        ttk.Label(bulk, text='State filter:', style='Card.TLabel').grid(row=0, column=0, sticky=W, padx=5,
                                                                        pady=4)
        ttk.Combobox(bulk, textvariable=bulk_state_var, values=list_states('All States'), width=12,
                    state='readonly').grid(row=0, column=1, sticky=W, padx=5, pady=4)
        ttk.Label(bulk, text='This can take a very long time across thousands of utilities. Safe to stop and '
                            'resume -- tariffs already saved are skipped on the next run.', style='Warn.TLabel',
                 wraplength=1000).grid(row=1, column=0, columnspan=4, sticky=W, padx=5, pady=4)

        def start_bulk(cancel_check, on_finally):
            state_filter = None if bulk_state_var.get() == 'All States' else bulk_state_var.get()
            log.run(refresh_all_utility_tariffs, state_filter, cancel_check, log=log.log, on_finally=on_finally)

        self._make_stoppable_action(bulk, 'tariff_bulk', 'Run Bulk Update', start_bulk).grid(
            row=2, column=0, columnspan=4, sticky=W, padx=5, pady=(6, 4))

        examine = self._card(tab, '3. Examine')
        ex_var, ex_combo, ex_refresh = self._make_file_picker(examine, UTILITIES_DIR, '*.csv')
        ttk.Label(examine, text='File:', style='Card.TLabel').grid(row=0, column=0, sticky=W, padx=5, pady=4)
        ex_combo.grid(row=0, column=1, sticky=W, padx=5, pady=4)
        ttk.Button(examine, text='Refresh List', command=ex_refresh).grid(row=0, column=2, padx=5, pady=4)

        def do_examine():
            if ex_var.get():
                self._preview_dataframe(pd.read_csv(os.path.join(UTILITIES_DIR, ex_var.get())),
                                       title=ex_var.get())

        ttk.Button(examine, text='Preview', style='Accent.TButton', command=do_examine).grid(
            row=0, column=3, padx=5, pady=4)

    # ---------- CO2 tab (Cambium + WattTime subtabs) ----------

    def _build_co2_tab(self):
        tab = self.co2_tab
        sub_notebook = ttk.Notebook(tab)
        sub_notebook.pack(fill=BOTH, expand=True)

        cambium_tab = ttk.Frame(sub_notebook)
        wattime_tab = ttk.Frame(sub_notebook)
        sub_notebook.add(cambium_tab, text='Cambium')
        sub_notebook.add(wattime_tab, text='WattTime')

        self._build_cambium_subtab(cambium_tab)
        self._build_wattime_subtab(wattime_tab)

    def _build_cambium_subtab(self, tab):
        tab = self._make_scrollable(tab)
        ttk.Label(tab, text='Cambium CO2 Intensity', style='Header.TLabel').pack(anchor=W, padx=10, pady=(10, 0))

        proc = self._card(tab, '1. Process a Raw Cambium File')
        raw_path = StringVar()
        state = StringVar()
        year = StringVar(value='2022')

        ttk.Label(proc, text='Raw Cambium csv:', style='Card.TLabel').grid(row=0, column=0, sticky=W, padx=5,
                                                                           pady=4)
        ttk.Entry(proc, textvariable=raw_path, width=45).grid(row=0, column=1, padx=5, pady=4)
        ttk.Button(proc, text='Browse...',
                  command=lambda: self._browse_file(raw_path, filetypes=(('CSV files', '*.csv'),))
                  ).grid(row=0, column=2, padx=5, pady=4)

        ttk.Label(proc, text='State:', style='Card.TLabel').grid(row=1, column=0, sticky=W, padx=5, pady=4)
        ttk.Combobox(proc, textvariable=state, values=list_states(), width=8, state='readonly').grid(
            row=1, column=1, sticky=W, padx=5, pady=4)
        ttk.Label(proc, text='Data year:', style='Card.TLabel').grid(row=2, column=0, sticky=W, padx=5, pady=4)
        ttk.Entry(proc, textvariable=year, width=10).grid(row=2, column=1, sticky=W, padx=5, pady=4)

        log = self._make_log_box(tab)

        def do_process():
            if not (raw_path.get() and state.get()):
                messagebox.showwarning('Missing input', 'Raw file and state are required.')
                return

            def on_done(result):
                ex_refresh()

            log.run(process_cambium_file, raw_path.get(), state.get(), int(year.get()), on_done=on_done,
                   log=log.log)

        ttk.Button(proc, text='Process', style='Accent.TButton', command=do_process).grid(
            row=3, column=0, sticky=W, padx=5, pady=6)

        examine = self._card(tab, '2. Examine')
        ex_var, ex_combo, ex_refresh = self._make_file_picker(examine, CAMBIUM_PROCESSED_DIR, '*.csv')
        ttk.Label(examine, text='File:', style='Card.TLabel').grid(row=0, column=0, sticky=W, padx=5, pady=4)
        ex_combo.grid(row=0, column=1, sticky=W, padx=5, pady=4)
        ttk.Button(examine, text='Refresh List', command=ex_refresh).grid(row=0, column=2, padx=5, pady=4)

        def do_examine():
            if not ex_var.get():
                return
            path = os.path.join(CAMBIUM_PROCESSED_DIR, ex_var.get())
            df = pd.read_csv(path)
            self._preview_dataframe(df, title=ex_var.get())
            if 'Emissivity' in df.columns:
                self._preview_series(df['Emissivity'].to_numpy(), title=f'Emissivity - {ex_var.get()} '
                                                                        f'(first 3 days)', ylabel='kg CO2/kWh')

        ttk.Button(examine, text='Preview', style='Accent.TButton', command=do_examine).grid(
            row=0, column=3, padx=5, pady=4)

    def _build_wattime_subtab(self, tab):
        tab = self._make_scrollable(tab)
        ttk.Label(tab, text='WattTime Grid CO2 Data', style='Header.TLabel').pack(anchor=W, padx=10, pady=(10, 0))
        ttk.Label(tab, text='Pulls real, time-stamped grid emissions data from the WattTime v3 API (requires '
                            'an account with historical data access). Data varies by balancing-authority '
                            'region, not by city, so each region is only fetched once -- eg SOCO alone covers '
                            'every reference city in both Alabama and Georgia. A region can still straddle a '
                            'timezone (SOCO spans CST Alabama and EST Georgia), so one processed file is saved '
                            'per region+timezone pair to keep each one correctly localized.', style='Sub.TLabel',
                 wraplength=1000).pack(anchor=W, padx=10)

        saved_creds = load_wattime_credentials()

        cred_card = self._card(tab, '1. WattTime Credentials')
        username_var = StringVar(value=saved_creds.get('username', ''))
        password_var = StringVar(value=saved_creds.get('password', ''))
        remember_var = BooleanVar(value=True)

        ttk.Label(cred_card, text='Username:', style='Card.TLabel').grid(row=0, column=0, sticky=W, padx=5,
                                                                          pady=4)
        ttk.Entry(cred_card, textvariable=username_var, width=25).grid(row=0, column=1, padx=5, pady=4)
        ttk.Label(cred_card, text='Password:', style='Card.TLabel').grid(row=0, column=2, sticky=W, padx=5,
                                                                          pady=4)
        ttk.Entry(cred_card, textvariable=password_var, width=25, show='*').grid(row=0, column=3, padx=5, pady=4)
        ttk.Checkbutton(cred_card, text='Remember on this machine (overwrites the shared default)',
                       variable=remember_var).grid(row=1, column=0, columnspan=4, sticky=W, padx=5, pady=4)

        def get_credentials():
            if remember_var.get():
                save_wattime_credentials(username_var.get(), password_var.get())
            return username_var.get(), password_var.get()

        signal_card = self._card(tab, '2. Signal')
        signal_labels = [d['label'] for d in WATTTIME_SIGNAL_TYPES.values()]
        signal_by_label = {d['label']: key for key, d in WATTTIME_SIGNAL_TYPES.items()}
        signal_var = StringVar(value=WATTTIME_SIGNAL_TYPES[DEFAULT_WATTTIME_SIGNAL]['label'])

        ttk.Label(signal_card, text='Signal type:', style='Card.TLabel').grid(row=0, column=0, sticky=W, padx=5,
                                                                               pady=4)
        ttk.Combobox(signal_card, textvariable=signal_var, values=signal_labels, width=72,
                    state='readonly').grid(row=0, column=1, sticky=W, padx=5, pady=4)

        def current_signal_type():
            return signal_by_label[signal_var.get()]

        log = self._make_log_box(tab)

        regions_card = self._card(tab, '3. City Regions')
        ttk.Label(regions_card, text='Resolves and caches every reference city\'s WattTime region into '
                                     'city_list.csv. Bulk Update below only pulls data for regions that have '
                                     'been resolved here (or via a prior Single City fetch) -- run this first '
                                     'for full bulk coverage. Safe to stop and resume.', style='Sub.TLabel',
                 wraplength=1000).pack(anchor=W)

        def start_resolve_regions(cancel_check, on_finally):
            username, password = get_credentials()
            log.run(resolve_wattime_regions, current_signal_type(), username, password, cancel_check,
                   log=log.log, on_finally=on_finally)

        self._make_stoppable_action(regions_card, 'wattime_regions', 'Resolve All Regions',
                                    start_resolve_regions).pack(anchor=W, pady=(6, 0))

        states = list_states()
        city_frame = pd.read_csv(CITY_LIST_PATH)

        def cities_for(state):
            return sorted(city_frame[city_frame['State'] == state]['City'].tolist())

        single = self._card(tab, '4. Single City')
        state_var = StringVar()
        city_var = StringVar()
        year_var = StringVar(value='2023')

        ttk.Label(single, text='State:', style='Card.TLabel').grid(row=0, column=0, sticky=W, padx=5, pady=4)
        state_combo = ttk.Combobox(single, textvariable=state_var, values=states, width=8, state='readonly')
        state_combo.grid(row=0, column=1, sticky=W, padx=5, pady=4)

        ttk.Label(single, text='City:', style='Card.TLabel').grid(row=0, column=2, sticky=W, padx=5, pady=4)
        city_combo = ttk.Combobox(single, textvariable=city_var, width=25, state='readonly')
        city_combo.grid(row=0, column=3, sticky=W, padx=5, pady=4)

        ttk.Label(single, text='Year:', style='Card.TLabel').grid(row=1, column=0, sticky=W, padx=5, pady=4)
        ttk.Entry(single, textvariable=year_var, width=8).grid(row=1, column=1, sticky=W, padx=5, pady=4)

        def on_state_change(event=None):
            city_combo['values'] = cities_for(state_var.get())
            city_var.set('')

        state_combo.bind('<<ComboboxSelected>>', on_state_change)

        def parsed_year():
            try:
                return int(year_var.get())
            except ValueError:
                messagebox.showwarning('Invalid input', 'Year must be an integer.')
                return None

        def do_single():
            if not (state_var.get() and city_var.get() and year_var.get()):
                messagebox.showwarning('Missing input', 'State, city, and year are required.')
                return
            year = parsed_year()
            if year is None:
                return
            username, password = get_credentials()
            log.run(download_and_process_wattime_city, state_var.get(), city_var.get(), year,
                   current_signal_type(), username, password, log=log.log)

        ttk.Button(single, text='Fetch & Process', style='Accent.TButton', command=do_single).grid(
            row=2, column=0, columnspan=2, sticky=W, padx=5, pady=4)
        ttk.Label(single, text='Saves one file per region+timezone (named by region and timezone, not city) '
                               '-- this also covers every other reference city sharing the same region.',
                 style='Sub.TLabel', wraplength=900).grid(row=3, column=0, columnspan=4, sticky=W, padx=5,
                                                          pady=(0, 4))

        bulk = self._card(tab, '5. Bulk Update')
        bulk_state_var = StringVar(value='All States')
        skip_existing_var = BooleanVar(value=True)

        ttk.Label(bulk, text='State:', style='Card.TLabel').grid(row=0, column=0, sticky=W, padx=5, pady=4)
        ttk.Combobox(bulk, textvariable=bulk_state_var, values=list_states('All States'), width=12,
                    state='readonly').grid(row=0, column=1, sticky=W, padx=5, pady=4)
        ttk.Label(bulk, text='Pulls every region touched by cities in this state (or all states), once per '
                            'region regardless of how many cities/states share it -- writing one file per '
                            'timezone within each region.', style='Sub.TLabel',
                 wraplength=1000).grid(row=1, column=0, columnspan=4, sticky=W, padx=5, pady=4)
        ttk.Checkbutton(bulk, text='Skip regions where every timezone already has a processed file for this '
                                   'year (uses the Year field in the Single City card above)',
                       variable=skip_existing_var).grid(row=2, column=0, columnspan=4, sticky=W, padx=5, pady=4)

        def start_bulk(cancel_check, on_finally):
            year = parsed_year()
            if year is None:
                on_finally()
                return
            state_filter = None if bulk_state_var.get() == 'All States' else bulk_state_var.get()
            username, password = get_credentials()
            log.run(bulk_download_wattime, year, current_signal_type(), username, password, state_filter,
                   skip_existing_var.get(), cancel_check, log=log.log, on_finally=on_finally)

        self._make_stoppable_action(bulk, 'wattime_bulk', 'Run Bulk Update', start_bulk).grid(
            row=3, column=0, columnspan=4, sticky=W, padx=5, pady=(6, 4))

        examine = self._card(tab, '6. Examine')
        ex_var, ex_combo, ex_refresh = self._make_file_picker(examine, WATTTIME_PROCESSED_DIR, '*.csv')
        ttk.Label(examine, text='File:', style='Card.TLabel').grid(row=0, column=0, sticky=W, padx=5, pady=4)
        ex_combo.grid(row=0, column=1, sticky=W, padx=5, pady=4)
        ttk.Button(examine, text='Refresh List', command=ex_refresh).grid(row=0, column=2, padx=5, pady=4)

        def do_examine():
            if not ex_var.get():
                return
            path = os.path.join(WATTTIME_PROCESSED_DIR, ex_var.get())
            df = pd.read_csv(path)
            self._preview_dataframe(df, title=ex_var.get())
            if 'Emissivity' in df.columns:
                self._preview_series(df['Emissivity'].to_numpy(), title=f'Emissivity - {ex_var.get()} '
                                                                        f'(first 3 days)', ylabel='kg CO2/kWh')

        ttk.Button(examine, text='Preview', style='Accent.TButton', command=do_examine).grid(
            row=0, column=3, padx=5, pady=4)


if __name__ == '__main__':
    root = Tk()
    app = DataImportWizard(root)
    root.mainloop()
