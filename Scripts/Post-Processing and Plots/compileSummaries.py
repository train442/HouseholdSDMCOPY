import numpy as np
import pandas as pd
import warnings

"""This script is meant to compile all of the scripts for the IDETC HES-PV paper into two refinable tables. """

warnings.filterwarnings('ignore')

master_file_name = 'IDETC_master_table'

run_list = ['IDETC_ATL_2024',
            'IDETC_ATL2_2024',
            'IDETC_PHX_2024',
            'IDETC_LA_2024',
            'IDETC_POR_2024',
            'IDETC_POR2_2024']

master_frame = pd.DataFrame()
for run in run_list:
    path = f'Outputs/{run}/{run}_summary.csv'
    frame = pd.read_csv(path)
    master_frame = pd.concat((master_frame, frame), ignore_index=True)

new_cols = ['City', 'Metric', 'Net Meter Type', 'EV Discharge Limit', 'House Load']

metrics = ['Total Bill ($)',
           'Total CO2 (kg)',
           'Baseline Savings ($)',
           'System Cost ($)',
           'System Cost Efficiency',
           'System Total Peak Shaving Efficiency',
           'System Payback Period',
           'Baseline Savings (kg CO2)']
cities = list(set(master_frame['City'].tolist()))
v2h_limits = np.unique(master_frame['EV Discharge Limit'].to_numpy())
pv_sizes = np.unique(master_frame['Solar Size (kW)'].to_numpy())
hes_sizes = np.unique(master_frame['HES Size'].to_numpy())

pv_sizes = pv_sizes[~np.isnan(pv_sizes)]
hes_sizes = hes_sizes[~np.isnan(hes_sizes)]

hes_opts = list(set(master_frame['HES Optimization'].tolist()))
net_mets = list(set(master_frame['Net Meter Policy'].tolist()))
house_loads = np.unique(master_frame['House Load'].to_numpy())

hes_cols = [(str(hes) + ' kWh') for hes in hes_sizes]
pv_cols = [(str(pv) + ' kW') for pv in pv_sizes]

hes_frame = pd.DataFrame()
pv_frame = pd.DataFrame()

orgs = ['by HES', 'by PV']

default_net_dict = {'Los Angeles': ['nem3', 'nem3.0'],
                    'Atlanta': ['wholesale'],
                    'Phoenix': ['net billing', 'net_billing'],
                    'Portland': ['one-to-one']}

j = 0
for metric in metrics:
    for city in cities:
        for v2h_limit in v2h_limits:
            for hes_opt in hes_opts:
                for net_met in net_mets:
                    for house_load in house_loads:
                        # common data
                        sub_frame = master_frame[(master_frame['City'] == city) &
                                                 (master_frame['EV Discharge Limit'] == v2h_limit) &
                                                 (master_frame['HES Optimization'] == hes_opt) &
                                                 (master_frame['Net Meter Policy'] == net_met) &
                                                 (master_frame['House Load'] == house_load)]
                        if len(sub_frame) != 0:
                            for org in orgs:
                                data = {'Metric': metric,
                                        'City': city,
                                        'EV Discharge Limit': v2h_limit,
                                        'HES Optimization': hes_opt,
                                        'Net Meter Policy': net_met,
                                        'Default Net': net_met in default_net_dict[city],
                                        'House Load': house_load}
                                if org == 'by HES':
                                    for pv in pv_sizes:  # by actual size not string
                                        sub_sub_frame = sub_frame[(sub_frame['Solar Size (kW)'] == pv)]
                                        if len(sub_sub_frame) != 0:
                                            i = 0
                                            data['Solar Size (kW)'] = pv
                                            for hes in hes_cols:
                                                size = hes_sizes[i]
                                                sub_sub_sub_frame = sub_sub_frame[(sub_sub_frame['HES Size'] == size)]
                                                if len(sub_sub_sub_frame) != 0:
                                                    data[hes] = sub_sub_sub_frame[metric].values[0]

                                                i += 1
                                            to_add = pd.DataFrame(data=data, index=[j])
                                            hes_frame = pd.concat((hes_frame, to_add), ignore_index=True)

                                elif org == 'by PV':
                                    for hes in hes_sizes:
                                        sub_sub_frame = sub_frame[(sub_frame['HES Size'] == hes)]
                                        if len(sub_sub_frame) != 0:
                                            i = 0
                                            data['HES Size'] = hes
                                            for pv in pv_cols:
                                                size = pv_sizes[i]
                                                sub_sub_sub_frame = sub_sub_frame[(sub_sub_frame['Solar Size (kW)'] ==
                                                                                   size)]
                                                if len(sub_sub_sub_frame) != 0:
                                                    data[pv] = sub_sub_sub_frame[metric].values[0]

                                                i += 1
                                            to_add = pd.DataFrame(data=data, index=[j])
                                            pv_frame = pd.concat((pv_frame, to_add), ignore_index=True)
                            j += 1
    print(metric + ' is done')
hes_path = master_file_name + '_by_HES.csv'
pv_path = master_file_name + '_by_PV.csv'

hes_frame.to_csv(hes_path, index=False)
pv_frame.to_csv(pv_path, index=False)
