import pandas as pd


df = pd.read_csv('../../Raw Data Files/zip_to_lat_lon_North America.csv')

df = df.loc[(df['Country'] == 'United States') & (df['state'].notna())]

red = ['postal code', 'place', 'state', 'statecode', 'province_or_county', 'latitude', 'longitude']
print(df[red])

df[red].to_csv('zipCodes.csv', index=False)
