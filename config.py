import os
from dotenv import load_dotenv

# Завантаження змінних з локального.env файлу (для тестування)
load_dotenv()

# Основні налаштування
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = os.getenv("ADMIN_ID")

# Налаштування Monobank
MONO_TOKEN = os.getenv("MONO_TOKEN")  # X-Token з api.monobank.ua
MONO_JAR_ID = os.getenv("MONO_JAR_ID") # ID банки (довгий рядок)
MONO_JAR_LINK = os.getenv("MONO_JAR_LINK") # Посилання на банку для користувача

# Налаштування Webhook
WEBHOOK_HOST = os.getenv("RAILWAY_PUBLIC_DOMAIN", "") # Автоматично заповниться на Railway
WEBHOOK_PATH = f"/webhook/{BOT_TOKEN}"
WEBHOOK_URL = f"https://{WEBHOOK_HOST}{WEBHOOK_PATH}"

# Порт для запуску веб-сервера (надається Railway)
PORT = int(os.getenv("PORT", 8080))
