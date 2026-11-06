import pandas as pd
import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np

# lookup_file = 'City Data/Load Profiles/City Load Lookup/GA_Atlanta_loads.csv'
lookup_file = 'City Data/Load Profiles/City Load Lookup/CA_Los Angeles_loads.csv'

do_all = False
do_median = True
do_max = False

upgrades = [2]
# upgrades = [10]
# upgrades = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
#
types = ['Single-Family Detached', 'Single-Family Attached']
# types =  ['Single-Family Attached']

lighting = ['100% Incandescent']
# lighting = ['100% LED']
# lighting = ['100% Incandescent', '100% LED', '100% CFL']
has_pv = False

house_lim = 15000
load_lim = 65000

upgrade_dict = {"0": "Baseline",
                "1": "Basic enclosure",
                "2": "Enhanced enclosure",
                "3": "Heat pumps, min-efficiency, electric backup",
                "4": "Heat pumps, high-efficiency, electric backup",
                "5": "Heat pumps, min-efficiency, existing heating as backup",
                "6": "Heat pump water heaters",
                "7": "Whole-home electrification, min efficiency",
                "8": "Whole-home electrification, high efficiency",
                "9": "Whole-home electrification, high efficiency + basic enclosure package (packages 1 & 8)",
                "10": "Whole-home electrification, high efficiency + enhanced enclosure package (packages 2 & 8)"}


colors = ['black', 'blue', 'red', 'green', 'orange', 'black', 'blue', 'red', 'green', 'orange', 'black', 'blue',
          'red', 'green', 'orange', 'black', 'blue','red', 'green', 'orange']
markers = ['.', '.', '.', '.', '.', 'x', 'x', 'x', 'x', 'x', '+', '+', '+', '+', '+', 'v', 'v', 'v', 'v', 'v']


lookup_frame = pd.read_csv(lookup_file)

subframe = lookup_frame[~lookup_frame['has pv']]
subframe = subframe[subframe['upgrade'].isin(upgrades)]
subframe = subframe[subframe['house type'].isin(types)]
subframe = subframe[subframe['total usage (kWh)'] < load_lim]
subframe = subframe[subframe['house size (ft^2)'] < house_lim]
subframe = subframe[subframe['lighting type'].isin(lighting)]

incomes = set(subframe['income level'].to_list())
incomes = sorted(incomes, key=lambda inc: int(inc.split('-')[0].replace('+', '').replace('<','')))

fig, ax = plt.subplots()


if do_all:
    for income, color, marker, in zip(incomes, colors, markers):
        sub_sub_frame = subframe[subframe['income level'] == income]
        x = sub_sub_frame['house size (ft^2)'].to_numpy()
        y = sub_sub_frame['total usage (kWh)'].to_numpy()
        ax.scatter(x=x, y=y, c=color, marker=marker, label=f'$ {income}')
        plt.title('House Load (kWh) vs House Size (ft^2) by Income')
elif do_median:
    for income, color, marker, in zip(incomes, colors, markers):
        sub_sub_frame = subframe[subframe['income level'] == income]
        xs = np.unique(sub_sub_frame['house size (ft^2)'].to_numpy())

        def average_load(size: float, frame: pd.DataFrame):
            mini_frame = frame[frame['house size (ft^2)'] == size]
            avg = np.median(mini_frame['total usage (kWh)'].to_numpy())
            return avg
        y = [average_load(x, sub_sub_frame) for x in xs]
        # y = sub_sub_frame['total usage (kWh)'].to_numpy()
        ax.scatter(x=xs, y=y, c=color, marker=marker, label=f'$ {income}')
        plt.title('House Load (kWh) vs House Size (ft^2) by Income')
elif do_max:
    for income, color, marker, in zip(incomes, colors, markers):
        sub_sub_frame = subframe[subframe['income level'] == income]
        xs = np.unique(sub_sub_frame['house size (ft^2)'].to_numpy())

        def max_load(size: float, frame: pd.DataFrame):
            mini_frame = frame[frame['house size (ft^2)'] == size]
            avg = np.max(mini_frame['total usage (kWh)'].to_numpy())
            return avg
        y = [max(x, sub_sub_frame) for x in xs]
        # y = sub_sub_frame['total usage (kWh)'].to_numpy()
        ax.scatter(x=xs, y=y, c=color, marker=marker, label=f'$ {income}')
        plt.title('House Load (kWh) vs House Size (ft^2) by Income')
else:
    for income, color, marker, in zip(incomes, colors, markers):
        sub_sub_frame = subframe[subframe['income level'] == income]
        xs = np.unique(sub_sub_frame['house size (ft^2)'].to_numpy())


        def load_intensity(size: float, frame: pd.DataFrame):
            mini_frame = frame[frame['house size (ft^2)'] == size]
            avg = np.median(mini_frame['total usage (kWh)'].to_numpy())/size
            return avg


        y = [load_intensity(x, sub_sub_frame) for x in xs]
        # y = sub_sub_frame['total usage (kWh)'].to_numpy()
        ax.scatter(x=xs, y=y, c=color, marker=marker, label=f'$ {income}')
        plt.title('House Load Intensity (kWh/ft^2) vs House Size (ft^2) by Income')

ax.legend(loc='center left', bbox_to_anchor=(1, 0.5))
ax.grid(True)


plt.xlabel('House Size (ft^2')
plt.ylabel('House Load (kWh)')

plt.show()


