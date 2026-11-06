import DataProcessing as dp
import os



lookup_path = '/City Data/Load Profiles/City Load Lookup'

processed_path = '/City Data/Load Profiles/Custom Loads/'

lookup_files = [lookup for lookup in os.listdir(lookup_path)]

usage = 11000

for lookup_file in lookup_files:
    lookup_split = lookup_file.split('_')
    state = lookup_split[0]
    city = lookup_split[1]
    try:
        dp.load_match_yearly(state, city, usage, 'Single-Family Detached')
    except dp.MissingValue:
        print(city, state, 'File could not be made due to lack of matching profiles')



