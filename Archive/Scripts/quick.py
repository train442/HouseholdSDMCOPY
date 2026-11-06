from bs4 import BeautifulSoup as bs
import requests
import re
# url = 'https://www.google.com/search?q=01477+latitude+and+longitude'
# url = 'https://www.google.com/search?q=01002+county'
# url = 'https://www.unitedstateszipcodes.org/00501/#cities'
url = 'https://apps.openei.org/USURDB/rate/view/634ecdd7ce47d9f8fe0fd281'

result = requests.get(url, headers={'user-agent': 'Mozilla/5.0 (X11; CrOS x86_64 8172.45.0) AppleWebKit/537.36 ('
                                                  'KHTML, like Gecko) Chrome/51.0.2704.64 Safari/537.36'})
doc = bs(result.text, "html.parser")
print(doc.prettify())

# tags = doc.find_all(["span"], {"data-ved": "2ahUKEwjN7PmI9e36AhVDjokEHWbkCJAQ2kooAXoECGEQAg"})

#tags = doc.find_all(["div"], class_='BNeawe s3v9rd AP7Wnd')


# tags = doc.find(['tbody']).find_all(['td'])
# print(tags)
# print(tags[3].text)
#
#
#print(tags[0].text.split()[0])

