# Updated scraper.py

# Importing necessary libraries
import requests
from bs4 import BeautifulSoup

class Scraper:
    def __init__(self):
        self.ads_data = []  # Correcting ads_data initialization

    def fetch_ads(self):
        url = 'https://example.com/ads'
        response = requests.get(url)
        self.parse_ads(response.text)

    def parse_ads(self, html):
        soup = BeautifulSoup(html, 'html.parser')
        ads = soup.find_all('div', class_='ad')
        for ad in ads:
            ad_id = ad['data-id']  # Correcting ad_id extraction
            self.ads_data.append({'id': ad_id, 'details': ad.text})

scraper = Scraper()
scraper.fetch_ads()