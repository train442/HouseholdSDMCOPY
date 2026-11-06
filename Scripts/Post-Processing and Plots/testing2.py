import os.path

import pandas as pd
import numpy as np
import Setup as sp
import TimeManage as tm
import DataProcessing as dp
import Parameters as pm
import Components as cp
import copy
import pickle
import Simulation as sm
import openpyxl
from openpyxl.styles.borders import Border, Side
import PostProcessing as pp

# zipcode = 75201  #dallas, tx
# zip_code = 78701
# zip_code = 48240 # detroit
# zip_code = 33130 # miami
# zip_code = 43215 # columbus
zip_code = 30332  # atlanta
# zip_code = 90033 #la
# zip_code = 85003 #phx
# zip_code = 97204 #por

zips = [30332, 90033, 85003, 97204]
cits = ['ATL', 'LA', 'PHX', 'POR']

# pvs = [0]

pvs = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
# hes = [0,3,5,7,10,15,20]
hes = [0]
loads = [6000, 11000, 15000]
v2h = [1, .95, .9, .85, .8, .75, .7, .65, .6, .55, .5, .45, .4, .35, .3]
# v2h = [1, .7, .5]
v2h = [.5]
# net_mets = ['wholesale', 'one-to-one', 'net_billing']
# net_mets2 = ['wholesale', 'one-to-one']
# net_mets3 = ['net billing']
# net_mets4 = ['NBC']
net_mets = ['default']
hes_opt = ['flat']


# commutes = ['20mi_7to3', '20mi_8to4', '20mi_9to5', '20mi_10to6',
#             '35mi_7to3', '35mi_8to4', '35mi_9to5', '35mi_10to6',
#             '50mi_7to3', '50mi_8to4', '50mi_9to5', '50mi_10to6',
#             '100mi_7to3', '100mi_8to4', '100mi_9to5', '100mi_10to6']
#
commutes = ['35mi_7to3']

#
# for zip_code, city in zip(zips, cits):
#     sp.generate_input_file(title=f'IMECE_2024_{city}_V2H_PV',
#                            zip_codes=[zip_code],
#                            net_met_policies=net_mets,
#                            commutes=commutes,
#                            pv_sizes=pvs,
#                            hes_sizes=hes,
#                            hes_opt_styles=hes_opt,
#                            v2h_limits=v2h)


# #
# sp.generate_input_file(title='IMECE_2024_ATL_V2H',
#                        zip_codes=[zip_code],
#                        net_met_policies=net_mets,
#                        commutes=commutes,
#                        pv_sizes=pvs,
#                        hes_sizes=hes,
#                        hes_opt_styles=hes_opt,
#                        v2h_limits=v2h)
#
#
# zip_code = 85003
# sp.generate_input_file(title='IMECE_2024_PHX_V2H',
#                        zip_codes=[zip_code],
#                        net_met_policies=net_mets,
#                        commutes=commutes,
#                        pv_sizes=pvs,
#                        hes_sizes=hes,
#                        hes_opt_styles=hes_opt,
#                        v2h_limits=v2h)
#
# zip_code = 90033
# sp.generate_input_file(title='IMECE_2024_LA_V2H',
#                        zip_codes=[zip_code],
#                        net_met_policies=net_mets,
#                        commutes=commutes,
#                        pv_sizes=pvs,
#                        hes_sizes=hes,
#                        hes_opt_styles=hes_opt,
#                        v2h_limits=v2h)
#
# zip_code = 97204
# sp.generate_input_file(title='IMECE_2024_POR_V2H',
#                        zip_codes=[zip_code],
#                        net_met_policies=net_mets,
#                        commutes=commutes,
#                        pv_sizes=pvs,
#                        hes_sizes=hes,
#                        hes_opt_styles=hes_opt,
#                        v2h_limits=v2h)

# sp.generate_input_file(title='Ford_DetroitMI_runs',zip_codes=[zip_code],net_met_policies=net_mets4, commutes=commutes)

# sp.generate_input_file(title='Ford_MiamiFL_runs', zip_codes=[zip_code],net_met_policies=net_mets3, commutes=commutes)

# sp.generate_input_file(title='Ford_ColumbusOH_runs', zip_codes=[zip_code], net_met_policies=net_mets3,
#                        commutes=commutes)


# start_date = [6, 1]
# end_date = [8, 1]
#
# op = pm.Operation()
# tk = pm.TimeKeep()
# city = sp.create_city(zipcode=zip_code)
# house_dict = {'Load Amount': 15000, 'Load File': np.nan}
# house = sm.make_house(new_row= house_dict, ref_city=city, op=op)
# pv_dict = {'PV Brand': np.nan, 'PV Model': np.nan, 'System Size (kW)': 5, 'Other Solar File': np.nan}
#
# pv = sm.make_pv(new_row=pv_dict, ref_city=city, tk=tk)
# util_dict = {'Utility File': np.nan, 'Utility Name': 'Georgia Power Co', 'Tariff ID': 'Schedule TOU-PEV-11- Plug-in Electric Vehicle'}
#
# util_dict = sp.get_best_util_for_zip(zip_code)
# util_dict['Net Meter Type'] = util_dict['Net Metering Policy']
# util_dict['Utility File'] = util_dict['File']
# util_dict['Utility Name'] = util_dict['Utility']
# util_dict['Tariff ID'] = util_dict['Tariff']
# tariff = sm.make_tariff(new_row=util_dict, ref_city=city, timekeep=tk)
# print(tariff.name)
# hr_arr = pp.load_hr_breakdown(house=house, timekeep=tk, weekday_only=True)
# hr_arr = pp.hour_breakdown(timekeep=tk, values=house.load_profile[:]/12)

# pp.plot_hr_breakdown(hr_arr=hr_arr, y_label='House Load (kWH)', title='House Load by Hour')
# b = dp.get_index_in_calendar(calendar=tk.calendar, day=21, month=3)

# hr_arr = pp.solar_hr_breakdown(pv=pv, timekeep=tk)

# pp.plot_hr_breakdown(hr_arr=hr_arr, y_label='GHI (kWh/m2)', title='GHI (kWh/m2) by Hour')

# hr_arr = pp.tariff_hr_breakdown(tariff=tariff, timekeep=tk, start_date=start_date, end_date=end_date)
# print(hr_arr)
# pp.plot_hr_breakdown(hr_arr=hr_arr, y_label='Electricity Cost ($/kWh)', title='Electricity Cost ($/kWh) by Hour')

# rate_arr = pp.by_cost_breakdown(tariff=tariff, values=house.load_profile[:]/12)
# pp.plot_cost_breakdown(rate_arr=rate_arr, title='House Load (kWh) by Rate ($/kWh)', y_label='Total Load (kWh)')

# per_arr = pp.by_period_breakdown(tariff=tariff, values=house.load_profile[:]/12)
# pp.plot_per_breakdown(per_arr=per_arr, title='House Load (kWh) by Rate ($/kWh)', y_label='Total Load (kWh)')

# uniq = np.unique(tariff.weekday_rates, axis=0)
# print(uniq)
#
# mons = np.linspace(start=1, stop=12, num=12)
#
# eq = [np.array_equal(row, uniq[0, :]) for row in tariff.weekday_rates]


# print(eq)
#
# print(mons[eq])

# pp.plot_rates_by_month(month_arr=tariff.weekday_rates)
# pp.plot_rate_chart(month_arr=tariff.weekday_rates)

# sm.run_model(input_file='Ford_DetroitMI_runs', collection_name='Ford_DetroitMI_runs')
# sm.run_model(input_file='Ford_MiamiFL_runs', collection_name='Ford_MiamiFL_runs')
# sm.run_model(input_file='Ford_ColumbusOH_runs', collection_name='Ford_ColumbusOH_runs')

# sm.run_model(input_file='Ford_AustinTX_V2H_runs', collection_name='Ford_AustinTX_V2H_runs', overwrite_runs=True)
# sm.run_model(input_file='Ford_DetroitMI_V2H_runs', collection_name='Ford_DetroitMI_V2H_runs', overwrite_runs=True)
# sm.run_model(input_file='Ford_MiamiFL_V2H_runs', collection_name='Ford_MiamiFL_V2H_runs')
# sm.run_model(input_file='Ford_ColumbusOH_V2H_runs', collection_name='Ford_ColumbusOH_V2H_runs')

# sm.run_model(input_file='IMECE_2024_ATL_V2H', collection_name='IMECE_2024_ATL_V2H')
# sm.run_model(input_file='IMECE_2024_LA_V2H', collection_name='IMECE_2024_LA_V2H')
# sm.run_model(input_file='IMECE_2024_PHX_V2H', collection_name='IMECE_2024_PHX_V2H')
# sm.run_model(input_file='IMECE_2024_POR_V2H', collection_name='IMECE_2024_POR_V2H')

# sm.run_model(input_file='IMECE_2024_ATL_V2H_PV', collection_name='DemoForEmily')
# sm.run_model(input_file='IMECE_2024_LA_V2H_PV', collection_name='IMECE_2024_LA_V2H_PV')
# sm.run_model(input_file='IMECE_2024_PHX_V2H_PV', collection_name='IMECE_2024_PHX_V2H_PV')
# sm.run_model(input_file='IMECE_2024_POR_V2H_PV', collection_name='IMECE_2024_POR_V2H_PV')

# sm.run_model(input_file='Top20_PV_HES_set/F8_FL_34787_EST_Orlando_FL',
#              collection_name='Top20_PV_HES_set/F8_FL_34787_EST_Orlando_FL',
#              overwrite_runs=True)
#
# sm.run_model(input_file='F26_CT_6010_EST_Hartford_CT',
#              collection_name='CT_debug',
#              overwrite_runs=True)


# sm.run_collection(collection_path='Top30_PV_HES_NoV2H_set', overwrite_runs=True)
# sm.run_collection(collection_path='Top30_PV_HES_V2H_set', overwrite_runs=True)

# sm.run_model('Top30_Commutes_set/F2_NY_11368_EST_New York_NY', overwrite_runs=True)



sm.run_collection(collection_path='Top30_commutes_set', overwrite_runs=False)
sm.run_collection(collection_path='FullV2H_new', overwrite_runs=True)



a = 1
