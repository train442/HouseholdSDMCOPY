import geopandas as gpd
import matplotlib.pyplot as plt
import pathlib

gdf = gpd.read_file('../../Raw Data Files/map_of_pumas_in_census_region_1_northeast.geojson')



gdf.plot(figsize=(10,6))
plt.show()
