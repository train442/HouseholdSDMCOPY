import pandas as pd
import numpy as np

"""This file creates TOU rates stored in "custom_tariffs.csv" within the Utilities folder using schedule files stored 
inside the Custom folder within Utilities"""

# Input Parameters
schedule_file = '3periodTOU'
monthly_rate = 15

schedule_loc = 'Utilities/Custom/'

schedule = pd.read_csv(schedule_loc + schedule_file + '.csv')


custom_path = '../../Utilities/Custom_tariffs.csv'
custom_frame = pd.read_csv(custom_path)

weekday_schedule = schedule[schedule['Weekday/end'] == 'Weekday'].iloc[:, 2:].to_numpy()  # get weekday schedule
weekend_schedule = schedule[schedule['Weekday/end'] == 'Weekend'].iloc[:, 2:].to_numpy()  # get weekend schedule


def get_max_diff(sched: np.ndarray):
    max_diff = np.max(np.max(sched, axis=1) - np.min(sched, axis=1))
    return max_diff


max_difference = max(get_max_diff(weekday_schedule), get_max_diff(weekend_schedule))

print(max_difference)

unique_rates = np.unique(np.append(np.unique(weekend_schedule), np.unique(weekday_schedule)))  # get unique rates
periods = []
for i in range(len(unique_rates)):
    weekday_schedule[weekday_schedule == unique_rates[i]] = i + 1
    weekend_schedule[weekend_schedule == unique_rates[i]] = i + 1
    periods.append([[-1, unique_rates[i]]])

weekday_schedule = str(weekday_schedule.astype(int).tolist())
weekend_schedule = str(weekend_schedule.astype(int).tolist())
periods = str(periods)

data = {'Name': schedule_file,
        'Utility': 'Custom',
        'Verified': True,
        'TimeOfUse': True,
        'Tiered': False,
        'Demand': False,
        'Monthly Charge': monthly_rate,
        'Minimum Charge': 0,
        'Time-of-Use Rates': periods,
        'Max Difference': max_difference,
        'Weekday Schedule - Energy': weekday_schedule,
        'Weekend Schedule - Energy': weekend_schedule,
        'Demand Rates': np.nan,
        'Weekday Schedule - Power': np.nan,
        'Weekend Schedule - Power': np.nan}

new_frame = pd.DataFrame(data=data, index=[len(custom_frame)])

custom_frame = pd.concat((custom_frame, new_frame))

custom_frame.to_csv(custom_path, index=False)

