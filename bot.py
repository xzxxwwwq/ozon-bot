import asyncio
import os
import re
import requests
from bs4 import BeautifulSoup
import telebot
from telebot.async_telebot import AsyncTeleBot

TOKEN = os.getenv("BOT_TOKEN")
PHONE = os.getenv("PHONE")

bot = AsyncTeleBot(TOKEN)

WAREHOUSE = "Софьино"
PROCESS = "Производство непрофиль"
CHECK_INTERVAL = 60
LAST_SHIFTS = set()
CHAT_ID = None
AUTH_CODE = None

def check_shifts():
    try:
        # Пробуем получить страницу смен (через сессию)
        session = requests.Session()
        
        # Сначала заходим на главную
        response = session.get("https://job.ozon.ru")
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Ищем склад
        warehouses = soup.find_all('div', class_='warehouse-item')
        for wh in warehouses:
            name = wh.find('div', class_='warehouse-name')
            if name and WAREHOUSE in name.text:
                # Получаем ID склада
                warehouse_id = wh.get('data-id')
                if warehouse_id:
                    # Запрашиваем список процессов для склада
                    process_url = f"https://job.ozon.ru/api/warehouse/{warehouse_id}/processes"
                    proc_response = session.get(process_url)
                    proc_data = proc_response.json()
                    
                    # Ищем нужный процесс
                    for proc in proc_data:
                        if PROCESS in proc.get('name', ''):
                            process_id = proc.get('id')
                            if process_id:
                                # Запрашиваем даты для процесса
                                shifts_url = f"https://job.ozon.ru/api/process/{process_id}/shifts"
                                shifts_response = session.get(shifts_url)
                                shifts_data = shifts_response.json()
                                
                                # Собираем доступные даты
                                available = []
                                for shift in shifts_data:
                                    if shift.get('available'):
                                        date = shift.get('date')
                                        if date:
                                            available.append(date)
                                
                                return available
        return []
    except Exception as e:
        print(f"Ошибка: {e}")
        return []

async def monitor_shifts():
    global LAST_SHIFTS, CHAT_ID
    while True:
        try:
            current_shifts = set(await asyncio.to_thread(check_shifts))
            if current_shifts:
                new_shifts = current_shifts - LAST_SHIFTS
                if new_shifts and CHAT_ID:
                    await bot.send_message(
                        CHAT_ID,
                        f"🔔 *НОВЫЕ СМЕНЫ!*\n\n📍 {WAREHOUSE}\n⚙️ {PROCESS}\n📅 " + "\n".join([f"• {d}" for d in new_shifts]),
                        parse_mode="Markdown"
                    )
                LAST_SHIFTS = current_shifts
        except Exception as e:
            print(f"Ошибка мониторинга: {e}")
        await asyncio.sleep(CHECK_INTERVAL)

@bot.message_handler(commands=['start'])
async def start(message):
    global CHAT_ID
    CHAT_ID = message.chat.id
    await bot.send_message(message.chat.id, "👋 Бот запущен! Буду присылать уведомления о сменах.")
    asyncio.create_task(monitor_shifts())

@bot.message_handler(commands=['auth'])
async def auth(message):
    global AUTH_CODE
    code = message.text.replace("/auth", "").strip()
    if code:
        AUTH_CODE = code
        await bot.send_message(message.chat.id, "✅ Код получен! Бот продолжит авторизацию.")
    else:
        await bot.send_message(message.chat.id, "❌ Отправь код так: /auth 123456")

@bot.message_handler(func=lambda message: True)
async def handle_code(message):
    global AUTH_CODE
    if message.text.isdigit() and len(message.text) >= 4:
        AUTH_CODE = message.text
        await bot.send_message(message.chat.id, "✅ Код получен! Бот продолжит авторизацию.")

async def main():
    print("🤖 Бот запущен!")
    await bot.polling()

if __name__ == "__main__":
    asyncio.run(main())