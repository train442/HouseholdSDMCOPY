"""
This module pertains to data post-processing, including data analytics and graphing.
"""
import os
import openpyxl
import pandas as pd
import Parameters as pm
import Components as cp
import Setup as sp
import Simulation as sm
from Parameters import TimeKeep, Tariff
from Components import House, PV
import numpy as np
from numpy import ndarray
from matplotlib import pyplot as plt
from matplotlib.colors import ListedColormap
from typing import Callable


def rg_slider(value, val_min, val_max) -> tuple:
    # if type(value) not in [int, float, np.float]:
    #     value = val_min
    if value < val_min:
        value = val_min
    elif value > val_max:
        value = val_max

    val_split = (val_min + val_max) / 2

    if value < val_split:
        rv = (value - val_min) / (val_split - val_min)
        gv = 1
    elif value > val_split:
        rv = 1
        gv = 1 - ((value - val_split) / (val_max - val_split))
    else:
        rv = 1
        gv = 1

    rg_val = (rv, gv, 0)
    return rg_val


def rgb_slider(value, val_min, val_max):
    if value < val_min:
        value = val_min
    elif value > val_max:
        value = val_max

    delta = (val_max - val_min) / 4
    val_spl1 = val_min + delta
    val_spl2 = val_spl1 + delta
    val_spl3 = val_spl2 + delta

    if value < val_spl1:
        bv = 1
        gv = (value - val_min) / (val_spl1 - val_min)
        rv = 0
    elif value < val_spl2:
        bv = 1 - ((value - val_spl1) / (val_spl2 - val_spl1))
        gv = 1
        rv = 0
    elif value < val_spl3:
        bv = 0
        gv = 1
        rv = (value - val_spl2) / (val_spl3 - val_spl2)
    else:
        bv = 0
        gv = 1 - (value - val_spl3) / (val_max - val_spl3)
        rv = 1
    return (rv, gv, bv)


def get_index_in_calendar(calendar: ndarray, month: int = 1, day: int = 0, hour: int = 0, minute: int = 0) -> int:
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

    ind = np.where((calendar[:, 2] == month) &
                   (calendar[:, 1] == day) &
                   (calendar[:, 4] == hour) &
                   (calendar[:, 5] == minute))[0][0]

    return int(ind)


def hour_breakdown(timekeep: TimeKeep, values: ndarray, season: str = None, weekday_only=False,
                   start_date: (ndarray, list, tuple) = None, end_date: (ndarray, list, tuple) = None,
                   do_average=False) -> ndarray:
    def check_date(date) -> list:
        if type(date) not in [list, tuple, ndarray]:
            date = None
        return date

    if start_date is not None:
        start_date = check_date(start_date)
    if end_date is not None:
        end_date = check_date(end_date)

    if (start_date is not None) and (end_date is not None):
        s1 = get_index_in_calendar(calendar=timekeep.calendar, month=start_date[0], day=start_date[1])
        e1 = get_index_in_calendar(calendar=timekeep.calendar, month=end_date[0], day=end_date[1])
        calendar = timekeep.calendar[s1:e1, :]
        values = values[s1:e1]

    elif type(season) is str:
        if season.lower() in ['winter']:
            e1 = get_index_in_calendar(calendar=timekeep.calendar, month=3, day=20)
            s2 = get_index_in_calendar(calendar=timekeep.calendar, month=12, day=21)
            calendar = np.vstack((timekeep.calendar[:e1, :], timekeep.calendar[s2:, :]))
            values = np.vstack((values[:e1], values[s2:]))
        elif season.lower() in ['spring']:
            s1 = get_index_in_calendar(calendar=timekeep.calendar, month=3, day=20)
            e1 = get_index_in_calendar(calendar=timekeep.calendar, month=6, day=21)
            calendar = timekeep.calendar[s1:e1, :]
            values = values[s1:e1]
        elif season.lower() in ['summer']:
            s1 = get_index_in_calendar(calendar=timekeep.calendar, month=6, day=21)
            e1 = get_index_in_calendar(calendar=timekeep.calendar, month=9, day=20)
            calendar = timekeep.calendar[s1:e1, :]
            values = values[s1:e1]
        elif season.lower() in ['fall', 'autumn']:
            s1 = get_index_in_calendar(calendar=timekeep.calendar, month=9, day=20)
            e1 = get_index_in_calendar(calendar=timekeep.calendar, month=9, day=20)
            calendar = timekeep.calendar[s1:e1, :]
            values = values[s1:e1]
        else:
            calendar = timekeep.calendar
    else:
        calendar = timekeep.calendar

    hr_arr = np.zeros((24, 3))
    hr_arr[:, 0] = np.linspace(start=0, stop=23, num=24)
    i = 0

    for ts in calendar:
        hr = ts[4]
        wd = ts[0]
        if (not weekday_only) or (weekday_only and (wd < 6)):
            hr_arr[hr, 1] += values[i]
            hr_arr[hr, 2] += 1

        i += 1

    if do_average:
        hr_arr[:, 1] = np.divide(hr_arr[:, 1], hr_arr[:, 2])

    return hr_arr[:, 0:2]


def load_hr_breakdown(house: House, timekeep: TimeKeep, season: str = None, weekday_only=False,
                      start_date: (ndarray, list, tuple) = None, end_date: (ndarray, list, tuple) = None) -> ndarray:
    hr_arr = hour_breakdown(timekeep=timekeep, values=house.load_profile / 12, season=season,
                            weekday_only=weekday_only, start_date=start_date, end_date=end_date)
    return hr_arr


def solar_hr_breakdown(pv: PV, timekeep: TimeKeep, season: str = None,
                       start_date: (ndarray, list, tuple) = None, end_date: (ndarray, list, tuple) = None) -> ndarray:
    hr_arr = hour_breakdown(timekeep=timekeep, values=pv.ghi / 12000, season=season,
                            start_date=start_date, end_date=end_date)
    return hr_arr


def tariff_hr_breakdown(tariff: Tariff, timekeep: TimeKeep, season: str = None, weekday_only=True,
                        start_date: (ndarray, list, tuple) = None, end_date: (ndarray, list, tuple) = None,
                        do_average=True) -> ndarray:
    hr_arr = hour_breakdown(timekeep=timekeep, values=tariff.tou_schedule[:, 0], season=season,
                            weekday_only=weekday_only, start_date=start_date, end_date=end_date, do_average=do_average)

    return hr_arr


def plot_hr_breakdown(hr_arr: ndarray, y_label: str = None, title: str = None):
    fig, ax = plt.subplots()

    ax.bar(hr_arr[:, 0], hr_arr[:, 1])
    if type(y_label) is str:
        ax.set_ylabel(y_label)

    if type(title) is str:
        ax.set_title(title)

    plt.show()


def by_cost_breakdown(tariff: Tariff, values: ndarray) -> ndarray:
    rate_arr = np.zeros((tariff.unique_tou_rates.shape[0], 2))
    rate_arr[:, 0] = tariff.unique_tou_rates

    for i in range(len(tariff.unique_tou_rates)):
        rate = rate_arr[i, 0]
        rate_arr[i, 1] = np.sum(values[np.where(tariff.tou_schedule[:, 0] == rate)])

    return rate_arr


def by_period_breakdown(tariff: Tariff, values: ndarray, cost_breakdown=True) -> ndarray:
    per_arr = np.empty((0, 4))
    periods = [0, .5, 1]
    for p in periods:
        if cost_breakdown:
            rates = np.unique(tariff.tou_schedule[np.where(tariff.tou_schedule[:, 1] == p), 0])
            for rate in rates:
                sub_total = np.sum(values[np.where((tariff.tou_schedule[:, 1] == p) &
                                                   (tariff.tou_schedule[:, 0] == rate))])
                to_add = [p, rate, sub_total, sub_total * rate]
                per_arr = np.vstack((per_arr, to_add))
        else:
            inds = np.where(tariff.tou_schedule[:, 1] == p)
            sub_values = values[inds]
            sub_total = np.sum(sub_values)  # total of values within period
            cost_total = np.sum(np.multiply(sub_values,
                                            tariff.tou_schedule[inds, 0]))
            to_add = np.array([p, np.nan, sub_total, cost_total])
            per_arr = np.vstack((per_arr, to_add))

    return per_arr


def plot_cost_breakdown(rate_arr: ndarray, y_label: str = None, title: str = None):
    """
    This method plots the subtotals of given values by the electricity rate at which they occur.
    Parameters
    ----------
    rate_arr
    y_label
    title

    Returns
    -------

    """
    fig, ax = plt.subplots()
    min_rate = np.min(rate_arr[:, 0])
    max_rate = np.max(rate_arr[:, 0])
    labels = [str(rate) for rate in rate_arr[:, 0]]
    colors = []
    for cost in rate_arr[:, 0]:
        colors.append(rgb_slider(value=cost, val_min=min_rate, val_max=max_rate))
    # colors = [rg_slider(value=cost, val_min=min_rate, val_max=max_rate) for cost in rate_arr[:, 0]]
    # ax.bar(x=np.linspace(start=0, stop=len(rate_arr[:,0]), num=len(rate_arr[:, 0])), height=rate_arr[:, 1],
    #        width=.05)
    ax.bar(x=labels, height=rate_arr[:, 1], color=colors)

    costs = np.round(np.multiply(rate_arr[:, 0], rate_arr[:, 1]), 2)

    rects = ax.patches

    if type(y_label) is str:
        ax.set_ylabel(y_label)

    if type(title) is str:
        ax.set_title(title)

    ax.set_xlabel('Rate ($/kWh)')

    for rect, total_cost in zip(rects, costs):
        height = rect.get_height()
        width = rect.get_width()
        x = rect.get_x()
        ax.text(x + width / 2, height / 2, f'$ {total_cost}', ha='center', va='center')

    plt.show()


def plot_per_breakdown(per_arr: ndarray, y_label: str = None, title: str = None):
    # test to see if per_arr is further broken down by rate (no nan) or simply off, mid, peak
    if np.isnan(per_arr[0, 1]):
        labels = ['off-peak', 'mid-peak', 'on-peak']
        colors = ['green', 'yellow', 'red']
    else:
        labels = []
        colors = []
        min_rate = np.min(per_arr[:, 1])
        max_rate = np.max(per_arr[:, 1])
        for row in per_arr:
            rate = row[1]
            if row[0] == 0:
                period = 'off-peak'
            elif row[0] == 1:
                period = 'on-peak'
            else:
                period = 'mid-peak'
            lab_str = f'{period}: \n $ {np.round(rate, 5)}/kWh'
            labels.append(lab_str)
            colors.append(rgb_slider(rate, min_rate, max_rate))

    fig, ax = plt.subplots()
    ax.bar(x=labels, height=per_arr[:, 2], color=colors)

    if type(y_label) is str:
        ax.set_ylabel(y_label)

    if type(title) is str:
        ax.set_title(title)

    ax.set_xlabel('Periods')

    rects = ax.patches
    for rect, total_cost in zip(rects, np.round(per_arr[:, 3], 2)):
        height = rect.get_height()
        width = rect.get_width()
        x = rect.get_x()
        ax.text(x + width / 2, height / 2, f'$ {total_cost}', ha='center', va='center')

    plt.show()


def plot_rates_by_month(month_arr: ndarray):
    unique_rates = np.unique(month_arr, axis=0)
    hours = np.linspace(start=0, stop=23, num=24).astype(int)
    mons = np.linspace(start=1, stop=12, num=12).astype(int)

    month_divs = [mons[[np.array_equal(month_row, unique_row) for month_row in month_arr]] for unique_row in
                  unique_rates]

    def month_divs_to_str(division: ndarray):
        months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
        tot_mon = len(division)
        mon_str = f'{months[division[0] - 1]} - '
        for i in range(tot_mon):
            if i != 0:
                if i == tot_mon - 1:  # reached end of division array
                    mon_str += f'{months[division[i] - 1]}'
                elif division[i] != division[i - 1] + 1:
                    mon_str += f'{months[division[i - 1] - 1]}, {months[division[i] - 1]} - '
        return mon_str

    month_strs = [month_divs_to_str(div) for div in month_divs]
    marks = ['.', 'x', 'o', 's']
    for rates, mark in zip(unique_rates, marks):
        plt.plot(hours, rates, marker=mark, linestyle='None')

    plt.legend(month_strs)
    plt.show()
    pass


def plot_rate_chart(month_arr: ndarray = None,
                    tariff: Tariff = None,
                    rate_type: str = 'weekday',
                    slider: Callable = None,
                    save_fig: bool = False,
                    save_path: str = None):
    """
    This method is meant to visualize the utility rates of the given utility.
    Parameters
    ----------
    month_arr
    tariff
    rate_type
    slider

    Returns
    -------

    """
    if tariff is not None:
        if rate_type == 'weekend':
            month_arr = np.round(tariff.weekend_rates, 3)
            rate_type = 'Weekend'
        else:
            month_arr = np.round(tariff.weekday_rates, 3)
            rate_type = 'Weekday'
        tit = f'{tariff.utility} - {tariff.name} {rate_type} Rates'
    elif month_arr is None:
        raise Exception('No input provided')

    else:
        tit = f'{rate_type.capitalize()} Rates'

    if slider is None:
        slider = rgb_slider

    rates = np.unique(month_arr)
    num_rates = len(rates)
    max_rate = np.round(np.max(month_arr), 3)
    min_rate = np.round(np.min(month_arr), 3)

    months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
    fig, ax = plt.subplots()

    ax.set_yticks(np.arange(len(months)), labels=months)
    newcolors = np.array([np.array(rgb_slider(value=val, val_min=0, val_max=1)) for val in np.linspace(0, 1, 256)])
    newcolors = np.hstack((newcolors, np.ones((256, 1)) * .9))
    newcmp = ListedColormap(newcolors)
    im = ax.imshow(month_arr, vmin=np.min(min_rate), vmax=max_rate, aspect='equal',
                   cmap=newcmp, extent=[0, 24, 11.5, -.5])
    ax.set_xlabel('Hour')
    ax.set_ylabel('Month')
    ax.set_xticks(np.arange(0, 24), minor=True)
    ax.set_yticks(np.arange(-.5, 11.5), minor=True)
    ax.grid(visible=True, which='minor', linestyle='--')
    ax.xaxis.grid(visible=True, which='major', linestyle='--')
    ax.set_title(tit)
    fixed_name = tariff.name.replace('/o', 'ithout')
    fixed_name = fixed_name.replace('/', 'ith')
    fixed_name = fixed_name.replace('.', '')
    fixed_name = fixed_name.replace(':', '')
    x = .95
    ymax = .7
    ymin = .1
    ystep = (ymax - ymin) / num_rates
    i = 0
    for rate in rates:
        rgb = newcmp((rate - min_rate) / (max_rate - min_rate))
        props = {'facecolor': rgb}
        ax.text(x, ymax - i * ystep, f'{rate} $/kWh', bbox=props, transform=plt.gcf().transFigure)
        i += 1

    if not save_fig:
        plt.show()
    else:
        fig.savefig(f'{save_path}/{tariff.utility}_{fixed_name}_{rate_type}Rates.png', bbox_inches='tight')


def make_pool_util_plots(pool_file: str):
    pool_frame = pd.read_csv(f'{pool_file}.csv')

    new_file_dir = f'Figures/UtilFigs/UtilFigs_{pool_file}'
    if not os.path.exists(new_file_dir):
        os.makedirs(new_file_dir)

    for index, row in pool_frame.iterrows():
        # Load necessary data files
        print(row['Reference City'], row['State'])
        util = sp.create_tariff(util_name=row['Utility'], tariff_name=row['Tariff'])
        plot_rate_chart(tariff=util, save_fig=True, save_path=new_file_dir)


def get_subdirs(path):
    subdirs = []
    for entry in os.scandir(path):
        if entry.is_dir():
            subdirs.append(entry.name)
    subdirs.sort(key=lambda x: int(x.split('_')[0][1:]))
    return subdirs


def analyze_set_optimum_HES_PV(collection_name: str, metric: str = None, loads: list[int] = None, by_loads=True):
    if len(collection_name.split('/')) == 1:
        collection_path = f'Outputs/{collection_name}'
    else:
        collection_path = collection_name
        collection_name = collection_name.split('/')[-1]
    new_path = f'Outputs/{collection_name}/{collection_name}_hes_pv_opt.xlsx'

    # if (metric is None) or (metric not in ['System Cost Efficiency', ])

    # Establish workbook and header cells
    master_wb = openpyxl.Workbook()
    master_sheet = master_wb.active
    master_sheet['A1'] = 'Inputs'
    master_sheet['D1'] = 'HES Only Results'
    master_sheet['H1'] = 'PV Only Results'
    master_sheet['L1'] = 'HES-PV-Combined Results'
    master_sheet.merge_cells('A1:C1')
    master_sheet.merge_cells('D1:G1')
    master_sheet.merge_cells('H1:K1')
    master_sheet.merge_cells('L1:P1')
    master_sheet['A2'] = 'City'
    master_sheet['B2'] = 'State'
    master_sheet['C2'] = 'House Load (kWh)'
    master_sheet['D2'] = 'Size (kWh)'
    master_sheet['E2'] = 'Cost ($)'
    master_sheet['F2'] = 'Savings ($)'
    master_sheet['G2'] = 'Cost Eff (%)'
    master_sheet['H2'] = 'Size (kW)'
    master_sheet['I2'] = 'Cost ($)'
    master_sheet['J2'] = 'Savings ($)'
    master_sheet['K2'] = 'Cost Eff (%)'
    master_sheet['L2'] = 'HES Size (kWh)'
    master_sheet['M2'] = 'PV Size (kW)'
    master_sheet['N2'] = 'Cost ($)'
    master_sheet['O2'] = 'Savings ($)'
    master_sheet['P2'] = 'Cost Eff (%)'

    i = 3
    for file_name in get_subdirs(path=collection_path):
        print(file_name)
        file_master = pd.read_csv(f'{collection_path}/{file_name}/{file_name}_summary.csv')
        cities = list(set(file_master['City'].to_list()))
        states = list(set(file_master['State'].to_list()))
        loads = np.unique(file_master['House Load'].to_numpy())
        file_master = file_master[file_master['EV Discharge Limit'] == 1]

        #add city and state to cells
        master_sheet.cell(row=i, column=1).value = cities[0]
        master_sheet.cell(row=i, column=2).value = states[0]
        master_sheet.merge_cells(start_row=i, end_row=i + 2, start_column=1, end_column=1)
        master_sheet.merge_cells(start_row=i, end_row=i + 2, start_column=2, end_column=2)

        for house_load in loads:
            red_frame = file_master[file_master['House Load'] == house_load]
            hes_only_frame = red_frame[red_frame['Solar Size (kW)'] == 0]
            pv_only_frame = red_frame[red_frame['HES Size'] == 0]

            both_max_row = red_frame.loc[red_frame['System Cost Efficiency'].idxmax()]
            hes_max_row = hes_only_frame.loc[hes_only_frame['System Cost Efficiency'].idxmax()]
            pv_max_row = pv_only_frame.loc[pv_only_frame['System Cost Efficiency'].idxmax()]

            master_sheet.cell(row=i, column=3).value = house_load
            master_sheet.cell(row=i, column=4).value = hes_max_row['HES Size']
            master_sheet.cell(row=i, column=5).value = hes_max_row['System Cost ($)']
            master_sheet.cell(row=i, column=6).value = hes_max_row['Baseline Savings ($)']
            master_sheet.cell(row=i, column=7).value = hes_max_row['System Cost Efficiency']
            master_sheet.cell(row=i, column=8).value = pv_max_row['Solar Size (kW)']
            master_sheet.cell(row=i, column=9).value = pv_max_row['System Cost ($)']
            master_sheet.cell(row=i, column=10).value = pv_max_row['Baseline Savings ($)']
            master_sheet.cell(row=i, column=11).value = pv_max_row['System Cost Efficiency']
            master_sheet.cell(row=i, column=12).value = both_max_row['HES Size']
            master_sheet.cell(row=i, column=13).value = both_max_row['Solar Size (kW)']
            master_sheet.cell(row=i, column=14).value = pv_max_row['System Cost ($)']
            master_sheet.cell(row=i, column=15).value = pv_max_row['Baseline Savings ($)']
            master_sheet.cell(row=i, column=16).value = pv_max_row['System Cost Efficiency']

            i += 1
    master_wb.save(new_path)


def make_summary_plots(path: str,
                       loads: int | list[int] = None,
                       hes_opts: str | list[str] = None,
                       commutes: str | list[str] = None,
                       v2h_lims: float | list[float] = None,
                       net_mets: str | list[str] = None,
                       do_baseline=True,
                       do_peak_eff=True,
                       do_hes_avoidance=True,
                       do_pv_avoidance=True,
                       do_20yr_value=True,
                       do_cost_eff=True,
                       do_v2h_eff=True,
                       do_degradation=True,
                       do_hes_pv_synergy=True):
    """
    This method makes all the key metric plots for a given input file
    Parameters
    ----------
    path: str
        The path to the output summary csv for the given input file.
    loads
    hes_opts
    v2h_lims
    net_mets
    do_baseline
    do_peak_eff
    do_hes_avoidance
    do_pv_avoidance
    do_20yr_value
    do_cost_eff
    do_v2h_eff
    do_degradation
    do_hes_pv_synergy

    Returns
    -------

    """
    #refine frame
    frame = pd.read_csv(path)
    directory = str.join('/', path.split('/')[1:-1])
    fig_direct = f'Figures/MetricFigures/{directory}/'
    if not os.path.exists(fig_direct):
        os.makedirs(fig_direct)
    file_name = str.join('_', path.split('/')[-1].split('_')[:-1])

    city = frame.loc[0, 'City']
    state = frame.loc[0, 'State']
    ref_city = frame.loc[0, 'Reference City']
    ref_state = frame.loc[0, 'Reference State']
    #refine loads

    if type(loads) is int:
        ind = frame['House Load'] == loads
        loads = [loads]
    elif type(loads) is list:
        ind = frame['House Load'].isin(loads)
    else:
        ind = []
        loads = np.unique(frame['House Load'].to_numpy())
    if len(ind) != 0:
        frame = frame[ind]

    #refine optimizations
    if type(hes_opts) is str:
        ind = frame['HES Optimization'] == hes_opts
        hes_opts = [hes_opts]
    elif type(hes_opts) is list:
        ind = frame['HES Optimization'].isin(hes_opts)
    else:
        ind = []
        hes_opts = list(set(frame['HES Optimization'].to_list()))
    if len(ind) != 0:
        frame = frame[ind]

    # refine v2h limits
    if type(v2h_lims) is float:
        ind = frame['EV Discharge Limit'] == v2h_lims
        v2h_lims = [v2h_lims]
    elif type(v2h_lims) is list:
        ind = frame['EV Discharge Limit'].isin(v2h_lims)
    else:
        ind = []
        v2h_lims = np.unique(frame['EV Discharge Limit'].to_numpy())

    if len(ind) != 0:
        frame = frame[ind]

    #refine commutes
    if type(commutes) is str:
        ind = frame['Pattern'] == commutes
        commutes = [commutes]
    elif type(commutes) is list:
        ind = frame['Pattern'].isin(v2h_lims)
    else:
        ind = []
        commutes = list(set(frame['Pattern'].to_list()))

    if len(ind) != 0:
        frame = frame[ind]

    if type(net_mets) is str:
        ind = frame['Net Meter Policy'] == net_mets
        net_mets = [net_mets]
    elif type(net_mets) is list:
        ind = frame['Net Meter Policy'].isin(net_mets)
    else:
        ind = []
        net_mets = list(set(frame['Net Meter Policy'].to_list()))
    if len(ind) != 0:
        frame = frame[ind]

    #function for getting row
    def get_row(sub_frame: pd.DataFrame,
                hes_size: int,
                pv_size: int | float,
                commute: str = '35mi_7to3',
                v2h: float = 1,
                net_met: str = 'wholesale',
                hes_opt: str = 'flat',
                house_load: int | float = 11000):
        reduced = sub_frame[(sub_frame['HES Size'] == hes_size) &
                            (sub_frame['Solar Size (kW)'] == pv_size) &
                            (sub_frame['Pattern'] == commute) &
                            (sub_frame['EV Discharge Limit'] == v2h) &
                            (sub_frame['House Load'] == house_load) &
                            (sub_frame['Net Meter Policy'] == net_met) &
                            (sub_frame['HES Optimization'] == hes_opt)]
        return reduced

    #Plot Constants
    x_lab = 'PV Size (kW)'
    y_lab = 'HES Size (kWh)'

    for load in loads:
        for opt in hes_opts:
            for commute in commutes:
                for v2h_lim in v2h_lims:
                    for met in net_mets:
                        int_lim = int(v2h_lim * 100)
                        int_load = int(load)
                        file_designator = (f'{file_name}_{int_load}kWh_{commute}_{int_lim}pV2Hlim_{opt}OptHES'
                                           f'_{met}NetMet')
                        label_str = '\n'.join([f'Location: {city}, {state}',
                                               f'Reference: {ref_city}, {ref_state}',
                                               f'Yearly Load (kWh): {load}',
                                               f'V2H Limit: {int_lim}%',
                                               f'Net Meter: {met}'])
                        #create mesh
                        hes_sizes = np.unique(frame['HES Size'].to_numpy())
                        pv_sizes = np.unique(frame['Solar Size (kW)'].to_numpy())
                        pv_mesh, hes_mesh = np.meshgrid(pv_sizes, hes_sizes)

                        effs = np.zeros(hes_mesh.shape)
                        paybacks = np.zeros(hes_mesh.shape)
                        savings = np.zeros(hes_mesh.shape)
                        two_decade_values = np.zeros(hes_mesh.shape)
                        fleet_avoidance = np.zeros(hes_mesh.shape)
                        v2h_effectiveness = np.zeros(hes_mesh.shape)
                        system_costs = np.zeros(hes_mesh.shape)
                        co2_savings = np.zeros(hes_mesh.shape)
                        peak_efficiencies = np.zeros(hes_mesh.shape)
                        net_values = np.zeros(hes_mesh.shape)
                        ev_sim_miles = np.zeros(hes_mesh.shape)
                        degs = np.zeros(hes_mesh.shape)

                        for i in range(len(hes_sizes)):
                            for j in range(len(pv_sizes)):
                                hes: int
                                pv: int
                                hes = hes_sizes[i]
                                pv = pv_sizes[j]
                                sub_frame = get_row(sub_frame=frame,
                                                    hes_size=hes,
                                                    pv_size=pv,
                                                    v2h=v2h_lim,
                                                    net_met=met,
                                                    hes_opt=opt,
                                                    house_load=load)

                                try:
                                    effs[i, j] = sub_frame['Baseline Savings ($)'] / (
                                            sub_frame['Solar Cost ($)'] + sub_frame['HES Cost ($)'])
                                except ValueError:
                                    effs[i, j] = 0

                                paybacks[i, j] += sub_frame['System Payback Period'].values[0]
                                savings[i, j] += sub_frame['Baseline Savings ($)'].values[0]
                                two_decade_values[i, j] += (savings[i, j] * 20 - sub_frame['System Cost ($)'].values[0])
                                fleet_avoidance[i, j] += sub_frame['Fleet Avoided Cost ($)'].values[0]
                                v2h_effectiveness[i, j] += fleet_avoidance[i, j] / \
                                                           sub_frame['EV Degradation ($)'].values[0]
                                system_costs[i, j] += sub_frame['System Cost ($)'].values[0]
                                co2_savings[i, j] += sub_frame['Baseline Savings (kg CO2)'].values[0]
                                peak_efficiencies[i, j] += sub_frame['System High Peak Shaving Efficiency'].values[0]
                                net_values[i, j] += sub_frame['Net Value ($)'].values[0]
                                degs[i, j] += sub_frame['EV Degradation ($)'].values[0]

                        # calculate synergies
                        hes_only_savings = np.tile(np.reshape(savings[:, 0], (len(hes_sizes), 1)), (1, len(pv_sizes)))
                        pv_only_savings = np.tile(np.reshape(savings[0, :], (1, len(pv_sizes))), (len(hes_sizes), 1))
                        hes_pv_synergies = savings - (hes_only_savings + pv_only_savings)

                        if do_baseline:
                            sub_direct = f'{fig_direct}/Baseline Savings'
                            if not os.path.exists(sub_direct):
                                os.makedirs(sub_direct)
                            base_fig = plt.figure()
                            base_ax = base_fig.add_subplot(111, projection='3d')
                            base_surf = base_ax.plot_surface(pv_mesh, hes_mesh, savings, cmap='viridis')
                            base_ax.set_xlabel('PV Size (kW)')
                            base_ax.set_ylabel('HES Size (kWh)')
                            base_ax.set_zlabel('Baseline Savings ($)')
                            base_ax.set_title('Baseline Savings ($)')
                            base_ax.view_init(azim=225, elev=30)
                            base_ax.text2D(0, .75, s=label_str, transform=base_ax.transAxes, fontsize=8)
                            base_fig.colorbar(base_surf, pad=.1)
                            base_fig.savefig(f'{sub_direct}/{file_designator}_BaselineSavings.png')

                        if do_cost_eff:
                            sub_direct = f'{fig_direct}/Cost Efficiency'
                            if not os.path.exists(sub_direct):
                                os.makedirs(sub_direct)
                            eff_fig = plt.figure()
                            eff_ax = eff_fig.add_subplot(111, projection='3d')
                            eff_surf = eff_ax.plot_surface(pv_mesh, hes_mesh, effs, cmap='viridis')
                            eff_ax.set_xlabel('PV Size (kW)')
                            eff_ax.set_ylabel('HES Size (kWh)')
                            eff_ax.set_zlabel('Cost Efficiency (%)')
                            eff_ax.set_title('Cost Efficiency (%)')
                            eff_ax.view_init(azim=225, elev=30)
                            eff_ax.text2D(0, .75, s=label_str, transform=eff_ax.transAxes, fontsize=8)
                            eff_fig.colorbar(eff_surf, pad=.1)
                            eff_fig.savefig(f'{sub_direct}/{file_designator}_CostEff.png')

                        if do_20yr_value:
                            sub_direct = f'{fig_direct}/20yr Value'
                            if not os.path.exists(sub_direct):
                                os.makedirs(sub_direct)
                            two_dec_fig = plt.figure()
                            two_dec_ax = two_dec_fig.add_subplot(111, projection='3d')
                            two_dec_surf = two_dec_ax.plot_surface(pv_mesh, hes_mesh, two_decade_values, cmap='viridis')
                            two_dec_ax.set_xlabel('PV Size (kW)')
                            two_dec_ax.set_ylabel('HES Size (kWh)')
                            two_dec_ax.set_zlabel('20 Yr Value ($)')
                            two_dec_ax.set_title('20 Yr Value ($)')
                            two_dec_ax.view_init(azim=225, elev=30)
                            two_dec_ax.text2D(0, .75, s=label_str, transform=two_dec_ax.transAxes, fontsize=8)
                            two_dec_fig.colorbar(two_dec_surf, pad=.1)
                            two_dec_fig.savefig(f'{sub_direct}/{file_designator}_20yr.png')

                        if do_peak_eff:
                            sub_direct = f'{fig_direct}/Peak Shaving Efficiency'
                            if not os.path.exists(sub_direct):
                                os.makedirs(sub_direct)
                            peak_eff_fig = plt.figure()
                            peak_eff_ax = peak_eff_fig.add_subplot(111, projection='3d')
                            peak_eff_surf = peak_eff_ax.plot_surface(pv_mesh, hes_mesh, peak_efficiencies,
                                                                     cmap='viridis')
                            peak_eff_ax.set_xlabel('PV Size (kW)')
                            peak_eff_ax.set_ylabel('HES Size (kWh)')
                            peak_eff_ax.set_zlabel('% of Peak Energy Provided')
                            peak_eff_ax.set_title('% of Peak Energy Provided')
                            peak_eff_ax.view_init(azim=225, elev=30)
                            peak_eff_ax.text2D(0, .75, s=label_str, transform=peak_eff_ax.transAxes, fontsize=8)
                            peak_eff_fig.colorbar(peak_eff_surf, pad=.1)
                            peak_eff_fig.savefig(f'{sub_direct}/{file_designator}_peakEff.png')

                        if do_hes_pv_synergy:
                            sub_direct = f'{fig_direct}/HES-PV Synergy'
                            if not os.path.exists(sub_direct):
                                os.makedirs(sub_direct)
                            hes_pv_fig = plt.figure()
                            hes_pv_ax = hes_pv_fig.add_subplot(111, projection='3d')
                            hes_pv_surf = hes_pv_ax.plot_surface(pv_mesh, hes_mesh, hes_pv_synergies, cmap='viridis')
                            hes_pv_ax.set_xlabel('PV Size (kW)')
                            hes_pv_ax.set_ylabel('HES Size (kWh)')
                            hes_pv_ax.set_zlabel('Synergy Value ($)')
                            hes_pv_ax.set_title('Synergy Value ($)')
                            hes_pv_ax.view_init(azim=225, elev=30)
                            hes_pv_ax.text2D(0, .75, s=label_str, transform=hes_pv_ax.transAxes, fontsize=8)
                            hes_pv_fig.colorbar(hes_pv_surf, pad=.1)
                            hes_pv_fig.savefig(f'{sub_direct}/{file_designator}_HesPvSyn.png')


def get_commute_str(commute: str) -> str:
    spl1 = commute.split('_')
    mileage = spl1[0]
    workday = spl1[1]
    spl2 = workday.split('to')
    leave = spl2[0]
    return_time = spl2[1]
    com_str = f'{mileage}, {leave}am-{return_time}pm'
    return com_str


def refine_commutes(commute_list: list[str],
                    compare_by_time=False,
                    compare_by_distance=False,
                    time: str = '9to5',
                    distance: str = '35mi') -> list[str]:
    """

    Parameters
    ----------
    commute_list: list[str]
        A list of commutes (rep as strings in format {dist}mi_{departHour}_{returnHour}, ex 35mi_9to5)
    compare_by_time: bool
        A boolean to filter commute list to compare times at a specified distance (see time)
    compare_by_distance
        A boolean to filter commute list to compare distances at a specified time (see dist)
    time: str
        A commute time specified by string in format {departHour}to{returnHour}, ex 9to5
    distance: str
        A commute distance specified by a string in format {dist}mi, ex 35mi.

    Returns
    -------
    new list: list[str]
        a filtered list of commutes
    """
    new_list = []
    for commute in commute_list:
        if compare_by_distance and compare_by_time:
            new_list.append(commute)
        elif compare_by_distance:
            if commute.split('_')[1] == time:
                new_list.append(commute)
        elif compare_by_time:
            if commute.split('_')[0] == distance:
                new_list.append(commute)
        else:
            new_list.append(commute)
    new_list = sorted(list(set(new_list)), key=lambda x: (int(x.split('mi')[0]), int(x.split('_')[1].split('to')[0])))
    return new_list


def get_style_and_clr(num: int):
    if num < 4:
        style = 'dashdot'
    elif num < 8:
        style = 'dotted'
    elif num < 12:
        style = 'dashed'
    else:
        style = 'solid'

    rem = num % 4

    if rem == 0:
        clr = '#d62728'
    elif rem == 1:
        clr = '#bcbd22'
    elif rem == 2:
        clr = '#2ca02c'
    elif rem == 3:
        clr = '#1f77b4'
    else:
        clr = '#1f77b4'

    return style, clr


def make_V2H_plot(path: str,
                  loads: int | list[int] = None,
                  by_spare_capacity=False,
                  battery_size=131):
    # load frame
    frame = pd.read_csv(path)
    directory = str.join('/', path.split('/')[:-1])
    fig_direct = f'{directory}/V2HFigures'
    if not os.path.exists(fig_direct):
        os.makedirs(fig_direct)
    file_name = str.join('_', path.split('/')[-1].split('_')[:-1])

    #refine frame
    if type(loads) is int:
        ind = frame['House Load'] == loads
        loads = [loads]
    elif type(loads) is list:
        ind = frame['House Load'].isin(loads)
    else:
        ind = []
        loads = np.unique(frame['House Load'].to_numpy())
    if len(ind) != 0:
        frame = frame[ind]

    frame = frame[frame['HES Size'] == 0]
    frame = frame[frame['Solar Size (kW)'] == 0]

    # hes_opts = list(set(frame['HES Optimization'].to_list()))
    v2h_lims = np.unique(frame['EV Discharge Limit'].to_numpy())
    # net_mets = list(set(frame['Net Meter Policy'].to_list()))
    commutes = list(set(frame['Pattern'].tolist()))
    commutes = sorted(commutes, key=lambda x: int(x.split('mi')[0]))

    distances = list(set([commute.split('_')[0] for commute in commutes]))
    times = list(set([commute.split('_')[1] for commute in commutes]))

    data_cols = ['Baseline Savings ($)', 'Baseline Savings (kg CO2)',
                 'Fleet Avoided Cost ($)', 'Fleet Avoided CO2 (kg)']

    shorthand_data_dict = {'Baseline Savings ($)': 'BaseSavings',
                           'Baseline Savings (kg CO2)': 'BaseCO2',
                           'Fleet Avoided Cost ($)': 'FleetSavings',
                           'Fleet Avoided CO2 (kg)': 'FleetCO2'}

    if by_spare_capacity:
        x_vals = (1 - v2h_lims) * battery_size
        x_tit = 'Spare Capacity (kWh)'
        by_val = 'SpareCap'
    else:
        x_vals = v2h_lims * 100
        x_tit = 'V2H Limit (%)'
        by_val = 'V2HLim'

    for load in loads:
        int_load = int(load)
        file_root = f'{fig_direct}/{file_name}_{int_load}kWh_by{by_val}'
        #Comparing time for each distance
        for dist in distances:
            com_list = refine_commutes(commute_list=commutes, compare_by_time=True, distance=dist)
            for data in data_cols:
                data_fig, data_ax = plt.subplots()
                data_ax.set_xlabel(x_tit)
                data_ax.set_ylabel(f'{data}')
                data_ax.set_title(f'{data}')
                data_short = shorthand_data_dict[data]
                png_name = f'{file_root}_CompByTimeFor{dist}_{data_short}.png'
                i = 0
                for commute in com_list:
                    style, clr = get_style_and_clr(i)
                    sub_frame = frame[frame['Pattern'] == commute]
                    values = [sub_frame.loc[sub_frame['EV Discharge Limit'] == limit, data].values[0] for limit in
                              v2h_lims]
                    data_ax.plot(x_vals, values, label=get_commute_str(commute=commute), linestyle=style,
                                 color=clr)

                    i += 1
                data_ax.legend(prop={'size': 8}, loc='upper left', bbox_to_anchor=(.8, 1))
                data_fig.savefig(png_name)
        for tm in times:
            com_list = refine_commutes(commute_list=commutes, compare_by_distance=True, time=tm)
            for data in data_cols:
                data_fig, data_ax = plt.subplots()
                data_ax.set_xlabel(x_tit)
                data_ax.set_ylabel(f'{data}')
                data_ax.set_title(f'{data}')
                data_short = shorthand_data_dict[data]
                png_name = f'{file_root}_CompByDistFor{tm}_{data_short}.png'
                i = 0
                for commute in com_list:
                    style, clr = get_style_and_clr(i)
                    sub_frame = frame[frame['Pattern'] == commute]
                    values = [sub_frame.loc[sub_frame['EV Discharge Limit'] == limit, data].values[0] for limit in
                              v2h_lims]
                    data_ax.plot(x_vals, values, label=get_commute_str(commute=commute), linestyle=style,
                                 color=clr)

                    i += 1
                data_ax.legend(prop={'size': 8}, loc='upper left', bbox_to_anchor=(.8, 1))
                data_fig.savefig(png_name)


def collection_summary_plots(collection_name: str):
    if len(collection_name.split('/')) == 1:
        collection_path = f'Outputs/{collection_name}'
    else:
        collection_path = collection_name
        collection_name = collection_name.split('/')[-1]

    for file_name in get_subdirs(path=collection_path):
        print(file_name)
        path = f'{collection_path}/{file_name}/{file_name}_summary.csv'
        try:
            make_summary_plots(path=path)
        except IndexError:
            print('FAILURE: IndexError')


def collection_v2h_plots(collection_name: str):
    if len(collection_name.split('/')) == 1:
        collection_path = f'Outputs/{collection_name}'
    else:
        collection_path = collection_name
        collection_name = collection_name.split('/')[-1]

    for file_name in get_subdirs(path=collection_path):
        print(file_name)
        path = f'{collection_path}/{file_name}/{file_name}_summary.csv'
        try:
            make_V2H_plot(path=path)
        except KeyError:
            print(f'{file_name} ****ERROR*****')


def v2h_tables(collection_name: str):
    if len(collection_name.split('/')) == 1:
        collection_path = f'Outputs/{collection_name}'
    else:
        collection_path = collection_name
        collection_name = collection_name.split('/')[-1]

    new_path = f'Outputs/{collection_name}/{collection_name}_v2h_deg_vs_sav.xlsx'

    # Establish workbook and header cells
    master_wb = openpyxl.Workbook()
    master_sheet = master_wb.active
    master_sheet['A1'] = 'Inputs'
    # master_sheet['D1'] = 'HES Only Results'
    # master_sheet['H1'] = 'PV Only Results'
    # master_sheet['L1'] = 'HES-PV-Combined Results'
    # master_sheet.merge_cells('A1:C1')
    # master_sheet.merge_cells('D1:G1')
    # master_sheet.merge_cells('H1:K1')
    # master_sheet.merge_cells('L1:P1')
    master_sheet['A2'] = 'Pool No'
    master_sheet['B2'] = 'City'
    master_sheet['C2'] = 'State'
    master_sheet['D2'] = 'House Load (kWh)'
    master_sheet['E2'] = 'Fleet Avoidance ($)'
    master_sheet['F2'] = 'Degradation ($)'
    master_sheet['G2'] = 'Breakeven Mileage (mi)'
    master_sheet['H2'] = 'Breakeven Unit Cost ($/kWh)'
    master_sheet['I2'] = 'V2H Effectiveness ($/kWh)'
    master_sheet['J2'] = 'Savings ($)'
    master_sheet['K2'] = 'CO2 Savings (kg CO2)'
    master_sheet['L2'] = 'Peak Shaving %'
    master_sheet['M2'] = 'V2H Miles'
    master_sheet['N2'] = 'Driven Miles'
    master_sheet['O2'] = 'Net Value ($)'
    master_sheet['P2'] = 'EV Discharge Limit'
    master_sheet['Q2'] = 'Commute'

    i = 3
    pool_no = 1
    for file_name in get_subdirs(path=collection_path):
        print(file_name)
        file_master = pd.read_csv(f'{collection_path}/{file_name}/{file_name}_summary.csv')
        cities = list(set(file_master['City'].to_list()))
        states = list(set(file_master['State'].to_list()))
        loads = np.unique(file_master['House Load'].to_numpy())
        file_master = file_master[(file_master['Solar Size (kW)'] == 0) &
                                  (file_master['HES Size'] == 0)]
        num_loads = len(loads)

        # add city and state to cells
        master_sheet.cell(row=i, column=1).value = pool_no
        master_sheet.cell(row=i, column=2).value = cities[0]
        master_sheet.cell(row=i, column=3).value = states[0]
        master_sheet.merge_cells(start_row=i, end_row=i + num_loads - 1, start_column=1, end_column=1)
        master_sheet.merge_cells(start_row=i, end_row=i + num_loads - 1, start_column=2, end_column=2)
        master_sheet.merge_cells(start_row=i, end_row=i + num_loads - 1, start_column=3, end_column=3)

        for house_load in loads:
            red_frame = file_master[(file_master['House Load'] == house_load)]

            max_row = red_frame.loc[red_frame['Fleet Avoided Cost ($)'].idxmax()]

            master_sheet.cell(row=i, column=4).value = house_load
            master_sheet.cell(row=i, column=5).value = max_row['Fleet Avoided Cost ($)']
            master_sheet.cell(row=i, column=6).value = max_row['EV Degradation ($)']
            master_sheet.cell(row=i, column=7).value = max_row['EV Breakeven Mileage (mi)']
            master_sheet.cell(row=i, column=8).value = max_row['EV Breakeven Cost ($/kWh)']
            master_sheet.cell(row=i, column=9).value = max_row['System Total Peak Shaving Efficiency']
            master_sheet.cell(row=i, column=10).value = max_row['Baseline Savings ($)']
            master_sheet.cell(row=i, column=11).value = max_row['Baseline Savings (kg CO2)']
            master_sheet.cell(row=i, column=12).value = max_row['System Total Peak Shaving Efficiency']
            master_sheet.cell(row=i, column=13).value = max_row['Fleet Sim Miles (mi)']
            master_sheet.cell(row=i, column=14).value = max_row['Fleet Driven Miles (mi)']
            master_sheet.cell(row=i, column=15).value = max_row['Net Value ($)']
            master_sheet.cell(row=i, column=16).value = max_row['EV Discharge Limit']
            master_sheet.cell(row=i, column=17).value = max_row['Pattern']

            i += 1
        pool_no += 1
    master_wb.save(new_path)

    # for file_name in get_subdirs(path=collection_path):
    #     print(file_name)
    #     path = f'{collection_path}/{file_name}/{file_name}_summary.csv'
    #     try:
    #         make_V2H_plot(path=path)
    #     except KeyError:
    #         print(f'{file_name} ****ERROR*****')


def peak_daily_insolations(ghi_arr: np.array, step: int = 5) -> np.array:
    if type(step) not in [int]:
        step = 5
    elif type not in [1, 5, 10, 12, 15, 20, 30, 60]:
        step = 5

    factor = int(60 / step)
    day_steps = int(24 * factor)
    num_days = int(len(ghi_arr) / day_steps)
    i = 0
    j = day_steps
    peaks = np.zeros(num_days)
    for num in range(num_days):
        peaks[num] = np.max(ghi_arr[i:j])
        i += day_steps
        j += day_steps

    return peaks


def peak_period_solar_hours(ghi_arr: np.array, tou_arr: np.array, solar_threshold: float, step: int = 5) -> float:
    """

    Parameters
    ----------
    ghi_arr:np.array
        Numpy array of GHI (W/m2) vs step
    tou_arr
        Numpy array of TOU rates vs step
    solar_threshold
        Amount which GHI must exceed to count as 'solar generating' step (W/m2)

    Returns
    -------

    """

    generating_steps = ghi_arr >= solar_threshold
    peak_steps = tou_arr > .98 * np.max(tou_arr)

    peak_solar_steps = generating_steps * peak_steps
    peak_solar_hours = np.sum(peak_solar_steps) / (60 / step)

    return np.round(peak_solar_hours, 2)


def emission_breakdown(tou_arr: np.array, co2_arr: np.array) -> (float, float):
    tou_max_steps = tou_arr > .98 * np.max(tou_arr)
    tou_min_steps = tou_arr < 1.02 * np.min(tou_arr)

    print(len(tou_arr[tou_max_steps]))

    avg_peak_co2 = np.mean(co2_arr[tou_max_steps])
    avg_off_co2 = np.mean(co2_arr[tou_min_steps])

    return avg_peak_co2, avg_off_co2


def pool_input_data_summary(pool_file: str):
    new_file = f'{pool_file}_dataSummary.xlsx'
    pool_frame = pd.read_csv(f'{pool_file}.csv')

    master_wb = openpyxl.Workbook()
    master_sheet = master_wb.active

    #Write column headers

    #Locality Info
    master_sheet['A1'] = 'Pool Info'
    master_sheet['A2'] = 'Pool ID'
    master_sheet['B2'] = 'Largest Zip Code'
    master_sheet['C2'] = 'City'
    master_sheet['D2'] = 'State'
    master_sheet['E2'] = 'Ref City'
    master_sheet['F2'] = 'Ref State'

    #Utility
    master_sheet['G1'] = 'Utility Info'
    master_sheet['G2'] = 'Utility'
    master_sheet['H2'] = 'Rate Schedule'
    master_sheet['I2'] = 'Peak Price ($/kWh)'
    master_sheet['J2'] = 'Price Differential ($/kWh)'
    master_sheet['K2'] = 'Peak Period Duration (hrs)'
    master_sheet['L2'] = 'Avg Rate ($/kWh)'

    #Solar
    master_sheet['M1'] = 'Solar Info'
    master_sheet['M2'] = 'Total Energy Intensity (kWh/m2)'
    master_sheet['N2'] = 'Avg Peak Insolation (W/m2)'
    master_sheet['O2'] = 'Solar-Peak Period Overlap (hrs)'

    #CO2
    master_sheet['P1'] = 'CO2 Info'
    master_sheet['P2'] = 'Avg Emission Rate (kgCO2/kWh)'
    master_sheet['Q2'] = 'Avg Peak Emission Rate (kgCO2/kWh)'
    master_sheet['R2'] = 'Avg Off-Peak Emission Rate (kgCO2/kWh)'

    tk = pm.TimeKeep()

    i = 3

    for index, row in pool_frame.iterrows():
        # Load necessary data files
        city = sp.create_city(zipcode=row['Largest Zip'])
        print((i - 2), city.name, city.state)
        util = sp.create_tariff(util_name=row['Utility'], tariff_name=row['Tariff'])
        util.create_tou_schedule(calendar=tk.calendar)
        max_rate = np.max(util.tou_schedule[:, 0])
        peak_duration = np.max(np.sum(util.weekday_rates == max_rate, axis=1))
        avg_rate = np.mean(util.tou_schedule[:, 0])

        ghi_file = sm.reference_solar_file(city.matched_state, city.matched_city)
        ghi_arr = pd.read_csv(ghi_file).to_numpy()[:, 1]
        total_energy_intensity = np.round(np.sum(ghi_arr) / 12 / 1000)

        avg_peak = np.round(np.mean(peak_daily_insolations(ghi_arr=ghi_arr)))
        peak_solar_hours = peak_period_solar_hours(ghi_arr=ghi_arr, tou_arr=util.tou_schedule[:, 0],
                                                   solar_threshold=.5 * avg_peak)

        emission_file = f'City Data/CO2 Profiles/Cambium 2021/Processed/{city.state}_Cambium_2022.csv'
        grid = cp.Grid(emission_file=emission_file)
        grid.change_dates()
        avg_emissivity = city.carbon_intensity
        print(np.mean(grid.emissions_rate))
        peak_emissivity, off_emissivity = emission_breakdown(tou_arr=util.tou_schedule[:, 0],
                                                             co2_arr=grid.emissions_rate)

        #Write Data
        #Locality
        master_sheet.cell(row=i, column=1).value = i - 2
        master_sheet.cell(row=i, column=2).value = row['Largest Zip']
        master_sheet.cell(row=i, column=3).value = city.name
        master_sheet.cell(row=i, column=4).value = city.state
        master_sheet.cell(row=i, column=5).value = city.matched_city
        master_sheet.cell(row=i, column=6).value = city.matched_state

        #Utility
        master_sheet.cell(row=i, column=7).value = util.utility
        master_sheet.cell(row=i, column=8).value = util.name
        master_sheet.cell(row=i, column=9).value = max_rate
        master_sheet.cell(row=i, column=10).value = row['Price Differential ($)']
        master_sheet.cell(row=i, column=11).value = peak_duration  # duration
        master_sheet.cell(row=i, column=12).value = avg_rate

        #Solar Data
        master_sheet.cell(row=i, column=13).value = total_energy_intensity
        master_sheet.cell(row=i, column=14).value = avg_peak
        master_sheet.cell(row=i, column=15).value = peak_solar_hours

        #CO2
        master_sheet.cell(row=i, column=16).value = avg_emissivity
        master_sheet.cell(row=i, column=17).value = peak_emissivity
        master_sheet.cell(row=i, column=18).value = off_emissivity

        i += 1

    master_wb.save(new_file)


def commute_solar_hours(ghi_arr: np.array, driving_pattern: np.array, solar_threshold: float, step: int = 5) -> float:
    """

    Parameters
    ----------
    ghi_arr:np.array
        Numpy array of GHI (W/m2) vs step
    driving_pattern
        Numpy array of TOU rates vs step
    solar_threshold
        Amount which GHI must exceed to count as 'solar generating' step (W/m2)

    Returns
    -------

    """

    generating_steps = ghi_arr >= solar_threshold

    peak_solar_steps = generating_steps * driving_pattern
    peak_solar_hours = np.sum(peak_solar_steps) / (60 / step)

    return np.round(peak_solar_hours, 2)


def commute_peak_breakdown(driving_pattern: np.ndarray, tou_arr: np.array, step: int = 5):
    peak_steps = tou_arr > .98 * np.max(tou_arr)
    off_peak_steps = tou_arr < 1.02 * np.min(tou_arr)

    factor = 60 / step

    peak_hours = np.sum(peak_steps) / factor
    print(peak_hours)
    peak_present_hours = np.sum(peak_steps * driving_pattern) / factor
    peak_percent = np.round(peak_present_hours / peak_hours * 100)
    off_peak_present_hours = np.sum(off_peak_steps * driving_pattern) / factor

    return peak_present_hours, peak_percent, off_peak_present_hours


def pool_commute_summary(pool_file: str):
    new_file = f'{pool_file}_commuteSummary.xlsx'
    pool_frame = pd.read_csv(f'{pool_file}.csv')

    master_wb = openpyxl.Workbook()
    master_sheet = master_wb.active

    # Write column headers

    # Locality Info
    master_sheet['A1'] = 'Pool Info'
    master_sheet['A2'] = 'Pool ID'
    master_sheet['B2'] = 'Largest Zip Code'
    master_sheet['C2'] = 'City'
    master_sheet['D2'] = 'State'
    master_sheet['E2'] = 'Ref City'
    master_sheet['F2'] = 'Ref State'

    master_sheet['G1'] = '7am to 3pm'
    master_sheet['G2'] = 'Peak Hours'
    master_sheet['H2'] = 'Peak Percentage (%)'
    master_sheet['I2'] = 'Off-Peak Hours'
    master_sheet['J2'] = 'Solar Gen Hours'

    master_sheet['K1'] = '8am to 4pm'
    master_sheet['K2'] = 'Peak Hours'
    master_sheet['L2'] = 'Peak Percentage (%)'
    master_sheet['M2'] = 'Off-Peak Hours'
    master_sheet['N2'] = 'Solar Gen Hours'

    master_sheet['O1'] = '9am to 5pm'
    master_sheet['O2'] = 'Peak Hours'
    master_sheet['P2'] = 'Peak Percentage (%)'
    master_sheet['Q2'] = 'Off-Peak Hours'
    master_sheet['R2'] = 'Solar Gen Hours'

    # CO2
    master_sheet['S1'] = '10am to 6pm'
    master_sheet['S2'] = 'Peak Hours'
    master_sheet['T2'] = 'Peak Percentage (%)'
    master_sheet['U2'] = 'Off-Peak Hours'
    master_sheet['V2'] = 'Solar Gen Hours'

    tk = pm.TimeKeep()

    times = ['7to3', '8to4', '9to5', '10to6']

    i = 3

    for index, row in pool_frame.iterrows():
        # Load necessary data files
        city = sp.create_city(zipcode=row['Largest Zip'])
        print((i - 2), city.name, city.state)
        util = sp.create_tariff(util_name=row['Utility'], tariff_name=row['Tariff'])
        util.create_tou_schedule(calendar=tk.calendar)

        ghi_file = sm.reference_solar_file(city.matched_state, city.matched_city)
        ghi_arr = pd.read_csv(ghi_file).to_numpy()[:, 1]
        avg_peak = np.round(np.mean(peak_daily_insolations(ghi_arr=ghi_arr)))

        # Locality
        master_sheet.cell(row=i, column=1).value = i - 2
        master_sheet.cell(row=i, column=2).value = row['Largest Zip']
        master_sheet.cell(row=i, column=3).value = city.name
        master_sheet.cell(row=i, column=4).value = city.state
        master_sheet.cell(row=i, column=5).value = city.matched_city
        master_sheet.cell(row=i, column=6).value = city.matched_state

        j = 7
        for time in times:
            commute_file = f'20mi_{time}.csv'
            dp = sp.create_driving_pattern(filename=commute_file)

            peak_hours, peak_percent, off_peak_hours = commute_peak_breakdown(driving_pattern=dp[:, 1],
                                                                              tou_arr=util.tou_schedule[:, 0])
            solar_hours = commute_solar_hours(ghi_arr=ghi_arr, driving_pattern=dp[:, 1], solar_threshold=.5 * avg_peak)

            master_sheet.cell(row=i, column=j).value = peak_hours
            master_sheet.cell(row=i, column=j + 1).value = peak_percent
            master_sheet.cell(row=i, column=j + 2).value = off_peak_hours
            master_sheet.cell(row=i, column=j + 3).value = solar_hours
            j += 4

        i += 1

    master_wb.save(new_file)


def plot_results(result: sm.Results):
    timestep = result.timekeep.timestep
    start_day = result.timekeep.starting_day
    num_steps = result.timekeep.num_steps
    year = result.timekeep.year
    row = np.where(result.timekeep.calendar[:, 3] == start_day)[0][0]
    start_dom = result.timekeep.calendar[row, 1]
    start_mon = result.timekeep.calendar[row, 2]
    start_date_short = str(year) + '-' + str(start_mon) + '-' + str(start_dom)
    start_date_long = str(year) + '-1-1'
    freq = str(timestep) + 'min'

    short_time = pd.period_range(start=start_date_short, periods=num_steps, freq=freq).to_timestamp()
    long_time = pd.period_range(start=start_date_long, periods=int(365 * 24 * 60 / timestep), freq=freq).to_timestamp()

    fig, ax = plt.subplots()
    ax.plot(short_time, result.fleet.ev_list[0].socs)
    ax.set_xlabel('Time')
    ax.set_ylabel('EV SoC (%)')

    ax2 = ax.twinx()
    ax2.plot(short_time, result.tariff.tou_schedule[:, 1], color='r')
    ax2.set_ylabel('Peak/Off-Peak')

    plt.show()
