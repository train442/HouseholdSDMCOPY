"""
This script was made to turn ev sales record file into a csv tracking ev sales by zip code.

"""
import pandas as pd


sales_frame = pd.read_csv('EVSales_customer_zip.csv')
ev_frame = pd.DataFrame(columns=['Zip Code', 'F150 Lightning', 'Mach-E', 'Total'])

zips = sales_frame['zipcode'].unique()

zips = [str(zip_code).zfill(5)[0:5] for zip_code in zips]
zips = sorted(zips)

for zip_code in zips:
    try:
        int_zip = int(zip_code)
        reduced_frame = sales_frame[sales_frame['zipcode'] == int_zip]
        num_trucks = 0
        num_machs = 0
        for index, row in reduced_frame.iterrows():
            if row['Vehicle'] == 'Mach E':
                num_machs += 1
            elif row['Vehicle'] == 'F150 LIGHTNING':
                num_trucks += 1

        total = num_machs + num_trucks
        data = {'Zip Code': str(int_zip).zfill(0),
                'Mach-E': num_machs,
                'F150 Lightning': num_trucks,
                'Total': total}
        new_frame = pd.DataFrame(data=data, index=[0])
        ev_frame = pd.concat((ev_frame, new_frame), ignore_index=True)
    except ValueError:
        print(f'invalid zip: {zip_code}')

ev_frame.to_csv('zip_to_ev_sales.csv', index=False)


