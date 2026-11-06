"""This script was made to download the parquet files from the ResStock database. BE sure this script is moved into
the main directory before running. Add this city to the cities desired list and run. After, run the load_processor
script to process the parquets into 5 minute steps. Then run the load_summarizer to update the lookup files for each
state."""

import webbrowser as wb
import pandas as pd
import os
import requests as rq
import time

master_file = '../../Archive/DataFiles/baseline_metadata_and_annual_results_simp.csv'

acceptable_house_types = ['Single-Family Detached', 'Single-Family Attached']
cities_desired = ['Atlanta', 'Marietta', 'Phoenix', 'Los Angeles', 'Detroit', 'Seattle', 'New York', 'Chicago',
                  'Denver', 'Austin', 'Miami', 'Montgomery', 'Jackson', 'Tallahassee', 'Charleston', 'Boston',
                  'Raleigh', 'Helena', 'Cheyenne', 'Topeka', 'Portland', 'Boise City', 'Lincoln', 'Salt Lake City',
                  'San Francisco', 'Las Vegas', 'Carson City', 'Minneapolis', 'Springfield', 'Bismarck', 'Pierre',
                  'Washington', 'Dallas', 'San Antonio', 'Santa Fe', 'Albuquerque', 'Kansas City',
                  'Memphis', 'Madison', 'Milwaukee', 'Des Moines', 'Fargo', 'Amarillo', 'Indianapolis', 'Cincinnati',
                  'Birmingham', 'Little Rock', 'Baton Rouge', 'Savannah', 'Tallahassee', 'Jacksonville', 'Columbia',
                  'Columbus', 'Charlotte', 'Frankfort', 'Cleveland', 'Dearborn', 'Pittsburgh', 'Philadelphia', 'Dover',
                  'Syracuse', 'Hartford', 'Providence', 'Montpelier', 'Concord', 'Augusta', 'Richmond', 'Asheville',
                  'Orlando', 'Houston', 'Oklahoma City', 'Grand Junction', 'Tucson', 'Reno', 'Buffalo', 'Knoxville',
                  'Trenton', 'Louisville', 'Billings', 'Missoula', 'Harrisburg', 'Rapid City', 'Sioux Falls',
                  'Burlington', 'Green Bay', 'El Paso', 'Flagstaff', 'Duluth', 'Moab', 'Spokane', 'Bend', 'Idaho Falls',
                  'Casper', 'Shreveport', 'Norfolk', 'Roanoke', 'Charlottesville', 'Bowling Green', 'Chattanooga',
                  'Mobile', 'Sacramento', 'St. Louis', 'Indianapolis', 'Baltimore', 'Nashville']

cities_accounted = []

upgrade_levels = range(11)

# dwnld_address = 'https://oedi-data-lake.s3.amazonaws.com/nrel-pds-building-stock/end-use-load-profiles-for-us-building-stock/2022/resstock_amy2018_release_1/timeseries_individual_buildings/by_state/upgrade=0/state=GA/10003-0.parquet'
dwnld_address = 'https://oedi-data-lake.s3.amazonaws.com/nrel-pds-building-stock/end-use-load-profiles-for-us-building-stock/2022/resstock_amy2018_release_1/timeseries_individual_buildings/by_state/upgrade='
t = 20
master_frame = pd.read_csv(master_file)
not_done = True
j = 0
while not_done:
    try:
        for i in range(0, master_frame.shape[0]):
            if i >= j:
                if i % 1000 == 0:
                    print(i)
                city = master_frame.loc[i, 'in.city']
                if city == 'St Louis':
                    city = 'St. Louis'
                elif city == 'Indianapolis City Balance':
                    city = 'Indianapolis'

                bld_type = master_frame.loc[i, 'in.geometry_building_type_acs']
                upgrade = master_frame.loc[i, 'upgrade']
                if (city in cities_desired) & (bld_type in acceptable_house_types) & (upgrade in upgrade_levels):
                    if city not in cities_accounted:
                        cities_accounted.append(city)
                    state = master_frame.loc[i, 'in.state']
                    bld_id = master_frame.loc[i, 'bldg_id']
                    # make directory if not already made
                    new_dir = 'E:/Load Profiles/Unprocessed/Parquets/' + state + '/' + city
                    if not os.path.isdir(new_dir):
                        os.makedirs(new_dir)
                    for j in upgrade_levels:
                        load_file = str(bld_id) + '-' + str(j)
                        if not os.path.exists(new_dir + '/' + load_file + '.parquet'):
                            url = dwnld_address + str(j) + '/state=' + state + '/' + load_file + '.parquet'
                            with rq.get(url) as req:
                                with open(new_dir + '/' + load_file + '.parquet', 'wb') as file:
                                    file.write(req.content)
                                    timed_out = False
            j += 1
        not_done = False
    except (TimeoutError, rq.exceptions.ReadTimeout):
        if timed_out:
            t += 5
        else:
            t = 20
        print(f'Timed out...waiting {t}s')
        time.sleep(t)
        timed_out = True

not_added = []
for city in cities_desired:
    if city not in cities_accounted:
        not_added.append(city)

print(not_added)