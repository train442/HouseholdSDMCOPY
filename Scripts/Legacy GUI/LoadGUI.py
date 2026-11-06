from tkinter import *
from tkinter import filedialog
import pandas as pd
import numpy as np
import pickle
from tkinter import ttk
import Parameters as pm
import Components as cp
import Setup as sp
import DataProcessing as dp
import Simulation as sm
import tktimepicker as tktp
from tkcalendar import DateEntry, Calendar
from datetime import date
import pandastable as pdt

# ------------Initialize Simulation Components----------------#
city = pm.City
utility = pm.Tariff
fleet = cp.Fleet([])
pv = cp.PV
house = cp.House
hes = cp.HES
results: sm.Results
ice = cp.ICE

# -----------Initialize Variables for Operation-------------#

util_list = ['']  # choices for utility
tariff_list = ['']  # choices for tariff

util_ind = 0  # index of utility selected from list

load_profile = np.array([])

ev_master_frame = pd.read_csv('D:/Bras Research/pythonProject/Model Data/EVs.csv')
ev_subframe = []
year_list = list(dict.fromkeys(ev_master_frame['Year'].tolist()))
make_list = ['']
model_list = ['']
trim_list = ['']

ev_pattern = np.array([])

ice_master_frame = pd.read_csv('D:/Bras Research/pythonProject/Model Data/processed_ice.csv')
ice_master_frame = ice_master_frame.loc[(ice_master_frame['Fuel Type'] == 'Regular') |
                                        (ice_master_frame['Fuel Type'] == 'Premium')]
ice_subframe = []
ice_year_list = list(dict.fromkeys(ice_master_frame['Year'].tolist()))
ice_make_list = ['']
ice_model_list = ['']

# ----------Create Root and Sub-frames----------#

root = Tk()
root.title('Household Simulation')
root.geometry('1600x1300')

top_row = Frame(root)
top_row.grid(row=0, column=0)

# Loader for Simulation Parameters

simu_frame = Frame(top_row, highlightbackground='black', highlightthickness=2)
simu_frame.grid(row=0, column=0, padx=5, pady=5)

# Loader for City (using zip)
zip_loader = Frame(top_row, highlightbackground='black', highlightthickness=2)
zip_loader.grid(row=1, column=0, pady=5, padx=5)

# Loader for Utility
util_loader = Frame(top_row, highlightbackground='black', highlightthickness=2)
util_loader.grid(row=0, column=1, pady=5, padx=5)

# Loader for House
house_loader = Frame(top_row, highlightbackground='black', highlightthickness=2)
house_loader.grid(row=1, column=1, pady=5, padx=5)

# Loader for HES
hes_loader = Frame(top_row, highlightbackground='black', highlightthickness=2)
hes_loader.grid(row=0, column=2, pady=5, padx=5)

# Loader for PV
pv_loader = Frame(top_row, highlightbackground='black', highlightthickness=2)
pv_loader.grid(row=1, column=2, padx=5, pady=5)

# Loader for Fleet
fleet_loader = Frame(root, highlightbackground='black', highlightthickness=2)
fleet_loader.grid(row=1, column=0, pady=5, padx=5)

driving_loader = Frame(fleet_loader, highlightbackground='black', highlightthickness=2)
driving_loader.grid(row=1, column=0, pady=5, padx=5)

ev_loader = Frame(fleet_loader, highlightbackground='black', highlightthickness=2)
ev_loader.grid(row=1, column=1, pady=5, padx=5)

commute_day_frame = Frame(driving_loader)
commute_day_frame.grid(row=2, column=0, columnspan=2)

fleet_overview = Frame(fleet_loader, highlightbackground='black', highlightthickness=2)
fleet_overview.grid(row=1, column=2, padx=5, pady=5)

ice_loader = Frame(fleet_loader, highlightbackground='black', highlightthickness=2)
ice_loader.grid(row=1, column=3, pady=5, padx=5)

bottom_frame = Frame(root, highlightbackground='black', highlightthickness=2)
bottom_frame.grid(row=2, column=0, padx=5, pady=5)

status_frame = Frame(bottom_frame, highlightbackground='black', highlightthickness=2)
status_frame.grid(row=0, column=0, padx=5, pady=5)

results_frame = Frame(bottom_frame, highlightbackground='black', highlightthickness=2)
results_frame.grid(row=0, column=1, pady=5, padx=5)

ev_ice_comp = Frame(bottom_frame, highlightbackground='black', highlightthickness=2)
ev_ice_comp.grid(row=0, column=2, padx=5, pady=5)

# ---------------Tkinter Variables--------------#

starting_day = IntVar(value=1)
computation_days = IntVar(value=365)
simu_name = StringVar()

zip_code = StringVar()
zip_warning = StringVar()
city_name = StringVar()
state_name = StringVar()
match_city_name = StringVar()
match_state_name = StringVar()
util_name = StringVar()
tariff_name = StringVar()

yearly_usage = StringVar()
save_load = BooleanVar()
load_file_path = StringVar()
load_file = StringVar()

hes_size = StringVar()
hes_size.set('10')
hes_charge_rate = StringVar()
hes_charge_rate.set('10')
hes_discharge_rate = StringVar()
hes_discharge_rate.set('7')

pv_size = StringVar()
pv_size.set('5')
ghi_custom_path = StringVar()
ghi_custom = StringVar()

ev_year = StringVar()
ev_make = StringVar()
ev_model = StringVar()
ev_trim = StringVar()
ev_mpge = DoubleVar()
ev_mpge_hwy = DoubleVar()
ev_mpge_city = DoubleVar()
ev_battery = DoubleVar()
ev_msrp = StringVar()
ev_charge_rate = DoubleVar()

selected_name = StringVar()
selected_mpge = DoubleVar(value=0)
selected_size = DoubleVar(value=0)
selected_msrp = DoubleVar(value=0)
selected_discharge_limit = IntVar(value=0)

ice_year = StringVar()
ice_make = StringVar()
ice_model = StringVar()
ice_disp = DoubleVar(value=0)
ice_cyl = IntVar(value=0)
ice_drive = StringVar()
ice_trans = StringVar()
ice_mpg = DoubleVar(value=0)
ice_emissivity = DoubleVar(value=0)

gas_cost = DoubleVar(value=3.5)

ev_driving_cost = DoubleVar(value=0)
ice_driving_cost = DoubleVar(value=0)
diff_driving_cost = DoubleVar(value=0)

commute_distance = StringVar()
commute_distance.set('20')
monday_var = BooleanVar()
monday_var.set(True)
tuesday_var = BooleanVar()
tuesday_var.set(True)
wednesday_var = BooleanVar()
wednesday_var.set(True)
thursday_var = BooleanVar()
thursday_var.set(True)
friday_var = BooleanVar()
friday_var.set(True)
saturday_var = BooleanVar()
sunday_var = BooleanVar()

pattern_file_path = StringVar()
pattern_file = StringVar()

ev_discharge_limit = StringVar()
ev_discharge_limit.set('70')

simu_year = IntVar()
simu_year.set(2018)

city_string = StringVar(value='Not Ready')
fleet_string = StringVar(value='Empty')
utility_string = StringVar(value='Not Ready')
house_string = StringVar(value='Not Ready')
pv_string = StringVar(value='Not Ready')
hes_string = StringVar(value='Not Ready')

bill_amount = DoubleVar(value=0)
co2_amount = DoubleVar(value=0)
pv_money_saved = DoubleVar(value=0)
pv_co2_saved = DoubleVar(value=0)
hes_money_saved = DoubleVar(value=0)
hes_co2_saved = DoubleVar(value=0)
fleet_money_saved = DoubleVar(value=0)
fleet_co2_saved = DoubleVar(value=0)

# -------- Label boxes--------#

# Zip Loader Frame

zip_title = Label(zip_loader, text='City Maker', font=12)
zip_title.grid(row=0, column=0, columnspan=2, padx=5, pady=5)

zip_label = Label(zip_loader, text='Enter Zip Code: ')
zip_label.grid(row=1, column=0, pady=5, padx=5)

zip_warn_label = Label(zip_loader, textvariable=zip_warning)
zip_warn_label.grid(row=2, column=1, padx=5, pady=5)

city_label = Label(zip_loader, text='City: ')
city_label.grid(row=5, column=0, pady=5, padx=5)
city_value = Label(zip_loader, textvariable=city_name)
city_value.grid(row=5, column=1, padx=5, pady=5)

state_label = Label(zip_loader, text='State: ')
state_label.grid(row=6, column=0, pady=5, padx=5)
state_value = Label(zip_loader, textvariable=state_name)
state_value.grid(row=6, column=1, pady=5, padx=5)

matched_city_label = Label(zip_loader, text='Match City: ')
matched_city_label.grid(row=7, column=0, pady=5, padx=5)
matched_city_value = Label(zip_loader, textvariable=match_city_name)
matched_city_value.grid(row=7, column=1, padx=5, pady=5)

matched_state_label = Label(zip_loader, text='Match State: ')
matched_state_label.grid(row=8, column=0, pady=5, padx=5)
matched_state_value = Label(zip_loader, textvariable=match_state_name)
matched_state_value.grid(row=8, column=1, pady=5, padx=5)

# Util Loader Frame

util_title = Label(util_loader, text='Create Utility', font=12)
util_title.grid(row=0, column=0, columnspan=2, pady=5, padx=5)

util_label = Label(util_loader, text='Select Utility: ')
util_label.grid(row=1, column=0, pady=5, padx=5)

tariff_label = Label(util_loader, text='Select Tariff: ')
tariff_label.grid(row=2, column=0, pady=5, padx=5)

# House Loader

house_title = Label(house_loader, text='House Maker', font=12)
house_title.grid(row=0, column=0, columnspan=2, padx=5, pady=5)

kwh_label = Label(house_loader, text='Yearly Usage: ')
kwh_label.grid(row=1, column=0, padx=5, pady=5)

or_label = Label(house_loader, text='---------OR---------')
or_label.grid(row=2, column=0, pady=5, padx=5)

load_file_label = Label(house_loader, text='Load File: ')
load_file_label.grid(row=3, column=0)

load_file_name = Label(house_loader, textvariable=load_file, width=30)
load_file_name.grid(row=3, column=1)

# HES Loader

hes_title = Label(hes_loader, text='HES Maker', font=12)
hes_title.grid(row=0, column=0, pady=5, padx=5, columnspan=2)

hes_size_label = Label(hes_loader, text='HES Size (kWh): ')
hes_size_label.grid(row=1, column=0, pady=5, padx=5)

hes_charge_label = Label(hes_loader, text='HES Charge Rate (kW): ')
hes_charge_label.grid(row=2, column=0, pady=5, padx=5)

hes_discharge_label = Label(hes_loader, text='HES Discharge Rate (kW): ')
hes_discharge_label.grid(row=3, column=0, pady=5, padx=5)

# PV Loader

pv_title = Label(pv_loader, text='PV Maker', font=12)
pv_title.grid(row=0, column=0, columnspan=2, pady=5, padx=5)

pv_size_label = Label(pv_loader, text='PV Size (kW): ')
pv_size_label.grid(row=1, column=0, pady=5, padx=5)

ghi_file_label = Label(pv_loader, text='Custom GHI file: ')
ghi_file_label.grid(row=2, column=0, padx=5, pady=5)

ghi_file_name = Label(pv_loader, textvariable=ghi_custom, width=30)
ghi_file_name.grid(row=2, column=1, pady=5, padx=5)

# Fleet Loader

fleet_loader_title = Label(fleet_loader, text='Fleet Maker', font=12)
fleet_loader_title.grid(row=0, column=0, columnspan=3, padx=5, pady=5)

ev_loader_title = Label(ev_loader, text='Choose EV Model', font=12)
ev_loader_title.grid(row=0, column=0, columnspan=2, padx=5, pady=5)

ev_year_label = Label(ev_loader, text='Model Year: ')
ev_year_label.grid(row=1, column=0, pady=5, padx=5)

ev_make_label = Label(ev_loader, text='Car Make: ')
ev_make_label.grid(row=2, column=0, padx=5, pady=5)

ev_model_label = Label(ev_loader, text='Car Model: ')
ev_model_label.grid(row=3, column=0, pady=5, padx=5)

ev_trim_label = Label(ev_loader, text='Car Trim: ')
ev_trim_label.grid(row=4, column=0, padx=5, pady=5)

ev_mpge_label = Label(ev_loader, text='MPGe Combined: ')
ev_mpge_label.grid(row=5, column=0, padx=5, pady=5)

ev_mpge_amount = Label(ev_loader, textvariable=ev_mpge)
ev_mpge_amount.grid(row=5, column=1, pady=5, padx=5)

ev_battery_label = Label(ev_loader, text='Battery Size (kWh)')
ev_battery_label.grid(row=6, column=0, padx=5, pady=5)

ev_battery_amount = Label(ev_loader, textvariable=ev_battery)
ev_battery_amount.grid(row=6, column=1, pady=5, padx=5)

ev_msrp_label = Label(ev_loader, text='MSRP ($): ')
ev_msrp_label.grid(row=7, column=0, pady=5, padx=5)

ev_msrp_amount = Label(ev_loader, textvariable=ev_msrp)
ev_msrp_amount.grid(row=7, column=1, padx=5, pady=5)

ev_discharge_label = Label(ev_loader, text='EV Discharge Limit (%): ')
ev_discharge_label.grid(row=8, column=0, pady=5, padx=5)

commute_title = Label(driving_loader, text='Commute Description', font=12)
commute_title.grid(row=0, column=0, columnspan=2, pady=5, padx=5)

commute_label = Label(driving_loader, text='Commute Distance (mi): ')
commute_label.grid(row=1, column=0, padx=5, pady=5)

leave_time_label = Label(driving_loader, text='Leave Time: ')
leave_time_label.grid(row=3, column=0, padx=5, pady=5)

return_time_label = Label(driving_loader, text='Return Time: ')
return_time_label.grid(row=4, column=0, padx=5, pady=5)

driving_or_label = Label(driving_loader, text='---------OR-------------')
driving_or_label.grid(row=5, column=0, pady=5, padx=5, columnspan=2)

driving_file_label = Label(driving_loader, text='Pattern File:  ')
driving_file_label.grid(row=6, column=0, pady=5, padx=5)

driving_file_name = Label(driving_loader, textvariable=pattern_file)
driving_file_name.grid(row=6, column=1, padx=5, pady=5)

fleet_overview_title = Label(fleet_overview, text='Fleet Overview', font=12)
fleet_overview_title.grid(row=0, column=0, columnspan=3, padx=5, pady=5)

selected_name_label = Label(fleet_overview, text='EV Selected: ')
selected_name_label.grid(row=3, column=0, padx=5, pady=5)

selected_name_value = Label(fleet_overview, textvariable=selected_name)
selected_name_value.grid(row=3, column=1, padx=5, pady=5, columnspan=2)

selected_mpge_label = Label(fleet_overview, text='MPGe Combined: ')
selected_mpge_label.grid(row=4, column=0, padx=5, pady=5)

selected_mpge_value = Label(fleet_overview, textvariable=selected_mpge)
selected_mpge_value.grid(row=4, column=1, padx=5, pady=5, columnspan=2)

selected_size_label = Label(fleet_overview, text='Battery Size (kWh): ')
selected_size_label.grid(row=5, column=0, pady=5, padx=5)

selected_size_value = Label(fleet_overview, textvariable=selected_size)
selected_size_value.grid(row=5, column=1, pady=5, padx=5, columnspan=2)

selected_msrp_label = Label(fleet_overview, text='MSRP ($): ')
selected_msrp_label.grid(row=6, column=0, pady=5, padx=5)

selected_msrp_value = Label(fleet_overview, textvariable=selected_msrp)
selected_msrp_value.grid(row=6, column=1, pady=5, padx=5, columnspan=2)

selected_discharge_limit_label = Label(fleet_overview, text='Discharge Limit (%): ')
selected_discharge_limit_label.grid(row=7, column=0, pady=5, padx=5)

selected_discharge_limit_value = Label(fleet_overview, textvariable=selected_discharge_limit)
selected_discharge_limit_value.grid(row=7, column=1, pady=5, padx=5, columnspan=2)

ice_title = Label(ice_loader, text='ICE Comparison', font=12)
ice_title.grid(row=0, column=0, columnspan=2, padx=5, pady=5)

ice_year_label = Label(ice_loader, text='Model Year: ')
ice_year_label.grid(row=1, column=0, pady=5, padx=5)

ice_make_label = Label(ice_loader, text='Car Make: ')
ice_make_label.grid(row=2, column=0, padx=5, pady=5)

ice_model_label = Label(ice_loader, text='Car Model: ')
ice_model_label.grid(row=3, column=0, pady=5, padx=5)

gas_price_label = Label(ice_loader, text='Gas Price ($/gal): ')
gas_price_label.grid(row=4, column=0, pady=5, padx=5)

ice_disp_label = Label(ice_loader, text='Engine Displacement (L): ')
ice_disp_label.grid(row=5, column=0, pady=5, padx=5)

ice_disp_value = Label(ice_loader, textvariable=ice_disp)
ice_disp_value.grid(row=5, column=1, pady=5, padx=5)

ice_cyl_label = Label(ice_loader, text='Engine Cylinders: ')
ice_cyl_label.grid(row=6, column=0, pady=5, padx=5)

ice_cyl_value = Label(ice_loader, textvariable=ice_cyl)
ice_cyl_value.grid(row=6, column=1, pady=5, padx=5)

ice_drive_label = Label(ice_loader, text='Drive Type: ')
ice_drive_label.grid(row=7, column=0, pady=5, padx=5)

ice_drive_value = Label(ice_loader, textvariable=ice_drive)
ice_drive_value.grid(row=7, column=1, pady=5, padx=5)

ice_trans_label = Label(ice_loader, text='Transmission Type: ')
ice_trans_label.grid(row=8, column=0, pady=5, padx=5)

ice_trans_value = Label(ice_loader, textvariable=ice_trans)
ice_trans_value.grid(row=8, column=1, pady=5, padx=5)

ice_mpg_label = Label(ice_loader, text='Combined MPG: ')
ice_mpg_label.grid(row=9, column=0, pady=5, padx=5)

ice_mpg_value = Label(ice_loader, textvariable=ice_mpg)
ice_mpg_value.grid(row=9, column=1, pady=5, padx=5)

ice_emissivity_label = Label(ice_loader, text='Emissivity (gCO2/mi)')
ice_emissivity_label.grid(row=10, column=0, pady=5, padx=5)

ice_emissivity_value = Label(ice_loader, textvariable=ice_emissivity)
ice_emissivity_value.grid(row=10, column=1, pady=5, padx=5)

# Simulation Parameter

simu_label = Label(simu_frame, text='Simulation Parameters', font=12)
simu_label.grid(row=0, column=0, columnspan=2, pady=5, padx=5)

start_date_label = Label(simu_frame, text='Enter Start Date: ')
start_date_label.grid(row=1, column=0, pady=5, padx=5)

end_date_label = Label(simu_frame, text='Enter End Date:  ')
end_date_label.grid(row=2, column=0, pady=5, padx=5)

simu_name_label = Label(simu_frame, text='Enter Simulation Name: ')
simu_name_label.grid(row=3, column=0, pady=5, padx=5)

# Simulation Checklist

status_label = Label(status_frame, text='Component Status', font=12)
status_label.grid(row=0, column=0, columnspan=2, pady=5, padx=5)

city_check_label = Label(status_frame, text='City Status: ')
city_check_label.grid(row=1, column=0, pady=5, padx=5)

city_check_status = Label(status_frame, textvariable=city_string)
city_check_status.grid(row=1, column=1, pady=5, padx=5)

utility_check_label = Label(status_frame, text='Utility Status: ')
utility_check_label.grid(row=2, column=0, pady=5, padx=5)

utility_check_status = Label(status_frame, textvariable=utility_string)
utility_check_status.grid(row=2, column=1, pady=5, padx=5)

house_check_label = Label(status_frame, text='House Status: ')
house_check_label.grid(row=3, column=0, pady=5, padx=5)

house_check_status = Label(status_frame, textvariable=house_string)
house_check_status.grid(row=3, column=1, pady=5, padx=5)

hes_check_label = Label(status_frame, text='HES Status: ')
hes_check_label.grid(row=4, column=0, pady=5, padx=5)

hes_check_status = Label(status_frame, textvariable=hes_string)
hes_check_status.grid(row=4, column=1, pady=5, padx=5)

pv_check_label = Label(status_frame, text='PV Status: ')
pv_check_label.grid(row=5, column=0, pady=5, padx=5)

pv_check_status = Label(status_frame, textvariable=pv_string)
pv_check_status.grid(row=5, column=1, pady=5, padx=5)

fleet_check_label = Label(status_frame, text='Fleet Status: ')
fleet_check_label.grid(row=6, column=0, pady=5, padx=5)

fleet_check_status = Label(status_frame, textvariable=fleet_string)
fleet_check_status.grid(row=6, column=1, pady=5, padx=5)

# Results

results_title = Label(results_frame, text='Simulation Results', font=12)
results_title.grid(row=0, column=0, columnspan=2, padx=5, pady=5)

bill_label = Label(results_frame, text='Bill Amount ($): ')
bill_label.grid(row=1, column=0, pady=5, padx=5)

bill_show = Label(results_frame, textvariable=bill_amount)
bill_show.grid(row=1, column=1, pady=5, padx=5)

co2_label = Label(results_frame, text='CO2 Amount (kg): ')
co2_label.grid(row=2, column=0, pady=5, padx=5)

co2_show = Label(results_frame, textvariable=co2_amount)
co2_show.grid(row=2, column=1, pady=5, padx=5)

pv_amount_label = Label(results_frame, text='PV Avoided Cost ($): ')
pv_amount_label.grid(row=3, column=0, pady=5, padx=5)

pv_amount_show = Label(results_frame, textvariable=pv_money_saved)
pv_amount_show.grid(row=3, column=1, pady=5, padx=5)

pv_co2_label = Label(results_frame, text='PV Avoided CO2 (kg): ')
pv_co2_label.grid(row=4, column=0, pady=5, padx=5)

pv_co2_show = Label(results_frame, textvariable=pv_co2_saved)
pv_co2_show.grid(row=4, column=1, pady=5, padx=5)

hes_amount_label = Label(results_frame, text='HES Avoided Cost ($): ')
hes_amount_label.grid(row=5, column=0, pady=5, padx=5)

hes_amount_show = Label(results_frame, textvariable=hes_money_saved)
hes_amount_show.grid(row=5, column=1, pady=5, padx=5)

hes_co2_label = Label(results_frame, text='HES Avoided CO2 (kg): ')
hes_co2_label.grid(row=6, column=0, pady=5, padx=5)

hes_co2_show = Label(results_frame, textvariable=hes_co2_saved)
hes_co2_show.grid(row=6, column=1, pady=5, padx=5)

fleet_amount_label = Label(results_frame, text='Fleet Avoided Cost ($): ')
fleet_amount_label.grid(row=7, column=0, pady=5, padx=5)

fleet_amount_show = Label(results_frame, textvariable=fleet_money_saved)
fleet_amount_show.grid(row=7, column=1, pady=5, padx=5)

fleet_co2_label = Label(results_frame, text='Fleet Avoided CO2 (kg): ')
fleet_co2_label.grid(row=8, column=0, pady=5, padx=5)

fleet_co2_show = Label(results_frame, textvariable=fleet_co2_saved)
fleet_co2_show.grid(row=8, column=1, pady=5, padx=5)

# EV ICE comparison

comp_title = Label(ev_ice_comp, text='EV vs ICE Cost', font=12)
comp_title.grid(row=0, column=0, columnspan=2, padx=5, pady=5)

ev_driving_cost_label = Label(ev_ice_comp, text='EV Cost of Driving ($): ')
ev_driving_cost_label.grid(row=1, column=0, pady=5, padx=5)

ev_driving_cost_value = Label(ev_ice_comp, textvariable=ev_driving_cost)
ev_driving_cost_value.grid(row=1, column=1, pady=5, padx=5)

ice_driving_cost_label = Label(ev_ice_comp, text='ICE Cost of Driving ($): ')
ice_driving_cost_label.grid(row=2, column=0, padx=5, pady=5)

ice_driving_cost_value = Label(ev_ice_comp, textvariable=ice_driving_cost)
ice_driving_cost_value.grid(row=2, column=1, padx=5, pady=5)

comp_driving_cost_label = Label(ev_ice_comp, text='Cost of Driving Savings ($): ')
comp_driving_cost_label.grid(row=3, column=0, pady=5, padx=5)

comp_driving_cost_value = Label(ev_ice_comp, textvariable=diff_driving_cost)
comp_driving_cost_value.grid(row=3, column=1, pady=5, padx=5)

# --------------Entry Boxes------------------#

simu_name_entry = Entry(simu_frame, textvariable=simu_name)
simu_name_entry.grid(row=3, column=1, padx=5, pady=5)

zip_entry = Entry(zip_loader, textvariable=zip_code)
zip_entry.grid(row=1, column=1, padx=5, pady=5)

kwh_entry = Entry(house_loader, textvariable=yearly_usage)
kwh_entry.grid(row=1, column=1)

hes_size_entry = Entry(hes_loader, textvariable=hes_size)
hes_size_entry.grid(row=1, column=1, padx=5, pady=5)

hes_charge_entry = Entry(hes_loader, textvariable=hes_charge_rate)
hes_charge_entry.grid(row=2, column=1, padx=5, pady=5)

hes_discharge_entry = Entry(hes_loader, textvariable=hes_discharge_rate)
hes_discharge_entry.grid(row=3, column=1, padx=5, pady=5)

pv_size_entry = Entry(pv_loader, textvariable=pv_size)
pv_size_entry.grid(row=1, column=1, pady=5, padx=5)

ev_discharge_entry = Entry(ev_loader, textvariable=ev_discharge_limit)
ev_discharge_entry.grid(row=8, column=1, padx=5, pady=5)

commute_entry = Entry(driving_loader, textvariable=commute_distance)
commute_entry.grid(row=1, column=1, pady=5, padx=5)

gas_cost_entry = Entry(ice_loader, textvariable=gas_cost)
gas_cost_entry.grid(row=4, column=1, pady=5, padx=5)

# --------------Check Boxes------------------#
save_load_box = Checkbutton(house_loader, text='Save Load', variable=save_load, onvalue=TRUE, offvalue=FALSE)
save_load_box.grid(row=2, column=1, padx=5, pady=5)

monday_box = Checkbutton(commute_day_frame, text='Mon', variable=monday_var, onvalue=TRUE, offvalue=FALSE)
monday_box.grid(row=0, column=0, padx=5, pady=5)

tuesday_box = Checkbutton(commute_day_frame, text='Tue', variable=tuesday_var, onvalue=TRUE, offvalue=FALSE)
tuesday_box.grid(row=0, column=1, padx=5, pady=5)

wednesday_box = Checkbutton(commute_day_frame, text='Wed', variable=wednesday_var, onvalue=TRUE, offvalue=FALSE)
wednesday_box.grid(row=0, column=2, padx=5, pady=5)

thursday_box = Checkbutton(commute_day_frame, text='Thu', variable=thursday_var, onvalue=TRUE, offvalue=FALSE)
thursday_box.grid(row=0, column=3, padx=5, pady=5)

friday_box = Checkbutton(commute_day_frame, text='Fri', variable=friday_var, onvalue=TRUE, offvalue=FALSE)
friday_box.grid(row=0, column=4, padx=5, pady=5)

saturday_box = Checkbutton(commute_day_frame, text='Sat', variable=saturday_var, onvalue=TRUE, offvalue=FALSE)
saturday_box.grid(row=0, column=5, padx=5, pady=5)

sunday_box = Checkbutton(commute_day_frame, text='Sun', variable=sunday_var, onvalue=TRUE, offvalue=FALSE)
sunday_box.grid(row=0, column=6, padx=5, pady=5)

# ----------------Time Picking---------------#

leave_time_pick = tktp.SpinTimePickerOld(driving_loader)
leave_time_pick.addAll(tktp.constants.HOURS12)
leave_time_pick.configure_12HrsTime(width=10)
leave_time_pick.configure_minute(width=10, values=[i for i in range(0, 60, 5)])
leave_time_pick.configure_period_width(new_width=10)
leave_time_pick.grid(row=3, column=1, pady=5, padx=5)

return_time_pick = tktp.SpinTimePickerOld(driving_loader)
return_time_pick.addAll(tktp.constants.HOURS12)
return_time_pick.configure_12HrsTime(width=10)
return_time_pick.configure_minute(width=10, values=[i for i in range(0, 60, 5)])
return_time_pick.configure_period_width(new_width=10)
return_time_pick.grid(row=4, column=1, pady=5, padx=5)

return_time_pick.addMinutes()


# ------------ Functions--------------------#

def load_zip_code():
    global city
    global util_list

    try:
        city = sp.create_city(zipcode=zip_code.get())
        city_name.set(city.name)
        state_name.set(city.state)
        match_city_name.set(city.matched_city)
        match_state_name.set(city.matched_state)

        util_list = city.utilities
        util_drop.configure(values=util_list)
        zip_warning.set('')
        city_string.set('Ready')
    except Exception:
        zip_warning.set('Zip not available')
        city_string.set('Not Ready')
        city_name.set('')
        state_name.set('')
        match_city_name.set('')
        match_state_name.set('')
        city = None


def populate_tariffs(*args):
    global tariff_list
    global util_ind

    eia = city.eias[util_drop.current()]
    tariff_drop.configure(values=sp.read_util(util_name.get(), eia))
    tariff_name.set('')


def load_utility():
    global utility
    utility = sp.create_tariff(util_name=util_name.get(), tariff_name=tariff_name.get())
    utility_string.set('Ready')


def get_load_file():
    global load_profile

    root.filename = filedialog.askopenfile(initialdir='D:/Bras Research/pythonProject/City Data/Load Profiles')
    load_file_path.set(root.filename.name)
    load_file.set(load_file_path.get().split('/')[-1])
    load_profile = pd.read_csv(load_file.get(), usecols=['Load(kW)']).to_numpy()
    print(load_profile)


def clear_load_file():
    global load_profile
    load_profile = np.array([])
    load_file.set('')


def create_house():
    global house

    if len(load_file.get()) != 0:  # we check if a load file has been loaded
        house = cp.House(load_profile=load_profile)
    elif len(yearly_usage.get()) != 0:
        try:
            house = cp.House(load_profile=dp.load_match_yearly(state=city.matched_state, city=city.matched_city,
                                                               usage=int(yearly_usage.get()),
                                                               save_profile=save_load.get()))
            house_string.set('Ready')
        except ValueError:
            print('invalid usage value')
            house = None
            house_string.set('Not Ready')
        except AttributeError:
            print('Please load Zip Code/ City')
            house = None
            house_string.set('Not Ready')


def create_hes():
    global hes

    try:
        hes = cp.HES(battery_size=int(hes_size.get()), lvl2_max_rate=int(hes_charge_rate.get()),
                     max_discharge=int(hes_discharge_rate.get()), use_curve=True)
        hes_string.set('Ready')
    except ValueError:
        print('invalid values')
        hes = None
        hes_string.set('Not Ready')


def get_custom_ghi():
    root.filename = filedialog.askopenfile(initialdir='D:/Bras Research/pythonProject/City Data/Solar Data/Custom')
    ghi_custom_path.set(root.filename.name)
    ghi_custom.set(load_file_path.get().split('/')[-1])
    print(ghi_custom.get())


def clear_ghi_file():
    global pv

    ghi_custom_path.set('')
    ghi_custom.set('')
    pv = None


def create_pv():
    global pv

    try:
        pv = cp.PV(system_size=round(float(pv_size.get()), 1))
        if len(ghi_custom.get()) != 0:  # custom ghi file has been provided
            pv.load_solar(solar_file=ghi_custom_path.get())
        else:
            ghi_file = city.matched_state + '_' + city.matched_city + '_GHI_2018_5min.csv'
            ghi_dir = 'City Data/Solar Data/' + city.matched_state + '/'
            pv.load_solar(solar_file=ghi_dir + ghi_file)
        pv_string.set('Ready')
    except ValueError:
        print('invalid pv size')
        pv = None
        pv_string.set('Not Ready')


def reset_ev_stats():
    ev_msrp.set('0.0')
    ev_mpge.set(0.0)
    ev_battery.set(0.0)


def populate_makes(*args):
    global ev_master_frame
    global make_list
    global model_list
    global trim_list

    subframe = ev_master_frame[ev_master_frame['Year'] == int(ev_year.get())]
    make_list = list(dict.fromkeys(subframe['Make'].tolist()))

    ev_make_drop.configure(values=make_list)
    ev_make.set('')

    model_list = ['']
    ev_model_drop.configure(values=model_list)
    ev_model.set('')

    trim_list = ['']
    ev_trim_drop.configure(values=trim_list)
    ev_trim.set('')

    reset_ev_stats()


def populate_models(*args):
    global ev_master_frame
    global ev_subframe
    global make_list
    global model_list
    global trim_list

    ev_subframe = ev_master_frame[(ev_master_frame['Year'] == int(ev_year.get())) &
                                  (ev_master_frame['Make'] == ev_make.get())]
    model_list = list(dict.fromkeys(ev_subframe['Model'].tolist()))

    ev_model_drop.configure(values=model_list)
    ev_model.set('')

    trim_list = ['']
    ev_trim_drop.configure(values=trim_list)
    ev_trim.set('')

    reset_ev_stats()


def populate_trims(*args):
    global ev_master_frame
    global ev_subframe
    global make_list
    global model_list
    global trim_list

    ev_subframe = ev_master_frame[(ev_master_frame['Year'] == int(ev_year.get())) &
                                  (ev_master_frame['Make'] == ev_make.get()) &
                                  (ev_master_frame['Model'] == ev_model.get())]
    trim_list = list(dict.fromkeys(ev_subframe['Trim'].tolist()))
    ev_trim_drop.configure(values=trim_list)
    ev_trim.set('')

    reset_ev_stats()


def choose_trim(*args):
    global ev_master_frame
    global ev_subframe
    global make_list
    global model_list
    global trim_list

    ev_subframe = ev_master_frame[(ev_master_frame['Year'] == int(ev_year.get())) &
                                  (ev_master_frame['Make'] == ev_make.get()) &
                                  (ev_master_frame['Model'] == ev_model.get()) &
                                  (ev_master_frame['Trim'] == ev_trim.get())]

    ev_msrp.set(ev_subframe['MSRP'].values[0])
    ev_mpge.set(ev_subframe['MPGe Comb'].values[0])
    ev_battery.set(ev_subframe['Battery Size (kWh)'].values[0])
    ev_mpge_hwy.set(ev_subframe['MPGe Hwy'].values[0])
    ev_mpge_city.set(ev_subframe['MPGe City'].values[0])
    ev_charge_rate.set(ev_subframe['Lvl2 Charge Rate (kW)'].values[0])


def get_pattern_file():
    global ev_pattern

    root.filename = filedialog.askopenfile(initialdir='D:/Bras Research/pythonProject/DrivingPatterns')
    pattern_file_path.set(root.filename.name)
    print(pattern_file_path.get())
    pattern_file.set(pattern_file_path.get().split('/')[-1])
    print(pattern_file.get())


def clear_pattern_file():
    global ev_pattern
    ev_pattern = np.array([])
    pattern_file_path.set('')
    pattern_file.set('')


def get_days():
    # analyzes the day boolean and returns a dictionary for use in the DrivingEvent class constructor
    return {'Monday': monday_var.get(),
            'Tuesday': tuesday_var.get(),
            'Wednesday': wednesday_var.get(),
            'Thursday': thursday_var.get(),
            'Friday': friday_var.get(),
            'Saturday': saturday_var.get(),
            'Sunday': sunday_var.get(),
            'Holiday': False}


def get_datetime(timepicker: tktp.SpinTimePickerOld):
    hr = timepicker.hours()
    minute = timepicker.minutes()
    minute = minute - (minute % 5)
    per = timepicker.period()
    time_str = str(hr) + ':' + str(minute).zfill(2) + ' ' + per
    return pd.to_datetime(time_str)


def add_ev():
    global ev_pattern

    # First we check if load profile has been loaded, since it has supremacy. If not we load commute
    if len(pattern_file_path.get()) != 0:  # File has been loaded
        ev_pattern = sp.create_driving_pattern(from_file=True, filename=pattern_file.get(),
                                               year=start_day.get_date().year)
    else:  # we make a DrivingEvent and Driving Schedule Object, from which we get the driving pattern
        days = get_days()
        start_time = get_datetime(leave_time_pick)
        end_time = get_datetime(return_time_pick)
        de = pm.DrivingEvent(name='Work', start_time=start_time, end_time=end_time,
                             miles_driven=int(commute_distance.get()), days=days)
        ds = pm.DrivingSchedule(minute_resolution=5)
        ds.add_event(de)
        ev_pattern = ds.create_pattern(year=start_day.get_date().year)

    ev = cp.EV(battery_size=int(ev_battery.get()),
               lvl2_max_rate=ev_charge_rate.get(),
               use_curve=True,
               ev_id=len(fleet.ev_list) + 1,
               year=int(ev_year.get()),
               make=ev_make.get(),
               model=ev_model.get(),
               trim=ev_trim.get(),
               msrp=ev_msrp.get(),
               mpge_hwy=ev_mpge_hwy.get(),
               mpge_city=ev_mpge_city.get(),
               mpge_comb=ev_mpge.get(),
               driving_pattern=ev_pattern,
               discharge_limit=int(ev_discharge_limit.get()) / 100)

    fleet.add_ev(ev)
    ev_listbox.insert(END, ev.full_name)
    fleet_string.set(str(len(fleet.ev_list)) + ' EVs')
    ev_listbox.selection_set(first=1)


def populate_selected(*args):
    global fleet

    ind = ev_listbox.curselection()[0]
    selected_name.set(fleet.ev_list[ind].full_name)
    selected_mpge.set(fleet.ev_list[ind].mpge_comb)
    selected_size.set(fleet.ev_list[ind].batterySize)
    selected_msrp.set(fleet.ev_list[ind].msrp)
    selected_discharge_limit.set(int(fleet.ev_list[ind].discharge_limit * 100))


def clear_selected(*args):
    selected_name.set('')
    selected_mpge.set(0)
    selected_size.set(0)
    selected_msrp.set(0)
    selected_discharge_limit.set(0)


def remove_ev():
    ind = ev_listbox.curselection()[0]
    fleet.remove_ev(ind)
    ev_listbox.delete(ind)
    if len(fleet.ev_list) == 0:
        fleet_string.set('Empty')
        clear_selected()
    else:
        fleet_string.set(str(len(fleet.ev_list)) + ' EVs')


def clear_fleet():
    ev_listbox.delete(0, END)
    fleet.clear_fleet()
    clear_selected()


def select_start_day(*args):
    #  fires when starting date is selected. We redefine the bounds for end_date DateEntry and the start_day variable
    starting_day.set(start_day.get_date().timetuple().tm_yday)

    end_day.configure(mindate=start_day.get_date(),
                      maxdate=date(start_day.get_date().year, 12, 31))

    if start_day.get_date() > end_day.get_date():
        end_day.set_date(date(start_day.get_date().year, 12, 31))

    computation_days.set((end_day.get_date() - start_day.get_date()).days + 1)


def select_end_day(*args):
    computation_days.set((end_day.get_date() - start_day.get_date()).days + 1)


def ready_to_simulate():
    return (city is not None) & (utility is not None) & (house is not None) & (pv is not None) & (hes is not None)


def save_simulation():
    global results

    if results is not None:
        with open('Outputs/GuiRuns/' + simu_name.get() + '.pkl', 'wb') as f:
            pickle.dump(results, f)


def clear_ice_stats():
    ice_disp.set(0)
    ice_cyl.set(0)
    ice_drive.set('')
    ice_trans.set('')
    ice_mpg.set(0)
    ice_emissivity.set(0)


def populate_ice_makes(*args):
    global ice_master_frame
    global ice_make_list
    global ice_model_list

    subframe = ice_master_frame[ice_master_frame['Year'] == int(ice_year.get())]
    ice_make_list = list(dict.fromkeys(subframe['Make'].tolist()))

    ice_make_drop.configure(values=ice_make_list)
    ice_make.set('')

    ice_model_list = ['']
    ice_model_drop.configure(values=ice_model_list)
    ice_model.set('')

    clear_ice_stats()


def populate_ice_models(*args):
    global ice_master_frame
    global ice_subframe
    global ice_make_list
    global ice_model_list

    ice_subframe = ice_master_frame[(ice_master_frame['Year'] == int(ice_year.get())) &
                                    (ice_master_frame['Make'] == ice_make.get())]
    ice_model_list = list(dict.fromkeys(ice_subframe['Model'].tolist()))

    ice_model_drop.configure(values=ice_model_list)
    ice_model.set('')

    clear_ice_stats()


def choose_ice_model(*args):
    global ice_master_frame
    global ice_subframe
    global ice_make_list
    global ice_model_list
    global ice

    ice_subframe = ice_master_frame[(ice_master_frame['Year'] == int(ice_year.get())) &
                                    (ice_master_frame['Make'] == ice_make.get()) &
                                    (ice_master_frame['Model'] == ice_model.get())]

    ice_disp.set(ice_subframe['Engine Displacement (L)'].values[0])
    ice_cyl.set(ice_subframe['Cylinders'].values[0])
    ice_drive.set(ice_subframe['Drive Type'].values[0])
    ice_trans.set(ice_subframe['Transmission Type'].values[0])
    ice_mpg.set(ice_subframe['Combined MPG'].values[0])
    ice_emissivity.set(ice_subframe['Emissivity (gCO2/mi)'].values[0])

    if ice_emissivity.get() == -1:
        ice_emissivity.set(round(8100 / ice_mpg.get()))

    ice = cp.ICE(make=ice_make.get(), model=ice_model.get(), year=ice_year.get(), mpg=ice_mpg.get(),
                 drive=ice_drive.get(), displacement=ice_disp.get(), transmission=ice_trans.get(),
                 emissivity=ice_emissivity.get())


def calc_ev_savings(*args):
    global ice

    ind = ev_listbox.curselection()[0]

    ev_driving_cost.set(np.round(fleet.ev_list[ind].cost_of_driving, 2)[0])
    ice_driving_cost.set(round(
        ice.get_cost_of_driving(miles_driven=fleet.ev_list[ind].miles_driven, gas_cost=gas_cost.get()), 2))
    diff_driving_cost.set(round(ice_driving_cost.get() - ev_driving_cost.get(), 2))


def clear_ev_savings(*args):
    ev_driving_cost.set(0)
    ice_driving_cost.set(0)
    diff_driving_cost.set(0)


def clear_results(*args):
    bill_amount.set(0)
    co2_amount.set(0)
    pv_money_saved.set(0)
    pv_co2_saved.set(0)
    hes_money_saved.set(0)
    hes_co2_saved.set(0)
    fleet_money_saved.set(0)
    fleet_co2_saved.set(0)


def run_simulation():
    # we now run the simulation. But before we do that we create some other objects necessary. But don't worry,
    # these can be created from what's already been provided by the user
    global results
    global utility
    global pv

    if ready_to_simulate():
        clear_ev_savings()
        clear_results()
        operation = pm.Operation(simu_name=str(simu_name.get()), hes_optimization='full charge', simu_id=0)
        timekeep = pm.TimeKeep(year=start_day.get_date().year, starting_day=starting_day.get(),
                               simu_days=computation_days.get())
        grid = cp.Grid(emission_file='City Data/CO2 Profiles/Cambium 2021/Processed/'
                                     + city.state + '_Cambium_2022.csv')
        utility.create_tou_schedule(timekeep.calendar)

        print('....running........')
        results = sm.run_simulation(operation=operation, city=city, tariff=utility, fleet=fleet, pv=pv, hes=hes,
                                    grid=grid, house=house, timekeep=timekeep)
        print('finished')
        bill_amount.set(round(results.bill.total_bill, 2))
        co2_amount.set(round(results.bill.co2_emissions, 2))
        pv_money_saved.set(round(results.solar_avoidance, 2))
        pv_co2_saved.set(round(results.solar_co2_savings, 2))
        hes_money_saved.set(round(results.hes_avoidance, 2))
        hes_co2_saved.set(round(results.hes_co2_savings, 2))
        fleet_money_saved.set(round(results.fleet_avoidance, 2))
        fleet_co2_saved.set(round(results.fleet_co2_savings, 2))


def show_bill():
    global results
    bill_frame = Toplevel()
    bill_frame.title('Bill Summary')
    bill_table = pdt.Table(bill_frame, dataframe=results.bill.summary, showtoolbar=True, showstatusbar=True)
    bill_table.show()

    bill_frame.mainloop()


# ---------------List Box---------------------#

ev_listbox = Listbox(fleet_overview, selectmode=SINGLE, exportselection=0, width=80)
ev_listbox.grid(row=1, column=0, pady=5, padx=5, columnspan=3)
ev_listbox.bind(sequence='<<ListboxSelect>>', func=populate_selected)

# -------------------Calendars-----------------#

start_day = DateEntry(simu_frame, year=2018, month=1, day=1, mindate=date(2018, 1, 1), maxdate=date(2022, 12, 31))
start_day.grid(row=1, column=1, pady=5, padx=5)

end_day = DateEntry(simu_frame, year=2018, month=12, day=31, mindate=start_day.get_date(),
                    maxdate=date(start_day.get_date().year, 12, 31))
end_day.grid(row=2, column=1, pady=5, padx=5)

# --------------Dropdown menus--------------- #

util_drop = ttk.Combobox(util_loader, textvariable=util_name, values=util_list, width=30)
util_drop.bind('<<ComboboxSelected>>', populate_tariffs)
util_drop.grid(row=1, column=1, padx=5, pady=5)

tariff_drop = ttk.Combobox(util_loader, textvariable=tariff_name, values=tariff_list, width=30)
tariff_drop.grid(row=2, column=1, padx=5, pady=5)

ev_year_drop = ttk.Combobox(ev_loader, textvariable=ev_year, values=year_list)
ev_year_drop.bind(sequence='<<ComboboxSelected>>', func=populate_makes)
ev_year_drop.grid(row=1, column=1, pady=5, padx=5)

ev_make_drop = ttk.Combobox(ev_loader, textvariable=ev_make, values=make_list)
ev_make_drop.bind('<<ComboboxSelected>>', populate_models)
ev_make_drop.grid(row=2, column=1, padx=5, pady=5)

ev_model_drop = ttk.Combobox(ev_loader, textvariable=ev_model, values=model_list)
ev_model_drop.bind('<<ComboboxSelected>>', populate_trims)
ev_model_drop.grid(row=3, column=1, pady=5, padx=5)

ev_trim_drop = ttk.Combobox(ev_loader, textvariable=ev_trim, values=trim_list)
ev_trim_drop.bind('<<ComboboxSelected>>', choose_trim)
ev_trim_drop.grid(row=4, column=1, padx=5, pady=5)

ice_year_drop = ttk.Combobox(ice_loader, textvariable=ice_year, values=ice_year_list)
ice_year_drop.bind(sequence='<<ComboboxSelected>>', func=populate_ice_makes)
ice_year_drop.grid(row=1, column=1, pady=5, padx=5)

ice_make_drop = ttk.Combobox(ice_loader, textvariable=ice_make, values=ice_make_list)
ice_make_drop.bind(sequence='<<ComboboxSelected>>', func=populate_ice_models)
ice_make_drop.grid(row=2, column=1, pady=5, padx=5)

ice_model_drop = ttk.Combobox(ice_loader, textvariable=ice_model, values=ice_model_list)
ice_model_drop.bind(sequence='<<ComboboxSelected>>', func=choose_ice_model)
ice_model_drop.grid(row=3, column=1, pady=5, padx=5)

# ----------------Buttons------------------#

zip_button = Button(zip_loader, text='Load Zip', command=load_zip_code)
zip_button.grid(row=2, column=0, padx=5, pady=5)

util_button = Button(util_loader, text='     Create Utility     ', command=load_utility)
util_button.grid(row=4, column=0, pady=5, padx=5, columnspan=2)

get_file_button = Button(house_loader, text='Load a File', command=get_load_file)
get_file_button.grid(row=4, column=0, pady=5, padx=5)

clear_load_button = Button(house_loader, text='Clear File', command=clear_load_file)
clear_load_button.grid(row=4, column=1, padx=5, pady=5)

create_house_button = Button(house_loader, text='       Create House       ', command=create_house)
create_house_button.grid(row=5, column=0, pady=5, padx=5, columnspan=2)

create_HES_button = Button(hes_loader, text='       Create HES       ', command=create_hes)
create_HES_button.grid(row=4, column=0, pady=5, padx=5, columnspan=2)

get_ghi_button = Button(pv_loader, text='Load Custom GHI', command=get_custom_ghi)
get_ghi_button.grid(row=3, column=0, padx=5, pady=5)

clear_ghi_button = Button(pv_loader, text='Clear GHI File', command=clear_ghi_file)
clear_ghi_button.grid(row=3, column=1, padx=5, pady=5)

create_pv_button = Button(pv_loader, text='       Create PV       ', command=create_pv)
create_pv_button.grid(row=4, column=0, padx=5, pady=5, columnspan=2)

load_pattern_button = Button(driving_loader, text='Load Pattern', command=get_pattern_file)
load_pattern_button.grid(row=7, column=0, pady=5, padx=5)

clear_pattern_button = Button(driving_loader, text='Clear Pattern', command=clear_pattern_file)
clear_pattern_button.grid(row=7, column=1, padx=5, pady=5)

add_ev_button = Button(ev_loader, text='       Add EV         ', command=add_ev)
add_ev_button.grid(row=9, column=0, padx=5, pady=5, columnspan=2)

remove_ev_button = Button(fleet_overview, text='Remove EV', command=remove_ev)
remove_ev_button.grid(row=2, column=0, pady=5, padx=5)

clear_fleet_button = Button(fleet_overview, text='Clear Fleet', command=clear_fleet)
clear_fleet_button.grid(row=2, column=1, padx=5, pady=5)

run_sim_button = Button(status_frame, text='Run Simulation', command=run_simulation)
run_sim_button.grid(row=7, column=0, columnspan=2, padx=5, pady=5)

save_sim_button = Button(results_frame, text='Save Simulation', command=save_simulation)
save_sim_button.grid(row=9, column=0, columnspan=2, padx=5, pady=5)

calc_ev_savings_btn = Button(ev_ice_comp, text='Calc Savings', command=calc_ev_savings)
calc_ev_savings_btn.grid(row=4, column=0, padx=5, pady=5)

show_bill_btn = Button(results_frame, text='View Bill', command=show_bill)
show_bill_btn.grid(row=10, column=0, columnspan=2, pady=5, padx=5)

# -----------------Event Bindings-------------#

start_day.bind('<<DateEntrySelected>>', select_start_day)
end_day.bind('<<DateEntrySelected>>', select_end_day)

# -----------------Variable Corrections--------#

# correct_variables()

root.mainloop()
