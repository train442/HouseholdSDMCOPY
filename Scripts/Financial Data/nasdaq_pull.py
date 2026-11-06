import os

import nasdaqdatalink as nsdq
from matplotlib import pyplot as plt

api_key = os.environ['NASDAQ_DATA_LINK_API_KEY']  # was hardcoded in source -- set this env var instead

indicators = ['ZSFH', 'LRSM', 'Z5BR', 'Z4BR', 'Z3BR', 'Z2BR', 'Z1BR']
labels = ['Single Family', 'Median List Price', '5 Bedroom Value', '4 Bedroom Value', '3 Bedroom Value',
          '2 Bedroom Value', '1 Bedroom Value']



nsdq.ApiConfig.api_key = api_key
db = nsdq.get_table('ZILLOW/DATA',indicator_id=indicators, region_id='1697')
# db = nsdq.get_table('ZILLOW/DATA', region_id='1697')

print(db['indicator_id'].unique())

for indicator, curve_label in zip(indicators, labels):
    subframe = db[db['indicator_id'] == indicator]
    if len(subframe) != 0:
        time_vals = subframe['date'].values
        vals = subframe['value'].values
        plt.plot(time_vals, vals, label = curve_label)

plt.title('Fayette County, GA House Price Indicators')
plt.ylabel('Value ($)')
plt.xlabel('Date')

plt.legend()
plt.show()
print(db)
print(type(db))
