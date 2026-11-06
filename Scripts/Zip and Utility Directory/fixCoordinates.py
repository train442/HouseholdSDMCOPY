import pandas as pd

df = pd.read_excel('majorCitiesRaw.xlsx')

for i in range(0, df.shape[0]):
    raw = df.loc[i, 'Latitude']
    coord = raw.split(' ')
    lat_coord = coord[0].split('°')
    if lat_coord[1] == 'N':
        df.loc[i, 'Latitude'] = float(lat_coord[0])
    else:
        df.loc[i, 'Latitude'] = -1 * float(lat_coord[0])

    long_coord = coord[1].split('°')
    if long_coord[1] == 'E':
        df.loc[i, 'Longitude'] = float(long_coord[0])
    else:
        df.loc[i, 'Longitude'] = -1 * float(long_coord[0])

print(df)

df.to_excel('Major_Cities.xlsx', index=False)

# print(df.loc[0, 'Latitude'])
# raw = df.loc[0, 'Latitude']
# print(raw.split(' '))
# coord = raw.split(' ')
# print(coord)
