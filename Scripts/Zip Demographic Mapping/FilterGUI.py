import numpy as np
import geopandas as gpd
from numpy import ndarray
import pandas as pd
from pandas import DataFrame
import matplotlib as mpl
from matplotlib.patches import Patch
from matplotlib.patches import Rectangle as rect
from matplotlib.patches import Circle as circ
from matplotlib.text import Text
from matplotlib.backends.backend_tkagg import (FigureCanvasTkAgg, NavigationToolbar2Tk)
from matplotlib.backend_bases import PickEvent
from matplotlib.artist import Artist
from matplotlib.figure import Figure
from matplotlib import pyplot as plt
from matplotlib.lines import Line2D as line
import tkinter as tk
from tkinter import Frame, Label
import tkinter.font as tkFont
from tkinter import ttk
import warnings

warnings.simplefilter(action='ignore', category=FutureWarning)

fig_width = 8
fig_height = 8

zip_json = 'Model Data/master_zip_geo.json'

# zip_shp = 'Model Data/Shape Files/cb_2018_us_zcta510_500k.shp'

us_outline_shp = 'Model Data/Shape Files/cb_2018_us_nation_20m.shp'

zip_new_file = 'Model Data/us_zips_json'

df_geo = gpd.read_file(zip_json)
# df_geo = gpd.read_file(zip_shp)
df_us = gpd.read_file(us_outline_shp)

xlims = [-126, -66]
ylims = [23, 50]


class DataSelect(Frame):
    def __init__(self, parent, *args, **kwargs):
        tk.Frame.__init__(self, parent, *args, **kwargs)
        self.parent: ZipPlot
        self.parent = parent

        self.title = Label(self, text='Data to View')
        self.title.grid(row=0, column=0, columnspan=2)




class ZipPlot(Frame):
    def __init__(self, parent, *args, **kwargs):
        tk.Frame.__init__(self, parent, *args, **kwargs)
        self.parent: MainApplication
        self.parent = parent

        # font
        self.overall_title_font = parent.overall_title_font
        self.frame_title_font = parent.frame_title_font

        # Overall Widget Title
        self.title = tk.Label(self, text='Data Map', font=self.overall_title_font)
        self.title.grid(row=0, column=0, columnspan=2)

        #Data Select Frame
        self.data_select = DataSelect(self, highlightbackground="black", highlightthickness=2, borderwidth=2)
        self.data_select.grid(row=0, column=0, padx=3, pady=3)


        # Plot Frame
        self.plot_frame = tk.Frame(self, highlightbackground="black",
                                   highlightthickness=2, borderwidth=2, relief=tk.RAISED)
        self.plot_frame.grid(row=1, column=1, rowspan=6, padx=3, pady=3)

        # Establish figure
        self.map_fig = Figure(figsize=(fig_width, fig_height))
        self.map_plot = self.map_fig.add_subplot(111)  # this is the ax object
        # self.map_plot.set(aspect='equal')
        self.map_plot.set_xlim(xlims)
        self.map_plot.set_ylim(ylims)
        df_geo.plot(ax=self.map_plot, color=[0, 0, 0, .25])

        # self.clrbr = plt.colorbar(ax=self.lat_plot)

        #  Placing Canvas into latticePlot subframe
        self.canvas = FigureCanvasTkAgg(figure=self.map_fig,
                                        master=self.plot_frame)
        self.canvas.draw()
        self.canvas.get_tk_widget().grid(row=0, column=0)
        self.toolbar = NavigationToolbar2Tk(canvas=self.canvas, window=self.plot_frame, pack_toolbar=False)
        self.toolbar.grid(row=1, column=0, sticky='w')
        self.toolbar.update()


class MainApplication(Frame):
    def __init__(self, parent, *args, **kwargs):
        tk.Frame.__init__(self, parent, *args, **kwargs)
        self.parent: MainApplication
        self.parent = parent

        # Fonts
        self.overall_title_font = tkFont.Font(family='Arial', size=20, weight=tkFont.BOLD)
        self.frame_title_font = tkFont.Font(family='Arial', size=16, weight=tkFont.BOLD)

        self.figure_frame = ZipPlot(self, highlightbackground="black", highlightthickness=2)
        self.figure_frame.grid(row=0, column=0)





root = tk.Tk()
root.title('XPAT Array Modeling')
MainApplication(root).grid(row=0, column=0)
root.mainloop()
