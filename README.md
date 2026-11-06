# HouseholdSim




## ----- Brief Description -----

This model was developed by Steven Johnston of the Sustainable Design and Manufacturing (SDM) Lab within the 
Woodruff School of Mechanical Engineering of the Georgia Institute of Technology in conjunction with Ford Motor Company.

The purpose of this model is to simulate a household with an installed photo-voltaic (PV) array and home energy 
system (HES) as well as one or more electric vehicles. The objective is to analyze the benefits of these systems 
both financial and in regard to CO2 emissions, with particular focus on vehicle-to-house (V2H) discharge 
capabilities and benefits/demerits. To this end, the model will generate several metrics such as cost avoidance for 
each component, total electricity bill, total CO2 emissions, and payback period (and several others as described in 
the Model Results section).

## ----- File Structure -----

The model was developed in Python to take advantage of its object-oriented nature. As such, it consists of several 
python modules containing a myriad of classes representing model components (ie, EV, HES, the House) and model 
parameters as well as functions and method necessary for the model to run. Below is a brief outline of the file 
structure including directories and subdirectories. 

> Note that not every file in the main directory is listed here (pending clean-up), but every file necessary to 
> **use** the model is listed here. Directories are **bold** followed by a "/" whereas specific files listed are in 
> *italics*.

- **Archive/**
  - This directory contains old files, that while not actively used by the model, were used in the process of making 
    the model, and are useful from an archival standpoint, unlike those in the **Obsolete/** directory.
  - **DataFiles/**
    - Contains archived data files. Mainly those related to utilities and zip codes.
  - **Scripts/**
    - Contains python scripts that were used to troubleshoot certain tasks that would be unwise to delete, despite 
      their lack of use in the functioning model. 
- **City Data/**
  - **CO2 Profiles/**
    - **Cambium 2021/**
      - **Processed/**
        - Processed 5-min CO2 profiles for each state of form "state_Cambium_2022.csv"
      - **Raw Data/** 
        - Unprocessed 30 min CO2 profiles for each state each contained in subdirectories from NREL Cambium
  - **Load Profiles/**
    - **City Load Lookup/**
      - Directory files for each of the model's reference cities of the form "state_cities_loads.csv" which contain 
        summaries and other details of all the stock load profiles for that city from the NREL ResStock Database.
    - **Custom Loads/**
      - Any custom load csv files derived from stock loads that are saved.
    - **Processed/**
      - **Parquets/**
        - {State Name}/
          - {City Name}/
            - Processed parquet files representing stock load profiles, with name format "house number-upgrade 
              level_5min.parquet"
    - **User Profiles/**
      - Custom user profiles in csv format. Must be in 5-min resolution to be used.
  - **Solar Data/**
    - {state}/
      - Contains 5min-resolution csv files for reference cities within the state, with naming format 
        "state_city_GHI_2018_5min.csv".
      - Some states have more than one file, while some only have one.
  - Tariffs - Defunct, moved to Utilities subdirectory. Pending Removal.
- **DrivingPatterns/**
  - Contains csv or Excel files representing driving schedules for the EVs. They consist of 24 rows (one for each hour) 
    and 16 columns.
  - Each day of the week gets 2 columns, the first containing one or zero to signify EV presence, and the second 
    containing the miles driven by the EV. There is an 8th set of 2 columns for Holiday, although this functionality 
    is not currently included in the model.
- **InputFiles/**
  - **EV Files/**
    - contains EV specific input files, in case multiple EVs are desired in the simulation. The models and their 
      operation parameters can be outlined in these files. These files are then reference in a main input file in 
      the "InputFiles" parent directory.
  - Contains the main input Excel files in which all parameters for model function to model component size and 
    behavior are defined in each of the columns. Each row represents a scenario to run. The main *runScenarioFiles.
    py* script will ask for one of these files. See "Defining Inputs" section for more details.
- **Model Data/**
  - **Calendars/**
    - Contains csv files representing calendar arrays for use in the model, though these don't necessarily need to be 
      used since they data they contain can be generated at runtime depending on the temporal inputs in the main 
      input file used.
    - These files have naming format "year_resolution.csv" where the resolution is the minute duration of each 
      timestep such as "5min" or "10min"
    - These files have a row for each timestep in that year and 6 columns in order: Day of Week, Day of Month, Month,
      Day of Year, Hour, Minute. 
  - Contained in this directory are files containing data necessary for proper model function and component creation,
    and are detailed here:
    - *city_list.csv* : 
      - A list of reference cities used in the model. 
      - Any zip_code given asa the locality input will be cross-referenced by proximity to a city in this list.
        - Ex: 30214 --> Fayetteville, GA ------> Atlanta, GA (reference city)
      - The model will pull data for this reference city (solar, CO2, house load) except for Utility 
        which will remain specific to the zipcode/municipality provided.
    - *efficiencies.csv* :
      - A tables of efficiencies of energy transfer between components.
      - Each component is written along the rows (energy from) and the columns (energy to).
      - Ex: Energy from a PV to the house is considered to occur at 92% efficiency.
    - *EVs.csv* :
      - A table of EV models from which the model will pull characteristics of EVs given in the main input file. 
    - *processed_ice.csv*
      - A table of ICE vehicles from which the model can pull emissions characteristics among other data for a 
        desired vehicle.
    - *PVs.xlsx* :
      - Table of PV models from which the model will pull characteristics of PVs given in the main input file.
      - Default is a custom model with 22% efficiency.
    - *states.csv* :
      - A table of the states, containing daylight savings and tax information for each state.
    - *util_to_zip_fixed* : 
      - A table of all utilities in the nation and which zipcodes they service. Also includes the utilities EIA codes.
    - *zip_to_util_fixed* : 
      - A table of all (most) zipcodes in the nation and which utilities operate in them and their EIA codes.
- **Obsolete/**
  - Contains obsolete files. At some point this subdirectory and its contents should be removed to streamline this 
    repository.
- **Outputs/**
  - {simulation name}/
    - A summary CSV (`{name}_summary.csv`) and a Parquet store (`{name}_results.parquet`) covering every scenario
      run under this name -- this is the default, always-written output, and holds everything a `full_results=False`
      pickle would have anyway, so most workflows never need individual pickle files at all.
    - **Results/** (only created when `save_pickles=True`)
      - Contains one `.pkl`/`.pkl.gz` file per scenario (`SimulationName_Run_scenarioID.pkl[.gz]`), each holding the
        `Results` object -- the full component objects (`city`, `tariff`, `house`, `grid`, `pv`, `hes`, `fleet`,
        `energy`, `timekeep`) only if `full_results=True` was also passed; otherwise the pickle is small and
        duplicates the Parquet store.
      - When `consolidate_results=True` is also passed, these per-scenario files are replaced by two shared files
        at the simulation-name level instead: `{name}_results_store.dat` and `{name}_results_store_index.csv`.
        *ResultsGUI.py* can open either layout -- picking a `_results_store.dat` file opens a scenario-ID picker
        instead of loading directly.
    - Optional per-file/per-chunk progress logs (`{name}_progress[__partNNNNNN].log`) when running via
      `Simulation.run_collection` -- see *Progress.py* below.
- **Scripts/**
  - Every script that isn't itself part of the model, a GUI/wizard, or a scenario runner lives here, sorted into
    topical subfolders (NSRDB Solar, ResStock Loads, Cambium CO2, Zip and Utility Directory, Pool Generation,
    Post-Processing and Plots, etc). Most of this is one-off data-acquisition/prep tooling that predates
    **DataImportWizard.py**, which now covers the same ground for solar/load/CO2/utility data through its GUI.
  - See **SCRIPTS.md** in the repo root for a full breakdown of every script and whether it's still active or
    superseded.
- **Utilities/**
  - **Custom/**
    - This directory contains any custom utility files in case greater control over TOU rates and other policies is 
      desired.
  - This directory contains csv files for every utility in the country, in which each of their tariff schedules are 
    outlined.
  - The file names follow the convention "UtilityName_eiaCode_tariffs.csv".
- *Components.py*
  - This module contains classes for each of the physical components of the model and their interactions. In short, 
    if you can touch it in real life, it is present in this module.
    - Classes:
      - Component - master class to Grid, House, PV, Battery, EV, and HES classes
      - Battery: master class to HES and EV classes (inherits Component)
      - House: class representing the household (inherits Component)
      - Grid: class representing the grid (inherits Component)
      - PV: class representing a photo voltaic system installed on the house (inherits Component)
      - EV: class representing an electric vehicle which leaves and returns to the house (inherits Battery)
      - HES: class representing a home energy system (think Tesla Power-wall) inside the house (inherits Battery)
      - Fleet: class representing a collective of EVs.
      - Energy: a class which tracks the energy flows between each component like a multi-directional meter.
      - ICE: a class representing an internal combustion vehicle. It is used for gasoline and CO2 savings for EVs.
- *DataProcessing.py*
  - This module contains constants and method pertaining to the processing of raw data into usable form for the 
    overall model. 
  - Generally speaking, the model operates in 5-minute timesteps so the methods in this module are 
    geared to turning raw data files of varying temporal resolution into this resolution. 
  - In addition, there are methods designed to correct the processed files and align them temporally within the desired dates for the 
    simulation since several of the datasets are derived from differing calendar years.
- *Parameters.py*
  - This module contains classes which emulate the non-tangible parts of the model which govern how the model behaves,
    and parts of the model external to the household.
  - Classes:
    - Operation : a class which contains variables which govern how the simulation runs and inter-component behavior.
    - Timekeep : a class which controls and accounts for the passage of time in the model using timesteps. Contains 
      all time related variables.
    - Tariff : a class which contains all utility tariff data governing electricity costs (TOU, tiered, or both)
    - City : a class which emulates the location in which the model is running a simulation and contains variables 
      pertaining to that location (ie, tax rates).
    - DrivingEvent : a class which represents a particular activity for the EV (ie, work, grocery shopping). This 
      class is not yet utilized in main model, but will likely be integrated into a user interface to make a custom 
      driving pattern.
    - DrivingSchedule : a class which represents a vehicle's driving schedule, such as when it 
      leaves for work and how far it drives in addition to other activities. Like DrivingEvent, this class is not 
      yet implemented into the main model.
- *ResultsGUI.py*
  - A GUI for opening result files and graphing fields from them -- either a legacy individual `.pkl`/`.pkl.gz`
    file, or a `consolidate_results` store (`_results_store.dat`), which opens a scenario-ID picker first.
    Styled via *gui_common.py*, matching *DataImportWizard.py*'s look.
- *DataImportWizard.py*
  - A GUI hub for importing, processing, and examining the raw datasets the model depends on: solar irradiance
    (NSRDB), house load profiles (NREL ResStock), utility tariffs (USURDB), and grid CO2 intensity (NREL
    Cambium/WattTime). Each tab wraps logic that previously only existed as standalone scripts under
    **Scripts/** with hardcoded, machine-specific paths.
- *InputBuilderWizard.py*
  - A GUI front end for *Setup.py*'s `generate_input_file`/`generate_input_collection` -- builds scenario-sweep
    input workbooks (or a whole collection folder of them) from form fields instead of hand-editing 38-column
    Excel files, with reference-data pickers (EV/PV/driving-pattern/zip) for the inputs that otherwise fail
    with a raw exception or a silent fallback deep inside `run_model` if mistyped, and a pre-write row-count
    preview since the factorial sweep can grow large fast.
- *gui_common.py*
  - Shared Tkinter look (a `ttk` theme/palette) and reusable widgets (scrollable frames, "card" panels, a
    filterable file-picker, a background-thread-backed activity log, a Start/Stop button pair for cancellable
    actions) used by all three GUIs above, so they share one visual style instead of each rolling its own.
- *Progress.py*
  - Cross-process progress reporting for `Simulation.run_collection`. Worker processes never print directly to
    the console (with several workers doing that at once, output interleaves); instead they report short events
    through a queue to a single main-process listener thread, which is the only thing that ever prints -- see
    `run_collection`'s `console_verbose` and `show_gui` parameters (the latter pops up a live per-file progress
    window).
- *main.py*
  - The simplest entry point for running the model: imports Simulation.py and calls `run_model` (one scenario) or
    `run_collection` (a full collection of scenarios/input files). Edit the call at the bottom and run directly.
- *runScenarioFiles.py*
  - **Deprecated.** This used to be the script you executed to run simulations, and it carried its own copies of 
    twelve constructor functions duplicated from *Simulation.py*. Nothing imported it, the copies had drifted, and 
    they contained a bug in `rows_match` that had already been fixed in *Simulation.py*.
  - It is now a thin shim that re-exports the *Simulation.py* implementations, so any old script importing from it 
    keeps working. Running it directly still prompts for an input file and a run name.
  - **Use `main.py` (or `Simulation.run_model` / `Simulation.run_collection`) instead.**
  - An annotated copy of the original 629-line file is kept at 
    *Obsolete/Optimization_Review_2026-08-09/runScenarioFiles_PRE_OPTIMIZATION.py*.
- *Setup.py*
  - This module was created to contain methods designed to facilitate the instantiation of the various components and
    parameters classes required to run the model.
- *Simulation.py*
  - This module contains classes and methods pertaining to the simulation algorithm and its results.
- *TimeManage.py*
  - This module was created to contain methods related to time and keeping track of it for the simulation. Some have been
    deprecated in favor of the pandas.Timestamp functionality.


# -----Using the Model-----

## -----Setting Up Simulation-----

As mentioned in the File Structure Section, the model uses Excel files contained in the **InputFiles** subdirectory. 
It is recommended to use the *Empty.xlsx* file and save as a new file and update the file title in the top right 
corner of the sheet.

Every input in the file has a respective column, which is detailed below:
  - Temporal Inputs:
    - ScenarioID: The number of the simulation within the set. Starts at 1.
      - Note: it is **VITALLY** important that no 2 scenarios share this attribute, or else the second of the 2 will 
        overwrite the results of the previous.
      - This attribute is how you identify this individual run's pkl file within its output folder. (See Model Results 
        section)
      - Start Date: The starting date of the simulation
        - Must be formatted dd-mm-yyyy
        - Must be BEFORE End Date.
      - End Date: The ending date of the simulation
        - Must be formatted dd-mm-yyyy
        - Must be AFTER Start Date
      - Year: The year of the simulation
        - Superseded by Start and End Date. In other words, this input will be ignored if start date is given.
      - Simulation Days: The number of days to be simulated.
        - Superseded if End Date is given.
      - Start Day: The day of year (out of 365/6) on which the simulation starts.
    - **Note**:
      - You need not fill every temporal input, since some supersede others. The model only needs that which allows 
        it to know the start and end of the simulation.
      - If every input is filled, the model will only use the start date and end date inputs.
      - In the absense of any input the model will default to 1/1/2018 and simulate the full calendar year. 
      - The following are valid inputs combinations:
        - Start Date only ---> End Date defaults to 12/31 of same year
        - Start Date, End Date
        - Start Date, Simulation Days
        - End Date only ---> Start Date defaults to 1/1 of same year
        - End Date, Start Day
        - End Date, Simulation Days
        - Year only ----> full calendar year
        - Year, Simulation Days ---> counted from 1/1
        - Year, Start Day ---> rest of calendar year
        - Year, Simulation Days, Start Day
  - City Inputs:
    - Zip Code : The zip code of the locality.
      - This is the only input needed, and it is recommended you use it.
    - City : The name of the city.
      - Instead of the zip code you can specifically name the city.
    - State: The name of the state.
      - Must use abbreviation (ie, Georgia ---> GA)
    - **Note:**
      - The model only needs the zip code to fix the location and pull all the necessary data locality specific data.
        However, you can give it a city, state (abbrev) combination.
  - Utility Inputs:
    - Utility Name : The name of the utility
    - Utility File : The utility file (from **Utilities** directory).
      - Superseded the Utility Name input
    - Tariff ID: The name of the actual tariff schedule provided by the utility. 
      - Under "Name" column in the utility's file.
      - Ex: Georgia Power -----> "Schedule TOU-PEV-9 - Plug-in Electric Vehicle"
    - Net Meter Type: The net metering policy. Matched case-insensitively against these groups
      (`Simulation.py:147-155`); any value outside them is treated as unrecognized and falls through
      to the utility's own default:
        - `one-to-one` / `full`: Excess solar is sold back to the grid at full retail rate. Most profitable for
          solar.
        - `netbilling` / `net billing` / `net_billing`: Solar *in excess of usage* is compensated at a lower rate.
        - `none` / `no compensation`: No compensation for excess solar.
        - `no excess` / `no extra` / `no_excess`: No compensation, and excess generation isn't carried over either.
        - `nem 3.0` / `nem3` / `nem3.0`: California's NEM 3.0 successor-tariff policy. Used by several of the
          sample/`FullV2H` input files.
        - `nbc` / `non_bypassable` / `nonbypassable` / `non-bypassable`: Compensated at retail rate minus
          non-bypassable charges.
        - `wholesale` / `avoided cost`: Excess solar is sold back at an avoided-energy rate (a low, state-specific
          rate). Least profitable for solar, and the default when nothing else applies.
        - `sellback` / `Sellback` (checked case-sensitively, unlike every other group above): a separate
          buyback-only scheme.
    - **Note:**
      - If none of these inputs are provided, the model will default to the first utility listed for the zip code 
        provided in City Inputs, with the tariff being the one with the greatest TOU price differential.
      - The default net meter policy is 'wholesale' if policy is not dictated in *Utilities.csv*
      - If no tariffID is provided, then the model will default to the tariff with the greatest TOU price 
        differential that the provided utility has.
  - House Inputs:
    - Load Amount: The amount of electricity used in a calendar year (in kWh).
      - With this amount the model will aggregate a profile based on the stock load profiles from NREL ResStock with 
        the yearly totals closest to this input.
    - Load File: A pre-processed 5-min resolution load file pulled from **City Data/Load Profiles/Custom Loads**
      - This input supersedes all others in this category
    - User File: An unprocessed user file straight from a utility. This functionality is not complete in the model.
    - **Note:**
      - The user file input should not be used.
      - If all inputs are left blank the model will default to a Load Amount value of 11000 kWh.
      - Load profiles will be made to match the user's temporal inputs. 
  - Grid Inputs:
    - Use Cambium: Whether to use NREL's Cambium files for the location provided. (TRUE or FALSE)
    - Use WattTime: Whether to use real, dated WattTime grid CO2 data for the balancing-authority region
      covering the location provided. (TRUE or FALSE)
      - Requires the city's WattTime region to have been resolved first (Data Import Wizard's WattTime tab ->
        "Resolve All Regions" or a Single City fetch), and that region's file to have been fetched for the
        target year.
      - Supersedes Use Cambium if both are set.
    - WattTime Year: Which fetched WattTime calendar year to use. Optional -- defaults to
      `Simulation.WATTTIME_DEFAULT_YEAR` if left blank.
    - Other File: a 5-min resolution emissivity (kg CO2/kWh) file, if one wishes to NOT use the Cambium/WattTime
      files. Checked in both **City Data/CO2 Profiles/Custom** and **City Data/CO2 Profiles/WattTime/Processed**.
      - This input supersedes Use Cambium, but not Use WattTime.
      - Must take care that the length of this file matches the temporal inputs.
  - Solar Inputs:
    - System Size (kW): The kW rating of the PV array.
      - Set to 0 if you wish to not have a PV array included in simulation
    - PV Brand: The brand of the PV array
    - PV Model : The model of the PV array
    - Other Solar File : An alternative GHI file, or else the model will use the ones derived from NREL's NSRDB for 
      the location provided.
      - Must be 5-min resolution, see City Data files for format.
      - Must match the temporal inputs (match dates).
    - **Note:**
      - Generally speaking, it is sufficient to simply put the system size and nothing else. You may add PVs to the 
        PV file (see *PVs.xlsx* in **Model Data** directory) in order to simulate a specific array.
      - In this absense of a brand or model, the model will default to the "Custom" array in the PV file. Solar 
        cost will be determined by the $/W rating for each state (see *States.csv*).
    - HES Inputs
      - Size (kWh): The size of the HES battery in kWh.
        - Set to 0 if you do not wish to have an HES included in the simulation. 
      - HES Min SoC: The minimum allowable state of charge. 
        - The model will not allow the HES to deplete below this limit. 
        - Must be between 0 to 100%. Recommended value is 20%
      - HES Max SoC: The maximum allowable state charge.
        - The model will not allow the HES to charge above this limit.
        - Must be between 0 to 100%. Default is 100%
      - Optimization: The optimization scheme for the HES
        - This governs how the model determines what state of charge (SoC) to charge the HES to in order to cover 
          the peak periods of electricity cost.
        - The functional schemes are listed here (only use these):
          - Simple: The model calculates the expected output from the PV array (in kWh) and the expected house need (in 
            kWH) for the entire peak period and charges enough to cover the difference.
          - Flat: The model charges the HES to the same SoC every time, which is hard set to 80%.
          - Full Charge: The model fully charges the HES, which is not the optimum strategy as it prevents capture 
            of excess solar energy, which in the absense of true net metering is often compensated poorly.
      - EV Inputs:
        - EV File:
          - An Excel file containing a list of all the EVs desired for the simulation, contained in a Fleet object.
          - These files can be found in **InputFiles/EV Files**
          - They include the SAME inputs as the rest of the inputs from this section, but each row signifies a 
            different EV model/trim.
        - Discharge Limit: The threshold below which vehicle-to-house (V2H) discharge is disabled.
          - If you wish to disable V2H entirely, then set to 100%
        - EV Min SoC: The minimum state of charge allowed (similar the HES input)
          - Not the same as discharge limit, as this prevents driving too.
        - EV Max SoC: the maximum allowable state of charge (similar to HES input)
          - Prevents model from charging EV beyond this limit.
        - EV Year: The model year of the EV
        - Make: The make of the EV.
        - Model: The model of the EV.
        - Trim: The trim level of the EV.
        - Pattern: The driving pattern file which governs when and how far the EV drives.
          - Contained in **DrivingPatterns** directory.
        - Qty: The number of this specific EV to add to the fleet.
        - Charge Type: How the EV charges. Only two values change behavior (`Components.py:986,1099`):
          `trickle charge` and `frontend`. Any other value (including blank) uses the default charging
          behavior.
      - **NOTE:**
        - Use the EV file input if you wish to have multiple DIFFERENT EVs included in the fleet.
          - As previously stated, the inputs in the EV files match the inputs in this section.
        - The model uses the year, make, model, trim inputs to locate the EV in the main EV file (see *EVs.xlsx* in 
          the **Model Data** directory) and pulls the necessary data (efficiency, battery, etc.) to create the EV 
          object for the model.

## -----Running the Simulation-----

Now that we've set up an input file (or a whole collection of them -- see *InputBuilderWizard.py* above for a GUI
that builds either), we're ready to run the model. Use `main.py` (edit the call at the bottom and run it), or call
`Simulation.run_model`/`Simulation.run_collection` directly from your own script or an IDE.
**`runScenarioFiles.py` is deprecated** -- see the File Structure section above.

- `run_model(input_file, collection_name, ...)` runs every scenario in one input file.
  - `input_file`: the input workbook's path under **InputFiles/**, without the `.xlsx` extension.
  - `collection_name`: the name given to this set of runs. The model creates a subdirectory by this name under
    **Outputs/**, so avoid characters forbidden in a directory name (`/ \ : * ?`). Using the same name as your
    input file (or a close variant) keeps things easy to track.
  - Leave both blank and it will prompt for them interactively instead.
- `run_collection(collection_path, ...)` runs every input file in an **InputFiles/** subdirectory (a collection
  folder, e.g. one built by *InputBuilderWizard.py*'s Collection tab), in parallel across worker processes.
  - `schedule='auto'` (the default) hands out whole input files while there are enough of them to keep every
    worker busy, and only starts splitting a file's remaining scenarios once fewer files remain than workers --
    so no core sits idle waiting on a single large straggler file, without paying a per-file rebuild cost when
    it isn't needed. `'file'` and `'chunk'` are also selectable for the old all-or-nothing behavior.
  - `console_verbose=True` prints every scenario's completion/error line (still cleanly ordered even with many
    worker processes -- see *Progress.py*); `show_gui=True` pops up a live Tkinter window with a progress bar
    per input file, an overall ETA, and which worker(s) are on each file.
  - `consolidate_results=True` (only meaningful alongside `save_pickles=True`) writes one shared results store
    per input file instead of thousands of individual pickle files -- see **Outputs/** above.

While running, the model prints each scenario as it completes, along with how long it took.

## -----Simulation Results-----

As the model completes each scenario, it appends a row to that run's summary CSV/Parquet store (see
**Outputs/** in the File Structure section) with the scenario's inputs and outputs. Saving the full `Results`
object (every component instance used in the simulation) to a pickle file is opt-in via `save_pickles=True`
(and `full_results=True` if you also want the full time-series data, not just summary scalars) -- most workflows
don't need this, since the summary/Parquet already holds everything a `full_results=False` pickle would.
Run *ResultsGUI.py* to open a GUI capable of reading either individual pickle files or a `consolidate_results`
store.

In addition, the model will save a summary csv file into the simulation's subdirectory with each scenario getting a 
row with its inputs and outputs outlined. The columns of this summary file are as follows:

- *ID*: The ID no of the scenario within the input file.
- *File Name*: Informational only, reflecting whatever `save_pickles` produced -- the resulting `.pkl`/`.pkl.gz`
  filename, a `store.dat#scenarioID` reference if `consolidate_results=True`, or a synthesized name if
  `save_pickles=False` (no pickle file exists).
- *Time Elapsed (s)*: Amount of time the individual scenario took to run.
- *Start Date*: Starting date of simulation
- *End Date*: Ending date of simulation
- *City*: Locality of the the household simulated.
- *State*: State of the household simulated.
- *Reference City*: The nearest reference city to the locality, for which house load, solar, and emissivity data is 
  pulled.
- *Reference State*: The state of the nearest reference city.
- *House Load*: Total household electricity need (in kWh)
- *Utility*: Name of the utility
- *Tariff*: Name of the tariff schedule
- *Net Meter Policy*: the net metering policy used by the utility
- *Solar Model*: the model of the PV array
- *Solar Size (kW)*: the kW rating of the PV array
- *Solar Cost ($)*: the cost of the solar array
- *HES Size (kWh)*: the battery size of the HES
- *HES Optimization*: the optimization strategy used in the simulation (see Setting Up Simulation section)
- *HES Avg SoC Target*: The average target state of charge of the HES for peak shaving. 
- *EV Models*: A list of the EV models in the Fleet.
- *EV Discharge Limit*: The discharge limit of the EVs in the fleet.
- *Fleet Cost ($)*: The total msrp of the EVs in the fleet.
- *Total Bill ($)*: The total electricity bill.
- *Total CO2 (kg)*: The total CO2 emissions.
- *PV Avoided Cost ($)*: The electricity cost avoided (value saved) by using the PV.
- *PV Avoided CO2 (kg)*: The CO2 emissions avoided (value saved) by using the PV.
- *HES Avoided Cost ($)*: The electricity cost avoided (value saved) by using the HES during peak hours.
- *HES Avoided CO2 (kg)*: The CO2 emissions avoided (value saved) by using the HES during peak hours.
- *Fleet Avoided Cost ($)*: The electricity cost avoided (value saved) by using V2H with the EVs during peak hours.
- *Fleet Avoided CO2 (kg)*: The CO2 emissions avoided (value saved) by using V2H with the EVs during peak hours.
- *Fleet Sim Miles (mi)*: The total number of simulated miles on the EVs from V2H discharge.
- *Fleet Driven Miles (mi)*: The total number of actual miles driven by the EVs.
- *EV Degradation ($)*: The estimated degradation cost of the EVs from V2H discharge
- *EV Breakeven Mileage (mi)*: The mileage lifetime of the EV battery necessary to break even with V2H discharge.
- *EV Breakeven Cost ($/kWh)*: The unit cost for an EV battery necessary to break even with V2H discharge.
- *System Loss (kWh)*: The amount of energy lost through inefficiencies in energy transfer between components. 
- *Cost of Loss (kWh)*: The loss of value ($) from energy loss.
- *Emissions from Loss (kg)*: The amount of increased emissions from energy loss.
- *Fleet Driving Cost ($)*: The total electricity cost due to EV driving.
- *Gas Savings ($)*: The gasoline savings from driving EVs vs ICEs.
- *Total Avoidance ($)*: The total electricity cost avoided by using the household components (HES, PV, EV)
- *Total Savings ($)*: The total value gained from the components (Avoidance + Gas Savings)
- *System Cost ($)*: The total cost of the system (excluding EV cost)
- *Baseline Savings ($)*: The total **electricity** savings over the baseline case (baseline being no PV, HES, or V2H 
  discharge)
- *Net Value ($)*: Total baseline savings minus the cost of any EV degradation.
- *Baseline Savings (kg CO2)*: The total **emissions** savings over the baseline case.
- *System Payback Period*: The years require to pay back the system with the current net value generated (per annum)
- *System Cost Efficiency*: The percent of the system cost generated back by the system (per annum)
- *System Total Peak Shaving Efficiency*: The percent of the total non-offpeak (ie on-peak and mid peak) house need 
  covered by the PV-HES-EV system and not the grid. 
- *System High Peak Shaving Efficiency*: The percent of the total on-peak house need covered by the PV-HES-EV system 
  and not the grid.
- *Is Baseline*: Whether the scenario was baseline scenario (no HES, no PV, no V2H enabled). Note EV is still present.