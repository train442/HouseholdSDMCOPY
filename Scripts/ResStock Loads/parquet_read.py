import pandas as pd

pd.options.display.width = 0
# pd.set_option('display.max_rows', None)

path = 'E:/Load Profiles/Processed/Parquets/GA/Atlanta/'
file = '16255-1_5min'

df = pd.read_parquet(path+file+'.parquet')

print(df)
# print(df['Load(kW)'].to_numpy().sum()/12)

df.to_csv('example_load.csv', index=False)

