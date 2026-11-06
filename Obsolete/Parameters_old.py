import os.path
import numpy as np
import pandas as pd
import TimeManage as tm

default_efficiencies_file = 'Model Data/efficiencies.xlsx'


class Operation:  # Contains operation variables pertaining to how the simulation runs

    def __init__(self, efficiency_file=default_efficiencies_file, do_dcfc=False, ev_discharge_limit=.5,
                 ev_as_source=True, track_costs_of_use=True, hes_optimization='perfect', hes_cover_mid=True,
                 simu_name='insert_name_here', simu_id=1):
        self.efficiency_file = efficiency_file
        self.do_dcfc = do_dcfc
        self.ev_discharge_limit = ev_discharge_limit  # min soc at which EV is allowed to discharge to house
        self.ev_as_source = ev_as_source & (ev_discharge_limit != 1)  # allow EV to discharge at all besides driving
        self.efficiencies = self.load_efficiencies()
        self.track_costs_of_use = track_costs_of_use
        self.hes_optimization = hes_optimization  # possible values ('perfect', 'previous day', 'previous days', 'none')
        self.hes_cover_mid = hes_cover_mid
        self.ev_throughput = 12  # kW that ev can put towards house. In practice, this is limited by inverter
        self.hes_buffer = .1  # buffer to hes optimization (extra x%)
        self.net_meter_scheme = 'Basic'  # can be 'Basic', 'One-to-One', 'Flat', or 'Tariff'
        self.avoided_rate = .03  # wholesale energy rate, will be unique to each state. Flat for now.
        self.net_meter_account_freq = 'monthly'  # frequency at which utility settles net meter balance
        self.simu_name = simu_name  # name by which simulation is referred
        self.simu_id = simu_id
        self.cost_of_gas = 3.803
        # perfect: prerun the coverage periods with no HES and determine the amount of grid out
        # previous day: utilize difference between pv and house load on previous day
        # previous days: utilize average difference between pv and house loads on previous days

    def load_efficiencies(self):
        return pd.read_excel(self.efficiency_file, index_col=None, usecols='B:G').to_numpy()

    # def get_calendar(self):  # get/create calendar for simulation
    #     # first check if calendar already exists
    #     cal_file = str(self.year) + '_' + str(self.timestep) + 'min.csv'
    #     if os.path.exists('Model Data/Calendars/' + cal_file):
    #         cal = pd.read_csv('Model Data/Calendars/' + cal_file).to_numpy()
    #     else:


class TimeKeep:  # class pertaining to all variables dealing with time

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
            start_date = pd.to_datetime('1/1/' + str(self.year)) + pd.Timedelta(str(starting_day-1) + 'days')
            end_date = start_date + pd.Timedelta(str(simu_days) + 'days')

        self.simu_days = (end_date-start_date).days  # number of days to simulate
        self.num_steps = int(self.simu_days * 24 * (60 / timestep))
        if year % 4 == 0:  # if year is leap year, then months starting days change
            # days on which month changes
            self.month_switch = np.array([1, 32, 60, 91, 121, 152, 182, 213, 244, 274, 305, 335], dtype=int)
        else:
            self.month_switch = np.array([1, 32, 61, 92, 122, 153, 183, 214, 245, 275, 306, 336], dtype=int)
        self.step = 1
        self.starting_day = start_date.day_of_year  # numbered day of year from which to start simulation
        self.ending_day = end_date.day_of_year  # numbered day of year on which to end simulation
        self.current_day = int(starting_day)  # current day within simulation
        self.current_month = start_date.month  # current month within simulation
        self.current_hour = int(0)  # current hour within simulation
        self.day_start_step = int((starting_day - 1) * 24 * 60 / timestep + 1)  # step on which current day starts
        self.day_end_step = self.day_start_step + 24 * 60 / timestep - 1  # step on which current day ends
        self.hour_start_step = (starting_day - 1) * 24 * 60 / timestep + 1  # step on which current hour starts
        self.hour_end_step = self.hour_start_step + 60 / timestep - 1  # step on which current hour ends
        self.simu_start_step = int(self.day_start_step)  # step on which simulation starts
        self.simu_end_step = int(self.ending_day * 24 * 60 / timestep)  # step on which simulation ends
        self.calendar = tm.create_calendar(self.year, self.timestep)
        self.step = self.simu_start_step
        self.index = self.simu_start_step - 1  # index for full_year data (solar, load, etc)
        self.e_index = 0  # index for energy flows, cou's, and soc's (length of sim, not necessarily full year)

    def increment_step(self):
        self.step += 1
        self.e_index += 1
        self.index += 1

    def update_day(self):  # update the starting and ending steps of the day
        self.day_start_step += 24 * 60 / self.timestep
        self.day_end_step += 24 * 60 / self.timestep
        self.current_day += 1

    def update_hour(self):  # update the starting and ending steps of the hour
        self.hour_start_step += 60 / self.timestep
        self.hour_end_step += 60 / self.timestep
        self.current_hour = (self.current_hour + 1) % 24

    def update_month(self):  # update the current month
        self.current_month = (self.current_month + 1) % 12


class Tariff:  # contains tariff data for specific data sheet
    def __init__(self, name, utility, monthly_charge, minimum_charge, periods_energy, weekday_schedule,
                 weekend_schedule, periods_demand, weekday_schedule_power, weekend_schedule_power, is_tou, is_tiered,
                 is_demand):
        self.name = name  # name or designation of the actual tariff
        self.utility = utility  # name of the utility
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
        if self.is_tou:
            self.unique_tou_rates = np.unique(np.append(self.weekday_rates, self.weekend_rates))
        else:
            self.unique_tou_rates = []

        if self.is_tiered:
            self.max_tiers = len(max(self.periods_energy, key=len))
        else:
            self.max_tiers = 0
        self.end = 0  # ending step of calendar
        self.is_currently_off = False
        self.is_currently_on = False
        self.is_currently_mid = False
        self.next_off = 0  # start of next off period
        self.end_of_current = 0  # end of current period

    # this converts period representation of week_day_schedule and weekend schedule to rate. In simpler terms it
    # replaces the 0's, 1's, etc that represent the periods with the actual rates therein.
    def create_rates(self):
        period_num = len(self.periods_energy)
        rates = np.array([per[0][1] for per in self.periods_energy])
        weekday_rates = self.weekday_schedule.astype(np.float)
        weekend_rates = self.weekend_schedule.astype(np.float)
        for i in range(period_num):
            weekend_rates[weekend_rates == (i + 1)] = rates[i]
            weekday_rates[weekday_rates == (i + 1)] = rates[i]
        return weekday_rates, weekend_rates

    def create_tou_schedule(self, calendar=np.ndarray):
        num = calendar.shape[0]
        tou = np.zeros((num, 2))
        pdow = 8  # previous day of week (if current is not equal we assess new rates for peak/off-peak
        for i in range(num):
            mon = int(calendar[i, 2])  # extract month
            hr = calendar[i, 4]  # extract hour
            dow = calendar[i, 1]  # extract day of week

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

    def get_tou_rate(self, step: int):  # return tou rate and peak value (1=onpeak, .5 = midpeak, 0 = offpeak)
        index = step - 1
        return self.tou_schedule[index, 0], self.tou_schedule[index, 1]

    def is_off_peak(self, step: int):
        index = step - 1
        # print(type(step))
        # print(type(index))
        return self.tou_schedule[index, 1] == 0

    def is_on_peak(self, step: int):
        index = step - 1
        return self.tou_schedule[index, 1] == 1

    def is_mid_peak(self, step: int):
        index = step - 1
        return self.tou_schedule[index, 1] == .5

    def get_end_of_period(self, step: int, update=False):  # returns timestep at which current period ends
        index = step - 1
        peak_num = self.tou_schedule[index, 1]
        try:
            eop = np.where(self.tou_schedule[index:index + 24 * 12, 1] != peak_num)[0][0] + index
        except IndexError:
            eop = self.end

        if update:
            self.end_of_current = eop
        return eop

    def get_next_off_peak(self, step: int, update=False):  # returns step of next off-peak
        index = step - 1
        try:
            if self.is_off_peak(step):
                end_of_off = np.where(self.tou_schedule[index:, 1] != 0)[0][0] + index
                start = np.where(self.tou_schedule[end_of_off:, 1] == 0)[0][0] + end_of_off + 1
            else:
                start = np.where(self.tou_schedule[index:, 1] == 0)[0][0] + index + 1
        except IndexError:
            start = self.end + 1

        if update:
            self.next_off = start
        return start

    def get_coverage_steps(self, step: int, operation: Operation):
        start = self.get_end_of_period(step) + 1
        eoc = self.get_next_off_peak(start) - 1

        if operation.hes_cover_mid:
            steps = np.linspace(start, eoc, eoc - start + 1)
        else:
            steps = np.where(self.tou_schedule[(start - 1):eoc == 1])[0] + start

        return steps.astype(int)

    def get_daily_rates(self, day, timestep=5):
        s = int((day - 1) * 24 * 60 / timestep)
        e = int(day * 24 * 60 / timestep - 1)
        rates = np.unique(self.tou_schedule[s:(e + 1), 0])
        return rates

    def update_status(self, step: int):
        self.is_currently_on = self.is_on_peak(step=step)
        self.is_currently_off = self.is_off_peak(step=step)
        self.is_currently_mid = self.is_mid_peak(step=step)

    def return_periods(self, start_step, end_step):
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


class City:
    def __init__(self, name, state, state_full, county, zipcode, latitude, longitude, time_zone, carbon_intensity,
                 tax_rate, utilities, eias, follows_dst=True, matched_city=None, matched_state=None):
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
        self.tax_rate = tax_rate  # combined tax rate for city
        self.utilities = utilities  # list of utilities in city
        self.eias = eias  # list of eia codes for utilities in city
        self.follows_dst = follows_dst  # whether city follows Daylight Saving Time (DST)


class DrivingEvent:
    def __init__(self, name: str, start_time: pd.Timestamp, end_time: pd.Timestamp, miles_driven: float, days: dict):
        self.name = name
        self.start_time = start_time
        self.end_time = end_time
        self.miles_driven = miles_driven
        self.days = days

    def check_conflict(self, event):
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
        day_string = ''
        if self.days['Monday']: day_string += 'M'
        if self.days['Tuesday']: day_string += 'T'
        if self.days['Wednesday']: day_string += 'W'
        if self.days['Thursday']: day_string += 'Th'
        if self.days['Friday']: day_string += 'F'
        if self.days['Saturday']: day_string += 'Sa'
        if self.days['Sun']: day_string += 'Sun'
        return day_string

    def duration_string(self):
        dur = str(self.start_time.time())[0:-3] + 'to' + str(self.end_time.time())[0:-3]
        return dur

    def transcribe_event(self):
        transcription = self.name + '_' + self.day_string() + '_' + self.duration_string() + '_' \
                        + str(self.miles_driven) + 'mi'
        return transcription


class DrivingSchedule:
    def __init__(self, minute_resolution=30):
        # attributes are event list and the schedule
        self.minute_resolution = minute_resolution
        self.event_list = []
        self.schedule = pd.read_csv('DrivingPatterns/empty_pattern.csv', parse_dates=['Time'])
        self.check_resolution()
        if self.minute_resolution < 30:
            self.increase_res()

    def check_resolution(self):
        # in case someone is an idiot and does not put in a proper resolution
        if type(self.minute_resolution) != int:
            try:
                self.minute_resolution = int(self.minute_resolution)
            except ValueError:
                self.minute_resolution = 30

        if self.minute_resolution > 30:
            self.minute_resolution = 30
        elif self.minute_resolution < 5:
            self.minute_resolution = 5
        elif (self.minute_resolution < 30) & (self.minute_resolution > 5):
            self.minute_resolution = 15

    def increase_res(self, making_pattern=False):
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
                if making_pattern & (step != 0):
                    new_row[miles_col] = 0
                new_schedule.loc[len(new_schedule), :] = new_row
        if making_pattern:
            return new_schedule
        else:
            self.schedule = new_schedule
            return None

    def get_event_list(self):
        return [event.name for event in self.event_list]

    def add_event(self, new_event: DrivingEvent):
        can_add = True  # Boolean which controls whether we add event by default (assume true initially)

        # check if events have already been added, if so we check for conflicts
        if (len(self.event_list) != 0) & (new_event.name not in self.get_event_list()):
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

        if bad_event.name in self.get_event_list():
            si = self.schedule.index[self.schedule['Time'] == bad_event.start_time][0]
            ei = self.schedule.index[self.schedule['Time'] == bad_event.end_time][0]

            for key in bad_event.days.keys():
                if bad_event.days[key]:  # boolean if event occurs on given day or not. We iterate through the week
                    self.schedule.loc[si:ei, key] = 1
                    self.schedule.loc[si, key + ' Miles'] = 0

    def create_pattern(self, year=2018, start_day=1, days_to_compute=365):

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
