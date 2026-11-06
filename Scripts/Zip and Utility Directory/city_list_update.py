import pandas as pd
import numpy as np
import time
from bs4 import BeautifulSoup as bs
import requests

city_frame = pd.read_csv('Model Data/city_list.csv', dtype={'Time Zone': str})

i = 0
for ind in city_frame.index:
    if np.isnan(city_frame.loc[ind, 'Latitude']):
        city = city_frame.loc[ind, 'City']
        state = city_frame.loc[ind, 'State']
        url = 'https://www.google.com/search?q=' + city + state + '+latitude+and+longitude'
        result = requests.get(url)
        doc = bs(result.text, "html.parser")

        coordStr = doc.find_all(["div"], class_='BNeawe iBp4i AP7Wnd')[0].text.split()
        lat = float(coordStr[0].split('°')[0])
        if coordStr[1][0] == 'S':
            lat *= -1

        long = float(coordStr[2].split('°')[0])
        if coordStr[3][0] == 'W':
            long *= -1

        city_frame.loc[ind, 'Latitude'] = lat
        city_frame.loc[ind, 'Longitude'] = long

    # print(type(city_frame.loc[ind, 'Time Zone']))
    # print(city_frame.loc[ind, 'Time Zone'])

    try:
        empty = np.isnan(city_frame.loc[ind, 'Time Zone'])
    except:
        empty = not (type(city_frame.loc[ind, 'Time Zone']) == str)

    if empty:
        city = city_frame.loc[ind, 'City']
        state = city_frame.loc[ind, 'State']
        print(city)
        url = 'https://www.google.com/search?q=' + city + state + '+time+zone'
        result = requests.get(url)
        doc = bs(result.text, "html.parser")
        try:
            coordStr = doc.find_all(["div"], class_='BNeawe iBp4i AP7Wnd')[0].text.split()
        except IndexError:
            try:
                coordStr = doc.find_all(["div"], class_='BNeawe iBp4i AP7Wnd')[1].text.split()
            except:
                # print(doc.prettify())
                # raise Exception('Take a look')3
                coordStr = doc.find_all(["div"], class_='BNeawe s3v9rd AP7Wnd lRVwie')[1].text.split()
                # print(doc.find_all(["div"], class_='BNeawe s3v9rd AP7Wnd lRVwie'))

        if coordStr[0] == 'Eastern':
            city_frame.loc[ind, 'Time Zone'] = 'EST'
            city_frame.loc[ind, 'Off UTC'] = -5
        elif coordStr[0] == 'Central':
            city_frame.loc[ind, 'Time Zone'] = 'CST'
            city_frame.loc[ind, 'Off UTC'] = -6
        elif coordStr[0] == 'Mountain':
            city_frame.loc[ind, 'Time Zone'] = 'MST'
            city_frame.loc[ind, 'Off UTC'] = -7
        elif coordStr[0] == 'Pacific':
            city_frame.loc[ind, 'Time Zone'] = 'PST'
            city_frame.loc[ind, 'Off UTC'] = -8

        print('done')
        # time.sleep(1)
city_frame.to_csv('Model Data/city_list.csv', index=False)
