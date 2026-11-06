import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

# run_name = 'IDETC_PHX_V2H_2024'
# run_name = 'Ford_ColumbusOH_V2H_runs'
# run_name = 'Ford_AustinTX_V2H_runs'
# run_name = 'Ford_DetroitMI_V2H_runs'
# run_name = 'Ford_MiamiFL_V2H_runs'

# run_name = 'Ford_ColumbusOH_V2H_runs'
# run_name = 'Ford_AustinTX_V2H_runs'
# run_name = 'Ford_DetroitMI_V2H_runs'
# run_name = 'Ford_MiamiFL_V2H_runs'

# run_name = 'IMECE_2024_ATL_V2H'
run_name = 'IMECE_2024_LA_V2H'
# run_name = 'IMECE_2024_PHX_V2H'
# run_name = 'IMECE_2024_POR_V2H'

summary_file = 'Outputs/' + run_name + '/' + run_name + '_summary.csv'
summary_frame = pd.read_csv(summary_file)
do_plot = True

house_load = 11000  # can be 6000, 11000, 15000
# house_load = 11000
# house_load = 6000
by_spare_capacity = False

by_distance = True  # compare distances (need to specify time)
time = '9to5'

by_time = True  # compare times (need to specify distance)
dist = '35mi'

hes_opt = 'flat'

bat_size = 98  # kWh

# desired_value = 'Baseline Savings (kg CO2)'
# desired_value = 'Baseline Savings ($)'
desired_value = 'Fleet Avoided Cost ($)'
# desired_value = 'Fleet Avoided CO2 (kg)'
pv_size = 0


def refine_commutes(commute_list) -> list[str]:
    new_list = []
    for commute in commute_list:
        if by_distance and by_time:
            new_list.append(commute)
        elif by_distance:
            if commute.split('_')[1] == time:
                new_list.append(commute)
        elif by_time:
            if commute.split('_')[0] == dist:
                new_list.append(commute)
    new_list = sorted(list(set(new_list)), key=lambda x: (int(x.split('mi')[0]), int(x.split('_')[1].split('to')[0])))
    return new_list


def get_commute_str(commute: str):
    spl1 = commute.split('_')
    mileage = spl1[0]
    workday = spl1[1]
    spl2 = workday.split('to')
    leave = spl2[0]
    return_time = spl2[1]
    com_str = f'{mileage}, {leave}am-{return_time}pm'
    return com_str


loads = np.unique(summary_frame['House Load'].to_numpy())
commutes = list(set(summary_frame['Pattern'].tolist()))

commutes = sorted(commutes, key=lambda x: int(x.split('mi')[0]))

city = list(set(summary_frame['City'].tolist()))[0]
state = list(set(summary_frame['State'].tolist()))[0]
if by_distance or by_time:
    commutes = refine_commutes(commute_list=commutes)

# commutes = commutes[5:].append(commutes[:5])

# commutes = ['20mi_9to5'] or list custom ones
v2h_limits = np.unique(summary_frame['EV Discharge Limit'].to_numpy())

if house_load not in loads:
    house_load = 11000

sub_frame = summary_frame[summary_frame['House Load'] == house_load]
sub_frame = sub_frame[sub_frame['Solar Size (kW)'] == pv_size]

if by_spare_capacity:
    x_vals = (1 - v2h_limits) * bat_size
    x_tit = 'Allowed Capacity (kWh)'
else:
    x_vals = v2h_limits
    x_tit = 'V2H Limit (%)'

if do_plot:
    i = 0
    for commute in commutes:
        if i < 4:
            style = 'dashdot'
        elif i < 8:
            style = 'dotted'
        elif i < 12:
            style = 'dashed'
        else:
            style = 'solid'

        rem = i % 4

        if rem == 0:
            clr = '#d62728'
        elif rem == 1:
            clr = '#bcbd22'
        elif rem == 2:
            clr = '#2ca02c'
        elif rem == 3:
            clr = '#1f77b4'
        else:
            clr = '#1f77b4'

        sub_sub_frame = sub_frame[sub_frame['Pattern'] == commute]
        values = [sub_sub_frame.loc[sub_sub_frame['EV Discharge Limit'] == limit, desired_value].values[0] for limit in
                  v2h_limits]
        ln = plt.plot(x_vals * 100, values, label=get_commute_str(commute=commute), linestyle=style, color=clr)
        print(ln[0].get_color())
        i += 1

    if by_spare_capacity:
        plt.xlabel('Spare Capacity (kWh)')
    else:
        plt.xlabel('V2H Limit (%)')
    if desired_value == 'Fleet Avoided Cost ($)':
        plt.ylabel('V2H Savings ($)')
        plt.title(f'V2H Savings ($) vs {x_tit} for {city}, {state}')
    else:
        plt.ylabel(f'{desired_value}')
        plt.title(f'{desired_value} vs {x_tit} for {city}, {state}')

    # plt.legend(loc='upper left', bbox_to_anchor=(1.05,1))
    plt.legend(prop={'size': 8}, loc='upper left', bbox_to_anchor=(.8, 1))
    plt.show()
