import h5pyd
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.image as mpimg
from scipy.spatial import cKDTree

f = h5pyd.File("/nrel/nsrdb/v3/nsrdb_2018.h5", 'r')

dset_coords = f['coordinates'][...]
tree = cKDTree(dset_coords)

def nearest_site(tree, lat_coord, lon_coord):
    lat_lon = np.array([lat_coord, lon_coord])
    dist, pos = tree.query(lat_lon)
    return pos

#city_coords = (40.7128, -74.0059)
city_coords = (33.9140, -84.381954)
city_index = nearest_site(tree, city_coords[0], city_coords[1])

meta = pd.DataFrame(f['meta'][...])
print(meta.loc[city_index, 'urban'])

dset = f['ghi']
time_index = pd.to_datetime(f['time_index'][...].astype(str))

ghi_series = dset[:, city_index]/dset.attrs['psm_scale_factor']

plt.plot(time_index, ghi_series)
plt.ylabel('GHI kW/m^2')
plt.title('GHI vs Time 2018')
plt.show()


