"""
This script was meant to be run after the ev_sales_to_zip script and add the ev_sales data to the master zip josn
file containing zip data for map gui
"""
import numpy as np
import pandas as pd
import geopandas as gpd

zip_json = 'Model Data/master_zip_geo.json'
df_geo = gpd.read_file(zip_json)
df_geo.loc[:, 'EV Sales'] = int(0)

sales_frame = pd.read_csv('EVSales_customer_zip.csv')
i = 0
for index, row in sales_frame.iterrows():
    zip_code = str(row['zipcode'])[0:5].zfill(5)
    zip_row = df_geo[df_geo['ZCTA5CE10'] == zip_code]
    in_data = len(zip_row) != 0
    if in_data:
        zip_ind = zip_row.index.values[0]
        try:
            df_geo.loc[zip_ind, 'EV Sales'] += 1
        except KeyError:
            df_geo.loc[zip_ind, 'EV Sales'] = 1
            print('new ev added')
    else:
        i += 1
        print(f'{zip_code} not in Json, Total Lost EVs: {i}')

df_geo.loc[df_geo['EV Sales'].isna(), 'EV Sales'] = int(0)
# path = 'D:/HouseholdSim/HouseholdSim/Model Data/master_zip_geo.json'
df_geo.to_file(filename='Model Data/master_zip_geo.json', driver='GeoJSON')

