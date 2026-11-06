import pandas as pd

raw_file = 'Raw Data Files/raw_ice_vehicles.csv'

new_file = '../../Model Data/processed_ice.csv'

columns = ['year', 'make', 'model', 'fuelType', 'displ', 'cylinders', 'drive', 'trany', 'VClass', 'city08',
           'highway08', 'comb08', 'phevCity', 'phevHwy', 'phevComb', 'cityE', 'highwayE', 'combE', 'co2', 'evMotor']

newcol_dict = {'year': 'Year',
               'make': 'Make',
               'model': 'Model',
               'fuelType': 'Fuel Type',
               'displ': 'Engine Displacement (L)',
               'cylinders': 'Cylinders',
               'drive': 'Drive Type',
               'trany': 'Transmission Type',
               'Vclass': 'Vehicle Class',
               'city08': 'City MPG',
               'highway08': 'Highway MPG',
               'comb08': 'Combined MPG',
               'phevCity': 'Hybrid City MPGe',
               'phevHwy': 'Hybrid Highway MPGe',
               'phevComb': 'Hybrid Combined MPGe',
               'cityE': 'EV City kWh/100mi',
               'hwyE': 'EV Highway kWh/100mi',
               'combE': 'EV Combined kWh/100mi',
               'co2': 'Emissivity (gCO2/mi)',
               'evMotor': 'Battery (kWh)'}

raw_frame = pd.read_csv(raw_file, usecols=columns)

raw_frame = raw_frame[columns]

raw_frame = raw_frame.rename(columns=newcol_dict)

print(raw_frame)

raw_frame = raw_frame.sort_values(['Year', 'Make', 'Model'])

raw_frame.to_csv(new_file, index=False)


