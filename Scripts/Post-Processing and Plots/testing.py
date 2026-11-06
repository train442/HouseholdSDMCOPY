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
import warnings

warnings.filterwarnings('ignore', category=RuntimeWarning)
# pp.analyze_set_optimum_HES_PV(collection_name='Top20_PV_HES_set')

# pp.collection_summary_plots(collection_name='Top20_PV_HES_set')
# pp.collection_summary_plots(collection_name='NEM3_LA')
# pp.collection_v2h_plots(collection_name='Top20_commutes_set')

# title = 'ATL_Test'
# zipcodes = [30269]
# house_loads = [11000]
# pvs = [0]
# hes = [0]
# commutes = ['20mi_7to3', '20mi_8to4', '20mi_9to5', '20mi_10to6',
#             '35mi_7to3', '35mi_8to4', '35mi_9to5', '35mi_10to6',
#             '50mi_7to3', '50mi_8to4', '50mi_9to5', '50mi_10to6',
#             '100mi_7to3', '100mi_8to4', '100mi_9to5', '100mi_10to6',
#             'stay_at_home']
# charge_schemes = ['trickle charge', 'default']
# sp.generate_input_file(title=title,
#                        commutes=commutes,
#                        house_loads=house_loads,
#                        zip_codes=zipcodes,
#                        pv_sizes=pvs,
#                        hes_sizes=hes,
#                        charge_schemes=charge_schemes)

# input_file = 'ATL_Test'
# sm.run_model(input_file=input_file,collection_name=input_file, full_results=True, overwrite_runs=True)

# res1 = sm.load_results_file(f'Outputs/{input_file}/Results/{input_file}_Run_2.pkl')
# #
# pp.plot_results(res1)
# #
# res2 = sm.load_results_file(f'Outputs/{input_file}/Results/{input_file}_Run_5.pkl')
# pp.plot_results(res2)


# pp.v2h_tables(collection_name='FullV2H')

# pp.pool_input_data_summary(pool_file='top20_pools_by_population')
# pp.pool_commute_summary(pool_file='top20_pools_by_population')

pp.make_pool_util_plots(pool_file='top30_pools_by_population')

