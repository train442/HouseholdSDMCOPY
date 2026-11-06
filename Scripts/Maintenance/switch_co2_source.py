"""
Switches scenario input files between the Cambium and WattTime grid-CO2 sources.

WHY THIS IS NOT JUST A FLAG FLIP
--------------------------------
The existing input workbooks carry a ``Use Cambium`` column but **no** ``Use WattTime`` column.
``Simulation.make_grid`` resolves the CO2 source in this order::

    if use_cambium:            -> Cambium profile
    elif use_wattime:          -> WattTime profile
    elif 'Other File' set:     -> that file
    else:                      -> flat rate from the city's carbon intensity

So clearing ``Use Cambium`` on its own does not select WattTime -- it silently falls through to the
city's flat carbon intensity, which looks like it worked and quietly changes your results. This script
therefore adds the ``Use WattTime`` column when it is missing.

``WattTime Year`` is deliberately left absent, so ``make_grid`` uses ``WATTTIME_DEFAULT_YEAR`` (2024).

COVERAGE
--------
A WattTime profile must exist for each scenario's reference city, named
``{region}_{timezone}_WattTime_{year}.csv`` under ``City Data/CO2 Profiles/WattTime/Processed``.
Where it does not, the run fails at ``make_grid`` with a missing-file error. Use ``--check`` to report
coverage before switching, and the Data Import Wizard's WattTime tab to fetch what is missing.

USAGE
-----
    python Scripts/Maintenance/switch_co2_source.py --check
    python Scripts/Maintenance/switch_co2_source.py --to wattime --dry-run
    python Scripts/Maintenance/switch_co2_source.py --to wattime --limit 5
    python Scripts/Maintenance/switch_co2_source.py --to wattime --workers 8
    python Scripts/Maintenance/switch_co2_source.py --to cambium --workers 8   # revert

Run from the repository root.
"""
import argparse
import glob
import os
import re
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed

import pandas as pd

sys.path.insert(0, os.getcwd())

HEADER_ROW = 3           # row holding the column names; data starts at row 4
FIRST_DATA_ROW = 4
CAMBIUM_COL = 'Use Cambium'
WATTTIME_COL = 'Use WattTime'
DEFAULT_YEAR = 2024
WATTTIME_DIR = os.path.join('City Data', 'CO2 Profiles', 'WattTime', 'Processed')
CITY_LIST = os.path.join('Model Data', 'city_list_refined.csv')
NAME_RE = re.compile(r'F\d+_[A-Z]{2}_\d+_[A-Z]{3}_(.+)_([A-Z]{2})\.xlsx$')


def header_map(ws) -> dict:
    """
    Returns {column name: column index} from the workbook's header row.

    Parameters
    ----------
    ws : openpyxl worksheet
        The sheet to inspect.

    Returns
    -------
    dict
        Mapping of header text to 1-based column index.
    """
    return {ws.cell(row=HEADER_ROW, column=c).value: c
            for c in range(1, ws.max_column + 1)
            if ws.cell(row=HEADER_ROW, column=c).value}


def switch_one(path: str, target: str) -> tuple:
    """
    Rewrites one input workbook to use the requested CO2 source.

    Edits in place with openpyxl so all other columns, formatting and the two title rows above the
    header are preserved. A missing ``Use WattTime`` column is appended after the last column.

    Parameters
    ----------
    path : str
        Path to the .xlsx input file.
    target : str
        Either 'wattime' or 'cambium'.

    Returns
    -------
    tuple
        ``(status, path, n_rows, message)`` where status is 'switched', 'skipped' or 'failed'.
    """
    import openpyxl
    try:
        wb = openpyxl.load_workbook(path)
        ws = wb.active
        hdr = header_map(ws)
        if CAMBIUM_COL not in hdr:
            return ('failed', path, 0, f'no {CAMBIUM_COL!r} column (headers look wrong)')
        if ws.max_row < FIRST_DATA_ROW:
            return ('skipped', path, 0, 'no data rows')

        cam_c = hdr[CAMBIUM_COL]

        # Resumability: if the workbook is already in the target state, skip without rewriting.
        # Re-running after an interruption then costs a read rather than a read plus a save.
        if WATTTIME_COL in hdr:
            want_cam = (target == 'cambium')
            first = ws.cell(row=FIRST_DATA_ROW, column=cam_c).value
            first_wt = ws.cell(row=FIRST_DATA_ROW, column=hdr[WATTTIME_COL]).value
            last = ws.cell(row=ws.max_row, column=cam_c).value
            if bool(first) == want_cam and bool(first_wt) != want_cam and bool(last) == want_cam:
                wb.close()
                return ('skipped', path, 0, 'already in target state')

        if WATTTIME_COL in hdr:
            wt_c = hdr[WATTTIME_COL]
        else:
            wt_c = ws.max_column + 1
            ws.cell(row=HEADER_ROW, column=wt_c).value = WATTTIME_COL
            # mirror the header styling of the column it sits beside
            ws.cell(row=HEADER_ROW, column=wt_c)._style = ws.cell(row=HEADER_ROW, column=cam_c)._style

        use_cambium = (target == 'cambium')
        n = 0
        for r in range(FIRST_DATA_ROW, ws.max_row + 1):
            if ws.cell(row=r, column=1).value is None:   # blank trailing row
                continue
            ws.cell(row=r, column=cam_c).value = use_cambium
            ws.cell(row=r, column=wt_c).value = not use_cambium
            n += 1

        wb.save(path)
        return ('switched', path, n, '')
    except Exception as ex:  # noqa: BLE001 - one bad workbook must not stop a 993-file run
        return ('failed', path, 0, str(ex))


def verify_one(path: str, target: str) -> tuple:
    """
    Re-reads a workbook the way the model does and confirms the flags landed.

    Parameters
    ----------
    path : str
        Path to the .xlsx input file.
    target : str
        Either 'wattime' or 'cambium'.

    Returns
    -------
    tuple
        ``(ok, message)``.
    """
    try:
        frame = pd.read_excel(path, header=HEADER_ROW - 1)
        if CAMBIUM_COL not in frame.columns:
            return (False, f'{CAMBIUM_COL} missing after write')
        want_cam = (target == 'cambium')
        if not (frame[CAMBIUM_COL].astype(bool) == want_cam).all():
            return (False, f'{CAMBIUM_COL} not uniformly {want_cam}')
        if target == 'wattime':
            if WATTTIME_COL not in frame.columns:
                return (False, f'{WATTTIME_COL} column absent')
            if not frame[WATTTIME_COL].astype(bool).all():
                return (False, f'{WATTTIME_COL} not uniformly True')
        return (True, '')
    except Exception as ex:  # noqa: BLE001
        return (False, str(ex))


def coverage_report(files: list, year: int = DEFAULT_YEAR) -> tuple:
    """
    Reports which input files have a WattTime profile available for their reference city.

    Parameters
    ----------
    files : list of str
        Input workbook paths.
    year : int, optional
        WattTime year to look for. Defaults to the model's WATTTIME_DEFAULT_YEAR.

    Returns
    -------
    tuple
        ``(covered, missing, unparsed)`` lists.
    """
    cities = pd.read_csv(CITY_LIST)
    reg = {(r['State'], r['City']): (r['WattTime Region'], r['Time Zone'])
           for _, r in cities.iterrows()}
    have = {os.path.basename(p) for p in glob.glob(os.path.join(WATTTIME_DIR, '*.csv'))}

    covered, missing, unparsed = [], [], []
    for f in files:
        m = NAME_RE.match(os.path.basename(f))
        if not m:
            unparsed.append(f)
            continue
        city, st = m.group(1), m.group(2)
        if (st, city) not in reg:
            missing.append((f, f'{city}, {st} not in city_list_refined'))
            continue
        region, tz = reg[(st, city)]
        if pd.isna(region):
            missing.append((f, f'{city}, {st} has no WattTime region'))
            continue
        fn = f'{region}_{tz}_WattTime_{year}.csv'
        (covered if fn in have else missing).append((f, fn) if fn in have else (f, f'missing {fn}'))
    return covered, missing, unparsed


def main() -> None:
    """Entry point."""
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--to', choices=['wattime', 'cambium'],
                        help='CO2 source to switch the input files to')
    parser.add_argument('--directory', default='InputFiles', help='root of the input workbooks')
    parser.add_argument('--check', action='store_true', help='report WattTime coverage only')
    parser.add_argument('--dry-run', action='store_true', help='report what would change')
    parser.add_argument('--limit', type=int, default=None, help='process at most N files')
    parser.add_argument('--workers', type=int, default=1, help='parallel worker processes')
    parser.add_argument('--year', type=int, default=DEFAULT_YEAR, help='WattTime year for --check')
    args = parser.parse_args()

    files = sorted(glob.glob(os.path.join(args.directory, '*.xlsx')) +
                   glob.glob(os.path.join(args.directory, '*', '*.xlsx')))
    if args.limit:
        files = files[:args.limit]
    if not files:
        raise SystemExit(f'No .xlsx input files found under {args.directory}')

    if args.check or not args.to:
        covered, missing, unparsed = coverage_report(files, args.year)
        print(f'input files            : {len(files)}')
        print(f'  WattTime {args.year} available : {len(covered)}')
        print(f'  no profile            : {len(missing)}')
        print(f'  filename not parsed   : {len(unparsed)}')
        if missing:
            from collections import Counter
            print('\nmissing profiles (fetch these in the Wizard\'s WattTime tab):')
            for k, n in Counter(m[1] for m in missing).most_common(30):
                print(f'   {n:5d} files  {k}')
        if unparsed:
            print('\nfilenames not matching the F<n>_<ST>_<zip>_<TZ>_<City>_<ST> pattern '
                  '(coverage unknown, will still be switched):')
            for u in unparsed[:10]:
                print('   ', os.path.basename(u))
        if not args.to:
            print('\nNo --to given, so nothing was changed. Add --to wattime to switch.')
        return

    print(f'{"would switch" if args.dry_run else "switching"} {len(files)} file(s) to {args.to}')
    if args.dry_run:
        for f in files[:10]:
            print('   ', f)
        if len(files) > 10:
            print(f'    ... and {len(files)-10} more')
        print('\nDry run: nothing was written.')
        return

    t0 = time.perf_counter()
    counts = {'switched': 0, 'skipped': 0, 'failed': 0}
    failures = []

    def record(res):
        status, path, n, msg = res
        counts[status] += 1
        if status == 'failed':
            failures.append(f'{os.path.basename(path)}: {msg}')

    if args.workers > 1:
        with ProcessPoolExecutor(max_workers=args.workers) as ex:
            futs = [ex.submit(switch_one, f, args.to) for f in files]
            for i, fut in enumerate(as_completed(futs), 1):
                record(fut.result())
                if i % 50 == 0 or i == len(files):
                    print(f'  {i}/{len(files)}  switched {counts["switched"]}  failed {counts["failed"]}')
    else:
        for i, f in enumerate(files, 1):
            record(switch_one(f, args.to))
            if i % 25 == 0 or i == len(files):
                print(f'  {i}/{len(files)}  switched {counts["switched"]}  failed {counts["failed"]}')

    # Verify a sample by re-reading exactly as the model does.
    sample = files[:: max(1, len(files) // 20)][:20]
    bad = [(f, msg) for f in sample for ok, msg in [verify_one(f, args.to)] if not ok]

    print('-' * 78)
    print(f'switched {counts["switched"]}, skipped {counts["skipped"]}, failed {counts["failed"]} '
          f'in {time.perf_counter()-t0:.1f}s')
    print(f'verified {len(sample)} sampled file(s): {"all OK" if not bad else str(len(bad)) + " BAD"}')
    for f, msg in bad:
        print('   ', os.path.basename(f), '->', msg)
    if failures:
        print(f'\nFAILURES ({len(failures)}):')
        for f in failures[:20]:
            print('   ', f)


if __name__ == '__main__':
    main()
