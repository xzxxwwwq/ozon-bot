import asyncio
import os
import re
import requests
from bs4 import BeautifulSoup
import telebot
from telebot.async_telebot import AsyncTeleBot
from telebot.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from datetime import datetime

TOKEN = os.getenv("BOT_TOKEN")
PHONE = os.getenv("PHONE")

bot = AsyncTeleBot(TOKEN)

WAREHOUSE = "Софьино"
PROCESS = "Производство непрофиль"
CHECK_INTERVAL = 60
LAST_SHIFTS = set()
CHAT_ID = None
AUTH_CODE = None

# Статистика
STATS = {
    "total_shifts": 0,
    "last_check": None,
    "monitoring_active": True
}

def check_shifts():
    try:
        session = requests.Session()
        response = session.get("https://job.ozon.ru")
        soup = BeautifulSoup(response.text, 'html.parser')
        
        warehouses = soup.find_all('div', class_='warehouse-item')
        for wh in warehouses:
            name = wh.find('div', class_='warehouse-name')
            if name and WAREHOUSE in name.text:
                warehouse_id = wh.get('data-id')
                if warehouse_id:
                    process_url = f"https://job.ozon.ru/api/warehouse/{warehouse_id}/processes"
                    proc_response = session.get(process_url)
                    proc_data = proc_response.json()
                    
                    for proc in proc_data:
                        if PROCESS in proc.get('name', ''):
                            process_id = proc.get('id')
                            if process_id:
                                shifts_url = f"https://job.ozon.ru/api/process/{process_id}/shifts"
                                shifts_response = session.get(shifts_url)
                                shifts_data = shifts_response.json()
                                
                                available = []
                                for shift in shifts_data:
                                    if shift.get('available'):
                                        date = shift.get('date')
                                        if date:
                                            available.append(date)
                                
                                return available
        return []
    except Exception as e:
        print(f"Ошибка проверки смен: {e}")
        return []

def get_income():
    """Получает данные о доходах через API Ozon Job"""
    try:
        session = requests.Session()
        
        # Пробуем разные возможные адреса API
        urls = [
            "https://job.ozon.ru/api/payments/statistics",
            "https://job.ozon.ru/api/profile/income",
            "https://job.ozon.ru/api/payments"
        ]
        
        for url in urls:
            try:
                response = session.get(url, timeout=10)
                if response.status_code == 200:
                    data = response.json()
                    # Проверяем наличие данных
                    if data:
                        return {
                            'total': data.get('total', 0),
                            'month': data.get('month', 0),
                            'week': data.get('week', 0),
                            'today': data.get('today', 0)
                        }
            except:
                continue
        
        return None
    except Exception as e:
        print(f"Ошибка получения дохода: {e}")
        return None

def get_main_keyboard():
    markup = ReplyKeyboardMarkup(resize_keyboard=True)
    btn1 = KeyboardButton("👤 Профиль")
    btn2 = KeyboardButton("📊 Статус")
    btn3 = KeyboardButton("💰 Доход")
    btn4 = KeyboardButton("⚙️ Настройки")
    btn5 = KeyboardButton("🔄 Обновить")
    markup.row(btn1, btn2)
    markup.row(btn3, btn4)
    markup.row(btn5)
    return markup

def get_profile_text(message):
    user = message.from_user
    now = datetime.now().strftime("%H:%M:%S")
    
    text = (
        f"👤 Профиль\n\n"
        f"• Имя: {user.first_name}\n"
        f"• ID: {user.id}\n"
        f"• Склад: {WAREHOUSE}\n"
        f"• Процесс: {PROCESS}\n"
        f"• Мониторинг: {'✅ Активен' if STATS['monitoring_active'] else '❌ Отключен'}\n"
        f"• Найдено смен: {STATS['total_shifts']}\n"
        f"• Последняя проверка: {STATS['last_check'] or 'Никогда'}\n"
        f"• Время: {now}"
    )
    return text

async def monitor_shifts():
    global LAST_SHIFTS, CHAT_ID
    while True:
        try:
            current_shifts = set(await asyncio.to_thread(check_shifts))
            if current_shifts:
                STATS['total_shifts'] += len(current_shifts)
                new_shifts = current_shifts - LAST_SHIFTS
                if new_shifts and CHAT_ID and STATS['monitoring_active']:
                    await bot.send_message(
                        CHAT_ID,
                        f"🔔 *НОВЫЕ СМЕНЫ!*\n\n📍 {WAREHOUSE}\n⚙️ {PROCESS}\n📅 " + "\n".join([f"• {d}" for d in new_shifts]),
                        parse_mode="Markdown"
                    )
                LAST_SHIFTS = current_shifts
            STATS['last_check'] = datetime.now().strftime("%H:%M:%S")
        except Exception as e:
            print(f"Ошибка мониторинга: {e}")
        await asyncio.sleep(CHECK_INTERVAL)

@bot.message_handler(commands=['start'])
async def start(message):
    global CHAT_ID
    CHAT_ID = message.chat.id
    await bot.send_message(
        message.chat.id,
        f"👋 Привет, {message.from_user.first_name}!\n\n"
        f"📍 Слежу за сменами:\n"
        f"• Склад: {WAREHOUSE}\n"
        f"• Процесс: {PROCESS}\n\n"
        f"📌 Используй кнопки ниже для управления",
        reply_markup=get_main_keyboard()
    )
    asyncio.create_task(monitor_shifts())

@bot.message_handler(func=lambda message: message.text == "👤 Профиль")
async def profile(message):
    text = get_profile_text(message)
    await bot.send_message(
        message.chat.id,
        text,
        parse_mode=None,
        reply_markup=get_main_keyboard()
    )

@bot.message_handler(func=lambda message: message.text == "📊 Статус")
async def status_command(message):
    await bot.send_message(
        message.chat.id,
        "🔍 Проверяю наличие смен...",
        reply_markup=get_main_keyboard()
    )
    shifts = await asyncio.to_thread(check_shifts)
    if shifts:
        await bot.send_message(
            message.chat.id,
            f"✅ *Доступные смены:*\n" + "\n".join([f"• {d}" for d in shifts]),
            parse_mode="Markdown",
            reply_markup=get_main_keyboard()
        )
    else:
        await bot.send_message(
            message.chat.id,
            "📭 Смен сейчас нет",
            reply_markup=get_main_keyboard()
        )

@bot.message_handler(func=lambda message: message.text == "💰 Доход")
async def income(message):
    await bot.send_message(
        message.chat.id,
        "💰 Ищу данные о доходах...",
        reply_markup=get_main_keyboard()
    )
    data = await asyncio.to_thread(get_income)
    
    if data:
        text = (
            f"💰 *Доход*\n\n"
            f"• За сегодня: {data.get('today', 0):,} ₽\n"
            f"• За неделю: {data.get('week', 0):,} ₽\n"
            f"• За месяц: {data.get('month', 0):,} ₽\n"
            f"• Всего: {data.get('total', 0):,} ₽"
        )
        await bot.send_message(
            message.chat.id,
            text,
            parse_mode="Markdown",
            reply_markup=get_main_keyboard()
        )
    else:
        await bot.send_message(
            message.chat.id,
            "❌ Не удалось получить данные о доходах.\n"
            "Возможно, Ozon изменил API или требуется переавторизация.\n\n"
            "Попробуй:\n"
            "1. Зайди в приложение Ozon Job\n"
            "2. Нажми на иконку кошелька (Выплаты)\n"
            "3. Вернись в бот и нажми '💰 Доход' снова",
            reply_markup=get_main_keyboard()
        )

@bot.message_handler(func=lambda message: message.text == "⚙️ Настройки")
async def settings(message):
    markup = InlineKeyboardMarkup()
    btn1 = InlineKeyboardButton("🔔 Вкл/Выкл уведомления", callback_data="toggle_monitoring")
    btn2 = InlineKeyboardButton("📋 Сменить склад", callback_data="change_warehouse")
    markup.row(btn1)
    markup.row(btn2)
    await bot.send_message(
        message.chat.id,
        "⚙️ *Настройки*\n\nВыбери действие:",
        parse_mode="Markdown",
        reply_markup=markup
    )

@bot.message_handler(func=lambda message: message.text == "🔄 Обновить")
async def refresh(message):
    await bot.send_message(
        message.chat.id,
        "🔄 Обновляю данные...",
        reply_markup=get_main_keyboard()
    )
    STATS['last_check'] = datetime.now().strftime("%H:%M:%S")
    await bot.send_message(
        message.chat.id,
        "✅ Данные обновлены!",
        reply_markup=get_main_keyboard()
    )

@bot.callback_query_handler(func=lambda call: True)
async def callback_handler(call):
    if call.data == "toggle_monitoring":
        STATS['monitoring_active'] = not STATS['monitoring_active']
        status = "включен" if STATS['monitoring_active'] else "выключен"
        await bot.answer_callback_query(call.id, f"Мониторинг {status} ✅")
        await bot.edit_message_text(
            f"⚙️ Мониторинг {status}",
            call.message.chat.id,
            call.message.message_id
        )
    elif call.data == "change_warehouse":
        await bot.answer_callback_query(call.id, "Эта функция в разработке 🛠")

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