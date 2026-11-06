import pandas as pd

file = '../../Old Utility Scripts/utility companies_zipcodes.csv'
zip_codes = pd.read_csv(file, dtype={'zip': str, 'eiaid': str})
print(zip_codes.size)
print(zip_codes.iloc[0, 0])
for i in range(zip_codes.shape[0]):
    zip_codes.iloc[i, 0] = zip_codes.iloc[i, 0].zfill(5)

print(zip_codes)
zip_codes.to_csv(file, index=False)
