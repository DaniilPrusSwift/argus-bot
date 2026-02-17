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
        "Я — Argus, система автоматичного моніторингу OLX.\n"
        "Я буду надсилати нові оголошення за твоїм запитом миттєво.\n\n"
        "Тобі надано **24 години** тестового доступу.",
        reply_markup=get_main_keyboard(True)
    )

@dp.callback_query(F.data == "set_link")
async def ask_link(callback: types.CallbackQuery):
    await callback.message.answer(
        "Надішліть мені посилання на пошук OLX з вже обраними фільтрами.\n\n"
        "Приклад:\n`https://www.olx.ua/uk/elektronika/telefony/?search%5Bfilter_float_price%3Afrom%5D=5000`"
    , parse_mode="Markdown")
    await callback.answer()

@dp.message(F.text.contains("olx.ua"))
async def save_link(message: types.Message):
    # Валідація посилання (базова)
    if "http" not in message.text:
        await message.answer("Будь ласка, надішліть коректне посилання.")
        return
        
    await database.update_search_url(message.from_user.id, message.text.strip())
    await message.answer("✅ Посилання збережено! Моніторинг розпочато.", reply_markup=get_main_keyboard(True))

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

@dp.callback_query(F.data == "profile")
async def show_profile(callback: types.CallbackQuery):
    status = await database.get_user_sub_status(callback.from_user.id)
    if not status:
        await callback.answer("Помилка профілю")
        return
        
    end_date = datetime.fromtimestamp(status['sub_end_date']).strftime('%Y-%m-%d %H:%M')
    state = "Активна ✅" if status['is_active'] else "Неактивна ❌"
    url = status['url'] if status['url'] else "Не встановлено"
    
    msg = (
        f"🆔 ID: `{callback.from_user.id}`\n"
        f"Статус: {state}\n"
        f"Закінчується: {end_date}\n"
        f"Посилання: {url}"
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
                
                # Пауза між запитами для різних URL, щоб не перевантажити сервер
                await asyncio.sleep(5) 
                
            # Глобальна пауза циклу (наприклад, раз на хвилину)
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
            
            # Логіка верифікації
            if amount >= 40000: # 400.00 грн
                # Шукаємо ID користувача в коментарі
                # Простий пошук числа в рядку
                words = comment.split()
                user_id = None
                for word in words:
                    if word.isdigit():
                        user_id = int(word)
                        break
                
                if user_id:
                    new_end = await database.extend_subscription(user_id, 30)
                    if new_end:
                        await bot.send_message(user_id, "✅ Оплату отримано! Підписку продовжено на 30 днів.")
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
    
    # Маршрут для Telegram (вбудований в aiogram)
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
