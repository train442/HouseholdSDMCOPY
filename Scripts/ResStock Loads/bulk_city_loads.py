"""
Bulk-downloads baseline (upgrade 0) ResStock load profiles for every reference city in Model Data/city_list.csv,
processes them to the model's 5-min parquet format, and rebuilds each city's load lookup table.

Same three steps as the Data Import Wizard's House Load tab (download_resstock_city -> process_resstock_city ->
build_load_lookup_city), restructured for a ~44,600-building / ~87 GB raw run:

-   The ResStock metadata is read once, not once per city.
-   Downloads run on a thread pool with retries/timeouts; processing runs on a process pool.
-   Downloads and processed files are written to '.part' and renamed on completion, so an interrupted run never
    leaves a truncated file that a resumed run would mistake for a finished one.
-   Fully resumable: anything already downloaded/processed/summarized is skipped. Just re-run it.

A city's existing lookup table is moved to LOOKUP_BACKUP_DIR (once -- a resumed run won't clobber the backup
with a half-rebuilt table) before the fresh one is built. The backup folder sits outside City Load Lookup
because custom_load_generate.py treats every entry in that folder as a city.

USAGE (from anywhere; the script chdirs to the repo root)
-----
    # what would run, per city, with building counts -- downloads nothing
    python "Scripts/ResStock Loads/bulk_city_loads.py" --dry-run

    # one small state first to sanity check
    python "Scripts/ResStock Loads/bulk_city_loads.py" --states VT

    # the full run; --delete-raw frees each city's ~2 MB/building raw parquets once its lookup is built
    python "Scripts/ResStock Loads/bulk_city_loads.py" --download-workers 24 --process-workers 8
"""
import argparse
import os
import shutil
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor, as_completed

import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
os.chdir(REPO_ROOT)
sys.path.insert(0, REPO_ROOT)
import DataProcessing as dp  # noqa: E402

# city_list.csv name -> ResStock 'in.city' name, where they differ
META_ALIAS = {
    ('IN', 'Indianapolis'): 'Indianapolis City Balance',
    ('MO', 'St. Louis'): 'St Louis',
}
UPGRADE = 0
LOOKUP_DIR = 'City Data/Load Profiles/City Load Lookup'
LOOKUP_BACKUP_DIR = 'City Data/Load Profiles/City Load Lookup (old440)'
LOG_DIR = 'City Data/Load Profiles/Unprocessed'  # gitignored

_thread_local = threading.local()


def _session() -> requests.Session:
    session = getattr(_thread_local, 'session', None)
    if session is None:
        session = requests.Session()
        retry = Retry(total=6, backoff_factor=2, status_forcelist=[429, 500, 502, 503, 504],
                      allowed_methods=['GET'])
        session.mount('https://', HTTPAdapter(max_retries=retry))
        _thread_local.session = session
    return session


def download_one(url: str, out_path: str) -> None:
    tmp = out_path + '.part'
    response = _session().get(url, timeout=(15, 180))
    response.raise_for_status()
    with open(tmp, 'wb') as f:
        f.write(response.content)
    os.replace(tmp, out_path)


def process_one(src: str, dst: str) -> None:
    tmp = dst + '.part'
    dp.process_resstock_load(src, tmp)
    os.replace(tmp, dst)


def run_city(state, city, bldg_ids, wiz, args, download_pool, process_pool, log):
    raw_dir = os.path.join(wiz.LOAD_PARQUET_RAW_DIR, state, city)
    proc_dir = os.path.join(wiz.LOAD_PARQUET_PROCESSED_DIR, state, city)
    os.makedirs(raw_dir, exist_ok=True)
    os.makedirs(proc_dir, exist_ok=True)

    names = [f'{b}-{UPGRADE}' for b in bldg_ids]
    raw_path = {n: os.path.join(raw_dir, n + '.parquet') for n in names}
    proc_path = {n: os.path.join(proc_dir, n + '_5min.parquet') for n in names}
    errors = []

    # 1. Download (skipping anything already processed, so --delete-raw runs stay resumable)
    to_get = [n for n in names if not os.path.exists(proc_path[n]) and not os.path.exists(raw_path[n])]
    t0 = time.time()
    futures = {download_pool.submit(download_one, f'{wiz.RESSTOCK_BASE_URL}{UPGRADE}/state={state}/{n}.parquet',
                                    raw_path[n]): n for n in to_get}
    for i, fut in enumerate(as_completed(futures), 1):
        try:
            fut.result()
        except Exception as ex:
            errors.append(f'download {futures[fut]}: {ex}')
        if i % 250 == 0:
            log(f'    downloaded {i}/{len(to_get)} ({i / (time.time() - t0):.1f} files/s)')
    if to_get:
        log(f'  downloaded {len(to_get) - len(errors)}/{len(to_get)} in {time.time() - t0:.0f}s')

    # 2. Process 15-min raw -> 5-min processed
    to_proc = [n for n in names if not os.path.exists(proc_path[n]) and os.path.exists(raw_path[n])]
    t0 = time.time()
    futures = {process_pool.submit(process_one, raw_path[n], proc_path[n]): n for n in to_proc}
    for fut in as_completed(futures):
        try:
            fut.result()
        except Exception as ex:
            n = futures[fut]
            errors.append(f'process {n}: {ex}')
            # most likely a corrupt raw file -- drop it so the next run re-downloads it
            if os.path.exists(raw_path[n]):
                os.remove(raw_path[n])
    if to_proc:
        log(f'  processed {len(to_proc)} in {time.time() - t0:.0f}s')

    # 3. Fresh lookup: move the stale table aside once, then (re)build -- build_load_lookup is itself resumable
    lookup = os.path.join(LOOKUP_DIR, f'{state}_{city}_loads.csv')
    backup = os.path.join(LOOKUP_BACKUP_DIR, f'{state}_{city}_loads.csv')
    if os.path.exists(lookup) and not os.path.exists(backup):
        os.makedirs(LOOKUP_BACKUP_DIR, exist_ok=True)
        os.replace(lookup, backup)
    wiz.build_load_lookup_city(state, city, log=lambda m: log('  ' + m))

    if args.delete_raw and not errors:
        shutil.rmtree(raw_dir, ignore_errors=True)

    missing = sum(not os.path.exists(proc_path[n]) for n in names)
    if missing:
        errors.append(f'{missing} of {len(names)} buildings still unprocessed -- re-run to retry')
    return errors


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--states', nargs='*', help='Only these state abbreviations (eg VT GA)')
    parser.add_argument('--cities', nargs='*', help='Only these city names (as in city_list.csv)')
    parser.add_argument('--download-workers', type=int, default=16)
    parser.add_argument('--process-workers', type=int, default=max(1, (os.cpu_count() or 2) - 1))
    parser.add_argument('--delete-raw', action='store_true',
                        help="Delete a city's raw parquets once it finishes cleanly")
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()

    import DataImportWizard as wiz  # here, not at module level, so process-pool workers don't import tkinter

    log_path = os.path.join(REPO_ROOT, LOG_DIR, f'bulk_city_loads_{time.strftime("%Y%m%d_%H%M%S")}.log')
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    log_file = open(log_path, 'a', encoding='utf-8')
    log_lock = threading.Lock()

    def log(msg):
        line = f'[{time.strftime("%H:%M:%S")}] {msg}'
        with log_lock:
            print(line, flush=True)
            log_file.write(line + '\n')
            log_file.flush()

    meta = pd.read_csv(wiz.RESSTOCK_METADATA_PATH,
                       usecols=['bldg_id', 'upgrade', 'in.state', 'in.city', 'in.geometry_building_type_acs'])
    meta = meta[meta['in.geometry_building_type_acs'].isin(wiz.ACCEPTABLE_HOUSE_TYPES) & (meta['upgrade'] == UPGRADE)]
    bldgs_by_city = meta.groupby(['in.state', 'in.city'])['bldg_id'].apply(list).to_dict()

    cities = pd.read_csv(wiz.CITY_LIST_PATH)
    if args.states:
        cities = cities[cities['State'].isin(args.states)]
    if args.cities:
        cities = cities[cities['City'].isin(args.cities)]

    plan = []
    for state, city in zip(cities['State'], cities['City']):
        bldg_ids = bldgs_by_city.get((state, META_ALIAS.get((state, city), city)), [])
        plan.append((state, city, bldg_ids))
    total = sum(len(b) for _, _, b in plan)
    log(f'{len(plan)} cities, {total} buildings (upgrade {UPGRADE}, single-family). Log: {log_path}')

    if args.dry_run:
        for state, city, bldg_ids in plan:
            proc_dir = os.path.join(wiz.LOAD_PARQUET_PROCESSED_DIR, state, city)
            have = sum(os.path.exists(os.path.join(proc_dir, f'{b}-{UPGRADE}_5min.parquet')) for b in bldg_ids)
            log(f'  {state} {city}: {len(bldg_ids)} buildings, {have} already processed')
        return

    failures = []
    t_start = time.time()
    with ThreadPoolExecutor(args.download_workers) as download_pool, \
            ProcessPoolExecutor(args.process_workers) as process_pool:
        for i, (state, city, bldg_ids) in enumerate(plan, 1):
            log(f'[{i}/{len(plan)}] {city}, {state}: {len(bldg_ids)} buildings')
            if not bldg_ids:
                failures.append((state, city, 'no matching buildings in ResStock metadata'))
                log('  FAILED: no matching buildings in ResStock metadata -- add a META_ALIAS entry?')
                continue
            try:
                errors = run_city(state, city, bldg_ids, wiz, args, download_pool, process_pool, log)
            except Exception as ex:
                errors = [f'{type(ex).__name__}: {ex}']
            if errors:
                failures.append((state, city, f'{len(errors)} error(s), first: {errors[0]}'))
                log(f'  FAILED ({len(errors)} error(s)), first: {errors[0]} -- continuing')
            else:
                log(f'  DONE {city}, {state}')

    log(f'Finished {len(plan)} cities in {(time.time() - t_start) / 3600:.2f} h. {len(failures)} with failures:')
    for state, city, msg in failures:
        log(f'  {city}, {state}: {msg}')
    if failures:
        log('Re-run the same command to retry -- completed work is skipped.')
    log_file.close()


if __name__ == '__main__':
    main()
