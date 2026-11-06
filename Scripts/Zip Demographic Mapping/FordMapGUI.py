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

plot_dim = (8, 8)

xlims = [-126, -66]
ylims = [23, 50]

zip_json = 'Model Data/master_zip_geo.json'
us_outline_shp = 'Model Data/Shape Files/cb_2018_us_nation_20m.shp'
state_outline_shp = 'Model Data/Shape Files/cb_2018_us_state_5m.shp'

states_frame = pd.read_csv('Model Data/states.csv')
states = states_frame['Abbreviation'].tolist()
df_geo = gpd.read_file(zip_json)
df_us = gpd.read_file(us_outline_shp)
df_states = gpd.read_file(state_outline_shp)

frame_padding = {'padx': 5,
                 'pady': 5}

widget_padding = {'padx': 3,
                  'pady': 3}

# Data Dict
data_dict = {'cost-diff': 'Max Difference',
             'avg-agi': 'Avg AGI',
             'pop-dens': 'Density',
             'ev-sales': 'EV Sales'}

lbl_dict = {'cost-diff': 'Peak/Off-peak Price Differential ($/kWh)',
            'avg-agi': 'Avg AGI ($1000)',
            'pop-dens': 'Population Density (people/sq mi)',
            'ev-sales': 'EV Sales'}


class LocationSelect(Frame):
    def __init__(self, parent, *args, **kwargs):
        Frame.__init__(self, parent, *args, **kwargs)
        self.parent: MainApplication
        self.parent = parent

        self.title = Label(self, text='Refine Location', font=self.parent.frame_font)
        self.title.grid(row=0, column=0, columnspan=3)

        self.loc_str = StringVar(self, value='by-state')
        self.state_str = StringVar(self, value='')
        self.zip_code = IntVar(self, value=0)
        self.window_rad = DoubleVar(self, value=50)
        self.lat_val = DoubleVar(self, value=np.nan)
        self.long_val = DoubleVar(self, value=np.nan)

        self.state_btn = Radiobutton(self, text='By State', variable=self.loc_str, value='by-state',
                                     command=self.select_location)
        self.state_btn.grid(widget_padding, row=1, column=0)

        self.zip_btn = Radiobutton(self, text='By Zip Code', variable=self.loc_str, value='by-zip',
                                   command=self.select_location)
        self.zip_btn.grid(widget_padding, row=1, column=1)

        self.coord_btn = Radiobutton(self, text='By Coordinate', variable=self.loc_str, value='by-coord',
                                     command=self.select_location)
        self.coord_btn.grid(widget_padding, row=1, column=2)

        # State

        self.state_sel_lbl = Label(self, text='State: ')
        self.state_sel_lbl.grid(widget_padding, row=2, column=0)

        self.state_sel_box = Combobox(self, textvariable=self.state_str, values=states, validate='key',
                                      validatecommand=self.check_states)
        self.state_sel_box.grid(widget_padding, row=2, column=1, columnspan=2)

        # Zip Code
        self.zip_sel_lbl = Label(self, text='Enter Zip Code: ')
        self.zip_sel_lbl.grid(widget_padding, row=3, column=0)

        self.zip_enter = Entry(self, textvariable=self.zip_code)
        self.zip_enter.grid(widget_padding, row=3, column=1, columnspan=2)
        self.zip_enter.config(state=DISABLED)

        # Coordinates
        self.coord_sel_lbl = Label(self, text='Latitude-Longitude: ')
        self.coord_sel_lbl.grid(widget_padding, row=4, column=0)

        self.lat_enter = Entry(self, textvariable=self.lat_val)
        self.lat_enter.grid(widget_padding, row=4, column=1)
        self.lat_enter.config(state=DISABLED)

        self.long_enter = Entry(self, textvariable=self.long_val)
        self.long_enter.grid(widget_padding, row=4, column=2)
        self.long_enter.config(state=DISABLED)

        # Set Radius
        self.rad_lbl = Label(self, text='Map Radius (mi)')
        self.rad_lbl.grid(widget_padding, row=5, column=0)

        self.rad_entry = Entry(self, textvariable=self.window_rad, validate='key', validatecommand=self.check_rad)
        self.rad_entry.grid(widget_padding, row=5, column=1, columnspan=2)
        self.rad_entry.config(state=DISABLED)

        # Refine Button
        self.change_btn = Button(self, text='Change Location', command=self.change_location)
        self.change_btn.grid(widget_padding, row=6, column=0, columnspan=2)

    def select_location(self):
        if self.loc_str.get() == 'by-state':
            self.state_sel_box.config(state=NORMAL)
            self.rad_entry.config(state=DISABLED)
            self.zip_enter.config(state=DISABLED)
            self.lat_enter.config(state=DISABLED)
            self.long_enter.config(state=DISABLED)
        elif self.loc_str.get() == 'by-zip':
            self.state_sel_box.config(state=DISABLED)
            self.rad_entry.config(state=NORMAL)
            self.zip_enter.config(state=NORMAL)
            self.lat_enter.config(state=DISABLED)
            self.long_enter.config(state=DISABLED)
        elif self.loc_str.get() == 'by-coord':
            self.state_sel_box.config(state=DISABLED)
            self.rad_entry.config(state=NORMAL)
            self.zip_enter.config(state=DISABLED)
            self.lat_enter.config(state=NORMAL)
            self.long_enter.config(state=NORMAL)

    def change_location(self):
        if self.loc_str.get() == 'by-state':
            st = self.state_str.get()
            print(f'state: {st}')
            if len(st) != 0:
                red_frame = states_frame[states_frame['Abbreviation'] == st]
                max_lat = red_frame['Max Latitude'].values[0]
                min_lat = red_frame['Min Latitude'].values[0]
                max_long = red_frame['Max Longitude'].values[0]
                min_long = red_frame['Min Longitude'].values[0]
                print(max_lat, min_lat, max_long, min_long)
                new_xlims = [min_long - .1, max_long + .1]
                new_ylims = [min_lat - .1, max_lat + .1]
            else:
                new_xlims = xlims
                new_ylims = ylims
        elif self.loc_str.get() == 'by-zip':
            zip_code = str(self.zip_code.get()).zfill(5)
            rad = self.window_rad.get()
            print(zip_code)
            try:
                red_frame = df_geo[df_geo['ZCTA5CE10'] == zip_code]
                # print(red_frame)
                # print(red_frame['geometry'])
                centroid = red_frame['geometry'].centroid.values[0]
                latitude = centroid.y
                longitude = centroid.x
                del_lat, del_long = angle_distance_delta(coords=(latitude, longitude), distance=rad)
                new_ylims = np.array([-del_lat, del_lat]) + latitude
                new_xlims = np.array([-del_long, del_long]) + longitude
            except ValueError:
                new_xlims = xlims
                new_ylims = ylims
        elif self.loc_str.get() == 'by-coord':
            rad = self.window_rad.get()
            latitude = self.lat_val.get()
            longitude = self.long_val.get()
            del_lat, del_long = angle_distance_delta(coords=(latitude, longitude), distance=rad)
            new_ylims = np.array([-del_lat, del_lat]) + latitude
            new_xlims = np.array([-del_long, del_long]) + longitude
        else:
            new_xlims = xlims
            new_ylims = ylims

        print(new_xlims, new_ylims)

        self.parent.map_plot.set_xlim(new_xlims)
        self.parent.map_plot.set_ylim(new_ylims)
        self.parent.canvas.draw()

    def check_states(self):
        if self.state_str.get() not in states:
            self.state_str.set('GA')
            return False
        else:
            return True

    def check_rad(self):
        val_min = 15
        val = self.window_rad.get()
        if type(val) in [float, int]:
            if val < val_min:
                val = val_min
                self.window_rad.set(value=val)
        else:
            self.window_rad.set(value=val_min)


class DataSelect(Frame):
    def __init__(self, parent, *args, **kwargs):
        Frame.__init__(self, parent, *args, **kwargs)
        self.parent: MainApplication
        self.parent = parent

        self.title = Label(self, text='Select Data to View', font=self.parent.frame_font)
        self.title.grid(row=0, column=0, columnspan=2)

        self.data_shown = StringVar(self, value='cost-diff')
        self.data_min = DoubleVar(self, value=np.nan)
        self.data_max = DoubleVar(self, value=np.nan)

        self.peak_diff_btn = Radiobutton(self, text='Peak/Off-Peak Cost Differential', variable=self.data_shown,
                                         value='cost-diff', command=self.select_data)
        self.peak_diff_btn.grid(widget_padding, row=1, column=0, columnspan=2, sticky='W')

        self.agi_avg_btn = Radiobutton(self, text='Average AGI', variable=self.data_shown, value='avg-agi',
                                       command=self.select_data)
        self.agi_avg_btn.grid(widget_padding, row=2, column=0, columnspan=2, sticky='W')

        self.pop_dens_btn = Radiobutton(self, text='Population Density (people/mi^2)', variable=self.data_shown,
                                        value='pop-dens', command=self.select_data)
        self.pop_dens_btn.grid(widget_padding, row=3, column=0, columnspan=2, sticky='W')

        self.ev_sales_btn = Radiobutton(self, text='EV Sales', variable=self.data_shown,
                                        value='ev-sales', command=self.select_data)
        self.ev_sales_btn.grid(widget_padding, row=4, column=0, columnspan=2, sticky='W')

        self.filter_btn = Radiobutton(self, text='Filter Multiple', variable=self.data_shown,
                                      value='filter', command=self.select_data)
        self.filter_btn.grid(widget_padding, row=5, column=0, columnspan=2, sticky='W')
        self.filter_btn.config(state=DISABLED)

        self.min_lbl = Label(self, text='Set Minimum: ')
        self.min_lbl.grid(widget_padding, row=6, column=0)

        self.min_entry = Entry(self, textvariable=self.data_min)
        self.min_entry.grid(widget_padding, row=6, column=1)

        self.min_lbl = Label(self, text='Set Maximum: ')
        self.min_lbl.grid(widget_padding, row=7, column=0)

        self.min_entry = Entry(self, textvariable=self.data_max)
        self.min_entry.grid(widget_padding, row=7, column=1)

        self.apply_btn = Button(self, text='Apply', command=self.apply_max_min)
        self.apply_btn.grid(widget_padding, row=8, column=0)

        self.restore_default_btn = Button(self, text='Default', command=self.restore_default)
        self.restore_default_btn.grid(widget_padding, row=8, column=1)

    def select_data(self):
        self.parent.change_data_shown()

    def apply_max_min(self):
        print('lolol')

    def restore_default(self):
        print('lolol')


class MainApplication(Frame):
    def __init__(self, parent, *args, **kwargs):
        Frame.__init__(self, parent, *args, **kwargs)

        # Fonts
        self.title_font = tkFont.Font(family='Arial', size=20, weight=tkFont.BOLD)
        self.frame_font = tkFont.Font(family='Arial', size=16)

        # Title
        self.title = Label(self, text='PV-HES-EV Household Simulation Data Map', font=self.title_font)
        self.title.grid(cnf=widget_padding,
                        row=0, column=0, columnspan=2)

        # Location Select Frame

        self.location_select = LocationSelect(parent=self, highlightbackground="black", highlightthickness=3)
        self.location_select.grid(cnf=frame_padding, row=1, column=0)

        # Data Select Frame
        self.data_select = DataSelect(parent=self, highlightbackground="black", highlightthickness=3)
        self.data_select.grid(cnf=frame_padding, row=2, column=0)

        # Plot

        self.x_lims = xlims
        self.y_lims = ylims

        self.map_holder = Frame(self, relief=RIDGE, highlightbackground="black", highlightthickness=3)
        self.map_holder.grid(cnf=frame_padding, row=1, column=1, rowspan=3)

        self.map_fig = Figure(figsize=plot_dim)
        self.canvas = FigureCanvasTkAgg(self.map_fig, master=self.map_holder)

        self.map_widget = self.canvas.get_tk_widget()
        self.map_widget.grid(row=0, column=0)

        self.map_plot = self.map_fig.add_subplot(111)
        self.base_map_ax = df_states.plot(ax=self.map_plot, color=[0, 0, 0, .25], edgecolor='black')
        self.data_lbl = 'Peak/Off-peak Price Differential ($/kWh)'
        self.data_ax = df_geo.plot(ax=self.map_plot,
                                   column='Max Difference',
                                   cmap='OrRd',
                                   legend=True,
                                   legend_kwds={'label': self.data_lbl, 'shrink': .5}
                                   )
        self.map_plot.set_xlim(self.x_lims)
        self.map_plot.set_ylim(self.y_lims)

        self.canvas.draw()

        self.toolbar = NavigationToolbar2Tk(self.canvas, self.map_holder, pack_toolbar=False)
        self.toolbar.grid(row=1, column=0, sticky='W')

    def change_data_shown(self):
        # self.data_ax.clear()
        # self.data_ax.get_legend().remove()
        # self.map_widget.delete('all')
        # self.data_lbl = lbl_dict[self.data_select.data_shown.get()]
        # self.data_ax = df_geo.plot(ax=self.map_plot,
        #                            column=data_dict[self.data_select.data_shown.get()],
        #                            cmap='RdYlGn',
        #                            legend=True,
        #                            legend_kwds={'label': self.data_lbl, 'shrink': .5}
        #                            )
        # self.toolbar = NavigationToolbar2Tk(self.canvas, self.map_holder, pack_toolbar=False)

        # self.map_plot = self.map_fig.add_subplot(111)
        # self.base_map_ax = df_states.plot(ax=self.map_plot, color=[0, 0, 0, .25], edgecolor='black')
        # self.data_lbl = lbl_dict[self.data_select.data_shown.get()]
        # self.data_ax = df_geo.plot(ax=self.map_plot,
        #                            column='Max Difference',
        #                            cmap='RdYlGn',
        #                            legend=True,
        #                            legend_kwds={'label': self.data_lbl, 'shrink': .5})

        self.map_holder.destroy()

        self.map_holder = Frame(self, relief=RIDGE, highlightbackground="black", highlightthickness=3)
        self.map_holder.grid(cnf=frame_padding, row=1, column=1, rowspan=3)

        self.map_fig = Figure(figsize=plot_dim)
        self.canvas = FigureCanvasTkAgg(self.map_fig, master=self.map_holder)

        self.map_widget = self.canvas.get_tk_widget()
        self.map_widget.grid(row=0, column=0)

        self.map_plot = self.map_fig.add_subplot(111)
        self.base_map_ax = df_states.plot(ax=self.map_plot, color=[0, 0, 0, .25], edgecolor='black')
        self.data_lbl = lbl_dict[self.data_select.data_shown.get()]
        self.data_ax = df_geo.plot(ax=self.map_plot,
                                   column=data_dict[self.data_select.data_shown.get()],
                                   cmap='OrRd',
                                   legend=True,
                                   legend_kwds={'label': self.data_lbl, 'shrink': .5}
                                   )
        self.map_plot.set_xlim(self.x_lims)
        self.map_plot.set_ylim(self.y_lims)
        self.map_plot.set_title(data_dict[self.data_select.data_shown.get()])

        self.canvas.draw()

        self.toolbar = NavigationToolbar2Tk(self.canvas, self.map_holder, pack_toolbar=False)
        self.toolbar.grid(row=1, column=0, sticky='W')

        self.canvas.draw()


root = tk.Tk()
root.title('PV-HES-EV Household Simulation Data Map')
main_app = MainApplication(root)
main_app.grid(row=0, column=0)
root.mainloop()
