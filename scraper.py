import asyncio
import logging
import undetected_chromedriver as uc
from bs4 import BeautifulSoup
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# Налаштування логування
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class OLXMonitor:
    def __init__(self):
        self.options = uc.ChromeOptions()
        # Запуск в режимі headless (без графічного вікна) критичний для сервера
        self.options.add_argument('--headless=new') 
        self.options.add_argument('--no-sandbox')
        self.options.add_argument('--disable-dev-shm-usage')
        self.options.add_argument('--disable-gpu')
        # Встановлюємо українську мову, щоб OLX не перекидав на інші локалі
        self.options.add_argument('--lang=uk-UA')
    
    def fetch_ads(self, url: str):
        """
        Синхронна функція запуску браузера.
        Повертає список словників з даними про оголошення.
        """
        driver = None
        ads_data =
        try:
            driver = uc.Chrome(options=self.options, version_main=None)
            driver.set_page_load_timeout(30)
            
            logger.info(f"Navigating to: {url}")
            driver.get(url)
            
            # Чекаємо завантаження списку оголошень
            # Шукаємо контейнер, що містить картки товарів
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "div[data-cy='l-card']"))
            )
            
            # Отримуємо HTML сторінки
            page_source = driver.page_source
            soup = BeautifulSoup(page_source, 'html.parser')
            
            # Знаходимо всі картки оголошень
            # data-cy='l-card' - стабільний селектор OLX для карток
            cards = soup.find_all('div', attrs={'data-cy': 'l-card'})
            
            for card in cards:
                try:
                    # Витягуємо посилання
                    link_tag = card.find('a', href=True)
                    if not link_tag: continue
                    
                    href = link_tag['href']
                    # Обробка відносних посилань
                    if href.startswith('/'):
                        full_url = f"https://www.olx.ua{href}"
                    else:
                        full_url = href
                        
                    # Ігноруємо рекламні оголошення (зазвичай ведуть на external domains або мають спец. класи)
                    if "olx.ua" not in full_url and not href.startswith('/'):
                        continue

                    # Витягуємо ID оголошення з URL (останні цифри перед.html)
                    # Приклад:.../iphone-13-ID12345.html
                    if "-ID" in full_url:
                        ad_id = full_url.split("-ID")[-1].split(".")
                    else:
                        continue # Нестандартне посилання

                    # Витягуємо ціну
                    price_tag = card.find('p', attrs={'data-testid': 'ad-price'})
                    price = price_tag.text.strip() if price_tag else "Договірна"
                    
                    # Витягуємо заголовок
                    title_tag = card.find('h6')
                    title = title_tag.text.strip() if title_tag else "Без назви"
                    
                    ads_data.append({
                        "id": ad_id,
                        "url": full_url,
                        "title": title,
                        "price": price
                    })
                    
                except Exception as e:
                    logger.error(f"Error parsing card: {e}")
                    continue
                    
        except Exception as e:
            logger.error(f"Global scraping error: {e}")
        finally:
            if driver:
                driver.quit()
                
        return ads_data

# Оскільки Selenium блокуючий, ми загортаємо його в executor
async def run_scraper_task(url: str):
    loop = asyncio.get_running_loop()
    # Запуск у окремому потоці, щоб не блокувати бота
    return await loop.run_in_executor(None, OLXMonitor().fetch_ads, url)
