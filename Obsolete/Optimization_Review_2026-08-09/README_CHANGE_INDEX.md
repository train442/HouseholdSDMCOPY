# Optimization Review — August 2026

Annotated copies of the four modules as they stood **before** the optimization pass, for side-by-side
comparison against the live versions in the repository root.

## How these were produced

Your Tier 1 changes had already been committed to git (`04daab78`, bundled with the previous session's
refresh), and `HEAD^` is from November 2024 — so there was no clean pre-optimization commit to snapshot.
These files were reconstructed by reverse-applying every change, then **verified by execution**: running
the reconstruction reproduces the original benchmark timing and results that are bit-identical to the
pre-change golden baseline across 16 pickled `Results` objects and four 55-column summary CSVs.

They are review artifacts. Nothing imports them and nothing should.

## Files

| File | Annotations |
|---|---|
| `Components_PRE_OPTIMIZATION.py` | 17 |
| `Parameters_PRE_OPTIMIZATION.py` | 4 |
| `Simulation_PRE_OPTIMIZATION.py` | 11 |
| `runScenarioFiles_PRE_OPTIMIZATION.py` | 1 |

Each annotation sits directly above the code it describes, in a boxed comment block giving the reason,
the replacement, and the measured impact.

## Tags

| Tag | Meaning |
|---|---|
| `[T1-nn]` | Runtime work |
| `[T1.9-nn]` | Collection scheduling |
| `[T2-nn]` | Results storage |
| `[T3-nn]` | Correctness fixes |
| `[T4-nn]` | Conventions, typing, dead code |

All tags are now **applied** in the root modules. The `PROPOSED` status inside the annotation text
reflects the state at the time of writing, before you approved the remaining tiers.

## Index

### Runtime — Components.py

| Tag | Location | Change |
|---|---|---|
| T1-01 | module header | Cached readers for `efficiencies.xlsx`, `PVs.xlsx`, GHI CSV (~185 ms/scenario) |
| T1-02 | `initialize_cost_of_use` | `(N,1)` → `(N,)`; scalar-indexed writes 4.7× faster |
| T1-03 | `initialize_emissivity` | 1-D array, and a true float scalar |
| T1-04 | `initialize_socs` | 1-D |
| T1-05 | `initialize_energy_profile` | 1-D |
| T1-06 | `Grid.__init__` | `.ravel()` + Python-list fast path |
| T1-07 | `Grid.change_dates` | drop reshape to `(N,1)` |
| T1-08 | `Grid.update_emissivity` | list lookup instead of NumPy scalar boxing |
| T1-09 | `PV.__init__` | cached PV catalogue |
| T1-10 | `PV.load_solar` | cached arrays, `np.concatenate` instead of repeated `pd.concat` |
| T1-11 | `HES` coverage | `step in coverage_steps` → boolean mask (40×) |
| T1-12 | `HES.reset` | clear the mask between scenarios |
| T1-13 | `Fleet` | cache `has_evs`; fix stale `ev_num` in `clear_fleet` |
| T1-14 | `Energy.__init__` | 1-D trackers + nested-list efficiency mirror |
| T1-15 | `Energy.update_flow` | full rewrite — 6.06 s → 1.39 s self-time |

### Runtime — Parameters.py / Simulation.py

| Tag | Location | Change |
|---|---|---|
| T1-16 | Parameters header | cached efficiency matrix loader |
| T1-17 | `load_efficiencies` | delegate to the cache |
| T1-18 | `get_next_off_peak` | bounded widening window instead of scanning the rest of the year |
| T1-19 | Simulation header | integer component codes + `itemgetter` sort key |
| T1-20 | `Results.__init__` | drop `(N,1)` reshapes |
| T1-21 | `sinks_and_sources` | rewrite — 3.81 s → 2.05 s self-time |
| T1-22 | `energy_flows` | string comparisons → integer codes |
| T1-23 | `optimize_hes` | preallocate instead of `np.append` in a loop |
| T1-24 | `run_simulation` | allocate the coverage mask |

### Scheduling and storage

| Tag | Location | Change |
|---|---|---|
| T1.9-01 | `run_collection` | `schedule='auto' \| 'file' \| 'chunk'` |
| T2-01 | `run_model` | Parquet store, opt-in pickles, build-once summary |

### Correctness

| Tag | Location | Severity |
|---|---|---|
| T3-01 | `Tariff.get_coverage_steps` | `IndexError` on a column that doesn't exist |
| T3-02 | `rows_match` | **compared a row against itself** — silent component reuse |
| T3-03 | `Results.add_objects` | wrong key mapping, missing `energy` restore |
| T3-05 | `update_baseline_metrics` | divide-by-zero → `inf` in the summary CSV |
| T3-06 | `HES.soc_targets` | **`HES Avg SoC Target` wrong in every existing summary CSV** |
| T3-07 | `Energy.update_flow` | grid→EV credited the wrong vehicle in multi-EV fleets |
| T3-08 | `can_be_source_update` | annotation statement, not an assignment |

Two further bugs were found and fixed during the Tier 4 sweep, both in dead branches:
`DataProcessing.load_match_yearly` / `load_match_monthly` used `upgrade is list`, which compares
identity against the type object and is always False, so the upgrade filter never ran.

### Conventions

| Tag | Scope |
|---|---|
| T4-01 | `runScenarioFiles.py` reduced from 629 lines to a re-export shim; README corrected |

Also: ~45 bitwise `&`/`|` on scalar booleans converted to `and`/`or` (genuine pandas and NumPy masks
deliberately left alone), 8 unused imports and 17 unused locals removed, the
`from Parameters import *` wildcard in `Components.py` made explicit, and ~70 type annotations added
across `Components.py`.

## Known remaining lint

Two items are intentional and should stay:

- `from tkinter import *` in `ResultsGUI.py` and `DataImportWizard.py` — the standard tkinter idiom.
- Bitwise `&` in pandas mask expressions — required; `and` would raise
  *"The truth value of a Series is ambiguous"*. Any linter flagging these is producing false positives.
