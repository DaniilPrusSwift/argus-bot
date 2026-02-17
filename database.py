import aiosqlite
import time
import logging

DB_NAME = "argus.db"

async def init_db():
    """Ініціалізація структури бази даних при першому запуску"""
    async with aiosqlite.connect(DB_NAME) as db:
        # Таблиця користувачів
        await db.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                join_date INTEGER,
                sub_end_date INTEGER,
                search_url TEXT,
                is_active INTEGER DEFAULT 1
            )
        ''')
        # Таблиця переглянутих оголошень (щоб не спамити)
        # Використовуємо індекс для швидкої перевірки наявності
        await db.execute('''
            CREATE TABLE IF NOT EXISTS seen_ads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ad_id TEXT UNIQUE,
                url TEXT,
                created_at INTEGER
            )
        ''')
        # Автоматичне очищення старих записів оголошень (старше 7 днів), щоб БД не розпухала
        await db.execute('CREATE INDEX IF NOT EXISTS idx_ad_id ON seen_ads(ad_id)')
        await db.commit()
        logging.info("Database initialized successfully.")

async def add_user(user_id: int, username: str):
    """Додавання нового користувача з пробним періодом 24 години"""
    current_time = int(time.time())
    trial_end = current_time + (24 * 3600) # +1 день
    
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute('''
            INSERT OR IGNORE INTO users (user_id, username, join_date, sub_end_date)
            VALUES (?,?,?,?)
        ''', (user_id, username, current_time, trial_end))
        await db.commit()

async def get_user_sub_status(user_id: int):
    """Перевірка статусу підписки"""
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute('SELECT sub_end_date, search_url FROM users WHERE user_id =?', (user_id,)) as cursor:
            row = await cursor.fetchone()
            if not row:
                return None
            
            sub_end, url = row
            is_active = sub_end > int(time.time())
            return {"is_active": is_active, "url": url, "sub_end": sub_end}

async def update_search_url(user_id: int, url: str):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute('UPDATE users SET search_url =? WHERE user_id =?', (url, user_id))
        await db.commit()

async def extend_subscription(user_id: int, days: int):
    """Продовження підписки"""
    seconds = days * 24 * 3600
    current_time = int(time.time())
    
    async with aiosqlite.connect(DB_NAME) as db:
        # Отримуємо поточну дату закінчення
        async with db.execute('SELECT sub_end_date FROM users WHERE user_id =?', (user_id,)) as cursor:
            row = await cursor.fetchone()
            if row:
                current_end = row
                # Якщо підписка активна, додаємо час до кінця. Якщо ні — до поточного часу.
                new_end = max(current_end, current_time) + seconds
                await db.execute('UPDATE users SET sub_end_date =? WHERE user_id =?', (new_end, user_id))
                await db.commit()
                return new_end
    return None

async def check_ad_exists(ad_id: str):
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute('SELECT 1 FROM seen_ads WHERE ad_id =?', (ad_id,)) as cursor:
            return await cursor.fetchone() is not None

async def save_ad(ad_id: str, url: str):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute('INSERT OR IGNORE INTO seen_ads (ad_id, url, created_at) VALUES (?,?,?)', 
                         (ad_id, url, int(time.time())))
        await db.commit()

async def get_all_monitoring_tasks():
    """Отримує список всіх користувачів з активною підпискою та встановленим URL"""
    current_time = int(time.time())
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute('''
            SELECT user_id, search_url 
            FROM users 
            WHERE sub_end_date >? AND search_url IS NOT NULL
        ''', (current_time,)) as cursor:
            return await cursor.fetchall()
