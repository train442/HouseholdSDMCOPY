"""
Summary
-------
This module contains classes which emulate the non-tangible parts of the model which govern how the model behaves,
and parts of the model external to the household.

Classes
-------
    -   Operation : a class which contains variables which govern how the simulation runs and inter-component behavior.
    -   Timekeep : a class which controls and accounts for the passage of time in the model using timesteps.
        Contains all time related variables.
    -   Tariff : a class which contains all utility tariff data governing electricity costs (TOU, tiered, or both)
    -   City : a class which emulates the location in which the model is running a simulation and contains variables
        pertaining to that location (ie, tax rates).
    -   DrivingEvent : a class which represents a particular activity for the EV (ie, work, grocery shopping). This
        class is not yet utilized in main model, but will likely be integrated into a user interface to make a custom
        driving pattern.
    -   DrivingSchedule : a class which represents a vehicle's driving schedule, such as when it leaves for work and
        how far it drives in addition to other activities. Like DrivingEvent, this class is not yet implemented into
        the main model.
"""
import os
from functools import lru_cache

import numpy as np
import pandas as pd
import TimeManage as tm
from numpy import ndarray

default_efficiencies_file = 'Model Data/efficiencies.xlsx'


@lru_cache(maxsize=8)
def _read_efficiencies(path: str, mtime: float) -> ndarray:
    """
    Cached reader for the component-to-component efficiency matrix.

    Reading this 6x6 table costs ~46 ms and it was previously re-read from Excel on every Operation
    construction, i.e. once per scenario -- roughly 32 minutes of pure Excel parsing across a 20-file
    collection. The mtime argument is part of the cache key so editing the workbook invalidates the entry.

    Parameters
    ----------
    path : str
        Path to the efficiencies workbook.
    mtime : float
        Modification time of that file, used only as a cache key.

    Returns
    -------
    ndarray
        The efficiency matrix, rows = source, columns = sink.
    """
    del mtime  # cache key only
    return pd.read_excel(path, index_col=None, usecols='B:G').to_numpy()


def load_efficiency_matrix(path: str = default_efficiencies_file) -> ndarray:
    """
    Returns a fresh copy of the cached efficiency matrix.

    Parameters
    ----------
    path : str, optional
        Path to the efficiencies workbook. Defaults to ``Model Data/efficiencies.xlsx``.

    Returns
    -------
    ndarray
        A copy of the efficiency matrix, so callers can mutate it without poisoning the cache.
    """
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        mtime = 0.0
    return _read_efficiencies(path, mtime).copy()


# noinspection PyTypeChecker
class Operation:  # Contains operation variables pertaining to how the simulation runs
    """
    This class represents the user input and control for how the model behaves. It contains several attributes and
    methods to this effect.

    Attributes
    ----------
    efficiency_file : str, optional
        CSV file from which the efficiency array for transfers between components is found. Default is
        default_efficiency_file variable defined in Parameters.py module.
    do_dcfc : bool, optional
        Tells model to enable DC fast-charging for model. Default is False. DCFC not yet implemented in model.
    ev_discharge_limit : float, optional
        State of charge at which EVs cease all V2H functionality. Default is 50%.
    ev_as_source : bool, optional
        Boolean variable which allows V2H functionality. Default is True.
    track_costs_of_use : bool, optional
        Boolean variable which tells model to track costs of use for components. Default is true. (Maybe removed)
    hes_optimization : str, optional
        Type of hes optimization scheme the model runs. Default is 'perfect'. (See Notes)
    hes_cover_mid : bool, optional
        Boolean variable which allows model to cover mid-peak periods as well as on-peak periods. Default is True.
    ev_throughput : int, float
        Maximum power rate that an EV can put towards the house. Default is 12 kW.
    hes_buffer : float
        Extra battery percentage added on top of percentage dictated by optimization regime.
    net_meter_scheme: str
        Net metering protocol used in simulation. Default is 'wholesale'. (See Notes)
    avoided_rate : float
        Wholesale rate (AKA avoided-cost rate) in $/kWh that utilities pay for excess solar generation.
    net_meter_account_freq : str
        Frequency with which net billing is assessed. Default is monthly.
    simu_name : str
        Name by which specific simulation is called. (Will be saved in form 'name.pkl')
    simu_id : int
        Number of current simulation within set of runs. Default is 1.
    cost_of_gas : float
        Cost of gas in $/gal. Default is $3.803/gal or average national rate.
    user_profile : bool
        Whether a specific user load profile has been loaded (True) or the sim defaults to the ResStock profiles.
    """

    def __init__(self, efficiency_file: str = default_efficiencies_file, do_dcfc=False, ev_discharge_limit: float = .5,
                 ev_as_source: bool = True, track_costs_of_use: bool = True, hes_optimization: str = 'perfect',
                 hes_cover_mid: bool = True, net_meter_scheme: str = 'wholesale', simu_name: str = 'insert_name_here',
                 simu_id: int = 1, user_profile: bool = False):
        self.efficiency_file = efficiency_file
        self.do_dcfc = do_dcfc
        self.ev_discharge_limit = ev_discharge_limit  # min soc at which EV is allowed to discharge to house
        self.ev_as_source = ev_as_source and (ev_discharge_limit != 1)  # allow EV to discharge at all besides driving
        self.efficiencies = self.load_efficiencies()
        self.track_costs_of_use = track_costs_of_use
        self.hes_optimization = hes_optimization  # possible values ('perfect', 'previous day', 'flat', 'none')
        self.hes_cover_mid = hes_cover_mid
        self.ev_throughput = 12  # kW that ev can put towards house. In practice, this is limited by inverter
        self.hes_buffer = .1  # buffer to hes optimization (extra x%)
        self.net_meter_scheme = net_meter_scheme  # can be 'Basic', 'One-to-One', 'Flat', or 'Tariff'
        self.avoided_rate = .03  # wholesale energy rate, will be unique to each state. Flat for now.
        self.net_meter_account_freq = 'yearly' if (net_meter_scheme in ['no excess', 'no_excess']) else 'monthly'
        self.simu_name = simu_name  # name by which simulation is referred
        self.simu_id = simu_id
        self.cost_of_gas = 3.803
        self.battery_cost = 157  # $/kWh
        self.ev_warranty = 100000  # mi
        self.user_profile = user_profile  # whether a user load profile is being provided to model
        # perfect: prerun the coverage periods with no HES and determine the amount of grid out
        # previous day: utilize difference between pv and house load on previous day
        # previous days: utilize average difference between pv and house loads on previous days

    def load_efficiencies(self) -> ndarray:
        """
        Returns
        -------
        ndarray:
            An array containing the efficiency of energy transfers between components. Rows are the
            source component, columns the sink, using the ordering
            ``0 = PV, 1 = HES, 2 = EV (L2), 3 = EV (DCFC), 4 = Grid, 5 = House``.
        """
        return load_efficiency_matrix(self.efficiency_file)

    # def get_calendar(self):  # get/create calendar for simulation
    #     # first check if calendar already exists
    #     cal_file = str(self.year) + '_' + str(self.timestep) + 'min.csv'
    #     if os.path.exists('Model Data/Calendars/' + cal_file):
    #         cal = pd.read_csv('Model Data/Calendars/' + cal_file).to_numpy()
    #     else:

    def update_net_met_policy(self, policy: str):
        self.net_meter_scheme = policy


class TimeKeep:  # class pertaining to all variables dealing with time
    """
    This class serves as a container for all time-related variables and methods.

    Attributes
    ----------
    timestep: int
        The duration (in minutes) of each step in the simulation.
    year: int
        The year in which the simulation starts.
    start_date : Timestamp
        The starting date of the simulation.
    end_date: Timestamp
        The ending date of the simulation.
    simu_days : int
        Number of days in simulation.
    num_steps : int
        Number of steps in simulation.
    calendar : array_like
        an N x 6 numpy array where N is the number of steps. Columns in order are day-of-week, day-of-month, month,
        day-of-year, hour, and minute.
    starting_day : int
        day of the year (out of 365/366) on which the simulation starts.
    ending_day: int
        day of year (out of 365/366) on which simulation ends.
    current_day : int
        Current day within simulation.
    current_month : int
        Current month within simulation.
    current_hour : int
        Current hour within simulation.
    day_start_step : int
        Step on which the current day started within simulation.
    day_end_step : int
        Step on which current day ends within simulation.
    hour_start_step : int
        Step on which current hour starts within simulation.
    hour_end_step : int
        Step on which current hour ends within simulation.
    simu_start_step : int
        Step on which current simulation starts. (Updated to be always 1, so may be removed).
    simu_end_step : int
        Step on which current simulation ends. (Redundant since "any date" update, so may be removed)
    step : int
        Current step in simulation. Starts at 1 and increments at each successive step.
    index : int
        Current index for accessing input data (solar, house load, etc.). Always 1 less than the step.
    e_index : int
        Current index for accessing and assigning data in energy flow arrays (See Components.Energy).

    """

    def __init__(self, timestep=5, year=2018, starting_day=1, simu_days=365, from_date=False,
                 start_date=pd.to_datetime('1/1/2018'), end_date=pd.to_datetime('12/31/2018')):
        try:
            self.timestep = int(timestep)  # minutes per timestep, default is 5 minutes
        except ValueError:
            self.timestep = 5

        if from_date:
            self.year = start_date.year
            if end_date < start_date:  # correct if end date is less than start date
                end_date = start_date + pd.Timedelta(str(simu_days) + ' days')
        else:
            self.year = int(year)
            start_date = pd.to_datetime('1/1/' + str(self.year)) + pd.Timedelta(str(starting_day - 1) + 'days')
            end_date = start_date + pd.Timedelta(str(simu_days - 1) + 'days')

        self.start_date = start_date
        self.end_date = end_date
        self.simu_days = (end_date - start_date).days + 1  # number of days to simulate (+1 to include initial day)
        self.num_steps = int(self.simu_days * 24 * (60 / timestep))
        self.calendar = tm.create_calendar_from_datetime(start=start_date, end=end_date, timestep=timestep)
        self.starting_day = start_date.day_of_year  # numbered day of year from which to start simulation
        self.ending_day = end_date.day_of_year  # numbered day of year on which to end simulation
        self.current_day = int(1)  # current day within simulation
        self.current_month = self.calendar[0, 2]  # current month within simulation
        self.current_hour = self.calendar[0, 4]  # current hour within simulation
        self.day_start_step = int(1)  # step on which current day starts
        self.day_end_step = self.day_start_step + int(24 * 60 / timestep) - 1  # step on which current day ends
        self.hour_start_step = int(1)  # step on which current hour starts
        self.hour_end_step = self.hour_start_step + int(60 / timestep) - 1  # step on which current hour ends
        self.simu_start_step = 1  # after "any date" update, starting step is always 1
        self.simu_end_step = self.simu_start_step + self.num_steps - 1  # step on which simulation ends
        self.step = self.simu_start_step
        self.index = self.simu_start_step - 1  # index for full_year data (solar, load, etc)
        self.e_index = 0  # index for energy flows, cou's, and soc's (length of sim, not necessarily full year)

    def increment_step(self):
        """
        This method increments the step, index, and e_index attributes by 1.
        Returns
        -------
        None
        """
        self.step += 1
        self.e_index += 1
        self.index += 1

    def update_day(self):  # update the starting and ending steps of the day
        """
        This method is called whenever the day changes. It reassigns the day_start_step and day_end_step attributes
        to reflect the new day. It also increments the current_day attribute. Finally, it reassigns the current_month
        attribute, which will change value to match the calendar attribute.

        Returns
        -------
        None
        """
        self.day_start_step += 24 * 60 / self.timestep
        self.day_end_step += 24 * 60 / self.timestep
        self.current_day += 1
        if self.step != self.num_steps:  # this check ensures we don't exceed the index limit of the calendar attribute.
            self.current_month = self.calendar[(self.index + 1), 2]

    def update_hour(self):  # update the starting and ending steps of the hour
        """
        This method reassigns the hour_start_step and hour_end_step attributes. It also increments the
        current_hour attribute and ensures that the hour does not exceed 23. (0 is 12:00am, 23 is 11:00pm)
        Returns
        -------

        """
        self.hour_start_step += 60 / self.timestep
        self.hour_end_step += 60 / self.timestep
        self.current_hour = (self.current_hour + 1) % 24

    def update_month(self):  # update the current month
        """
        This method increments the current month. (obsolete)
        Returns
        -------
        None
        """
        self.current_month = (self.current_month + 1) % 12

    def reset(self):
        """
        This method resets the incrementing attributes of the Timekeep class for use in successive simulations using
        the same dates.
        Returns
        -------
        None
        """
        self.current_day = int(1)
        self.current_month = self.calendar[0, 2]
        self.current_hour = self.calendar[0, 4]
        self.day_start_step = int(1)
        self.day_end_step = self.day_start_step + int(24 * 60 / self.timestep) - 1
        self.hour_start_step = int(1)
        self.hour_end_step = self.hour_start_step + int(60 / self.timestep) - 1
        self.simu_start_step = 1
        self.simu_end_step = self.simu_start_step + self.num_steps - 1
        self.step = self.simu_start_step
        self.index = self.simu_start_step - 1
        self.e_index = 0

    def get_results_data(self):
        data = {'Start Date': self.start_date,
                'End Data': self.end_date,
                'Step': self.timestep}
        return data

    def get_index_in_calendar(self, month: int = 1, day: int = 0, hour: int = 0, minute: int = 0) -> int:

        if type(month) is not int:
            month = 1
        elif (month < 1) or (month > 12):
            month = 1

        if month in [4, 6, 9, 11]:
            day_lim = 30
        elif month in [1, 3, 5, 7, 8, 10, 12]:
            day_lim = 31
        else:
            day_lim = 28

        if type(day) is not int:
            day = 1
        elif (day < 1) or (day > day_lim):
            day = 1

        if type(hour) is not int:
            hour = 0
        elif (hour < 0) or (hour > 23):
            hour = 0

        if type(minute) is not int:
            minute = 0
        elif (minute < 0) or (minute > 55):
            minute = 0

        ind = np.where((self.calendar[:, 2] == month) & (self.calendar[:, 1] == day) &
                       (self.calendar[:, 4] == hour) & (self.calendar[:, 5] == minute))[0][0]

        return int(ind)


class Tariff:  # contains tariff data for specific data sheet
    """
    This class represents the utility which provides power to the household. It contains attributes and methods
    pertaining to a utility and its rates.

    Attributes
    ----------
    name : str
        Name or designation of the tariff schedule the household is subject too.
    utility : str
        Name of the utility providing the power.
    monthly_charge : float
        Monthly non-usage costs (ie, connection fees, etc.) charged to customer on monthly basis.
    minimum_charge : float
        Minimum bill amount imposed by utility on monthly basis.
    periods_energy : list
        A list of lists, with each element representing a period, containing a rate ($/kWh) and a tier limit (kWh).
        Non-tiered periods have -1 as there tier limit.
    weekday_schedule : array_like
        A 12 x 24 numpy array with each row corresponding to a month, and each column corresponding to hours in the
        day. Each element is an integer representing which period (tier and rate) applies at that hour,
        in that month, during a weekday.
    weekend_schedule : array_like
        A 12 x 24 numpy array with each row corresponding to a month, and each column corresponding to hours in the
        day. Each element is an integer representing which period (tier and rate) applies at that hour,
        in that month, during a weekend.
    periods_demand : list
        A list of lists, with each element representing a period and containing a rate ($/kW) and a tier limit (kW).
        Non-tiered periods have -1 as a tier limit. This is for schedules with demand charges, which are costs per
        peak kW usage in a given segment of time (usually an hour).
    weekday_schedule_power : array_like
        A 12 x 24 numpy array with each row corresponding to a month, and each column corresponding to hours in the
        day. Each element is an integer representing which demand period (tier and rate) applies at that hour,
        in that month, during a weekday.
    weekend_schedule_power : array_like
        A 12 x 24 numpy array with each row corresponding to a month, and each column corresponding to hours in the
        day. Each element is an integer representing which demand period (tier and rate) applies at that hour,
        in that month, during a weekend.
    is_tou : bool
        Whether the current schedule is time-of-use (TOU) meaning there are peak and off-peak periods for all or
        some of the year.
    is_tiered : bool
        Whether the current schedule is tiered, meaning the electricity has different costs per kWh depending on the
        total usage is a certain amount of time.
    is_demand : bool
        Whether the current schedule has demand charges ($/kW), based on the maximum average power draw of a
        household in a given amount of time (usually an hour).
    tou_schedule : array_like
        This is N x 2 numpy array containing the rates ($/kWh) in the first column and the peak (1), mid (.5),
        or off-peak (0) status at each timestep in the simulation. N is the number of steps.
    weekday_rates : array_like
        12 x 24 numpy array showing the per kWh cost at each hour (column) and month (row) for weekdays.
    weekend_rates : array_like
        12 x 24 numpy array showing the per kWh cost at each hour (column) and month (row) for weekends.
    unique_tou_rates : array_like
        A numpy array containing the unique tou rates found in the schedule. Will be empty if schedule is not TOU.
    max_tiers : int
        The maximum number of tiers contained in any given period of the schedule.
    end : int
        Ending step of the tou calendar. Will match number of simulation steps.
    is_currently_off : bool
        whether the current timestep is currently off-peak (True) or not (False).
    is_currently_on : bool
        whether the current timestep is currently on-peak (True) or not (False).
    is_currently_mid : bool
        whether the current timestep is currently off-mid (True) or not (False).
    next_off : int
        timestep in which the net off-peak begins. Important for HES optimization.
    end_of_current : int
        timestep in which current rate period ends.

    """

    def __init__(self, name: str, utility: str, eia: str, monthly_charge: float, minimum_charge: float, sellback: float,
                 periods_energy: list, weekday_schedule: np.ndarray, weekend_schedule: np.ndarray, periods_demand: list,
                 weekday_schedule_power: np.ndarray, weekend_schedule_power: np.ndarray, is_tou: bool, is_tiered: bool,
                 is_demand: bool, net_met_policy: str, re_up_freq: str, nbc: int = 0):
        self.name = name  # name or designation of the actual tariff
        self.utility = utility  # name of the utility
        self.eia = eia  # eia code of utility
        self.sellback_rate = sellback  # sellback rate (avoided cost + any adders)
        self.monthly_charge = monthly_charge  # monthly charge on bill
        self.minimum_charge = minimum_charge  # minimum charge on bill
        self.periods_energy = periods_energy  # rates of each period
        self.weekday_schedule = weekday_schedule  # rate schedule for weekdays
        self.weekend_schedule = weekend_schedule  # rate schedule for weekends
        self.periods_demand = periods_demand  # demand rates for each period
        self.weekend_schedule_power = weekend_schedule_power  # demand rate schedule for weekdays
        self.weekday_schedule_power = weekday_schedule_power  # demand rate schedule for weekends
        self.is_tou = is_tou
        self.is_tiered = is_tiered
        self.is_demand = is_demand
        self.tou_schedule = np.array([])
        self.weekday_rates, self.weekend_rates = self.create_rates()
        self.net_met_policy = net_met_policy
        self.re_up_freq = re_up_freq  # how often bill credits are translated to currency (monthly or yearly)
        self.nbc = nbc  # non bypassable charges
        if self.is_tou:
            self.unique_tou_rates = np.unique(np.append(self.weekday_rates, self.weekend_rates))
        else:
            self.unique_tou_rates = []

        if self.is_tiered:
            self.max_tiers = len(max(self.periods_energy, key=len))
        else:
            self.max_tiers = 0
        self.end = 105120  # ending step of calendar
        self.is_currently_off = False
        self.is_currently_on = False
        self.is_currently_mid = False
        self.next_off = 0  # start of next off period
        self.end_of_current = 0  # end of current period

    def reset(self):
        """
        This method resets the Tariff object for use in successive simulations with the same tariff schedule.
        Returns
        -------
        None
        """
        # self.end = 105120  # ending step of calendar
        self.is_currently_off = False
        self.is_currently_on = False
        self.is_currently_mid = False
        self.next_off = 0  # start of next off period
        self.end_of_current = 0  # end of current period

    # this converts period representation of week_day_schedule and weekend schedule to rate. In simpler terms it
    # replaces the 0's, 1's, etc. that represent the periods with the actual rates therein.
    def create_rates(self):
        """
        This method is called during instantiation and generates the weekday_rates and weekend_rates attributes
        using the periods_energy, weekday_schedule and weekend_schedule attributes. IT essentially replaces the
        integers in the schedules with the rates of their corresponding periods in the periods_energy list.
        Returns
        -------
        weekday_rates: np.ndarray
            12 x 24 numpy array showing the per kWh cost at each hour (column) and month (row) for weekdays.
        weekend_rates: np.ndarray
            12 x 24 numpy array showing the per kWh cost at each hour (column) and month (row) for weekends.
        """
        period_num = len(self.periods_energy)
        rates = np.array([per[0][1] for per in self.periods_energy])
        weekday_rates = self.weekday_schedule.astype(float)
        weekend_rates = self.weekend_schedule.astype(float)
        for i in range(period_num):
            weekend_rates[weekend_rates == (i + 1)] = rates[i]
            weekday_rates[weekday_rates == (i + 1)] = rates[i]
        return weekday_rates, weekend_rates

    def create_tou_schedule(self, calendar: np.ndarray):
        """
        This method must be called after instantiation and generates the tou_schedule attribute using a simulation
        calendar provided as an input (see Timekeep for description of said calendar)

        Parameters
        ----------
        calendar: np.ndarray
            a numpy array containing date (day, month, hour, minute, etc.) for each timestep. (see Timekeep.calendar)

        Returns
        -------
            None
        """
        num = calendar.shape[0]
        tou = np.zeros((num, 2))
        pdow = 8  # previous day of week (if current is not equal we assess new rates for peak/off-peak
        rates = []
        for i in range(num):
            mon = int(calendar[i, 2])  # extract month
            hr = calendar[i, 4]  # extract hour
            dow = calendar[i, 0]  # extract day of week

            if dow in [6, 7]:  # weekend rate
                rate = self.weekend_rates[mon - 1, hr]  # mon -1 due to indexing
                daily_rates = self.weekend_rates[mon - 1, :]
            else:
                rate = self.weekday_rates[mon - 1, hr]
                daily_rates = self.weekday_rates[mon - 1, :]

            if dow != pdow:  # if new day, then reassess rates for the day to determine peak periods
                rates = np.unique(daily_rates)
                pdow = dow

            if rate == min(rates):  # off-peak
                peak_value = 0
            elif rate == max(rates):  # on-peak
                peak_value = 1
            else:  # mid-peak
                peak_value = .5

            tou[i, 0] = rate
            tou[i, 1] = peak_value
        self.tou_schedule = tou
        self.end = len(tou[:, 0])

    def get_tou_rate(self, step: int):  # return tou rate and peak value (1=on-peak, .5 = mid-peak, 0 = off-peak)
        """
        This method returns the tou rate at the step provided asa well as the peak/mid/off-peak designation of the
        step (1 = on-peak, .5 = mid-peak, 0 = off-peak).
        Parameters
        ----------
        step: int
            Step in simulation for which the current electricity rate is desired.
        Returns
        -------
        float:
            electricity rate ($/kWh) at desired step
        float:
            peak/mid-peak/off-peak designation for step
        """
        index = step - 1
        return self.tou_schedule[index, 0], self.tou_schedule[index, 1]

    def is_off_peak(self, step: int):
        """
        This method returns True if the step provided is off-peak. False otherwise.
        Parameters
        ----------
        step: int
            step to check for off-peak status. Can be any step, but is typically the current one in simulation.

        Returns
        -------
        bool:
            Whether step provided is off-peak (True) or not (False).
        """
        index = step - 1
        return self.tou_schedule[index, 1] == 0

    def is_on_peak(self, step: int):
        """
        This method returns True if the step provided is on-peak. False otherwise.
        Parameters
        ----------
        step: int
            step to check for on-peak status. Can be any step, but is typically the current one in simulation.

        Returns
        -------
        bool:
            Whether step provided is on-peak (True) or not (False).
        """
        index = step - 1
        return self.tou_schedule[index, 1] == 1

    def is_mid_peak(self, step: int):
        """
        This method returns True if the step provided is mid-peak. False otherwise.
        Parameters
        ----------
        step: int
            step to check for mid-peak status. Can be any step, but is typically the current one in simulation.
        Returns
        -------
        bool:
            Whether step provided is mid-peak (True) or not (False).
        """
        index = step - 1
        return self.tou_schedule[index, 1] == .5

    def get_end_of_period(self, step: int, update=False):  # returns timestep at which current period ends
        """
        This method returns the timestep for which the period containing the provided step ends. It will also update
        the end_of_current attribute with this timestep if told to by the update parameter.
        Parameters
        ----------
        step : int
            Step which is contained in the period in question. Method will return last timestep of the period which
            contains this step.
        update: bool
            Whether to update the end_of_current attribute with the value returned by this method. True when we wish
            to know the end of the current period within the simulation using the current timestep.

        Returns
        -------
        eop: int
            Short for end-of-period. It is the ending timestep of the period containing the step provided.
        """
        index = step - 1

        try:
            peak_num = self.tou_schedule[index, 1]
            eop = np.where(self.tou_schedule[index:index + 3 * 24 * 12, 1] != peak_num)[0][0] + index  # search 3 days
        except IndexError:
            eop = self.end

        if update:
            self.end_of_current = eop
        return eop

    def get_next_off_peak(self, step: int, update=False):  # returns step of next off-peak
        """
        This method will give the starting timestep of the next off-peak period after the period containing the step
        given. It will also update the next_off attribute with this timestep if directed by the update parameter.
        Parameters
        ----------
        step: int
            A step contained in a period for which we want to find the next closest off-peak period.
        update: bool
            Whether to update the next_off attribute
        Returns
        -------
        start : int
            starting step of next off-peak period after the period containing the step provided.
        """
        index = step - 1
        peaks = self.tou_schedule[:, 1]
        try:
            if self.is_off_peak(step):
                end_of_off = self._first_index_where(peaks, index, equal=False, value=0.0)
                start = self._first_index_where(peaks, end_of_off, equal=True, value=0.0) + 1
            else:
                start = self._first_index_where(peaks, index, equal=True, value=0.0) + 1
        except IndexError:
            start = self.end + 1

        if update:
            self.next_off = start
        return start

    @staticmethod
    def _first_index_where(peaks: ndarray, start: int, equal: bool, value: float) -> int:
        """
        Finds the first index at or after ``start`` whose peak designation matches (or fails to match) ``value``.

        Searches in widening windows rather than scanning to the end of the year. The callers are looking for
        a period boundary, which is almost always within a day or two; the previous unbounded
        ``np.where(arr[index:] == 0)`` scanned every remaining timestep of the simulation on every call
        (~120 microseconds each).

        Parameters
        ----------
        peaks : ndarray
            The peak-designation column of the TOU schedule.
        start : int
            Index to begin searching from.
        equal : bool
            True to find the first index matching ``value``, False to find the first index not matching it.
        value : float
            The peak designation to compare against (0 off-peak, 0.5 mid-peak, 1 on-peak).

        Returns
        -------
        int
            Absolute index of the first match.

        Raises
        ------
        IndexError
            If no match exists at or after ``start``.
        """
        total = peaks.shape[0]
        window = 3 * 24 * 12  # three days at 5-minute resolution
        while start < total:
            stop = min(start + window, total)
            chunk = peaks[start:stop]
            hits = np.flatnonzero(chunk == value) if equal else np.flatnonzero(chunk != value)
            if hits.size:
                return int(hits[0]) + start
            if stop >= total:
                break
            start = stop
            window *= 4  # widen fast so pathological tariffs don't degrade to a linear crawl
        raise IndexError('no matching peak designation at or after the given step')

    def get_coverage_steps(self, step: int, operation: Operation):
        """
        Returns a 1D numpy array containing all the steps between off-peaks for which the HES is allowed to discharge
        governed by the Operation object provided. If the hes_cover_mid attribute of the Operation object is True,
        then mid-peak steps are included, else only the on-peak periods are used. This method should be called at the
        beginning of an off-peak period, with the step provided being the current step.
        Parameters
        ----------
        step : int
            Step from which the coverage steps are calculated. The end of the period containing this step will be the
            start of the coverage steps.
        operation : Operation
            An Operation object which governs model behavior. Determines if mid-peak periods are included in coverage.
        Returns
        -------
        steps : ndarray
            numpy array containing steps for which HES is allowed to discharge to house provided it has energy.
        """
        start = self.get_end_of_period(step) + 1
        eoc = self.get_next_off_peak(start) - 1

        steps = np.zeros(0, dtype=int)  # initialised so an exception below can't leave this unbound
        try:
            if operation.hes_cover_mid:
                steps = np.arange(start, eoc + 1, dtype=int)
            else:
                # Column 1 holds the peak designation (0 off, .5 mid, 1 on). This previously read
                # column 2, which does not exist -- tou_schedule is (N, 2) -- so this branch raised
                # IndexError, which the old "except ValueError" did not catch.
                on_peak = np.flatnonzero(self.tou_schedule[(start - 1):eoc, 1] == 1)
                steps = (on_peak + start).astype(int)
        except (ValueError, IndexError) as ex:
            print(f'get_coverage_steps failed between steps {start} and {eoc}: {ex}')
        return steps

    def get_daily_rates(self, day, timestep=5):
        """
        This method returns the TOU rates for the day given the numbered day of the simulation (ie, day 1 or 50).
        Parameters
        ----------
        day : int
            The numbered day of the simulation. (Not the day of month or day of year)
        timestep : int, optional
            The duration of a timestep in minutes. Default is 5.

        Returns
        -------
        rates : ndarray
            Numpy array containing the TOU rates for the given day.
        """
        s = int((day - 1) * 24 * 60 / timestep)
        e = int(day * 24 * 60 / timestep - 1)
        rates = np.unique(self.tou_schedule[s:(e + 1), 0])
        return rates

    def update_status(self, step: int):
        """
        This method updates the on-peak/mid-peak/off-peak status of the tariff by calling the is_currently_off,
        is_currently_off and is_currently_mid methods using the current timestamp as a parameter.
        Parameters
        ----------
        step: int
            Timestep for which the Tariff object is updated. Should be the current simulation timestep.

        Returns
        -------
        None
        """
        self.is_currently_on = self.is_on_peak(step=step)
        self.is_currently_off = self.is_off_peak(step=step)
        self.is_currently_mid = self.is_mid_peak(step=step)

    def return_periods(self, start_step: int, end_step: int):
        """
        This method returns a list of periods (represented by sub-lists) between two steps provided. Each period
        sub-list is of the form [order, start_step, end_step, tou_rate, peak_value] where order is the order in
        which the period occurs, start_step and end_step are the beginning and end of each period respectively,
        tou_rate is the electricity cost ($/kWh) and peak_value is 0 for off-peak, .5 for mid-peak, and 1 for on-peak.
        Parameters
        ----------
        start_step: int
            Lower bound step for list of periods.
        end_step : int
            Upper bound step for list of periods.
        Returns
        -------
        periods: list
            A list of periods between the steps provided.
        """
        #  returns list of periods (denoted as list) between a starting and ending step.
        #  sublist: [order, start, end, tou_rate, peak_value]
        more_periods = True
        period_start = start_step
        periods = []
        i = 1
        while more_periods:
            period_end = self.get_end_of_period(period_start)
            tou_rate, peak_num = self.get_tou_rate(period_start)
            period_end = min(period_end, end_step)  # end of period cannot exceed end of time inquired
            period = [i, period_start, period_end, tou_rate, peak_num]
            periods.append(period)
            more_periods = (period_end != end_step) and (period_end < self.end)  # still more periods in inquiry period
            if more_periods:
                i += 1
                period_start = period_end + 1
                more_periods = period_start < self.end

        return periods

    def update_sellback(self, new_rate: float):
        self.sellback_rate = new_rate

    def is_same_period(self, step1: int, step2: int):
        """
        Tells user whether two steps given occur in same period.
        Parameters
        ----------
        step1: int
            first step
        step2: int
            second step

        Returns
        -------
        same_period: bool
            whether the two steps given are in the same period
        -------

        """
        same_period = True
        rate1 = self.get_tou_rate(step1)
        rate2 = self.get_tou_rate(step2)
        if rate1 != rate2:  # if rates don't match then they are different periods
            same_period = False
        # if there are rates between then periods don't match
        elif np.count_nonzero(self.tou_schedule[(step1-1):step2] != rate1) > 0:
            same_period = False

        return same_period

    def get_unique_rates(self) -> ndarray:
        """
        This method returns a refined array of unique TOU rates by month for use in plotting rates.
        Returns
        -------

        """
        pass

    def update_net_met_policy(self, policy: str):
        self.net_met_policy = policy


class City:
    """
    This class represents the city in which the household is located and contains attributes pertinent to this role.

    Attributes
    ----------
    name : str
        name of the city
    state : str
        abbreviation of the state in which the city is located. (ie, GA, AZ, ME)
    state_full : str
        full name of state in which the city is located (ie, Georgia, Arizona, California)
    county : str
        name of county the city is located in.
    zipcode : str
        Zipcode of household.
    latitude : float
        Latitude of city.
    longitude : float
        Longitude of city.
    time_zone : str
        Timezone of city. (ie, EST, PST)
    carbon_intensity : float
        Average carbon intensity (kg CO2/ kWh) of grid in state which household is located.
    matched_city : str
        Name of closest city for which house load and solar data is available. Model will use this data.
    matched_state : str
        Name of state containing the matched city for which house load and solar data is available.
    matched_wattime_region : str
        WattTime balancing-authority region code covering the matched city, if one has been resolved (see the
        Data Import Wizard's WattTime tab). None if not yet resolved.
    tax_rate : float
        Combined sales tax rate for electricity in locality.
    utilities : list
        A list of utilities servicing this locality.
    eias : list
        A list of the EIA codes for each of the utilities servicing each locality.
    follows_dst : bool
        Whether locality follows daylight savings time (True) or not (False)

    """

    def __init__(self, name, state, state_full, county, zipcode, latitude, longitude, time_zone, carbon_intensity,
                 tax_rate, utilities, eias, follows_dst=True, matched_city=None, matched_state=None,
                 solar_unit_cost: float = 2.86, matched_wattime_region=None):
        """

        Parameters
        ----------
        name : str
            name of the city
        state : str
            abbreviation of the state in which the city is located. (ie, GA, AZ, ME)
        state_full : str
            full name of state in which the city is located (ie, Georgia, Arizona, California)
        county : str
            name of county the city is located in.
        zipcode : str
            Zipcode of household.
        latitude : float
            Latitude of city.
        longitude : float
            Longitude of city.
        time_zone : str
            Timezone of city. (ie, EST, PST)
        carbon_intensity : float
            Average carbon intensity (kg CO2/ kWh) of grid in state which household is located.
        matched_city : str, optional
            Name of closest city for which house load and solar data is available. Model will use this data.
            Defaults to None.
        matched_state : str, optional
            Name of state containing the matched city for which house load and solar data is available. Defaults to
            None.
        matched_wattime_region : str, optional
            WattTime balancing-authority region code covering the matched city. Defaults to None.
        tax_rate : float
            Combined sales tax rate for electricity in locality.
        utilities : list
            A list of utilities servicing this locality.
        eias : list
            A list of the EIA codes for each of the utilities servicing each locality.
        follows_dst : bool, optional
            Whether locality follows daylight savings time (True) or not (False). Default is True.
        """
        self.name = name  # name of city
        self.state = state  # state city lies in (abbr.)
        self.state_full = state_full  # full name of state city lies in
        self.county = county  # county that city lies in
        self.zipcode = zipcode  # zipcode (maybe one of many) of city
        self.latitude = latitude  # latitude of city
        self.longitude = longitude  # longitude of city
        self.time_zone = time_zone  # time zone of city
        self.carbon_intensity = carbon_intensity  # average kg CO2 emitted per kWh produced on grid
        self.matched_city = matched_city  # city from which solar and load data are sourced
        self.matched_state = matched_state  # see matched city
        self.matched_wattime_region = matched_wattime_region  # WattTime BA region covering matched city
        self.tax_rate = tax_rate  # combined tax rate for city
        self.utilities = list(utilities)  # list of utilities in city
        self.eias = list(eias)  # list of eia codes for utilities in city
        self.follows_dst = follows_dst  # whether city follows Daylight Saving Time (DST)
        self.solar_unit_cost = solar_unit_cost

    def get_results_data(self):
        data = {'Name': self.name,
                'State': self.state,
                'Reference City': self.matched_city,
                'Reference State': self.matched_state}
        return data


class DrivingEvent:
    """
    This class is designed to emulate a driving event for the EV such as work, grocery store trips, etc.

    Attributes
    ----------
    name : str
        The name or purpose of the trip (ie, Work)
    start_time : pd.Timestamp
        The time of departure for the trip.
    end_time : pd.Timestamp
        The time of return/end of the trip.
    miles_driven : float
        The amount of miles for the trip.
    days : dict
        A dictionary of with keys corresponding to days of the week paired with boolean values describing if the
        event occurs on that day.
    """

    def __init__(self, name: str, start_time: pd.Timestamp, end_time: pd.Timestamp, miles_driven: float, days: dict):
        """
        The initialization method for the DrivingEvent class.
        Parameters
        ----------
        name : str
            The name or purpose of the trip (ie, Work)
        start_time : pd.Timestamp
            The time of departure for the trip.
        end_time : pd.Timestamp
            The time of return/end of the trip.
        miles_driven : float
            The amount of miles for the trip.
        days : dict
            A dictionary of with keys corresponding to days of the week paired with boolean values describing if the
            event occurs on that day.
        """
        self.name = name
        self.start_time = start_time
        self.end_time = end_time
        self.miles_driven = miles_driven
        self.days = days

    def check_conflict(self, event):
        """
        This method checks for a time or name conflict with another
        Parameters
        ----------
        event: DrivingEvent
            Another DrivingEvent instance which is to be checked against current event for conflict.
        Returns
        -------
        bool
            If the events are conflicting in name or time (TRUE) or not (FALSE).
        """
        same_day = False

        same_name = self.name == event.name

        for key in self.days.keys():
            if self.days[key] & event[key]:
                same_day = True

        times1 = set(pd.date_range(start=self.start_time, end=self.end_time, freq='5min'))
        times2 = set(pd.date_range(start=event.start_time, end=event.end_time, freq='5min'))

        same_time = bool(times1 & times2)

        # if events ok on same day and same time, they are in conflict. Can't add event with same name
        return (same_day & same_time) | same_name

    def day_string(self):
        """
        This method returns a string containing days of the week this event occurs on. For example, a Monday,
        Wednesday, and Friday event would return 'MWF'.

        Returns
        -------
        day_string : str
            A string containing abbreviated letters for days of the week on which the event occurs.
        """
        day_string = ''
        if self.days['Monday']:
            day_string += 'M'
        if self.days['Tuesday']:
            day_string += 'T'
        if self.days['Wednesday']:
            day_string += 'W'
        if self.days['Thursday']:
            day_string += 'Th'
        if self.days['Friday']:
            day_string += 'F'
        if self.days['Saturday']:
            day_string += 'Sa'
        if self.days['Sun']:
            day_string += 'Sun'
        return day_string

    def duration_string(self):
        """
        This method returns a string describing the start and end times of the event.

        Returns
        -------
        dur : str
            A string describing the start and end times of the event of form '{start time} to {end time}'
        """
        dur = str(self.start_time.time())[0:-3] + 'to' + str(self.end_time.time())[0:-3]
        return dur

    def transcribe_event(self):
        """
        This method returns a string representation of the event and all of its attributes.

        Returns
        -------
        transcription: str
            A string describing all attributes of a driving event.
        """
        transcription = self.name + '_' + self.day_string() + '_' + self.duration_string() + '_' + str(
            self.miles_driven) + 'mi'
        return transcription


class DrivingSchedule:
    """
    This method describes a driving schedule of the EV consisting of several driving events. It starts off as an
    empty schedule loaded from empty_pattern.csv in the DrivingPatterns folder.

    Attributes
    ----------
    minute_resolution : int
        The time resolution of the schedule in minutes. Can be 5, 15, or 30 minutes.
    event_list : list
        A list of DrivingEvents objects added to the DrivingSchedule.
    schedule : DataFrame
        A pandas dataframe representation of the driving schedule. See Notes for details.

    Notes
    -----
    -   The schedule attribute consists of a time column, with resolution given by the minute_resolution.
    -   The schedule attribute also contains 2 columns for each day of the week and holidays. One contains 1 if the
        EV is present and 0 if the EV is gone, and the other column contains the miles driven.
    """

    def __init__(self, minute_resolution=30):
        """
        This is the initialization method of the DrivingSchedule class.

        Parameters
        ----------
        minute_resolution : int
            The time resolution of the schedule in minutes. Can be 5, 15, or 30 minutes.
        """
        self.minute_resolution = minute_resolution
        self.event_list = []
        self.schedule = pd.read_csv('DrivingPatterns/empty_pattern.csv', parse_dates=['Time'])
        self.check_resolution()
        if self.minute_resolution > 30:
            self.increase_res()

    def check_resolution(self):
        """
        This method checks the minute_resolution attribute and corrects it into one of the 3 options (5, 15,
        30 minutes).

        Returns
        -------
        None
        """
        # in case someone is an idiot and does not put in a proper resolution
        if not isinstance(self.minute_resolution, int):
            try:
                self.minute_resolution = int(self.minute_resolution)
            except ValueError:
                self.minute_resolution = 30

        if self.minute_resolution > 30:
            self.minute_resolution = 30
        elif self.minute_resolution < 5:
            self.minute_resolution = 5
        elif (self.minute_resolution < 30) and (self.minute_resolution > 5):
            self.minute_resolution = 15

    def increase_res(self, making_pattern=False):
        """
        This method increases the resolution of the schedule.
        Parameters
        ----------
        making_pattern : bool
            Whether a driving pattern array for use in the simulation is being derived from schedule (see
            create_pattern class method).
        Returns
        -------
        new_schedule : DataFrame
            A new updated schedule with new resolution.
        """
        # call this function BEFORE you start adding events

        miles_col = ['Monday Miles', 'Tuesday Miles', 'Wednesday Miles', 'Thursday Miles', 'Friday Miles',
                     'Saturday Miles', 'Sunday Miles', 'Holiday Miles']

        if making_pattern:
            step_num = int(self.minute_resolution / 5)
        else:
            step_num = int(30 / self.minute_resolution)

        new_schedule = pd.DataFrame(columns=self.schedule.columns)  # create new empty frame in which to fill rows
        for index, row in self.schedule.iterrows():
            new_row = row.copy()
            base_min = row['Time'].minute
            for step in range(0, step_num):
                new_row['Time'] = new_row['Time'].replace(minute=(base_min + step * self.minute_resolution) % 60)
                if making_pattern and (step != 0):
                    new_row[miles_col] = 0
                new_schedule.loc[len(new_schedule), :] = new_row
        if making_pattern:
            return new_schedule
        else:
            self.schedule = new_schedule
            return None

    def get_event_list(self):
        """
        This method returns a list of the names of all the DrivingEvent objects in the list. For the actual objects
        themselves, call the event_list attribute.

        Returns
        -------
        list
            A list of the names of the DrivingEvents contained in the schedule.
        """
        return [event.name for event in self.event_list]

    def add_event(self, new_event: DrivingEvent):
        """
        This method adds a DrivingEvent to the schedule.

        Parameters
        ----------
        new_event : DrivingEvent
            A DrivingEvent to be added to the schedule.
        Returns
        -------
        None

        """
        can_add = True  # Boolean which controls whether we add event by default (assume true initially)

        # check if events have already been added, if so we check for conflicts
        if (len(self.event_list) != 0) and (new_event.name not in self.get_event_list()):
            for event in self.event_list:
                if event.check_conflict(new_event):
                    can_add = False

        if can_add:
            si = self.schedule.index[self.schedule['Time'] == new_event.start_time][0]
            ei = self.schedule.index[self.schedule['Time'] == new_event.end_time][0]

            for key in new_event.days.keys():
                if new_event.days[key]:  # boolean if event occurs on given day or not. We iterate through the week
                    self.schedule.loc[si:ei, key] = 0
                    self.schedule.loc[si, key + ' Miles'] = new_event.miles_driven

    def remove_event(self, bad_event: DrivingEvent):
        """
        This method removes an event from the DrivingSchedule.

        Parameters
        ----------
        bad_event : DrivingEvent
            Event to be removed.

        Returns
        -------
        None
        """
        if bad_event.name in self.get_event_list():
            si = self.schedule.index[self.schedule['Time'] == bad_event.start_time][0]
            ei = self.schedule.index[self.schedule['Time'] == bad_event.end_time][0]

            for key in bad_event.days.keys():
                if bad_event.days[key]:  # boolean if event occurs on given day or not. We iterate through the week
                    self.schedule.loc[si:ei, key] = 1
                    self.schedule.loc[si, key + ' Miles'] = 0

    def create_pattern(self, year=2018, start_day=1, days_to_compute=365):
        """
        This method returns a driving pattern array for use in the simulation.
        Parameters
        ----------
        year : int
            Year of the simulation.
        start_day : int
            Day of the year the simulation starts.
        days_to_compute : int
            Number of days in the simulation.

        Returns
        -------
        driving_pattern : ndarray
            An N x 3 array, where N is the number of simulation steps. Rows have the format step, EV presence (1 or 0),
            and miles driven.
        """
        day_dict = {'1': 'Monday', '2': 'Tuesday', '3': 'Wednesday', '4': 'Thursday', '5': 'Friday', '6': 'Saturday',
                    '7': 'Sunday', '8': 'Holiday'}

        driving_pattern = np.empty((0, 3))
        dow = tm.get_start_day_of_week(year=year, simu_start_day=start_day)[0]  # day of week in number form
        end_day = start_day + days_to_compute - 1

        step_frame = self.increase_res(making_pattern=True)

        for d in range(start_day, end_day + 1):
            day_of_week = day_dict[str(dow)]  # day of week in string form
            s = (d - 1) * 12 * 24
            e = d * 12 * 24 - 1
            steps = np.array(range(s, e + 1)).reshape((-1, 1))
            from_frame = step_frame.loc[:, [day_of_week, day_of_week + ' Miles']].to_numpy()
            to_add = np.hstack((steps, from_frame))
            driving_pattern = np.vstack((driving_pattern, to_add))
            dow += 1
            if dow == 8:
                dow = 1

        return driving_pattern