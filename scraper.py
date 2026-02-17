import logging
import aiohttp
from bs4 import BeautifulSoup
import asyncio

# Налаштування логування
logger = logging.getLogger(__name__)

# Заголовки, щоб сайти думали, що ми справжній браузер
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "uk-UA,uk;q=0.9,en-US;q=0.8,en;q=0.7"
}

async def fetch_html(url: str):
    """Універсальна функція для завантаження HTML"""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=HEADERS, ssl=False) as response:
                if response.status == 200:
                    return await response.text()
                else:
                    logger.error(f"Помилка {response.status} при завантаженні {url}")
    except Exception as e:
        logger.error(f"Помилка з'єднання з {url}: {e}")
    return None

async def run_scraper_task(url: str) -> list:
    """Головна функція-роутер. Визначає сайт і викликає потрібний парсер."""
    if "olx.ua" in url:
        return await parse_olx(url)
    elif "auto.ria.com" in url:
        return await parse_autoria(url)
    elif "rst.ua" in url:
        return await parse_rst(url)
    # Сюди можна додати reono.ua та cars.ua аналогічним чином
    else:
        logger.warning(f"Невідомий домен: {url}")
        return []

# --- ПАРСЕР OLX ---
async def parse_olx(url: str) -> list:
    html = await fetch_html(url)
    if not html: return []
    
    soup = BeautifulSoup(html, "lxml")
    ads = []
    
    cards = soup.find_all("div", {"data-cy": "l-card"})
    for card in cards:
        try:
            link_tag = card.find("a", href=True)
            if not link_tag: continue
            
            ad_url = link_tag["href"]
            if ad_url.startswith("/"): ad_url = "https://www.olx.ua" + ad_url
            
            # ID
            card_id = card.get("id")
            if not card_id and "-ID" in ad_url:
                card_id = ad_url.split("-ID")[-1].replace(".html", "")

            title = card.find("h6").text.strip() if card.find("h6") else "Без назви"
            price = card.find("p", {"data-testid": "ad-price"}).text.strip() if card.find("p", {"data-testid": "ad-price"}) else "Договірна"

            if card_id:
                ads.append({"id": f"olx_{card_id}", "url": ad_url, "title": title, "price": price})
        except Exception:
            continue
    return ads

# --- ПАРСЕР AUTO.RIA ---
async def parse_autoria(url: str) -> list:
    html = await fetch_html(url)
    if not html: return []

    soup = BeautifulSoup(html, "lxml")
    ads = []
    
    # Auto.RIA використовує section class="ticket-item" для оголошень
    tickets = soup.select("section.ticket-item")
    
    for ticket in tickets:
        try:
            # Отримуємо ID
            ad_id = ticket.get("data-advertisement-id")
            
            # Шукаємо блок контенту
            content = ticket.find("div", class_="content")
            if not content: continue

            # Посилання
            link_tag = content.find("a", class_="m-link-ticket")
            if not link_tag: continue
            ad_url = link_tag.get("href")

            # Назва
            title_tag = link_tag.find("span", class_="blue")
            title = title_tag.text.strip() if title_tag else "Авто"

            # Ціна (шукаємо долари або гривні)
            price_div = content.find("div", class_="price-ticket")
            price = price_div.text.strip().replace(" ", "") if price_div else "Ціна не вказана"
            # Очищуємо ціну від зайвих символів перенесення рядка
            price = " ".join(price.split())

            if ad_id:
                ads.append({
                    "id": f"ria_{ad_id}", # Префікс ria_, щоб не плутати з іншими
                    "url": ad_url,
                    "title": title,
                    "price": price
                })
        except Exception as e:
            logger.error(f" помилка парсингу RIA: {e}")
            continue
            
    return ads

# --- ПАРСЕР RST ---
async def parse_rst(url: str) -> list:
    html = await fetch_html(url)
    if not html: return []

    soup = BeautifulSoup(html, "lxml")
    ads = []
    
    # RST - старий сайт, там оголошення в блоках .rst-ocb-i
    items = soup.find_all("div", class_="rst-ocb-i")
    
    for item in items:
        try:
            # Посилання та ID
            link_tag = item.find("a", class_="rst-ocb-i-a", href=True)
            if not link_tag: continue
            
            ad_url = "https://rst.ua" + link_tag["href"]
            # ID витягуємо з URL (наприклад, /oldcars/vaz/2109/123456.html -> 123456)
            ad_id = link_tag["href"].split("/")[-1].replace(".html", "")

            # Назва
            title_span = item.find("span", class_="rst-ocb-i-h")
            title = title_span.text.strip() if title_span else "Авто"

            # Ціна
            price_span = item.find("span", class_="rst-ocb-i-d-l-i-s-p")
            price = price_span.text.strip() if price_span else "Не вказана"

            if ad_id:
                ads.append({
                    "id": f"rst_{ad_id}",
                    "url": ad_url,
                    "title": title,
                    "price": price
                })
        except Exception:
            continue
            
    return ads
