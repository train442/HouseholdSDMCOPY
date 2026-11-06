from tkinter import *
from tkinter import filedialog
import pandas as pd
import numpy as np
from matplotlib import pyplot as plt
from tkinter import ttk

import Simulation as sm
import gui_common
from gui_common import PALETTE, FONT_FAMILY

file_list = []
file_strings = []

plt.ion()
plt.figure(1)

# Allowed colors for first axis
prim_colors = ['b', 'g', 'r', 'c']
second_colors = ['tab:orange', 'm', 'k', 'tab:brown']

p_colors = prim_colors.copy()
s_colors = second_colors.copy()

# plot labels/legend
plt_labels = []
plt1_leg_pos = (1.2, 1)
plt2_labels = []  # separate legend for separate axis
plt2_leg_pos = (1.2, 0)
# Component/Parameter List for Listbox
comp_list = ['Tariff', 'Grid', 'House', 'PV', 'HES', 'EV Fleet', 'Energy Flows']

# Field Lists for Each component
hes_list = ['States of Charge', 'Cost Of Use ($/kWh)', 'Emissivity (kg CO2/kWh)']
ev_list = ['States of Charge', 'Cost Of Use ($/kWh)', 'Emissivity (kg CO2/kWh)', 'Driving Pattern']
pv_list = ['Raw GHI (W/m2)', 'Power (kW)']
grid_list = ['Cost Of Use ($/kWh)', 'Emissivity (kg CO2/kWh)']
house_list = ['Load (kW)', 'Energy Required (kWh)']
energy_list = ['Grid-to-House', 'Grid-to-HES', 'Grid-to-EV', 'Grid-to-Fleet', 'Grid-to-All', 'Back-to-Grid',
               'Solar-to-All', 'Solar-to-House', 'Solar-to-HES', 'Solar-to-EV', 'Solar-to-Fleet',
               'Solar-to-Grid', 'Total-to-HES', 'HES-to-All', 'HES-to-House', 'HES-to-EV', 'HES-to-Fleet',
               'Total-to-EV', 'EV-to-House', 'Total-to-Fleet', 'Fleet-to-House', 'Total-to-House']
tariff_list = ['On-Mid-Off Peaks', 'TOU Schedule']

# ----------------------------- Window + style -----------------------------

root = Tk()
root.title('HouseholdSim - Results Viewer')
root.geometry('1150x800')
gui_common.configure_style(root)

title_bar = ttk.Frame(root, style='App.TFrame')
title_bar.pack(fill=X)
ttk.Label(title_bar, text='  HouseholdSim Results Viewer', style='AppTitle.TLabel').pack(side=LEFT, pady=10)

body = ttk.Frame(root)
body.pack(fill=BOTH, expand=True)

left_col = ttk.Frame(body)
left_col.pack(side=LEFT, fill=BOTH, expand=True, anchor='n')
right_col = ttk.Frame(body)
right_col.pack(side=LEFT, fill=BOTH, expand=True, anchor='n')


def _listbox(parent, **kw):
    # ttk has no themed Listbox, so this keeps a plain tkinter one visually consistent with the
    # surrounding Card surface instead of the raw platform-default look.
    defaults = dict(selectmode=SINGLE, exportselection=0, bg=PALETTE['surface'], fg=PALETTE['text'],
                    font=(FONT_FAMILY, 10), highlightthickness=1, highlightbackground=PALETTE['border'],
                    relief='flat')
    defaults.update(kw)
    return Listbox(parent, **defaults)


# ----------------------------- "1. Results Files" card -----------------------------

files_card = gui_common.card(left_col, '1. Results Files')

ttk.Label(files_card, text='Open a legacy .pkl/.pkl.gz file, or a consolidate_results store '
                           '(pick a scenario from the list that opens).', style='Sub.TLabel',
         wraplength=380).grid(row=0, column=0, columnspan=3, sticky=W, pady=(0, 6))

file_listbox = _listbox(files_card, width=48, height=8)
file_listbox.grid(row=1, column=0, columnspan=3, sticky=W, pady=(0, 8))

# ----------------------------- "2. Scenario Details" card -----------------------------

details_card = gui_common.card(left_col, '2. Scenario Details')

# Result File Attribute Labels
city_label = ttk.Label(details_card, text='Simulation City:', style='Card.TLabel')
city_value = ttk.Label(details_card, text='', style='Card.TLabel')

state_label = ttk.Label(details_card, text='Simulation State:', style='Card.TLabel')
state_value = ttk.Label(details_card, text='', style='Card.TLabel')

zip_label = ttk.Label(details_card, text='Zip Code:', style='Card.TLabel')
zip_value = ttk.Label(details_card, text='', style='Card.TLabel')

reference_city_label = ttk.Label(details_card, text='Reference City:', style='Card.TLabel')
reference_city_value = ttk.Label(details_card, text='', style='Card.TLabel')

reference_state_label = ttk.Label(details_card, text='Reference State:', style='Card.TLabel')
reference_state_value = ttk.Label(details_card, text='', style='Card.TLabel')

utility_label = ttk.Label(details_card, text='Utility:', style='Card.TLabel')
utility_value = ttk.Label(details_card, text='', style='Card.TLabel')

tariff_label = ttk.Label(details_card, text='Tariff:', style='Card.TLabel')
tariff_value = ttk.Label(details_card, text='', style='Card.TLabel')

load_file_label = ttk.Label(details_card, text='Load File:', style='Card.TLabel')
load_file_value = ttk.Label(details_card, text='', style='Card.TLabel')

solar_label = ttk.Label(details_card, text='Solar Size (kW):', style='Card.TLabel')
solar_value = ttk.Label(details_card, text='', style='Card.TLabel')

hes_label = ttk.Label(details_card, text='HES Size (kWh):', style='Card.TLabel')
hes_value = ttk.Label(details_card, text='', style='Card.TLabel')

fleet_label = ttk.Label(details_card, text='Fleet Size:', style='Card.TLabel')
fleet_value = ttk.Label(details_card, text='', style='Card.TLabel')

ev_label = ttk.Label(details_card, text='First EV:', style='Card.TLabel')
ev_value = ttk.Label(details_card, text='', style='Card.TLabel')

bill_label = ttk.Label(details_card, text='Total Electric Bill ($):', style='Card.TLabel')
bill_value = ttk.Label(details_card, text='', style='Card.TLabel')

solar_avoid_label = ttk.Label(details_card, text='Solar Avoided Cost ($):', style='Card.TLabel')
solar_avoid_value = ttk.Label(details_card, text='', style='Card.TLabel')

solar_co2_label = ttk.Label(details_card, text='Solar CO2 Savings (kg CO2):', style='Card.TLabel')
solar_co2_value = ttk.Label(details_card, text='', style='Card.TLabel')

hes_avoid_label = ttk.Label(details_card, text='HES Avoided Cost ($):', style='Card.TLabel')
hes_avoid_value = ttk.Label(details_card, text='', style='Card.TLabel')

hes_co2_label = ttk.Label(details_card, text='HES CO2 Savings (kg CO2):', style='Card.TLabel')
hes_co2_value = ttk.Label(details_card, text='', style='Card.TLabel')

fleet_avoid_label = ttk.Label(details_card, text='EV Fleet Avoided Cost ($):', style='Card.TLabel')
fleet_avoid_value = ttk.Label(details_card, text='', style='Card.TLabel')

fleet_co2_label = ttk.Label(details_card, text='EV Fleet CO2 Savings (kg CO2):', style='Card.TLabel')
fleet_co2_value = ttk.Label(details_card, text='', style='Card.TLabel')

_detail_rows = [
    (city_label, city_value), (state_label, state_value), (zip_label, zip_value),
    (reference_city_label, reference_city_value), (reference_state_label, reference_state_value),
    (utility_label, utility_value), (tariff_label, tariff_value), (load_file_label, load_file_value),
    (solar_label, solar_value), (hes_label, hes_value), (fleet_label, fleet_value), (ev_label, ev_value),
    (bill_label, bill_value), (solar_avoid_label, solar_avoid_value), (solar_co2_label, solar_co2_value),
    (hes_avoid_label, hes_avoid_value), (hes_co2_label, hes_co2_value),
    (fleet_avoid_label, fleet_avoid_value), (fleet_co2_label, fleet_co2_value),
]
for _row, (_lbl, _val) in enumerate(_detail_rows):
    _lbl.grid(row=_row, column=0, sticky=W, pady=2, padx=(0, 8))
    _val.grid(row=_row, column=1, sticky=W, pady=2)

# ----------------------------- "3. Plot Setup" card -----------------------------

plot_card = gui_common.card(right_col, '3. Plot Setup')

ttk.Label(plot_card, text='Select Component/Parameter:', style='Card.TLabel').grid(
    row=0, column=0, sticky=W, padx=5, pady=(0, 2))
comp_listbox = _listbox(plot_card, height=7)
comp_listbox.grid(row=1, column=0, sticky=W, padx=5, pady=(0, 8))
for comp in comp_list:
    comp_listbox.insert(END, comp)

ttk.Label(plot_card, text='Select Field to Plot:', style='Card.TLabel').grid(
    row=0, column=1, sticky=W, padx=5, pady=(0, 2))
field_listbox = _listbox(plot_card, height=7)
field_listbox.grid(row=1, column=1, sticky=W, padx=5, pady=(0, 8))

ttk.Label(plot_card, text='Select EV (if applicable):', style='Card.TLabel').grid(
    row=2, column=0, sticky=W, padx=5, pady=(0, 2))
ev_select = StringVar(root)
ev_select.set('Select EV')
ev_combo = ttk.Combobox(plot_card, textvariable=ev_select)
ev_combo.grid(row=3, column=0, sticky=W, padx=5, pady=(0, 8))

# Radio Button for Plot Selection
plot_new = IntVar(root)
plot_new.set(True)
radio_frame = ttk.Frame(plot_card, style='Card.TFrame')
radio_frame.grid(row=2, column=1, rowspan=2, sticky=W, padx=5, pady=(0, 8))
new_plt_radio = ttk.Radiobutton(radio_frame, text='New Plot', variable=plot_new, value=1)
new_plt_radio.grid(row=0, column=0, sticky=W)
current_plt_radio = ttk.Radiobutton(radio_frame, text='Current Plot', variable=plot_new, value=0)
current_plt_radio.grid(row=1, column=0, sticky=W)

# Radio Button for Axis Selection
axis_var = IntVar(root)
primary_axis_radio = ttk.Radiobutton(radio_frame, text='Primary Axis', variable=axis_var, value=0)
primary_axis_radio.grid(row=0, column=1, sticky=W, padx=(12, 0))
secondary_axis_radio = ttk.Radiobutton(radio_frame, text='Secondary Axis', variable=axis_var, value=1)
secondary_axis_radio.grid(row=1, column=1, sticky=W, padx=(12, 0))

# Labels and Entries for Figure updating
label_frame = ttk.Frame(plot_card, style='Card.TFrame')
label_frame.grid(row=4, column=0, columnspan=2, sticky=W, pady=(4, 0))

tit_lbl = ttk.Label(label_frame, text='Title', style='Card.TLabel')
tit_lbl.grid(row=0, column=0, sticky=E, padx=5, pady=3)
tit_var = StringVar(root)
tit_entry = ttk.Entry(label_frame, textvariable=tit_var)
tit_entry.grid(row=0, column=1, sticky=W, padx=5, pady=3)

x_lbl = ttk.Label(label_frame, text='X Axis Label', style='Card.TLabel')
x_lbl.grid(row=1, column=0, sticky=E, padx=5, pady=3)
x_var = StringVar(root)
x_entry = ttk.Entry(label_frame, textvariable=x_var)
x_entry.grid(row=1, column=1, sticky=W, padx=5, pady=3)

y1_lbl = ttk.Label(label_frame, text='Y1 Axis Label', style='Card.TLabel')
y1_lbl.grid(row=2, column=0, sticky=E, padx=5, pady=3)
y1_var = StringVar(root)
y1_entry = ttk.Entry(label_frame, textvariable=y1_var)
y1_entry.grid(row=2, column=1, sticky=W, padx=5, pady=3)

y2_lbl = ttk.Label(label_frame, text='Y2 Axis Label', style='Card.TLabel')
y2_lbl.grid(row=3, column=0, sticky=E, padx=5, pady=3)
y2_var = StringVar(root)
y2_entry = ttk.Entry(label_frame, textvariable=y2_var)
y2_entry.grid(row=3, column=1, sticky=W, padx=5, pady=3)


# ----------------------------- Behavior (unchanged from before the restyle) -----------------------------

def populate_ev_combo():
    #  populate ev combobox
    res = file_list[file_strings.index(file_listbox.get(file_listbox.curselection()))]
    names = [ev.full_name for ev in res.fleet.ev_list]
    ev_combo.configure(values=names)


def _pick_store_scenario(index_path):
    """
    Modal listbox of the ScenarioIDs available in a consolidate_results store (Simulation.py),
    with a filter box since a store can hold thousands of scenarios. Returns the chosen ID, or
    None if the dialog was closed without a selection.
    """
    ids = sm.list_store_scenarios(index_path)
    picked = {'id': None}

    dialog = Toplevel(root)
    dialog.title('Select Scenario')
    dialog.geometry('320x420')
    dialog.configure(bg=PALETTE['bg'])
    dialog.transient(root)
    dialog.grab_set()

    ttk.Label(dialog, text=f'{len(ids)} scenarios in this store').pack(anchor='w', padx=8, pady=(8, 0))
    filter_var = StringVar()
    ttk.Entry(dialog, textvariable=filter_var).pack(fill='x', padx=8, pady=6)

    listbox = _listbox(dialog, height=16)
    listbox.pack(fill='both', expand=True, padx=8, pady=4)

    def refresh(*_):
        listbox.delete(0, END)
        needle = filter_var.get().strip()
        for sid in ids:
            if needle in sid:
                listbox.insert(END, sid)

    filter_var.trace_add('write', refresh)
    refresh()

    def confirm():
        selection = listbox.curselection()
        if selection:
            picked['id'] = listbox.get(selection[0])
        dialog.destroy()

    ttk.Button(dialog, text='Open', command=confirm, style='Accent.TButton').pack(pady=8)
    listbox.bind('<Double-Button-1>', lambda e: confirm())
    root.wait_window(dialog)
    return picked['id']


def open_result():
    global file_list
    global file_strings

    root.filename = filedialog.askopenfile(initialdir='Outputs',
                                           title='Select Results File',
                                           filetypes=(('Results files', '*.pkl *.pkl.gz *_results_store.dat'),
                                                      ('pkl files', '*.pkl'),
                                                      ('compressed pkl files', '*.pkl.gz'),
                                                      ('consolidated results store', '*_results_store.dat'),
                                                      ('All Files', '*.*')))
    if root.filename is None:
        return
    print(root.filename.name)

    if root.filename.name.endswith('_results_store.dat'):
        # Simulation.run_collection's consolidate_results=True writes one shared store per input
        # file instead of one .pkl per scenario -- pick which scenario inside it to open.
        index_path = root.filename.name[: -len('.dat')] + '_index.csv'
        scenario_id = _pick_store_scenario(index_path)
        if scenario_id is None:
            return
        res = sm.load_result_from_store(root.filename.name, index_path, scenario_id)
    else:
        # Simulation.load_results_file detects gzip from the file's magic bytes, so compressed and
        # uncompressed results both open here without the user needing to know which is which.
        res = sm.load_results_file(root.filename.name)

    file_list.append(res)

    try:
        file_strings.append(res.operation.simu_name + '_Run_' + res.operation.simu_id)
        file_listbox.insert(END, res.operation.simu_name + '_Run_' + res.operation.simu_id)
    except TypeError:
        file_strings.append(res.operation.simu_name)
        file_listbox.insert(END, res.operation.simu_name)

    file_listbox.selection_set(0)
    populate_ev_combo()
    file_listbox.bind('<<ListboxSelect>>', populate_ev_combo())


def remove_result():
    global file_list
    global file_strings

    selected = file_listbox.get(file_listbox.curselection())
    ind = file_strings.index(selected)
    file_strings.remove(selected)
    file_list.pop(ind)
    file_listbox.delete(ANCHOR)

    print(file_list)
    print(file_strings)


def read_result():
    # This function is for button to read result key file attributes
    global file_list
    global file_strings

    selected = file_listbox.get(file_listbox.curselection())
    print(selected)
    ind = file_strings.index(selected)
    res = file_list[ind]
    populate_ev_combo()

    city_value.configure(text=res.city.name)
    state_value.configure(text=res.city.state)
    zip_value.configure(text=res.city.zipcode)
    reference_city_value.configure(text=res.city.matched_city)
    reference_state_value.configure(text=res.city.matched_state)
    utility_value.configure(text=res.tariff.utility)
    tariff_value.configure(text=res.tariff.name)
    if res.house.load_file is None:
        load_file_value.configure(text=res.house.usage)
    else:
        load_file_value.configure(text=res.house.load_file.split('/')[-1])
    solar_value.configure(text=res.pv.system_size)
    hes_value.configure(text=res.hes.batterySize)
    fleet_value.configure(text=res.fleet.ev_num)
    ev_value.configure(text=res.fleet.ev_list[0].full_name)
    bill_value.configure(text=res.bill.total_bill)
    solar_avoid_value.configure(text=res.solar_avoidance)
    solar_co2_value.configure(text=res.solar_co2_savings)
    hes_avoid_value.configure(text=res.hes_avoidance)
    hes_co2_value.configure(text=res.hes_co2_savings)
    fleet_avoid_value.configure(text=res.fleet_avoidance)
    fleet_co2_value.configure(text=res.fleet_co2_savings)


def select_comp():
    field_listbox.delete('0', 'end')
    cmp = comp_listbox.get(comp_listbox.curselection())
    populate_ev_combo()
    if cmp == 'Tariff':
        fld_list = tariff_list
    elif cmp == 'HES':
        fld_list = hes_list
    elif cmp == 'EV Fleet':
        fld_list = ev_list
    elif cmp == 'Grid':
        fld_list = grid_list
    elif cmp == 'PV':
        fld_list = pv_list
    elif cmp == 'House':
        fld_list = house_list
    else:  # we assume energy flows
        fld_list = energy_list

    for fld in fld_list:
        field_listbox.insert(END, fld)


def plot_field():
    global prim_colors
    global p_colors
    global second_colors
    global s_colors
    global plt_labels
    global plt2_labels
    #  we ascertain which file we wish to load from
    res = file_list[file_strings.index(file_listbox.get(file_listbox.curselection()))]
    #  we ascertain which component/parameter we wish to get fields from
    cmp = comp_listbox.get(comp_listbox.curselection())
    # we ascertain which field we wish to plot
    fld = field_listbox.get(field_listbox.curselection())
    # we ascertain the ev number (so we can access proper columns)
    ev_num = ev_combo.current()

    if cmp == 'EV Fleet':
        plt_lbl = ev_combo.get() + ' ' + fld
    else:
        plt_lbl = cmp + ' ' + fld

    # print(res.fleet.ev_list[ev_num].socs)
    # print(res.hes.socs)
    # print(len(res.hes.socs) == len(res.fleet.ev_list[ev_num].socs))

    # print(new_plt_radio.getvar())
    fig = plt.figure(1)

    axes = fig.get_axes()

    if plot_new.get() == 1:
        print('cleared')
        plt.clf()
        p_colors = prim_colors.copy()
        s_colors = second_colors.copy()
        plt_labels = []
        plt2_labels = []

    # First we ascertain the time limits of our plots
    timestep = res.timekeep.timestep
    start_day = res.timekeep.starting_day
    num_steps = res.timekeep.num_steps
    year = res.timekeep.year
    row = np.where(res.timekeep.calendar[:, 3] == start_day)[0][0]
    start_dom = res.timekeep.calendar[row, 1]
    start_mon = res.timekeep.calendar[row, 2]
    start_date_short = str(year) + '-' + str(start_mon) + '-' + str(start_dom)
    start_date_long = str(year) + '-1-1'
    freq = str(timestep) + 'min'

    short_time = pd.period_range(start=start_date_short, periods=num_steps, freq=freq).to_timestamp()
    long_time = pd.period_range(start=start_date_long, periods=int(365 * 24 * 60 / timestep), freq=freq).to_timestamp()
    time_vec = []
    vals = []
    if fld == 'States of Charge':
        time_vec = short_time
        if cmp == 'HES':
            vals = res.hes.socs
        if cmp == 'EV Fleet':
            vals = res.fleet.ev_list[ev_num].socs
    elif fld == 'Cost Of Use ($/kWh)':
        time_vec = short_time
        if cmp == 'HES':
            vals = res.hes.cost_of_uses
        if cmp == 'EV Fleet':
            vals = res.fleet.ev_list[ev_num].cost_of_uses
        if cmp == 'Grid':
            vals = res.grid.cost_of_uses
    elif fld == 'Emissivity (kg CO2/kWh)':
        time_vec = short_time
        if cmp == 'HES':
            vals = res.hes.emissivity_arr
        if cmp == 'EV Fleet':
            vals = res.fleet.ev_list[ev_num].emissivity_arr
        if cmp == 'Grid':
            vals = res.grid.emissions_rate
    elif fld == 'Driving Pattern':
        time_vec = long_time
        vals = res.fleet.ev_list[ev_num].driving_pattern[:, 1]
    elif fld == 'On-Mid-Off Peaks':
        time_vec = long_time
        vals = res.tariff.tou_schedule[:, 1]
    elif fld == 'TOU Schedule':
        time_vec = long_time
        vals = res.tariff.tou_schedule[:, 0]
    elif fld == 'Load (kW)':
        time_vec = long_time
        vals = res.house.load_profile
    elif fld == 'Energy Required (kWh)':
        time_vec = long_time
        vals = res.house.energy_profile
    elif fld == 'Raw GHI (W/m2)':
        time_vec = long_time
        vals = res.pv.ghi
    elif fld == 'Power (kW)':
        time_vec = long_time
        vals = res.pv.power
    elif fld == 'Grid-to-House':
        time_vec = short_time
        vals = res.energy.grid_to_house
    elif fld == 'Grid-to-HES':
        time_vec = short_time
        vals = res.energy.grid_to_hes
    elif fld == 'Grid-to-Fleet':
        time_vec = short_time
        vals = res.energy.grid_to_fleet
    elif fld == 'Grid-to-EV':
        time_vec = short_time
        vals = res.energy.grid_to_ev[:, ev_num]
    elif fld == 'Back-to-Grid':
        time_vec = short_time
        vals = res.energy.grid_in
    elif fld == 'Grid-to-All':
        time_vec = short_time
        vals = res.energy.grid_out
    elif fld == 'Solar-to-All':
        time_vec = short_time
        vals = res.energy.pv_out
    elif fld == 'Solar-to-House':
        time_vec = short_time
        vals = res.energy.pv_to_house
    elif fld == 'Solar-to-HES':
        time_vec = short_time
        vals = res.energy.pv_to_hes
        plt.plot(short_time, res.energy.pv_to_hes)
    elif fld == 'Solar-to-EV':
        time_vec = short_time
        vals = res.energy.pv_to_ev[:, ev_num]
    elif fld == 'Solar-to-Fleet':
        time_vec = short_time
        vals = res.energy.pv_to_fleet
    elif fld == 'Solar-to-Grid':
        time_vec = short_time
        vals = res.energy.pv_to_grid
    elif fld == 'Total-to-HES':
        time_vec = short_time
        vals = res.energy.hes_in
    elif fld == 'HES-to-All':
        time_vec = short_time
        vals = res.energy.hes_out
    elif fld == 'HES-to-EV':
        time_vec = short_time
        vals = res.energy.hes_to_ev[:, ev_num]
    elif fld == 'HES-to-House':
        time_vec = short_time
        vals = res.energy.hes_to_house
    elif fld == 'HES-to-Fleet':
        time_vec = short_time
        vals = res.energy.hes_to_fleet
    elif fld == 'Total-to-EV':
        time_vec = short_time
        vals = res.energy.ev_in[:, ev_num]
    elif fld == 'EV-to-House':
        time_vec = short_time
        vals = res.energy.ev_to_house[:, ev_num]
    elif fld == 'Total-to-Fleet':
        time_vec = short_time
        vals = res.energy.ev_in_total
    elif fld == 'Fleet-to-House':
        time_vec = short_time
        vals = res.energy.ev_out_total
    elif fld == 'Total-to-House':
        time_vec = short_time
        vals = res.energy.house_in

    if len(axes) == 0:
        plt.plot(time_vec, vals, color=p_colors[0], label=plt_lbl)
        p_colors.pop(0)
        plt_labels.append(plt_lbl)
        plt.legend(labels=plt_labels, loc='upper left')
    elif len(axes) == 1:
        if plot_new.get() == 1:
            plt.plot(time_vec, vals, color=p_colors[0], label=plt_lbl)
            p_colors.pop(0)
            plt_labels.append(plt_lbl)
            plt.legend(labels=plt_labels, loc='upper left')
        else:
            if axis_var.get() == 1:
                ax2 = axes[0].twinx()
                ax2.plot(time_vec, vals, color=s_colors[0], label=plt_lbl)
                s_colors.pop(0)
                plt2_labels.append(plt_lbl)
                plt.legend(labels=plt2_labels, loc='lower left')
            else:
                axes[0].plot(time_vec, vals, color=p_colors[0], label=plt_lbl)
                plt_labels.append(plt_lbl)
                plt.legend(plt_labels, loc='upper left')
    else:  # both axes are accounted for
        if axis_var.get() == 0:
            axes[0].plot(time_vec, vals, color=p_colors[0], label=plt_lbl)
            p_colors.pop(0)
            plt_labels.append(plt_lbl)
            plt.legend(plt_labels, loc='upper left')
        else:
            axes[1].plot(time_vec, vals, color=s_colors[0], label=plt_lbl)
            s_colors.pop(0)
            plt2_labels.append(plt_lbl)
            plt.legend(labels=plt2_labels, loc='lower left')

    if len(p_colors) == 0:
        p_colors = prim_colors.copy()

    if len(s_colors) == 0:
        s_colors = second_colors.copy()

    # print(short_time)
    # print(long_time)3


def update_figure():
    fig = plt.figure(1)
    plt.suptitle(tit_var.get())
    fig_axes = fig.get_axes()
    fig_axes[0].set_xlabel(x_var.get())
    fig_axes[0].set_ylabel(y1_var.get())

    fig_axes[0].legend(labels=plt_labels, loc='upper left', bbox_to_anchor=(1.05, 1), borderaxespad=.2)

    if len(fig_axes) == 2:
        fig_axes[1].set_ylabel(y2_var.get())
        fig_axes[1].legend(labels=plt2_labels, loc='lower left', bbox_to_anchor=(1.05, 0), borderaxespad=.2)

    plt.tight_layout()
    # fig.get_axes()[0].secondary_yaxis.set_ylabel(y2_var.get())

    # plt.xlabel(x_var.get())
    # plt.ylabel(y1_var.get())
    # plt.axes(2)
    # plt.ylabel(y2_var.get())


# ----------------------------- Buttons (now that their commands are defined) -----------------------------

files_btn_row = ttk.Frame(files_card, style='Card.TFrame')
files_btn_row.grid(row=2, column=0, columnspan=3, sticky=W)
open_btn = ttk.Button(files_btn_row, text='Open Result File', command=open_result, style='Accent.TButton')
open_btn.pack(side=LEFT)
remove_btn = ttk.Button(files_btn_row, text='Remove Result File', command=remove_result)
remove_btn.pack(side=LEFT, padx=(6, 0))
read_res_btn = ttk.Button(files_btn_row, text='Read Result File', command=read_result)
read_res_btn.pack(side=LEFT, padx=(6, 0))

select_comp_btn = ttk.Button(plot_card, text='Select Component/Parameter', command=select_comp)
select_comp_btn.grid(row=5, column=0, sticky=W, padx=5, pady=(8, 0))

plot_btn_row = ttk.Frame(plot_card, style='Card.TFrame')
plot_btn_row.grid(row=5, column=1, sticky=W, padx=5, pady=(8, 0))
plot_field_btn = ttk.Button(plot_btn_row, text='Plot Selection', command=plot_field, style='Accent.TButton')
plot_field_btn.pack(side=LEFT)
update_fig_btn = ttk.Button(plot_btn_row, text='Update Figure', command=update_figure)
update_fig_btn.pack(side=LEFT, padx=(6, 0))

root.mainloop()
