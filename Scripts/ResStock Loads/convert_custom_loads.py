"""
Converts the Custom Loads library from legacy CSV to the compact .npz format.

WHY
---
A custom load profile was stored as a CSV holding a redundant ``Time`` column plus ``Load(kW)`` at
~16 significant digits: 4.18 MB for a 105,120-step year. The model throws the timestamps away (the
grid is a fixed 5-minute cadence) and rounds the values to 3 decimals on load, so nearly all of that
was written and re-parsed for nothing.

Measured on a real profile:

    legacy .csv     4.18 MB    72.0 ms to read
    new    .npz     0.22 MB     1.9 ms to read     19x smaller, 38x faster

Across the 356-file library that is roughly 1.45 GB -> 78 MB.

The conversion is lossless with respect to what the model actually uses: ``House.generate_load`` has
always rounded to 3 decimals, and this script verifies every converted file reproduces the original
rounded array exactly before the CSV is removed.

GIT
---
This deletes the CSVs and adds .npz files. That is a normal delete+add: history is untouched, no
force-push, and anyone with a clone just pulls. Note it does NOT shrink the .git directory -- the old
CSV blobs remain in history forever. The saving is in the working tree.

USAGE
-----
    python "Scripts/ResStock Loads/convert_custom_loads.py" --dry-run     # report only, change nothing
    python "Scripts/ResStock Loads/convert_custom_loads.py"               # convert, verify, delete CSVs
    python "Scripts/ResStock Loads/convert_custom_loads.py" --keep-csv    # convert and verify, keep CSVs

Run from the repository root.
"""
import argparse
import os
import sys
import time

import numpy as np
import pandas as pd

# Allow running directly from the Scripts subfolder.
sys.path.insert(0, os.getcwd())
import DataProcessing as dp  # noqa: E402


def read_legacy_csv(path: str) -> np.ndarray:
    """
    Reads a legacy load CSV exactly the way the old House.generate_load did.

    Parameters
    ----------
    path : str
        Path to the CSV.

    Returns
    -------
    ndarray
        The load values rounded to 3 decimals.
    """
    values = pd.read_csv(path, usecols=['Load(kW)']).to_numpy()
    return np.round(values.flatten(), 3)


def convert_directory(directory: str, delete_csv: bool = True, dry_run: bool = False) -> dict:
    """
    Converts every legacy CSV load profile in a directory to .npz.

    Each file is converted, read back, and compared against the original before the CSV is removed.
    A file whose .npz already exists is skipped. Any file that fails verification is left completely
    alone and reported.

    Parameters
    ----------
    directory : str
        Directory of load profiles, e.g. 'City Data/Load Profiles/Custom Loads/'.
    delete_csv : bool, optional
        Remove the CSV once its .npz is verified. Default True.
    dry_run : bool, optional
        Report what would happen without writing or deleting anything. Default False.

    Returns
    -------
    dict
        Counts and byte totals for the run.
    """
    csvs = sorted(f for f in os.listdir(directory) if f.endswith('.csv'))
    stats = {'converted': 0, 'skipped': 0, 'failed': 0, 'bytes_before': 0, 'bytes_after': 0,
             'failures': []}
    if not csvs:
        print(f'No legacy CSV profiles found in {directory}')
        return stats

    print(f'Found {len(csvs)} legacy CSV profile(s) in {directory}')
    print(f"{'file':58s} {'before':>9} {'after':>9} {'ratio':>7}  status")
    print('-' * 100)

    for name in csvs:
        csv_path = os.path.join(directory, name)
        stem = csv_path[:-4]
        npz_path = stem + '.npz'
        before = os.path.getsize(csv_path)
        stats['bytes_before'] += before

        if os.path.exists(npz_path):
            stats['skipped'] += 1
            stats['bytes_after'] += os.path.getsize(npz_path)
            print(f'{name[:58]:58s} {before/1e6:8.2f}M {"":>9} {"":>7}  skipped (.npz exists)')
            continue

        try:
            original = read_legacy_csv(csv_path)
            if dry_run:
                stats['converted'] += 1
                print(f'{name[:58]:58s} {before/1e6:8.2f}M {"":>9} {"":>7}  would convert')
                continue

            dp.save_load_profile(original, stem)
            # Verify through the same loader the model uses, not through the writer.
            roundtrip = dp.load_load_profile(npz_path)
            if roundtrip.shape != original.shape or not np.array_equal(roundtrip, original):
                os.remove(npz_path)
                stats['failed'] += 1
                stats['failures'].append(name)
                print(f'{name[:58]:58s} {before/1e6:8.2f}M {"":>9} {"":>7}  FAILED verification, left as-is')
                continue

            after = os.path.getsize(npz_path)
            stats['bytes_after'] += after
            stats['converted'] += 1
            if delete_csv:
                os.remove(csv_path)
            print(f'{name[:58]:58s} {before/1e6:8.2f}M {after/1e6:8.2f}M {before/after:6.1f}x  '
                  f'{"converted" if delete_csv else "converted (csv kept)"}')

        except Exception as ex:  # noqa: BLE001 - report and continue; one bad file must not stop the run
            stats['failed'] += 1
            stats['failures'].append(f'{name}: {ex}')
            print(f'{name[:58]:58s} {before/1e6:8.2f}M {"":>9} {"":>7}  ERROR: {ex}')

    return stats


def main() -> None:
    """Entry point."""
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--directory', default=dp.custom_loads_path,
                        help='directory of load profiles (default: the Custom Loads folder)')
    parser.add_argument('--dry-run', action='store_true', help='report only; write and delete nothing')
    parser.add_argument('--keep-csv', action='store_true', help='convert and verify but keep the CSVs')
    args = parser.parse_args()

    if not os.path.isdir(args.directory):
        raise SystemExit(f'Directory not found: {args.directory}\nRun this from the repository root.')

    t0 = time.perf_counter()
    stats = convert_directory(args.directory, delete_csv=not args.keep_csv, dry_run=args.dry_run)
    elapsed = time.perf_counter() - t0

    print('-' * 100)
    print(f"converted {stats['converted']}, skipped {stats['skipped']}, failed {stats['failed']} "
          f'in {elapsed:.1f}s')
    if stats['bytes_after']:
        saved = stats['bytes_before'] - stats['bytes_after']
        print(f"{stats['bytes_before']/1e9:.2f} GB -> {stats['bytes_after']/1e9:.2f} GB "
              f"({stats['bytes_before']/stats['bytes_after']:.1f}x, {saved/1e9:.2f} GB reclaimed)")
    if stats['failures']:
        print('\nFAILURES (originals left untouched):')
        for f in stats['failures']:
            print('  ', f)
    if args.dry_run:
        print('\nDry run: nothing was written or deleted.')
    else:
        print('\nNote: this shrinks the working tree, not .git -- the old CSV blobs remain in history.')


if __name__ == '__main__':
    main()
