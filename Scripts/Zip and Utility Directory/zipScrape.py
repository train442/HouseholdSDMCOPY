import pandas as pd
import time
from bs4 import BeautifulSoup as bs
import requests

zip_codes = pd.read_csv('../../Archive/DataFiles/LostZips.csv', dtype={'postal code': str, 'EIA Code': str})

print(zip_codes)
print(zip_codes.shape[0])
print(zip_codes.iloc[0, 0])

# num = zip_codes.size[0]
num = 5

for i in range(num):
    # extract zip
    code = zip_codes.iloc[i, 0]

    # load lat/long url
    url = 'https://www.google.com/search?q=' + code + '+latitude+and+longitude'
    result = requests.get(url)
    doc = bs(result.text, "html.parser")

    # extract latitude and longitude
    coordStr = doc.find_all(["div"], class_='BNeawe iBp4i AP7Wnd')[1].text.split()
    lat = float(coordStr[0].split('°')[0])
    if coordStr[1][0] == 'S':
        lat *= -1

    long = float(coordStr[2].split('°')[0])
    if coordStr[3][0] == 'W':
        long *= -1

    # load city info url
    url2 = 'https://www.unitedstateszipcodes.org/' + code + '/'
    result2 = requests.get(url2, headers={'user-agent': 'Mozilla/5.0 (X11; CrOS x86_64 8172.45.0) AppleWebKit/537.36 ('
                                                        'KHTML, like Gecko) Chrome/51.0.2704.64 Safari/537.36'})
    doc2 = bs(result2.text, "html.parser")
    tags = doc2.find(['tbody'])

    if tags is None:
        print(tags)
    else:
        tags = tags.find_all(['td'])
        print(tags)

    # if tags is None:
    #
    # else:
    #     city = tags[0].text.split(',')[0]
    #     county = tags[2].text.split()[0]

    # print([lat, long, city, county])
    # print(doc2.prettify())
    time.sleep(1)
