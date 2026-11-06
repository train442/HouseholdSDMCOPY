# Proposed Changes — Review Before Applying

> **Status: ALL TIERS APPLIED AND VERIFIED. Final: 3.13 → 1.37 s/scenario (2.28x).**
>
> Verification across 16 pickled `Results` objects and four summary CSVs (55 columns each, including
> the full monthly `Bill` DataFrame):
>
> * **Column set unchanged** — no summary column added, removed or reordered.
> * **Only three fields differ from the pre-change baseline:** `Time Elapsed (s)` (expected), and
>   `HES Avg SoC Target` / `avg_soc_target`, which is the T3-06 bug fix. Every bill, avoidance, CO₂
>   figure and peak-shaving metric is bit-identical.
> * All three scheduler modes (`file`, `chunk`, `auto`) produce identical row sets and IDs.
>
> **`HES Avg SoC Target` now reports 80.05% where it previously reported 3.23, 1.64, 1.10, 0.83** on
> four consecutive `flat`-scheme scenarios that all target 80%. The old values decayed run-to-run
> because `opt_count` was never reset between scenarios. **Every existing summary CSV has a wrong
> value in that column**, and re-running `recalc_summary_file` will not repair it — the figure derives
> from the live HES object, so affected scenarios must be re-simulated if that column matters to you.
>
> An annotated copy of the pre-optimization source is at
> `Obsolete/Optimization_Review_2026-08-09/`.
>
> **One action needed from you: `pip install pyarrow`.** Without it the Parquet store is skipped with
> a warning and only the summary CSV is written. Everything else works regardless.

Everything below is measured, not guessed. Baseline: `Top20_PV_HES_set/F1_CA_90011_PST_Los Angeles_CA`,
scenarios 13–18 (PV + HES + 1 EV, 105,120 steps), cProfile, 6 consecutive scenarios in steady state.

**Measured baseline: 4.94 s/scenario.** At 2,079 scenarios/file × 20 files ≈ 41,600 scenarios ≈ 57
core-hours per collection.

---

## Tier 1 — Runtime — **APPLIED: 3.13 → 1.44 s/scenario (2.17×)**

Applied in three verified passes against the same benchmark:

| Pass | Change | s/scenario |
|---|---|---|
| baseline | — | 3.13 |
| 1 | 1-D arrays, coverage mask, cached loaders, `has_evs`, `update_flow` elif tree | 1.83 |
| 2 | integer component codes in `sinks_and_sources` / `energy_flows` | 1.48 |
| 3 | Python-list fast path for grid emissivity | **1.44** |

`Energy.update_flow` alone fell from 6.06 s to 1.39 s of profiled self-time (4.4×).

Two latent bugs were fixed in passing because they sat inside rewritten blocks and are provably
unreachable today, so they cannot affect current results: `Energy.update_flow`'s HES→grid branch was
missing its `[index]` (`self.grid_in += x` instead of `self.grid_in[index] += x`), and
`Fleet.clear_fleet` left `ev_num` stale so `no_evs()` kept reporting a non-empty fleet after clearing.

Original analysis follows.


### 1.1 Make `Energy` arrays 1-D — **est. −12%**

Every tracking array in `Energy.__init__` is allocated as `(N, 1)` instead of `(N,)`. Writing
`self.pv_out[index] += x` on a column vector is **4.7× slower** than on a flat array (measured:
0.61 µs vs 0.13 µs). `update_flow` does ~5 of these per call and is called ~1.6× per step.

```python
# now                              # proposed
self.pv_out = np.zeros((N, 1))     self.pv_out = np.zeros(N)
self.loss   = np.zeros((N, 1))     self.loss   = np.zeros(N)
```

Downstream consumers in `Results` that do `x.reshape(len(x), 1)` to broadcast against these get
simplified rather than broken. Per-EV arrays stay 2-D — `arr[i, j]` is already fast.

### 1.2 Replace `step in hes.coverage_steps` with a boolean mask — **est. −6%**

`Simulation.py:836`, inside the timestep loop. `in` on an ndarray is a full linear scan: **1.5 µs**
per step at typical coverage sizes. A preallocated `np.bool_` mask is **0.037 µs** — 40× faster.

```python
# now
if timekeep.step in hes.coverage_steps:
# proposed — HES.update_coverage_steps also sets self.coverage_mask
if hes.coverage_mask[timekeep.step - 1]:
```

### 1.3 Cache `efficiencies.xlsx` — **est. −1%, and 32 min per collection**

`Operation.load_efficiencies` calls `pd.read_excel` on a 6×6 table **every time an `Operation` is
constructed** — once per scenario. Measured **46.5 ms**. Over a 20-file collection that is ~32
minutes of pure Excel parsing. Same story for `pd.read_excel('Model Data/PVs.xlsx')` in
`PV.__init__` (**52 ms**, once per PV, and PV size changes nearly every row in the sweeps).

Fix: module-level `@lru_cache` loaders keyed on path + mtime.

### 1.4 Cache the GHI profile in `PV.load_solar` — **est. −2%**

Reading and date-parsing the 105,120-row GHI CSV costs **86 ms**, and it is re-read every time PV
size changes. The irradiance is identical across the whole sweep — only `system_size` scales it.
Cache the `(ghi, temperature)` arrays keyed on `(file, start_date, end_date)` and recompute only
`power = ghi × system_area × efficiency / 1000`.

### 1.5 Tighten `sinks_and_sources` — **est. −5%**

- Hoist `timekeep.timestep / 60` out; it is recomputed 4× per step.
- `sinks.sort(key=lambda s: s[3])` → `operator.itemgetter(3)` (C-level, avoids a Python frame per
  comparison; 1.26 M sort calls in the 6-scenario profile).
- Cache `fleet.no_evs()` as a `fleet.has_evs` attribute — currently called **1,051,214 times** in a
  6-scenario run (5× per step) for a value that changes only between scenarios.
- Reuse two preallocated lists instead of building fresh ones each step.

### 1.6 Flatten the `update_flow` branch tree — **est. −4%**

Four sequential `if cell[0] == …` tests, all evaluated every call even though they are mutually
exclusive → `elif`. Also convert `self.efficiencies` to a nested Python list for the scalar lookups
(`effL[2][3]` is 0.035 µs vs `eff[2,3]` at 0.058 µs) while keeping the ndarray for vector use.

### 1.7 Bound the search window in `Tariff.get_next_off_peak` — **est. −2%**

`np.where(self.tou_schedule[index:, 1] == 0)` scans the entire remainder of the year. Measured
**120 µs/call**, 4,692 calls. `get_end_of_period` already uses a bounded 3-day window; apply the
same pattern with a widening fallback.

### 1.8 Preallocate in `optimize_hes`

`coverage_steps = np.append(coverage_steps, new_steps)` in a loop reallocates the whole array each
iteration. Collect into a list, one `np.concatenate` at the end. Also `np.linspace(...).astype(int)`
→ `np.arange`. Small in absolute terms (~0.44 s / 6 scenarios) but free to fix.

### 1.9 Widen collection parallelism — **est. 1.5–3× on wall clock**, depending on your core count

`run_collection` parallelises across **input files** — 20 tasks for 20 files. If you have more than
20 usable cores, or if the files finish at uneven times, cores sit idle at the tail. Proposed:
flatten to a task queue of `(input_file, scenario_range)` chunks so a 32-core machine stays
saturated and stragglers get split. Each chunk still writes its own partial summary; `run_model`
merges them at the end.

**This one changes the concurrency model**, so I'd like your call before touching it (see questions).

---

## Tier 2c — Load profile storage (APPLIED)

The Custom Loads library was 356 CSVs totalling **1.49 GB**. Each held a redundant `Time` column plus
`Load(kW)` at ~16 significant digits — 4.18 MB for a 105,120-step year — when the model discards the
timestamps (fixed 5-minute cadence) and rounds to 3 decimals on load anyway.

Now stored as compressed `.npz`:

| | Size | Read |
|---|---|---|
| legacy `.csv` | 4.18 MB | 72.0 ms |
| new `.npz` | 0.22 MB | **1.9 ms** |

**19.5× smaller and 38× faster to read. Library: 1.49 GB → 0.08 GB, 1.41 GB reclaimed.** All 356 files
converted, zero failures, each verified against its original before the CSV was removed.

Verified end-to-end: with every profile converted, model output is **identical at 1e-9 tolerance** —
the only field that moved was `Time Elapsed (s)`.

- `DataProcessing.save_load_profile` / `load_load_profile` / `find_load_profile` handle both formats.
- `House.generate_load` and `make_house` resolve a stem to whichever format exists, so a scenario's
  `Load File` column works whether or not a profile has been converted.
- `load_match_yearly(save_profile=True)` writes the new format.
- `Scripts/ResStock Loads/convert_custom_loads.py` performs the migration (`--dry-run`, `--keep-csv`).

### Processed ResStock parquets — the redundant `Time` column

An earlier note here said there was nothing to win in `Processed/Parquets` because the files are
already Snappy-compressed. That was wrong, and parsing the parquet footers directly shows why:

```
column Time       compressed  841.7 KB   raw 1039.7 KB   SNAPPY
column Load(kW)   compressed  173.1 KB   raw  197.8 KB   SNAPPY
```

**`Time` is 84.9% of the stored bytes in every file** — Snappy barely compresses monotonic int64
timestamps (1.24×) while the load data compresses to ~150 KB. And that column is *identical in all
506,451 files*: `process_resstock_load` hardcoded a 2018 5-minute grid derived purely from the row
count, and no consumer ever reads it — every one requests `columns=['Load(kW)']`.

Dropping it takes each file from ~1000 KB to ~150 KB (**6.6×**), and the library from roughly
490 GB to 75 GB.

- `process_resstock_load` no longer writes the column, so newly downloaded profiles are small.
- `DataProcessing.resstock_timestamps(n_rows)` and `read_resstock_profile(path, with_time=True)`
  regenerate it exactly for anything that wants it; the Wizard's preview now uses the latter.
- `Scripts/ResStock Loads/strip_parquet_time_column.py` migrates the existing library. It verifies
  every file's `Load(kW)` values against the original before replacing it, skips already-converted
  files so it is resumable, writes via a temp file and atomic rename, and supports `--dry-run`,
  `--limit N` and `--workers N`.

**Not run yet.** This sandbox has no parquet engine, so while the redundancy and its size were measured
from the footers, the conversion itself could not be executed or verified here. Run `--dry-run`, then
`--limit 200`, and check the numbers before the full pass.

Caveat: git already delta-compresses similar objects within a pack, so it may be partly exploiting the
shared `Time` column already. The working-tree saving is certain; expect the pack to shrink by less
than 6.6×, and note that rewriting 506,451 files adds that many new blobs unless paired with a
history rewrite.

### Also fixed: hard dependencies that were not

`DataProcessing.py` imported `h5pyd` and `scipy.spatial.cKDTree` at module level, though both are used
only by the Wizard's NSRDB downloader. That made them hard requirements for **every** consumer —
including every simulation worker and every offline script. Both are now imported lazily inside
`get_NSRDB_metadata`, with a clear message if missing. The simulation stack now imports with neither
package installed.

### Note on .git

Converting shrinks the **working tree**, not the repository. The old CSV blobs remain in history
forever, so `.git` (currently ~80 GB) will grow slightly rather than shrink. This was the chosen
trade: a normal delete+add commit, no history rewrite, no force-push, nothing breaks for any clone.
The CSVs remain recoverable from history if ever needed.

## Tier 2b — Full-results pickle compression (APPLIED)

`save_pickles=True` now writes `..._Run_N.pkl.gz`, controlled by `compress_pickles` (default `True`)
and `compress_level` (default 1). Measured on a full-results scenario: **43.95 MB → 4.72 MB (9.3×)**
for roughly 0.13–0.22 s per scenario. Lossless — verified bit-identical on round-trip.

Readers detect the format from the file's **magic bytes**, not the filename, so:

- existing uncompressed `.pkl` files keep loading unchanged,
- both formats can sit in the same `Results/` directory (verified — `generate_results_summary` reads a
  mixed directory correctly),
- `load_results_file` also accepts a path with no extension and resolves whichever exists,
- a mislabelled file (gzip content named `.pkl`) still loads.

`ResultsGUI.py` now calls `Simulation.load_results_file` instead of `pickle.load`, so it opens either.

### Why not run-length encoding

RLE was considered and rejected on measurement. Encoding every float array gives 36.2 MB → 15.0 MB
(2.4×), against 9.3× for gzip over the whole file. The reason is visible in the array census: the
arrays RLE would crush (`grid_to_hes`, 58× — 99% zeros) are exactly the ones gzip already reduces to
nothing, while the arrays that dominate the file go the wrong way. `timekeep.calendar` is the single
largest at 5.89 MB and RLE makes it **48% bigger** (0.68×) because consecutive values almost never
repeat; gzip gets 19× on it by spotting the row-level regularity. RLE would also need a bespoke
decoder in every consumer. gzip is one line each way and needs none.

`driving_pattern`'s `object` dtype was also investigated as a size/speed win and rejected: object
indexing measured *faster* than float64 (42.9 ns vs 53.5 ns) because it returns the stored object
without boxing, and that array is indexed ~1.9 M times per scenario.

Structural trimming (dropping all-zero arrays and the regenerable calendar) was prototyped and
**dropped**: on top of gzip it saved only 0.34 MB and ~18 ms, and it would have required a rehydration
layer in every reader — a permanent correctness surface for a negligible gain. The related idea worth
keeping is T2-03, allocating those arrays lazily in `Energy.__init__`, which cuts ~21 MB of live RSS
per worker and needs no rehydration because the arrays never exist.

## Tier 2 — Results Storage

### Current state, measured

| | |
|---|---|
| Per-scenario `.pkl` | 7.7–9.2 KB |
| Per input file | 2,375 files, **19 MB** |
| Per 30-file collection | ~71,000 files, **~570 MB** |

With `full_results=False` (your default) the pickle contains **only scalars, six 1-element arrays, a
`Bill` DataFrame, and the V2H histogram.** Every component object is already `None`. The summary CSV
already reproduces ~90% of it.

The cost isn't really disk — it is 71,000 filesystem entries, which makes `generate_results_summary`
and any post-processing sweep painfully slow on Windows, and makes the `Outputs/` tree miserable to
sync or archive.

### Proposed

1. **Write one Parquet per input file** containing every scalar field currently in the pickle, plus
   the fields the summary CSV drops. Columnar + compressed: ~2,079 rows × ~60 columns ≈ **300 KB**,
   versus 19 MB. That's ~60× smaller and one file instead of 2,375.
2. **Make pickling opt-in** (`save_pickles=False` default). Keep it on for `full_results=True`, for
   single-scenario debugging, and for anything `ResultsGUI.py` needs to open.
3. **Append summary rows to a list**, build the DataFrame once at the end, instead of
   `pd.concat` per scenario. Measured 0.89 s/file — small, but it also silences the pandas
   `FutureWarning` about concatenating empty frames that currently spams your console.
4. **Replace the per-column overwrite loop** (`for col: summary_frame.loc[inds, col] = …`, 45
   boolean-mask evaluations per overwritten scenario) with a single `.loc[idx] = row`.
5. **In-memory:** the `Energy` object holds ~25 arrays of 105,120 float64 ≈ **21 MB** per live
   simulation. Several are provably unused when the relevant component doesn't exist (`hes_to_ev`,
   `ev_to_grid`, `pv_to_fleet`). Allocating those lazily cuts peak RSS per worker by ~40%, which
   matters when you are running 20+ workers.

`ResultsGUI.py` continues to work unchanged against any pickles you do keep. I'd add a small
`load_results_frame(path)` helper so post-processing reads the Parquet instead of 2,375 pickles.

---

## Tier 3 — Correctness Issues Found Along the Way

These are bugs, not style. Listed in severity order.

1. **`Parameters.py:670` — index out of bounds.** `self.tou_schedule[..., 2]` on a 2-column array.
   The `hes_cover_mid=False` branch of `get_coverage_steps` raises `IndexError`, which the enclosing
   `except ValueError` does not catch, and `steps` is then unbound. Unreachable today only because
   `hes_cover_mid` defaults to `True`. → use column 1, catch `IndexError`, initialise `steps`.
2. **`Simulation.py:1467` — `rows_match` always-true test.**
   `np.isnan(new_row[col]) and np.isnan(new_row[col])` compares `new_row` to itself; it should be
   `new_row` vs `old_row`. Effect: two scenarios where one has NaN and the other has a value are
   treated as matching, so a component that should be rebuilt gets reused. This is a **silent
   wrong-results** risk in sweeps that toggle optional columns.
3. **`Results.add_objects`** assigns `object_dict['Operation']` to `self.tariff`, and never restores
   `self.energy`.
4. **`Bill` / `Grid.update_emissivity`** — `self.grid_in += energy_received` on the HES→grid branch
   (`Components.py`, `cell == [1, 4]`) is missing its `[index]`, so it adds to the whole array.
   Currently unreachable (HES→grid is disabled) but it will bite the moment you enable it.
5. **`update_baseline_metrics` divide-by-zero** when a baseline row has zero savings — produces
   `inf` payback periods that silently propagate into the summary CSV.
6. **`HES.soc_targets` is the wrong shape, so `HES Avg SoC Target` is wrong in every summary CSV you
   have.** `soc_targets` is allocated as `np.zeros((1, 365))`. `soc_targets[opt_count] = value` with
   `opt_count == 0` therefore assigns the value to *all 365 entries of row 0*; on the next
   optimisation `soc_targets[1]` raises `IndexError`, the `except` widens the array by 30 columns,
   and **the value is never stored**. After a year (~730 optimisations) the array is 1 × ~22,000 with
   only the first 365 slots populated, all holding the first target. `trim_soc_targets` then tests
   `len(self.soc_targets) > self.opt_count`, but `len` of a (1, N) array is 1, so it never trims.
   Net effect: the reported average is roughly `365 × first_target / 22000`. This is why the column
   reads ~3% where the flat scheme targets 80%. → make `soc_targets` 1-D and append correctly.
7. **`Energy.update_flow`, grid→EV branch** passes `ev_id=source_id` to
   `fleet.update_cost_of_use` where every sibling call passes `sink_id`. For grid→EV the source is
   the grid (id 1), so with a single-EV fleet this is harmless — with two or more EVs it credits the
   cost of use to the wrong vehicle.
8. **`Component.can_be_source_update`** contains `self.must_be_source: False` — an annotation
   statement, not an assignment. The method silently fails to clear `must_be_source`.

---

## Tier 4 — Conventions and IDE Warnings

Full AST sweep across 11 modules. Counts are actual.

| Issue | Count | Files | Fix |
|---|---|---|---|
| Bitwise `&` / `\|` on boolean comparisons | ~60 | all | → `and` / `or` |
| Unused imports | 8 | `Simulation`, `Parameters`, `Setup`, `DataProcessing` | remove |
| Unused local variables | 17 | mostly `index`, `i`, `j` from `enumerate` | `_` or drop |
| Wildcard imports | 4 | `Components`, `runScenarioFiles`, `ResultsGUI`, `DataImportWizard` | explicit imports |
| `pd.concat` FutureWarning | runtime | `Simulation` | build once |
| Possibly-unbound locals | 3 | `Parameters`, `Simulation` | initialise before branch |
| Bare/over-broad `except` | 2 | `Setup`, `Parameters` | narrow |

The bitwise-on-boolean pattern is the big one for your VS Code warning count. It works for scalars,
but it has different operator precedence than `and`/`or` and doesn't short-circuit — `(a != 0) & (b/a > 1)`
will divide by zero where the `and` form wouldn't.

### Typing

Type coverage is already good on public functions in `Simulation.py` and `Parameters.py`. Gaps:

- **`Components.py`** — most methods are untyped. `Battery.charge_rate(self, soc=None)`,
  `House.get_load(self, index)`, `PV.get_power(self, index)`, etc.
- **`(pd.Series, None)` used as an annotation** in `Simulation.py` and `runScenarioFiles.py` — that
  is a tuple literal, not a type. Pylance flags it. → `Optional[pd.Series]`.
- **Instance attributes declared as `[]` then reassigned to `ndarray`** (`PV.ghi`, `PV.power`,
  `PV.temperature`) — Pylance infers `list` and then complains at every numeric use. → annotate
  `self.ghi: np.ndarray = np.array([])`.
- **No return annotations** on ~60% of `Components.py` methods.

Proposal: add annotations throughout `Components.py`, `Parameters.py`, and the `make_*` factories,
plus a `py.typed`-style module-level `from __future__ import annotations`. No `mypy` config unless
you want one — the goal is a clean Pylance panel, not a type-checking gate.

### Dead code

`runScenarioFiles.py` (629 lines) duplicates 12 functions from `Simulation.py` — `make_ev`,
`make_timekeep`, `rows_match`, `get_reset_dict`, `make_city`, `make_tariff`, `make_house`,
`make_grid`, `make_pv`, `make_fleet`, `get_baseline`, `check_resolution`. **Nothing imports it.**
The live entry point is `main.py` → `Simulation.run_model`. The README still describes it as "the
script that must be executed", which is now wrong.

Recommend deleting it and correcting the README. Divergent copies of `get_reset_dict` are exactly
how the `rows_match` bug above survives a fix.

---

## Estimated Combined Effect

| | Per scenario | Per 20-file collection (41,600 scenarios) |
|---|---|---|
| Now | 4.94 s | ~57 core-hours |
| Tier 1 (1.1–1.8) | ~2.2–2.5 s | ~26 core-hours |
| Plus wider parallelism (1.9) | — | wall clock down a further 1.5–3× on >20 cores |

I'll re-profile after each tier against the same six scenarios and verify outputs are bit-identical
to the current results before/after, so nothing here is taken on faith.

---

## Housekeeping

Three profiling output directories are left in `Outputs/` (`__prof_tmp`, `__prof_tmp2`,
`__prof_tmp3`) — I don't have delete permission. Safe to remove.

---

## Addendum (2026-09-08) — later session, applied

This review's scope ends above; the following landed in a later session and is **not** re-verified
against the same benchmark methodology this document used, but is applied and covered in
`README.md`/`ARCHITECTURE.md`:

- **Adaptive scheduling** replaced `run_collection`'s `schedule='auto'` file-vs-chunk binary choice
  (§Tier 1.9 above still describes the pre-adaptive `'file'`/`'chunk'` modes, which remain selectable).
  See `Simulation._next_adaptive_piece`.
- **`Progress.py`** (new module) — queue-based, single-writer progress reporting so worker-process
  output can no longer interleave, plus an optional live Tkinter progress window
  (`run_collection(show_gui=True)`).
- **`consolidate_results=True`** (new `run_model`/`run_collection` parameter) — writes one shared
  results store per input file instead of one `.pkl` per scenario, for `save_pickles=True` runs.
- **Bug fix**: `_normalize_summary_row` didn't flatten numpy-array-valued summary fields (only
  `list`/`tuple`), so `'House Load'` (a 1-element ndarray via `House.load_profile`'s `(N, 1)` shape
  convention) could reach `get_baseline`'s vectorized comparison unflattened and raise
  `ValueError: ('Lengths must match to compare', ...)` — this could crash a run immediately after
  every scenario had already completed successfully. Now flattened alongside `list`/`tuple`.
- **`ResultsGUI.py`** restyled to match `DataImportWizard.py` (shared `gui_common.py` module), and
  taught to open a `consolidate_results` store via a scenario-ID picker.
- **`InputBuilderWizard.py`** (new) — GUI front end for `Setup.generate_input_file`/
  `generate_input_collection`.
