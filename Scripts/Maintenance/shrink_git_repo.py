"""
Guided helper for reducing the size of the HouseholdSim git repository.

CONTEXT
-------
Measured on this repo: a 79.23 GiB pack across 608,605 objects, from only 140 commits. Almost nothing
is unreachable, so ``git gc`` alone reclaims very little. The bulk is tracked data:

    City Data/Load Profiles/Processed   506,451 files   ResStock library, regenerable via the Wizard
    Outputs/                            125,227 files   simulation results, regenerable by re-running
    Archive/Old Outputs/                 41,642 files   superseded results (42.5 MB pickles each)

``.gitignore`` currently covers only credentials and ``__pycache__``, so every simulation run has been
committing its results into history. That is the ongoing growth, and stage 2 stops it.

STAGES
------
Each stage is progressively more invasive. Run them in order and stop wherever you are comfortable.

    analyze        Report what is consuming the repository. Changes nothing.
    gc             Expire reflogs and repack. Safe. Recovers only unreachable objects (~200 MB here).
    stop-bleeding  .gitignore + 'git rm --cached' for generated data. No history rewrite, no space
                   reclaimed, but the repo stops growing. Safe and revertible by a normal commit.
    rewrite        Purge paths from ALL history with git-filter-repo, then aggressively repack. This
                   is what actually reclaims the pack. IRREVERSIBLE. Rewrites every commit SHA.

Every stage defaults to a dry run. Nothing happens without ``--apply``, and ``rewrite`` additionally
requires ``--i-have-a-backup`` plus a typed confirmation.

USAGE
-----
    python Scripts/Maintenance/shrink_git_repo.py analyze
    python Scripts/Maintenance/shrink_git_repo.py gc --apply
    python Scripts/Maintenance/shrink_git_repo.py stop-bleeding
    python Scripts/Maintenance/shrink_git_repo.py stop-bleeding --apply
    python Scripts/Maintenance/shrink_git_repo.py rewrite --preset results
    python Scripts/Maintenance/shrink_git_repo.py rewrite --preset results --apply --i-have-a-backup

Run from the repository root.
"""
import argparse
import os
import shutil
import subprocess
import sys

# Paths that are pure generated output: results you can recreate by re-running the model.
RESULTS_PATHS = [
    'Outputs/',
    'Archive/Old Outputs/',
]

# Downloaded source data: regenerable through DataImportWizard, but expensive to re-acquire.
DATA_PATHS = [
    'City Data/Load Profiles/Processed/',
]

PRESETS = {
    # Only the ResStock load library. Leaves Outputs/, Archive/ and ALL code history untouched.
    'loads': DATA_PATHS,
    # Only generated results.
    'results': RESULTS_PATHS,
    # Alias kept for the earlier naming.
    'data': DATA_PATHS,
    'all': RESULTS_PATHS + DATA_PATHS,
}

PRESET_HELP = {
    'loads': 'ResStock load library only (506,451 files) -- code, Outputs and Archive history kept',
    'results': 'Outputs/ and Archive/Old Outputs/ (166,869 files) -- generated results only',
    'data': 'alias for "loads"',
    'all': 'both the load library and generated results',
}

GITIGNORE_BLOCK = """
# ---- Generated simulation output -------------------------------------------------
# Results are reproducible by re-running the model, and committing them was the main
# driver of repository growth (125,227 tracked files under Outputs/ alone).
Outputs/
Archive/Old Outputs/

# Scratch files left by the parquet migration script.
*.parquet.tmp
"""


def run(cmd, capture=True, check=False):
    """
    Runs a command, returning (returncode, stdout).

    Parameters
    ----------
    cmd : list of str
        Command and arguments.
    capture : bool, optional
        Capture stdout rather than streaming it. Default True.
    check : bool, optional
        Raise on a non-zero exit. Default False.

    Returns
    -------
    tuple
        ``(returncode, stdout_text)``.
    """
    if capture:
        p = subprocess.run(cmd, capture_output=True, text=True)
        if check and p.returncode:
            raise SystemExit(f'command failed: {" ".join(cmd)}\n{p.stderr}')
        return p.returncode, (p.stdout or '') + (p.stderr or '')
    p = subprocess.run(cmd)
    if check and p.returncode:
        raise SystemExit(f'command failed: {" ".join(cmd)}')
    return p.returncode, ''


def preflight(require_clean=True):
    """
    Verifies we are in a git repository and, optionally, that the working tree is clean.

    Parameters
    ----------
    require_clean : bool, optional
        Refuse to continue with uncommitted changes. Default True.

    Returns
    -------
    None
    """
    if shutil.which('git') is None:
        raise SystemExit('git is not on PATH.')
    rc, _ = run(['git', 'rev-parse', '--git-dir'])
    if rc:
        raise SystemExit('Not a git repository. Run this from the repository root.')
    if require_clean:
        # -uno skips the scan for untracked files. On this repo git still has to refresh an index of
        # ~630,000 entries, which takes a while on a cold cache -- warn rather than appear hung.
        print('checking working tree is clean (this can take a minute on a repo this large)...',
              flush=True)
        rc, out = run(['git', 'status', '--porcelain', '-uno'])
        if out.strip():
            n = len(out.strip().splitlines())
            preview = '\n  '.join(out.strip().splitlines()[:10])
            raise SystemExit(
                f'Working tree has {n} uncommitted change(s) to tracked files:\n  {preview}\n'
                'Commit or stash them first -- these operations must not be mixed with unsaved work.\n'
                '(Use --skip-clean-check to override, only if you know what you are doing.)')


def pack_size():
    """
    Returns the human-readable pack size reported by git.

    Returns
    -------
    str
        The size-pack line, or 'unknown'.
    """
    _, out = run(['git', 'count-objects', '-vH'])
    for line in out.splitlines():
        if line.startswith('size-pack:'):
            return line.split(':', 1)[1].strip()
    return 'unknown'


def have_filter_repo():
    """
    Returns whether git-filter-repo is available.

    Returns
    -------
    bool
    """
    rc, _ = run(['git', 'filter-repo', '--version'])
    return rc == 0


def cmd_analyze(args):
    """Reports what is consuming the repository."""
    preflight(require_clean=False)
    print(f'pack size          : {pack_size()}')
    _, out = run(['git', 'rev-list', '--count', 'HEAD'])
    print(f'commits            : {out.strip()}')
    _, out = run(['git', 'count-objects', '-v'])
    for line in out.splitlines():
        if line.startswith(('count:', 'in-pack:', 'packs:')):
            print(f'{line.split(":")[0]:19s}: {line.split(":",1)[1].strip()}')

    print('\ntracked file counts for the candidate paths:')
    for path in RESULTS_PATHS + DATA_PATHS:
        _, out = run(['git', 'ls-files', '--', path.rstrip('/')])
        n = len([x for x in out.splitlines() if x.strip()])
        print(f'  {n:>9,}  {path}')

    if have_filter_repo():
        print('\ngit-filter-repo is installed. For an authoritative per-path breakdown of what is')
        print('actually consuming the PACK (not just the working tree), run:')
        print('    git filter-repo --analyze')
        print('then read .git/filter-repo/analysis/path-all-sizes.txt')
    else:
        print('\ngit-filter-repo is NOT installed. Install it for the authoritative size report:')
        print('    pip install git-filter-repo')
        print('Tree sizes alone are misleading here: pickles compress ~9x while parquets barely')
        print('compress but deduplicate heavily, so packed cost per path cannot be inferred from disk.')


def cmd_gc(args):
    """Expires reflogs and repacks. Safe."""
    preflight(require_clean=False)
    before = pack_size()
    steps = [
        ['git', 'reflog', 'expire', '--expire=now', '--all'],
        ['git', 'gc', '--prune=now'],
    ]
    print(f'pack before: {before}')
    for c in steps:
        print('  $', ' '.join(c))
    if not args.apply:
        print('\nDry run. Re-run with --apply to execute.')
        return
    for c in steps:
        run(c, capture=False, check=False)
    print(f'\npack after : {pack_size()}')
    print('Note: this only reclaims UNREACHABLE objects. Reachable history is untouched.')


def cmd_stop_bleeding(args):
    """Adds generated output to .gitignore and untracks it, without touching history."""
    preflight(require_clean=not args.skip_clean_check)
    paths = PRESETS['results']
    print('This will:')
    print('  1. append a block to .gitignore covering:', ', '.join(paths))
    print('  2. git rm -r --cached those paths (files STAY on disk)')
    print('  3. leave you a staged commit to review\n')

    existing = ''
    if os.path.exists('.gitignore'):
        existing = open('.gitignore', encoding='utf-8').read()
    already = 'Outputs/' in existing

    for path in paths:
        _, out = run(['git', 'ls-files', '--', path.rstrip('/')])
        n = len([x for x in out.splitlines() if x.strip()])
        print(f'  would untrack {n:>9,} file(s) from {path}')
    print(f'\n.gitignore already covers Outputs/: {already}')

    if not args.apply:
        print('\nDry run. Re-run with --apply to execute.')
        return

    if not already:
        with open('.gitignore', 'a', encoding='utf-8') as f:
            f.write(GITIGNORE_BLOCK)
        print('appended to .gitignore')

    for path in paths:
        run(['git', 'rm', '-r', '--cached', '--quiet', '--ignore-unmatch', path.rstrip('/')],
            capture=False)
    run(['git', 'add', '.gitignore'], capture=False)
    print('\nStaged. Review with "git status" then commit, e.g.:')
    print('    git commit -m "Stop tracking generated simulation output"')
    print('\nFiles remain on disk. This does not shrink .git -- it stops it growing.')


def cmd_rewrite(args):
    """Purges paths from all history with git-filter-repo. Irreversible."""
    preflight(require_clean=not args.skip_clean_check)
    if not have_filter_repo():
        raise SystemExit('git-filter-repo is not installed.\n    pip install git-filter-repo')

    paths = PRESETS[args.preset] if args.preset else args.path
    if not paths:
        raise SystemExit('Specify --preset {results,data,all} or one or more --path values.')

    cmd = ['git', 'filter-repo', '--invert-paths']
    for p in paths:
        cmd += ['--path', p]
    if args.force:
        cmd.append('--force')

    print('THIS REWRITES EVERY COMMIT IN THE REPOSITORY. It cannot be undone.\n')
    print('Paths to purge from all history:')
    for p in paths:
        print('   ', p)
    print('\nCommand:')
    print('   $', ' '.join(cmd))
    print('   $ git gc --prune=now --aggressive')
    print(f'\npack size now: {pack_size()}')
    print('\nWhat is PRESERVED:')
    print('  * every other file keeps its full history -- all versions, diffs and commit messages.')
    print('    Only the listed paths are removed. Your .py files are untouched in content.')
    print('\nConsequences:')
    print('  * every commit SHA changes (a commit hash depends on its tree), so any link or note')
    print('    referencing a specific hash will break')
    print('  * commits that touched ONLY the purged paths become empty and are dropped')
    print('  * collaborators must RE-CLONE, not pull (origin/schmidt-review-main suggests others)')
    print('  * git-filter-repo removes the "origin" remote afterward; you re-add it and force-push')
    print('  * the GitHub Enterprise server keeps old objects until ITS gc runs, so the remote will')
    print('    not shrink immediately -- you may need GT support to trigger it')
    print('  * purged files then exist ONLY in your working tree; back them up first')

    if not args.apply:
        print('\nDry run. Re-run with --apply --i-have-a-backup to execute.')
        return
    if not args.i_have_a_backup:
        raise SystemExit('\nRefusing to run without --i-have-a-backup.\n'
                         'Make one first:\n'
                         '    git clone --no-local . ../HouseholdSim-backup\n'
                         'and copy the data directories somewhere outside the repo.')

    typed = input('\nType exactly "rewrite history" to proceed: ')
    if typed.strip() != 'rewrite history':
        raise SystemExit('Aborted.')

    run(cmd, capture=False, check=True)
    run(['git', 'gc', '--prune=now', '--aggressive'], capture=False)
    print(f'\npack size after: {pack_size()}')
    print('\nNext:')
    print('    git remote add origin <your remote url>')
    print('    git push --force --all origin')
    print('    git push --force --tags origin')
    print('\nThe purged files are still on disk but no longer tracked. To keep them in the repo with')
    print('a single slim version instead of the whole fat history, add them back as one new commit:')
    for p in paths:
        print(f'    git add "{p}"')
    print('    git commit -m "Re-add data at current size"')


def main():
    """Entry point."""
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    # Not required, so running the script bare prints usable guidance instead of an argparse error.
    sub = parser.add_subparsers(dest='stage')

    p = sub.add_parser('analyze', help='report what is consuming the repository')
    p.set_defaults(func=cmd_analyze)

    p = sub.add_parser('gc', help='expire reflogs and repack (safe)')
    p.add_argument('--apply', action='store_true')
    p.set_defaults(func=cmd_gc)

    p = sub.add_parser('stop-bleeding', help='untrack generated output (safe, no rewrite)')
    p.add_argument('--apply', action='store_true')
    p.add_argument('--skip-clean-check', action='store_true',
                   help='skip the slow working-tree cleanliness check')
    p.set_defaults(func=cmd_stop_bleeding)

    p = sub.add_parser('rewrite', help='purge paths from all history (IRREVERSIBLE)')
    p.add_argument('--preset', choices=sorted(PRESETS),
                   help='; '.join(f'{k}: {v}' for k, v in PRESET_HELP.items()))
    p.add_argument('--path', action='append', default=[], help='explicit path (repeatable)')
    p.add_argument('--apply', action='store_true')
    p.add_argument('--i-have-a-backup', action='store_true')
    p.add_argument('--force', action='store_true', help='pass --force to git filter-repo')
    p.add_argument('--skip-clean-check', action='store_true',
                   help='skip the slow working-tree cleanliness check')
    p.set_defaults(func=cmd_rewrite)

    args = parser.parse_args()

    if not args.stage:
        print(__doc__.strip())
        print('\n' + '=' * 78)
        print('Pick a stage. Nothing below changes anything unless you add --apply.\n')
        print('  1. See what is going on (safe, read-only):')
        print('       python Scripts/Maintenance/shrink_git_repo.py analyze\n')
        print('  2. Stop the repo growing (safe, no history rewrite):')
        print('       python Scripts/Maintenance/shrink_git_repo.py stop-bleeding')
        print('       python Scripts/Maintenance/shrink_git_repo.py stop-bleeding --apply\n')
        print('  3. Reclaim unreachable objects (safe, small gain here):')
        print('       python Scripts/Maintenance/shrink_git_repo.py gc --apply\n')
        print('  4. Actually shrink the pack (IRREVERSIBLE, needs a backup):')
        print('       python Scripts/Maintenance/shrink_git_repo.py rewrite --preset results')
        print('=' * 78)
        raise SystemExit(0)

    args.func(args)


if __name__ == '__main__':
    main()
