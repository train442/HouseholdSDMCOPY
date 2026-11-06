import numpy as np
import pandas as pd
import os

# This script takes all of the load profiles from Resstock and creates summary files for each representative city so
# that customer provided load data may be matched to the load data and a fitted load profile can be generated. This
# file will have a columns describing the upgrade level, house characteristics, total kwh usage, and usage data for
# each month for every building id.

redo_files = True
use_processed = True  # use processed files to find total load and such

master_sheet = pd.read_csv('../../Archive/DataFiles/baseline_metadata_and_annual_results_simp.csv')

city_frame = pd.read_csv('../../Model Data/city_list.csv')

raw_path = 'E:/Load Profiles/Unprocessed/Parquets'
cooked_path = '../../City Data/Load Profiles/Processed/Parquets'

processed_path = '../../City Data/Load Profiles/City Load Lookup/'

# summary_columns = ['bldg_id',
#                    'upgrade',
#                    'house type',
#                    'city',
#                    'state',
#                    'county code',
#                    'puma code',
#                    'house size (ft^2)',
#                    'bedrooms',
#                    'total usage (kWh)', 'monthly usage (kWh)', 'emissions region', 'climate zone', 'lat',
#                    'long']

summary_columns = ['bldg_id',
                   'upgrade',
                   'total usage (kWh)',
                   'house type',
                   'house year',
                   'house size (ft^2)',
                   'bedrooms',
                   'stories',
                   'garage',
                   'attic',
                   'foundation category',
                   'roof type',
                   'window',
                   'has pv',
                   'pv size',
                   'lighting type',
                   'has pool',
                   'income level',
                   'occupancy',
                   'monthly usage (kWh)',
                   'usage category',
                   'poverty level',
                   'city',
                   'state',
                   'county code',
                   'puma code',
                   'puma metro category',
                   'emissions region',
                   'climate zone',
                   'lat',
                   'long']

month_ends = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334, 365]

if use_processed:
    steps_per_day = 24 * 12
    load_path = cooked_path
    after_factor = 1 / 12
    load_header = 'Load(kW)'
else:
    steps_per_day = 24 * 4
    load_path = raw_path
    after_factor = 1
    load_header = 'out.electricity.total.energy_consumption'

state_list = [state for state in os.listdir(load_path) if os.path.isdir(os.path.join(load_path, state))]

for state in state_list:
    city_list = [city for city in os.listdir(load_path + '/' + state) if
                 os.path.isdir(os.path.join(load_path + '/' + state, city))]
    for city in city_list:
        summary_file = state + '_' + city + '_loads.csv'
        # check if summary file already exists
        if os.path.exists(processed_path + summary_file) & ~redo_files:
            summary_frame = pd.read_csv(processed_path + summary_file)
            added_row = False  # trips true if something new is added to summary file, in order to save
        else:
            summary_frame = pd.DataFrame(columns=summary_columns)
            added_row = True  # trips true if something new is added to summary file
        file_list = [file for file in os.listdir(load_path + '/' + state + '/' + city)]
        for file in file_list:
            print(file)
            file_split = file.split('.')[0].split('_')[0].split('-')
            # file_split = file[0:-8].split('-')
            bldg_id = int(file_split[0])
            upgrade = int(file_split[1])
            add_row = False
            # now we check if building id is in summary file already
            if bldg_id not in summary_frame['bldg_id'].values:
                add_row = True
            else:  # id is already in frame, but now we check upgrade level
                sub_frame = summary_frame[summary_frame['bldg_id'] == bldg_id]
                add_row = upgrade not in sub_frame['upgrade'].values

            if add_row:  # this load file has not been placed in summary file already, so we append
                ind = master_sheet.index[master_sheet['bldg_id'] == bldg_id].values[0]
                house_type = master_sheet.loc[ind, 'in.geometry_building_type_acs']
                county_code = master_sheet.loc[ind, 'in.county']
                puma_code = master_sheet.loc[ind, 'in.puma']
                sqft = master_sheet.loc[ind, 'in.sqft']
                bedrooms = master_sheet.loc[ind, 'in.bedrooms']
                emissions_region = master_sheet.loc[ind, 'in.generation_and_emissions_assessment_region']
                climate_zone = master_sheet.loc[ind, 'in.building_america_climate_zone']
                lat = master_sheet.loc[ind, 'in.weather_file_latitude']
                long = master_sheet.loc[ind, 'in.weather_file_longitude']
                load_frame = pd.read_parquet(load_path + '/' + state + '/' + city + '/' + file)
                all_usage = load_frame[load_header].to_numpy() * after_factor
                yr_usage = np.around(np.sum(all_usage), decimals=2)
                month_usage = []
                usage_category = master_sheet.loc[ind, 'in.usage_level']
                num_stories = master_sheet.loc[ind, 'in.geometry_stories']
                garage_type = master_sheet.loc[ind, 'in.geometry_garage']
                poverty_level = master_sheet.loc[ind, 'in.federal_poverty_level']
                attic_type = master_sheet.loc[ind, 'in.geometry_attic_type']
                foundation_type = master_sheet.loc[ind, 'in.geometry_foundation_type']
                exterior_type = master_sheet.loc[ind, 'in.geometry_wall_exterior_finish']
                interior_wall_type = master_sheet.loc[ind, 'in.geometry_wall_type']
                pv_present = True if master_sheet.loc[ind, 'in.has_pv'] == 'Yes' else False
                income_category = master_sheet.loc[ind, 'in.income']
                lighting_category = master_sheet.loc[ind, 'in.lighting']
                has_pool = True if master_sheet.loc[ind, 'in.misc_pool'] == 'Has Pool' else False
                occupants = master_sheet.loc[ind, 'in.occupants']
                puma_metro_status = master_sheet.loc[ind, 'in.puma_metro_status']
                pv_size = master_sheet.loc[ind, 'in.pv_system_size']
                roof_type = master_sheet.loc[ind, 'in.roof_material']
                occupant_type = master_sheet.loc[ind, 'in.tenure']
                house_year = master_sheet.loc[ind, 'in.vintage']
                window_type = master_sheet.loc[ind, 'in.windows']
                added_row = True
                for i in range(1, 13):
                    start = month_ends[i - 1] * steps_per_day
                    end = month_ends[i] * steps_per_day - 1
                    month_usage.append(np.around(np.sum(all_usage[start:end]) * after_factor, decimals=2))

                month_usage = str(month_usage)
                new_data = {'bldg_id': bldg_id,
                            'upgrade': upgrade,
                            'total usage (kWh)': yr_usage,
                            'house type': house_type,
                            'house year': house_year,
                            'house size (ft^2)': sqft,
                            'bedrooms': bedrooms,
                            'stories': num_stories,
                            'garage': garage_type,
                            'attic': attic_type,
                            'foundation category': foundation_type,
                            'roof type': roof_type,
                            'window': window_type,
                            'has pv': pv_present,
                            'pv size': pv_size,
                            'lighting type': lighting_category,
                            'has pool': has_pool,
                            'income level': income_category,
                            'occupancy': occupants,
                            'monthly usage (kWh)': month_usage,
                            'usage category': usage_category,
                            'poverty level': poverty_level,
                            'city': city,
                            'state': state,
                            'county code': county_code,
                            'puma code': puma_code,
                            'puma metro category': puma_metro_status,
                            'emissions region': emissions_region,
                            'climate zone': climate_zone,
                            'lat': lat,
                            'long': long}
                new_frame = pd.DataFrame(data=new_data, index=[0])

                summary_frame = pd.concat([summary_frame, new_frame], axis=0)

        if added_row:
            summary_frame.to_csv(processed_path + summary_file, index=False)
