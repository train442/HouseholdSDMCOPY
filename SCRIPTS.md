# Scripts Reference

This catalogs every script in the repo outside of the core model package, GUIs/wizards, and scenario runners
(those live in the repo root and are described in `README.md`). Everything else — one-off data acquisition,
data cleanup, analysis, and scratch scripts — lives under `Scripts/`, sorted by topic.

**Status legend**

| Status | Meaning |
|---|---|
| **Active** | Still the right tool for the job; nothing in the current workflow replaces it. |
| **Legacy** | Superseded by `DataImportWizard.py` (or another current tool) — kept for reference/history, not needed going forward. |
| **One-off** | Ran once (or a few times) to produce a specific artifact or figure; not meant to be rerun as-is. |
| **Scratch** | Ad hoc / exploratory / debug script, not a maintained tool. |

**A general portability note**: most scripts here use bare imports like `import DataProcessing` or
`import Setup`, which only resolve if the repo root is on `sys.path`. This project is developed in PyCharm,
which adds the Content Root (repo root) to `sys.path` automatically for any run configuration regardless of a
script's own location — so these work as-is inside PyCharm. Scripts confirmed **Active** below have an explicit
`sys.path` fix added so they also run from the command line; Legacy/One-off/Scratch scripts generally don't, to
avoid mechanically patching a large amount of code that isn't part of the current workflow. Also note the
repo's own convention (see `DataImportWizard.py`'s docstring) is to run everything with the **repo root as the
working directory** — scripts below that use `'../'`-prefixed paths are the exception (see each folder's notes).

---

## Root: model package, GUIs/wizards, scenario runners

Not in `Scripts/` — these are the files the repo root is meant to strictly contain.

| File | Role |
|---|---|
| `Components.py`, `Parameters.py`, `Setup.py`, `Simulation.py`, `DataProcessing.py`, `TimeManage.py` | The model package — the simulation engine itself. |
| `Progress.py` | Cross-process progress reporting for `Simulation.run_collection` — a queue-based single-writer console listener plus an optional Tkinter live-progress window (`show_gui=True`). Not a GUI entry point itself; imported by `Simulation.py`. |
| `DataImportWizard.py` | GUI for importing/processing/examining solar (NSRDB), load (ResStock), CO2 (Cambium/WattTime), and utility tariff (USURDB) data. Supersedes most of `Scripts/`. |
| `ResultsGUI.py` | GUI for reading and graphing result files — either a legacy `.pkl`/`.pkl.gz`, or a `consolidate_results` store (`_results_store.dat`), which opens a scenario-ID picker first. |
| `InputBuilderWizard.py` | GUI front end for `Setup.generate_input_file`/`generate_input_collection` — builds scenario-sweep input workbooks/collections from form fields plus reference-data pickers, instead of hand-editing 38-column Excel files. |
| `gui_common.py` | Shared `ttk` style/palette and reusable widgets (scrollable frames, card panels, file pickers, a threaded activity log, cancellable Start/Stop actions) used by all three GUIs above. Not a GUI entry point itself. |
| `usurdb_read.py` | Not a GUI/model file itself, but kept in root because `DataImportWizard.py` imports it directly (`import usurdb_read as ur`) for its Tariffs tab — moving it would break that import. |
| `main.py` | Simplest model entry point — imports `Simulation` and calls `run_model`/`run_collection`. |
| `runScenarioFiles.py` | **Deprecated** thin shim re-exporting `Simulation.py`'s implementations — use `main.py`/`Simulation.run_model`/`run_collection` instead. |

---

## Scripts/Zip and Utility Directory

USURDB tariff scraping/processing and zip↔utility directory maintenance. **All of this is superseded by
`DataImportWizard.py`'s Utilities → Directories/Tariffs tabs**, except `make_tariff.py` and the raw scraper.

| File | Purpose | Status |
|---|---|---|
| `utility_rate_database_scrape.py` | Scrapes USURDB by zip code (23800–99999) to build the raw `util_to_zip.csv`/`zip_to_util.csv`. | **Active** (only way to redo the raw scrape if USURDB's zip index changes — the wizard only rebuilds *from* this output, it doesn't redo the scrape) |
| `make_tariff.py` | Builds a custom TOU tariff row from a schedule CSV and appends it to `Utilities/Custom_tariffs.csv`. | **Active** (the wizard has no custom-tariff authoring tab) |
| `create_utility_files.py` | Pulls every tariff per utility from USURDB via `usurdb_read`, writes `Utilities/{Utility}_{EIA}_tariffs.csv`. | Legacy — replaced by the wizard's "Bulk Update All Utilities" |
| `utility_importer.py` | Near-duplicate of `create_utility_files.py` with resume/overwrite toggles. | Legacy — same, superseded by the wizard |
| `util_tariff_process.py` | Predecessor of `create_utility_files.py`; reads a filtered tariff CSV and builds per-utility files. Hardcoded `D:/Bras Research/...` paths — broken as-is. | Legacy |
| `processTariffs.py` | Filters a master USURDB dump to residential/non-obsolete tariffs. Hardcoded `F:/Household Sim/...` path — broken as-is. | Legacy |
| `filterTariffs.py` | Same idea as `processTariffs.py`, different source file. | Legacy |
| `create_zip_directory.py` | One-time join of raw zip/lat-long data with utility data to build the original `zip_directory.csv`. | Legacy — folded into the wizard's "Refresh Directories" |
| `fix_zip_to_util.py` | Zero-pads zip codes and re-resolves utility names. | Legacy — same rebuild the wizard now performs |
| `fix_util_names.py` | One-time fix for utility names that got word-order-mangled ("City of X" vs "X City of"). | Legacy |
| `fixZipLength.py`, `fixZipCoord.py`, `fixCoordinates.py` | Early-stage one-time zip/coordinate cleanup scripts. | Legacy |
| `zipScrape.py` | Patch script for zip codes missing from the main lat/long file (Google + unitedstateszipcodes.org scrape). Looks unfinished (`num = 5` hardcoded). | Legacy / possibly unfinished |
| `geojson_read.py` | Reads/plots a geojson file. | Scratch |
| `scrape_zip_website.py` | Scrapes zipdatamaps.com to fill Time Zone/Population/Area into `new_zip_directory.csv`. | Legacy — replaced by the wizard's "Enrich Time Zone/Population/Area" (same underlying `dp.zip_scrape` call) |
| `city_list_update.py` | Scrapes Google result snippets to fill missing Latitude/Longitude/Time Zone for reference cities in `city_list.csv`. | **Active** — not covered by the wizard; fragile HTML-scraping approach, would need re-verifying if it still works |
| `test_util.csv` | Leftover test/debug output (raw USURDB-shaped data), origin unclear. | Scratch artifact |

---

## Scripts/NSRDB Solar

Superseded by the wizard's **Solar (NSRDB)** tab.

| File | Purpose | Status |
|---|---|---|
| `NSRDB_API_importer.py` | NREL's own boilerplate PSM3 API example (placeholder API key). | Legacy — sample template, not repo-specific |
| `nsrdb_importer.py` | KD-tree nearest-grid-cell lookup + per-city GHI/temp download from an HDF5 endpoint. Hardcoded `E:/Solar Profiles/...`. | Legacy |
| `NSRDB_processor.py` | Converts raw per-state solar downloads to 5-min CSVs. Hardcoded `E:/Solar Profiles/...`. | Legacy |
| `NSRDB_get_profiles.py` | Exploratory script against the public h5pyd NSRDB endpoint; hardcoded Atlanta coordinate, just plots. | Scratch |

---

## Scripts/ResStock Loads

Superseded by the wizard's **House Load (ResStock)** tab (download → process → build load lookup).

| File | Purpose | Status |
|---|---|---|
| `load_importer.py` | Downloads ResStock parquets for a hardcoded ~100-city list. Hardcoded `E:/Load Profiles/...`. | Legacy — replaced by the wizard's "1. Download" |
| `load_processor.py` | Converts raw parquets to 5-min format, registers new cities. Hardcoded `E:/Load Profiles/...`. | Legacy — replaced by the wizard's "2. Process" |
| `load_summarizer.py` | Builds the per-city Load Lookup summary CSVs. Hardcoded `E:/Load Profiles/...`. | Legacy — replaced by `DataProcessing.build_load_lookup` / the wizard's "3. Build Load Lookup" |
| `filter_metadata_loads.py` | One-time reduction of the raw ResStock metadata to `baseline_metadata_and_annual_results_simp.csv` (the file `RESSTOCK_METADATA_PATH` points at). | **Active** — the only way to redo this if NREL republishes metadata or a fuller/upgrade-inclusive metadata file needs to be regenerated (see the metadata-coverage gap noted in `RESSTOCK_METADATA_PATH`'s usage — it currently only covers `upgrade=0`) |
| `custom_load_generate.py` | Bulk-generates and saves custom load CSVs for every city × `[6000, 11000, 15000]` kWh × house type, via `dp.load_match_yearly(..., save_profile=True)`. | **Active** — the wizard only builds the lookup table, not bulk pre-generated load files |
| `custom_load_generate_legacy.py` | Earlier, simpler version of the above (single hardcoded usage/house-type, no exception handling). Renamed from `custom_load_generate.py` to avoid colliding with the root file's name. | Legacy duplicate |
| `parquet_read.py` | Debug: dumps one hardcoded processed parquet to `example_load.csv`. Hardcoded `E:/Load Profiles/...`. | Scratch |

---

## Scripts/Cambium CO2

| File | Purpose | Status |
|---|---|---|
| `cambium_process.py` | Converts raw per-state-per-year Cambium downloads to the model's processed format. Uses leading-`/` paths (eg `/Model Data/states.csv`) which look fragile/OS-dependent. | Legacy — replaced by the wizard's CO2 → Cambium tab |

## Scripts/ICE Vehicle Data

| File | Purpose | Status |
|---|---|---|
| `ice_processor.py` | Reads raw EPA vehicle data, produces `Model Data/processed_ice.csv` (used for ICE vs EV cost/CO2 comparisons). | **Active** — not covered by the wizard; only needed again if EPA data is refreshed |

---

## Scripts/Zip Demographic Mapping

Builds/consumes `Model Data/master_zip_geo.json` — a geopandas file combining zip boundaries with utility
price-differential, population density, AGI, and EV sales data, for exploratory/dissertation/Ford-project
mapping. Not part of the simulation runtime.

| File | Purpose | Status |
|---|---|---|
| `make_zip_json.py` | Builds `master_zip_geo.json` from Census ZCTA shapes + zip directory + IRS AGI data. | **Active/one-off** — foundational builder for this data pipeline |
| `ev_sales_to_zip.py` | Tallies Ford EV sales (Mach-E/Lightning) by zip. | One-off (Ford project) |
| `add_ev_sales_to_json.py` | Adds an EV Sales column into `master_zip_geo.json`. Run after `ev_sales_to_zip.py`. | One-off (Ford project) |
| `zip_map.py` | Filters/plots `master_zip_geo.json` by threshold criteria over a US basemap. | One-off/scratch |
| `FilterGUI.py` | Tkinter+matplotlib GUI prototype to explore `master_zip_geo.json` layers interactively. Several handlers are stub `print(...)` placeholders. | One-off/incomplete prototype |
| `FordMapGUI.py` | Simpler GUI shell, just plots the basemap with a title bar, no data controls. | One-off/prototype (likely predates `FilterGUI.py`) |
| `DissertMap.py` | Plots the top-20 zip pools from `refined_pools.csv` as a dissertation figure. | One-off |

---

## Scripts/Pool Generation

The scenario-batch input pipeline: group zip codes into "pools" sharing the same reference city/state/utility/
tariff, then generate scenario input files from them.

| File | Purpose | Status |
|---|---|---|
| `generate_pools.py` | Core pool builder — for every zip, finds best TOU utility/tariff + reference city, groups matching zips into pools. Produces `pool_test.csv`. | **Active** |
| `refine_pools.py` | Filters `pool_test.csv` by coverage thresholds, drops non-TOU/AK/HI/DC, outputs `refined_pools.csv` / `topN_pools_by_population.csv`. | **Active** (no `sys.path` fix needed — no local module imports) |
| `making_dissert_sets.py` | Hand-edited driver that calls `Setup.generate_input_collection(...)` for various scenario sweeps. | **Active/one-off** — meant to be edited per run |
| `pool_test.csv`, `refined_pools.csv`, `top15_pools_by_population.csv`, `top16_to_60_pools_by_population.csv`, `top20_pools_by_population.csv`, `top20_pools_by_population_commuteSummary.xlsx`, `top20_pools_by_population_dataSummary.xlsx`, `top30_pools_by_population.csv`, `top50_pools_by_population.csv` | Data outputs of the scripts above. | Data artifacts |

---

## Scripts/Post-Processing and Plots

`PostProcessing.py` is a real reusable library (hourly/seasonal breakdowns, cost/rate charts, TOU heatmaps, HES/PV
sizing-sweep surface plots, Excel summary generators); everything else here is a one-off consumer of it, kept
in the same folder so their bare `import PostProcessing` keeps resolving.

| File | Purpose | Status |
|---|---|---|
| `PostProcessing.py` | Reusable analysis/plotting library. Imported by the other files in this folder. | **Active** (as a library — not imported by `ResultsGUI.py`/`runScenarioFiles.py`/`main.py`, only by the peripheral scripts below) |
| `testing.py` | Scratch runner; ~200 lines of commented-out historical run configs, one live line at the bottom (`pp.make_pool_util_plots(...)`). | Scratch |
| `testing2.py` | Similar scratch runner, mostly commented-out `sp.generate_input_file`/`sm.run_model` calls for IMECE/Ford runs; live lines at the bottom call `sm.run_collection(...)`. | Scratch |
| `FordPlots.py` | Loads a hardcoded run's summary, computes HES×PV metric meshes, 3D surface plots. | One-off (Ford project) |
| `SummaryPlot.py` | Same idea as `FordPlots.py`, hardcoded to a different run (`Ford_MiamiFL_runs`). | One-off/scratch |
| `V2H_Plot.py` | Line-plots a metric vs V2H discharge limit for a hardcoded run (`IMECE_2024_LA_V2H`). | One-off (IMECE 2024) |
| `compileSummaries.py` | Compiles several `IDETC_*` run summaries into master HES/PV tables. | One-off (IDETC paper) |
| `compileSummariesV2H.py` | Same idea for the V2H `IDETC_*_V2H_2024` run set. **Appears incomplete** — reads data and defines `metrics` but never builds/saves the output tables. | One-off/incomplete |
| `plotHouseProfiles.py` | Scatter-plots ResStock load vs house size from a Load Lookup CSV. | Scratch |
| `plotInputData.py` | Compares solar/load/emissivity/TOU data across cities for the IDETC paper. | One-off (IDETC paper) |

---

## Scripts/Financial Data

Exploratory, not part of the simulation's core data pipeline.

| File | Purpose | Status |
|---|---|---|
| `irs_analysis.py` | Plots IRS county AGI-bracket data for a hardcoded county. | Scratch — feeds `make_zip_json.py`'s AGI logic |
| `nasdaq_pull.py` | Plots Zillow home-value indicators for a hardcoded region via the Nasdaq Data Link API. **Had a hardcoded API key in source — removed and switched to reading `NASDAQ_DATA_LINK_API_KEY` from the environment**; set that env var before running. | Scratch |

---

## Scripts/Scratch and Testing

Generic, domain-less "run whatever" scripts — not tied to one data pipeline.

| File | Purpose | Status |
|---|---|---|
| `testing3.py` | 4 lines: `Simulation.run_collection(collection_path='Top20_PV_HES_set', overwrite_runs=False)`. | Scratch |
| `testing.xlsx` | Leftover scratch spreadsheet, origin unclear. | Scratch artifact |

---

## Scripts/Legacy GUI

| File | Purpose | Status |
|---|---|---|
| `LoadGUI.py` | An earlier, monolithic Tkinter GUI (~1270 lines) combining zip/utility/house/HES/PV/EV/ICE setup and a "Run Simulation" button — everything `ResultsGUI.py`/`DataImportWizard.py`/`main.py` now do as separate, purpose-built tools. Multiple hardcoded `D:/Bras Research/pythonProject/...` paths that don't exist on this machine. | **Legacy/broken** — not imported by anything else; kept for reference only |

---

## Not covered here: `Obsolete/`

`Obsolete/` (including `Obsolete/Old Utility Scripts/`) already exists as its own clearly-labeled home for
fully retired code (early-generation predecessors of the zip/utility directory pipeline) and was left as-is —
it wasn't part of this cleanup, which focused on the repo root and the old `Processing Scripts/` folder.
