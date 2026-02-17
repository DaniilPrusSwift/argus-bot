import asyncio
import logging
import sys
from datetime import datetime

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web

import config
import database
from scraper import run_scraper_task

# Ініціалізація
bot = Bot(token=config.BOT_TOKEN)
dp = Dispatcher()
logging.basicConfig(level=logging.INFO, stream=sys.stdout)

# Список доменів, які підтримує бот
SUPPORTED_DOMAINS = ["olx.ua", "auto.ria.com", "rst.ua"]

# --- Клавіатури ---
def get_main_keyboard(is_active: bool) -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text="🔗 Встановити посилання", callback_data="set_link")],
        [InlineKeyboardButton(text="👤 Профіль", callback_data="profile")],
        [InlineKeyboardButton(text="💳 Оплатити підписку", callback_data="pay")],
    ]

    if not is_active:
        buttons.insert(0, [InlineKeyboardButton(text="🚀 Активувати", callback_data="pay")])

    return InlineKeyboardMarkup(inline_keyboard=buttons)

# --- Обробники команд (Handlers) ---

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await database.add_user(message.from_user.id, message.from_user.username)
    await message.answer(
        f"Вітаю, {message.from_user.first_name}! 🤖\n\n"
        "Я — Argus, система моніторингу оголошень (OLX, Auto.RIA, RST).\n"
        "Я буду надсилати нові оголошення за твоїм запитом миттєво.\n\n"
        "Тобі надано **24 години** тестового доступу.",
        reply_markup=get_main_keyboard(True)
    )

@dp.callback_query(F.data == "set_link")
async def ask_link(callback: types.CallbackQuery):
    await callback.message.answer(
        "Надішліть мені посилання на пошук з **OLX, Auto.RIA або RST** з вже обраними фільтрами.\n\n"
        "Приклад:\n`https://www.olx.ua/uk/elektronika/telefony/...`\n"
        "або\n`https://auto.ria.com/uk/search/...`"
    , parse_mode="Markdown")
    await callback.answer()

# --- Оновлений обробник посилань (підтримує різні сайти) ---
@dp.message(lambda msg: any(domain in (msg.text or "") for domain in SUPPORTED_DOMAINS))
async def save_link(message: types.Message):
    url = message.text.strip()
    
    # Валідація http/https
    if not url.startswith("http"):
        await message.answer("⚠️ Посилання має починатися з http:// або https://")
        return
        
    await database.update_search_url(message.from_user.id, url)
    
    # Визначаємо назву сайту для повідомлення
    site_name = "Сайт"
    if "olx.ua" in url: site_name = "OLX"
    elif "auto.ria.com" in url: site_name = "Auto.RIA"
    elif "rst.ua" in url: site_name = "RST"

    await message.answer(
        f"✅ Посилання на **{site_name}** збережено!\nМоніторинг розпочато.", 
        reply_markup=get_main_keyboard(True),
        parse_mode="Markdown"
    )

@dp.callback_query(F.data == "pay")
async def send_invoice(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    msg = (
        "💳 **Оплата підписки (30 днів)**\n\n"
        f"Вартість: **400 грн**\n\n"
        f"1. Перейдіть за посиланням: [Поповнити Банку]({config.MONO_JAR_LINK})\n"
        f"2. У коментарі до платежу вкажіть цифри: `{user_id}`\n\n"
        "⚠️ **Важливо:** Без ID у коментарі автоматична активація неможлива!"
    )
    await callback.message.answer(msg, parse_mode="Markdown", disable_web_page_preview=True)
    await callback.answer()

# --- Оновлений Профіль з таймером ---
@dp.callback_query(F.data == "profile")
async def show_profile(callback: types.CallbackQuery):
    status = await database.get_user_sub_status(callback.from_user.id)
    if not status:
        await callback.answer("Помилка профілю")
        return
        
    end_date_dt = datetime.fromtimestamp(status['sub_end_date'])
    end_date_str = end_date_dt.strftime('%Y-%m-%d %H:%M')
    
    # Розрахунок часу, що залишився
    now = datetime.now()
    remaining = end_date_dt - now
    
    if remaining.total_seconds() > 0:
        days = remaining.days
        hours = remaining.seconds // 3600
        minutes = (remaining.seconds % 3600) // 60
        time_left_str = f"{days} дн. {hours} год. {minutes} хв."
    else:
        time_left_str = "Термін вийшов ⌛️"

    state = "Активна ✅" if status['is_active'] else "Неактивна ❌"
    url = status['url'] if status['url'] else "Не встановлено"
    
    msg = (
        f"🆔 ID: `{callback.from_user.id}`\n"
        f"Статус: {state}\n"
        f"Закінчується: {end_date_str}\n"
        f"⏱ **Залишилось:** {time_left_str}\n\n"
        f"🔗 Посилання: {url}"
    )
    await callback.message.answer(msg, parse_mode="Markdown")
    await callback.answer()

# --- Фоновий процес моніторингу ---
async def monitoring_worker():
    """Нескінченний цикл перевірки оновлень"""
    while True:
        try:
            tasks = await database.get_all_monitoring_tasks()
            # Групуємо користувачів за URL, щоб не робити дублюючі запити
            url_map = {}
            for user_id, url in tasks:
                if url not in url_map:
                    url_map[url] = []
                url_map[url].append(user_id)
            
            for url, user_ids in url_map.items():
                logging.info(f"Checking URL for {len(user_ids)} users: {url}")
                # Скрапер сам розбереться, який це сайт (OLX/RIA/RST)
                new_ads = await run_scraper_task(url)
                
                for ad in new_ads:
                    if not await database.check_ad_exists(ad['id']):
                        await database.save_ad(ad['id'], ad['url'])
                        
                        # Розсилка користувачам
                        msg = (
                            f"⚡️ **Нова пропозиція!**\n\n"
                            f"🏷 {ad['title']}\n"
                            f"💵 **{ad['price']}**\n\n"
                            f"👉 [Відкрити оголошення]({ad['url']})"
                        )
                        for uid in user_ids:
                            try:
                                await bot.send_message(uid, msg, parse_mode="Markdown")
                            except Exception as e:
                                logging.warning(f"Failed to send to {uid}: {e}")
                
                # Пауза між запитами для різних URL
                await asyncio.sleep(5) 
                
            # Глобальна пауза циклу
            await asyncio.sleep(60)
            
        except Exception as e:
            logging.error(f"Monitoring Loop Error: {e}")
            await asyncio.sleep(60)

# --- Вебхук для Monobank ---
async def monobank_webhook_handler(request):
    try:
        data = await request.json()
        logging.info(f"Received webhook: {data}")
        
        if data.get('type') == 'StatementItem':
            item = data['data']['statementItem']
            amount = item['amount'] # копійки
            comment = item.get('comment', '')
            
            # Логіка верифікації (400 грн)
            if amount >= 40000: 
                words = comment.split()
                user_id = None
                for word in words:
                    if word.isdigit():
                        user_id = int(word)
                        break
                
                if user_id:
                    new_end = await database.extend_subscription(user_id, 30)
                    if new_end:
                        try:
                            await bot.send_message(user_id, "✅ Оплату отримано! Підписку продовжено на 30 днів.")
                        except:
                            pass
                        return web.Response(status=200)
        
        return web.Response(status=200)
    except Exception as e:
        logging.error(f"Webhook process error: {e}")
        return web.Response(status=500)

async def on_startup(app):
    await database.init_db()
    # Запускаємо моніторинг у фоні
    asyncio.create_task(monitoring_worker())
    
    # Встановлення вебхуку для Telegram
    await bot.set_webhook(config.WEBHOOK_URL)

def main():
    # Налаштування веб-сервера aiohttp
    app = web.Application()
    
    # Маршрут для Telegram
    webhook_requests_handler = SimpleRequestHandler(
        dispatcher=dp,
        bot=bot,
    )
    webhook_requests_handler.register(app, path=config.WEBHOOK_PATH)
    
    # Маршрут для Monobank
    app.router.add_post('/monobank_webhook', monobank_webhook_handler)
    
    setup_application(app, dp, bot=bot)
    app.on_startup.append(on_startup)
    
    web.run_app(app, host='0.0.0.0', port=config.PORT)

if __name__ == "__main__":
    main()
