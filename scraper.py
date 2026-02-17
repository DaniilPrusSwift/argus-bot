import logging
import aiohttp
from bs4 import BeautifulSoup

# Налаштування логування
logger = logging.getLogger(__name__)

async def run_scraper_task(url: str) -> list:
    """
    Асинхронна функція, яку викликає bot.py.
    Завантажує HTML сторінку OLX та парсить оголошення.
    Повертає список словників: [{'id': ..., 'title': ..., 'price': ..., 'url': ...}]
    """
    ads = []
    
    # Заголовки, щоб імітувати браузер (уникнення блокування)
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
        "Accept-Language": "uk-UA,uk;q=0.9,en-US;q=0.8,en;q=0.7"
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as response:
                if response.status != 200:
                    logger.error(f"Помилка завантаження {url}: статус {response.status}")
                    return []

                html = await response.text()
                soup = BeautifulSoup(html, "lxml")

                # --- ЛОГІКА ПАРСИНГУ ---
                # OLX часто змінює структуру, але "div" з атрибутом data-cy="l-card" є стабільним
                cards = soup.find_all("div", {"data-cy": "l-card"})
                
                for card in cards:
                    try:
                        # 1. Пошук посилання
                        link_tag = card.find("a", href=True)
                        if not link_tag:
                            continue
                        
                        ad_url = link_tag["href"]
                        # Виправляємо відносні посилання
                        if ad_url.startswith("/"):
                            ad_url = f"https://www.olx.ua{ad_url}"

                        # 2. Пошук ID
                        card_id = card.get("id")
                        if not card_id:
                            # Якщо ID немає в атрибуті, спробуємо дістати з URL
                            # Приклад: ...-IDxxxxx.html
                            if "-ID" in ad_url:
                                card_id = ad_url.split("-ID")[-1].replace(".html", "")
                            else:
                                continue # Без ID ми не можемо працювати

                        # 3. Назва
                        title_tag = card.find("h6")
                        title = title_tag.text.strip() if title_tag else "Без назви"

                        # 4. Ціна
                        price_tag = card.find("p", {"data-testid": "ad-price"})
                        price = price_tag.text.strip() if price_tag else "Договірна"

                        ads.append({
                            "id": card_id,
                            "url": ad_url,
                            "title": title,
                            "price": price
                        })

                    except Exception as e:
                        logger.error(f"Помилка парсингу картки: {e}")
                        continue

    except Exception as e:
        logger.error(f"Критична помилка scraper: {e}")

    return ads
