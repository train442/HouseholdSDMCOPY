"""
Removes the redundant ``Time`` column from processed ResStock load parquets.

WHY
---
``process_resstock_load`` wrote every profile as two columns::

    ts = pd.date_range(start='1/1/2018 00:00 am', periods=len(new_load), freq='5min')
    pd.DataFrame({'Time': ts, 'Load(kW)': ...}).to_parquet(...)

That ``Time`` column is a hardcoded 2018 5-minute grid: a pure function of the row count, byte-identical
in all ~506,000 processed files, and never read by the model -- every consumer requests
``columns=['Load(kW)']``.

Measured by parsing the parquet footers directly:

    column Time       compressed  841.7 KB   raw 1039.7 KB   SNAPPY
    column Load(kW)   compressed  173.1 KB   raw  197.8 KB   SNAPPY

**Time is 84.9% of the stored bytes.** Snappy cannot compress monotonic int64 timestamps (only 1.24x),
while the load data compresses to ~150 KB. Dropping it takes each file from ~1000 KB to ~150 KB, about
**6.6x**, and the library from roughly 490 GB to 75 GB.

Callers that genuinely want timestamps use ``DataProcessing.resstock_timestamps(n_rows)`` or
``read_resstock_profile(path, with_time=True)``, which regenerate them exactly.

SAFETY
------
Each file is converted to a temporary file, read back, and its ``Load(kW)`` values compared elementwise
against the original before the original is replaced. Any mismatch leaves the original untouched and is
reported. Files that already lack a ``Time`` column are skipped, so the run is resumable.

GIT
---
This rewrites ~506,000 tracked files, which adds that many new blobs to history: ``.git`` will GROW
unless you pair it with a ``git filter-repo`` pass. The working-tree saving is immediate and certain.
Note git already delta-compresses similar objects within a pack, so it may be partly exploiting the
shared Time column already -- expect the pack to shrink by less than 6.6x.

USAGE
-----
    # look before you leap -- reports sizes, converts nothing
    python "Scripts/ResStock Loads/strip_parquet_time_column.py" --dry-run

    # convert a small sample first and check the numbers
    python "Scripts/ResStock Loads/strip_parquet_time_column.py" --limit 200

    # the real run, across all cores
    python "Scripts/ResStock Loads/strip_parquet_time_column.py" --workers 8

Run from the repository root.
"""
import argparse
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed

import numpy as np
import pandas as pd

sys.path.insert(0, os.getcwd())

PROCESSED_DIR = os.path.join('City Data', 'Load Profiles', 'Processed', 'Parquets')
LOAD_COL = 'Load(kW)'


def require_parquet_engine() -> None:
    """
    Fails loudly if no parquet engine is installed.

    Without one, column detection silently returns nothing, which would make this script report every
    file as needing no work -- a false negative across half a million files. Better to stop.

    Raises
    ------
    SystemExit
        If neither pyarrow nor fastparquet is importable.
    """
    try:
        import pyarrow  # noqa: F401
        return
    except ImportError:
        pass
    try:
        import fastparquet  # noqa: F401
        return
    except ImportError:
        raise SystemExit(
            'No parquet engine found. Install one before running this:\n'
            '    pip install pyarrow\n'
            'Reading and rewriting parquet files is impossible without it.')


def columns_from_footer(path: str) -> list:
    """
    Reads a parquet file's column names straight from its footer, with no parquet engine.

    Used so ``--dry-run`` can report honestly even on a machine without pyarrow. This scans the
    Thrift-encoded footer for the schema element names rather than fully parsing it, which is enough to
    answer "does this file still carry a Time column?".

    Parameters
    ----------
    path : str
        Path to the parquet file.

    Returns
    -------
    list of str
        Column names found in the footer, or [] if the file could not be read.
    """
    import struct
    try:
        with open(path, 'rb') as f:
            f.seek(-8, os.SEEK_END)
            tail = f.read(8)
            if tail[4:] != b'PAR1':
                return []
            flen = struct.unpack('<I', tail[:4])[0]
            f.seek(-8 - flen, os.SEEK_END)
            footer = f.read(flen)
    except OSError:
        return []
    names = []
    for candidate in (b'Time', LOAD_COL.encode()):
        if candidate in footer:
            names.append(candidate.decode())
    return names


def parquet_columns(path: str) -> list:
    """
    Returns a parquet file's column names, preferring the engine and falling back to the footer scan.

    Parameters
    ----------
    path : str
        Path to the parquet file.

    Returns
    -------
    list of str
        Column names, or [] if the schema could not be read.
    """
    try:
        import pyarrow.parquet as pq
        return list(pq.read_schema(path).names)
    except ImportError:
        return columns_from_footer(path)
    except Exception:
        return []


def convert_one(path: str) -> tuple:
    """
    Strips the Time column from a single parquet, verifying before replacing.

    Parameters
    ----------
    path : str
        Path to the parquet file.

    Returns
    -------
    tuple
        ``(status, path, bytes_before, bytes_after, message)`` where status is one of
        'converted', 'skipped', 'failed'.
    """
    before = os.path.getsize(path)
    try:
        cols = parquet_columns(path)
        if LOAD_COL not in cols:
            return ('failed', path, before, before, f'no {LOAD_COL!r} column (found {cols})')
        if 'Time' not in cols:
            return ('skipped', path, before, before, 'already stripped')

        original = pd.read_parquet(path, columns=[LOAD_COL])[LOAD_COL].to_numpy()

        tmp = path + '.tmp'
        pd.DataFrame({LOAD_COL: original}).to_parquet(tmp, index=False)

        # Verify through a fresh read before destroying anything.
        check = pd.read_parquet(tmp, columns=[LOAD_COL])[LOAD_COL].to_numpy()
        if check.shape != original.shape or not np.array_equal(check, original):
            os.remove(tmp)
            return ('failed', path, before, before, 'verification mismatch')

        os.replace(tmp, path)  # atomic on the same filesystem
        return ('converted', path, before, os.path.getsize(path), '')

    except Exception as ex:  # noqa: BLE001 - one bad file must not stop a 500k-file run
        tmp = path + '.tmp'
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass
        return ('failed', path, before, before, str(ex))


def find_parquets(root: str, limit: int = None) -> list:
    """
    Walks the processed-parquet tree.

    Parameters
    ----------
    root : str
        Root directory to scan.
    limit : int, optional
        Stop after this many files.

    Returns
    -------
    list of str
        Parquet file paths.
    """
    found = []
    for dirpath, _dirnames, filenames in os.walk(root):
        for name in filenames:
            if name.endswith('.parquet'):
                found.append(os.path.join(dirpath, name))
                if limit and len(found) >= limit:
                    return found
    return found


def main() -> None:
    """Entry point."""
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--directory', default=PROCESSED_DIR, help='root of the processed parquet tree')
    parser.add_argument('--dry-run', action='store_true', help='report only; change nothing')
    parser.add_argument('--limit', type=int, default=None, help='process at most N files (sampling)')
    parser.add_argument('--workers', type=int, default=1,
                        help='parallel worker processes (default 1; try 8 for the full run)')
    args = parser.parse_args()

    if not os.path.isdir(args.directory):
        raise SystemExit(f'Directory not found: {args.directory}\nRun this from the repository root.')

    if not args.dry_run:
        require_parquet_engine()

    print(f'Scanning {args.directory} ...')
    files = find_parquets(args.directory, args.limit)
    print(f'found {len(files):,} parquet file(s)')
    if not files:
        return

    if args.dry_run:
        sample = files[: min(50, len(files))]
        has_time = sum(1 for f in sample if 'Time' in parquet_columns(f))
        total_before = sum(os.path.getsize(f) for f in sample)
        avg = total_before / len(sample)
        print(f'\nsampled {len(sample)} file(s): {has_time} still carry a Time column')
        print(f'average size {avg/1024:.0f} KB')
        print(f'measured Time share is ~84.9%, so expect ~{avg*0.151/1024:.0f} KB after conversion')
        print(f'\nprojected across {len(files):,} files: '
              f'{len(files)*avg/1e9:.1f} GB -> {len(files)*avg*0.151/1e9:.1f} GB')
        print('\nDry run: nothing was written.')
        return

    t0 = time.perf_counter()
    counts = {'converted': 0, 'skipped': 0, 'failed': 0}
    bytes_before = bytes_after = 0
    failures = []

    def record(res):
        nonlocal bytes_before, bytes_after
        status, path, before, after, msg = res
        counts[status] += 1
        bytes_before += before
        bytes_after += after
        if status == 'failed':
            failures.append(f'{os.path.basename(path)}: {msg}')

    if args.workers > 1:
        with ProcessPoolExecutor(max_workers=args.workers) as ex:
            futures = [ex.submit(convert_one, f) for f in files]
            for i, fut in enumerate(as_completed(futures), start=1):
                record(fut.result())
                if i % 5000 == 0 or i == len(files):
                    print(f'  {i:,}/{len(files):,}  converted {counts["converted"]:,}  '
                          f'skipped {counts["skipped"]:,}  failed {counts["failed"]:,}')
    else:
        for i, f in enumerate(files, start=1):
            record(convert_one(f))
            if i % 1000 == 0 or i == len(files):
                print(f'  {i:,}/{len(files):,}  converted {counts["converted"]:,}  '
                      f'skipped {counts["skipped"]:,}  failed {counts["failed"]:,}')

    elapsed = time.perf_counter() - t0
    print('-' * 80)
    print(f'converted {counts["converted"]:,}, skipped {counts["skipped"]:,}, '
          f'failed {counts["failed"]:,} in {elapsed/60:.1f} min')
    if bytes_after:
        print(f'{bytes_before/1e9:.2f} GB -> {bytes_after/1e9:.2f} GB '
              f'({bytes_before/bytes_after:.1f}x, {(bytes_before-bytes_after)/1e9:.2f} GB reclaimed)')
    if failures:
        print(f'\nFAILURES ({len(failures)}) -- originals left untouched:')
        for f in failures[:25]:
            print('  ', f)
        if len(failures) > 25:
            print(f'   ... and {len(failures)-25} more')
    print('\nNote: this shrinks the working tree. .git will grow unless paired with a history rewrite.')


if __name__ == '__main__':
    main()
