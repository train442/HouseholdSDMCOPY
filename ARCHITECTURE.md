# HouseholdSim — Data Pipeline and Model Architecture

A technical companion to `README.md`. Where the README describes *what files exist*, this document
describes *how data gets into the model*, *how the model executes*, and *how results come back out*.

Audience: someone who needs to understand, extend, or defend the model — not someone looking for a
directory listing.

---

## Part 1 — Data Collection

The model consumes five independent classes of external data. Each is acquired once, processed into a
canonical form, and cached to disk. None of it is fetched at simulation time.

| Data class                                   | Source                                                                               | Native resolution     | Canonical form                                                                               |
| -------------------------------------------- | ------------------------------------------------------------------------------------ | --------------------- | -------------------------------------------------------------------------------------------- |
| Solar irradiance (GHI) + ambient temperature | NREL**NSRDB** (via `h5pyd` against the HSDS endpoint)                        | 30 min                | `City Data/Solar Data/{ST}/{ST}_{City}_GHI_2018_5min.csv`                                  |
| Household electrical load                    | NREL**ResStock**                                                               | 15 min                | `City Data/Load Profiles/Processed/Parquets/{State}/{City}/{house}-{upgrade}_5min.parquet` |
| Grid CO₂ intensity                          | NREL**Cambium** (long-run marginal) or **WattTime** (real-time marginal) | 30 min / 5 min        | `City Data/CO2 Profiles/{Cambium 2021\|WattTime}/Processed/*.csv`                           |
| Electricity tariffs                          | NREL**USURDB**                                                                 | n/a (rate structures) | `Utilities/{Utility Name}_{EIA}_tariffs.csv`                                               |
| Locality / demographic mapping               | Census + utility service-territory tables                                            | n/a                   | `Model Data/zip_to_util_fixed.csv`, `util_to_zip_fixed.csv`, `city_list.csv`           |

### 1.1 Acquisition

`DataImportWizard.py` is the current front door. It is a Tkinter GUI with one tab per data class,
and it wraps logic that previously lived as one-off scripts with hardcoded paths under `Scripts/`
(those scripts are retained and catalogued in `SCRIPTS.md`, but the Wizard supersedes them).

- **Solar** — the Wizard resolves a city's lat/long, queries NSRDB metadata to find the nearest grid
  point (`DataProcessing.get_NSRDB_metadata` builds a `cKDTree`; `get_NSRDB_index` queries it), and
  pulls the GHI and temperature time series for that point.
- **Load** — ResStock building-level profiles are downloaded per reference city and indexed into a
  per-city lookup table (`build_load_lookup`) recording square footage, bedrooms, heating fuel,
  upgrade level, and annual kWh for every stock building.
- **CO₂** — Cambium state files are downloaded as annual "typical year" profiles; WattTime profiles
  are fetched per balancing-authority region for a specific real calendar year. The distinction
  matters at alignment time (§1.3).
- **Tariffs** — `usurdb_read.py` and `DataProcessing.parse_usurdb_rate_structure` flatten USURDB's
  nested JSON-ish rate structures into flat per-utility CSVs, one row per tariff.
- **Zip/utility directory** — `refresh_zip_utility_directories` and `enrich_zip_directory` build and
  repair the zip→utility and utility→zip mappings, including scraping missing zip metadata.

Credentials for NSRDB and WattTime are stored in `nsrdb_credentials.json` / `wattime_credentials.json`
and are gitignored.

### 1.2 Resolution normalisation

**The model runs on a uniform 5-minute grid.** Every incoming profile is upsampled to that grid
before it is stored, so no resampling happens at simulation time. The upsamplers are deliberately
different because the physical quantities behave differently:

- `increase_solar_res` / `resample_to_5min` — irradiance is **interpolated**; it is a smoothly
  varying instantaneous quantity.
- `increase_load_res` — load is **held / distributed** rather than interpolated, preserving the
  15-minute energy total.
- `increase_co2_res` — marginal emissions rate is interpolated by default (`interpolate=True`),
  with a step-hold fallback.

A 365-day year at 5-minute resolution is **105,120 timesteps**. That number appears throughout the
codebase as the default array length.

### 1.3 Temporal alignment

The datasets come from different calendar years, so they must be aligned before they can be used
together. This is handled by the `shift_by_day` / `shift_by_hour` family in `DataProcessing.py` and
by `Grid.change_dates` / `PV.load_solar`:

- **Day-of-week alignment.** Load and WattTime profiles are shifted by whole days so that the
  weekday pattern of the source year lines up with the weekday pattern of the simulation year. This
  matters because TOU tariffs price weekdays and weekends differently, and household load is
  strongly weekday/weekend dependent.
- **Cambium exception.** Cambium is a synthetic "typical year", not a dated year, so it is aligned
  by *date* only (`cambium=True` path), not by day-of-week.
- **Timezone.** Solar and CO₂ profiles are shifted by whole hours to the reference city's local
  time. A WattTime balancing region can straddle a UTC-offset boundary (e.g. SOCO spans CST Alabama
  and EST Georgia), so the processed filename encodes the timezone as well as the region.
- **Leap years.** `PV.load_solar` stacks copies of a single-year profile to span multi-year
  simulations, splicing in a duplicated Feb 28 for leap years (the `[0:16992] + [16704:]` slice).

### 1.4 Load matching

A scenario does not name a specific ResStock building. It names a **city** and an **annual usage in
kWh** (`Load Amount`), and the model picks a stock profile that matches.

- `load_match_yearly` — selects the stock building in that city whose annual consumption is closest
  to the requested figure, optionally filtered by house type, upgrade level, or bedroom count, then
  scales it to hit the target exactly.
- `load_match_monthly` — the richer path used when a *user* supplies real utility-bill data. The
  user's monthly kWh totals (`monthly_load_summary`) are matched against the stock library
  month-by-month, then `normalize_profile_hourly` rescales the chosen stock profile so its hourly
  shape is preserved but its monthly energy matches the user's actual bills.

Matched profiles are cached to `City Data/Load Profiles/Custom Loads/{ST}_{City}_{kWh}kWh.csv` so the
match is done once, not once per scenario.

### 1.5 Locality resolution

A scenario specifies a **zip code**. `Setup.create_city` resolves it as follows:

1. Zip → lat/long, state, county, timezone (`zip_read` against the zip directory).
2. Lat/long → nearest **reference city** in `Model Data/city_list.csv` by great-circle distance
   (`haversine` / `closest_index`).
3. Zip → **utility** via the zip→utility directory; where several utilities serve a zip,
   `get_best_utility` picks by service-territory customer count.
4. Utility → **tariff**, either named explicitly by `Tariff ID` or chosen by `get_best_tariff`.

The consequence: **solar, load, and CO₂ come from the reference city; the tariff and tax rate come
from the actual zip.** Fayetteville GA 30214 gets Atlanta's weather and Georgia Power's rates.

---

## Part 2 — Defining a Run

### 2.1 Scenario files

An **input file** is one `.xlsx` in `InputFiles/` with a 3-row header. Each subsequent row is one
**scenario** — a complete, independent specification of a household-year. The 38 columns group into:

| Group     | Columns                                                                                                                                 |
| --------- | --------------------------------------------------------------------------------------------------------------------------------------- |
| Temporal  | `Start Date`, `End Date`, `Year`, `Simulation Days`, `Start Day`, `TimeStep`                                                |
| Locality  | `Zip Code`, `City`, `State`                                                                                                       |
| Tariff    | `Utility Name`, `Utility File`, `Tariff ID`, `Net Meter Type`                                                                   |
| Load      | `Load Amount`, `Load File`, `User File`                                                                                           |
| Emissions | `Use Cambium`, `Use WattTime`, `WattTime Year`, `Other File`                                                                    |
| PV        | `System Size (kW)`, `PV Brand`, `PV Model`, `Other Solar File`                                                                  |
| HES       | `Size (kWh)`, `HES Min SoC`, `HES Max SoC`, `Optimization`                                                                      |
| EV        | `EV File`, `Discharge Limit`, `EV Min/Max SoC`, `EV Year`, `Make`, `Model`, `Trim`, `Pattern`, `Qty`, `Charge Type` |

`Setup.generate_input_file` and `Setup.generate_input_collection` build these programmatically —
they take lists of values per axis and emit the full factorial sweep. `InputBuilderWizard.py` is a
Tkinter front end for exactly these two functions, adding reference-data pickers (EV/PV/driving
pattern/zip) for the columns that otherwise fail with a raw exception or a silent fallback deep in
`run_model` if mistyped, and a pre-write row-count preview.

### 2.2 Collections

A **collection** is a subdirectory of `InputFiles/` holding many input files — typically one per
city. `Top20_PV_HES_set/` is 20 cities × 2,079 scenarios each ≈ 41,600 simulated household-years.

Output mirrors input:

```
Outputs/{collection}/{input file}/
├── {input file}_summary.csv           one row per scenario -- always written
├── {input file}_results.parquet       columnar mirror of the summary, for fast bulk reads
└── Results/                           only when save_pickles=True
    ├── {input file}_Run_{ScenarioID}.pkl[.gz]           per-scenario, one file each
    └── (or, with consolidate_results=True instead)
        {input file}_results_store.dat                    every scenario's pickle, concatenated
        {input file}_results_store_index.csv               ScenarioID -> byte offset/length
```

`full_results=False` (the default whenever `save_pickles=True`) pickles hold nothing the Parquet
store doesn't — they're the same summary scalars, just serialized per-scenario. `full_results=True`
additionally keeps the live component objects (`city`, `tariff`, `house`, `grid`, `pv`, `hes`,
`fleet`, `energy`, `timekeep`) on the `Results` object, which is what `ResultsGUI.py` needs for its
time-series plots.

### 2.3 Entry points

```python
import Simulation as sm

sm.run_model(input_file='ATL_Test', collection_name='ATL_Test', overwrite_runs=True)
sm.run_collection(collection_path='Top20_commutes_set', overwrite_runs=False)   # needs __main__ guard
```

`run_collection`'s default `schedule='auto'` is an **adaptive scheduler**, not a fixed whole-file
split: it hands out whole input files across the `ProcessPoolExecutor` while there are enough
untouched files to keep every worker busy (zero overhead — each input file still owns its own output
directory and summary CSV, so workers never contend), and only starts splitting a file's *undispatched*
tail once a worker frees up with no untouched file left to give it — i.e. exactly when fewer files
remain than workers wanting work. Each split halves the largest remaining tail, so no worker waits
long on a single straggler, without paying a per-file component-rebuild tax on files that never
needed splitting in the first place. `schedule='file'` (old whole-file-only behavior, can idle
workers in the tail) and `schedule='chunk'` (every file pre-split from the start, always pays the
rebuild tax) remain selectable. See `_next_adaptive_piece`'s docstring in `Simulation.py` for the
exact algorithm.

Progress reporting (`Progress.py`) runs independently of scheduling: worker processes never print
directly (with many workers doing that at once, raw prints interleave) — they report short events
through a queue to a single main-process listener thread, which is the only thing that ever writes to
the console (`console_verbose=True` for full per-scenario output) or drives an optional Tkinter
progress window (`show_gui=True`, one bar per input file plus overall ETA).

On Windows the calling script must guard the call with `if __name__ == '__main__':` or the spawn
start method will recursively re-execute it.

---

## Part 3 — Model Lifecycle

### 3.1 Object model

Two modules define the world. `Components.py` holds anything physical; `Parameters.py` holds
everything intangible.

```
Component (base: sink/source state machine, cost-of-use, emissivity)
├── House    load profile → energy demand, always a sink, priority -999 (always served first)
├── Grid     infinite source, carries the marginal $/kWh and kgCO2/kWh of the moment
├── PV       GHI × panel area × efficiency → kW; always a source
└── Battery  SoC, charge curve, capacity limits, cost-of-use accounting
    ├── EV   + driving pattern, presence schedule, departure deadlines, V2H discharge limit
    └── HES  + coverage steps, SoC target, charging deadline

Fleet       collection of EVs, dispatches per-EV calls by EViD
Energy      the meter: ~25 arrays recording every directed flow at every timestep
ICE         counterfactual combustion vehicle for gas/CO2 comparison

Operation   run-level switches: efficiencies matrix, optimisation scheme, net-metering policy
TimeKeep    the clock: calendar array, step/index/e_index, day and hour boundaries
Tariff      TOU schedule, tiered rates, period boundary queries
City        location, tax rate, carbon intensity, solar unit cost, reference-city match
```

**Three indices, and they are not the same thing.** This trips people up:

- `TimeKeep.step` — 1-based simulation timestep. What tariffs and deadlines speak in.
- `TimeKeep.index` — 0-based index into *full-year* data (solar, load, driving pattern).
- `TimeKeep.e_index` — 0-based index into *simulation-length* arrays (energy flows, SoC, cost-of-use).

`index` and `e_index` diverge whenever a simulation starts on a day other than Jan 1.

### 3.2 The efficiency matrix

`Model Data/efficiencies.xlsx` is a 6×6 matrix loaded into `Operation.efficiencies`. Row = source,
column = sink, using this ordering:

```
0 = PV   1 = HES   2 = EV(L2)   3 = EV(DCFC)   4 = Grid   5 = House
```

So `efficiencies[0, 5]` is PV→House (0.92), `efficiencies[4, 1]` is Grid→HES. The `cell = [row, col]`
pairs scattered through `energy_flows` and `Energy.update_flow` index directly into this matrix.
**Energy sent is always recorded from the source's perspective; energy received is post-efficiency.**
The difference is booked to `Energy.loss`.

### 3.3 Instantiation (`run_model`)

Per input file, once:

1. Read the scenario `.xlsx` into a DataFrame.
2. Read or create the summary CSV; if `overwrite_runs=False`, resume from `len(summary_frame)`.

Then per scenario row:

3. **`get_reset_dict(prev_row, row)`** — compares the current row against the previous one, column
   group by column group, and decides which of the eight objects actually need rebuilding. This is
   the single most important performance mechanism in the model: in a sweep that varies only PV size,
   the tariff, house, grid, and fleet are reused rather than re-read from disk. Note that
   `New Timekeep` cascades — a new clock invalidates everything downstream of it.
4. Build or reset, in dependency order: `Operation` → `TimeKeep` → `City` → `Tariff` → `House` →
   `Grid` → `PV` → `HES` → `Fleet` → `ICE`.
   - `TimeKeep` builds the calendar (`create_calendar_from_datetime`): an N×6 array of
     `[day_of_week, day_of_month, month, day_of_year, hour, minute]`.
   - `Tariff.create_tou_schedule(calendar)` walks the calendar and produces an N×2 array of
     `[rate, peak_value]` where peak_value ∈ {0 off, 0.5 mid, 1 on}. Every downstream tariff query
     is a lookup into this array.
   - `PV.load_solar` reads GHI, stacks/slices it to the simulation window, and precomputes
     `power = ghi × system_area × efficiency / 1000`.
   - `Grid.change_dates` aligns the emissions profile to the simulation window.
   - `Setup.driving_pattern_from_calendar` expands a 24×16 weekly driving pattern into a full N×3
     array of `[step, presence, miles]` for each EV.

### 3.4 Pre-loop initialisation (`run_simulation`)

1. Allocate per-step tracking arrays sized to `num_steps`: SoC, cost-of-use, emissivity, house
   energy profile.
2. Seed the HES: if the simulation opens off-peak, set SoC to 0.5 and target 1.0 by the end of the
   off-peak window; otherwise set SoC to 0.8.
3. Establish the first HES coverage window (which steps it is permitted to discharge into).
4. Construct the `Energy` object — the ~25 flow-tracking arrays.

### 3.5 The timestep loop

For each `step` from `simu_start_step` to `simu_end_step`:

1. **Price and emissions** — `tariff.get_tou_rate(step)`; `grid.update_cost_of_use`,
   `grid.update_emissivity`.
2. **Demand and supply** — `house.get_energy_required(index)`, `house.record_energy(e_index)`,
   `pv.get_energy_available(index)`.
3. **HES optimisation** — fires only when `step == tariff.next_off`, i.e. once per off-peak
   transition (~twice a day), not every step. `optimize_hes` enumerates the upcoming non-off-peak
   periods, sorts them worst-first, and under the default `simple` scheme computes the target SoC as
   the projected (house load − PV output) over the periods it intends to cover. `flat` targets 80%,
   `full charge` targets SoC max, `none` targets SoC min. It writes back a **target SoC**, a
   **charging start step**, and a **coverage step set**.
4. **Fleet management** — `manage_fleet`. On departure: debit miles, schedule the next arrival. On
   arrival or scheduled update: find the next departure, then decide the charging **deadline** and
   **start step** from the interaction of the departure time with the tariff period structure
   (arrival and departure in the same off-peak, same peak, adjacent periods, or straddling a peak —
   each is a separate branch). If the EV already has enough charge for the next trip and the trip is
   within the current peak period, it declines to charge at all.
5. **Status** — `update_comp_status` sets each component's `can_be_sink` / `must_be_source` /
   `can_be_used` flags from SoC, presence, discharge limits, and charging deadlines.
6. **Sink/source lists** — `sinks_and_sources` emits two lists of
   `[name, id, energy, priority]`. Sinks sort ascending by **priority** (House = −999, so the house
   is always served first). Sources sort ascending by **cost of use**, so the cheapest energy is
   consumed first. This is the model's dispatch rule, and it is greedy rather than optimal.
7. **Dispatch** — `energy_flows` walks the sink list outer, source list inner, and for each valid
   pair applies the policy gates:

   - PV → anything, freely.
   - HES → house, unless the HES has already been charged this step (no simultaneous charge/discharge).
   - EV → house, only if the EV wasn't charged this step, only during a non-off-peak period, and
     only if the rate now differs from the rate it will have to recharge at. This is what prevents
     economically pointless V2H cycling.
   - Grid → house always; grid → EV only off-peak or against a hard departure deadline; grid → HES
     only off-peak, after the computed charging start step, and only on a TOU tariff.

   Each transfer is settled through `Energy.update_flow`, which applies the efficiency, books the
   loss (and the loss's cost and emissions), and propagates the source's cost-of-use and emissivity
   into the sink's own blended figures. This is how a kWh in the HES "remembers" that it came from
   solar rather than from off-peak grid.
8. **Net metering** — any PV energy left after all sinks are satisfied flows to the grid
   (`cell = [0, 4]`).
9. **Record and reset** — `Energy.update_components` snapshots SoC, cost-of-use, and emissivity;
   sink/source flags are cleared; EVs that discharged reschedule their charging step.
10. **Advance** — update hour/day boundaries, increment `step` / `index` / `e_index`.

### 3.6 Completion

`Results.__init__` runs once the loop exits and computes:

- **`Bill`** — a monthly-rows DataFrame reconstructing an actual utility bill: TOU or tiered energy
  charges, monthly fixed charge, minimum charge, sales tax, and net-metering settlement. Five
  compensation regimes are modelled (`one-to-one`, `net billing`, `NEM 3.0`, `no compensation`,
  `no excess`), which differ in whether exports offset consumption at retail rate, at an avoided-cost
  rate, or roll forward as a credit balance settled annually rather than monthly.
- **Cost avoidance per component** — `Σ (grid TOU rate − component's own cost of use) × energy delivered`, grossed up by sales tax. Because cost-of-use is propagated through every transfer,
  this correctly credits solar-charged HES discharge more than grid-charged HES discharge.
- **CO₂ avoidance** — the same calculation against marginal emissions rates.
- **V2H economics** — per EV: avoidance, V2H efficiency ($/kWh cycled), battery degradation cost
  (`miles / warranty × capacity × $/kWh`), and the two break-even figures (the battery life in miles,
  and the battery unit cost, at which degradation exactly cancels the V2H savings).
- **Gas savings** — miles driven × ICE cost/mile, minus the electricity cost of those same miles.
- **Peak-shaving effectiveness** — the share of on-peak (and on+mid-peak) house load served by
  something other than the grid.
- **System cost** — PV at the state's $/W plus $2,000 inverter, HES at $7,500/13.5 kWh plus $1,200,
  both with the 30% federal ITC applied and state sales tax added.

If `full_results=False` (the default) the component objects are dropped and only scalars survive.
One row is always appended to the summary CSV/Parquet store; the object itself is only pickled at all
if `save_pickles=True`, to `Outputs/…/Results/` (or a shared `consolidate_results` store instead of
one file per scenario — see §2.2/2.3).

### 3.7 Cross-scenario post-processing

`update_baseline_metrics` runs after all scenarios in an input file complete. It locates the
**baseline** scenario (no PV, no HES, no V2H — `is_baseline`) and back-fills every other row with
savings measured *against that baseline*: net value, payback period, and cost efficiency. These
columns are meaningless until this pass runs, which is why an interrupted run leaves them zeroed and
why `recalc_summary_file` exists.

---

## Part 4 — Performance Characteristics

Measured on a 365-day, 5-minute scenario (105,120 steps) with PV + HES + one EV:

| Phase                            | Share of wall time |
| -------------------------------- | ------------------ |
| `run_simulation` timestep loop | ~88%               |
| Object construction and file I/O | ~12%               |

Within the loop:

| Function                                 | Share |
| ---------------------------------------- | ----- |
| `Energy.update_flow`                   | ~25%  |
| `energy_flows` (excl. `update_flow`) | ~24%  |
| `sinks_and_sources`                    | ~22%  |
| `Energy.update_components`             | ~9%   |
| loop body in`run_simulation`           | ~9%   |
| `update_comp_status`                   | ~6%   |
| `manage_fleet`                         | ~4%   |

The loop executes 105,120 times and calls `update_flow` roughly 1.6× per step, so per-call costs in
the single microseconds dominate the total. Anything touching a NumPy array with a scalar index
inside this loop is on the critical path.

---

## Part 5 — Known Rough Edges

- `runScenarioFiles.py` duplicates ~12 constructor functions from `Simulation.py` and is no longer
  imported by anything, despite what the README says. `main.py` → `Simulation.run_model` is the
  live path.
- `Tariff.get_coverage_steps` indexes `tou_schedule[:, 2]` on a 2-column array. The
  `hes_cover_mid=False` branch therefore raises `IndexError`, which the surrounding `except ValueError` does not catch. Unreached today because `hes_cover_mid` defaults to `True`.
- `Results.add_objects` assigns `object_dict['Operation']` to `self.tariff` and never restores
  `self.energy`.
- `Operation.load_efficiencies` re-reads `efficiencies.xlsx` on every construction, i.e. once per
  scenario.
- Boolean logic uses bitwise `&` / `|` on comparisons in ~60 places. It works for scalars but has
  different precedence than `and` / `or` and does not short-circuit.
