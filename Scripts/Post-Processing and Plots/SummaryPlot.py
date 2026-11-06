import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d import Axes3D
import os
import warnings

warnings.filterwarnings('ignore')

# Parameters
# run_name = 'IDETC_LA_2024'
# run_name = 'IDETC_POR2_2024'
# run_name = 'IDETC_PHX_2024'
# run_name = 'IDETC_ATL_2024'

# run_name = 'Ford_ColumbusOH_runs'
# run_name = 'Ford_AustinTX_runs'
# run_name = 'Ford_DetroitMI_runs'
run_name = 'Ford_MiamiFL_runs'


# house_load = 15000   # can be 6000, 11000, 15000
house_load = 11000
# house_load = 6000

# house_load = 17632.2
# house_load = 7158.5



hes_opt = 'flat'  # can be simple flat
# hes_opt = 'simple'

# net_met = 'one-to-one'
# net_met = 'wholesale'
# netmet = 'none'
# net_met = 'nem3'  # LA only
# net_met = 'no_excess'
# net_met = 'net_billing'
net_met = 'NBC'

v2h_limit = 1  # no V2H for these for now

commute = '35mi_7to3'

do_plot = True  # do plots at all
do_baseline = False
do_peak_eff = False
do_eff = True
do_20yr = False

do_v2h = False
do_deg = False

do_v2h_eff = False
do_nets = False

summary_file = 'Outputs/' + run_name + '/' + run_name + '_summary.csv'

print(os.path.exists(summary_file))

summary_frame = pd.read_csv(summary_file)

loads = np.unique(summary_frame['House Load'].to_numpy())
netmets = list(set(summary_frame['Net Meter Policy'].values.tolist()))
opts = list(set(summary_frame['HES Optimization'].values.tolist()))
if 'Pattern' in summary_frame.columns:
    commutes = list(set(summary_frame['Pattern'].values.tolist()))
    if commute not in commutes:
        commutes = commutes[0]

if house_load not in loads:
    house_load = 11000

if hes_opt not in opts:
    hes_opt = 'simple'

if net_met not in netmets:
    net_met = netmets[0]



# reduce summary frame to desired parameters

summary_frame = summary_frame[summary_frame['House Load'] == house_load]
summary_frame = summary_frame[summary_frame['Net Meter Policy'] == net_met]
summary_frame = summary_frame[summary_frame['HES Optimization'] == hes_opt]
summary_frame = summary_frame[summary_frame['EV Discharge Limit'] == v2h_limit]
if 'Pattern' in summary_frame.columns:
    summary_frame = summary_frame[summary_frame['Pattern'] == commute]

cities = list(set(summary_frame['Reference City'].tolist()))

real_city = list(set(summary_frame['City'].tolist()))

print(cities)

pv_sizes = np.unique(summary_frame['Solar Size (kW)'].to_numpy())
hes_sizes = np.unique(summary_frame['HES Size'].to_numpy())
pv_mesh, hes_mesh = np.meshgrid(pv_sizes, hes_sizes)

reduce_HES = False
reduce_HES_amount = 1

reduce_pv = False
reduce_pv_amount = 1

effs = np.zeros(hes_mesh.shape)
paybacks = np.zeros(hes_mesh.shape)
savings = np.zeros(hes_mesh.shape)
two_decade_values = np.zeros(hes_mesh.shape)
two_decade_values_dep = np.zeros(hes_mesh.shape)
fleet_avoidance = np.zeros(hes_mesh.shape)
v2h_effectiveness = np.zeros(hes_mesh.shape)
system_costs = np.zeros(hes_mesh.shape)
co2_savings = np.zeros(hes_mesh.shape)
peak_efficiencies = np.zeros(hes_mesh.shape)
net_values = np.zeros(hes_mesh.shape)
ev_sim_miles = np.zeros(hes_mesh.shape)
degs = np.zeros(hes_mesh.shape)


def get_row(frame: pd.DataFrame, city: str, hes_size: int, pv_size: int | float, v2h=1):
    reduced = frame[(frame['HES Size'] == hes_size) & (frame['City'] == city) & (frame['Solar Size (kW)'] == pv_size) &
                    (frame['EV Discharge Limit'] == v2h) & (frame['Net Meter Policy'] == net_met)]
    return reduced


def get_max(arr: np.ndarray):
    value = np.max(arr)
    row, col = np.unravel_index(arr.argmax(), arr.shape)
    hes_max = hes_sizes[row]
    pv_max = pv_sizes[col]
    return value, hes_max, pv_max


def get_min(arr: np.ndarray):
    value = np.min(arr)
    row, col = np.unravel_index(arr.argmin(), arr.shape)
    hes_max = hes_sizes[row]
    pv_max = pv_sizes[col]
    return value, hes_max, pv_max


def stack_results():
    fill = np.zeros((1, 11))
    stack = np.vstack((savings, fill, co2_savings, fill, system_costs, fill, effs, fill, paybacks, fill,
                       two_decade_values, fill, fleet_avoidance, fill, v2h_effectiveness, fill, peak_efficiencies))
    stack = pd.DataFrame(stack)
    return stack


dep_mult = np.sum(np.linspace(100, 80, 20)) / 100

for i in range(len(hes_sizes)):
    for j in range(len(pv_sizes)):
        hes = hes_sizes[i]
        pv = pv_sizes[j]
        sub_frame = get_row(frame=summary_frame, city=real_city[0], hes_size=hes, pv_size=pv, v2h=v2h_limit)
        # try:
        #     effs[i, j] += sub_frame['System Cost Efficiency']
        # except ValueError:
        #     print(sub_frame['System Cost Efficiency'])
        #     print(i, j)
        if reduce_HES | reduce_pv:
            pv_cost = sub_frame['Solar Cost ($)']
            hes_cost = reduce_HES_amount * sub_frame['HES Cost ($)']
            if reduce_pv:
                pv_cost *= reduce_pv_amount
            if reduce_HES:
                hes_cost *= reduce_HES_amount

            effs[i, j] = np.max(sub_frame['Net Value ($)'] / (pv_cost + hes_cost),0)
            # effs[i, j] = sub_frame['Baseline Savings ($)'] / (pv_cost + hes_cost)
        else:
            try:
                # effs[i, j] += np.max(sub_frame['System Cost Efficiency'], 0)
                effs[i, j] = sub_frame['Baseline Savings ($)'] / (sub_frame['Solar Cost ($)'] + sub_frame['HES Cost ($)'])
            except ValueError:
                effs[i, j] = 0
        paybacks[i, j] += sub_frame['System Payback Period']
        savings[i, j] += sub_frame['Baseline Savings ($)']
        two_decade_values[i, j] += (savings[i, j] * 20 - sub_frame['System Cost ($)'])
        two_decade_values_dep[i, j] += (savings[i, j] * dep_mult - sub_frame['System Cost ($)'])
        fleet_avoidance[i, j] += sub_frame['Fleet Avoided Cost ($)']
        v2h_effectiveness[i, j] += fleet_avoidance[i, j] / sub_frame['EV Degradation ($)']
        system_costs[i, j] += sub_frame['System Cost ($)']
        co2_savings[i, j] += sub_frame['Baseline Savings (kg CO2)']
        peak_efficiencies[i, j] += sub_frame['System High Peak Shaving Efficiency']
        net_values[i, j] += sub_frame['Net Value ($)']
        degs[i, j] += sub_frame['EV Degradation ($)']

effs[np.where(np.isnan(effs))] = 0
paybacks[0, 0] = np.inf
paybacks[np.where(paybacks < 0)] = np.inf
two_decade_values[0, 0] += -np.inf
two_decade_values_dep[0, 0] = -np.inf

v2h_effectiveness = np.round(v2h_effectiveness, 2)
effs = np.round(effs, 4)
savings = np.round(savings, 2)
two_decade_values_dep = np.round(two_decade_values_dep, 2)
two_decade_values = np.round(two_decade_values, 2)
fleet_avoidance = np.round(fleet_avoidance, 2)
paybacks = np.round(paybacks, 2)

effs_max, effs_hes, effs_pv = get_max(effs)
paybacks_max, paybacks_hes, paybacks_pv = get_min(paybacks)
savings_max, savings_hes, savings_pv = get_max(savings)
two_decade_values_max, two_decade_values_hes, two_decade_values_pv = get_max(two_decade_values)
two_decade_values_dep_max, two_decade_values_dep_hes, two_decade_values_dep_pv = get_max(two_decade_values_dep)
fleet_avoidance_max, fleet_avoidance_hes, fleet_avoidance_pv = get_max(fleet_avoidance)
v2h_effectiveness_max, v2h_effectiveness_hes, v2h_effectiveness_pv = get_max(v2h_effectiveness)
shaving_max, shaving_hes, shaving_pv = get_max(peak_efficiencies)

paybacks[0, 0] = 0
two_decade_values[0, 0] = 0
two_decade_values_dep[0, 0] = 0

data = [['Efficiency', effs_max, effs_hes, effs_pv],
        ['Payback Period', paybacks_max, paybacks_hes, paybacks_pv],
        ['Baseline Savings ($)', savings_max, savings_hes, savings_pv],
        ['2 Decade Value', two_decade_values_max, two_decade_values_hes, two_decade_values_pv],
        ['2 Decade Value w/ Deprec', two_decade_values_dep_max, two_decade_values_dep_hes, two_decade_values_dep_pv],
        ['EV Avoided Cost', fleet_avoidance_max, fleet_avoidance_hes, fleet_avoidance_pv],
        ['V2H Net', v2h_effectiveness_max, v2h_effectiveness_hes, v2h_effectiveness_pv]]

info_frame = pd.DataFrame(data=data, columns=['Metric', 'Value', 'HES Size (kWh)', 'PV Size (kW)'])
info_frame.to_clipboard()

test_arr = info_frame.iloc[:, 1:].to_numpy().flatten()
test_arr = np.reshape(test_arr[[6, 7, 8, 3, 4, 5, 0, 1, 2, 9, 10, 11]], (1, 12))
# pd.DataFrame(test_arr).to_clipboard()

# stack_results().to_clipboard()


if do_plot:
    num = 1
    if do_eff:
        fig1 = plt.figure(num)
        ax1 = fig1.add_subplot(111, projection='3d')
        surf1 = ax1.plot_surface(pv_mesh, hes_mesh, effs, cmap='viridis')
        ax1.set_xlabel('PV Size (kW)')
        ax1.set_ylabel('HES Size (kWh)')
        ax1.set_zlabel('System Cost Efficiency')
        ax1.set_title(cities[0] + ' - System Cost Efficiency')
        fig1.colorbar(surf1, pad=.1)
        num += 1

    if do_baseline:
        fig2 = plt.figure(num)
        ax2 = fig2.add_subplot(111, projection='3d')
        surf2 = ax2.plot_surface(pv_mesh, hes_mesh, savings, cmap='viridis')
        ax2.set_xlabel('PV Size (kW)')
        ax2.set_ylabel('HES Size (kWh)')
        ax2.set_zlabel('Baseline Savings ($)')
        ax2.set_title(cities[0] + '- Baseline Savings ($)')
        fig2.colorbar(surf2, pad=.1)
        num += 1

    if do_20yr:
        fig3 = plt.figure(num)
        ax3 = fig3.add_subplot(111, projection='3d')
        surf3 = ax3.plot_surface(pv_mesh, hes_mesh, two_decade_values, cmap='viridis')
        ax3.set_xlabel('PV Size (kW)')
        ax3.set_ylabel('HES Size (kWh)')
        ax3.set_zlabel('20 Year Value ($)')
        ax3.set_title(cities[0] + '- 20 Year Value ($)')
        fig3.colorbar(surf3, pad=.1)
        num += 1

    if do_v2h:
        fig4 = plt.figure(num)
        ax4 = fig4.add_subplot(111, projection='3d')
        surf4 = ax4.plot_surface(pv_mesh, hes_mesh, fleet_avoidance, cmap='viridis')
        ax4.set_xlabel('PV Size (kW)')
        ax4.set_ylabel('HES Size (kWh)')
        ax4.set_zlabel('EV Cost Avoided ($)')
        ax4.set_title(cities[0] + '- EV Cost Avoided ($)')
        fig4.colorbar(surf4, pad=.1)
        num += 1

    if do_peak_eff:
        fig5 = plt.figure(num)
        ax5 = fig5.add_subplot(111, projection='3d')
        surf5 = ax5.plot_surface(pv_mesh, hes_mesh, peak_efficiencies, cmap='viridis')
        ax5.set_xlabel('PV Size (kW)')
        ax5.set_ylabel('HES Size (kWh)')
        ax5.set_zlabel('Peak Shaving Efficiency')
        ax5.set_title(cities[0] + '- Peak Shaving Efficiency')
        fig5.colorbar(surf5, pad=.1)
        num += 1

    if do_v2h_eff:
        fig6 = plt.figure(num)
        ax6 = fig6.add_subplot(111, projection='3d')
        surf6 = ax6.plot_surface(pv_mesh, hes_mesh, v2h_effectiveness, cmap='viridis')
        ax6.set_xlabel('PV Size (kW)')
        ax6.set_ylabel('HES Size (kWh)')
        ax6.set_zlabel('V2H Effectiveness ($)')
        ax6.set_title(cities[0] + '- V2H Effectiveness')
        fig6.colorbar(surf6, pad=.1)
        num += 1

    if do_deg:
        fig7 = plt.figure(num)
        ax7 = fig7.add_subplot(111, projection='3d')
        surf7 = ax7.plot_surface(pv_mesh, hes_mesh, degs, cmap='viridis')
        ax7.set_xlabel('PV Size (kW)')
        ax7.set_ylabel('HES Size (kWh)')
        ax7.set_zlabel('EV Degradation ($)')
        ax7.set_title(cities[0] + '- EV Degradation ($)')
        fig7.colorbar(surf7, pad=.1)
        num += 1

    if do_nets:
        fig8 = plt.figure(num)
        ax8 = fig8.add_subplot(111, projection='3d')
        surf8 = ax8.plot_surface(pv_mesh, hes_mesh, net_values, cmap='viridis')
        ax8.set_xlabel('PV Size (kW)')
        ax8.set_ylabel('HES Size (kWh)')
        ax8.set_zlabel('Net Value ($)')
        ax8.set_title(cities[0] + '- Net Value ($)')
        fig8.colorbar(surf8, pad=.1)
        num += 1

    plt.show()
