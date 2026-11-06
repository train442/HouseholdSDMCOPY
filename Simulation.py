"""
This module contains classes and methods pertaining to the simulation algorithm and results.

Classes
-------
-   Bill: A Class representing the electricity bill containing information such as cost, net-metering
    amounts, etc.
-   Results : A Class which calculates and contains a variety of desired metrics for the simulation and
    serves as a repository for all the various Component and Parameter classes that serve as inputs. This class can be
    saved as a pickle file and serve to save the simulation.

Methods
-------
-   update_comp_status: This method updates of the usability status of the various components in the simulation
    based on conditions unique to each component.
-   sinks_and_sources: This method gives a list of components that can/must be sources, and another of components
    that can/must be sinks.
-   energy_flows: This method calculates and implements the energy flow between the sources and sinks.
-   optimize_hes : This method calculates the desired HES state of charge to reach and the time it must attain it
    based on the optimization scheme designated in the Operations object.
-   run_simulation : This method is the main function which runs the simulation, utilizing the other methods in this
    module, and returns a Results object.

"""
import numpy as np
import pandas as pd
from pandas import DataFrame
import Components as cp
from Components import HES, EV, Fleet, PV, House, Grid, Energy, ICE
import Parameters as pm
from Parameters import Operation, TimeKeep, Tariff, City
import TimeManage as tm
import DataProcessing as dp
import Setup as sp
import time
import warnings
import os
import pickle
import copy
import datetime
import traceback
import concurrent.futures
import multiprocessing
import gzip
import Progress
from operator import itemgetter
from typing import Optional

#  Settings and Constants
pd.set_option('display.max_columns', None)
warnings.simplefilter(action='ignore', category=FutureWarning)

_priority = itemgetter(3)  # sort key for the per-timestep sink/source lists (see sinks_and_sources)

# Component kind codes. These are deliberately the row/column indices of the efficiency matrix
# (Model Data/efficiencies.xlsx), so a (source_kind, sink_kind) pair indexes it directly. The sink/source
# lists built each timestep carry these instead of component name strings: integer comparison in the
# dispatch tree is meaningfully cheaper than string comparison at ~630k iterations per scenario.
KIND_PV = 0
KIND_HES = 1
KIND_EV = 2
KIND_EV_DCFC = 3
KIND_GRID = 4
KIND_HOUSE = 5

WATTTIME_DEFAULT_YEAR = 2024  # calendar year of WattTime profile used when a scenario doesn't set 'WattTime
                              # Year' -- see make_grid. Override per-scenario-row instead of changing this.

ev_model_frame = pd.read_csv('Model Data/EVs.csv')
pv_model_frame = pd.read_excel('Model Data/PVs.xlsx')
match_city_frame = pd.read_csv('Model Data/city_list_refined.csv')
zip_frame = pd.read_csv('Model Data/zip_directory.csv', dtype={'Zip Code': str})
save_loads = False


# Define Results and Bill Classes


class Bill:
    """
    A Class representing the electricity bill containing information such as cost, net-metering
    amounts, etc.

    Attributes
    ----------
    summary : DataFrame
        A Dataframe modeled after a monthly bill containing electricity usage and cost metrics as well as net metering.
    total_bill : float
        The total cost of electricity (including sales tax).
    co2_emissions : float
        The total amount of CO2 emitted by the all components (in kg CO2).

    """

    def __init__(self, op: Operation, timekeep: pm.TimeKeep, energy: cp.Energy, tariff: pm.Tariff, city: pm.City,
                 grid: cp.Grid):
        """
        This is the initialization method for the Bill class.

        Parameters
        ----------
        op : Operation
            The Operation object used in simulation (See Parameters).
        timekeep : TimeKeep
            The TimeKeep object used in simulation (See Parameters).
        energy : Energy
            The Energy object used in simulation (See Components).
        tariff : Tariff
            The Tariff object used in simulation (See Parameters).
        city : City
            The City object used in simulation (See Parameters).
        grid : Grid
            The Grid object used in simulation (See Components).
        """
        self.summary = pd.DataFrame()
        self.generate_bill(op=op, timekeep=timekeep, energy=energy, tariff=tariff, city=city, grid=grid)
        self.total_bill = np.sum(self.summary['After Tax Total'].to_numpy())
        self.co2_emissions = np.sum(self.summary['CO2 Emissions'].to_numpy())

    def generate_bill(self, op: Operation, timekeep: TimeKeep, energy: Energy, tariff: Tariff, city: City, grid: Grid):
        """
        This method populates the summary attribute for the Bill object using the model inputs.

        Parameters
        ----------
        op : Operation
            The Operation object used in simulation (See Parameters).
        timekeep : TimeKeep
            The Tariff object used in simulation (See Parameters).
        energy : Energy
            The Energy object used in simulation (See Components).
        tariff : Tariff
            The Tariff object used in simulation (See Parameters).
        city : City
            The City object used in simulation (See Parameters).
        grid : Grid
            The Grid object used in simulation (See Components).

        Returns
        -------
        None
        """
        # this returns a bill summary in the form of a pandas dataframe
        # in the first half of this function, we assess the columns that will be in bill
        column = ['Period Start', 'Period End', 'House Load', 'Fleet Load', 'Fleet Out', 'HES Load', 'HES Out',
                  'Solar Output', 'Total Usage', 'Total Outflow', 'System Loss', 'CO2 Emissions']
        one_to_one = op.net_meter_scheme.lower() in ['one-to-one', 'full']
        net_billing = op.net_meter_scheme.lower() in ['netbilling', 'net billing', 'net_billing']
        no_compensation = op.net_meter_scheme.lower() in ['none', 'no compensation']
        no_excess = op.net_meter_scheme.lower() in ['no excess', 'no extra', 'no_excess']
        nem3 = op.net_meter_scheme.lower() in ['nem 3.0', 'nem3', 'nem3.0']
        is_nbc = op.net_meter_scheme.lower() in ['nbc', 'non_bypassable', 'nonbypassable', 'non-bypassable']
        is_wholesale = op.net_meter_scheme.lower() in ['wholesale', 'avoided cost']
        tou_solar = one_to_one or nem3 or net_billing or no_excess or is_nbc  # solar buyback is tou (not wholesale)
        is_sellback = op.net_meter_scheme in ['sellback', 'Sellback']

        running = op.net_meter_account_freq == 'yearly'  # extra kWh balance is carried over and reupped when at the
        # end of the year.

        if no_compensation:
            solar_sell_rate = 0
        elif is_wholesale:
            solar_sell_rate = tariff.sellback_rate
        elif is_sellback:
            solar_sell_rate = tariff.sellback_rate
        elif net_billing:
            solar_sell_rate = tariff.sellback_rate
        else:
            solar_sell_rate = .03

        sell_factor = .25 if nem3 else 1  # what percent of retail you are compensated (if one-to-on or nem3)

        if tariff.is_tou:  # tariff is time of use
            add_col = []
            for i in range(len(tariff.unique_tou_rates)):
                num = i + 1
                add_col.append('Rate ' + str(num) + ': Unit Cost')
                add_col.append('Rate ' + str(num) + ': Usage')
                add_col.append('Rate ' + str(num) + ': Outflow')
                if tou_solar:

                    add_col.append('Rate ' + str(num) + ': Net')
                    if nem3 or is_nbc:
                        add_col.append('Rate ' + str(num) + ': Credit')
                    if running:
                        add_col.append('Rate ' + str(num) + ': Balance')  # running balance of credits at that rate
                        add_col.append('Rate ' + str(num) + ': Charged')
                add_col.append('Rate ' + str(num) + ': Subtotal')
            column += add_col  # add new set of columns to master columns variable

        if tariff.is_tiered:
            add_col = []
            for i in range(tariff.max_tiers):
                num = i + 1
                add_col.append('Tier ' + str(num) + ': Cap')
                add_col.append('Tier ' + str(num) + ': Usage')
                add_col.append('Tier ' + str(num) + ': Rate')
                add_col.append('Tier ' + str(num) + ': Subtotal')
            column += add_col

        periods = tariff.periods_energy

        if tariff.is_tou & tariff.is_tiered:
            # we must reduce periods array so that we aren't double counting electricity
            for per in periods:
                first_rate = per[0][1]
                for tier in per:
                    tier[1] = np.round(tier[1] - first_rate, 5)

        if not tou_solar:
            column += ['Solar Credit']  # we add this column if there is flat rate for solar sent to grid

        column += ['Monthly Charge', 'Subtotal', 'After Tax Total']

        bill_summary = pd.DataFrame(columns=column)

        emissions = grid.emissions_rate[timekeep.simu_start_step - 1:timekeep.simu_end_step] * energy.grid_out

        month_inds = tm.month_indices_from_calendar(timekeep.calendar)

        for i in range(month_inds.shape[0]):
            s_ind_t = month_inds[i, 0]  # start index for tariff and calendar array
            e_ind_t = month_inds[i, 1]  # start index for tariff and calendar array
            s_ind_e = s_ind_t - timekeep.simu_start_step + 1  # index for energy arrays
            e_ind_e = e_ind_t - timekeep.simu_start_step + 1  # index for energy arrays

            start_date_string = tm.calendar_row_to_date_string(row=timekeep.calendar[s_ind_t, :])
            end_date_string = tm.calendar_row_to_date_string(row=timekeep.calendar[e_ind_t, :])
            hes_usage = energy.grid_to_hes[s_ind_e:e_ind_e + 1]  # grid pull into HES
            hes_out = energy.hes_out[s_ind_e:e_ind_e + 1]  # energy out of HES
            fleet_usage = energy.grid_to_fleet[s_ind_e:e_ind_e + 1]  # grid pull for all EVs
            fleet_out = energy.ev_out_total[s_ind_e:e_ind_e + 1]  # output from all EVs
            solar_output = energy.pv_out[s_ind_e:e_ind_e + 1]
            house_usage = energy.house_in[s_ind_e:e_ind_e + 1]
            grid_usage = energy.grid_out[s_ind_e:e_ind_e + 1]
            grid_outflow = energy.grid_in[s_ind_e:e_ind_e + 1]  # subarray of grid outflow for month
            total_loss = energy.loss[s_ind_e:e_ind_e + 1]
            co2_emitted = emissions[s_ind_e:e_ind_e + 1]  # co2
            if tariff.is_tou:
                tous = tariff.tou_schedule[s_ind_t:e_ind_t + 1, 0]
            else:
                tous = []

            month = timekeep.calendar[s_ind_t, 2]
            total_hes = np.round(np.sum(hes_usage), 3)  # total grid pull for HES
            total_hes_out = np.round(np.sum(hes_out), 3)
            total_fleet = np.round(np.sum(fleet_usage), 3)  # total grid pull for EV fleet
            total_fleet_out = np.round(np.sum(fleet_out), 3)  #
            total_solar = np.round(np.sum(solar_output), 3)  # total solar output in period at panel level
            total_house = np.round(np.sum(house_usage), 3)  # total load (kwh) required by house in period
            total_usage = np.round(np.sum(grid_usage), 3)  # total kwh usage in period (irrespective of time)
            total_outflow = np.round(np.sum(grid_outflow), 3)  # total kwh outflow to grid (irrespective of time)
            total_net = total_usage - total_outflow  # net inflow from grid vs outflow
            total_loss = np.round(np.sum(total_loss), 3)  # total loss from component transfer
            total_co2 = np.round(np.sum(co2_emitted), 3)  # total co2 emitted
            if one_to_one:
                e_balance = total_net  # for use in tiered bills, if one-to-one net metering, tier usage is based on net
            else:
                e_balance = total_usage  # if not one-to-one, tier usage is based on total inflow from grid
            subtotal = 0
            old_balance = 0
            new_balance = 0  # for running credit totals
            charged = 0
            per = tariff.weekday_schedule[month - 1, 0] - 1  # acquire index for applicable set of tiers/rates
            cap = tariff.periods_energy[per][0][0]  # acquire energy cap of first tier (irrelevant to pure tou tariffs)
            num_tiers = len(tariff.periods_energy[per])
            data = {}
            for col in column:
                if col == 'Period Start':
                    data[col] = start_date_string
                elif col == 'Period End':
                    data[col] = end_date_string
                elif col == 'House Load':
                    data[col] = total_house
                elif col == 'Fleet Load':
                    data[col] = total_fleet
                elif col == 'Fleet Out':
                    data[col] = total_fleet_out
                elif col == 'HES Load':
                    data[col] = total_hes
                elif col == 'HES Out':
                    data[col] = total_hes_out
                elif col == 'Solar Output':  # as recorded at panel level
                    data[col] = total_solar
                elif col == 'Total Usage':
                    data[col] = total_usage
                elif col == 'Total Outflow':
                    data[col] = total_outflow
                elif col == 'System Loss':
                    data[col] = total_loss
                elif col == 'CO2 Emissions':
                    data[col] = total_co2
                elif col == 'Monthly Charge':
                    val = tariff.monthly_charge
                    subtotal += val
                    data[col] = val
                elif col == 'Subtotal':
                    # if we are carrying running totals then the final month we re_ep
                    if running and (i == (month_inds.shape[0] - 1)) and (not no_excess):
                        re_up_credit = 0
                        for j in range(len(tariff.unique_tou_rates)):
                            num = j + 1
                            balance_header = 'Rate' + str(num) + ': Balance'
                            rate_header = 'Rate ' + str(num) + ': Unit Cost'
                            rate = bill_summary.loc[-1, rate_header]
                            balance = bill_summary.loc[-1, balance_header]
                            if one_to_one:
                                re_up_credit += rate * balance
                            elif net_billing:
                                re_up_credit += balance * solar_sell_rate
                        subtotal += re_up_credit
                    data[col] = round(subtotal, 2)
                elif col == 'After Tax Total':
                    data[col] = round(subtotal * (1 + city.tax_rate), 2)
                elif col == 'Solar Credit':
                    val = total_outflow * solar_sell_rate
                    subtotal -= val
                    data[col] = round(val, 2)
                elif col[0:4] == 'Tier':
                    spl = col.split()
                    tier = int(spl[1][0:-1])
                    if tier <= num_tiers:
                        head = spl[-1]  # information asked for by column
                        if head == 'Cap':
                            if tier != 1:
                                data[col] = max(periods[per][tier - 1][0] - cap, 0)
                                cap = periods[per][tier - 1][0]
                            else:
                                data[col] = cap
                        elif head == 'Usage':
                            key_name = spl[0] + ' ' + spl[1] + ' Cap'
                            cap = data[key_name]
                            if e_balance < 0:  # solar exceeded load
                                if tier == 1:  # we record excess solar on first tier
                                    data[col] = e_balance
                                else:
                                    data[col] = 0
                            else:
                                if cap == 0:  # correct tier cap for 0 value (which designates that there is no cap)
                                    cap = np.inf
                                if e_balance > cap:
                                    data[col] = cap
                                    e_balance -= cap
                                else:
                                    data[col] = e_balance
                                    e_balance = 0
                        elif head == 'Rate':
                            data[col] = periods[per][tier - 1][1]
                        elif head == 'Subtotal':
                            if (tier == 1) and (e_balance < 0):  # solar exceed load
                                val = data[spl[0] + ' ' + spl[1] + ' Usage'] * op.avoided_rate
                            else:
                                val = data[spl[0] + ' ' + spl[1] + ' Usage'] * data[spl[0] + ' ' + spl[1] + ' Rate']
                            subtotal += val
                            data[col] = val
                    else:
                        data[col] = None
                elif col[0:4] == 'Rate':
                    spl = col.split()
                    num = int(spl[1][0:-1])
                    head = spl[2]
                    rate = tariff.unique_tou_rates[num - 1]
                    if head == 'Unit':
                        data[col] = np.round(rate, 5)
                    elif head == 'Usage':
                        data[col] = np.round(np.sum(grid_usage[tous == rate]), 3)
                    elif head == 'Outflow':
                        data[col] = np.round(np.sum(grid_outflow[tous == rate]), 3)
                    elif head == 'Net':
                        data[col] = data[spl[0] + ' ' + spl[1] + ' Usage'] - data[spl[0] + ' ' + spl[1] + ' Outflow']
                    elif head == 'Balance':  # if re-up frequency is yearly, we find new running balance
                        # old balance is 0 if it's the first month (duh).
                        old_balance = 0 if i == 0 else bill_summary.loc[i - 1, col]
                        net = data[spl[0] + ' ' + spl[1] + ' Net']
                        new_balance = old_balance - net
                        if new_balance < 0:
                            charged = abs(new_balance)
                            new_balance = 0
                        else:
                            charged = 0
                        data[col] = new_balance
                    elif head == 'Charged':
                        data[col] = charged
                    elif head == 'Subtotal':
                        #  val is subtotal for current rate, subtotal is subtotal for overall month for all rates
                        usage = data[spl[0] + ' ' + spl[1] + ' Usage']
                        outflow = data[spl[0] + ' ' + spl[1] + ' Outflow']
                        net = usage - outflow
                        if not running:
                            charged = net
                        rate = data[spl[0] + ' ' + spl[1] + ' Unit Cost']
                        if one_to_one:  # full compensation for solar sent to grid at tou rate
                            val = charged * rate  # net usage times tou rate
                        elif net_billing:  # Usage covered in full, excess sold at wholesale rate
                            if net < 0:
                                if running:  # if we reup yearly then subtotal is zero and balance is carried over
                                    val = 0
                                else:
                                    val = charged * solar_sell_rate  # if negative, we apply avoided rate
                            else:
                                val = charged * rate
                        elif nem3:
                            val = rate * (usage - sell_factor * outflow)
                        elif is_nbc:
                            val = rate * usage - (rate - tariff.nbc) * outflow
                        else:
                            val = usage * rate
                        data[col] = round(val, 2)
                        subtotal += val  # this is OVERALL subtotal for month, not subtotal for current rate
                        charged = 0
            to_add = pd.DataFrame(data=data, index=[i])
            bill_summary = pd.concat([bill_summary, to_add], ignore_index=True, axis=0)
        self.summary = bill_summary


class Results:
    """
    A class which calculates and contains a variety of desired metrics for the simulation and serves as a repository
    for all the various Component and Parameter classes that serve as inputs. This class can be saved as a pickle
    file and serve to save the simulation.

    Attributes
    ----------
    operation : Operation
        The Operation object used in simulation (See Parameters).
    tariff : Tariff
        The Tariff object used in simulation (See Parameters).
    timekeep : TimeKeep
        The TimeKeep object used in simulation (See Parameters).
    energy : Energy
        The Energy object used in simulation (See Components).
    city : City
        The City object used in simulation (See Parameters).
    grid : Grid
        The Grid object used in simulation (See Components).
    hes : HES
        The HES object used in simulation (See Components).
    pv : PV
        The PV object used in simulation (See Components).
    house : House
        The House object used in simulation (See Components).
    fleet : Fleet
        The Fleet object used in simulation (See Components).
    bill : Bill
        The Bill object derived from the simulation.
    solar_output : float
        Total energy generated by the PV array.
    hes_avoidance : float
        The total electricity cost ($) avoided through HES peak shaving. Negative means HES use caused value loss.
    hes_co2_savings : float
        The total CO2 emissions prevented through HES use. Negative means more CO2 was emitted as a result.
    hes_cost : float
        Total cost of HES system ($).
    avg_soc_target : float
        The average state of charge the HES was told to charge to via optimization.
    solar_avoidance : float
        The cost savings generated by supplying the house with solar energy from the PV.
    solar_co2_savings : float
        The total CO2 emissions prevented by the PV system.
    pv_cost : float
        The total cost of the PV system.
    ev_avoidances : np.ndarray
        A numpy array containing the savings of each EV in the Fleet from V2H discharge.
    ev_co2_savings : np.ndarray
        A numpy array containing the CO2 emissions prevented by V2H discharge for each EV.
    gas_costs : np.ndarray
        A numpy array containing the cost of the miles driven in terms of gasoline for each EV in the Fleet.
    driving_costs : np.ndarray
        A numpy array containing the cost of driving for each EV.
    ev_degradations : np.ndarray
        A numpy array containing the costs of the battery degradation experienced by each EV from V2H.
    ev_breakeven_miles: np.ndarray
        A numpy array containing the battery life (in miles) needed for value loss from degradation to equal the V2H
        savings for each EV in the Fleet.
    ev_breakeven_cost : np.ndarray
        A numpy array containing the battery unit cost ($/kWh) needed for value loss from degradation to equal the
        V2H savings for each EV in the Fleet.
    fleet_avoidance : float
        The savings generated by the entire Fleet from V2H peak shaving.
    fleet_co2_savings : float
        The amount of CO2 emissions prevented by V2H peak shaving (in kg CO2).
    fleet_gas_costs : float
        The cost in gas needed to for an ICE to drive the same miles the Fleet has driven.
    fleet_driving_costs : float
        The total cost ($) of driving the EVs in the Fleet in terms of electricity.
    gas_savings : float
        The total amount of savings form driving EVs in the Fleet versus their ICE counterparts.
    fleet_cost : float
        The total MSRP of all EVs in the Fleet.
    house_peak_usage : float
        The amount of energy (kwH) used by the house during on-peak periods.
    house_mid_usage : float
        The amount of energy (kwH) used by the house during mid-peak periods.
    house_off_usage : float
        The amount of energy (kwH) used by the house during off-peak periods.
    grid_to_house_peak : float
        The amount of energy (kwH) sent by the grid to the house during on-peak periods.
    grid_to_house_mid : float
        The amount of energy (kwH) sent by the grid to the house during mid-peak periods.
    grid_to_house_off : float
        The amount of energy (kwH) sent by the grid to the house during off-peak periods.
    peak_shaving_effectiveness : float
        The percent of house load during peak and mid-peak periods covered by sources other than the grid (ie, PV).
    high_peak_shaving_effectiveness : float
        The percent of house load exclusively during peak periods covered by sources other than the grid (ie, PV).
    sanity : np.ndarray
        A N x 3 numpy array tracking energy flows into the system, out of the system, and the difference between
        these totals where N is the number of steps.
    check_sum : float
        The sum over every step of the energy into the system vs energy out of the system, which includes loss. This
        will ideally be as close to zero as possible.
    """

    def __init__(self, operation: Operation, tariff: Tariff, timekeep: TimeKeep, city: City, grid: Grid,
                 energy: Energy, hes: HES, pv: PV, house: House, fleet: Fleet, ice: ICE, full_results: bool = False):

        self.operation = operation
        self.tariff = tariff if full_results else None
        self.timekeep = timekeep if full_results else None
        self.energy = energy if full_results else None
        self.city = city if full_results else None
        self.grid = grid if full_results else None
        self.hes = hes if full_results else None
        self.pv = pv if full_results else None
        self.house = house if full_results else None
        self.fleet = fleet if full_results else None
        self.input_row = None
        self.time_elapsed = None

        self.bill = Bill(op=operation, timekeep=timekeep, energy=energy, tariff=tariff, city=city, grid=grid)

        self.solar_output = np.sum(pv.power * (timekeep.timestep / 60))

        # avoided costs associated with component use in lieu of grid.
        # These are 1-D to match the (now 1-D) per-step tracking arrays; no reshape needed.
        tou_costs = tariff.tou_schedule[(timekeep.simu_start_step - 1):timekeep.simu_end_step, 0]
        emissions = grid.emissions_rate[(timekeep.simu_start_step - 1):timekeep.simu_end_step]

        if hes.exists and operation.track_costs_of_use:
            self.hes_avoidance = np.round(np.sum(np.multiply(tou_costs - hes.cost_of_uses, energy.hes_to_house)) * (
                    1 + city.tax_rate), 2)
            self.hes_co2_savings = np.round(np.sum(np.multiply(emissions - hes.emissivity_arr, energy.hes_to_house)), 2)
            self.hes_cost = np.round((hes.batterySize * (7500 / 13.5) + 1200) * (1 + city.tax_rate), 2)
            if pv.exists:
                self.hes_cost *= .7

            self.avg_soc_target = np.round(np.mean(hes.soc_targets) * 100, 2)

        else:
            self.hes_avoidance = 0
            self.hes_co2_savings = 0
            self.hes_cost = 0
            self.avg_soc_target = 0

        if pv.exists:
            # if city.state == 'AZ':
            #     costperw = 2.44
            # elif city.state == 'GA':
            #     costperw = 3.2
            # elif city.state == 'OR':
            #     costperw = 3.02
            # elif city.state == 'CA':
            #     costperw = 2.86
            # else:
            #     costperw = 2.85

            costperw = city.solar_unit_cost

            self.solar_avoidance = np.round(np.sum(np.multiply(tou_costs, energy.pv_to_house)) * (1 + city.tax_rate), 2)
            self.solar_co2_savings = np.round(np.sum(np.multiply(emissions, energy.pv_to_house)), 2)
            self.pv_cost = np.round((costperw * (pv.system_size * 1000) + 2000) * (1 + city.tax_rate) * .7, 2)
        else:
            self.solar_avoidance = 0
            self.solar_co2_savings = 0
            self.pv_cost = 0

        if fleet.has_evs:
            self.commute = fleet.ev_list[0].commute
            self.ev_charge_scheme = fleet.ev_list[0].charging_scheme
            self.ev_avoidances = np.array([])
            self.ev_co2_savings = np.array([])
            self.gas_costs = np.array([])
            self.driving_costs = np.array([])
            self.ev_degradations = np.array([])
            self.ev_breakeven_miles = np.array([])
            self.ev_breakeven_cost = np.array([])
            self.ev_v2h_summaries = []
            self.v2h_effs = []
            for ev in fleet.ev_list:
                ev2h = energy.ev_to_house[:, ev.EViD - 1]  # already 1-D: a column slice of the per-EV array
                total_v2h = ev.miles_driven_simulated * ev.kwhpm_comb
                v2h_sum = dp.v2h_summary(v2h_arr=ev2h)
                avoidance = np.sum(np.multiply(tou_costs - ev.cost_of_uses, ev2h)) * (1 + city.tax_rate)
                v2h_eff = avoidance / total_v2h if total_v2h > 0 else np.nan
                co2_savings = np.sum(np.multiply(emissions - ev.emissivity_arr, ev2h))
                degradation = \
                    (ev.miles_driven_simulated / operation.ev_warranty) * ev.batterySize * operation.battery_cost
                if ev.miles_driven_simulated != 0:
                    be_miles = (ev.miles_driven_simulated / avoidance) * ev.batterySize * operation.battery_cost
                    be_battery_cost = avoidance * operation.ev_warranty / (ev.batterySize * ev.miles_driven_simulated)
                else:
                    be_miles = 0
                    be_battery_cost = 0
                self.ev_v2h_summaries.append(v2h_sum)
                self.v2h_effs.append(np.round(v2h_eff, 4))
                self.ev_avoidances = np.append(self.ev_avoidances, [np.round(avoidance, 2)])
                self.ev_co2_savings = np.append(self.ev_co2_savings, [np.round(co2_savings, 2)])
                self.gas_costs = np.append(self.gas_costs, [np.round(ev.miles_driven *
                                                                     ice.cost_per_mile(gas_cost=operation.cost_of_gas),
                                                                     2)])
                self.driving_costs = np.append(self.driving_costs, [np.round(ev.cost_of_driving, 2)])
                self.ev_degradations = np.append(self.ev_degradations, [np.round(degradation, 2)])
                self.ev_breakeven_miles = np.append(self.ev_breakeven_miles, [np.round(be_miles)])
                self.ev_breakeven_cost = np.append(self.ev_breakeven_cost, [np.round(be_battery_cost, 2)])
            self.fleet_avoidance = np.round(np.sum(self.ev_avoidances), 2)
            self.fleet_gas_costs = np.round(np.sum(self.gas_costs), 2)
            self.fleet_driving_costs = np.round(np.sum(self.driving_costs), 2)
            self.gas_savings = np.round(self.fleet_gas_costs - self.fleet_driving_costs, 2)
            self.fleet_co2_savings = np.round(np.sum(self.ev_co2_savings), 2)
            self.fleet_cost = np.round(fleet.fleet_cost(), 2)
        else:
            self.commute = np.nan
            self.ev_v2h_summaries = []
            self.v2h_effs = []
            self.ev_avoidances = 0
            self.fleet_avoidance = 0
            self.fleet_cost = 0
            self.gas_cost = 0
            self.fleet_gas_costs = 0
            self.driving_costs = 0
            self.fleet_driving_costs = 0
            self.gas_savings = 0
            self.ev_co2_savings = 0
            self.fleet_co2_savings = 0
            self.ev_degradations = np.array([0])
            self.ev_breakeven_miles = np.array([0])
            self.ev_breakeven_cost = np.array([0])

        self.total_avoidance = np.round(self.hes_avoidance + self.solar_avoidance + self.fleet_avoidance, 2)
        self.total_system_savings = np.round(self.total_avoidance + self.gas_savings, 2)
        self.is_baseline = (not hes.exists) & (not pv.exists) & (not fleet.V2H_enabled)
        self.hes_pv_cost = np.round(self.hes_cost + self.pv_cost, 2)
        self.system_cost = np.round(self.hes_pv_cost + self.fleet_cost, 2)

        # peak shaving effectiveness
        self.house_peak_usage = np.round(np.sum(house.energy_profile[np.where(tariff.tou_schedule[:, 1] == 1)]), 2)
        self.house_mid_usage = np.round(np.sum(house.energy_profile[np.where(tariff.tou_schedule[:, 1] == .5)]), 2)
        self.house_off_usage = np.round(np.sum(house.energy_profile[np.where(tariff.tou_schedule[:, 1] == 0)]), 2)

        self.grid_to_house_peak = np.round(np.sum(energy.grid_to_house[np.where(tariff.tou_schedule[:, 1] == 1)]), 2)
        self.grid_to_house_mid = np.round(np.sum(energy.grid_to_house[np.where(tariff.tou_schedule[:, 1] == .5)]), 2)
        self.grid_to_house_off = np.round(np.sum(energy.grid_to_house[np.where(tariff.tou_schedule[:, 1] == 0)]), 2)

        self.peak_shaving_effectiveness = np.round(1 - (self.grid_to_house_peak + self.grid_to_house_mid) / (
                self.house_peak_usage + self.house_mid_usage), 2)
        self.peak_shaving_effectiveness = np.round(self.peak_shaving_effectiveness * 100, 2)

        self.high_peak_shaving_effectiveness = np.round(1 - (self.grid_to_house_peak / self.house_peak_usage), 4) * 100

        # Extract unique component data (unique to each sim)
        self.time_data = timekeep.get_results_data()
        self.city_data = city.get_results_data()
        self.pv_data = pv.get_results_data()
        self.hes_data = hes.get_results_data()
        self.fleet_data = fleet.get_results_data()
        self.house_usage = house.usage
        self.utility = tariff.utility
        self.tariff_name = tariff.name
        self.energy_data = energy.get_results_data()

        do_sanity = False
        if do_sanity:
            system_in = energy.grid_out  # + energy.pv_out + energy.ev_out_total + energy.hes_out
            system_out_or_stored = energy.grid_in + energy.house_in + energy.loss
            if pv.exists:
                system_in += energy.pv_out
            if fleet.has_evs:
                system_in += energy.ev_out_total
                system_out_or_stored += energy.ev_in_total
            if hes.exists:
                system_in += energy.hes_out
                system_out_or_stored += energy.hes_in

            self.sanity = np.column_stack((system_in, system_out_or_stored, system_in - system_out_or_stored))
            self.check_sum = np.sum(self.sanity[:, 2])

    def add_objects(self, object_dict: dict):
        """
        Adds full sim objects to Results object
        Parameters
        ----------
        object_dict: dict
            A dictionary full of the objects required for sim
        Returns
        -------

        """
        # 'Tariff', not 'Operation' -- the old mapping stored the Operation object on self.tariff and
        # never restored self.energy at all, so a rehydrated Results had a broken tariff and no flows.
        self.operation = object_dict.get('Operation', self.operation)
        self.tariff = object_dict['Tariff']
        self.timekeep = object_dict['Timekeep']
        self.energy = object_dict.get('Energy', self.energy)
        self.city = object_dict['City']
        self.grid = object_dict['Grid']
        self.hes = object_dict['HES']
        self.pv = object_dict['PV']
        self.house = object_dict['House']
        self.fleet = object_dict['Fleet']

    def clear_objects(self):
        self.tariff = None
        self.timekeep = None
        self.energy = None
        self.city = None
        self.grid = None
        self.hes = None
        self.pv = None
        self.house = None
        self.fleet = None

    def add_row(self, row: pd.Series):
        self.input_row = row

    def add_time_elapsed(self, time_elapsed: float):
        self.time_elapsed = time_elapsed


def update_comp_status(operation: pm.Operation, fleet: cp.Fleet, hes: cp.HES, timekeep: pm.TimeKeep):
    """
    This method updates the sink/source/usability status of each of the components in the simulation base on
    circumstances and conditions at a given time.

    Parameters
    ----------
    operation : Operation
        An Operation object used in Simulation.
    fleet : Fleet
        A Fleet object containing all the EVS used in the simulation.
    hes : HES
        The home energy system (HES) object used in the simulation.
    timekeep : TimeKeep
        The Timekeep object used in the simulation.
    Returns
    -------
    None
    """
    # HES
    if hes.exists:
        if hes.soc >= hes.soc_max:  # hes is full, thus can only be a source
            hes.must_be_source_update(True)
        elif hes.soc <= hes.soc_min:  # hes is depleted, thus can only be a sink
            hes.must_be_sink_update(True)
        else:  # hes is somewhere between
            hes.can_be_sink_update(True)
            hes.can_be_source_update(True)

        if (timekeep.step >= hes.step_to_start_charging) and (timekeep.step < hes.next_deadline):
            hes.must_be_sink_update(hes.soc <= hes.soc_max)  # if hes is full, everything set to false

    # Fleet and EVs
    if fleet.has_evs:
        for ev in fleet.ev_list:
            if ev.is_here(timekeep.step - 1):
                ev.can_be_used_update(True)
                if operation.ev_as_source:
                    if ev.soc >= ev.soc_max:  # ev is full
                        ev.must_be_source_update(True)
                    elif ev.soc <= ev.soc_min:
                        ev.must_be_sink_update(True)
                    elif ev.soc <= ev.discharge_limit:  # ev is depleted past amount where ev-2-house is allowed
                        ev.can_be_sink_update(True)
                        ev.can_be_source_update(False)
                    else:
                        ev.can_be_sink_update(True)
                        ev.can_be_source_update(True)
                else:
                    ev.can_be_sink_update(True)
                    ev.can_be_source_update(False)
            else:
                ev.can_be_used_update(False)

    return None


def sinks_and_sources(operation: pm.Operation, fleet: cp.Fleet, pv: cp.PV, hes: cp.HES,
                      grid: cp.Grid, house: cp.House, timekeep: pm.TimeKeep):
    """
    This method classifies each component as an energy sink or an energy source depending on current conditions are and
    returns a list of the sinks and a list of the sources.

    Notes
    -----
    -   Sinks are sorted based on a preset priority, with House being first, EVs second, and HES third.
    -   Sources are sorted based on their cost of use (ie, whichever is the cheapest source of energy).
    -   All components other than EVs have an ID of 1. The ID for EVs will be their EViD parameter.

    Parameters
    ----------
    operation : Operation
        An Operation object used in Simulation.
    fleet : Fleet
        A Fleet object containing all the EVS used in the simulation.
    pv : PV
        The PV array object used in simulation.
    hes : HES
        The home energy system (HES) object used in the simulation.
    grid : Grid
        The Grid object used in simulation.
    house : House
        The House object used in simulation.
    timekeep : TimeKeep
        The Timekeep object used in the simulation.

    Returns
    -------
    sinks : list
        A list of the sinks for the current timestep with each element representing a component and being a list of
        the form [name, ID, energy required, priority]. Will be sorted based on priority.
    sources : list
        A list of the sources for the current timestep with each element representing a component and being a list of
        the form [name, ID, energy availability, priority (cost of use)]. Will be sorted based on priority,
        with the cheapest source being ranked first.

    """

    step = timekeep.step
    hours_per_step = timekeep.timestep / 60  # hoisted: was recomputed up to 4x per timestep

    sinks = []
    sources = []

    # PV -- appended before the grid so that, after a stable sort on equal priorities, PV still ranks first
    # (the net-metering block downstream relies on sources[0] being the PV when one exists).
    if pv.exists:
        pv_energy = pv.get_energy_available(step - 1, timekeep.timestep)
        if pv_energy > 0:  # only add to sources if it has energy
            sources.append([KIND_PV, 1, pv_energy, 0])

    # House
    sinks.append([KIND_HOUSE, 1, house.energy_required, house.sink_priority])

    # Grid
    sources.append([KIND_GRID, 1, np.inf, grid.cost_of_use])

    # HES
    if hes.exists:
        if hes.must_be_source:  # HES is full and can only be a source
            add_sink = False
            add_source = bool(hes.coverage_mask[step - 1])  # prescribed coverage period (from optimization)
        elif hes.must_be_sink:  # HES is depleted and must be a sink
            add_sink, add_source = True, False
        else:
            can_sink = hes.can_be_sink
            can_source = hes.can_be_source
            # If it can be either -- or, defensively, neither -- offer it as both and let whichever need
            # arises first claim it. This mirrors the original branch tree exactly.
            add_sink = can_sink or not can_source
            add_source = can_source or not can_sink
        if add_sink:
            hes_max_input = hes.charge_rate() * hours_per_step  # rated max energy input
            hes_cap_in = (hes.soc_max - hes.soc) * hes.batterySize  # max input based on remaining capacity
            sinks.append([KIND_HES, 1, min(hes_cap_in, hes_max_input), hes.sink_priority])
        if add_source:
            hes_cap_out = (hes.soc - hes.soc_min) * hes.batterySize  # max output based on remaining capacity
            hes_max_output = hes.max_discharge * hours_per_step  # rated max energy output
            sources.append([KIND_HES, 1, min(hes_cap_out, hes_max_output), hes.cost_of_use])

    # Fleet/ EVs
    if fleet.has_evs:
        ev_max_output = operation.ev_throughput * hours_per_step  # identical for every EV; hoisted out of the loop
        for ev in fleet.ev_list:
            if not ev.can_be_used:
                continue
            if ev.must_be_sink:
                add_sink, add_source = True, False
            elif ev.must_be_source:
                add_sink, add_source = False, True
            else:
                can_sink = ev.can_be_sink
                can_source = ev.can_be_source
                add_sink = can_sink or not can_source
                add_source = can_source or not can_sink
            if add_sink:
                ev_max_input = ev.charge_rate() * hours_per_step
                ev_cap_in = (ev.soc_max - ev.soc) * ev.batterySize
                sinks.append([KIND_EV, ev.EViD, min(ev_cap_in, ev_max_input), ev.sink_priority])
            if add_source:
                ev_cap_out = (ev.soc_max - ev.discharge_limit) * ev.batterySize
                # we must correct for negatives if discharge limit > soc
                sources.append([KIND_EV, ev.EViD, max(min(ev_max_output, ev_cap_out), 0), ev.cost_of_use])

    # Sort Sinks and Sources.
    # itemgetter is a C-level callable, so it avoids a Python frame per comparison. The length guards skip
    # the call entirely in the common case of a single sink (house only) or a single source (grid only).
    if len(sinks) > 1:
        sinks.sort(key=_priority)
    if len(sources) > 1:
        sources.sort(key=_priority)

    return sinks, sources


def energy_flows(operation: pm.Operation, fleet: cp.Fleet, pv: cp.PV, tariff: pm.Tariff, hes: cp.HES, grid: cp.Grid,
                 house: cp.House, timekeep: pm.TimeKeep, energy: cp.Energy, sinks: list, sources: list):
    """
    This method calculates and facilitates the energy flows between the components based on how they were sorted as
    sinks or sources.

    Parameters
    ----------
    operation : Operation
        An Operation object used in Simulation.
    fleet : Fleet
        A Fleet object containing all the EVS used in the simulation.
    pv : PV
        The PV array object used in simulation.
    tariff : Tariff
        The Tariff object used in simulation.
    hes : HES
        The home energy system (HES) object used in the simulation.
    grid : Grid
        The Grid object used in simulation.
    house : House
        The House object used in simulation.
    timekeep : TimeKeep
        The Timekeep object used in the simulation.
    energy : Energy
        The Energy object keeping track of energy flows for simulation.
    sinks : list
        A list of the sinks for the current timestep (see sinks_and_sources method).
    sources
        A list of the sinks for the current timestep (see sinks_and_sources method).
    Returns
    -------
    None

    """
    cell = [-1, -1]
    step = timekeep.step
    ev_list = fleet.ev_list
    efficiencies = operation.efficiencies
    for sink in sinks:
        sink_kind = sink[0]
        sink_id = sink[1]
        sink_energy = sink[2]

        for source in sources:
            source_kind = source[0]
            source_id = source[1]
            # source_energy = source[2]
            # source_cost_of_use = source[3]
            can_be_supplied = sink_energy > 0  # can only supply if sink needs/can fit more
            can_supply = False  # we assume source cannot provide until proven otherwise
            if (source[2] > 0) and can_be_supplied:  # source can only be used if it has energy
                if sink_kind == KIND_HOUSE:
                    if source_kind == KIND_PV:
                        cell = [KIND_PV, KIND_HOUSE]
                        can_supply = True
                    elif source_kind == KIND_HES:
                        if not hes.used_as_sink:
                            cell = [KIND_HES, KIND_HOUSE]
                            can_supply = True
                            hes.was_used_as_source()
                    elif source_kind == KIND_EV:
                        # EV can't be source if already used by sink, if currently off-peak,and if it will later have
                        # to charge at current grid rate
                        source_ev = ev_list[source_id - 1]
                        as_sink = source_ev.used_as_sink
                        deadline = min(source_ev.step_to_start_charging, timekeep.simu_end_step)
                        match_rate = tariff.get_tou_rate(step) == tariff.get_tou_rate(deadline)

                        if (not as_sink) and (not tariff.is_off_peak(step=step)) and (not match_rate):
                            cell = [KIND_EV, KIND_HOUSE]
                            can_supply = True
                            fleet.was_used_as_source(ev_id=source_id)
                    elif source_kind == KIND_GRID:
                        cell = [KIND_GRID, KIND_HOUSE]
                        can_supply = True
                        grid.was_used_as_source()
                elif sink_kind == KIND_EV:
                    sink_ev = ev_list[sink_id - 1]
                    if not sink_ev.used_as_source:
                        if source_kind == KIND_PV:
                            cell = [KIND_PV, KIND_EV]
                            can_supply = True
                        elif source_kind == KIND_HES:
                            if not hes.used_as_sink:
                                cell = [KIND_HES, KIND_EV]
                                can_supply = True
                                hes.was_used_as_source()
                        elif source_kind == KIND_EV:
                            can_supply = False  # no EV to EV functionality for now
                        elif source_kind == KIND_GRID:
                            # EV will only pull from grid during off-peak (or because it must meet departure deadline)
                            must_charge = (step >= sink_ev.step_to_start_charging) and (
                                    step < sink_ev.next_deadline)
                            if tariff.is_off_peak(step) or must_charge:
                                cell = [KIND_GRID, KIND_EV]
                                can_supply = True
                                grid.was_used_as_source()

                        if can_supply:
                            fleet.was_used_as_sink(ev_id=sink_id)

                elif sink_kind == KIND_HES:
                    if not hes.used_as_source:
                        if source_kind == KIND_PV:
                            cell = [KIND_PV, KIND_HES]
                            can_supply = True
                        elif source_kind == KIND_GRID:
                            # cannot charge from grid during peaks, and not until necessary during off-peak
                            if tariff.is_off_peak(step) and (
                                    step >= hes.step_to_start_charging) and tariff.is_tou:
                                cell = [KIND_GRID, KIND_HES]
                                can_supply = True
                                grid.was_used_as_source()
                        # HES->HES and EV->HES are not allowed, so they fall through with can_supply False
                        if can_supply:
                            hes.was_used_as_sink()

                else:
                    print('how did you get here?')

            # We now try and find the energy received by the sink, and sent by the source. Note that e_sent will
            # always be greater than e_received due to efficiency losses
            if can_supply:
                eff = efficiencies[cell[0], cell[1]]
                if source_kind == KIND_GRID:  # if source is grid, we supply the rest of the energy the sink can take
                    e_received = sink_energy
                    e_sent = sink_energy / eff
                    sink[2] = 0
                    sink_energy = 0
                else:  # source is either PV or HES
                    if source[2] * eff >= sink_energy:  # source can supply all sink needs
                        e_received = sink_energy
                        e_sent = e_received / eff
                        sink[2] = 0
                        sink_energy = 0
                        source[2] -= e_sent

                    else:  # source cannot supply all but can give some
                        e_received = source[2] * eff
                        e_sent = source[2]
                        sink_energy -= e_received
                        source[2] = 0

                energy.update_flow(timekeep=timekeep, cell=cell, energy_received=e_received, energy_sent=e_sent,
                                   sink_id=sink_id, source_id=source_id, operation=operation, hes=hes, fleet=fleet,
                                   pv=pv, grid=grid, house=house)

    # Net Metering: if pv exists and still has energy after all sinks have been supplied. Then we can push it back to
    # the grid. If PV exists it will always be first on the source list. And can only supply energy if there is
    # energy left

    if (sources[0][0] == KIND_PV) and (sources[0][2] > 0):
        cell = [KIND_PV, KIND_GRID]
        eff = efficiencies[cell[0], cell[1]]
        source_id = 1
        sink_id = 1
        e_sent = sources[0][2]
        e_received = e_sent * eff
        energy.update_flow(timekeep=timekeep, cell=cell, energy_received=e_received, energy_sent=e_sent,
                           sink_id=sink_id, source_id=source_id, operation=operation, hes=hes, fleet=fleet,
                           pv=pv, grid=grid, house=house)

    # Update soc arrays for hes and ev for record

    energy.update_components(timekeep=timekeep, hes=hes, fleet=fleet)

    # reset component use
    if hes.exists:
        hes.reset_sink_source()
        hes.status_reset()

    if fleet.has_evs:
        for ev in fleet.ev_list:
            if ev.used_as_source:
                step_start_charge = tariff.next_off
                if ev.charging_scheme == "trickle charge":
                    ev.trickle_charge_curve = ev.trickle_charge(ev.next_deadline - step_start_charge)
                ev.update_charging_step(target_soc=ev.soc_max, timestep=timekeep.timestep, next_off=tariff.next_off)
            ev.status_reset()
        fleet.reset_sink_source()


def optimize_hes(operation: pm.Operation, tariff: pm.Tariff, fleet: cp.Fleet, pv: cp.PV, hes: cp.HES, house: cp.House,
                 timekeep: pm.TimeKeep):
    """
    This method calculates the desired HES target state-of-charge (SoC) to charge to in order to cover an eminent peak
    period based on a user-input optimization scheme. It will then update the HES with this value.

    Notes
    -----
    -   A 'perfect' optimization scheme will calculate an exact state-of-charge which will maximize profit. This
        method is still under development.
    -   A 'simple' optimization scheme will calculate the desired SoC using the difference between house load and
        solar energy for the period to be covered by the HES. This scheme is the default.
    -   A 'flat' optimization scheme will simply set the desired target to 80%. Further updates will have this be a
        user controlled parameter. This is the least calculation intensive option at the cost of profit.
    -   A 'full charge' scheme will simply fully charge the HES to its SoC max (usually 100%). Depending on the net
        metering scheme, this runs the risk of being unable to capture excess solar energy which may be more profitable
        to keep than to send back to grid.

    Parameters
    ----------
    operation : Operation
        An Operation object used in Simulation.
    tariff : Tariff
        The Tariff object used in simulation.
    fleet : Fleet
        A Fleet object containing all the EVS used in the simulation.
    pv : PV
        The PV array object used in simulation.
    hes : HES
        The home energy system (HES) object used in the simulation.
    house : House
        The House object used in simulation.
    timekeep : TimeKeep
        The Timekeep object used in the simulation.

    Returns
    -------
    None
    """
    periods = list(tariff.return_periods(tariff.end_of_current + 1, min(tariff.next_off - 1, timekeep.simu_end_step)))
    periods.sort(key=lambda x: (-x[4], -x[3]))

    # Below block to be fleshed out later
    if operation.hes_optimization in ['Perfect', 'perfect']:
        print('tbd')
        if fleet.has_evs:
            print('tbd')

    elif operation.hes_optimization in ['simple', 'Simple']:  # house load minus pv in, ignore ev
        # Collect step ranges in a list and concatenate once. np.append in a loop reallocates and copies the
        # whole array on every iteration.
        coverage_parts = []
        hours_per_step = timekeep.timestep / 60
        hes_cap_left = hes.free_cap * operation.efficiencies[0, 5]
        latest_peak = 0  # position of the latest peak period
        earliest_peak = 0  # position of the earliest peak period (will equal the latest if only one peak period
        for per in periods:
            pv_in = np.sum(pv.power[(per[1] - 1): (per[2] - 1)]) * hours_per_step
            house_need = np.sum(house.load_profile[(per[1] - 1): (per[2] - 1)]) * hours_per_step
            e_needed = house_need - pv_in
            if per[4] == 1:  # period is on-peak, and thus is automatically added
                hes_cap_left -= e_needed
                hes_cap_left = max(hes_cap_left, 0)
                coverage_parts.append(np.arange(per[1], per[2] + 1, dtype=np.int64))
                latest_peak = max(latest_peak, per[0])
                earliest_peak = min(earliest_peak, per[0])
            elif operation.hes_cover_mid:  # period is mid-peak, but mid-peak coverage is enabled
                #  only add if there is energy left to provide or if last period of non-off-peak region
                if hes_cap_left > e_needed:  # hes has cap left to cover
                    hes_cap_left -= e_needed
                    hes_cap_left = max(hes_cap_left, 0)
                    coverage_parts.append(np.arange(per[1], per[2] + 1, dtype=np.int64))
                else:  # hes does not have capacity left to cover period in full
                    # in this case, we can only cover periods after the latest peak period lest we run out of energy
                    # for upcoming peak period
                    if per[0] > latest_peak:
                        hes_cap_left = 0
                        coverage_parts.append(np.arange(per[1], per[2] + 1, dtype=np.int64))
        coverage_steps = np.concatenate(coverage_parts) if coverage_parts else np.zeros(0, dtype=np.int64)
        hes.update_coverage_steps(coverage_steps)
        target_soc = hes.soc_min + (hes.free_cap - hes_cap_left) / hes.batterySize
        hes.update_soc_to_reach(target_soc=target_soc)

    elif operation.hes_optimization in ['flat', 'Flat']:
        target_soc = min(.8, hes.soc_max) if pv.exists else hes.soc_max  #if no pv then might as well charge fully
        hes.update_soc_to_reach(target_soc)
        hes.update_coverage_steps(tariff.get_coverage_steps(step=timekeep.step, operation=operation))

    elif operation.hes_optimization in ['Full Charge', 'full charge']:
        hes.update_soc_to_reach(hes.soc_max)
        hes.update_coverage_steps(tariff.get_coverage_steps(step=timekeep.step, operation=operation))

    return None


def manage_fleet(step: int, fleet: Fleet, hes: HES, house: House, pv: PV, tariff: Tariff, timekeep: TimeKeep) -> None:
    for ev in fleet.ev_list:
        if not ev.is_here(timekeep.index):  # ev is not here
            if (step != timekeep.simu_start_step) and (ev.is_here(timekeep.index - 1)):  # ev just departed
                ev.drive_miles(ev.driving_pattern[timekeep.index, 2])
                ev.next_arrival(index=timekeep.index, update=True)
                ev.trickle_charge_curve = 0
        else:  # ev is here
            start_of_sim = step == timekeep.simu_start_step  #  sim just started
            just_arrived = (not start_of_sim) and (not ev.is_here(timekeep.index - 1))
            needs_update = step == ev.next_update
            if just_arrived or needs_update:  # ev just returned or needs update
                update_deadline = True
                if just_arrived: ev.next_departure(index=timekeep.index, update=True)
                end_of_current = tariff.get_end_of_period(step=timekeep.step)
                dept_in_current = ev.next_dept < end_of_current
                if (ev.next_dept == timekeep.num_steps + 1):  # no more departures or stay at home case
                    if end_of_current == tariff.end: # this is last period
                        deadline = ev.next_dept
                    else:
                        deadline = end_of_current if tariff.is_currently_off else (tariff.get_end_of_period(tariff.next_off))

                    step_start_charge = timekeep.step if tariff.is_currently_off else tariff.next_off
                    ev.next_update = timekeep.step if tariff.is_currently_off else tariff.next_off

                elif dept_in_current:  # not end of sim, departure occurs in same period as it just arrived
                    next_dept_is_offpeak = tariff.is_off_peak(step=ev.next_dept)
                    if next_dept_is_offpeak:  # ev arrives and leaves all within the same off-peak period
                        deadline = ev.next_dept
                        step_start_charge = timekeep.step
                    else:  # ev arrives and leaves all within same peak (not off) period (needs expounding)
                        next_miles = ev.driving_pattern[(ev.next_dept - 1), 1]
                        kwh_needed = next_miles * ev.kwhpm_comb  # amount of energy needed to make trip
                        if kwh_needed < ev.current_cap:  # ev has enough juice to make the trip, so don't charge
                            update_deadline = False
                            deadline = None
                            step_start_charge = None
                        else:  # ev doesn't have enough to make trip. must charge regardless.
                            step_start_charge = timekeep.step
                            deadline = ev.next_dept

                else:  # we haven't reached end of sim, departure occurs in different period.
                    next_dept_is_offpeak = tariff.is_off_peak(step=ev.next_dept)
                    if next_dept_is_offpeak & tariff.is_currently_off:  # arr and dept in two diff off-peaks
                        deadline = end_of_current
                        step_start_charge = timekeep.step
                        ev.next_update = tariff.next_off  # tariff.next_off will have already been updated under HES opt
                    elif next_dept_is_offpeak & (not tariff.is_currently_off):  # arr in peak/midpeak, dept in off-peak
                        step_start_charge = tariff.next_off
                        end_of_next_off = tariff.get_end_of_period(step=tariff.next_off)
                        deadline = min(ev.next_dept, end_of_next_off)
                        if ev.next_dept > end_of_next_off:  # EV presence straddles over a peak period
                            ev.next_update = tariff.get_next_off_peak(end_of_next_off + 1)  # start of following off
                            # period
                    elif (not next_dept_is_offpeak) & tariff.is_currently_off:  # arr in off, dept in peak/midpeak
                        step_start_charge = timekeep.step
                        deadline = end_of_current
                        if tariff.next_off < ev.next_dept:  # EV presence straddles at least one peak period.
                            ev.next_update = tariff.next_off
                    elif (not next_dept_is_offpeak) & (not tariff.is_currently_off):  # arr peak/mid, dept in diff peak
                        step_start_charge = tariff.next_off
                        end_of_next_off = tariff.get_end_of_period(step=tariff.next_off)
                        deadline = end_of_next_off
                        next_next_off = tariff.get_next_off_peak(step=deadline+1, update=False)
                        if ev.next_dept > next_next_off: # EV departs in peak after next, so EV straddles next peak.
                            ev.next_update = next_next_off
                    else:  # shouldn't get here but pycharm gets upset.
                        step_start_charge = tariff.next_off
                        end_of_next_off = tariff.get_end_of_period(step=tariff.next_off)
                        deadline = end_of_next_off
                if update_deadline:
                    ev.update_deadline(deadline)
                    if ev.next_deadline < len(ev.driving_pattern):
                        if ev.charging_scheme == "trickle charge":
                            ev.trickle_charge_curve = ev.trickle_charge(ev.next_deadline - step_start_charge)
                        ev.update_charging_step(target_soc=ev.soc_max, timestep=timekeep.timestep,
                                                next_off=tariff.next_off)
                # if ev.next_dept == timekeep.num_steps + 1:  # we've reached end of sim
                #     deadline = ev.next_dept
                # elif tariff.is_off_peak(ev.next_dept):  # departure occurs during off-peak, so it becomes
                #     # deadline
                #     deadline = ev.next_dept
                # else:  # departure occurs during a non-off peak, so we try to set deadline to end of off-peak
                #     if not tariff.is_currently_off:
                #         end_of_next_off = tariff.get_end_of_period(step=tariff.next_off)
                #         deadline = min(ev.next_dept, end_of_next_off)  # deadline is end of next off or next
                #         # departure, whichever comes first.
                #     else:
                #         deadline = tariff.end_of_current
                # ev.update_deadline(deadline)
                # if ev.next_deadline < len(ev.driving_pattern):
                #     if ev.charging_scheme == "trickle charge":
                #         ev.trickle_charge_curve = ev.trickle_charge(ev.next_deadline - tariff.next_off)
                #     ev.update_charging_step(target_soc=ev.soc_max, timestep=timekeep.timestep,
                #                             next_off=tariff.next_off)


def run_simulation(operation: pm.Operation, city: pm.City, tariff: pm.Tariff, fleet: cp.Fleet, ice: cp.ICE, pv: cp.PV,
                   hes: cp.HES, grid: cp.Grid, house: cp.House, timekeep: pm.TimeKeep,
                   full_results: bool = False) -> Results:
    """
    This method serves as the overall method for running the simulation, utilizing the various sub-methods described
    in this file and other imported files. Its input consists of all the Component and Parameter objects necessary
    for the simulation to run.

    Parameters
    ----------
    operation : Operation
        An Operation object used in Simulation.
    city : City
        A City object representing the household location for the simulation.
    tariff : Tariff
        The Tariff object used in simulation.
    fleet : Fleet
        A Fleet object containing all the EVS used in the simulation.
    ice : ICE
        An ICE object for the EVs in the fleet to be compared to for gas savings calculation.
    pv : PV
        The PV array object used in simulation.
    hes : HES
        The home energy system (HES) object used in the simulation.
    grid : Grid
        The Grid object used in simulation.
    house : House
        The House object used in simulation.
    timekeep : TimeKeep
        The Timekeep object used in the simulation.

    Returns
    -------
    results : Results
        A Results object containing all the composite objects for the simulation as well as a variety of
        performance metrics for the household.

    """
    daily_rates = tariff.get_daily_rates(day=timekeep.starting_day)
    # Initialize costs of use and states of charge for components
    grid.update_emissivity(timekeep.simu_start_step)
    grid.initialize_cost_of_use(min(daily_rates), efficiency=1, cost_of_use_track=True, num_steps=timekeep.num_steps)

    if hes.exists:
        hes.initialize_cost_of_use(tou_cost=min(daily_rates), efficiency=operation.efficiencies[4, 1],
                                   cost_of_use_track=operation.track_costs_of_use, num_steps=timekeep.num_steps)
        hes.initialize_emissivity(grid_intensity=grid.emissivity, efficiency=operation.efficiencies[4, 1],
                                  num_steps=timekeep.num_steps)
        hes.initialize_socs(num_steps=timekeep.num_steps)

    if fleet.has_evs:
        fleet.initialize_socs(num_steps=timekeep.num_steps)
        if operation.do_dcfc:
            fleet.initialize_cost_of_use(tou_cost=min(daily_rates), efficiency=operation.efficiencies[4, 3],
                                         cost_of_use_track=operation.track_costs_of_use, num_steps=timekeep.num_steps)
            fleet.initialize_emissivity(grid_intensity=grid.emissivity, efficiency=operation.efficiencies[4, 3],
                                        num_steps=timekeep.num_steps)
        else:
            fleet.initialize_cost_of_use(tou_cost=min(daily_rates), efficiency=operation.efficiencies[4, 2],
                                         cost_of_use_track=operation.track_costs_of_use, num_steps=timekeep.num_steps)
            fleet.initialize_emissivity(grid_intensity=grid.emissivity, efficiency=operation.efficiencies[4, 2],
                                        num_steps=timekeep.num_steps)
    grid.initialize_cost_of_use(tou_cost=tariff.get_tou_rate(timekeep.simu_start_step)[0], efficiency=1,
                                cost_of_use_track=operation.track_costs_of_use, num_steps=timekeep.num_steps)

    # initialize necessary variables

    house.initialize_energy_profile(num_steps=timekeep.num_steps)  # to keep track of house energy requirements

    hes.initialize_coverage_mask(num_steps=timekeep.num_steps)

    if tariff.is_off_peak(step=timekeep.simu_start_step):  # start on off-peak

        start_of_next = tariff.get_end_of_period(timekeep.simu_start_step, update=True) + 1

        next_off = tariff.get_next_off_peak(start_of_next, update=True)
        coverage = np.linspace(start_of_next, next_off - 1, (next_off - start_of_next), dtype=int)
        if hes.exists:
            hes.overwrite_soc(.5)
            hes.update_deadline(start_of_next)
            hes.update_soc_to_reach(1)
            hes.update_charging_step(hes.soc_to_reach)
    else:  # start not off-peak (probably mid)
        next_off = tariff.get_next_off_peak(timekeep.simu_start_step, update=True)
        coverage = np.linspace(timekeep.simu_start_step, next_off - 1, (next_off - timekeep.simu_start_step), dtype=int)
        if hes.exists:
            hes.overwrite_soc(.8)
            hes.update_soc_to_reach(.8)

    hes.update_coverage_steps(coverage)

    energy = cp.Energy(op=operation, tk=timekeep, fleet=fleet, hes=hes)

    # Iterate through timesteps
    for step in range(timekeep.simu_start_step, timekeep.simu_end_step + 1):

        tou_rate, _peak_value = tariff.get_tou_rate(timekeep.step)  # peak value unused here

        grid.update_cost_of_use(index=timekeep.e_index, tou_rate=tou_rate)
        grid.update_emissivity(step=timekeep.step)

        house.get_energy_required(index=timekeep.index)
        house.record_energy(index=timekeep.e_index)
        pv.get_energy_available(index=timekeep.index)

        # HES Optimization
        if timekeep.step == tariff.next_off:
            #  time between current and next off periods comprises the possible times that HES discharge is allowed
            tariff.get_next_off_peak(step=timekeep.step, update=True)  # we ascertain start of next off period
            tariff.get_end_of_period(step=timekeep.step, update=True)  # we update end of current off period

            #  we only optimize if HES exists and if before end of sim
            if hes.exists and tariff.next_off < timekeep.simu_end_step:
                hes.update_deadline(tariff.end_of_current)  # HES must be charged by end of current off period
                if operation.hes_optimization not in ['None', 'none']:
                    optimize_hes(operation=operation, tariff=tariff, fleet=fleet, pv=pv, hes=hes, house=house,
                                 timekeep=timekeep)

                else:  # no hes optimization
                    hes.update_soc_to_reach(hes.soc_min)
                    hes.update_coverage_steps(tariff.get_coverage_steps(step=timekeep.step, operation=operation))

                hes.update_charging_step(hes.soc_to_reach)

        # EV Fleet Management
        if fleet.has_evs:
            manage_fleet(step=step, fleet=fleet, hes=hes, house=house, pv=pv, tariff=tariff, timekeep=timekeep)


        # Sinks and Sources
        update_comp_status(operation=operation, fleet=fleet, hes=hes, timekeep=timekeep)
        sinks, sources = sinks_and_sources(operation=operation, fleet=fleet, pv=pv, hes=hes,
                                           grid=grid, house=house,
                                           timekeep=timekeep)

        # Calculate and record energy flows
        energy_flows(operation=operation, fleet=fleet, pv=pv, tariff=tariff, hes=hes, grid=grid, house=house,
                     timekeep=timekeep, energy=energy, sinks=list(sinks), sources=list(sources))

        # Increment the timestep and update time variables
        if step == timekeep.hour_end_step:
            timekeep.update_hour()

        if step == timekeep.day_end_step:
            timekeep.update_day()

        timekeep.increment_step()

    # Steps have been iterated through, now we finalize any components and summarize results into Bill and Results.
    hes.trim_soc_targets()

    results = Results(operation=operation, tariff=tariff, timekeep=timekeep, city=city, grid=grid, energy=energy,
                      hes=hes, pv=pv, house=house, fleet=fleet, ice=ice, full_results=full_results)

    return results


def check_resolution(resolution):
    options = [1, 5, 10, 15, 20, 30, 60]
    if resolution not in options:
        if (type(resolution) not in [int, float]) or np.isnan(resolution):
            resolution = 5
        else:  # resolution is a number, but just not a supported one, so we find the closest option
            resolution = min(options, key=lambda x: abs(x - resolution))

    return resolution


def make_timekeep(time_dict: dict, resolution=5):
    #  this takes the time-related scenario variables and makes a timekeep object

    if not pd.isna(time_dict['Start Date']):  # we check if start date is provided
        if not pd.isna(time_dict['End Date']):
            time_keeper = pm.TimeKeep(from_date=True, start_date=time_dict['Start Date'],
                                      end_date=time_dict['End Date'], timestep=resolution)
        elif not pd.isna(time_dict['Sim Days']):
            time_dict['End Date'] = time_dict['Start Date'] + pd.Timedelta(str(time_dict['Sim Days']))
            time_keeper = pm.TimeKeep(from_date=True, start_date=time_dict['Start Date'],
                                      end_date=time_dict['End Date'], timestep=resolution)
        else:  # we assume that sim runs until end of year
            time_dict['End Date'] = pd.Timestamp('12/31/' + str(time_dict['Start Date'].year))
            time_keeper = pm.TimeKeep(from_date=True, start_date=time_dict['Start Date'],
                                      end_date=time_dict['End Date'], timestep=resolution)
    else:  # start date is not given
        if not pd.isna(time_dict['End Date']):  # but end date is given somehow
            if not pd.isna(time_dict['Start Day']):  # we see if starting DOY is given
                time_dict['Start Date'] = time_dict['End Date'] - pd.Timedelta(str(time_dict['End Date'].day_of_year -
                                                                                   time_dict['Start Day']) + ' days')
                if time_dict['End Date'] < time_dict['Start Date']:  # we correct if start DOY is later than end date
                    time_dict['Start Date'] = pd.Timestamp('1/1/' + str(time_dict['End Date'].year))  # correct to 1/1
                time_keeper = pm.TimeKeep(from_date=True, start_date=time_dict['Start Date'],
                                          end_date=time_dict['End Date'], timestep=resolution)
            elif not pd.isna(time_dict['Sim Days']):  # we see if simulation days are given and we count backwards
                time_dict['Start Date'] = time_dict['End Date'] - pd.Timedelta(str(time_dict['Sim Days'] - 1) + 'days')
                time_keeper = pm.TimeKeep(from_date=True, start_date=time_dict['Start Date'],
                                          end_date=time_dict['End Date'], timestep=resolution)
            else:  # in absence of other information, we assume that start date is Jan 1st of same year.
                time_dict['Start Date'] = pd.Timestamp('1/1/' + str(time_dict['End Date'].year))
                time_keeper = pm.TimeKeep(from_date=True, start_date=time_dict['Start Date'],
                                          end_date=time_dict['End Date'], timestep=resolution)
        else:  # neither date is given
            if pd.isna(time_dict['Year']) or (type(time_dict['Year']) not in [int, float]):
                time_dict['Year'] = 2018  # we default year to 2018
            if pd.isna(time_dict['Start Day']) | (type(time_dict['Start Day']) not in [int, float]):
                time_dict['Start Day'] = 1
            if pd.isna(time_dict['Sim Days']) | (type(time_dict['Sim Days']) not in [int, float]):
                time_dict['Sim Days'] = 365
            time_keeper = pm.TimeKeep(from_date=False, starting_day=time_dict['Start Day'],
                                      simu_days=time_dict['Sim Days'], year=time_dict['Year'], timestep=resolution)
    return time_keeper


def rows_match(old_row: Optional[pd.Series], new_row: pd.Series, options: list) -> bool:
    """
    Returns whether the given columns match between two scenario rows.

    Two values match if they are equal, or if BOTH are missing. The previous implementation tested
    ``np.isnan(new_row[col]) and np.isnan(new_row[col])`` -- new_row against itself -- so any NaN in the
    new row declared a match regardless of the old row's value, and get_reset_dict then reused a
    component that should have been rebuilt.

    Parameters
    ----------
    old_row : pandas.Series or None
        The previous scenario's row. None on the first scenario.
    new_row : pandas.Series
        The current scenario's row.
    options : list
        Column names to compare.

    Returns
    -------
    bool
        True when every listed column matches.
    """
    if old_row is None:
        return False
    for col in options:
        new_val = new_row[col]
        old_val = old_row[col]
        if new_val == old_val:
            continue
        try:
            both_missing = np.isnan(new_val) and np.isnan(old_val)
        except TypeError:
            both_missing = pd.isna(new_val) and pd.isna(old_val)
        if not both_missing:
            return False
    return True


def get_reset_dict(old_row: Optional[pd.Series], new_row: pd.Series) -> dict:
    # this function returns a dictionary full of booleans which tells the model to use the same components as the
    # previous scenario or to load new ones

    reset_dict = {'New Timekeep': True,
                  'New City': True,
                  'New House': True,
                  'New Tariff': True,
                  'New Grid': True,
                  'New PV': True,
                  'New HES': True,
                  'New Fleet': True}

    if old_row is not None:  # we pass none on the very first scenario
        # first we see if we need new timekeep variable, if so we reset every component which relies on it.
        if new_row['User File'] == old_row['User File']:
            reset_dict['New Timekeep'] = False  # user provided file is same so no need to change
            reset_dict['New House'] = False
        elif (new_row['Start Date'] == old_row['Start Date']) and (new_row['End Date'] == old_row['End Date']):
            reset_dict['New Timekeep'] = False  # dates match so no need to change
            reset_dict['New House'] = ~(new_row['Load Amount'] == old_row['Load Amount'])
        else:
            opt = ['Start Date', 'End Date', 'Year', 'Simulation Days', 'Start Day']
            reset_dict['New Timekeep'] = not rows_match(old_row=old_row, new_row=new_row, options=opt)
            reset_dict['New House'] = not (new_row['Load Amount'] == old_row['Load Amount'])

        # We check if we have to make new city object
        if new_row['Zip Code'] == old_row['Zip Code']:
            reset_dict['New City'] = False
        elif (new_row['State'] == old_row['State']) and (new_row['City'] == old_row['City']):
            reset_dict['New City'] = False

        # We check other components should we not have to change timekeep object
        # (otherwise we change the rest by default)
        if not reset_dict['New Timekeep']:
            # check Tariff object
            opt = ['Utility Name', 'Utility File', 'Tariff ID']
            reset_dict['New Tariff'] = not rows_match(old_row=old_row, new_row=new_row, options=opt)

            # Check grid object
            opt = ['Use Cambium', 'Other File']
            opt += [c for c in ('Use WattTime', 'WattTime Year') if c in new_row.index and c in old_row.index]
            reset_dict['New Grid'] = not rows_match(old_row=old_row, new_row=new_row, options=opt)

            # Check PV Object
            opt = ['Other Solar File', 'System Size (kW)', 'PV Brand', 'PV Model']
            reset_dict['New PV'] = not rows_match(old_row=old_row, new_row=new_row, options=opt)

            # Check HES Object
            opt = ['Size (kWh)', 'HES Min SoC', 'HES Max SoC', 'Optimization']
            reset_dict['New HES'] = not rows_match(old_row=old_row, new_row=new_row, options=opt)

            # Check EV/Fleet

            if old_row['EV File'] == new_row['EV File']:
                reset_dict['New Fleet'] = False
            else:
                opt = ['Discharge Limit', 'EV Min SoC', 'EV Max SoC', 'EV Year', 'Make', 'Model', 'Trim', 'Pattern',
                       'Qty', 'Charge Type']
                reset_dict['New Fleet'] = not rows_match(old_row=old_row, new_row=new_row, options=opt)

        # the tariff, house load pool, grid emissions profile and reference solar are all built from the city,
        # so none of them can carry over to a different one
        if reset_dict['New City']:
            for comp in ('New Tariff', 'New House', 'New Grid', 'New PV'):
                reset_dict[comp] = True
    return reset_dict


def make_operation(new_row: pd.Series, collection_name):
    scen_id = new_row['ScenarioID']
    opt_method = new_row['Optimization']
    net_meter_method = new_row['Net Meter Type']

    user_file = new_row['User File']

    if pd.isna(user_file):
        user_profile_given = False
    else:
        if os.path.exists('City Data/Load Profiles/User Profiles/' + user_file + '.csv'):
            user_profile_given = True
        else:
            user_profile_given = False

    operation = pm.Operation(ev_discharge_limit=new_row['Discharge Limit'], simu_name=collection_name,
                             simu_id=str(scen_id),
                             hes_optimization=opt_method, net_meter_scheme=net_meter_method,
                             user_profile=user_profile_given)


def make_city(new_row: pd.Series):
    # pass row to make a new city object
    zipcode = new_row['Zip Code']
    if not np.isnan(int(zipcode)):  # file is given a zip code, which overrides city and state entry.
        new_city = sp.create_city(zipcode=zipcode)
    else:  # file is given by city and state entry, which must match a city in reference list
        city_name = new_row['City']
        state_name = new_row['State']
        new_city = sp.create_city(name=city_name, st_abr=state_name, from_zip=False)
    return new_city


def make_tariff(new_row: pd.Series, ref_city: pm.City, timekeep: pm.TimeKeep):
    # pass current row and city object to make tariff object
    util_file = new_row['Utility File']
    util_name = new_row['Utility Name']
    tariff_id = new_row['Tariff ID']
    if not pd.isnull(util_file):  # util file is provided
        util_name = util_file.split('_')[0]
        if util_name in (ref_city.utilities + ['Custom']):  # we make sure the utility one available in city or Custom
            if not pd.isnull(tariff_id):  # tariff id is provided
                new_tariff = sp.create_tariff(util_file=util_file, tariff_name=tariff_id)
            else:  # tariff id is not provided
                new_tariff = sp.create_tariff(util_file=util_file)
        else:  # util is not in list, so we resort to first utility listed in city
            util_name = ref_city.utilities[0]
            new_tariff = sp.create_tariff(util_name=util_name)
    elif not pd.isnull(util_name):  # without util file we fall back to util name being listed
        if util_name in ref_city.utilities:  # we make sure the utility one available in city
            if not pd.isnull(tariff_id):  # tariff id is provided
                new_tariff = sp.create_tariff(util_name=util_name, tariff_name=tariff_id)
            else:  # tariff id is not provided
                new_tariff = sp.create_tariff(util_name=util_name)
        else:  # util is not in list, so we resort to first utility listed in city
            util_name = ref_city.utilities[0]
            new_tariff = sp.create_tariff(util_name=util_name)
    else:  # neither util file nor name have been provided, default to city list
        new_tariff = sp.create_tariff(util_name=ref_city.utilities[0])

    if not pd.isnull(new_row['Net Meter Type']):
        new_tariff.update_net_met_policy(new_row['Net Meter Type'])

    new_tariff.create_tou_schedule(timekeep.calendar)
    return new_tariff


def make_house(new_row: pd.Series, ref_city: pm.City, op: pm.Operation,
               user_dataframe: Optional[pd.DataFrame] = None) -> House:
    load_file = new_row['Load File']
    load_amount = new_row['Load Amount']

    if op.user_profile:
        summary = dp.monthly_load_summary(user_dataframe)
        load_profile = dp.load_match_monthly(state=ref_city.matched_state, city=ref_city.matched_city, summary=summary)
        load_profile = dp.normalize_profile_hourly(original=load_profile,
                                                   normalizer=user_dataframe['Usage (kWh)'].to_numpy())
        new_house = House(load_profile=load_profile)
    # find_load_profile resolves a stem to whichever format exists, preferring the compact .npz, so a
    # scenario's 'Load File' column keeps working whether the profile has been converted or not.
    elif not pd.isnull(load_file) and dp.find_load_profile(dp.custom_loads_path + load_file):
        new_house = House(load_file=dp.find_load_profile(dp.custom_loads_path + load_file))
    elif not np.isnan(load_amount):
        # check if load file already exists with that usage amount
        potential_stem = f'{dp.custom_loads_path}{ref_city.matched_state}_{ref_city.matched_city}_{load_amount}kWh'
        existing = dp.find_load_profile(potential_stem)
        if existing:
            new_house = House(load_file=existing)
        else:
            new_house = House(
                load_profile=dp.load_match_yearly(state=ref_city.matched_state, city=ref_city.matched_city,
                                                  usage=load_amount, save_profile=save_loads))
    else:  # we assume basic US average usage
        new_house = House(load_profile=dp.load_match_yearly(state=ref_city.matched_state, city=ref_city.matched_city,
                                                            usage=11000, save_profile=save_loads))
    return new_house


def make_grid(new_row: pd.Series, ref_city: pm.City, tk: pm.TimeKeep):
    # provide current row and reference city to create grid object
    use_cambium = new_row['Use Cambium']
    use_wattime = ('Use WattTime' in new_row.index and not pd.isnull(new_row['Use WattTime'])
                   and bool(new_row['Use WattTime']))
    other_emissions_file = new_row['Other File']
    wattime_year = WATTTIME_DEFAULT_YEAR

    if use_cambium:
        emissions_file = ref_city.matched_state + '_Cambium_2022.csv'
        new_grid = Grid(emission_file='City Data/CO2 Profiles/Cambium 2021/Processed/' + emissions_file)
    elif use_wattime:
        if not ref_city.matched_wattime_region:
            raise Exception(f"'Use WattTime' is set for {ref_city.matched_city}, {ref_city.matched_state} but it "
                            f"has no resolved WattTime region -- run 'Resolve All Regions' (or a Single City "
                            f"fetch) for it in the Data Import Wizard's WattTime tab first.")
        if 'WattTime Year' in new_row.index and not pd.isnull(new_row['WattTime Year']):
            wattime_year = int(new_row['WattTime Year'])
        # a region can straddle a UTC-offset boundary (eg SOCO spans CST Alabama and EST Georgia), so the
        # matched reference city's own timezone (not just its region) picks the correctly-localized file.
        emissions_file = f'{ref_city.matched_wattime_region}_{ref_city.time_zone}_WattTime_{wattime_year}.csv'
        new_grid = Grid(emission_file='City Data/CO2 Profiles/WattTime/Processed/' + emissions_file)
    elif not pd.isnull(other_emissions_file):
        custom_path = 'City Data/CO2 Profiles/Custom/' + other_emissions_file
        wattime_path = 'City Data/CO2 Profiles/WattTime/Processed/' + other_emissions_file
        if os.path.exists(custom_path):
            new_grid = Grid(emission_file=custom_path)
        elif os.path.exists(wattime_path):
            new_grid = Grid(emission_file=wattime_path)
        else:  # file doesn't exist. default to city flat rate
            new_grid = Grid(flat_emission_rate=ref_city.carbon_intensity)
    else:
        new_grid = Grid(flat_emission_rate=ref_city.carbon_intensity)

    if use_wattime:
        # WattTime profiles are a real dated calendar year (not Cambium's "typical year" pattern), so they're
        # aligned to the simulation's dates by day-of-week shift (cambium=False) using their actual fetch year.
        new_grid.change_dates(start_date=tk.start_date, end_date=tk.end_date, cambium=False, file_year=wattime_year)
    else:
        new_grid.change_dates(start_date=tk.start_date, end_date=tk.end_date, cambium=use_cambium)

    return new_grid


_solar_fallback_warned = set()


def reference_solar_file(state: str, city: str) -> str:
    """
    Returns the path of a reference city's 5-min solar profile, preferring 2018 (the weather year behind the
    ResStock AMY2018 house loads, so PV output and load stay weather-coincident) and otherwise falling back to
    the most recent non-leap year on disk. Leap years are excluded because PV.load_solar indexes the profile by
    day of year assuming 365 days.
    """
    ghi_dir = 'City Data/Solar Data/' + state + '/'
    preferred = ghi_dir + state + '_' + city + '_GHI_2018_5min.csv'
    if os.path.exists(preferred):
        return preferred

    prefix, suffix = state + '_' + city + '_GHI_', '_5min.csv'
    years = []
    if os.path.isdir(ghi_dir):
        for f in os.listdir(ghi_dir):
            name = f[len(prefix):-len(suffix)]
            if f.startswith(prefix) and f.endswith(suffix) and name.isdigit() \
                    and not pd.Timestamp(year=int(name), month=1, day=1).is_leap_year:
                years.append(int(name))
    if not years:
        raise FileNotFoundError(f'No non-leap-year solar profile for {city}, {state} in {ghi_dir} (looked for '
                                f'{prefix}<year>{suffix}). Download one from the Data Import Wizard Solar tab.')

    path = ghi_dir + prefix + str(max(years)) + suffix
    if (state, city) not in _solar_fallback_warned:
        _solar_fallback_warned.add((state, city))
        print(f'Note: no 2018 solar profile for {city}, {state}; using {max(years)} instead. PV and house load '
              f'will come from different weather years.')
    return path


def make_pv(new_row: pd.Series, ref_city: pm.City, tk: pm.TimeKeep):
    # Provide current row and reference city to make PV object
    pv_brand = new_row['PV Brand']
    pv_model = new_row['PV Model']
    pv_size = new_row['System Size (kW)']
    if np.isnan(pv_size):
        pv_size = 0
    else:
        pv_size = min(max(pv_size, 0), 10)

    if pd.isnull(pv_brand) or pd.isnull(pv_model):
        new_pv = PV(system_size=pv_size)
    else:
        new_pv = PV(system_size=pv_size, brand=pv_brand, model=pv_model)

    other_solar_file = new_row['Other Solar File']
    if pd.isnull(other_solar_file):  # we default to NREL 2018 for reference city
        solar_file = reference_solar_file(ref_city.matched_state, ref_city.matched_city)
        new_pv.load_solar(solar_file=solar_file, start_date=tk.start_date, end_date=tk.end_date)
    else:  # we use other file
        new_pv.load_solar(solar_file='City Data/Solar Data/Custom/' + other_solar_file, start_date=tk.start_date,
                          end_date=tk.end_date)
    return new_pv


#ES: add new_ev_charging to make_ev function
def make_ev(new_year, new_make, new_model, new_trim, new_ev_pattern, new_ev_limit, new_ev_charging, commute):
    ev_ind = ev_model_frame.index[(ev_model_frame['Year'] == new_year) & (ev_model_frame['Model'] == new_model) & (ev_model_frame['Trim'] == new_trim) & (ev_model_frame['Make'] == new_make)]
    new_ev = EV(ev_model_frame.loc[ev_ind, 'Battery Size (kWh)'].values[0],
                ev_model_frame.loc[ev_ind, 'Lvl2 Charge Rate (kW)'].values[0],
                True,
                1,  # EV ID
                ev_model_frame.loc[ev_ind, 'Year'].values[0],
                ev_model_frame.loc[ev_ind, 'Make'].values[0],
                ev_model_frame.loc[ev_ind, 'Model'].values[0],
                ev_model_frame.loc[ev_ind, 'Trim'].values[0],
                ev_model_frame.loc[ev_ind, 'MSRP'].values[0],
                ev_model_frame.loc[ev_ind, 'MPGe Hwy'].values[0],
                ev_model_frame.loc[ev_ind, 'MPGe City'].values[0],
                ev_model_frame.loc[ev_ind, 'MPGe Comb'].values[0],
                driving_pattern=new_ev_pattern,
                discharge_limit=new_ev_limit,
                #ES: incorporate new_ev_charging into make_ev function
                charging_scheme=new_ev_charging,
                commute=commute)

    return new_ev


def make_fleet(new_row: pd.Series, tk: pm.TimeKeep):
    # provide current row to make new fleet object
    ev_list = []

    #  We check for EV file, if not there we default to the ones listed.
    ev_file = new_row['EV File']
    if not pd.isnull(ev_file):
        ev_list_frame = pd.read_excel('InputFiles/EV Files/' + ev_file)
        for ev_index, ev_row in ev_list_frame.iterrows():
            ev_limit = new_row['Discharge Limit']
            if pd.isnull(ev_limit):
                ev_limit = ev_row['Discharge Limit']
            ev_year = ev_row['Year']
            ev_model = ev_row['Model']
            ev_make = ev_row['Make']
            ev_trim = ev_row['Trim']
            ev_pattern_file = ev_row['Pattern']
            #ES: read charging type
            ev_charging_scheme = new_row['Charge Type']

            if pd.isnull(ev_pattern_file):
                ev_pattern = sp.driving_pattern_from_calendar(timekeep=tk, filename='basic_commute.csv')
            else:
                ev_pattern = sp.driving_pattern_from_calendar(timekeep=tk, filename=ev_pattern_file + '.csv')
            ev_qty = ev_row['Qty']
            #ES: add charging type to make_ev command
            add_ev = make_ev(new_year=ev_year, new_model=ev_model, new_make=ev_make, new_trim=ev_trim,
                             new_ev_pattern=ev_pattern, new_ev_limit=ev_limit,
                             new_ev_charging=ev_charging_scheme, commute=ev_pattern_file)
            if np.isnan(ev_qty):
                ev_qty = 1
            for j in range(ev_qty):
                ev_list.append(copy.deepcopy(add_ev))
    else:
        ev1_limit = new_row['Discharge Limit']
        ev1_year = new_row['EV Year']
        ev1_make = new_row['Make']
        ev1_model = new_row['Model']
        ev1_trim = new_row['Trim']
        ev1_pattern_file = new_row['Pattern']
        #ES: read charging type
        ev1_charging_scheme = new_row['Charge Type']
        if pd.isnull(ev1_pattern_file):
            ev1_pattern = sp.create_driving_pattern(from_file=True, filename='basic_commute.csv')
        else:
            ev1_pattern = sp.create_driving_pattern(from_file=True, filename=ev1_pattern_file + '.csv')

        ev1_qty = new_row['Qty']
        if np.isnan(ev1_qty):
            ev1_qty = 1
        if not np.isnan(ev1_year):
            #ES: add charging type to make_ev command
            add_ev = make_ev(new_year=ev1_year, new_make=ev1_make, new_model=ev1_model, new_trim=ev1_trim,
                             new_ev_pattern=ev1_pattern, new_ev_limit=ev1_limit,
                             new_ev_charging=ev1_charging_scheme, commute=ev1_pattern_file)
            for _ in range(ev1_qty):
                ev_list.append(copy.deepcopy(add_ev))

    new_fleet = Fleet(ev_list)
    return new_fleet


def generate_object_dict(row: pd.Series) -> dict:
    """
    Placeholder for building the object dictionary consumed by Results.add_objects.

    Not yet implemented -- the body was a stub that assigned two dummy values and fell through to a
    bare ``pass``, so it returned None. Raising is clearer than silently handing back None.

    Parameters
    ----------
    row : pandas.Series
        A scenario row.

    Raises
    ------
    NotImplementedError
        Always.
    """
    raise NotImplementedError('generate_object_dict is a stub; build the objects via run_model instead.')


def get_baseline(baseline_frame: pd.DataFrame, line: pd.Series):
    # this function finds the baseline scenario for comparison given a current row in a summary frame
    cols = baseline_frame.columns

    sub_frame = baseline_frame[(baseline_frame['City'] == line['City']) & (baseline_frame['State'] == line['State']) & (baseline_frame['Start Date'] == line['Start Date']) & (baseline_frame['End Date'] == line['End Date']) & (baseline_frame['Utility'] == line['Utility']) & (baseline_frame['Tariff'] == line['Tariff']) & (baseline_frame['EV Models'] == line['EV Models']) & (baseline_frame['Solar Model'] == line['Solar Model']) & (baseline_frame['House Load'] == line['House Load']) & (baseline_frame['HES Optimization'] == line['HES Optimization']) & (baseline_frame['Net Meter Policy'] == line['Net Meter Policy'])]

    if 'Pattern' in cols:
        sub_frame = sub_frame[sub_frame['Pattern'] == line['Pattern']]

    if 'EV Charge Scheme' in cols:
        sub_frame = sub_frame[sub_frame['EV Charge Scheme'] == line['EV Charge Scheme']]

    return sub_frame


def update_baseline_metrics(summary_frame: DataFrame):
    base_frame = summary_frame[summary_frame['Is Baseline']]
    for index, row in summary_frame.iterrows():
        if not row['Is Baseline']:
            red_frame = get_baseline(baseline_frame=base_frame, line=row)
            if len(red_frame) == 0:
                summary_frame.loc[index, 'Baseline Savings ($)'] = np.nan
                summary_frame.loc[index, 'Baseline Savings (kg CO2)'] = np.nan
                summary_frame.loc[index, 'Net Value ($)'] = np.nan
                summary_frame.loc[index, 'System Payback Period'] = np.nan
                summary_frame.loc[index, 'System Cost Efficiency'] = np.nan
            else:
                summary_frame.loc[index, 'Baseline Savings ($)'] = \
                    np.round(red_frame['Total Bill ($)'].values[0] - row['Total Bill ($)'], 2)
                summary_frame.loc[index, 'Baseline Savings (kg CO2)'] = \
                    np.round(red_frame['Total CO2 (kg)'].values[0] - row['Total CO2 (kg)'], 2)
                summary_frame.loc[index, 'Net Value ($)'] = \
                    np.round((summary_frame.loc[index, 'Baseline Savings (''$)'] -
                              summary_frame.loc[index, 'EV Degradation ($)']), 2)
                # Guard the division. A system that saves nothing never pays back, so report NaN
                # deliberately rather than letting numpy emit inf into the summary CSV.
                net_value = summary_frame.loc[index, 'Net Value ($)']
                summary_frame.loc[index, 'System Payback Period'] = \
                    np.round(summary_frame.loc[index, 'System Cost ($)'] / net_value, 2) \
                    if net_value else np.nan
                if summary_frame.loc[index, 'System Cost ($)'] == 0:
                    summary_frame.loc[index, 'System Cost Efficiency'] = 0
                else:
                    summary_frame.loc[index, 'System Cost Efficiency'] = \
                        np.round(summary_frame.loc[index, 'Net Value ($)'] /
                                 summary_frame.loc[index, 'System Cost ($)'], 4)
    return summary_frame


def get_result_summary_data_from_file(result: Results, file_name: str = None) -> dict:
    scen_id = result.operation.simu_id
    # 'File Name' records the pickle this row came from. When the caller knows the real filename it
    # passes it in, so the column reflects .pkl vs .pkl.gz (and is simply informational when
    # save_pickles is off).
    if file_name is None:
        file_name = f"{str(result.operation.simu_name).split('/')[-1]}_Run_{scen_id}.pkl"
    scenario_filename = file_name

    if hasattr(result, 'v2h_effs'):
        v2h_eff = result.v2h_effs[0]
    else:
        v2h_eff = np.nan

    if hasattr(result, 'commute'):
        commute = result.commute
    else:
        commute = 'see input'

    if hasattr(result, 'ev_charge_scheme'):
        ev_charge_scheme = result.ev_charge_scheme
    else:
        ev_charge_scheme = 'see input'

    data = {'ID': scen_id,
            'File Name': scenario_filename,
            'Time Elapsed (s)': result.time_elapsed,
            'Start Date': result.time_data['Start Date'],
            'End Date': result.time_data['End Data'],
            'City': result.city_data['Name'],
            'State': result.city_data['State'],
            'Reference City': result.city_data['Reference City'],
            'Reference State': result.city_data['Reference State'],
            'House Load': np.round(result.house_usage, 1),
            'Utility': result.utility,
            'Tariff': result.tariff_name,
            'Net Meter Policy': result.operation.net_meter_scheme,
            'Solar Model': result.pv_data['Solar Model'],
            'Solar Size (kW)': result.pv_data['Solar Size (kW)'],
            'Solar Cost ($)': np.round(result.pv_cost, 2),
            'HES Size': result.hes_data['Battery Size (kWh)'],
            'HES Cost ($)': np.round(result.hes_cost, 2),
            'HES Optimization': result.operation.hes_optimization,
            'HES Avg SoC Target': result.avg_soc_target,
            'EV Models': result.fleet_data['EV List'],
            'EV Discharge Limit': result.operation.ev_discharge_limit,
            'Pattern': commute,
            'EV Charge Scheme': ev_charge_scheme,
            'Fleet Cost ($)': result.fleet_data['Fleet Cost ($)'],
            'Total Bill ($)': np.round(result.bill.total_bill, 2),
            'Total CO2 (kg)': np.round(result.bill.co2_emissions, 2),
            'PV Avoided Cost ($)': np.round(result.solar_avoidance, 2),
            'PV Avoided CO2 (kg)': np.round(result.solar_co2_savings, 2),
            'HES Avoided Cost ($)': np.round(result.hes_avoidance, 2),
            'HES Avoided CO2 (kg)': np.round(result.hes_co2_savings, 2),
            'Fleet Avoided Cost ($)': np.round(result.fleet_avoidance, 2),
            'Fleet Avoided CO2 (kg)': np.round(result.fleet_co2_savings, 2),
            'Fleet Sim Miles (mi)': result.fleet_data['Fleet Sim Miles (mi)'],
            'Fleet Driven Miles (mi)': result.fleet_data['Fleet Driven Miles (mi)'],
            'V2H Eff ($/kWh)': v2h_eff,
            'EV Degradation ($)': np.round(result.ev_degradations[0]),
            'EV Breakeven Mileage (mi)': np.round(result.ev_breakeven_miles[0]),
            'EV Breakeven Cost ($/kWh)': np.round(result.ev_breakeven_cost[0]),
            'System Loss (kWh)': result.energy_data['System Loss (kWh)'],
            'Cost of Loss ($)': result.energy_data['Cost of Loss ($)'],
            'Emissions from Loss (kg)': result.energy_data['Emissions from Loss (kg)'],
            'Fleet Driving Cost ($)': np.round(result.fleet_driving_costs, 2),
            'Gas Savings ($)': np.round(result.gas_savings, 2),
            'Total Avoidance($)': np.round(result.total_avoidance, 2),
            'Total Savings($)': np.round(result.total_system_savings, 2),
            'System Cost ($)': np.round(result.hes_pv_cost, 2),
            'Baseline Savings ($)': 0,
            'Net Value ($)': 0,
            'Baseline Savings (kg CO2)': 0,
            'System Payback Period': 0,
            'System Cost Efficiency': 0,
            'System Total Peak Shaving Efficiency': np.round(result.peak_shaving_effectiveness, 2),
            'System High Peak Shaving Efficiency': np.round(result.high_peak_shaving_effectiveness, 2),
            'Is Baseline': bool(result.is_baseline)
            }
    return data


def generate_results_summary(results_path: str, save_frame=True):
    # Accepts both .pkl and .pkl.gz. The scenario number is the trailing "_N" of the stem, so strip any
    # known extension first rather than splitting on '.' -- city names like "St.Louis" contain periods.
    def _stem(name: str) -> str:
        for ext in RESULT_EXTENSIONS:
            if name.endswith(ext):
                return name[: -len(ext)]
        return os.path.splitext(name)[0]

    res_list = [f for f in os.listdir(results_path) if f.endswith(RESULT_EXTENSIONS)]
    try:
        res_list = sorted(res_list, key=lambda x: int(_stem(x).split('_')[-1]))
    except ValueError:
        res_list = sorted(res_list)

    rows = []
    for i, file_name in enumerate(res_list, start=1):
        result = load_results_file(os.path.join(results_path, file_name))
        rows.append(_normalize_summary_row(
            get_result_summary_data_from_file(result=result, file_name=file_name)))
        print(f'Scenario {i} Added')

    summary_frame = pd.DataFrame(rows)
    if 'Is Baseline' in summary_frame.columns:
        summary_frame['Is Baseline'] = summary_frame['Is Baseline'].astype('boolean')

    if save_frame:
        summary_frame = update_baseline_metrics(summary_frame=summary_frame)
        path_split = results_path.split('/')
        summary_path = '/'.join(path_split[0:2]) + '/' + path_split[1] + '_summary.csv'
        summary_frame.to_csv(summary_path, index=False)

    return summary_frame


def recalc_summary_frame(results_path: str, save_frame: bool = False):
    summary_frame = generate_results_summary(results_path=results_path, save_frame=save_frame)
    return summary_frame


def run_row(row: pd.Series, only_run: dict):
    cols = row.keys()
    run = False
    for key in only_run.keys():
        if key in cols and not run:
            if type(only_run[key]) in [list, set, tuple]:
                run = row[key] in only_run[key]
            else:
                run = row[key] == only_run[key]
    return run


def run_model(input_file: str = None, collection_name: str = None, overwrite_runs: bool = False,
              only_run: dict = None, starting_scen: int = None, end_scen: int = None,
              full_results: bool = None, save_pickles: bool = False, summary_suffix: str = '',
              write_parquet: bool = True, compress_pickles: bool = True, compress_level: int = 1,
              consolidate_results: bool = False):
    """
    Runs every scenario in one input file and writes the results.

    Parameters
    ----------
    input_file : str, optional
        Name of the scenario workbook under InputFiles/, without the .xlsx extension. Prompted for if
        omitted.
    collection_name : str, optional
        Name of the output directory under Outputs/. Defaults to input_file.
    overwrite_runs : bool, optional
        Whether to re-run scenarios that already have results. Default False, which resumes.
    only_run : dict, optional
        Column-name -> value (or list of values) filter restricting which scenarios run.
    starting_scen, end_scen : int, optional
        Inclusive ScenarioID bounds. Used by run_collection's chunked scheduler.
    full_results : bool, optional
        Keep the full component objects on each Results object. Implies save_pickles.
    save_pickles : bool, optional
        Write one .pkl per scenario. Default False -- a 30-file collection previously produced roughly
        71,000 pickles totalling ~570 MB, and with full_results False they hold nothing the Parquet
        does not. Forced True when full_results is set.
    summary_suffix : str, optional
        Appended to the summary filename. run_collection's chunked scheduler uses this so concurrent
        workers on the same input file write separate partial summaries.
    write_parquet : bool, optional
        Write the columnar results store alongside the summary CSV. Default True.
    compress_pickles : bool, optional
        gzip the per-scenario pickles, giving files named ``..._Run_N.pkl.gz``. Default True; a
        full-results pickle shrinks about 9x (44 MB -> 4.7 MB measured) for roughly 0.12 s per
        scenario. Lossless. Readers detect the format from the file's magic bytes, so old uncompressed
        .pkl files keep working and the two can sit side by side in the same directory.
    compress_level : int, optional
        gzip level 1-9, default 1. Level 6 is only ~12% smaller for nearly 3x the CPU.
    consolidate_results : bool, optional
        When save_pickles is in effect, append each scenario's Results to one shared per-input-file
        store (save_result_to_store) instead of writing it as its own ``..._Run_N.pkl(.gz)`` file.
        Default False, preserving today's one-file-per-scenario layout. No effect when save_pickles is
        False, since there's nothing to consolidate. See save_result_to_store/load_result_from_store.

    Returns
    -------
    str
        Path of the summary file written.
    """
    if full_results:
        save_pickles = True  # the component objects only survive in the pickle

    # assess inputs
    if (input_file is None) and (collection_name is None):
        input_file = input('Please input scenario input file:  ')
        collection_name = input('What is the title of these runs?:   ')
    elif collection_name is None:
        collection_name = input_file
    elif input_file is None:
        input_file = input('Please input scenario input file:  ')

    input_path = 'InputFiles/' + input_file + '.xlsx'

    if not os.path.exists(input_path):
        raise Exception('Input file does not exist')

    collection_dir = 'Outputs/' + collection_name
    results_dir = 'Outputs/' + collection_name + '/Results'

    # makedirs rather than mkdir so a nested collection path ('Top20_set/F1_CA_...') works, and
    # exist_ok so concurrent workers on the same collection cannot race each other.
    os.makedirs(collection_dir, exist_ok=True)
    os.makedirs(results_dir, exist_ok=True)

    base_name = collection_name.split('/')[-1]
    summary_path = f'{collection_dir}/{base_name}_summary{summary_suffix}.csv'
    parquet_path = f'{collection_dir}/{base_name}_results{summary_suffix}.parquet'
    store_path = f'{collection_dir}/{base_name}_results_store{summary_suffix}.dat'
    store_index_path = f'{collection_dir}/{base_name}_results_store_index{summary_suffix}.csv'

    #  Load scenario list file
    scenario_frame = pd.read_excel(input_path, header=2,
                                   dtype={'Zip Code': str, 'Discharge Limit': float},
                                   parse_dates=['Start Date', 'End Date'])
    if starting_scen is None:
        starting_scen = 1
    if end_scen is None:
        end_scen = len(scenario_frame)

    if only_run is not None:
        red_frame = scenario_frame[(scenario_frame['ScenarioID'] >= starting_scen) & (scenario_frame['ScenarioID'] <= end_scen)]
        for key in only_run.keys():
            if key in scenario_frame.columns:
                if type(only_run[key]) in [list, tuple]:
                    red_frame = red_frame[red_frame[key].isin(only_run[key])]
                else:
                    red_frame = red_frame[red_frame[key] == only_run[key]]
        total_scenarios = len(red_frame)
        del red_frame
    else:
        total_scenarios = len(scenario_frame)

    summary_columns = ['ID',
                       'City', 'State', 'Reference City', 'Reference State', 'Utility', 'Tariff', 'Solar Model',
                       'Solar Size (kW)', 'HES Size', 'HES Optimization', 'EV Models', 'EV Discharge Limit',
                       'Total Bill ($)', 'Total CO2 (kg)', 'PV Avoided Cost ($)', 'PV Avoided CO2 (kg)',
                       'HES Avoided Cost ($)', 'HES Avoided CO2 (kg)', 'Fleet Avoided Cost ($)',
                       'Fleet Avoided CO2 (kg)',
                       'Time Elapsed (s)']

    if os.path.exists(summary_path):
        summary_frame = pd.read_csv(summary_path)
    else:
        if len(os.listdir(results_dir)) == 0:
            summary_frame = pd.DataFrame(columns=summary_columns)
        else:
            summary_frame = generate_results_summary(results_path=results_dir, save_frame=True)
    # set membership, not ndarray membership: "scen_id in ndarray" is a linear scan per scenario
    already_done = set(summary_frame['ID'].tolist())
    # New rows are accumulated here and turned into a DataFrame once at the end. Growing a frame with
    # pd.concat inside the loop copies the whole thing every iteration (~0.9 s per input file) and is
    # what emits the pandas FutureWarning about concatenating empty entries.
    pending_rows = []

    i = 0 if overwrite_runs else len(summary_frame)

    scenarios_ran = 0
    scenarios_remaining = total_scenarios - i
    avg_time = None
    timekeep = None
    house = None
    city = None
    grid = None
    pv = None
    fleet = Fleet([])
    hes = None
    tariff = None
    prev_row = None
    exception_thrown = False
    for _, row in scenario_frame.iloc[i:].iterrows():

        scen_id = row['ScenarioID']

        run_the_row = (scen_id <= end_scen) and (scen_id >= starting_scen)  # must fall within bounds

        if (only_run is not None) and overwrite_runs and run_the_row:
            run_the_row = run_row(row, only_run=only_run)

        if run_the_row:
            t0 = time.time()

            reset_comps = get_reset_dict(old_row=prev_row, new_row=row)
            # Get file ID

            # Stem only: save_result_file appends .pkl or .pkl.gz depending on compress_pickles.
            scenario_stem = f'{base_name}_Run_{scen_id}'

            # Check for User Load File
            # if a user profile is provided, its dates will define the time limits of the simulation
            user_file = row['User File']

            if pd.isna(user_file):
                user_profile_given = False
            else:
                if os.path.exists('City Data/Load Profiles/User Profiles/' + user_file + '.csv'):
                    user_profile_given = True
                else:
                    user_profile_given = False

            if user_profile_given:
                user_frame = pd.read_csv('City Data/Load Profiles/User Profiles/' + user_file + '.csv',
                                         parse_dates=['Time'],
                                         dtype={'Usage (kWh)': float})
                load_start = user_frame.iloc[0, 0]
                load_end = user_frame.iloc[-1, 0]
            else:
                user_frame = None
                load_start = pd.Timestamp('1/1/2018')
                load_end = pd.Timestamp('12/31/2018 23:55')
                load_res = 5

            # Create Operation object  (this will change for every run, since every run has different ID)

            opt_method = row['Optimization']
            net_meter_method = row['Net Meter Type']
            operation = pm.Operation(ev_discharge_limit=row['Discharge Limit'], simu_name=collection_name,
                                     simu_id=str(scen_id),
                                     hes_optimization=opt_method, net_meter_scheme=net_meter_method,
                                     user_profile=user_profile_given)

            # Create Timekeep object
            if reset_comps['New Timekeep']:
                time_resolution = check_resolution(row['TimeStep'])
                year = row['Year']
                simulation_days = row['Simulation Days']
                simu_start_day = row['Start Day']
                start_date = row['Start Date']
                end_date = row['End Date']

                if user_profile_given:
                    start_date = load_start
                    end_date = load_end

                timekeep_dict = {'Sim Days': simulation_days, 'Start Day': simu_start_day, 'Start Date': start_date,
                                 'End Date': end_date, 'Year': year}

                timekeep = make_timekeep(time_dict=timekeep_dict, resolution=time_resolution)
            else:
                timekeep.reset()

            # timekeep = pm.TimeKeep(year=year, starting_day=simu_start_day, simu_days=simulation_days)

            # Create City object
            if reset_comps['New City']:
                city = make_city(new_row=row)

            # Create Tariff Object

            if reset_comps['New Tariff']:
                tariff = make_tariff(new_row=row, ref_city=city, timekeep=timekeep)
            else:
                tariff.reset()

            # Create House Object

            if reset_comps['New House']:
                house = make_house(new_row=row, ref_city=city, op=operation, user_dataframe=user_frame)
            else:
                house.reset()

            # Create Grid object
            if reset_comps['New Grid']:
                grid = make_grid(new_row=row, ref_city=city, tk=timekeep)
            else:
                grid.reset()

            # create Solar Object
            if reset_comps['New PV']:
                pv = make_pv(new_row=row, ref_city=city, tk=timekeep)

            # create HES object
            if reset_comps['New HES']:
                hes = HES(battery_size=row['Size (kWh)'], lvl2_max_rate=10, max_discharge=7, use_curve=True)
            else:
                hes.reset()

            #  Create Fleet/EV Objects
            if reset_comps['New Fleet']:
                fleet = make_fleet(new_row=row, tk=timekeep)
            else:
                fleet.reset_evs(new_limit=row['Discharge Limit'])

            # load ICE for comparison
            ice = ICE()

            # We run the simulation now
            try:
                result = run_simulation(operation=operation, timekeep=timekeep, city=city, grid=grid, tariff=tariff,
                                        house=house, pv=pv, hes=hes, fleet=fleet, ice=ice, full_results=full_results)

                t1 = time.time()
                t_tot = t1 - t0
                result.add_time_elapsed(time_elapsed=t_tot)
                if full_results:
                    result.add_row(row=row)

                saved_name = scenario_stem + ('.pkl.gz' if compress_pickles else '.pkl')
                if save_pickles and consolidate_results:
                    save_result_to_store(result, store_path, store_index_path, scen_id,
                                         compress_level=compress_level)
                    # Always record the *final* (unsuffixed) store name: _finalize_chunked_file merges
                    # every __partNNNNNN store into one, so that's the name this will resolve to even
                    # when this particular scenario was written by a chunk worker.
                    saved_name = f'{base_name}_results_store.dat#{scen_id}'
                elif save_pickles:
                    saved_name = os.path.basename(
                        save_result_file(result, f'{results_dir}/{scenario_stem}',
                                         compress=compress_pickles, compress_level=compress_level))

                # Retrieve data for summary file. Written after add_time_elapsed so the recorded
                # duration covers the whole scenario, which the old ordering missed.
                data = _normalize_summary_row(
                    get_result_summary_data_from_file(result=result, file_name=saved_name))
                if scen_id in already_done:
                    idx = summary_frame.index[summary_frame['ID'] == scen_id]
                    for col, val in data.items():
                        if col not in summary_frame.columns:
                            summary_frame[col] = np.nan
                        summary_frame.loc[idx, col] = val
                else:
                    pending_rows.append(data)
                    already_done.add(scen_id)

            except (Exception, KeyboardInterrupt) as ex:

                Progress.report_scenario_error(scen_id, ex, traceback.format_exc())
                exception_thrown = True
                summary_frame = _merge_pending(summary_frame, pending_rows)
                pending_rows = []
                summary_frame.to_csv(summary_path, index=False)
                if write_parquet:
                    _write_results_parquet(summary_frame, parquet_path)
                break

            i += 1
            scenarios_ran += 1
            scenarios_remaining -= 1
            prev_row = row.copy()
            avg_time = t_tot if avg_time is None else (avg_time + (t_tot - avg_time) / scenarios_ran)
            est_time_remaining = avg_time * scenarios_remaining
            time_str = str(datetime.timedelta(seconds=est_time_remaining))
            Progress.report_scenario_done(scen_id, t_tot, time_str[:-4])

        # Once we're done going through rows we write the summary file
    if not exception_thrown:
        summary_frame = _merge_pending(summary_frame, pending_rows)
        # Baseline metrics compare every scenario against the no-PV/no-HES/no-V2H run, so this can only
        # be done once the whole input file is present. Chunked workers therefore skip it and
        # run_collection re-runs it after merging (see _finalize_chunked_file).
        if summary_suffix == '':
            summary_frame = update_baseline_metrics(summary_frame=summary_frame)
        summary_frame.to_csv(summary_path, index=False)
        if write_parquet:
            _write_results_parquet(summary_frame, parquet_path)

    return summary_path


def _normalize_summary_row(data: dict) -> dict:
    """
    Flattens list- and array-valued summary fields to scalars.

    'EV Models' arrives as a list. The previous per-row ``pd.DataFrame(data=data, index=[i])``
    construction collapsed a one-element list into a scalar as a side effect of index alignment (and
    raised outright for a multi-EV fleet). Building the frame from a list of dicts instead preserves the
    list object in the cell, which then breaks the Series comparisons in get_baseline. Normalising here
    keeps the column scalar for any fleet size.

    'House Load' has the same problem via a different route: House.load_profile is an (N, 1) array (the
    convention DataProcessing uses for GHI/temperature too), so indexing it per-timestep and
    accumulating into House.usage leaves Results.house_usage -- and so this column -- as a 1-element
    numpy array rather than a plain float. That's not a list/tuple, so it used to slip past this
    function unflattened and break get_baseline's vectorized comparison the same way a raw EV list once
    did (ValueError: 'Lengths must match to compare').

    Parameters
    ----------
    data : dict
        One row of summary data.

    Returns
    -------
    dict
        The same row with list/tuple/ndarray values reduced to a scalar or a comma-joined string.
    """
    out = {}
    for key, val in data.items():
        if isinstance(val, np.ndarray):
            val = val.ravel().tolist()
        if isinstance(val, (list, tuple)):
            out[key] = val[0] if len(val) == 1 else ', '.join(str(v) for v in val)
        else:
            out[key] = val
    return out


def _merge_pending(summary_frame: DataFrame, pending_rows: list) -> DataFrame:
    """
    Folds accumulated result rows into the summary frame in a single concat.

    Parameters
    ----------
    summary_frame : DataFrame
        The frame built so far.
    pending_rows : list of dict
        Rows produced since the last merge.

    Returns
    -------
    DataFrame
        The combined frame, with 'Is Baseline' restored to a nullable boolean.
    """
    if not pending_rows:
        return summary_frame
    new_frame = pd.DataFrame(pending_rows)
    # Column order is preserved deliberately: the seeded summary_columns come first, then the rest in
    # the order get_result_summary_data_from_file emits them. That is the layout every existing summary
    # CSV already has, so old and new files stay concatenable.
    ordered = list(summary_frame.columns) + [c for c in new_frame.columns if c not in summary_frame.columns]
    combined = pd.concat([summary_frame, new_frame], ignore_index=True, axis=0)
    combined = combined.reindex(columns=ordered)
    if 'Is Baseline' in combined.columns:
        combined['Is Baseline'] = combined['Is Baseline'].astype('boolean')
    return combined


def _write_results_parquet(summary_frame: DataFrame, parquet_path: str) -> None:
    """
    Writes the results table as a single compressed Parquet file.

    One columnar file per input file replaces thousands of per-scenario pickles: about 300 KB against
    19 MB, and one filesystem entry instead of ~2,375. Falls back silently to CSV-only if no Parquet
    engine (pyarrow or fastparquet) is installed.

    Parameters
    ----------
    summary_frame : DataFrame
        The completed results table.
    parquet_path : str
        Destination path.

    Returns
    -------
    None
    """
    if len(summary_frame) == 0:
        return
    frame = summary_frame.copy()
    # Object columns holding mixed types (EV model lists, for instance) are not Parquet-representable;
    # stringify them so the write cannot fail on a stray list.
    for col in frame.columns:
        if frame[col].dtype == object:
            frame[col] = frame[col].astype(str)
    try:
        frame.to_parquet(parquet_path, index=False, compression='snappy')
    except (ImportError, ValueError) as ex:
        print(f'Parquet results store not written ({ex}). Install pyarrow to enable it; '
              f'the summary CSV is unaffected.')


def load_results_frame(collection_name: str) -> DataFrame:
    """
    Loads the columnar results store for a collection, falling back to the summary CSV.

    This is the fast path for post-processing: one Parquet read instead of unpickling every scenario.

    Parameters
    ----------
    collection_name : str
        Output directory name under Outputs/, e.g. 'Top20_PV_HES_set/F1_CA_90011_PST_Los Angeles_CA'.

    Returns
    -------
    DataFrame
        One row per scenario.
    """
    base = collection_name.split('/')[-1]
    parquet_path = f'Outputs/{collection_name}/{base}_results.parquet'
    if os.path.exists(parquet_path):
        return pd.read_parquet(parquet_path)
    csv_path = f'Outputs/{collection_name}/{base}_summary.csv'
    if os.path.exists(csv_path):
        return pd.read_csv(csv_path)
    raise FileNotFoundError(f'no results store or summary found for {collection_name}')


#: Extensions a saved Results file may carry, newest convention first.
RESULT_EXTENSIONS = ('.pkl.gz', '.pkl')
_GZIP_MAGIC = b'\x1f\x8b'  # gzip header; a raw protocol-5 pickle starts b'\x80\x05'


def save_result_file(result: Results, path_stem: str, compress: bool = True,
                     compress_level: int = 1) -> str:
    """
    Writes a Results object to disk, optionally gzip-compressed.

    A full-results pickle is dominated by ~70 float arrays of 105,120 elements, most of them either
    largely zero or highly regular, so it compresses about 9x (44 MB -> 4.7 MB measured). Compression
    is lossless: the unpickled object is bit-identical either way.

    gzip is used rather than raw zlib so the file is a genuine .gz that gunzip, 7-Zip and friends can
    open. That costs roughly 20 ms more per file than raw zlib for the same size.

    Parameters
    ----------
    result : Results
        The object to save.
    path_stem : str
        Destination path WITHOUT extension; the correct one is appended.
    compress : bool, optional
        Write gzip-compressed. Default True.
    compress_level : int, optional
        gzip level 1-9. Default 1: level 6 is only ~12% smaller for nearly 3x the CPU, and
        decompression speed barely varies with level.

    Returns
    -------
    str
        The path actually written, including extension.
    """
    blob = pickle.dumps(result, protocol=5)
    if compress:
        path = path_stem + '.pkl.gz'
        with open(path, 'wb') as f:
            f.write(gzip.compress(blob, compress_level))
    else:
        path = path_stem + '.pkl'
        with open(path, 'wb') as f:
            f.write(blob)
    return path


def load_results_file(path: str) -> Results:
    """
    Loads a Results file, transparently handling compressed and uncompressed pickles.

    The format is detected from the file's magic bytes, not its name, so a mislabelled file still
    loads. If ``path`` has no recognised extension, both are tried -- this means callers can pass a
    stem and get whichever exists.

    Parameters
    ----------
    path : str
        Path to a .pkl or .pkl.gz results file, or the same path without an extension.

    Returns
    -------
    Results
        The unpickled results object.

    Raises
    ------
    FileNotFoundError
        If no matching file exists.
    """
    if not os.path.exists(path):
        stem = path
        for ext in RESULT_EXTENSIONS:
            if stem.endswith(ext):
                stem = stem[: -len(ext)]
                break
        candidates = [stem + ext for ext in RESULT_EXTENSIONS]
        path = next((c for c in candidates if os.path.exists(c)), None)
        if path is None:
            raise FileNotFoundError(f'no results file found for {stem!r} (tried {RESULT_EXTENSIONS})')

    with open(path, 'rb') as f:
        blob = f.read()
    if blob[:2] == _GZIP_MAGIC:
        blob = gzip.decompress(blob)
    return pickle.loads(blob)


def save_result_to_store(result: Results, store_path: str, index_path: str, scenario_id,
                         compress_level: int = 1) -> None:
    """
    Appends one scenario's Results to a shared per-input-file store instead of writing it as its own
    file -- the opt-in alternative to save_result_file for consolidate_results=True.

    Both the data and index files are opened in append mode and written to immediately, exactly like
    save_result_file writes its one file immediately: nothing is batched in memory across scenarios.
    That matters because get_reset_dict-driven component reuse mutates shared City/Tariff/Grid/House
    objects in place between scenarios (see run_model), so a Results object must be fully serialized
    before the next scenario's .reset() call, not held for a later batched write.

    If a scenario is written more than once (e.g. re-run after an interrupted collection), the index
    simply gets a second row for that ID -- load_result_from_store always takes the last one, the same
    keep='last' convention _finalize_chunked_file already uses for duplicate summary rows.

    Parameters
    ----------
    result : Results
        The object to save.
    store_path : str
        Path to the shared .dat file (created if missing).
    index_path : str
        Path to the shared index CSV (created if missing).
    scenario_id
        This record's ScenarioID, written to the index.
    compress_level : int, optional
        gzip level 1-9. Default 1, matching save_result_file.

    Returns
    -------
    None
    """
    blob = gzip.compress(pickle.dumps(result, protocol=5), compress_level)
    offset = os.path.getsize(store_path) if os.path.exists(store_path) else 0
    with open(store_path, 'ab') as f:
        f.write(blob)
    with open(index_path, 'a') as f:
        f.write(f'{scenario_id},{offset},{len(blob)}\n')


def load_result_from_store(store_path: str, index_path: str, scenario_id) -> Results:
    """
    Loads one scenario's Results from a consolidate_results store by seeking directly to its record,
    without reading the rest of the (potentially large) data file.

    Parameters
    ----------
    store_path : str
        Path to the store's .dat file.
    index_path : str
        Path to the store's index CSV.
    scenario_id
        The ScenarioID to load.

    Returns
    -------
    Results
        The unpickled results object.

    Raises
    ------
    FileNotFoundError
        If scenario_id has no entry in the index.
    """
    offset = length = None
    with open(index_path) as f:
        for line in f:
            sid, off, ln = line.rstrip('\n').split(',')
            if str(sid) == str(scenario_id):
                offset, length = int(off), int(ln)  # keep scanning -- last match wins, see write side
    if offset is None:
        raise FileNotFoundError(f'no scenario {scenario_id!r} in store index {index_path!r}')
    with open(store_path, 'rb') as f:
        f.seek(offset)
        blob = f.read(length)
    return pickle.loads(gzip.decompress(blob))


def list_store_scenarios(index_path: str) -> list:
    """Returns the distinct ScenarioIDs recorded in a consolidate_results store index, in file order."""
    seen = set()
    ordered = []
    with open(index_path) as f:
        for line in f:
            sid = line.split(',', 1)[0]
            if sid not in seen:
                seen.add(sid)
                ordered.append(sid)
    return ordered


def recalc_summary_file(file_path: str):
    summary_frame = pd.read_csv(file_path)
    summary_frame = update_baseline_metrics(summary_frame=summary_frame)
    summary_frame.to_csv(file_path, index=False)


def _run_collection_file(file_path: str, file_name: str, overwrite_runs: bool, save_pickles: bool = False,
                         compress_pickles: bool = True, consolidate_results: bool = False) -> str:
    # Worker target for the whole-file scheduler. Must be a top-level function so it can be pickled by
    # multiprocessing on Windows (spawn start method).
    Progress.start_task(file_name, f'Outputs/{file_path}/{file_name}_progress.log')
    try:
        run_model(input_file=file_path, collection_name=file_path, overwrite_runs=overwrite_runs,
                  save_pickles=save_pickles, compress_pickles=compress_pickles,
                  consolidate_results=consolidate_results)
    finally:
        Progress.end_task()
    return file_path


def _run_collection_chunk(file_path: str, file_name: str, start_scen: int, end_scen: int, overwrite_runs: bool,
                          save_pickles: bool = False, compress_pickles: bool = True,
                          consolidate_results: bool = False) -> str:
    # Worker target for the chunked scheduler. Each chunk writes its own partial summary
    # (summary_suffix) so concurrent workers on the same input file never collide, and skips baseline
    # metrics because those need the whole file. The progress log and results store use the same
    # suffix scheme so concurrent chunks of the same file don't collide on one file either.
    Progress.start_task(file_name, f'Outputs/{file_path}/{file_name}_progress__part{start_scen:06d}.log')
    try:
        run_model(input_file=file_path, collection_name=file_path, overwrite_runs=overwrite_runs,
                  starting_scen=start_scen, end_scen=end_scen, save_pickles=save_pickles,
                  compress_pickles=compress_pickles, consolidate_results=consolidate_results,
                  summary_suffix=f'__part{start_scen:06d}', write_parquet=False)
    finally:
        Progress.end_task()
    return f'{file_path}[{start_scen}-{end_scen}]'


def _finalize_chunked_file(file_path: str) -> None:
    """
    Merges a chunked input file's partial summaries into one summary CSV and Parquet store.

    Parameters
    ----------
    file_path : str
        Collection-relative path of the input file, e.g. 'Top20_set/F1_CA_90011_PST_Los Angeles_CA'.

    Returns
    -------
    None
    """
    out_dir = f'Outputs/{file_path}'
    base = file_path.split('/')[-1]
    parts = sorted(f for f in os.listdir(out_dir)
                   if f.startswith(f'{base}_summary__part') and f.endswith('.csv'))
    if not parts:
        return
    frames = [pd.read_csv(os.path.join(out_dir, p)) for p in parts]
    merged = pd.concat(frames, ignore_index=True, axis=0)
    merged = merged.drop_duplicates(subset='ID', keep='last').sort_values('ID').reset_index(drop=True)
    if 'Is Baseline' in merged.columns:
        merged['Is Baseline'] = merged['Is Baseline'].astype('boolean')
    # Deferred from the workers: baseline metrics compare against the no-PV/no-HES/no-V2H scenario,
    # which may well have been simulated by a different chunk.
    merged = update_baseline_metrics(summary_frame=merged)
    merged.to_csv(f'{out_dir}/{base}_summary.csv', index=False)
    _write_results_parquet(merged, f'{out_dir}/{base}_results.parquet')
    for p in parts:
        os.remove(os.path.join(out_dir, p))

    # If consolidate_results was used, each chunk also wrote its own results-store part (.dat +
    # index CSV, same __partNNNNNN suffix scheme as the summary CSVs above). Concatenate the raw
    # bytes and shift each part's index offsets by how much has already been written -- a plain
    # streamed byte-copy, not a full-file read, so this stays cheap regardless of store size.
    store_prefix = f'{base}_results_store'
    store_parts = sorted(f for f in os.listdir(out_dir)
                         if f.startswith(f'{store_prefix}__part') and f.endswith('.dat'))
    if store_parts:
        final_store = f'{out_dir}/{base}_results_store.dat'
        final_index = f'{out_dir}/{base}_results_store_index.csv'
        cumulative = os.path.getsize(final_store) if os.path.exists(final_store) else 0
        with open(final_store, 'ab') as out_f, open(final_index, 'a') as out_idx:
            for p in store_parts:
                suffix = p[len(store_prefix):-len('.dat')]  # e.g. '__part000001'
                part_store = os.path.join(out_dir, p)
                part_index = os.path.join(out_dir, f'{base}_results_store_index{suffix}.csv')
                part_size = os.path.getsize(part_store)
                with open(part_store, 'rb') as in_f:
                    out_f.write(in_f.read())
                if os.path.exists(part_index):
                    with open(part_index) as in_idx:
                        for line in in_idx:
                            sid, off, ln = line.rstrip('\n').split(',')
                            out_idx.write(f'{sid},{int(off) + cumulative},{ln}\n')
                    os.remove(part_index)
                cumulative += part_size
                os.remove(part_store)


def _plan_chunks(file_paths: list, workers: int, chunk_size: int = None) -> list:
    """
    Builds the (input file, scenario range) task list for the chunked scheduler.

    Chunk size is deliberately large. Every chunk begins with ``prev_row = None``, so its first
    scenario has to rebuild the tariff, house, grid, PV and fleet from disk (0.6-1.4 s) because
    get_reset_dict cannot reuse components across a chunk boundary. At 500 scenarios per chunk that
    overhead is about 0.3%; at 50 it is about 3%. Targeting ~3 chunks per worker keeps the pool fed
    for load balancing without paying the rebuild tax more often than necessary.

    Parameters
    ----------
    file_paths : list of str
        Collection-relative input file paths.
    workers : int
        Number of worker processes the pool will use.
    chunk_size : int, optional
        Force a fixed chunk size instead of deriving one.

    Returns
    -------
    list of tuple
        ``(file_path, start_scenario_id, end_scenario_id)`` triples, largest files first.
    """
    counts = []
    for fp in file_paths:
        try:
            n = len(pd.read_excel(f'InputFiles/{fp}.xlsx', header=2, usecols=['ScenarioID']))
        except Exception:  # unreadable file -- let run_model raise the real error in the worker
            n = 0
        counts.append((fp, n))

    total = sum(n for _, n in counts)
    if chunk_size is None:
        target_chunks = max(workers * 3, 1)
        chunk_size = max(200, -(-total // target_chunks))  # ceiling division, floored at 200

    tasks = []
    for fp, n in sorted(counts, key=lambda x: -x[1]):  # longest-processing-time first
        if n == 0:
            tasks.append((fp, 1, 1))
            continue
        for start in range(1, n + 1, chunk_size):
            tasks.append((fp, start, min(start + chunk_size - 1, n)))
    return tasks


def _count_scenarios(file_paths: list, file_names: list) -> dict:
    # Only used to size GUI progress bars, so it's skipped entirely unless show_gui=True.
    totals = {}
    for fp, fn in zip(file_paths, file_names):
        try:
            n = len(pd.read_excel(f'InputFiles/{fp}.xlsx', header=2, usecols=['ScenarioID']))
        except Exception:
            n = 0
        totals[fn] = n
    return totals


def _next_adaptive_piece(state: dict, chunk_floor: int, first_touch_divisor: int = 1):
    """
    Picks the next (file_name, start, end) scenario range for the adaptive scheduler.

    While a file has never been touched, hands out its whole range in one piece -- zero rebuild
    overhead, same as whole-file scheduling -- unless there are more workers than files, in which
    case first_touch_divisor pre-splits every file's first slice evenly so every worker still gets
    real work in the initial round instead of a few workers claiming whole files while the rest sit
    idle waiting for the untouched-file supply to run out.

    Once every file has been touched at least once -- i.e. fewer files remain than workers wanting
    work -- splits the largest remaining *undispatched* tail in half instead, so a freed worker never
    waits on an entire straggler file; it just peels off another slice, and the slice after that
    halves again. Ranges already claimed by another worker are never touched, so nothing is ever
    recomputed and no running worker needs to be interrupted.

    Parameters
    ----------
    state : dict
        file_name -> {'next_start': int, 'end': int, 'touched': bool}, mutated in place.
    chunk_floor : int
        Minimum piece size once splitting -- avoids slicing so thin that the per-piece
        component-rebuild cost described in _plan_chunks starts to matter.
    first_touch_divisor : int, optional
        How many pieces to pre-split each file's first touch into. 1 (default) hands out the whole
        file, matching whole-file scheduling; used when there are more workers than files so priming
        the pool doesn't hand out every file whole before all workers have something to run.

    Returns
    -------
    tuple or None
        (file_name, start, end), or None once every file is fully dispatched.
    """
    untouched = [fn for fn, s in state.items() if not s['touched'] and s['next_start'] <= s['end']]
    if untouched:
        fn = max(untouched, key=lambda k: state[k]['end'] - state[k]['next_start'] + 1)
        start = state[fn]['next_start']
        remaining = state[fn]['end'] - start + 1
        piece = remaining if first_touch_divisor <= 1 else \
            min(remaining, max(chunk_floor, -(-remaining // first_touch_divisor)))
        end = start + piece - 1
        state[fn]['touched'] = True
        state[fn]['next_start'] = end + 1
        return fn, start, end

    candidates = [fn for fn, s in state.items() if s['next_start'] <= s['end']]
    if not candidates:
        return None
    fn = max(candidates, key=lambda k: state[k]['end'] - state[k]['next_start'] + 1)
    start = state[fn]['next_start']
    remaining = state[fn]['end'] - start + 1
    piece = remaining if remaining <= chunk_floor else max(chunk_floor, remaining // 2)
    end = start + piece - 1
    state[fn]['next_start'] = end + 1
    return fn, start, end


def run_collection(collection_path: str, overwrite_runs: bool = True, parallel: bool = True,
                   max_workers: int = None, schedule: str = 'auto', chunk_size: int = None,
                   save_pickles: bool = False, compress_pickles: bool = True,
                   console_verbose: bool = False, show_gui: bool = False,
                   consolidate_results: bool = False):
    """
    Runs every scenario input file within a collection subdirectory of InputFiles.

    Parameters
    ----------
    collection_path : str
        Name of the subdirectory within InputFiles containing the scenario files for this collection.
    overwrite_runs : bool, optional
        Whether to overwrite previously completed scenarios. Default is True.
    parallel : bool, optional
        Whether to run concurrently in separate processes. Default is True.
    max_workers : int, optional
        Number of worker processes. Defaults to os.cpu_count() (leaving one core free is often wise if
        you want to keep using the machine while this runs).
    schedule : {'auto', 'file', 'chunk'}, optional
        How work is distributed across the pool.

        ``'file'``
            One task per input file. Simple, zero rebuild overhead, and each worker keeps its
            component-reuse chain intact for the whole file -- but a task can't be subdivided once
            running, so if fewer files remain than workers, the extra workers just go idle.
        ``'chunk'``
            Every file is pre-split into (input file, scenario range) tasks from the start, via
            _plan_chunks. Cores stay saturated the whole run, at the cost of a small component-rebuild
            tax (see _plan_chunks) on every file, even while there'd have been enough whole files to
            go around anyway.
        ``'auto'``
            Default, and generally the best choice. Adaptive scheduling (see _next_adaptive_piece):
            hands out whole files while there are enough untouched ones for every worker (zero
            overhead, same as ``'file'``), and only starts splitting a file's undispatched tail once a
            worker frees up with no untouched file left to give it -- i.e. exactly when fewer files
            remain than workers. Splits keep halving the largest remaining tail, so no core ever waits
            on a single straggler for long, without paying the chunk rebuild tax on files that never
            needed splitting in the first place.

        Why this matters: files are not equal. Top20_PV_HES_set is 17 files of 2,079 scenarios and 3 of
        4,158, so naive whole-file scheduling (with no splitting at all) cannot finish before the
        largest file does -- modelled as greedy longest-task-first, that would leave roughly 4% of
        cores idle at 8-12 workers but 28% at 16, 43% at 20 and 64% at 32. ``'auto'`` avoids this
        without needing ``'chunk'``'s always-on rebuild tax.
    chunk_size : int, optional
        Scenarios per chunk when chunking. Derived from the workload if omitted; see _plan_chunks.
    save_pickles : bool, optional
        Write per-scenario pickles. Default False -- results go to the per-file Parquet store.
    compress_pickles : bool, optional
        gzip those pickles (``..._Run_N.pkl.gz``). Default True; about 9x smaller, lossless, and
        readers accept compressed and uncompressed files interchangeably.
    console_verbose : bool, optional
        Print every per-scenario completion/error line as it happens. Default False, which prints only
        the file/chunk-level banners. Regardless of this flag, worker processes never print directly --
        all progress travels through a queue to a single main-process listener thread, so turning this
        on is always cleanly ordered rather than interleaved raw output from multiple processes. The
        per-scenario ETA line and full exception tracebacks always go to a per-file/-chunk log file
        (``<file>_progress[__partNNNNNN].log`` next to that file's other outputs) whether or not this is
        set. See Progress.py.
    show_gui : bool, optional
        Pop up a Tkinter window with one progress bar per input file, plus which worker slot(s) are
        currently on it. Default False. Reporting progress costs one non-blocking queue put and one log
        line per scenario -- negligible next to a ~1.4 s scenario -- so this adds no meaningful runtime
        whether or not it's enabled.
    consolidate_results : bool, optional
        When save_pickles is in effect, write each input file's per-scenario results into one shared
        store (``<file>_results_store.dat`` + an index CSV) instead of thousands of individual
        ``..._Run_N.pkl(.gz)`` files. Default False, preserving today's layout. See
        Simulation.save_result_to_store / load_result_from_store.

    Returns
    -------
    None

    Notes
    -----
    -   IMPORTANT (Windows): because this uses multiprocessing, the script that calls run_collection with
        parallel=True MUST guard its top-level call with `if __name__ == '__main__':`. Without this guard,
        each worker process will re-import and re-execute the calling script, which on Windows' spawn start
        method causes runaway recursive process spawning.
    """
    if schedule not in ('auto', 'file', 'chunk'):
        raise ValueError(f"schedule must be 'auto', 'file' or 'chunk', got {schedule!r}")

    master_path = f'InputFiles/{collection_path}'
    os.makedirs(f'Outputs/{collection_path}', exist_ok=True)

    all_dirs = os.listdir(master_path)
    all_dirs = sorted(all_dirs, key=lambda x: int(x.split('_')[0][1:]))

    file_paths = []
    file_names = []
    for file_name in all_dirs:
        if file_name.count('.') == 2:
            name = ".".join(file_name.split('.')[:2])
        else:
            name = file_name.split('.')[0]
        file_paths.append(f'{collection_path}/{name}')
        file_names.append(file_name)
        # each input file gets its own output subdirectory, so pre-creating them here avoids any race between
        # worker processes creating the same directory simultaneously.
        os.makedirs(f'Outputs/{collection_path}/{name}', exist_ok=True)
        os.makedirs(f'Outputs/{collection_path}/{name}/Results', exist_ok=True)

    # Workers report progress through this queue instead of printing directly; a single listener
    # thread in this process is the only thing that ever writes to the console (see Progress.py).
    # init_worker() here too so the non-parallel fallback below -- which runs run_model() directly in
    # this process rather than in a pool worker -- reports through the same pipeline.
    progress_queue = multiprocessing.Queue()
    Progress.init_worker(progress_queue)
    listener = Progress.ProgressListener(progress_queue, console_verbose=console_verbose)

    try:
        if not (parallel and len(file_paths) > 1):
            def _drive():
                for file_path, file_name in zip(file_paths, file_names):
                    print(f'********************INPUT FILE - {file_name} starting*************')
                    Progress.start_task(file_name, f'Outputs/{file_path}/{file_name}_progress.log')
                    try:
                        run_model(input_file=file_path, collection_name=file_path, overwrite_runs=overwrite_runs,
                                  save_pickles=save_pickles, compress_pickles=compress_pickles,
                                  consolidate_results=consolidate_results)
                    finally:
                        Progress.end_task()
                    print(f'********************INPUT FILE - {file_name} COMPLETED*************')

            if show_gui:
                gui = Progress.ProgressGui(_count_scenarios(file_paths, file_names))
                listener.attach_gui(gui)
                Progress.drive_with_gui(_drive, gui)
            else:
                _drive()
            return

        max_workers = max_workers or os.cpu_count() or 1

        if schedule == 'auto':
            # Adaptive scheduling: hand out whole files while there are enough of them to go around
            # (zero rebuild overhead), and only start splitting a file's undispatched tail once a
            # worker frees up with no untouched file left to give it -- i.e. exactly when fewer files
            # remain than workers wanting work. See _next_adaptive_piece.
            fn_to_fp = dict(zip(file_names, file_paths))
            counts = _count_scenarios(file_paths, file_names)
            chunk_floor = chunk_size or 200
            first_touch_divisor = (-(-max_workers // len(file_paths))
                                    if len(file_paths) < max_workers else 1)
            state = {fn: {'next_start': 1, 'end': max(counts[fn], 1), 'touched': False}
                     for fn in file_names}
            total_scenarios = sum(s['end'] for s in state.values())
            failed_files = set()

            def _drive():
                print(f'Running {len(file_paths)} input files ({total_scenarios} scenarios) across up '
                      f'to {max_workers} worker processes (adaptive scheduling)...')
                with concurrent.futures.ProcessPoolExecutor(
                        max_workers=max_workers, initializer=Progress.init_worker,
                        initargs=(progress_queue,)) as executor:
                    pending = {}

                    def _submit_next():
                        piece = _next_adaptive_piece(state, chunk_floor, first_touch_divisor)
                        if piece is None:
                            return
                        fn, s, e = piece
                        fut = executor.submit(_run_collection_chunk, fn_to_fp[fn], fn, s, e,
                                              overwrite_runs, save_pickles, compress_pickles,
                                              consolidate_results)
                        pending[fut] = (fn_to_fp[fn], fn, s, e)

                    for _ in range(max_workers):
                        _submit_next()

                    while pending:
                        done, _ = concurrent.futures.wait(pending.keys(),
                                                           return_when=concurrent.futures.FIRST_COMPLETED)
                        for future in done:
                            fp, fn, s, e = pending.pop(future)
                            try:
                                future.result()
                                print(f'  chunk {fn} scenarios {s}-{e} complete')
                            except Exception as ex:
                                failed_files.add(fp)
                                print(f'  chunk {fn} scenarios {s}-{e} FAILED: {ex}')
                            _submit_next()

                for file_path, file_name in zip(file_paths, file_names):
                    try:
                        _finalize_chunked_file(file_path)
                        status = 'COMPLETED' if file_path not in failed_files else 'COMPLETED WITH FAILED CHUNKS'
                        print(f'********************INPUT FILE - {file_name} {status}*************')
                    except Exception as ex:
                        print(f'********************INPUT FILE - {file_name} MERGE FAILED: {ex}*************')

            if show_gui:
                totals = {fn: state[fn]['end'] for fn in file_names}
                gui = Progress.ProgressGui(totals)
                listener.attach_gui(gui)
                Progress.drive_with_gui(_drive, gui)
            else:
                _drive()
            return

        if schedule == 'file':
            def _drive():
                print(f'Running {len(file_paths)} input files across up to {max_workers} worker processes...')
                with concurrent.futures.ProcessPoolExecutor(
                        max_workers=max_workers, initializer=Progress.init_worker,
                        initargs=(progress_queue,)) as executor:
                    futures = {executor.submit(_run_collection_file, fp, fn, overwrite_runs, save_pickles,
                                               compress_pickles, consolidate_results): fn
                               for fp, fn in zip(file_paths, file_names)}
                    for future in concurrent.futures.as_completed(futures):
                        file_name = futures[future]
                        try:
                            future.result()
                            print(f'********************INPUT FILE - {file_name} COMPLETED*************')
                        except Exception as ex:
                            print(f'********************INPUT FILE - {file_name} FAILED: {ex}*************')

            if show_gui:
                gui = Progress.ProgressGui(_count_scenarios(file_paths, file_names))
                listener.attach_gui(gui)
                Progress.drive_with_gui(_drive, gui)
            else:
                _drive()
            return

        # schedule == 'chunk'
        tasks = _plan_chunks(file_paths, max_workers, chunk_size)
        fp_to_fn = dict(zip(file_paths, file_names))
        failed_files = set()

        def _drive():
            print(f'Running {len(tasks)} scenario chunks from {len(file_paths)} input files '
                  f'across up to {max_workers} worker processes...')
            with concurrent.futures.ProcessPoolExecutor(
                    max_workers=max_workers, initializer=Progress.init_worker,
                    initargs=(progress_queue,)) as executor:
                futures = {executor.submit(_run_collection_chunk, fp, fp_to_fn[fp], s, e, overwrite_runs,
                                           save_pickles, compress_pickles, consolidate_results): (fp, s, e)
                           for fp, s, e in tasks}
                done = 0
                for future in concurrent.futures.as_completed(futures):
                    fp, s, e = futures[future]
                    done += 1
                    try:
                        future.result()
                        print(f'  [{done}/{len(tasks)}] chunk {fp} scenarios {s}-{e} complete')
                    except Exception as ex:
                        failed_files.add(fp)
                        print(f'  [{done}/{len(tasks)}] chunk {fp} scenarios {s}-{e} FAILED: {ex}')

            for file_path, file_name in zip(file_paths, file_names):
                try:
                    _finalize_chunked_file(file_path)
                    status = 'COMPLETED' if file_path not in failed_files else 'COMPLETED WITH FAILED CHUNKS'
                    print(f'********************INPUT FILE - {file_name} {status}*************')
                except Exception as ex:
                    print(f'********************INPUT FILE - {file_name} MERGE FAILED: {ex}*************')

        if show_gui:
            totals = {}
            for fp, s, e in tasks:
                fn = fp_to_fn[fp]
                totals[fn] = totals.get(fn, 0) + (e - s + 1)
            gui = Progress.ProgressGui(totals)
            listener.attach_gui(gui)
            Progress.drive_with_gui(_drive, gui)
        else:
            _drive()
    finally:
        listener.stop()
