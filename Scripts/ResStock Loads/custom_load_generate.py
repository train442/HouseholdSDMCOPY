import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))  # repo root
import DataProcessing as dp



lookup_path = 'City Data/Load Profiles/City Load Lookup'

processed_path = 'City Data/Load Profiles/Custom Loads/'

lookup_files = [lookup for lookup in os.listdir(lookup_path)]

usages = [6000, 11000, 15000]
housetypes = [None, 'Single-Family Detached', 'Single-Family Attached']

for lookup_file in lookup_files:
    lookup_split = lookup_file.split('_')
    state = lookup_split[0]
    city = lookup_split[1]

    for usage in usages:
        for housetype in housetypes:
            try:
                dp.load_match_yearly(state=state,
                                     city=city,
                                     usage=usage,
                                     house_type=housetype,
                                     save_profile=True)
            except dp.MissingValue:
                print(city, state, 'File could not be made due to lack of matching profiles')
    print(f'{city}, {state} done')


