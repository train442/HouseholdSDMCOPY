import pandas as pd

file = '../../Raw Data Files/baseline_metadata_and_annual_results.csv'
newfile = 'baseline_metadata_and_annual_results_simp.csv'

cols = ['bldg_id', 'upgrade', 'in.geometry_building_type_acs', 'in.city', 'in.state', 'in.county', 'in.puma',
        'in.sqft', 'in.bedrooms', 'out.electricity.total.energy_consumption.kwh',
        'in.generation_and_emissions_assessment_region', 'in.building_america_climate_zone',
        'in.weather_file_city', 'in.weather_file_latitude', 'in.weather_file_longitude']

frame = pd.read_csv(file, usecols=cols)

for i in range(0, frame.shape[0]):
    str_split = frame.loc[i, 'in.city'].split(', ')
    if len(str_split) > 1:
        str_split = str_split[1].split('-')
        city_name = str_split[0]
        if city_name == 'Louisville Jefferson County Metro Government Balance':  # fixing one weird line item
            city_name = 'Louisville'
        frame.loc[i, 'in.city'] = city_name

new_frame = frame[cols]

new_frame.to_csv(newfile, index=False)
