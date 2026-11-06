import os
import sys

import numpy as np

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))  # repo root
import Setup as sp



# Top 30 full HES-PV analysis
# set_title = 'Top30_PV_HES_V2H_set'
# pool_file = 'top30_pools_by_population.csv'
# net_mets = ['default']
# house_loads = [6000, 11000, 15000]
# pvs = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
# hes = [0, 3, 5, 7, 10, 15, 20, 30, 40]
# commutes = ['35mi_7to3', '35mi_best']
# v2h_lims = [1, .7, .5, .3]
# hes_opts = ['flat']
#
# sp.generate_input_collection(collection_title=set_title,
#                              pool_file=pool_file,
#                              net_met_policies=net_mets,
#                              house_loads=house_loads,
#                              pv_sizes=pvs,
#                              hes_sizes=hes,
#                              hes_opt_styles=hes_opts,
#                              v2h_limits=v2h_lims,
#                              commutes=commutes)

# Top 30 commute analysis
# set_title = 'Top30_commutes_set'
# pool_file = 'top30_pools_by_population.csv'
# net_mets = ['default']
# hes_opts = ['flat']
# charge_schemes = ['default', 'trickle charge']
# pvs = [0]
# hes = [0]
# house_loads = [6000, 11000, 15000]
# commutes = ['20mi_7to3', '20mi_8to4', '20mi_9to5', '20mi_10to6',
#             '35mi_7to3', '35mi_8to4', '35mi_9to5', '35mi_10to6',
#             '50mi_7to3', '50mi_8to4', '50mi_9to5', '50mi_10to6',
#             '100mi_7to3', '100mi_8to4', '100mi_9to5', '100mi_10to6', 'stay_at_home']
# v2h_lims = [1, .95, .9, .85, .8, .75, .7, .65, .6, .55, .5, .45, .4, .35, .3]
#
# sp.generate_input_collection(collection_title=set_title,
#                              pool_file=pool_file,
#                              net_met_policies=net_mets,
#                              house_loads=house_loads,
#                              pv_sizes=pvs,
#                              hes_sizes=hes,
#                              hes_opt_styles=hes_opts,
#                              v2h_limits=v2h_lims,
#                              commutes=commutes,
#                              charge_schemes=charge_schemes)

# All TOU
set_title = 'FullV2H_new'
net_mets = ['default']
hes_opts = ['flat']
pvs = [0]
hes = [0]
house_loads = [6000, 11000, 15000]
v2h_lims = [1, .7, .5, .3]
commutes = ['35mi_7to3', '35mi_best']
pool_file = 'refined_pools.csv'
charge_schemes = ['default', 'trickle charge']
sp.generate_input_collection(collection_title=set_title,
                             pool_file=pool_file,
                             net_met_policies=net_mets,
                             house_loads=house_loads,
                             pv_sizes=pvs,
                             hes_sizes=hes,
                             hes_opt_styles=hes_opts,
                             v2h_limits=v2h_lims,
                             commutes=commutes,
                             charge_schemes=charge_schemes)


# Top 30 full HES-PV analysis
# set_title = 'Top30_PV_HES_NoV2H_set'
# pool_file = 'top30_pools_by_population.csv'
# net_mets = ['default']
# house_loads = [6000, 11000, 15000]
# pvs = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
# hes = [0, 3, 5, 7, 10, 15, 20, 30, 40, 60, 80]
# commutes = ['35mi_7to3', '35mi_best']
# v2h_lims = [1]
# hes_opts = ['flat']
#
# sp.generate_input_collection(collection_title=set_title,
#                              pool_file=pool_file,
#                              net_met_policies=net_mets,
#                              house_loads=house_loads,
#                              pv_sizes=pvs,
#                              hes_sizes=hes,
#                              hes_opt_styles=hes_opts,
#                              v2h_limits=v2h_lims,
#                              commutes=commutes)
