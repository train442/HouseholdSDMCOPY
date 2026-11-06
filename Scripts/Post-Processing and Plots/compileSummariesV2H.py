import numpy as np
import pandas as pd
import warnings


warnings.filterwarnings('ignore')

master_file_name = 'IDETC_master_table'


run_list = ['IDETC_ATL_V2H_2024',
            'IDETC_PHX_V2H_2024',
            'IDETC_LA_V2H2_2024',
            'IDETC_POR_V2H_2024']

master_frame = pd.DataFrame()
for run in run_list:
    path = f'Outputs/{run}/{run}_summary.csv'
    frame = pd.read_csv(path)
    master_frame = pd.concat((master_frame, frame), ignore_index=True)

new_cols = ['City', 'Metric', 'House Load', 'EV Discharge Limit']

metrics = ['Total Bill ($)',
           'Total CO2 (kg)',
           'Baseline Savings ($)',
           'Baseline Savings (kg CO2)']