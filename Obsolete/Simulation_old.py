import numpy as np
import pandas
import pandas as pd
import Components as cp
import Setup as sp
import Parameters as pm
import TimeManage as tm
import copy

pandas.set_option('display.max_columns', None)


# Define Results and Bill Classes
class Bill:
    def __init__(self, op: pm.Operation, timekeep: pm.TimeKeep, energy: cp.Energy, tariff: pm.Tariff, city: pm.City,
                 grid: cp.Grid):
        self.summary = pd.DataFrame()
        self.total = 0
        self.blah = 'blah'
        self.generate_bill(op=op, timekeep=timekeep, energy=energy, tariff=tariff, city=city, grid=grid)
        self.total_bill = np.sum(self.summary['After Tax Total'].to_numpy())
        self.co2_emissions = np.sum(self.summary['CO2 Emissions'].to_numpy())

    def generate_bill(self, op: pm.Operation, timekeep: pm.TimeKeep, energy: cp.Energy, tariff: pm.Tariff,
                      city: pm.City, grid: cp.Grid):
        # this returns a bill summary in the form of a pandas dataframe
        # in the first half of this function, we assess the columns that will be in bill
        column = ['Period Start', 'Period End', 'House Load', 'Fleet Load', 'Fleet Out', 'HES Load', 'HES Out',
                  'Solar Output', 'Total Usage', 'Total Outflow', 'System Loss', 'CO2 Emissions']
        one_to_one = op.net_meter_scheme in ['One-to-One', 'one-to-one']
        if tariff.is_tou:  # tariff is time of use
            add_col = []
            for i in range(len(tariff.unique_tou_rates)):
                num = i + 1
                add_col.append('Rate ' + str(num) + ': Unit Cost')
                add_col.append('Rate ' + str(num) + ': Usage')
                if one_to_one:
                    add_col.append('Rate ' + str(num) + ': Outflow')
                    add_col.append('Rate ' + str(num) + ': Net')
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

        if not one_to_one:
            column += ['Solar Credit']  # we add this column if there is flat rate for solar sent to grid

        column += ['Monthly Charge', 'Subtotal', 'After Tax Total']

        bill_summary = pd.DataFrame(columns=column)

        emissions = grid.emissions_rate[timekeep.simu_start_step - 1:timekeep.simu_end_step] * energy.grid_out

        # now we iterate through the months contained in the simulation
        # calculate starting steps for each month, so we can demarcate the months
        # month_starts = (timekeep.month_switch[1:] - 1) * 24 * (60 / timekeep.timestep) + 1
        # month_starts = month_starts[month_starts >= timekeep.simu_start_step]  # eliminate values less than start step
        # month_starts = month_starts[month_starts <= timekeep.simu_end_step]  # eliminate values greater than end step
        # month_starts = np.concatenate([[timekeep.simu_start_step], month_starts, [timekeep.simu_end_step]])
        # month_starts = month_starts.astype(int)
        month_inds = tm.month_indices_from_calendar(timekeep.calendar)

        for i in range(month_inds.shape[0]):
            s_ind_t = month_inds[i, 0]  # start index for tariff and calendar array
            e_ind_t = month_inds[i, 1]   # start index for tariff and calendar array
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
                    data[col] = round(subtotal, 2)
                elif col == 'After Tax Total':
                    data[col] = round(subtotal * (1 + city.tax_rate), 2)
                elif col == 'Solar Credit':
                    val = total_outflow * op.avoided_rate
                    subtotal -= val
                    data[col] = round(val, 2)
                elif col[0:4] == 'Tier':
                    spl = col.split()
                    tier = int(spl[1][0:-1])
                    if tier <= num_tiers:
                        head = spl[-1]  # information asked for by column
                        if head == 'Cap':
                            if tier != 1:
                                data[col] = max(tariff.periods_energy[per][tier - 1][0] - cap, 0)
                                cap = tariff.periods_energy[per][tier - 1][0]
                            else:
                                data[col] = cap
                        elif head == 'Usage':
                            cap = data[spl[0] + ' ' + spl[1] + ' Cap']
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
                            data[col] = tariff.periods_energy[per][tier - 1][1]
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
                    elif head == 'Subtotal':
                        if one_to_one:
                            amount = data[spl[0] + ' ' + spl[1] + ' Net']
                        else:
                            amount = data[spl[0] + ' ' + spl[1] + ' Usage']
                        if amount < 0:
                            val = amount * op.avoided_rate  # if negative, we apply avoided rate
                        else:
                            val = amount * data[spl[0] + ' ' + spl[1] + ' Unit Cost']
                        data[col] = round(val, 2)
                        subtotal += val
            to_add = pd.DataFrame(data=data, index=[i])
            bill_summary = pd.concat([bill_summary, to_add], ignore_index=True, axis=0)
        self.summary = bill_summary


class Results:
    def __init__(self, operation: pm.Operation, tariff: pm.Tariff, timekeep: pm.TimeKeep, city: cp.City, grid: cp.Grid,
                 energy: cp.Energy, hes: cp.HES, pv: cp.PV, house: cp.House, fleet: cp.Fleet, ice: cp.ICE):
        self.operation = operation
        self.tariff = tariff
        self.timekeep = timekeep
        self.energy = energy
        self.city = city
        self.grid = grid
        self.hes = hes
        self.pv = pv
        self.house = house
        self.fleet = fleet
        self.bill = Bill(op=operation, timekeep=timekeep, energy=energy, tariff=tariff, city=city, grid=grid)

        # avoided costs associated with component use in lieu of grid
        tou_costs = tariff.tou_schedule[(timekeep.simu_start_step - 1):timekeep.simu_end_step, 0]
        tou_costs = tou_costs.reshape(len(tou_costs), 1)

        emissions = grid.emissions_rate[(timekeep.simu_start_step - 1):timekeep.simu_end_step, 0]
        emissions = emissions.reshape(len(emissions), 1)

        if hes.exists and operation.track_costs_of_use:
            self.hes_avoidance = np.sum(np.multiply(tou_costs - hes.cost_of_uses, energy.hes_to_house)) * (
                    1 + city.tax_rate)
            self.hes_co2_savings = np.sum(np.multiply(emissions - hes.emissivity_arr, energy.hes_to_house))
        else:
            self.hes_avoidance = 0
            self.hes_co2_savings = 0

        if pv.exists:
            self.solar_avoidance = np.sum(np.multiply(tou_costs, energy.pv_to_house)) * (1 + city.tax_rate)
            self.solar_co2_savings = np.sum(np.multiply(emissions, energy.pv_to_house))
        else:
            self.solar_avoidance = 0
            self.solar_co2_savings = 0

        if not fleet.no_evs():
            self.ev_avoidances = np.array([])
            self.ev_co2_savings = np.array([])
            self.gas_costs = np.array([])
            self.driving_costs = np.array([])
            for ev in fleet.ev_list:
                ev2h = energy.ev_to_house[:, ev.EViD - 1]
                ev2h = ev2h.reshape(len(ev2h), 1)
                avoidance = np.sum(np.multiply(tou_costs - ev.cost_of_uses, ev2h)) * (1 + city.tax_rate)
                co2_savings = np.sum(np.multiply(emissions - ev.emissivity_arr, ev2h))
                self.ev_avoidances = np.append(self.ev_avoidances, [avoidance])
                self.ev_co2_savings = np.append(self.ev_co2_savings, [co2_savings])
                self.gas_costs = np.append(self.gas_costs, [ev.miles_driven *
                                           ice.cost_per_mile(gas_cost=operation.cost_of_gas)])
                self.driving_costs = np.append(self.driving_costs, [ev.cost_of_driving])
            self.fleet_avoidance = np.sum(self.ev_avoidances)
            self.fleet_gas_costs = np.sum(self.gas_costs)
            self.fleet_driving_costs = np.sum(self.driving_costs)
            self.gas_savings = self.fleet_gas_costs - self.fleet_driving_costs
            self.fleet_co2_savings = np.sum(self.ev_co2_savings)
        else:
            self.ev_avoidances = 0
            self.fleet_avoidance = 0
            self.gas_cost = 0
            self.fleet_gas_costs = 0
            self.driving_costs = 0
            self.fleet_driving_costs = 0
            self.gas_savings = 0
            self.ev_co2_savings = 0
            self.fleet_co2_savings = 0

        self.total_system_savings = self.hes_avoidance + self.fleet_avoidance + self.solar_avoidance + self.gas_savings

        do_sanity = True
        if do_sanity:
            system_in = energy.grid_out  # + energy.pv_out + energy.ev_out_total + energy.hes_out
            system_out_or_stored = energy.grid_in + energy.house_in + energy.loss
            if pv.exists:
                system_in += energy.pv_out
            if not fleet.no_evs():
                system_in += energy.ev_out_total
                system_out_or_stored += energy.ev_in_total
            if hes.exists:
                system_in += energy.hes_out
                system_out_or_stored += energy.hes_in

            self.sanity = np.hstack((system_in, system_out_or_stored, system_in - system_out_or_stored))
            self.check_sum = np.sum(self.sanity[:, 2])


def update_comp_status(operation: pm.Operation, tariff: pm.Tariff, fleet: cp.Fleet, hes: cp.HES, timekeep: pm.TimeKeep):
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
    if not fleet.no_evs():
        for ev in fleet.ev_list:
            if ev.is_here(timekeep.step - 1):
                ev.can_be_used_update(True)
                if operation.ev_as_source:
                    if ev.soc >= ev.soc_max:  # ev is full
                        ev.must_be_source_update(True)
                    elif ev.soc <= ev.soc_min:
                        ev.must_be_sink_update(True)
                    elif ev.soc <= ev.discharge_limit:  # ev is depleted past amount where ev2house is allowed
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


def sinks_and_sources(operation: pm.Operation, fleet: cp.Fleet, pv: cp.PV,
                      hes: cp.HES, grid: cp.Grid, house: cp.House, timekeep: pm.TimeKeep):
    # function creates list of sinks and sources comprised of lists.
    # sinks are sorted on rank (house first, ev second, HES third (if applicable)
    # sources are sorted based on cost of use
    # all components other than EV's have IDs of 1.
    # sink lists --> [name, ID, energy required, priority(rank)]
    # source lists --> [name, ID, energy available, priority(cost of use)]
    sinks = []
    sources = []

    # PV
    if pv.exists:
        pv_energy = pv.get_energy_available(timekeep.step - 1, timekeep.timestep)
        if pv_energy > 0:  # only add to sources if it has energy
            sources.append([pv.name, 1, pv_energy, 0])

    # House
    sinks.append([house.name, 1, house.energy_required, house.sink_priority])

    # Grid
    sources.append([grid.name, 1, np.inf, grid.cost_of_use])

    # HES
    if hes.exists:
        hes_max_input = hes.charge_rate() * (timekeep.timestep / 60)  # rated max energy input
        hes_cap_in = (hes.soc_max - hes.soc) * hes.batterySize  # max input based on remaining capacity
        hes_energy_needed = min(hes_cap_in, hes_max_input)  # energy that can be put in
        hes_cap_out = (hes.soc - hes.soc_min) * hes.batterySize  # max output based on remaining capacity
        hes_max_output = hes.max_discharge * (timekeep.timestep / 60)  # rated max energy output
        hes_energy_available = min(hes_cap_out, hes_max_output)  # energy that can be taken out
        hes_sink = [hes.name, 1, hes_energy_needed, hes.sink_priority]
        hes_source = [hes.name, 1, hes_energy_available, hes.cost_of_use]
        if hes.must_be_source:  # HES is full and can only be a source
            if timekeep.step in hes.coverage_steps:  # prescribed HES coverage period (from optimization)
                sources.append(hes_source)
        elif hes.must_be_sink:  # HES is depleted and must be a sink
            sinks.append(hes_sink)
        elif hes.can_be_sink and not hes.can_be_source:
            sinks.append(hes_sink)
        elif hes.can_be_source and not hes.can_be_sink:
            sources.append(hes_source)
        else:  # can be either sink or source. it will be whatever is required of it first
            sinks.append(hes_sink)
            sources.append(hes_source)

    # Fleet/ EVs
    if not fleet.no_evs():
        for ev in fleet.ev_list:
            ev_max_input = ev.charge_rate() * (timekeep.timestep / 60)
            ev_cap_in = (ev.soc_max - ev.soc) * ev.batterySize
            ev_energy_needed = min(ev_cap_in, ev_max_input)
            ev_max_output = operation.ev_throughput * (timekeep.timestep / 60)
            ev_cap_out = (ev.soc_max - ev.discharge_limit) * ev.batterySize
            # we must correct for negatives if discharge limit > soc
            ev_energy_available = max(min(ev_max_output, ev_cap_out), 0)
            ev_sink = [ev.name, ev.EViD, ev_energy_needed, ev.sink_priority]
            ev_source = [ev.name, ev.EViD, ev_energy_available, ev.cost_of_use]
            if ev.can_be_used:
                if ev.must_be_sink:
                    sinks.append(ev_sink)
                elif ev.must_be_source:
                    sources.append(ev_source)
                elif ev.can_be_sink and not ev.can_be_source:
                    sinks.append(ev_sink)
                elif ev.can_be_source and not ev.can_be_sink:
                    sources.append(ev_source)
                else:  # can be either sink or source. it will be whatever is required of it first
                    sinks.append(ev_sink)
                    sources.append(ev_source)

    # Sort Sinks and Sources

    sinks.sort(key=lambda sink: sink[3])
    sources.sort(key=lambda source: source[3])

    return sinks, sources


def energy_flows(operation: pm.Operation, fleet: cp.Fleet, pv: cp.PV, tariff: pm.Tariff, hes: cp.HES, grid: cp.Grid,
                 house: cp.House, timekeep: pm.TimeKeep, energy: cp.Energy, sinks: list, sources: list):
    cell = [-1, -1]
    for sink in sinks:
        sink_name = sink[0]
        sink_id = sink[1]
        sink_energy = sink[2]

        for source in sources:
            source_name = source[0]
            source_id = source[1]
            # source_energy = source[2]
            # source_cost_of_use = source[3]
            can_be_supplied = sink_energy > 0  # can only supply if sink needs/can fit more
            can_supply = False  # we assume source cannot provide until proven otherwise
            if (source[2] > 0) and can_be_supplied:  # source can only be used if it has energy
                if sink_name == 'House':
                    if source_name == 'PV':
                        cell = [0, 5]
                        can_supply = True
                    elif source_name == 'HES':
                        if not hes.used_as_sink:
                            cell = [1, 5]
                            can_supply = True
                            hes.was_used_as_source()
                    elif source_name == 'EV':
                        # EV can't be source if already used by sink, if currently off-peak,and if it will later have
                        # to charge at current grid rate
                        as_sink = fleet.ev_list[source_id - 1].used_as_sink
                        deadline = fleet.ev_list[source_id - 1].step_to_start_charging
                        match_rate = tariff.get_tou_rate(timekeep.step) == tariff.get_tou_rate(deadline)
                        if (not as_sink) and (not tariff.is_off_peak(step=timekeep.step)) and (not match_rate):
                            cell = [2, 5]
                            can_supply = True
                            fleet.was_used_as_source(ev_id=source_id)
                    elif source_name == 'Grid':
                        cell = [4, 5]
                        can_supply = True
                        grid.was_used_as_source()
                elif sink_name == 'EV':
                    if not fleet.ev_list[sink_id - 1].used_as_source:
                        if source_name == 'PV':
                            cell = [0, 2]
                            can_supply = True
                        elif source_name == 'HES':
                            if not hes.used_as_sink:
                                cell = [1, 2]
                                can_supply = True
                                hes.was_used_as_source()
                        elif source_name == 'EV':
                            can_supply = False  # no EV to EV functionality for now
                        elif source_name == 'Grid':
                            # EV will only pull from grid during off-peak (or because it must meet departure deadline)
                            must_charge = (timekeep.step >= fleet.ev_list[sink_id - 1].step_to_start_charging) and (
                                    timekeep.step < fleet.ev_list[sink_id - 1].next_deadline)
                            if tariff.is_off_peak(timekeep.step) or must_charge:
                                cell = [4, 2]
                                can_supply = True
                                grid.was_used_as_source()

                        if can_supply:
                            fleet.was_used_as_sink(ev_id=sink_id)

                elif sink_name == 'HES':
                    if not hes.used_as_source:
                        if source_name == 'PV':
                            cell = [0, 1]
                            can_supply = True
                        elif source_name == 'HES':  # can't happen
                            can_supply = False
                        elif source_name == 'EV':  # not allowed
                            can_supply = False
                        elif source_name == 'Grid':
                            # cannot charge from grid during peaks, and not until necessary during off-peak
                            if tariff.is_off_peak(timekeep.step) and (timekeep.step >= hes.step_to_start_charging) and tariff.is_tou:
                                cell = [4, 1]
                                can_supply = True
                                grid.was_used_as_source()
                        if can_supply:
                            hes.was_used_as_sink()

                else:
                    print('how did you get here?')

            # We now try and find the energy received by the sink, and sent by the source. Note that e_sent will
            # always be greater than e_received due to efficiency losses
            if can_supply:
                eff = operation.efficiencies[cell[0], cell[1]]
                if source_name == 'Grid':  # if source is grid, we supply the rest of the energy that the sink can take
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

    if (sources[0][0] == 'PV') & (sources[0][2] > 0):
        cell = [0, 4]
        eff = operation.efficiencies[cell[0], cell[1]]
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

    if not fleet.no_evs():
        for ev in fleet.ev_list:
            if ev.was_used_as_source():
                ev.update_charging_step()
            ev.status_reset()
        fleet.reset_sink_source()


def optimize_hes(operation: pm.Operation, city: pm.City, tariff: pm.Tariff, fleet: cp.Fleet, pv: cp.PV,
                 hes: cp.HES, grid: cp.Grid, house: cp.House, timekeep: pm.TimeKeep):
    periods = tariff.return_periods(tariff.end_of_current + 1, min(tariff.next_off - 1, timekeep.simu_end_step))
    periods.sort(key=lambda x: (-x[4], -x[3]))

    if operation.hes_optimization in ['Perfect', 'perfect']:
        a = 1
        if not fleet.no_evs():
            a = 2

    elif operation.hes_optimization in ['simple', 'Simple']:  # house load minus pv in, ignore ev
        coverage_steps = np.array([])
        hes_cap_left = hes.free_cap * operation.efficiencies[0, 5]
        latest_peak = 0  # position of the latest peak period
        earliest_peak = 0  # position of the earliest peak period (will equal the latest if only one peak period
        for per in periods:
            pv_in = np.sum(pv.power[(per[1] - 1): (per[2] - 1)]) * timekeep.timestep / 60
            house_need = np.sum(house.load_profile[(per[1] - 1): (per[2] - 1)]) * (timekeep.timestep / 60)
            e_needed = house_need - pv_in
            if per[4] == 1:  # period is on-peak, and thus is automatically added
                hes_cap_left -= e_needed
                hes_cap_left = max(hes_cap_left, 0)
                new_steps = np.linspace(start=per[1], stop=per[2], num=per[2] - per[1] + 1, dtype=int)
                coverage_steps = np.append(coverage_steps, new_steps)
                latest_peak = max(latest_peak, per[0])
                earliest_peak = min(earliest_peak, per[0])
            elif operation.hes_cover_mid:  # period is mid-peak, but mid-peak coverage is enabled
                #  only add if there is energy left to provide or if last period of non-off-peak region
                if hes_cap_left > e_needed:  # hes has cap left to cover
                    hes_cap_left -= e_needed
                    hes_cap_left = max(hes_cap_left, 0)
                    new_steps = np.linspace(start=per[1], stop=per[2], num=per[2] - per[1] + 1, dtype=int)
                    coverage_steps = np.append(coverage_steps, new_steps)
                else:  # hes does not have capacity left to cover period in full
                    # in this case, we can only cover periods after the latest peak period lest we run out of energy
                    # for upcoming peak period
                    if per[0] > latest_peak:
                        hes_cap_left = 0
                        new_steps = np.linspace(start=per[1], stop=per[2], num=per[2] - per[1] + 1, dtype=int)
                        coverage_steps = np.append(coverage_steps, new_steps)
        hes.update_coverage_steps(coverage_steps)
        target_soc = hes.soc_min + (hes.free_cap - hes_cap_left) / hes.batterySize
        hes.update_soc_to_reach(target_soc=target_soc)

    elif operation.hes_optimization in ['flat', 'Flat']:
        hes.update_soc_to_reach(.8)
        hes.update_coverage_steps(tariff.get_coverage_steps(step=timekeep.step, operation=operation))

    elif operation.hes_optimization in ['Full Charge', 'full charge']:
        hes.update_soc_to_reach(hes.soc_max)
        hes.update_coverage_steps(tariff.get_coverage_steps(step=timekeep.step, operation=operation))

    return None


def run_simulation(operation: pm.Operation, city: pm.City, tariff: pm.Tariff, fleet: cp.Fleet, ice: cp.ICE, pv: cp.PV,
                   hes: cp.HES, grid: cp.Grid, house: cp.House, timekeep: pm.TimeKeep):
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

    if not fleet.no_evs():
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
        # print('Step:', step)
        tou_rate, peak_value = tariff.get_tou_rate(timekeep.step)

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
                    optimize_hes(operation=operation, city=city, tariff=tariff, fleet=fleet, pv=pv, hes=hes, grid=grid,
                                 house=house, timekeep=timekeep)

                else:  # no hes optimization
                    hes.update_soc_to_reach(hes.soc_min)
                    hes.update_coverage_steps(tariff.get_coverage_steps(step=timekeep.step, operation=operation))

                hes.update_charging_step(hes.soc_to_reach)

        # EV Fleet Management
        if not fleet.no_evs():
            for ev in fleet.ev_list:
                if not ev.is_here(timekeep.index):  # ev is not here
                    if (step != timekeep.simu_start_step) and (ev.is_here(timekeep.index - 1)):  # ev just departed
                        ev.drive_miles(ev.driving_pattern[timekeep.index, 2])
                        ev.next_arrival(index=timekeep.index, update=True)

                else:  # ev is here
                    if (step != timekeep.simu_start_step) and (not ev.is_here(timekeep.index - 1)):  # ev just returned
                        ev.update_deadline(ev.next_departure(index=timekeep.index, update=True))
                        if ev.next_deadline < len(ev.driving_pattern):
                            ev.update_charging_step(target_soc=ev.soc_max, timestep=timekeep.timestep)

        # Sinks and Sources
        update_comp_status(operation=operation, fleet=fleet, hes=hes, timekeep=timekeep, tariff=tariff)
        sinks, sources = sinks_and_sources(operation=operation, fleet=fleet, pv=pv, hes=hes, grid=grid, house=house,
                                           timekeep=timekeep)
        a = 1
        energy_flows(operation=operation, fleet=fleet, pv=pv, tariff=tariff, hes=hes, grid=grid, house=house,
                     timekeep=timekeep, energy=energy, sinks=sinks, sources=sources)

        if step == timekeep.hour_end_step:
            timekeep.update_hour()

        if step == timekeep.day_end_step:
            timekeep.update_day()

        # if timekeep.current_day in timekeep.month_switch:  # new day is in new month
        #     timekeep.update_month()

        timekeep.increment_step()

    # Steps have been iterated through, now we summarize results into Bill and Results Objects

    results = Results(operation=operation, tariff=tariff, timekeep=timekeep, city=city, grid=grid, energy=energy,
                      hes=hes, pv=pv, house=house, fleet=fleet, ice=ice)

    return results
