import numpy as np
import geopandas as gpd
import pandas as pd
import matplotlib.pyplot as plt
import tkinter as tk
import tkinter.font as tkFont
from tkinter import Frame, Label, Entry, RIDGE, Radiobutton, StringVar, DoubleVar, IntVar, Button, DISABLED, NORMAL
from tkinter.ttk import Combobox
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import (FigureCanvasTkAgg, NavigationToolbar2Tk)
from Setup import angle_distance_delta
from shapely.ops import unary_union

zip_json = 'Model Data/master_zip_geo.json'
us_outline_shp = 'Model Data/Shape Files/cb_2018_us_nation_20m.shp'
state_outline_shp = 'Model Data/Shape Files/cb_2018_us_state_5m.shp'

xlims = [-125, -66.5]
ylims = [24.45, 49.8]



pool_frame = pd.read_csv('refined_pools.csv')[0:20]
zip_geoframe = gpd.read_file(zip_json)

us_geoframe = gpd.read_file(us_outline_shp)
state_geoframe = gpd.read_file(state_outline_shp)


fig, ax = plt.subplots()
ax.set_xlim(xlims)
ax.set_ylim(ylims)
ax.set_ylabel('Latitude')
ax.set_xlabel('Longitude')
ax.set_title('Regions of Analysis')

# us_ax = us_geoframe.plot(ax=ax, color=[0, 0, 0, .25])
state_ax = state_geoframe.plot(ax=ax, color=[0, 0, 0, .25], edgecolor='black')
i=1
for index, pool in pool_frame.iterrows():
    ref_city = pool['Reference City']
    print(f'{i}: {ref_city}')
    red_frame = zip_geoframe[zip_geoframe['ZCTA5CE10'].isin(eval(pool['Zips Included']))]
    merged_poly = unary_union(red_frame['geometry'])
    gpd.GeoSeries([merged_poly]).boundary.plot(ax=ax, facecolor=[1, 0, 0, .5], edgecolor='black')

plt.show()


