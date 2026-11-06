"""
This module was created to contain methods related to time and keeping track of it for the simulation. Some have been
deprecated in favor of the pandas.Timestamp functionality.

Methods
-------
get_start_day_of_week(get_start_day_of_week(year=2018, simu_start_day=1)
    Get the day of the week (ie, Monday) of the starting day of the simulation, given the day of year (out of 365)
    and year.
create_calendar(year=2018, timestep=5)
    Creates calendar in form of numpy array for calendar year, with columns [dow dom month doy hr min]. This method
    is deprecated in favor of create_calendar_from_timestamp method.
steps_between_dates(start: Timestamp, end: Timestamp, timestep=5)
    This method returns the number of timesteps between two pandas Timestamps, given the timestep resolution.
create_calendar_from_datetime(start=pd.to_datetime('1/1/2018'), end=None, steps=None, timestep=5)
    This method creates a calendar represented by a (N x 6) numpy  between the timestamps provided (start and end). The
    column values are : [dow dom month doy hr min]. Where dow is day of week (ie, 1 = monday), doy is day of year (
    out of 365/6), and dom is day of month (out of 28/30/31). N is the number of timesteps in the year,
    based on the timestep parameter. Should the end parameter steps parameter be unfilled, then a calendar array will
    be made for the calendar year given by the start parameter (ending on 12/31 23:55).
timestep_to_index(start_step: int, step: int):
    This method converts a timestep to an index by simply subtracting the starting timestep. This method is simple
    and unused and has therefore been deprecated.
month_indices_from_calendar(calendar: ndarray)
    This method returns the starting and ending indices of each month contained within the calendar numpy array
    provided. Should a calendar start or end in the middle of a month then the starting and ending index of that
    month will be zero or the length of the calendar minus 1 respectively.
calendar_row_to_timestamp(row: np.ndarray):
    This method, given a row from a calendar array (see create_calendar_from_datetime method), will return the
    corresponding pandas Timestamp.
calendar_row_to_date_string(row: np.ndarray):
    This method returns a date in the form of string corresponding to a calendar row provided.
timestamp_to_date_string(time: pd.Timestamp):
    This method extracts the date only (excluding time) of a pandas Timestamp in the form of a string.
"""

import numpy as np
import os
import math as m
import pandas as pd
from pandas import Timestamp
from numpy import ndarray


def get_start_day_of_week(year=2018, simu_start_day=1):
    """
    This method returns the starting day of the year and the starting day of the week for the simulation. If the
    simulation starts on Jan 1, then these values will be the same. Note that Monday = 1, etc.

    Parameters
    ----------
    year : int
        Year in question
    simu_start_day
        Day of the year (out of 365) on which the simulation starts.

    Returns
    -------
    year_start : int
        Day of the week that provided year starts (Monday = 1, etc.).
    starting_day : int
        Day of week that simulation starts on (Monday = 1, etc.)
    """
    # Returns starting day of week of first day of simulation
    # Note: Monday=1
    master = {'2018': 1, '2019': 2, '2020': 3, '2021': 5, '2022': 6, '2023': 7}
    base_year = 2020
    if str(year) not in master.keys():
        diff = year - base_year
        min_yr = min(year, base_year)
        max_yr = max(year, base_year)
        day_add = 0
        for yr in range(min_yr, max_yr):
            day_add += 1 + (yr % 4 == 0)
        print(day_add)
        if diff > 0:
            year_start = (master[str(base_year)] + day_add) % 7  # day of the week the year starts on
        else:
            year_start = (8 - master[str(base_year)] + day_add) % 7
            if year_start == 0:
                year_start = 7
            year_start = 8 - year_start

    else:
        year_start = master[str(year)]

    starting_day = (year_start + simu_start_day - 1) % 7
    if starting_day == 0:
        starting_day = 7

    return year_start, starting_day


def create_calendar(year=2018, timestep=5) -> ndarray:
    """
    This method creates a calendar represented by a (N x 6) numpy array. The column values are : [dow dom month doy hr
    min]. Where dow is day of week (ie, 1 = monday), doy is day of year (out of 365/6), and dom is day of month (out of
    28/30/31). N is the number of timesteps in the year, based on the timestep parameter. NOTE: This method is
    deprecated at this time in favor of the create_calendar_from_datetime method.

    Parameters
    ----------
    year : int, optional
        The year for which calendar array is to be created. Default is 2018.
    timestep : int, optional
        Duration of each timestep of simulation in minutes. Default is 5.

    Returns
    -------

    """

    filename = 'Model Data/Calendars/' + str(year) + '_' + str(timestep) + 'min.csv'
    if os.path.exists(filename):
        save_file = False
        calendar = pd.read_csv(filename, index_col=False).to_numpy()
    else:
        save_file = True
        month_num_days = {'1': 31, '2': 28, '3': 31, '4': 30, '5': 31, '6': 30, '7': 31, '8': 31, '9': 30, '10': 31,
                          '11': 30, '12': 31}
        year_sum = 365
        if year % 4 == 0:  # correct for leap year
            month_num_days['2'] += 1
            year_sum += 1
        start_dow = get_start_day_of_week(year=year)[0]  # get starting day of week

        calendar = np.zeros((year_sum * 24 * int((60 / timestep)), 6), dtype=int)

        dow = start_dow
        dom = 1
        minute = 0
        hr = 0
        doy = 1
        month = 1
        day_lim = month_num_days[str(month)]  # day limit for given month
        for i in range(calendar.shape[0]):
            # set row values
            calendar[i, 0] = dow
            calendar[i, 1] = dom
            calendar[i, 2] = month
            calendar[i, 3] = doy
            calendar[i, 4] = hr
            calendar[i, 5] = minute

            minute += timestep
            if minute == 60:  # hour is up
                minute = 0  # reset to zero
                hr += 1  # increment hour

            if hr == 24:  # day is up
                dow += 1  # increment day of week
                dom += 1  # increment day of month
                doy += 1  # increment day of year
                hr = 0

            if dow == 8:  # week is up
                dow = 1  # set day of week back to monday (week ends on sunday)

            if dom > day_lim:  # month is up
                month += 1  # increment month
                dom = 1  # set day of month back to 1
                if month < 13:
                    day_lim = month_num_days[str(month)]
    if save_file:
        filename = 'Model Data/Calendars/' + str(year) + '_' + str(timestep) + 'min.csv'
        column_list = ['Day of Week', 'Day of Month', 'Month', 'Day of Year', 'Hour', 'Minute']
        pd.DataFrame(data=calendar, columns=column_list).to_csv(filename, index=False)
    return calendar


def steps_between_dates(start: Timestamp, end: Timestamp, timestep=5) -> int:
    """
    This method returns the number of timesteps between two pandas Timestamps, given the timestep resolution.

    Parameters
    ----------
    start : Timestamp
        The starting Timestamp of the interval desired.
    end : Timestamp
        The ending Timestamp of the interval desired
    timestep : int, optional
        Duration of each timestep in minutes. Default is 5.

    Returns
    -------
    steps : int
        Number of timesteps between the provided Timestamps.

    """
    td = end - start
    step_per_hour = int(60 / timestep)
    steps = (td.days * 24 * step_per_hour) + (td.components.hours * step_per_hour) + m.floor(
        td.components.minutes / timestep) + 1
    return steps


def create_calendar_from_datetime(start=pd.to_datetime('1/1/2018'), end=None, steps=None, timestep=5) -> ndarray:
    """
    This method creates a calendar represented by a (N x 6) numpy  between the timestamps provided (start and end). The
    column values are : [dow dom month doy hr min]. Where dow is day of week (ie, 1 = monday), doy is day of year (
    out of 365/6), and dom is day of month (out of 28/30/31). N is the number of timesteps in the year,
    based on the timestep parameter. Should the end parameter steps parameter be unfilled, then a calendar array will
    be made for the calendar year given by the start parameter (ending on 12/31 23:55).

    Parameters
    ----------
    start : Timestamp
        The starting date and time (Timestamp) for the calendar.
    end : Timestamp, optional
        The ending date and time (Timestamp) for the calendar. Default is None
    steps : int
        The number of timesteps desired for the simulation. Supersedes "end" if both are provided. Default is None.
    timestep : int
        Duration of each timestep in minutes. Default is 5.

    Returns
    -------
    calendar: ndarray
        A (N x 6) numpy array where N is the number of timesteps in the simulation and the columns have the following
        form:  [day-of-week day-of-month month day-of-year hour minute]
    """

    if (steps is None) and (end is None):
        end = pd.to_datetime('12/31/' + str(start.year) + ' 23:55')
        steps = steps_between_dates(start=start, end=end, timestep=timestep)
    elif (steps is None) and (end is not None):
        end = end.replace(hour=23, minute=55)
        steps = steps_between_dates(start=start, end=end, timestep=timestep)

    calendar = np.zeros((steps, 7)).astype(int)
    date = start + pd.Timedelta('0min')
    for i in range(steps):
        calendar[i, :] = np.array([date.day_of_week + 1, date.day, date.month, date.day_of_year, date.hour,
                                   date.minute, date.year], dtype=int)
        date += pd.Timedelta(str(timestep) + 'min')

    return calendar


def timestep_to_index(start_step: int, step: int):
    """
    This method converts a timestep to an index by simply subtracting the starting timestep. This method is simple
    and unused and has therefore been deprecated.

    Parameters
    ----------
    start_step : int
        starting timestep of simulation
    step : int
        Timestep for which index is desired
    Returns
    -------
    index : int
        index of timestep in question.
    """

    index = (step - start_step)
    return index


def month_indices_from_calendar(calendar: ndarray) -> ndarray:
    """
    This method returns the starting and ending indices of each month contained within the calendar numpy array
    provided. Should a calendar start or end in the middle of a month then the starting and ending index of that
    month will be zero or the length of the calendar minus 1 respectively.

    Parameters
    ----------
    calendar: ndarray
        A (N x 6) numpy array where N is the number of timesteps in the simulation and the columns have the following
        form:  [day-of-week day-of-month month day-of-year hour minute]

    Returns
    -------
    month_inds : ndarray
        A M x 2 numpy array with M being the number of months contained in the calendar array provided the 2 columns
        being the starting and ending index of each month respectively.
    """

    # this function returns the starting and ending indices of months between in a given calendar array
    vals = calendar[:, 2]  # original month values from calendar
    shift = np.append(vals[0], vals[0:-1])  # month values shifted by one to see where value changes
    start_inds = np.where(vals != shift)[0]  # where value changes, new month starts
    end_inds = start_inds - 1  # ends occur one index before starts
    start_inds = np.append(0, start_inds)  # add 0 to front to account for initial index
    end_inds = np.append(end_inds, len(vals) - 1)
    month_inds = np.hstack((start_inds.reshape(start_inds.shape[0], 1), end_inds.reshape(end_inds.shape[0], 1)))
    return month_inds


def calendar_row_to_timestamp(row: np.ndarray):
    """
    This method, given a row from a calendar array (see create_calendar_from_datetime method), will return the
    corresponding pandas Timestamp.
    Parameters
    ----------
    row : ndarray
        A calendar row (1 x 6 numpy array) of form [day-of-week day-of-month month day-of-year hour minute].

    Returns
    -------
    Timestamp
        A pandas Timestamp corresponding to the calendar row provided (ie, 1/1/2020 14:55).
    """
    return pd.Timestamp(str(row[2]) + '/' + str(row[1]) + '/' + str(row[6]))


def calendar_row_to_date_string(row: np.ndarray):
    """
    This method returns a date in the form of string corresponding to a calendar row provided.

    Parameters
    ----------
    row : ndarray
        A calendar row (1 x 6 numpy array) of form [day-of-week day-of-month month day-of-year hour minute].

    Returns
    -------
    str
        A string of the date corresponding to the row provided (ie, "12/10/2019").
    """
    return str(row[2]) + '/' + str(row[1]) + '/' + str(row[6])


def timestamp_to_date_string(time: pd.Timestamp):
    """
    This method extracts the date only (excluding time) of a pandas Timestamp in the form of a string.
    Parameters
    ----------
    time: Timestamp
        A pandas Timestamp for which we wish to extract the date as a string.

    Returns
    -------
    str
        Calendar date of provided Timestamp in form of string.
    """
    return str(time).split()[0]
