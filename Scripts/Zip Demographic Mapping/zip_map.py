import numpy as np
import geopandas as gpd
import pgeocode
from shapely.geometry import Point
import geodatasets
import pandas as pd
import matplotlib.pyplot as plt

zip_json = 'Model Data/master_zip_geo.json'

# zip_shp = 'Model Data/Shape Files/cb_2018_us_zcta510_500k.shp'

us_outline_shp = 'Model Data/Shape Files/cb_2018_us_nation_20m.shp'

zip_new_file = 'Model Data/us_zips_json'

xlims = [-126, -66]
ylims = [23, 50]

tou_min = .10
pop_min = 2500
agi_min = 80
ev_min = 10

df_geo = gpd.read_file(zip_json)
# df_geo = gpd.read_file(zip_shp)
df_us = gpd.read_file(us_outline_shp)

red_geo = df_geo[(df_geo['Max Difference'] > tou_min) &
                 (df_geo['Density'] > pop_min) &
                 (df_geo['Avg AGI'] > agi_min) &
                 (df_geo['EV Sales'] > ev_min)]

# lbl = 'Peak/Off-peak Price Differential ($/kWh)'
# tit = 'Nationwide Price Differential ($/kWh)'

# metric = 'Density'
# lbl = 'Population Density (people/sq mi)'
# tit = 'Population Density'

# metric = 'Avg AGI'
# lbl = 'Avg AGI ($1000)'
# tit = 'Average AGI'

# df = pd.read_json(zip_json)

# print(df)
# print(df_geo)
# print(df_us)
#
# print(df_geo.columns)
# print(df_us.columns)
#
# print(df_geo.ZCTA5CE10)

fig, ax = plt.subplots()

# us_ax = df_us.plot(ax=ax, color=[0,0,0,.25])
ax.set_xlim(xlims)
ax.set_ylim(ylims)
base_zip_ax = df_geo.plot(ax=ax, color=[0, 0, 0, .25])
red_zip_ax = red_geo.plot(ax=ax, color=[1, 0, 0, .5])
tit = 'Filtered Results'
# zip_ax = df_geo.plot(ax=ax,
#                      column=metric,
#                      cmap='OrRd',
#                      legend=True,
#                      legend_kwds={'label': lbl,
#                                   'shrink': .75})

ax.set_title(tit)

plt.show()
# gpd.plot(ax=zip_ax)

