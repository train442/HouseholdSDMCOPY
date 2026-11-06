import PostProcessing as pp
import Parameters as pm
import Setup as sp
import Simulation as sm
import numpy as np

# zipcode = 75201  #dallas, tx
zip_code = 78701  # austin, tx
zip_code = 48202 # detroit
# zip_code = 33130  # miami
# zip_code = 43215 # columbus

# zip_code = 85016  # PHX
# zip_code = 28741 # ATL
# zip_code = 97002 # PORT
# zip_code = 85328  #LA


house_load = 15000

op = pm.Operation()
tk = pm.TimeKeep()
city = sp.create_city(zipcode=zip_code)
util_dict = {}
if zip_code == 85016:
    util_dict['Net Meter Type'] = 'sellback'
    util_dict['Utility File'] = 'Arizona Public Service Co_803_tariffs.csv'
    util_dict['Utility Name'] = 'Arizona Public Service Co'
    util_dict['Tariff ID'] = 'Time-of-Use 4pm-7pm Weekdays (R-TOU-E)'
else:
    util_dict = sp.get_best_util_for_zip(zip_code)
    util_dict['Net Meter Type'] = util_dict['Net Metering Policy']
    util_dict['Utility File'] = util_dict['File']
    util_dict['Utility Name'] = util_dict['Utility']
    util_dict['Tariff ID'] = util_dict['Tariff']

tariff = sm.make_tariff(new_row=util_dict, ref_city=city, timekeep=tk)
print(tariff.utility + ' ' + tariff.name)

house_dict = {'Load Amount': house_load, 'Load File': np.nan}
house = sm.make_house(new_row=house_dict, ref_city=city, op=op)

rate_arr = pp.by_cost_breakdown(tariff=tariff, values=house.load_profile[:]/12)
pp.plot_cost_breakdown(rate_arr=rate_arr, title='House Load (kWh) by Rate ($/kWh)', y_label='Total Load (kWh)')

# per_arr = pp.by_period_breakdown(tariff=tariff, values=house.load_profile[:] / 12)
# pp.plot_per_breakdown(per_arr=per_arr,
#                       title=f'{city.name} House Load (kWh) by Rate ($/kWh) for {house_load} kWh Annual Load',
#                       y_label='Total Load (kWh)')

pp.plot_rate_chart(tariff=tariff)

hr_arr = pp.load_hr_breakdown(house=house, timekeep=tk)
# pp.plot_hr_breakdown(hr_arr=hr_arr, title=f'{city.name} Hourly Load Breakdown for {house_load} Annual Load')
