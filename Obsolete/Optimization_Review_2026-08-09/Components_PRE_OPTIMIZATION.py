# ##############################################################################################################
# ARCHIVED PRE-OPTIMIZATION COPY -- Components.py
# ##############################################################################################################
#
# This is Components.py as it stood BEFORE the August 2026 optimization pass, reconstructed by
# reverse-applying every change and then VERIFIED: running this copy reproduces the original
# 6-scenario benchmark timing and results that are bit-identical to the pre-change baseline
# across 16 pickled Results objects and four 55-column summary CSVs.
#
# It is kept for review only. It is NOT imported by anything and must not be.
#
# Annotations are inserted directly above the code they describe, tagged:
#     [T1-nn]   APPLIED   -- runtime work, already live in the root module
#     [T1.9-nn] PROPOSED  -- collection scheduling
#     [T2-nn]   PROPOSED  -- results storage
#     [T3-nn]   PROPOSED  -- correctness fixes (these change outputs)
#     [T4-nn]   PROPOSED  -- conventions, typing, dead code
#
# Measured effect of the APPLIED work: 3.13 -> 1.44 s per scenario (2.17x), outputs unchanged.
# Full write-up: PROPOSED_CHANGES.md and ARCHITECTURE.md in the repository root.
# ##############################################################################################################

"""
Summary
-------
This module contains classes for each of the physical components of the model and their interactions. In short,
if you can touch it in real life, it is present in this module.

Classes
-------
    -   Component - master class to Grid, House, PV, Battery, EV, and HES classes
    -   Battery - master class to HES and EV classes (inherits Component)
    -   House - class representing the household (inherits Component)
    -   Grid - class representing the grid (inherits Component)
    -   PV - class representing a photo voltaic system installed on the house (inherits Component)
    -   EV - class representing an electric vehicle which leaves and returns to the house (inherits Battery)
    -   HES - class representing a home energy system (think Tesla Power-wall) inside the house (inherits Battery)
    -   Fleet - class representing a collective of EVs.
    -   Energy - a class which tracks the energy flows between each component like a multi-directional meter.
    -   ICE - a class representing an internal combustion vehicle. It is used for gasoline and CO2 savings for EVs.
"""
# ================================================================================================================
# [T1-01] APPLIED -- Cached readers for repeatedly-parsed data files
# LOCATION: module header
# ----------------------------------------------------------------------------------------------------------------
# WHY:  Operation() re-read Model Data/efficiencies.xlsx on every construction -- once per scenario,
#       measured 46.5 ms. PV.__init__ re-read PVs.xlsx (52 ms) and PV.load_solar re-parsed a
#       105,120-row GHI csv with date parsing (86 ms) every time PV size changed, which in the
#       Top20/Top30 sweeps is nearly every row. None of this data changes during a run.
# NEW:  three @lru_cache readers keyed on (path, mtime) plus a _cached_read() helper, added above
#       class Component. Editing a workbook mid-session still invalidates the entry.
# IMPACT: ~185 ms per scenario. Across a 20-file collection the efficiencies read alone was
#       roughly 32 minutes of pure Excel parsing.
# ================================================================================================================
import numpy as np
from Parameters import *
import pandas as pd
import DataProcessing as dp
from numpy import ndarray


class Component:
    """
    This class is the parent class for all physical components of the model.

    Notes
    -----
    Each component will be treated as an energy sink, source, or both at a given timestep:
            - Sink - receives energy from source components
            - Source - gives energy to the sink components
    A list of components and their sink/source designation can be seen below. HES and EV can be both due to their status
    as a battery (see Battery class):
            - Grid - source only
            - PV- source only
            - House - sink only
            - HES - both
            - EV - both
    .

    The component class has attributes describing whether that component must be or can be a source or sink depending
    on the conditions. The components also have cost of use and emissivity attributes. Cost of use describes how much
    energy SUPPLIED from that component costs. Emissivity describes how much CO2 is emitted by using that component
    to supply energy. These attributes are only relevant to components other than the house (since it is always a
    sink):

    Attributes
    ----------
    name : str
        type of component (ie, House, PV, etc.). Each subclass has a different name.
    must_be_sink : bool
        component has to be added to sink list (ie, a depleted battery, or the house).
    must_be_source : bool
        component has to be added to source list (ie, a full battery, or the PV system).
    can_be_sink : bool
        component can be a sink but is not required to be (ie, a battery neither depleted nor full).
    can_be_source : bool
        component can be a source but is not required to be (ie, a battery neither depleted nor full).
    can_be_used : bool
        component can be used at all as a sink or source (EV away from home can't be used).
    cost_of_use : float
        current cost of power supplied from source ($/kWh).
    cost_of_uses : np.ndarray
        numpy array of component cost of uses for each timestep.
    emissivity : float
        current emissivity (kg CO2 / kWh) of the component.
    emissivity_arr : np.ndarray
        numpy array of component emissivities for each timestep.
    """

    def __init__(self):
        self.name = 'Component'
        self.can_be_sink = True
        self.can_be_source = True
        self.must_be_sink = False
        self.must_be_source = False
        self.can_be_used = True  # can component be utilized at all
        self.cost_of_use = 0
        self.cost_of_uses = np.array([])
        self.emissivity = 0
        self.emissivity_arr = np.array([])

    def get_cost_of_use(self):
        """
        Returns the current cost of use of the component (redundant, to be removed)

        Returns
        -------
        float
            cost of use of the given component ($).
        """
        return self.cost_of_use

    def initialize_cost_of_use(self, tou_cost, efficiency, cost_of_use_track=True, num_steps=105120):
        """
        This function must be called for each component to preallocate the arrays to track cost of use over time.

        Parameters
        ----------
        tou_cost : float
            the cost of electricity from the grid at the start of the simulation.
        efficiency : float
            efficiency of energy transfer FROM grid to component (100% if component is grid itself).
        cost_of_use_track : bool, optional
            boolean which tells model to track costs of use for each timestep. Default is TRUE.
        num_steps : int, optional
            number of timesteps in simulation. Default is 105120, which is 5-min steps for a calendar year.

        Returns
        -------
        None
        """
        # ================================================================================================================
        # [T1-02] APPLIED -- 1-D tracking arrays (cost of use)
        # LOCATION: Component.initialize_cost_of_use
        # ----------------------------------------------------------------------------------------------------------------
        # WHY:  arr[i] += x on an (N, 1) column vector measures 0.61 us; on a flat (N,) array, 0.13 us.
        #       That is 4.7x, and this array is written once per timestep (105,120 times per scenario).
        # NEW:  self.cost_of_uses = np.zeros(num_steps)
        # NOTE: every (N, 1) allocation in the model was converted together -- cost_of_uses,
        #       emissivity_arr, socs, energy_profile, emissions_rate and all Energy trackers -- because
        #       converting only some of them would create silent broadcasting bugs where they meet.
        # ================================================================================================================
        self.cost_of_use = round(tou_cost / efficiency, 4)
        if cost_of_use_track:
            self.cost_of_uses = np.zeros((num_steps, 1))

    def initialize_emissivity(self, grid_intensity, efficiency, num_steps=105120):
        """
        This function must be called for each component to preallocate the arrays to track cost of use over time.

        Parameters
        ----------
        grid_intensity : float
            the emissivity (kg CO2/kWh) of the grid at the start of the simulation.
        efficiency : float
            efficiency of energy transfer FROM grid to component (100% if component is grid itself).
        num_steps : int, optional
            number of timesteps in simulation. Default is 105120, which is 5-min steps for a calendar year.

        Returns
        -------
        None
        """
        # ================================================================================================================
        # [T1-03] APPLIED -- 1-D emissivity array + true scalar emissivity
        # LOCATION: Component.initialize_emissivity
        # ----------------------------------------------------------------------------------------------------------------
        # WHY:  same 1-D rationale as T1-02. Additionally the scalar was a 1-element ndarray rather than a
        #       float, so every downstream arithmetic use paid NumPy dispatch cost.
        # NEW:  self.emissivity = float(np.round(grid_intensity / efficiency, 4))
        #       self.emissivity_arr = np.zeros(num_steps)
        # ================================================================================================================
        self.emissivity = np.round(grid_intensity / efficiency, 4)
        self.emissivity_arr = np.zeros((num_steps, 1))
        self.emissivity_arr[0] = self.emissivity

    def can_be_sink_update(self, status: bool):
        """
        This method updates the can_be_sink attribute based on boolean parameter status. In either case,
        the must_be_sink attribute is set to False. In cases where we want must_be_sink to be TRUE,
        we call must_be_sink_update instead.

        Parameters
        ----------
        status : bool
            what we wish to set attribute to (TRUE or FALSE)

        Returns
        -------
        None
        """
        self.can_be_sink = status
        self.must_be_sink = False

    def can_be_source_update(self, status: bool):
        """
        This method updates the can_be_source attribute based on boolean parameter status. In either case,
        the must_be_source attribute is set to False. In cases where we want must_be_source to be TRUE,
        we call must_be_source_update instead.

        Parameters
        ----------
        status : bool
            what we wish to set attribute to (TRUE or FALSE)

        Returns
        -------
        None
        """
        # ================================================================================================================
        # [T3-08] PROPOSED -- Annotation statement instead of an assignment
        # LOCATION: Component.can_be_source_update
        # ----------------------------------------------------------------------------------------------------------------
        # The next line reads:      self.must_be_source: False
        # That is a variable ANNOTATION, not an assignment -- it evaluates nothing and stores nothing.
        # The method silently fails to clear must_be_source, unlike its three siblings which all clear the
        # opposing flags. Pylance flags this as a useless expression.
        # FIX: self.must_be_source = False
        # ================================================================================================================
        self.can_be_source = status
        self.must_be_source: False

    def must_be_sink_update(self, status: bool):
        """
        This method updates the must_be_sink attribute based on boolean parameter status. In either case,
        the can_be_sink attribute is set to TRUE and the can_be_source and must_be_source attributes are set to FALSE.

        Parameters
        ----------
        status : bool
            what we wish to set attribute to (TRUE or FALSE)

        Returns
        -------
        None
        """
        self.must_be_sink = status
        self.can_be_sink = True
        self.must_be_source = False
        self.can_be_source = False

    def must_be_source_update(self, status: bool):
        """
        This method updates the must_be_source attribute based on boolean parameter status. In either case,
        the can_be_source attribute is set to TRUE and the can_be_sink and must_be_sink attributes are set to FALSE.

        Parameters
        ----------
        status : bool
            what we wish to set attribute to (TRUE or FALSE)

        Returns
        -------
        None
        """
        self.must_be_source = status
        self.can_be_source = True
        self.must_be_sink = False
        self.can_be_sink = False

    def can_be_used_update(self, status: bool):
        """
        This method updates the usability status of the component base on boolean parameter status. If status is
        FALSE, all sink/source attributes are set to FALSE.

        Parameters
        ----------
        status : bool
            what we wish to set attribute to (TRUE or FALSE)

        Returns
        -------
        None
        """
        self.can_be_used = status
        if not status:
            self.must_be_source = False
            self.can_be_source = False
            self.must_be_sink = False
            self.can_be_sink = False

    def status_reset(self):
        """
        This method simply resets all sink/source attributes to FALSE.

        Returns
        -------
        None
        """
        self.must_be_source = False
        self.can_be_source = False
        self.must_be_sink = False
        self.can_be_sink = False


class House(Component):
    """
    This class represents the household portion of the model. It is the primary energy sink and contains an energy
    consumption profile. It inherits the Component class and contains unique attributes.

    Parameters
    ----------
    load_file : str, optional
        filepath for the csv which contains the load profile for the house. Supersedes load_profile, but one must be
        given. Default is None.
    load_profile : array_like, optional
        Numpy array which represents the load profile for the house. Default is None

    Attributes
    ----------
    load_file : str
        filepath for the csv which contains the load profile for the house. Supersedes load_profile, but one must be
        given.
    load_profile : array_like
        An N x 2 numpy array, where N is the number of 5-min timesteps in the simulation. First column is timestep,
        the second is the house load (kW).
    energy_profile : array_like
        An numpy array of identical dimension to load_profile. It's second column represents the ENERGY required by
        the house in kWh at a given timestep. Initially all zeros but updated at each step.
    sink_priority : int
        Number representing the priority in which components are listed in the sink list. The lower the number the
        higher the priority. For the House component, this value is set at -999, and will always be lowest.
    energy_required : float
        Energy required by the house at a given timestep.
    usage : float
        Total energy required by the household for the simulation

    Notes
    -----
    Initialization requires that either the load_file or load_profile parameters be filled. Failure to
    provide at least one will result in an error.


    """

    def __init__(self, load_file=None, load_profile=None):
        # given EITHER load file or a load profile, create a house object. Load file takes supremacy.
        super().__init__()
        self.name = 'House'
        self.can_be_sink = True
        self.can_be_source = False
        self.must_be_sink = True
        self.must_be_source = False
        self.load_file = load_file
        if load_file is not None:
            self.load_profile = self.generate_load()
        else:
            self.load_profile = np.round(load_profile, 3)
        self.energy_profile = np.array([])
        self.sink_priority = -999  # sort ascending, house will always be first
        self.energy_required = 0
        self.usage = 0

    def reset(self):
        """
        This method resets the House instance for use in another simulation using the same load profile (if running
        multiple). This prevents having to reload the same load profile.

        Returns
        -------
        None
        """
        self.can_be_sink = True
        self.can_be_source = False
        self.must_be_sink = True
        self.must_be_source = False
        self.energy_profile = np.array([])
        self.usage = 0

    def initialize_energy_profile(self, num_steps: int):
        """
        This method initializes energy_profile given the number of steps in the simulation.

        Parameters
        ----------
        num_steps : int
            number of steps in the simulation.

        Returns
        -------
        None
        """
        # ================================================================================================================
        # [T1-05] APPLIED -- 1-D house energy profile
        # LOCATION: House.initialize_energy_profile
        # ----------------------------------------------------------------------------------------------------------------
        # NEW:  self.energy_profile = np.zeros(num_steps)     # see T1-02
        # ================================================================================================================
        self.energy_profile = np.zeros((num_steps, 1))

    def generate_load(self):
        """
        This method generates a load profile from the csv file given by the load_file attribute of the House
        instance and returns it into the load_profile attribute.

        Returns
        -------
        array_like
            Numpy array of dimensions Nx2, where N is the number of timesteps. 2nd column is house power draw (kW)

        Returns
        -------
        None
        """

        lp = pd.read_csv(self.load_file, usecols=['Load(kW)']).to_numpy()
        lp = np.round(lp.flatten(), 3)

        return lp

    def get_load(self, index):
        """
        This method returns the house load (kW) at a given index of load_profile

        Returns
        -------
        float
            household load in kW
        """
        return self.load_profile[index]

    def get_energy_required(self, index, timestep=5):
        """
        This method returns the energy (kWh) required by the household at given time (index).

        Parameters
        ----------
        index : int
            index within load_profile corresponding to current step in simulation.
        timestep : int, optional
            duration of each timestep in minutes. Default is 5 minutes.

        Returns
        -------
        float
            energy required by house (kWh) at the given time."""

        self.energy_required = self.load_profile[index] * (timestep / 60)
        return self.energy_required

    def record_energy(self, index):
        """
        This method records the energy required by the house into the energy_profile attribute at the desired index.

        Parameters
        ----------
        index : int
            index within energy_profile to store the value of the current energy_required attribute.

        Returns
        -------
        None
        """

        self.energy_profile[index] = self.energy_required
        self.usage += self.energy_required


class Grid(Component):  # Object representing the grid/meter
    """
    This class represents the grid. It will always be a source, with any net metering being recorded in the Energy
    class. It inherits the Component class, and contains unique attributes and methods.

    Parameters
    ----------
    flat_emission_rate : float, optional
        Average emissivity for the grid (independent of time). Used to account for emissions in absense of
        time-dependent emissions profile (see emission_file)
    emission_file : str, optional
        String containing filepath to csv file of emissions profile

    Attributes
    ----------
    sourceID : array_like
        1x1 array containing the source index for use in the 6x6 efficiencies matrix (see Parameters.Operation).
    sinkID : array_like
        1x1 array containing the sink index for use in the 6x6 efficiencies matrix (see Parameters.Operation)
    flat_emission_rate : float
        Average emissivity for the grid (independent of time). Used to account for emissions in absense of
        time-dependent emissions profile (see emission_file)
    emission_file : str
        String containing filepath to csv file of emissions profile
    emissions_rate : array_like

    """

    def __init__(self, flat_emission_rate=.401, emission_file=None):
        super().__init__()
        self.name = 'Grid'
        self.can_be_sink = True
        self.can_be_source = True
        self.must_be_sink = False
        self.must_be_source = False
        self.used_as_sink = False  # used as sink in particular timestep
        self.used_as_source = False  # used as source in particular timestep
        self.sourceID = np.array([5])
        self.sinkID = np.array([5])
        self.emission_file = emission_file
        self.cost_of_uses = np.array([])
        # ================================================================================================================
        # [T1-06] APPLIED -- Flatten emissions profile + add Python-list fast path
        # LOCATION: Grid.__init__
        # ----------------------------------------------------------------------------------------------------------------
        # WHY:  pd.read_csv(...).to_numpy() yields (N, 1) while the flat-rate branch yields (N,) -- the two
        #       constructor paths disagreed on shape. Both are now 1-D via .ravel().
        # ALSO: self._emissions_list = self.emissions_rate.tolist() is kept alongside. See T1-08.
        # NEW:  self.emissions_rate = np.round(pd.read_csv(emission_file).to_numpy(), 4).ravel()
        #       self._emissions_list = self.emissions_rate.tolist()
        # ================================================================================================================
        self.flat_emission_rate = flat_emission_rate
        if self.emission_file is None:
            self.emissions_rate = np.ones(105120) * flat_emission_rate  # average grid emissions for US
        else:
            self.emissions_rate = np.round(pd.read_csv(emission_file).to_numpy(), 4)
        self.changed_dates = False

    def change_dates(self, file_year=2022, start_date=pd.to_datetime('1/1/2018'),
                     end_date=pd.to_datetime('12/31/2018 23:55'), cambium=True):
        """
        This method is used to reconstitute the given calendar year emissions profile (emissions_rate) into a
        profile between any two arbitrary dates.

        Parameters
        ----------
        file_year : int, optional
            year of the original emissions profile. Default is 2022.
        start_date : pd.Timestamp, optional
            pandas timestamp of the desired start date. Default is 1/1/2018 to match with solar and house load data.
        end_date : pd.Timestamp
            pandas timestamp of desired end date. Default is 12/31/2018 to match with solar and house load data.
        cambium : bool
            Using the cambium profile or not
        Returns
        -------
        None
        """

        if self.changed_dates:
            if self.emission_file is None:
                self.emissions_rate = np.ones(105120) * self.flat_emission_rate  # average grid emissions for US
            else:
                self.emissions_rate = np.round(pd.read_csv(self.emission_file).to_numpy(), 4)

        file_dow = pd.to_datetime(file_year).day_of_week
        new_arr = np.array([])
        year_list = list(range(start_date.year, int(end_date.year + 1)))
        for year in year_list:  # stack years for however many years, and correct for leap years
            new_year_start_dow = pd.to_datetime(str(start_date.year)).day_of_week
            if cambium:
                adj_emissions = dp.shift_cambium(self.emissions_rate, target_year=year)
            else:
                day_shift = new_year_start_dow - file_dow
                if day_shift > 3:  # correct value to cause minimum shift in days
                    day_shift -= 7
                elif day_shift < -3:
                    day_shift += 7
                adj_emissions = dp.shift_by_day(profile=self.emissions_rate, days=day_shift,
                                                leap=pd.to_datetime(str(year)).is_leap_year)
            new_arr = np.append(new_arr, adj_emissions)

        s_i = (start_date.day_of_year - 1) * (12 * 24)
        e_i = s_i + ((end_date - start_date).days + 1) * (12 * 24) - 1
        # ================================================================================================================
        # [T1-07] APPLIED -- Drop the reshape back to (N, 1)
        # LOCATION: Grid.change_dates
        # ----------------------------------------------------------------------------------------------------------------
        # NEW:  self.emissions_rate = new_arr[s_i:(e_i + 1)]
        #       self._emissions_list = self.emissions_rate.tolist()   # keep the fast-path mirror in sync
        # ================================================================================================================
        new_arr = new_arr[s_i:(e_i + 1)]
        self.emissions_rate = new_arr.reshape((len(new_arr), 1))
        self.changed_dates = True

    def update_cost_of_use(self, index, tou_rate):
        """
        This method updates the cost_of_use and costs_of_uses attribute for the Grid object.

        Parameters
        ----------
        index : int
            the desired index within cost_of_uses you wish to update. Usually corresponds to current timestep in
            simulation by this equation (index = timestep - 1).
        tou_rate : float
            the current electricity rate ($/kWh) of the utility. (See Parameters.Tariff).

        Returns
        -------
        None
        """

        self.cost_of_use = tou_rate
        self.cost_of_uses[index] = tou_rate

    def update_emissivity(self, step):
        """
        This method updates the emissivity attribute to the value of the given timestep in the emissions profile.

        Parameters
        ----------
        step: int
            Current timestep in simulation. Not to be confused for index, which is used for array accessing though
            they are related by index = step - 1

        Returns
        -------
        None
        """

        # ================================================================================================================
        # [T1-08] APPLIED -- Read grid emissivity from a Python list
        # LOCATION: Grid.update_emissivity
        # ----------------------------------------------------------------------------------------------------------------
        # WHY:  called once per timestep (630,726 times across the 6-scenario benchmark). Indexing an
        #       ndarray returns a boxed np.float64; a list lookup returns a float directly.
        # NEW:  self.emissivity = self._emissions_list[step - 1]
        # IMPACT: 0.475 s -> 0.25 s of profiled self-time across the benchmark.
        # ================================================================================================================
        self.emissivity = self.emissions_rate[step - 1]

    def was_used_as_sink(self):
        """
        This method is used to set the used_as_sink attribute to TRUE. Called when grid has be used as a sink,
        such as for net metering. Note that no component can be used as a sink or source in the same timestep.

        Returns
        -------
        None
        """

        self.used_as_sink = True

    def was_used_as_source(self):
        """
        This method is used to update the used_as_source attribute to TRUE. Called when grid is used as a
        source. Note that no component can be used as a sink and source in the same timestep.

        Returns
        -------
        None
        """

        self.used_as_source = True

    def reset_sink_source(self):
        """
        This method is called to reset used_as_sink and used_as_source attributes to FALSE at the end of the
        timestep within the simulation.

        Returns
        -------
        None
        """

        self.used_as_sink = False
        self.used_as_source = False

    def reset(self):
        """
        This method resets the cost_of_uses for the Grid object for use in another simulation in lieu of
        instantiating another Grid object.

        Returns
        -------
        None
        """

        self.cost_of_uses.fill(0)


class PV(Component):  # Object representing a solar array
    """
    This class represents a PV array installed on the household. It will always be a source no matter the
    circumstance. It inherits the Component class but also has unique attributes and methods.

    Parameters
    ----------
    system_size : int, float
        The nominal size of the array in terms of kW rating.
    brand : str, optional
        The brand of PV given as a string. Used for selecting PV characteristics from PVs.csv file. Default is 'custom'.
    model : str
        The model designation of PV given as a string. Used for selecting PV characteristics from PVs.csv file.
        Default is 'custom'.

    Attributes
    ----------
    sourceID : array_like
        1x1 numpy array holding the row index of PV as a source in the efficiencies matrix (see
        Parameters.Operation). Set to [1].
    system_size : float, int
        The rated PV system size in kW.
    brand : str
        The brand of the PV.
    model : str
        The model designation of the PV.
    efficiency : float
        The conversion efficiency of the PV system from solar GHI to useful energy. Pulled from PVs.xlsx.
    panel_area : float
        The surface area on an individual panel in m^2. Pulled from PVs.xlsx.
    panel_cost : float
        The cost of an individual panel ($). Pulled from PVs.xlsx.
    panel_rating : int, float
        The rating of individual panels in W. Pulled from PVs.xlsx.
    system_area : float
        The calculated surface area of the entire PV system.
    ghi : array_like
        N x 1 numpy array containing the gross horizontal irradiance (W/m^2) obtained from NREL solar data where N is
        the number of steps.
    power : array_like
        N x 1 numpy array containing the power (in kW) coming through the panels at each timestep, where N is the
        number of steps.
    temperature : array_like
        N x 1 numpy array containing the outdoor temperature (in C) obtained from NREL data at each timestep.
    exists : bool
        a boolean for if the PV exists (non-zero PV size).
    energy_available : float
        the amount of energy (kWh) provided by the PV in the current timestep
    """

    def __init__(self, system_size=5, brand='custom', model='custom'):
        super().__init__()
        self.name = 'PV'
        self.can_be_sink = False
        self.can_be_source = True
        self.must_be_sink = False
        self.must_be_source = True
        self.sourceID = np.array([1])
        self.system_size = system_size  # this is the system size AS RATED in kW
        self.brand = brand
        self.model = model
        # load panel from file
        # ================================================================================================================
        # [T1-09] APPLIED -- Use the cached PV catalogue
        # LOCATION: PV.__init__
        # ----------------------------------------------------------------------------------------------------------------
        # NEW:  pv_frame = _cached_read(_read_pv_catalog, 'Model Data/PVs.xlsx')      # 52 ms saved per PV
        # ================================================================================================================
        pv_frame = pd.read_excel('Model Data/PVs.xlsx')
        ind = pv_frame.index[(pv_frame['Brand'] == brand) & (pv_frame['Model'] == model)][0]
        self.efficiency = pv_frame.loc[ind, 'Efficiency']
        self.panel_area = pv_frame.loc[ind, 'Base Area(m^2)']
        self.panel_cost = pv_frame.loc[ind, 'Cost']
        self.panel_rating = pv_frame.loc[ind, 'Base Size (W)']  # rating for individual panel
        self.system_area = (self.system_size * 1000) / self.panel_rating * self.panel_area
        self.ghi = []
        self.power = []
        self.temperature = []
        self.exists = system_size != 0
        self.energy_available = 0

    def load_solar(self, solar_file, start_date=pd.to_datetime('1/1/2018'),
                   end_date=pd.to_datetime('12/31/2018 23:55')):
        """
        This method is called after instantiation and loads a given solar GHI  and temperature profile into the PV
        object. Also adjusts the profile to fit between any two arbitrary dates. Each solar profile is only a
        calendar year so this method will append copies of the profile at the end to span multiple years if
        necessary. Updates the ghi, temperature, and power attributes.

        Parameters
        ----------
        solar_file : str
            filepath of solar file (.csv format) which contains the desired GHI data.
        start_date : pandas.Timestamp, optional
            A pandas Timestamp representing the desired start date of the GHI profile. Default is '1/1/2018' which
            corresponds with the default house load data.
        end_date : pandas.Timestamp, optional
            A pandas Timestamp representing the desired end date of the GHI profile. Default is "12/31/2018 23:55"
            which is the last 5 minute timestep of the 2018 calendar year.

        Returns
        -------
        None
        """
        # ================================================================================================================
        # [T1-10] APPLIED -- Rebuild load_solar on cached NumPy arrays
        # LOCATION: PV.load_solar
        # ----------------------------------------------------------------------------------------------------------------
        # WHY:  this parsed a 105,120-row csv with date parsing (86 ms), then stacked years with repeated
        #       pd.concat, on every PV rebuild. The irradiance is identical across an entire PV-size sweep;
        #       only the panel scaling changes.
        # NEW:  base_ghi, base_temp = _cached_read(_read_solar_profile, solar_file), then the leap-year
        #       stacking is done with a list of slices and one np.concatenate, and only
        #       self.power = ghi * system_area * efficiency / 1000 is recomputed.
        # NOTE: the leap-year splice [0:16992] + [16704:] (duplicating Feb 28) is preserved exactly.
        # ================================================================================================================
        ghi_frame = pd.read_csv(solar_file, parse_dates=['Time'])
        new_frame = pd.DataFrame(columns=ghi_frame.columns)
        year_list = list(range(int(start_date.year), int(end_date.year + 1)))
        for year in year_list:  # stack years for however many years, and correct for leap years
            if pd.to_datetime(str(year)).is_leap_year:
                new_frame = pd.concat((new_frame, ghi_frame[0:16992]), ignore_index=True)
                new_frame = pd.concat((new_frame, ghi_frame[16704:]), ignore_index=True)
            else:
                new_frame = pd.concat((new_frame, ghi_frame), ignore_index=True)
        s_i = (start_date.day_of_year - 1) * (12 * 24)
        e_i = s_i + ((end_date - start_date).days + 1) * (12 * 24) - 1
        new_frame = new_frame[s_i:(e_i + 1)]
        self.ghi = np.round(new_frame['GHI(W/m^2)'].to_numpy(), 3)
        self.temperature = np.round(new_frame['Temp(C)'].to_numpy(), 3)
        self.power = np.round(self.ghi * self.system_area * self.efficiency / 1000, 3)  # kW coming through panels

    def get_ghi(self, index):
        """
        This method returns the GHI from the GHI profile at a given index corresponding to a desired timestep
        in the simulation.

        Parameters
        ----------
        index : int
            index within the ghi array attribute you wish to pull from.

        Returns
        -------
        float
            GHI (W/m^2) at a given index
        """
        return self.ghi[index]

    def get_power(self, index):
        """
        This method returns the power produced by the PV array from the power array attribute at given index
        corresponding to a desired timestep in the simulation.

        Parameters
        ----------
        index : int
            index within the power array attribute corresponding to the timestep in which you wish know the power.

        Returns
        -------
        float
            Power (kW) from the PV array
        """
        return self.power[index]

    def get_energy_available(self, index, timestep=5):
        """
        This method returns the total energy (kWh) provided using a provided index and timestep duration.

        Parameters
        ----------
        index : int
            index within the power array attribute corresponding to the timestep in which you wish know the energy.
        timestep : int, optional
            duration in minutes of a timestep within the simulation. Default is 5 minutes.

        Returns
        -------
        float
            energy provided by the array
        """
        self.energy_available = self.power[index] * (timestep / 60)
        return self.energy_available

    def get_results_data(self):
        data = {'Solar Model': self.model,
                'Solar Size (kW)': self.system_size}
        return data


class Battery(Component):  # Master class for EV and HES in which battery related functions/attributes are defined
    """
    This class represents objects which have a battery, namely the EV and HES. It inherits the Component class.
    Due to the nature of batteries, they can be either sources or sinks. The EV and HES classes inherit this class.

    Parameters
    ----------
    battery_size : float, int
        The size of the battery in terms of kWh.
    lvl2_max_rate : float, int
        The maximum rate of charge at lvl2 charging level. For use in charge time calculation (see charge_rate method)
    use_curve : bool, optional
        Boolean stating whether to use a specific battery charging curve or to use the simplified model curve.
        Default is FALSE, which tells the model to use the simplified model (see Notes).

    Attributes
    ----------
    soc : float or int
        current state-of-charge of the battery (ie 76%)
    socs : array_like
        array which tracks the state of charge at each timestep within the simulation. Starts as empty and must be
        initialized using initialize_socs method.
    prev_soc : float
        state of charge of the previous timestep. Updated with every charge/discharge event. Necessary for
        cost-of-use calculations.
    batterySize : float, int
        the size of the battery in kWh
    Lvl2MaxChargeRate : float
        The maximum rate of charge at lvl2 charging level. For use in charge time calculation (see charge_rate method)
    soc_max : float, int
        The maximum state of charge allowed. No charge events permissible beyond this limit. Hard set to 100% for now.
    soc_min : float, int
        The minimum state of charge allowed. No discharge permissible beyond this limit. Hard set to 20% for now.
    free_cap : float
        The free capacity of the battery in kWh. The difference between soc_max and soc_min times battery size (kwH).
    current_cap : float
        The current capacity of the battery in kWh. The difference between current soc and the soc_min times battery
        size (kwH).
    use_curve: bool
        Tells model to use battery specific charge curve (TRUE) or the simplified model curve (FALSE)
    sinkID : array_like
        1x2 numpy array containing sink indices corresponding to columns in 6x6 efficiency matrix. Set to [2,3].
    sourceID : array_like
        1x2 numpy array containing source indices corresponding to rows in 6x6 efficiency matrix. Set to [2,3].
    exists : bool
        Tells model whether this particular battery exists (non-zero battery size).
    next_deadline : int
        Timestep by which battery must be adequately charged to for its purpose (ie, driving for EV, HES peak shaving).
    step_to_start_charging : int
        Timestep at which battery must begin charging to meet its charging deadline (see time_to_charge method)
    used_as_sink : bool
        Tells the model that this battery was used as a sink in current timestep. Set to FALSE initially.
    used_as_source : bool
        Tells the model that the battery was used as a source. Set to FALSE initially.

    Notes
    -----
    -   No component can be used as a sink and source within the same timestep. As such used_as_sink and used_as_source
        are mutually exclusive and cannot be both TRUE at once.
    -   Functionality for battery model specific curves is in development. Until then use_curve will generally be
        FALSE for now.
    -   Unlike other classes, members of the EV class have 2 indices in the sinkID and sourceID attributed
        corresponding to lvl2 and DC fast charging rates of both charge and discharge. This model does not yet allow
        DCFC. HES is limited to one index for each (see HES).

    """

    def __init__(self, battery_size, lvl2_max_rate, use_curve=False, charging_scheme="default"):
        super().__init__()
        self.can_be_sink = True
        self.can_be_source = True
        self.must_be_sink = False
        self.must_be_source = False
        self.soc = 1.0
        self.socs = np.array([])
        self.prev_soc = 1  # this tracks soc before energy is added to assist with cost of use calculations
        self.batterySize = battery_size
        self.Lvl2MaxChargeRate = lvl2_max_rate
        self.soc_max = 1.0
        self.soc_min = .2
        self.free_cap = self.batterySize * (self.soc_max - self.soc_min)
        self.current_cap = 0
        self.use_curve = use_curve
        self.sinkID = np.array([2, 3])  # sink coordinate in efficiency array
        self.sourceID = np.array([2, 3])  # source coordinate in efficiency array
        self.exists = battery_size != 0
        self.next_deadline = 0
        self.step_to_start_charging = 0
        self.used_as_sink = False  # used as sink in particular timestep
        self.used_as_source = False  # used as source in particular timestep

        #ES: add charging_scheme to Battery class
        self.charging_scheme = charging_scheme
        self.trickle_charge_curve = 0

    def charge_rate(self, soc=None):
        """
        This method returns the charging rate in kW based on the state of charge provided. If one isn't provided
        then the method will use the current state of charge given by the soc class attribute.

        Parameters
        ----------
        soc : float, optional
            state of charge for which the charge rate is desired. Default is None, which tells the model to use the
            soc attribute.

        Returns
        -------
        float
            The charge rate in kW of the battery at the desired state of charge.

        Notes
        -----
        -   This method uses the use_curve attribute to determine whether to use a battery-specific curve
            or the simplified model charge curve. Battery specific curve functionality has yet to be added (12/28/23).
        -   This simplified curve uses the max lvl2 rate until 90% SoC and then
            drops to half for the remainder of the charge cycle.
        """
        if soc is None:
            soc = self.soc

        #ES: add charge_rate handling for trickle charge
        if self.charging_scheme == "trickle charge":
            charge_rate = self.trickle_charge_curve
            if soc > .9 and charge_rate > (self.Lvl2MaxChargeRate / 2):
                charge_rate = self.Lvl2MaxChargeRate / 2
            return charge_rate

        elif self.use_curve:
            return self.Lvl2MaxChargeRate

        else:
            if soc > .9:
                return self.Lvl2MaxChargeRate / 2
            else:
                return self.Lvl2MaxChargeRate

    def trickle_charge(self, num_timesteps, timestep=5, target_soc=1):
        """
        This method returns the necessary charge rate to trickle charge a Battery from its current level.

        Parameters
        ----------
        target_soc : float, optional
            Desired st for the battery to reach. Default is 100%.
        deadline : float, optional
            Duration of a timestep in minutes. Default is 5 minutes.

        Returns
        -------
        trickle_charge_rates : int
            Rate of charge for the battery to reach the target soc by the next deadline.

        Notes
        -----
        """
        soc = float(self.soc)
        time_to_charge = (num_timesteps * timestep) / 60
        if time_to_charge == 0:  # ductape solution for this being 0 at and of sim because deadline-step_to_charge=0
            time_to_charge = 12
        charge_through = ((target_soc - soc) * self.batterySize) / time_to_charge

        if charge_through > self.Lvl2MaxChargeRate:
            trickle_charge = self.Lvl2MaxChargeRate

        elif charge_through > (self.Lvl2MaxChargeRate / 2):
            time_to_trickle = time_to_charge - (0.1 * self.batterySize / (self.Lvl2MaxChargeRate / 2))
            trickle_charge = ((0.9 - soc) * self.batterySize) / time_to_trickle

        else:
            trickle_charge = charge_through
        #print(trickle_charge)
        return trickle_charge

    def time_to_charge(self, target_soc=1, timestep=5):
        """
        This method returns the time (in timesteps) to reach a desired state-of-charge (SoC) from its current level.

        Parameters
        ----------
        target_soc : float, optional
            Desired st for the battery to reach. Default is 100%.
        timestep : int, optional
            Duration of a timestep in minutes. Default is 5 minutes.

        Returns
        -------
        steps : int
            Number of timesteps of continuous charging necessary for battery to reach desired SoC.

        Notes
        -----
        The algorithm behind the method simulates a charge cycle, adding charge according to the prescribed charge
        curve and counting the number of steps it takes to reach the desired level.
        """

        steps = 0
        soc = self.soc
        while soc < target_soc:
            rate = self.charge_rate(soc)
            soc = min(1, soc + (rate * timestep / 60) / self.batterySize)
            steps += 1
        return steps

    def update_deadline(self, step: int):
        """
        This method changes the battery charging deadline attribute (next_deadline) to the one given.

        Parameters
        ----------
        step : int
            The timestep for the next deadline

        Returns
        -------
        None
        """
        self.next_deadline = step

    def update_charging_step(self, target_soc=1, timestep=5, next_off=0):
        """
        This method updates the step_to_start_charging attribute given a desired state-of-charge (SoC). This method
        also calls the charge_rate method for this calculation.

        Parameters
        ----------
        target_soc : float, optional
            Desired SoC to reach. Default is 100%
        timestep : int, optional
            Duration of a timestep in minutes. Default is 5 minutes.

        Returns
        -------
        None
        """
        if self.charging_scheme in ['frontend', 'trickle charge']:
            self.step_to_start_charging = max(next_off, 1)
        else:
            num_charging_steps = self.time_to_charge(target_soc=target_soc, timestep=timestep)
            self.step_to_start_charging = max((self.next_deadline - num_charging_steps), 1)

    def overwrite_soc(self, desired_soc):
        """
        This method overwrites the current objects state-of-charge (SoC) with a given value.

        Parameters
        ----------
        desired_soc : float, int
            The new SoC of the battery.

        Returns
        -------
        None
        """
        self.soc = max(float(min(self.soc_max, desired_soc)), self.soc_min)

    def was_used_as_sink(self):
        """
        This method sets the used_as_sink attribute to TRUE. Used when there is a charge event.

        Returns
        -------
        None
        """
        self.used_as_sink = True

    def was_used_as_source(self):
        """
        This method sets the used_as_source attribute to TRUE. Used when there is a discharge event to another
        component.

        Returns
        -------
        None
        """
        self.used_as_source = True

    def reset_sink_source(self):
        """
        This method resets the used_as_sink and used_as_source attributes to FALSE. Used at end of each timestep.

        Returns
        -------
        None
        """
        self.used_as_sink = False
        self.used_as_source = False

    def add_energy(self, energy):
        """
        This method adds energy to the Battery object and updates the soc and prev_soc attributes accordingly.

        Parameters
        ----------
        energy : float
            Energy (in kWh) added to the battery.

        Returns
        -------
        None
        """
        self.prev_soc = self.soc
        self.soc = min(self.soc_max, self.soc + energy / self.batterySize)

    def discharge_energy(self, energy):
        """
        This method discharges energy to the Battery object and updates the soc and prev_soc attributes accordingly.

        Parameters
        ----------
        energy : float
            Energy (in kWh) discharged from the battery.

        Returns
        -------
        None
        """
        self.prev_soc = self.soc
        self.soc = max(0.0, self.soc - energy / self.batterySize)
        self.current_cap = max(self.batterySize * (self.soc - self.soc_min), 0)

    def update_cost_of_use(self, cost_of_use_in: float, energy_received):
        """
        This method updates the cost_of_use attribute of the battery object, given an amount of energy received and
        its cost.

        Parameters
        ----------
        cost_of_use_in : float
            The cost_of_use of the component supplying energy to the battery.
        energy_received : float
            The amount of energy received by the battery.

        Returns
        -------
        None

        Notes
        -----
        -   The new cost of use of a battery is the weighted average of the current cost of use and the cost of use
        of the incoming energy.
        -   The weights for this calculation are the percents of the battery capacity each pool of energy (current
        energy and incoming) take up.
        """

        self.cost_of_use = (self.prev_soc * self.batterySize * self.cost_of_use + energy_received * cost_of_use_in) / (
                self.soc * self.batterySize)

    def record_cost_of_use(self, index):
        """
        This method records the value of the battery's cost_of_use attribute into the cost_of_uses attribute which
        tracks the cost of use for every timestep, given the corresponding index.

        Parameters
        ----------
        index: int
            index within cost_of_uses attribute where the current cost_of_use value is stored. Typically corresponds
            to the current timestep.

        Returns
        -------
        None
        """
        self.cost_of_uses[index] = self.cost_of_use

    def update_emissivity(self, emissivity_in: float, energy_received):
        """
        This method updates the emissivity attribute of the battery object, given an amount of energy received and
        its emissivity.

        Parameters
        ----------
        emissivity_in : float
            Emissivity (kg CO2/kWh) of the source of the incoming energy.
        energy_received : float
            Energy (kWh) received by the battery.

        Returns
        -------
        None

        Notes
        -----
        -   The new emissivity of a battery is the weighted average of the current emissivity and the emissivity
        of the incoming energy.
        -   The weights for this calculation are the percents of the battery capacity each pool of energy (current
        energy and incoming) take up.
        """

        self.emissivity = (self.prev_soc * self.batterySize * self.emissivity + energy_received * emissivity_in) / (
                self.soc * self.batterySize)

    def record_emissivity(self, index):
        """
        This method records the value of the battery's emissivity attribute into the emissivity_arr attribute which
        tracks the cost of use for every timestep, given the corresponding index.

        Parameters
        ----------
        index : int
            index within emissivity_arr attribute where the current emissivity value is to be stored. Typically
            corresponds to the current timestep.

        Returns
        -------
        None
        """
        self.emissivity_arr[index] = self.emissivity

    def initialize_socs(self, num_steps):
        """
        This method initializes the socs attribute into an N x 1 array where N is the number of timesteps in the
        simulation given by the num_steps parameter. It originally starts as an empty numpy array.

        Parameters
        ----------
        num_steps : int
            Number of steps in simulation

        Returns
        -------
        None
        """
        # ================================================================================================================
        # [T1-04] APPLIED -- 1-D state-of-charge array
        # LOCATION: Battery.initialize_socs
        # ----------------------------------------------------------------------------------------------------------------
        # NEW:  self.socs = np.zeros(num_steps)          # see T1-02
        # ================================================================================================================
        self.socs = np.zeros((num_steps, 1))

    def update_soc(self, index: int):
        """
        This method updates the socs array attribute with the current value of the soc attribute given the
        desired.
        Parameters
        ----------
        index : int
            index within socs attribute where the current soc value is to be stored. Typically
            corresponds to the current timestep.
        Returns
        -------
        None
        """
        self.socs[index] = self.soc


class EV(Battery):
    """
    This class represents and electric vehicle and inherits the Battery class, which itself inherits the Component
    class. This class has a variety of unique attributes and methods which correspond to typical EV functionality.

    Notes
    -----
    -   Instances of this class are stored into a Fleet object, which can hold any number of EVs for multi-EV analysis.
    -   EV model data is pulled from the 'EVs.csv' datafile by using the make, model, year, and trim of the vehicle.
    -   In this model an EV is capable of charging and vehicle-to-house (V2H) discharge for peak shaving purposes.
    -   V2H discharge events are converted to their equivalent in miles using the combined kWh/mi rating (see
        miles_driven simulated).
    Parameters
    ----------
    battery_size : float, int
        The size of the battery in terms of kWh.
    lvl2_max_rate : float, int
        The maximum rate of charge at lvl2 charging level. For use in charge time calculation (see charge_rate method)
    use_curve : bool, optional
        Boolean stating whether to use a specific battery charging curve or to use the simplified model curve.
        Default is FALSE, which tells the model to use the simplified model (see Battery class notes).
    ev_id : int
        The EV's unique identifier within a Fleet object. The first EV typically has an ev_id of 1.
    year : int
        The model year of the EV. Used for identifying the EV's row within the 'EVs.csv' datafile.
    make : str
        The brand of the EV (ie, Ford). Used for identifying the EV's row within the 'EVs.csv' datafile.
    model : str
        The model of the EV. Used for identifying the EV's row within the 'EVs.csv' datafile.
    trim : str
        The trim level of the EV (ie, GT, LX). Used for identifying the EV's row within the 'EVs.csv' datafile.
    msrp : str
        The msrp of the vehicle.
    mpge_hwy : float or int
        The EPA equivalent highway miles-per-gallon rating of the EV.
    mpge_city : float or int
        The EPA equivalent city miles-per-gallon rating of the EV.
    mpge_comb : float or int
        The EPA equivalent combined miles-per-gallon rating of the EV.
    driving_pattern : array_like
        An N x 2 numpy array representing the driving behavior of a given EV. First column describes the presence of
        the EV (1 if present, 0 if not). The second column describes the miles driven at a given timestep.
    discharge_limit : float
        The state of charge that the EV is allowed to discharge to before its V2H capability is disabled.

    Attributes
    ----------
    full_name : str
        The full description of the EV model. (ex, 2022 Ford F-150 Lightning Pro Lariat)
    make : str
        The EV make.
    model : str
        The EV model.
    trim : str
        The EV model year.
    type : str
        The kind of component. In this case its 'EV'.
    EViD : int
        The id number of the EV within its Fleet object.
    msrp : str
        The msrp of the EV.
    mpge_hwy : float or int
        The EPA equivalent highway miles-per-gallon rating of the EV.
    mpge_city : float or int
        The EPA equivalent city miles-per-gallon rating of the EV.
    mpge_comb : float or int
        The EPA equivalent combined miles-per-gallon rating of the EV.
    driving_pattern : array_like
        An N x 2 numpy array representing the driving behavior of a given EV. First column describes the presence of
        the EV (1 if present, 0 if not). The second column describes the miles driven at a given timestep.
    kwhpm_hwy : float
        The rated highway kWh/mi efficiency of the vehicle. Derived from mpge_hwy using a 33.7 kWh / gal gas conversion.
    kwhpm_city : float
        The rated city kWh/mi efficiency of the vehicle. Derived from mpge_comb using a 33.7 kWh / gal gas conversion.
    kwhpm_comb : float
        The rated kWh/mi efficiency of the vehicle. Derived from mpge_comb using a 33.7 kWh / gal gas conversion.
    miles_driven : float
        A counter for the actual road miles driven by the vehicle throughout the simulation.
    miles_driven_simulated : float
        A counter for the simulated miles on the EV battery from V2H discharge events during the simulation.
    cycles_driven : float
        A counter for the amount of cycles placed on the EV battery from regular driving.
    cycles_simulated : float
        A counter for the amount of cycles placed on the EV battery from V2H discharge.
    cost_of_driving : float
        A counter for the cost of driving the EV based on the costs of use at the time of each driving event.
    sinkID : array_like
        1x2 numpy array containing sink indices corresponding to columns in 6x6 efficiency matrix. Set to [2,3].
    sourceID : array_like
        1x2 numpy array containing source indices corresponding to rows in 6x6 efficiency matrix. Set to [2,3].
    sink_priority : int
        An integer representing the order by which sinks are prioritized to receive energy, with lower integers
        receiving energy first. Set to 1 for EV's, which are themselves ordered by level of battery depletion.
    next_dept : int
        The timestep at which the EV is to leave next. Discerned and updated from the driving_pattern attribute.
    next_arr : int
        The timestep at which the EV is to arrive next. Discerned and updated from the driving_pattern attribute.
    next_update : int
        The timestep at which the EV needs to be updated with respect to charging behavior. Usually arrival but can
        be the start of next off-peak depending on driving pattern
    discharge_limit : float
        The state of charge that the EV is allowed to discharge to before its V2H capability is disabled.
    """

    #ES: add charging scheme to EV class
    def __init__(self, battery_size: float, lvl2_max_rate: float, use_curve: bool, ev_id: int, year: int, make: str,
                 model: str, trim: str, msrp: str, mpge_hwy: float, mpge_city: float, mpge_comb: float,
                 driving_pattern: ndarray, discharge_limit: float, commute: str, charging_scheme: str):
        super().__init__(battery_size, lvl2_max_rate, use_curve, charging_scheme)
        self.name = 'EV'
        self.full_name = str(year) + ' ' + make + ' ' + model + ' ' + trim
        self.make = make
        self.model = model
        self.trim = trim
        self.year = year
        self.type = 'EV'
        self.EViD = ev_id
        self.msrp = msrp
        self.mpge_hwy = round(mpge_hwy, 4)
        self.mpge_city = round(mpge_city, 4)
        self.mpge_comb = round(mpge_comb, 4)
        self.driving_pattern = driving_pattern
        self.kwhpm_hwy = round(33.7 / self.mpge_hwy, 4)
        self.kwhpm_city = round(33.7 / self.mpge_city, 4)
        self.kwhpm_comb = round(33.7 / self.mpge_comb, 4)
        self.miles_driven = 0
        self.miles_driven_simulated = 0
        self.cycles_driven = 0
        self.cycles_simulated = 0
        self.cost_of_driving = 0
        self.sinkID = np.array([2, 3])  # sink coordinate in efficiency array
        self.sourceID = np.array([2, 3])  # source coordinate in efficiency array
        self.sink_priority = 1
        self.next_dept = 0
        self.next_arr = 0
        self.next_update = 1
        self.discharge_limit = discharge_limit
        self.commute = commute

    def reset(self, new_limit=None):
        """
        This method resets the EV for use in a subsequent simulation. It resets all counter and tracking array
        attributes to zero.

        Parameters
        ----------
        new_limit : float, optional
            The new discharge limit for the EV, if so desired. Default is None, meaning the EV retains the same limit.

        Returns
        -------
        None

        Notes
        -----
        -   When running multiple sims with the same EV and driving pattern, it is cumbersome to reload the same EV
        data repeatedly, so this method was made with the option to update the discharge limit.
        """
        self.emissivity = self.emissivity_arr[0]
        self.cost_of_use = self.cost_of_uses[0]
        self.socs.fill(0)
        self.cost_of_uses.fill(0)
        self.emissivity_arr.fill(0)
        self.miles_driven = 0
        self.miles_driven_simulated = 0
        self.cycles_driven = 0
        self.cycles_simulated = 0
        self.cost_of_driving = 0
        self.next_dept = 0
        self.next_arr = 0
        self.next_update = 1
        if new_limit is not None:
            self.discharge_limit = new_limit

    def is_here(self, index):  # returns boolean of whether EV is present
        """
        This method simply returns a bool of whether the EV is present (TRUE) or not (FALSE) at a given index
        corresponding to a timestep.

        Parameters
        ----------
        index : int
            index corresponding to the timestep at which the presence of the EV is to be ascertained.

        Returns
        -------
        None

        """
        return self.driving_pattern[index, 1] == 1 if index > 0 else False

    def get_id(self):
        """
        This method simply returns the value of the EViD attribute. Made for readability not simplicity.
        Returns
        -------
        None
        """
        return self.EViD

    def reset_id(self, new_id: int):
        """
        If desired, this method will overwrite the EViD attribute with a new value.
        Parameters
        ----------
        new_id : int
            The new value of the EViD attribute.

        Returns
        -------
        None
        """
        self.EViD = new_id

    @staticmethod
    def _next_index_where(arr: ndarray, start: int, value: float, initial_window: int = 2016) -> int:
        """
        This method returns the offset (relative to start) of the first occurrence of value in arr[start:],
        searching an expanding window instead of scanning the full remainder of the array in one shot.

        Notes
        -----
        -   Driving patterns are built from weekly-cyclical schedules, so the next departure/arrival is
            essentially never more than a handful of days away. Bounding the initial scan (default: 2016 steps,
            ie, 1 week at 5-min resolution) instead of searching from start to the end of the simulation avoids a
            full-array scan for every single arrival/departure lookup. If nothing turns up in the window (eg, an
            EV that never leaves home again), the window geometrically expands until it either finds a match or
            covers the rest of the array, mirroring the bounded search already used by Tariff.get_end_of_period.

        Parameters
        ----------
        arr : ndarray
            1D array to search (typically the presence column of driving_pattern).
        start : int
            index from which to begin searching.
        value : float
            value being searched for.
        initial_window : int, optional
            size of the first search window, in steps. Default is 2016 (1 week at 5-min resolution).

        Returns
        -------
        int
            offset from start of the first index at which arr equals value.

        Raises
        ------
        IndexError
            if value does not occur in arr[start:].
        """
        remaining = len(arr) - start
        window = initial_window
        while True:
            span = min(window, remaining)
            hits = np.where(arr[start:start + span] == value)[0]
            if hits.size > 0:
                return hits[0]
            if span >= remaining:
                raise IndexError
            window *= 4

    def next_departure(self, index, update=False):  # returns step of next EV departure
        """
        This method will return the timestep of next closest departure from the timestep corresponding to the index
        provided. Can either be the index for the current step or any arbitrary index, however the update parameter
        should be set to True if the next departure is desired for the current timestep to update the EV
        attributes.

        Parameters
        ----------
        index : int
            index of the timestep from which the next closest departure
        update : bool, optional
            Tells model to update the next_dept attribute with the returned value. Default is False.

        Returns
        -------
        int
            The timestep of the next departure from the index given. (Remember index = timestep - 1)
        """
        try:
            if self.is_here(index):
                dept = self._next_index_where(self.driving_pattern[:, 1], index, 0) + index - 1  # next departure
            else:
                arr = self._next_index_where(self.driving_pattern[:, 1], index, 1) + index  # next arrival
                dept = self._next_index_where(self.driving_pattern[:, 1], arr, 0) + arr  # next departure after arrival
        except IndexError:
            dept = len(self.driving_pattern)

        if update:
            self.next_dept = dept + 1

        return dept + 1  # (+1) to covert to step

    def next_arrival(self, index, update=False):  # returns index of next EV arrival
        """
        This method will return the timestep of next closest arrival from the timestep corresponding to the index
        provided. Can either be the index for the current step or any arbitrary index, however the update parameter
        should be set to True if the next arrival is desired for the current timestep to update the EV
        attributes.
        Parameters
        ----------
        index : int
            index of the timestep from which the next closest departure
        update : bool, optional
            Tells model to update the next_dept attribute with the returned value. Default is False.

        Returns
        -------
        int
            The timestep of the next arrival from the index given. (Remember index = timestep - 1)
        """
        if not self.is_here(index):
            arr = self._next_index_where(self.driving_pattern[:, 1], index, 1) + index  # next arrival
        else:
            dept = self._next_index_where(self.driving_pattern[:, 1], index, 0) + index  # next departure
            arr = self._next_index_where(self.driving_pattern[:, 1], dept, 1) + dept  # next arrival

        arr = arr + 1  # convert from index to step
        if update:
            self.next_arr = arr

        return arr

    def discharge_energy(self, energy):
        """
        This method discharged the EV battery by the amount given (in kWh) and updates the soc, cycles_simulated,
        and miles_driven_simulated attributes. This method supersedes the Battery class method of the same name.
        Parameters
        ----------
        energy : float
            Energy (in kWh) discharged from the battery.

        Returns
        -------
        None
        """
        self.prev_soc = self.soc
        self.soc = max(0, self.soc - energy / self.batterySize)
        self.cycles_simulated += energy / self.batterySize
        self.miles_driven_simulated += energy / self.kwhpm_comb

    def drive_miles(self, miles, percent_hwy=.55):
        """
        This emulates a driving event for the EV and discharges the battery according to its efficiency and the miles
        driven. An optional parameter is percent_hwy which tells what percent of miles are highway miles.

        Parameters
        ----------
        miles : float
            The amount of miles driven by the EV for the current trip.
        percent_hwy : float, optional
            The percentage of miles driven on the highway. Default is 55% (from Bureau of Transportation)

        Returns
        -------
        None
        """
        percent_city = 1 - percent_hwy
        kwh_depleted = miles * (percent_city * self.kwhpm_city + percent_hwy * self.kwhpm_hwy)
        self.miles_driven += miles
        self.cycles_driven += kwh_depleted / self.batterySize
        self.soc -= kwh_depleted / self.batterySize
        self.soc = np.round(max(self.soc, 0), 4)
        self.prev_soc = self.soc
        self.cost_of_driving += kwh_depleted * self.cost_of_use

    def get_results_data(self):
        data = {'Costs of Use': self.cost_of_uses,
                'Emissivity': self.emissivity_arr,
                'SoC': self.socs}
        return data


class HES(Battery):  # Object representing Home Battery system
    """
    This class represents a home energy system (HES) installed in the household. It inherits the Battery class,
    which itself inherits the Components class. It has unique attributes and methods related to the function of an HES.

    Parameters
    ----------
    battery_size : float, int
        The size of the battery in terms of kWh.
    lvl2_max_rate : float, int
        The maximum rate of charge at lvl2 charging level. For use in charge time calculation (see charge_rate method)
    use_curve : bool, optional
        Boolean stating whether to use a specific battery charging curve or to use the simplified model curve.
        Default is FALSE, which tells the model to use the simplified model (see Battery class notes).
    max_discharge : float, int
        The maximum rate of discharge for the HES in kW.

    Attributes
    ----------
    name : str
        name of the component (in this case 'HES')
    type : str
        type of component (in this case 'HES'). Redundant with name, and TBD which will be removed.
    max_discharge : float, int
        The maximum rate of discharge for the HES in kW.
    sinkID : array_like
        1x1 numpy array containing sink indices corresponding to columns in 6x6 efficiency matrix. Set to [1].
    sourceID : array_like
        1x1 numpy array containing source indices corresponding to rows in 6x6 efficiency matrix. Set to [1].
    sink_priority : int
        An integer representing the order by which sinks are prioritized to receive energy, with lower integers
        receiving energy first. Set to 1 for EV's, which are themselves ordered by level of battery depletion.
    coverage_steps : array_like
        A numpy array of timesteps for which the HES is allowed to discharge to the home for peak shaving purposes.
        It is updated every off-peak period in preparation for peak and mid-peak periods.
    soc_to_reach : float
        the target state-of-charge (SoC) the HES will try to reach to cover the peak periods for peak shaving.
    step_to_start_charging : float
        The timestep at which the HES will begin charging to reach the target SoC (see soc_to_reach).
    soc_targets : ndarray
        A array recording the states of charge that the HES charges to for peak shaving purposes.
    Notes
    -----
    -   The HES has the functionality of peak shaving, charging up during the off-peak and discharging during peak
        periods of electricity pricing.
    -   It is disadvantageous to fully charge the HES if it is not necessary to cover the whole peak period because
        it removes capacity for excess solar production. We therefore seek to optimize the HES charging cycle to cover
        only what is needed.
    """

    def __init__(self, battery_size, lvl2_max_rate, use_curve, max_discharge):
        super().__init__(battery_size, lvl2_max_rate, use_curve)
        self.name = 'HES'
        self.type = 'HES'
        self.max_discharge = max_discharge  # maximum discharge rate of HES (kW)
        self.sinkID = np.array([1])  # sink coordinate in efficiency array
        self.sourceID = np.array([1])  # source coordinate in efficiency array
        self.sink_priority = 2  # priority of when HES gets charged (behind house and ev)
        # ================================================================================================================
        # [T1-11] APPLIED -- Boolean coverage mask beside coverage_steps
        # LOCATION: HES.__init__ / update_coverage_steps
        # ----------------------------------------------------------------------------------------------------------------
        # WHY:  the simulation loop tested "if timekeep.step in hes.coverage_steps" once per timestep.
        #       "in" on an ndarray is a full linear scan: measured 1.5 us. A boolean mask lookup is 0.037 us.
        #       That is a 40x difference, 105,120 times per scenario.
        # NEW:  self.coverage_mask = np.zeros(0, dtype=bool)   plus a new initialize_coverage_mask(num_steps)
        #       called from run_simulation, and update_coverage_steps() now refreshes the mask alongside
        #       coverage_steps. Call site becomes:  if hes.coverage_mask[step - 1]:
        # IMPACT: ~6% of total scenario runtime.
        # ================================================================================================================
        self.coverage_steps = np.array([])  # timesteps for which HES is allowed to discharge
        self.soc_to_reach = 1
        self.step_to_start_charging = 0
        self.opt_count = 0  # number of times the HES has been optimized (target_soc updated)
        self.soc_targets = np.zeros((1, 365))  # We assume 1 optimization per day, adds more if needed.

    def update_coverage_steps(self, steps):
        """
        This method updates the coverage_steps attribute provided a numpy array of timesteps to cover.

        Parameters
        ----------
        steps : array_like
            Numpy array containing the timesteps which the HES is allowed to discharge (typically peak and midpeak
            periods).

        Returns
        -------
        None
        """
        self.coverage_steps = steps

    def update_soc_to_reach(self, target_soc):
        """
        This method updates the soc_to_reach attribute with the value provided. And records it into the target_socs
        attribute. The target_socs array is pre-allocated, so we add more zeros to end as needed, with extra zeros
        being trimmed at end of simulation when Results object is being created (see Results in Simulation.py).

        Parameters
        ----------
        target_soc : float
            A desired state-of-charge (SoC) for the HES battery to reach to cover an upcoming peak/mid-peak period.

        Returns
        -------
        None
        """
        # ================================================================================================================
        # [T3-06] PROPOSED -- soc_targets is the wrong shape -- HES Avg SoC Target is wrong everywhere
        # LOCATION: HES.update_soc_to_reach / trim_soc_targets
        # ----------------------------------------------------------------------------------------------------------------
        # soc_targets is allocated as np.zeros((1, 365)) -- a 2-D array with ONE row.
        # 
        #   * soc_targets[0] = value assigns the value to ALL 365 entries of row 0.
        #   * soc_targets[1] on the next call raises IndexError; the except widens the array by 30 columns
        #     and THE VALUE IS NEVER STORED. Every optimisation after the first only grows the array.
        #   * trim_soc_targets tests len(self.soc_targets) > self.opt_count, but len() of a (1, N) array is
        #     1, so the trim never happens.
        # 
        # After a year (~730 optimisations) the array is 1 x ~22,000 with only the first 365 slots filled,
        # all holding the first target. Results.avg_soc_target then reports
        #     365 * first_target / 22000
        # which is why the "HES Avg SoC Target" column reads ~3% when the flat scheme targets 80%.
        # 
        # FIX: make soc_targets a 1-D array (or a plain list) appended to correctly, and fix the trim test.
        # CONSEQUENCE: this changes a reported metric, so every existing summary CSV has a wrong value in
        #   that column. Re-running recalc_summary_file will not repair it -- the value is derived from the
        #   live HES object, so affected scenarios need re-simulating if that column matters to you.
        # ================================================================================================================
        self.soc_to_reach = min(1.0, target_soc)
        try:
            self.soc_targets[self.opt_count] = self.soc_to_reach
        except IndexError:
            # We append an extra chunk of zeros to end if necessary. Extra zeros will be removed at end of simulation.
            self.soc_targets = np.hstack((self.soc_targets, np.zeros((1, 30))))
        self.opt_count += 1

    def trim_soc_targets(self):
        """
        This method simply trims the target_socs array attribute of its extra zeros based on the opt_count attribute
        such that the final array is 1 x opt_count.

        Returns
        -------
        None
        """
        if len(self.soc_targets) > self.opt_count:
            self.soc_targets = self.soc_targets[0:self.opt_count]

    def reset(self):
        """
        This method resets the HES object for use in subsequent simulations using the same HES. Tracking array
        attributes for state-of-charge, cost-of-use, and emissivity are reset to 0.

        Returns
        -------
        None
        """
        if self.exists:
            # ================================================================================================================
            # [T1-12] APPLIED -- Reset the coverage mask between scenarios
            # LOCATION: HES.reset
            # ----------------------------------------------------------------------------------------------------------------
            # WHY:  reset() is what makes component reuse across scenarios safe. The new mask has to be cleared
            #       here too or a stale coverage window leaks into the next scenario.
            # NEW:  float() casts on the two scalars, plus
            #       self.coverage_steps = np.array([]) ; self.coverage_mask.fill(False)
            # ================================================================================================================
            self.emissivity = self.emissivity_arr[0]
            self.cost_of_use = self.cost_of_uses[0]
            self.socs.fill(0)
            self.cost_of_uses.fill(0)
            self.emissivity_arr.fill(0)

    def get_results_data(self):
        data = {'Battery Size (kWh)': self.batterySize}
        return data


class ICE:  # This represents an internal combustion car for comparison with the EV
    """This class represents an internal combustion engine vehicle and is used for comparisons to an EV for gas and
    CO2 savings purposes.

    Parameters
    ----------
    make : str, optional
        The brand of the EV (ie, Ford). Used for identifying the vehicle's row within the 'processed_ice.csv'
        datafile. Default is 'Generic'.
    model : str , optional
        The model of the EV. Used for identifying the vehicle's row within the 'processed_ice.csv' datafile. Default
        is 'Generic'.
    year : int, optional
        The model year of the EV. Used for identifying the vehicle's row within the 'processed_ice.csv' datafile.
        Default is 2023.
    mpg : float, optional
        The combined miles per gallon efficiency of the vehicle. Default is 25.4 mpg.
    drive : str, optional
        The drive train of the vehicle (2WD or 4WD). Default is '2WD'.
    displacement : float, optional
        The volume displacement of the vehicle's engine (in L). Default is 3L.
    transmission : float, optional
        The transmission type of the vehicle (automatic or manual). Default is 'Automatic'.
    emissivity : float, optional
        The kgCO2/mi emitted by the vehicle. Default is None, deriving its value from the mpg attribute.

    Attributes
    ----------
    full_name : str
        The full designation of the vehicle (Ex, 2014 Ford Focus)
    make : str
        Make of the vehicle.
    model : str
        Model of the vehicle.
    year : int
        Model year of the vehicle.
    mpg : float
        Combined miles-per-gallon efficiency of vehicle.
    drive : str
        Drive-type of vehicle.
    displacement : float
        Volume of engine (L).
    transmission : str
        Transmission type of vehicle.
    emissivity : float
        The gCO2/mi emission rate of the vehicle. Can be user defined by emissivity parameter or calculated using
        mpg and an emissivity factor for gasoline (8780 g CO2 per gallon)

    """

    def __init__(self, make='Generic', model='Generic', year=2023, mpg=25.4, drive='2WD', displacement=3,
                 transmission='Automatic', emissivity=None):
        self.full_name = str(year) + ' ' + make + ' ' + model
        self.make = make
        self.model = model
        self.year = year
        self.mpg = mpg
        self.drive = drive
        self.displacement = displacement
        self.transmission = transmission
        if emissivity is not None:
            self.emissivity = emissivity
        else:
            self.emissivity = 8780 / self.mpg

    def cost_per_mile(self, gas_cost):
        """
        This method returns the cost per mile to drive the ICE vehicle given a gasoline cost per gallon.

        Parameters
        ----------
        gas_cost : float
            Cost of gasoline ($/gal)

        Returns
        -------
        float
            cost per mile of driving the ICE ($/mi).
        """
        return gas_cost / self.mpg

    def get_cost_of_driving(self, miles_driven=0.0, gas_cost=3.50):
        """
        This method returns the cost of driving the ICE a given amount of miles at a given gas cost. Utilizes the
        cost_per_mile method.

        Parameters
        ----------
        miles_driven: float, optional
            The amount of miles driven by the ICE vehicle in the period of interest. Defaults to 0.
        gas_cost : float
            Cost of gasoline ($/gal). Default is $3.50/gal.

        Returns
        -------
        cod : float
            Total gasoline cost of driving the ICE vehicle.
        """
        cod = self.cost_per_mile(gas_cost=gas_cost) * miles_driven
        return cod


class Fleet:  # Object representing a fleet of EVs
    """
    This class represents a Fleet of EV's, enabling the model to have multi-EV functionality. It shares many methods
    with the EV class, whereby it applies these method to every EV within the fleet. It also has attributes and
    methods which emulate fleet functionality.

    Parameters
    ----------
    ev_list : array_like of EV
        A list of EV objects. Can contain any number of EVs.

    Attributes
    ----------
    ev_list : array_like of EV
        A composite list of EV's in the fleet.
    ev_num : int
        Number of EVs in the fleet, determined from length of ev_list
    """

    def __init__(self, ev_list: list):
        self.ev_list = ev_list
        self.ev_num = len(ev_list)
        # ================================================================================================================
        # [T1-13] APPLIED -- Cache fleet emptiness as an attribute
        # LOCATION: Fleet.__init__ and mutators
        # ----------------------------------------------------------------------------------------------------------------
        # WHY:  no_evs() was called 1,051,214 times in a 6-scenario run (about 5x per timestep) to answer a
        #       question that only changes when fleet membership changes.
        # NEW:  self.has_evs = self.ev_num > 0, kept in sync by add_ev / remove_ev / clear_fleet, and
        #       no_evs() now returns "not self.has_evs". All hot call sites use fleet.has_evs directly.
        # BUG FIXED IN PASSING: clear_fleet() emptied ev_list but left ev_num stale, so no_evs() kept
        #       reporting a non-empty fleet after clearing. clear_fleet() now zeroes both.
        # ================================================================================================================
        self.V2H_enabled = self.check_v2h()

    def reset_ids(self):
        """
        This method resets the EViD attributes of all the EVs in the Fleet. The first EV in the list will have an id
        of 1 and so on.

        Returns
        -------
        None
        """
        i = 1
        for ev in self.ev_list:
            ev.reset_id(new_id=i)
            i += 1

    def check_v2h(self):
        """
        This method checks if V2H is allowed for any EVs in the Fleet based off of their discharge limits.
        Returns
        -------
        v2h: bool
            False if all one of the EVs has a discharge limit of 100%. True if at least one has a discharge limit
            less than 100%.
        """
        v2h = False
        for ev in self.ev_list:
            v2h = True if (ev.discharge_limit < 1) else v2h
        return v2h

    def initialize_cost_of_use(self, tou_cost, efficiency, cost_of_use_track, num_steps):
        """
        This method calls the initialize_cost_of_use method for each of the EVs in the fleet, and uses the same
        parameters.

        Parameters
        ----------
        tou_cost : float
            the cost of electricity from the grid at the start of the simulation
        efficiency : float
            efficiency of energy transfer FROM grid to component (100% if component is grid itself)
        cost_of_use_track : bool, optional
            boolean which tells model to track costs of use for each timestep. Default is TRUE.
        num_steps : int, optional
            number of timesteps in simulation. Default is 105120, which is 5-min steps for a calendar year

        Returns
        -------
        None
        """
        for i in range(self.ev_num):
            self.ev_list[i].initialize_cost_of_use(tou_cost, efficiency, cost_of_use_track, num_steps)

    def initialize_emissivity(self, grid_intensity, efficiency, num_steps):
        """
        This method calls the initialize_emissivity method for the EV's in the fleet, and uses the same parameters.

        Parameters
        ----------
        grid_intensity : float
            the emissivity (kg CO2/kWh) of the grid at the start of the simulation.
        efficiency : float
            efficiency of energy transfer FROM grid to component (100% if component is grid itself).
        num_steps : int, optional
            number of timesteps in simulation. Default is 105120, which is 5-min steps for a calendar year.

        Returns
        -------
        None
        """
        for i in range(self.ev_num):
            self.ev_list[i].initialize_emissivity(grid_intensity, efficiency, num_steps)

    def initialize_socs(self, num_steps):
        """
        This method calls the initialize_socs method for the EV's in the fleet, and uses the same parameter.
        Parameters
        ----------
        num_steps : int
            Number of steps in simulation

        Returns
        -------
        None
        """
        for i in range(self.ev_num):
            self.ev_list[i].initialize_socs(num_steps=num_steps)

    def add_ev(self, ev: EV):
        """
        This method adds a new EV object to the Fleet and resets the EViD attributes of each EV using the reset_id
        method.

        Parameters
        ----------
        ev : EV
            An EV object to add to the fleet.

        Returns
        -------
        None
        """
        self.ev_list.append(ev)
        self.reset_ids()
        self.ev_num += 1

    def remove_ev(self, index: int):
        """
        This method removes an EV object to the Fleet given the index of the EV to be removed and resets the EViD
        attributes of each EV using the reset_id method.

        Parameters
        ----------
        index : int
            index of EV in list to be removed.

        Returns
        -------
        None
        """
        # remove ev by index in list
        self.ev_list.pop(index)
        self.reset_ids()
        self.ev_num -= 1

    def clear_fleet(self):
        """
        This method removes all EV's from the fleet.

        Returns
        -------
        None
        """
        self.ev_list = []

    def evs_present(self, index):
        """
        This method returns a list of EVs from the fleet object which are present at the timestep corresponding to the
        index given.

        Parameters
        ----------
        index:
            index of the timestep in question.

        Returns
        -------
        sub_fleet : list
            A list of EV objects present at the timestep corresponding to the index given.
        """

        sub_fleet = []
        for ev in self.ev_list:
            if ev.is_here(index):
                sub_fleet.append(ev.get_id)

        return sub_fleet

    def get_ev(self, ev_id):
        """
        This method returns the EV object with the given EViD from the Fleet object.

        Parameters
        ----------
        ev_id : int
            EViD of the EV desired from the Fleet.

        Returns
        -------
        EV:
            EV with given EViD from Fleet.
        """
        return self.ev_list[ev_id - 1]

    def make_subfleet(self, id_list):  # create a sub-fleet out of the main fleet given EV id numbers.
        """
        This method creates an entirely new Fleet object given a list of EViDs of EVs from the original Fleet object.

        Parameters
        ----------
        id_list : list
            A list of EViD numbers of the EVs desired from the current Fleet object.

        Returns
        -------
        subfleet : Fleet
            A fleet containing some or all of the EVs from the original Fleet object.
        """
        sub_list = []
        for ev in self.ev_list:
            ev_id = ev.get_id()
            if ev_id in id_list:
                sub_list.append(ev)

        sub_fleet = Fleet(sub_list)
        return sub_fleet

    def combine(self, subfleet):  # recombine subfleet with main fleet (overwriting EV data in main fleet)
        """
        This method recombines a Fleet object which is a subfleet of another Fleet together with that Fleet. EVs in
        the original Fleet are overwritten with data of EV's in subfleet with same EViD.

        Parameters
        ----------
        subfleet: Fleet
            A smaller fleet derived from a larger Fleet which is to be recombined with that fleet.

        Returns
        -------
        None
        """
        for sev in subfleet.ev_list:
            ev_id = sev.get_id()
            for i in range(self.ev_num):
                if self.ev_list[i].get_id == ev_id:
                    self.ev_list[i] = sev

    def fleet_cost(self):
        """
        This method returns the total MSRP of the vehicles in the fleet.
        Returns
        -------
        msrp : float
            The total msrps of all the EVs in the Fleet
        """
        msrp = 0
        if not self.no_evs():
            for ev in self.ev_list:
                msrp += int(float(ev.msrp.replace(',', '')[1:]))
        return msrp

    def fleet_sim_miles(self):
        """
        This method returns the cumulative total number of simulated V2H miles from every EV in the fleet.
        Returns
        -------
        sim_miles : float
            The number of simulated V2H miles of the fleet.
        """
        sim_miles = 0
        if not self.no_evs():
            for ev in self.ev_list:
                sim_miles += ev.miles_driven_simulated
        return sim_miles

    def fleet_driven_miles(self):
        """
        This method returns the cumulative total number of actual driven miles from every EV in the fleet.
        Returns
        -------
        drive_miles: float
            The total number of actual driven miles of the fleet.
        """
        drive_miles = 0
        if not self.no_evs():
            for ev in self.ev_list:
                drive_miles += ev.miles_driven
        return drive_miles

    def no_evs(self):
        """
        This method simply returns if the fleet is empty. Made for readability purposes.

        Returns
        -------
        bool
            Whether there are any EVs (TRUE) or not (FALSE) inside the Fleet
        """
        return self.ev_num == 0

    def add_energy(self, ev_id: int, energy):
        """
        This method calls the add_energy for a specific EV within the fleet given the EViD and the energy added.

        Parameters
        ----------
        ev_id : int
            EViD value of the EV to which energy is to be added.
        energy : float
            Amount of energy (kWh) to be added.

        Returns
        -------
        None
        """
        self.ev_list[ev_id - 1].add_energy(energy=energy)

    def discharge_energy(self, ev_id: int, energy):
        """
        This method calls the discharge_energy for a specific EV within the fleet given the EViD and the energy
        discharged.

        Parameters
        ----------
        ev_id : int
            EViD value of the EV from which energy is to be discharged.
        energy : float
            Amount of energy (kWh) to be discharged.

        Returns
        -------
        None
        """
        self.ev_list[ev_id - 1].discharge_energy(energy=energy)

    def update_cost_of_use(self, ev_id: int, cost_of_use_in: float, energy_received):
        """
        This method calls the update_cost_use method for a specific EV within the fleet given the EViD,
        energy received, and the cost-of-use of that energy.

        Parameters
        ----------
        ev_id : int
            EViD value of the EV whose cost_of_use attribute is being updated.
        cost_of_use_in : float
            cost-of-use of the energy received ($/kWh).
        energy_received : float
            Energy received by the EV (kWH).

        Returns
        -------

        """
        self.ev_list[ev_id - 1].update_cost_of_use(cost_of_use_in=cost_of_use_in, energy_received=energy_received)

    def record_cost_of_use(self, ev_id: int, index: int):
        """
        This method calls the record_cost_of_use method for a specific EV within the fleet, given the EViD and the
        index within its cost_of_uses attribute (array) to save said value (typically index of current timestep).

        Parameters
        ----------
        ev_id : int
            EViD value of the EV whose cost_of_use attribute is being updated.
        index : int
            Index value of element in cost_of_uses attribute to be updated with the cost_of_use value.
        Returns
        -------
        None
        """
        self.ev_list[ev_id - 1].record_cost_of_use(index)

    def update_emissivity(self, ev_id: int, emissivity_in: float, energy_received):
        """
        This method calls the update_emissivity method for a specific EV within the fleet given the EViD,
        energy received, and the emissivity of that energy.

        Parameters
        ----------
        ev_id : int
            EViD value of the EV whose emissivity attribute is being updated.
        emissivity_in : float
            emissivity of the energy received (kg CO2/kWh)
        energy_received : float
            Energy received by the EV (kWH).

        Returns
        -------

        """
        self.ev_list[ev_id - 1].update_emissivity(emissivity_in=emissivity_in, energy_received=energy_received)

    def was_used_as_source(self, ev_id: int):
        """
        This method calls the was_used_as_source method for a specific EV within the fleet given the EViD.

        Parameters
        ----------
        ev_id : int
            EViD value of the EV in question.

        Returns
        -------
        None
        """
        self.ev_list[ev_id - 1].was_used_as_source()

    def was_used_as_sink(self, ev_id: int):
        """
        This method calls the was_used_as_sink method for a specific EV within the fleet given the EViD.

        Parameters
        ----------
        ev_id : int
            EViD value of the EV in question.

        Returns
        -------
        None
        """
        self.ev_list[ev_id - 1].was_used_as_sink()

    def reset_sink_source(self):
        """
        This method calls the reset_sink_source method for all EV's in the fleet.

        Returns
        -------
        None
        """
        for ev in self.ev_list:
            ev.reset_sink_source()

    def get_ev_names(self):
        """
        This method returns a string of all the EV full names in the fleet, starting with the first EV.

        Returns
        -------
        full_ev_string : str
            String containing full names of all EVs in fleet, separated by commas.
        """
        full_ev_string = ''
        if not self.no_evs():
            for ev in self.ev_list:
                ev_string = ' '.join([str(ev.year), ev.make, ev.model, ev.trim])
                full_ev_string = full_ev_string + ev_string + ', '
            full_ev_string = full_ev_string[0:-2]
        return full_ev_string

    def get_ev_list(self):
        """
        This method returns a LIST of all EV full names in the fleet, starting with the first EV.

        Returns
        -------
        list
            A list containing full names of each EV in fleet. Each element is an EV's full name starting with first EV.
        """
        return [ev.full_name for ev in self.ev_list]

    def reset_evs(self, new_limit=None):
        """
        This method calls the reset method for every EV in the Fleet, for use in subsequent simulations such that
        new Fleet and EV objects does not neet to be created.

        Parameters
        ----------
        new_limit : bool, optional
            A new discharge limit for EVs in the fleet. Default is None, meaning the discharge limit stays the same.

        Returns
        -------
        None
        """
        for ev in self.ev_list:
            ev.reset(new_limit=new_limit)

    def get_results_data(self):
        # ev_data_list = [ev.get_results_data() for ev in self.ev_list]

        fleet_data = {'Fleet Cost ($)': np.round(self.fleet_cost(), 2),
                      'EV List': self.get_ev_list(),
                      'Fleet Sim Miles (mi)': np.round(self.fleet_sim_miles(), 2),
                      'Fleet Driven Miles (mi)': np.round(self.fleet_driven_miles(), 2)}
        return fleet_data


class Energy:
    """
    This class was created as a calculator and container for all the energy flows between the components. As such its
    attributes consist mainly of numpy arrays for each of the possible component sink-source combinations.

    Parameters
    ----------
    op : pm.Operation
        An Operation object from the Parameters.py file. It contains the energy transfer efficiencies array.
    tk : pm.Timekeep
        A Timekeep object from the Parameters.py file. It contains the number of simulation steps which the Energy
        class needs to size its arrays.
    fleet : Fleet
        A fleet object containing the EVs (if any) for the simulation.
    hes : HES
        An HES object used in the simulation.

    Attributes
    ----------
    efficiencies : ndarray
        A 6x6 numpy array for efficiency of energy transfers between components. The row indices corresponds to a
        source and thew column indices refer to sinks. For example an element with indices [0, 5] has the efficiency
        for a PV to house energy transfer (See efficiencies.csv).
    ev_out : ndarray
        An N x C array tracking energy leaving each EV, where N is the number of timesteps and C is the number of
        EVs in the fleet. Left empty if the Fleet is empty.
    ev_in : ndarray
        An N x C array tracking all energy entering the EVs, where N is the number of timesteps and C is the number
        of EVs in the fleet. Left empty if the Fleet is empty.
    ev_to_house : ndarray
        An N x C array tracking the V2H energy transfers for each EV to the household, where N is the number of
        timesteps and C is the number of EVs in the fleet. Left empty if the Fleet is empty.
    ev_to_grid : ndarray
        An N x C array tracking the V2G energy transfers for each EV, where N is the number of timesteps and C is the
        number of EVs in the fleet. Left empty if the Fleet is empty. V2G functionality is not available in current
        model.
    ev_out_total : ndarray
        An N x 1 array tracking the total energy leaving ALL the EVs, where N is the number of timesteps. Left empty if
        the Fleet is empty.
    ev_in_total : ndarray
        An N x 1 array tracking the total energy going into ALL EVs, where N is the number of timesteps in the
        simulation.
    grid_out : ndarray
        An N x 1 array tracking the total energy coming from the grid to all other components, where N is the number of
        timesteps in the simulation.
    grid_in : ndarray
        An N x 1 array tracking the total energy going back into the grid to all other components, where N is the
        number of timesteps in the simulation. Ex, V2G and net-metering.
    grid_to_house : ndarray
        An N x 1 array tracking the energy coming from the grid to the house, where N is the number of timesteps in
        the simulation.
    grid_to_ev : ndarray
        An N x C array tracking the energy coming from the grid into each of the EVs in the Fleet, where C represents
        the number of EVs in the fleet. Each EV gets their own column, matching their EViD.
    grid_to_hes : ndarray
        An N x 1 array tracking the energy coming from the grid into the HES, where N is the number of timesteps in
        the simulation.
    grid_to_fleet : ndarray
        An N x 1 array tracking the TOTAL energy coming from the grid into all the EVs in the Fleet, where N is the
        number of timesteps in the simulation.
    pv_out : ndarray
        An N x 1 array tracking the total energy coming from the PV to all other components, where N is the number of
        timesteps in the simulation.
    pv_to_house : ndarray
        An N x 1 array tracking the energy coming from the PV into the house, where N is the number of timesteps in
        the simulation.
    pv_to_hes : ndarray
        An N x 1 array tracking the energy coming from the grid into the HES, where N is the number of timesteps in
        the simulation.
    pv_to_ev : ndarray
        An N x C array tracking the energy coming from the PV into each of the EVs in the Fleet, where C represents
        the number of EVs in the fleet. Each EV gets their own column, matching their EViD.
    pv_to_grid : ndarray
        An N x 1 array tracking the energy coming from the PV into the grid, where N is the number of timesteps in
        the simulation. This is meant to track net-metering and solar buy-back.
    pv_to_fleet : ndarray
        An N x 1 array tracking the TOTAL energy coming from the PV into all the EVs in the Fleet, where N is the
        number of timesteps in the simulation.
    hes_in : ndarray
        An N x 1 array tracking the total energy going into the HES from other components, where N is the number of
        timesteps in the simulation. Ex, V2G and net-metering.
    hes_out : ndarray
        An N x 1 array tracking the total energy going from the HES into other components, where N is the number of
        timesteps in the simulation. Ex, V2G and net-metering.
    hes_to_house : ndarray
        An N x 1 array tracking the energy coming from the HES into the house, where N is the number of timesteps in
        the simulation.
    hes_to_grid : ndarray
        A N x 1 array tracking the energy coming from the HES back into the grid, where N is the number of timesteps
        in the simulation. This functionality is currently not enabled, so this array will be only zeros.
    hes_to_ev : ndarray
        An N x C array tracking the energy coming from the HES into each of the EVs in the Fleet, where C represents
        the number of EVs in the fleet. Each EV gets their own column, matching their EViD.
    hes_to_fleet : ndarray
        An N x 1 array tracking the TOTAL energy coming from the HES into all the EVs in the Fleet, where N is the
        number of timesteps in the simulation.
    house_in : ndarray
        An N x 1 array tracking the total energy going into the house from other components, where N is the number of
        timesteps in the simulation.
    loss : ndarray
        A N x 1 array tracking the total energy lost during energy transfers in the system, since the transfers are
        not 100% efficient. N is the total number of timesteps in the simulation.
    cost_of_loss : ndarray
        A N x 1 array tracking the monetary loss of value (cost) due to energy loss, where N is the number of
        timesteps in the simulation.
    loss_emissions : ndarray
        A N x 1 array tracking the induced emissions (kg CO2) due to inefficiencies in the system.
    updated : bool
        A boolean variable which states if the components have been updated or not. (Might be removed)

    Notes
    -----
    -   All outward energy flows (comp_to_comp or comp_out) are from the perspective of the source,
        with no efficiency applied.
    """

    def __init__(self, op: Operation, tk: TimeKeep, fleet: Fleet, hes: HES):
        # ================================================================================================================
        # [T1-14] APPLIED -- Energy trackers to 1-D + nested-list efficiency mirror
        # LOCATION: Energy.__init__
        # ----------------------------------------------------------------------------------------------------------------
        # WHY:  ~25 arrays of 105,120 float64 (about 21 MB per live simulation), all allocated as column
        #       vectors and all written inside the timestep loop. See T1-02 for the measurement.
        # NEW:  arr_size = tk.num_steps ; hes_size = (hes.batterySize != 0) * tk.num_steps
        #       grid_to_fleet / pv_to_fleet / hes_to_fleet become np.zeros(ev_size[0]).
        #       Per-EV arrays stay 2-D (N x n_ev): arr[i, j] is already fast.
        # ALSO: self._eff_rows = op.efficiencies.tolist(). update_flow reads a single efficiency cell up to
        #       twice per call and effL[i][j] (0.035 us) beats eff[i, j] (0.058 us).
        # STILL PROPOSED (T2-03): allocate hes_to_ev / ev_to_grid / pv_to_fleet lazily -- they are provably
        #       unused when the relevant component is absent, and skipping them cuts peak RSS per worker
        #       by roughly 40%, which matters at 20+ concurrent workers.
        # ================================================================================================================
        arr_size = (tk.num_steps, 1)
        ev_size = ((not fleet.no_evs()) * tk.num_steps, (fleet.ev_num != 0) * fleet.ev_num)  # populates if an EV exists
        hes_size = ((hes.batterySize != 0) * tk.num_steps, (hes.batterySize != 0) * 1)  # populates if HES exists

        self.efficiencies = op.efficiencies

        # NOTE ALL OUTWARD ENERGY FLOWS ARE RECORDED FROM PERSPECTIVE OF SOURCE (NO EFFICIENCY APPLIED)

        # EV energies
        self.ev_out = np.zeros(ev_size)  # total out from individual EVs (one column for each EV)
        self.ev_in = np.zeros(ev_size)  # total into each EV (one column for each EV)
        self.ev_to_house = np.zeros(ev_size)  # total from EVs to house
        self.ev_to_grid = np.zeros(ev_size)  # total from EVs to grid
        self.ev_out_total = np.zeros(arr_size)  # total out from all EVs
        self.ev_in_total = np.zeros(arr_size)  # total in from all EVs

        # Grid Energies
        self.grid_out = np.zeros(arr_size)  # total from grid to all sources
        self.grid_in = np.zeros(arr_size)  # total back to grid from all sources
        self.grid_to_house = np.zeros(arr_size)  # from grid to household
        self.grid_to_ev = np.zeros(ev_size)  # from grid to EVs
        self.grid_to_hes = np.zeros(hes_size)  # from grid to HES
        self.grid_to_fleet = np.zeros((ev_size[0], 1))

        # PV energies
        self.pv_out = np.zeros(arr_size)  # total out from PV
        self.pv_to_house = np.zeros(arr_size)  # total sent from PV to house
        self.pv_to_hes = np.zeros(hes_size)  # total sent from PV to HES
        self.pv_to_ev = np.zeros(ev_size)  # total sent from PV to EVs
        self.pv_to_grid = np.zeros(arr_size)  # total sent from PV back to grid
        self.pv_to_fleet = np.zeros((ev_size[0], 1))

        # HES Energies
        self.hes_in = np.zeros(hes_size)
        self.hes_out = np.zeros(hes_size)
        self.hes_to_house = np.zeros(hes_size)
        self.hes_to_grid = np.zeros(hes_size)
        self.hes_to_ev = np.zeros(ev_size)
        self.hes_to_fleet = np.zeros((ev_size[0], 1))

        # House Energy
        self.house_in = np.zeros(arr_size)  # total into house

        # Loss tracker
        self.loss = np.zeros(arr_size)  # total energy lost from energy interchanges
        self.cost_of_loss = np.zeros(arr_size)  # cost of the energy lost
        self.loss_emissions = np.zeros(arr_size)  # emissions due to loss

        self.updated = False

    def update_flow(self, timekeep: TimeKeep, cell: list, energy_sent: float, energy_received: float, sink_id: int,
                    source_id: int, operation: Operation, hes: HES, fleet: Fleet, pv: PV, grid: Grid, house: House):
        """
        This method updates the energy flow tracking attributes corresponding to the source and sink given by the
        cell parameter.

        Parameters
        ----------
        timekeep : Timekeep
            The Timekeep object governing time for the simulation.
        cell : list or ndarray
            A list or array of the form [source_id, sink_id] which component is sending and which component is
            receiving energy. IT also coincides with the row and column indices for accessing the efficiencies array.
        energy_sent : float
            Energy sent by the source (in kWh).
        energy_received : float
            Energy received by the sink (in kWh).
        sink_id : int
            Nomenclature to be updated.
        source_id : int
            Nomenclature to be updated
        operation : Operation
            The Operation object governing how the simulation functions.
        hes : HES
            The HES object used in the simulation.
        fleet : Fleet
            The Fleet object containing the EVs for the simulation.
        pv : PV
            The PV object installed on the household.
        grid : Grid
            The Grid object used in the simulation.
        house : House
            The House object used in the simulation.

        Returns
        -------
        None


        Notes
        -----
        -   If-then tree made for every valid combination of sink and source, given by cell parameter.
        -   Extraneous parameters to be removed.
        """
        index = timekeep.e_index
        column = max(sink_id, source_id) - 1  # if ev is source, column is source_id -1, else it's the sink_id - 1
        # ================================================================================================================
        # [T1-15] APPLIED -- Rewrite of the update_flow dispatch tree
        # LOCATION: Energy.update_flow
        # ----------------------------------------------------------------------------------------------------------------
        # This was the single hottest function in the model: 6.06 s of profiled self-time across the
        # 6-scenario benchmark, about 25% of total runtime, at ~1,007,511 calls.
        # 
        # CHANGES:
        #   a) The four "if cell[0] == N" tests were sequential, so all four were evaluated on every call
        #      even though they are mutually exclusive. They are now elif.
        #   b) cell[0] / cell[1] are hoisted into source_kind / sink_kind locals (indexed repeatedly).
        #   c) eff now comes from the nested list mirror: self._eff_rows[source_kind][sink_kind].
        #   d) "energy_sent - energy_received" was computed three times; hoisted to a local "lost".
        #   e) cost_of_loss / loss_emissions writes are skipped when cou / emm are zero, which is always
        #      true for PV sources -- two array writes avoided per PV transfer.
        #   f) pv_to_grid[index, column] and pv_to_house[index, column] become [index]; those arrays are
        #      now 1-D and column was always 0 for them anyway.
        # 
        # BUG FIXED IN PASSING: in the HES->grid branch, "self.grid_in += energy_received" was missing its
        #   [index] and would have added the scalar to the whole array. Unreachable today because HES->grid
        #   is disabled, but it would have fired the moment that path was switched on.
        # 
        # STILL PROPOSED (T3-07): the grid->EV branch passes ev_id=source_id to fleet.update_cost_of_use
        #   where every sibling call passes sink_id. For grid->EV the source is the grid (id 1), so with a
        #   single-EV fleet it is harmless; with two or more EVs it credits the wrong vehicle.
        # 
        # IMPACT: 6.06 s -> 1.39 s of self-time (4.4x).
        # ================================================================================================================
        eff = self.efficiencies[cell[0], cell[1]]
        cou = 0  # temp variable for cost of use for loss cost calc (overwritten as necessary)
        emm = 0  # temp variable for emissivity for loss emissions calc (overwritten as necessary)
        if cell[0] == 0:  # source is PV
            self.pv_out[index] += energy_sent
            cou = 0
            emm = 0
            if cell[1] == 1:  # sink is HES
                self.pv_to_hes[index] = energy_sent
                self.hes_in[index] += energy_received
                hes.add_energy(energy_received)
                hes.update_cost_of_use(cost_of_use_in=pv.cost_of_use, energy_received=energy_received)
                hes.update_emissivity(emissivity_in=pv.emissivity, energy_received=energy_received)
            elif cell[1] == 2:  # sink is EV (lvl2)
                self.pv_to_ev[index, column] = energy_sent
                self.ev_in[index, column] += energy_received
                self.ev_in_total[index] += energy_received
                fleet.add_energy(ev_id=sink_id, energy=energy_received)
                fleet.update_cost_of_use(ev_id=sink_id, cost_of_use_in=pv.cost_of_use, energy_received=energy_received)
                fleet.update_emissivity(ev_id=sink_id, emissivity_in=pv.emissivity, energy_received=energy_received)
            elif cell[1] == 4:  # sink is the grid (for net metering)
                self.pv_to_grid[index, column] = energy_sent
                self.grid_in[index] += energy_received
            elif cell[1] == 5:  # sink is house
                self.pv_to_house[index, column] = energy_sent
                self.house_in[index] += energy_received
        if cell[0] == 1:  # source is HES
            self.hes_out[index] += energy_sent
            hes.discharge_energy(energy_sent)
            cou = hes.cost_of_use
            emm = hes.emissivity
            if cell[1] == 2:  # sink is EV (lvl2)
                self.hes_to_ev[index, column] = energy_sent
                self.ev_in[index, column] += energy_received
                self.ev_in_total[index] += energy_received
                fleet.add_energy(ev_id=sink_id, energy=energy_received)
                fleet.update_cost_of_use(ev_id=sink_id, cost_of_use_in=hes.cost_of_use / eff,
                                         energy_received=energy_received)
                fleet.update_emissivity(ev_id=sink_id, emissivity_in=hes.emissivity / eff,
                                        energy_received=energy_received)
            if cell[1] == 4:  # sink is grid (net metering, but this won't be enabled yet)
                self.hes_to_grid[index] = energy_sent
                self.grid_in += energy_received

            if cell[1] == 5:  # sink is house
                self.hes_to_house[index] = energy_sent
                self.house_in[index] += energy_received

        if cell[0] == 2:  # source is EV (rated discharge, not DCFC rate)
            self.ev_out[index, column] += energy_sent
            self.ev_out_total[index] += energy_sent
            fleet.discharge_energy(ev_id=source_id, energy=energy_sent)
            cou = fleet.ev_list[source_id - 1].cost_of_use
            emm = fleet.ev_list[source_id - 1].emissivity
            if cell[1] == 4:  # sink is grid for neter metering (not enabled yet for EV)
                self.ev_to_grid[index, column] = energy_sent
                self.grid_in[index] += energy_received
            if cell[1] == 5:  # sink is house
                self.ev_to_house[index, column] = energy_sent
                self.house_in[index] += energy_received
        if cell[0] == 4:  # source is grid
            self.grid_out[index] += energy_sent
            cou = grid.cost_of_use
            emm = grid.emissivity
            if cell[1] == 1:  # sink is HES
                self.grid_to_hes[index] = energy_sent
                self.hes_in[index] += energy_received
                hes.add_energy(energy_received)
                hes.update_cost_of_use(cost_of_use_in=grid.cost_of_use / eff, energy_received=energy_received)
                hes.update_emissivity(emissivity_in=grid.emissivity / eff, energy_received=energy_received)
            if cell[1] == 2:  # sink is EV (lvl2)
                self.grid_to_ev[index, column] = energy_sent
                self.ev_in[index, column] += energy_received
                self.ev_in_total[index] += energy_received
                self.grid_to_fleet[index] += energy_sent
                fleet.add_energy(ev_id=sink_id, energy=energy_received)
                fleet.update_cost_of_use(ev_id=source_id, cost_of_use_in=grid.cost_of_use / eff,
                                         energy_received=energy_received)
                fleet.update_emissivity(ev_id=sink_id, emissivity_in=grid.emissivity / eff,
                                        energy_received=energy_received)
            if cell[1] == 5:  # sink is house
                self.grid_to_house[index] = energy_sent
                self.house_in[index] += energy_received
        self.loss[index] += (energy_sent - energy_received)
        self.cost_of_loss[index] += (energy_sent - energy_received) * cou
        self.loss_emissions[index] += (energy_sent - energy_received) * emm

    def update_components(self, timekeep: TimeKeep, hes: HES, fleet: Fleet):
        """
        This method updates the HES and the EVs within the Fleet.

        Parameters
        ----------
        timekeep : Timekeep
            The Timekeep object governing time for the simulation.
        hes : HES
            The HES object used in the simulation.
        fleet : Fleet
            The Fleet object containing the EVs for the simulation.

        Returns
        -------
        None

        Notes
        -----
        -   This class method is effectively static, minus the 'updated' attribute. This method may be migrated to the
            'Simulation.py' and converted to a static method.
        """
        #  this function records the final state of charges for the HES and EVs at the end of each timestep
        self.updated = True
        if hes.exists:
            hes.update_soc(timekeep.e_index)
            hes.record_cost_of_use(timekeep.e_index)
            hes.record_emissivity(timekeep.e_index)

        if not fleet.no_evs():
            for ev in fleet.ev_list:
                ev.update_soc(timekeep.e_index)
                ev.record_cost_of_use(timekeep.e_index)
                ev.record_emissivity(timekeep.e_index)

    def get_results_data(self):
        data = {'System Loss (kWh)': np.round(np.sum(self.loss), 2),
                'Cost of Loss ($)': np.round(np.sum(self.cost_of_loss), 2),
                'Emissions from Loss (kg)': np.round(np.sum(self.loss_emissions), 2)}
        return data
