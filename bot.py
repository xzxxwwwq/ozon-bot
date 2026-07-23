import asyncio
import os
import requests
from bs4 import BeautifulSoup
import telebot
from telebot.async_telebot import AsyncTeleBot
from telebot.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from datetime import datetime

TOKEN = os.getenv("BOT_TOKEN")
PHONE = os.getenv("PHONE")
OZON_TOKEN = os.getenv("OZON_TOKEN")

bot = AsyncTeleBot(TOKEN)

# ===== НАСТРОЙКИ =====
USER_SETTINGS = {
    "warehouse": "Софьино",
    "process": "Производство непрофиль",
    "monitoring_active": True
}

# Полный список процессов (все, что ты показал)
ALL_PROCESSES = [
    "Сортировка крупного товара",
    "Сортировка мелкого товара",
    "Размещение",
    "Подбор",
    "Приемка",
    "Упаковка",
    "Возвраты",
    "Консолидация",
    "Обработка проблемного товара",
    "Производство непрофиль",
    "Сортировка непрофиль",
    "Погрузка и разгрузка",
    "Подбор возвратов",
    "Инвентаризация"
]

CHECK_INTERVAL = 60
LAST_SHIFTS = set()
CHAT_ID = None

STATS = {"total_shifts": 0, "last_check": None}

# ===== ФУНКЦИЯ ПРОВЕРКИ СМЕН =====
def check_shifts():
    try:
        session = requests.Session()
        response = session.get("https://job.ozon.ru")
        soup = BeautifulSoup(response.text, 'html.parser')
        
        warehouse = USER_SETTINGS["warehouse"]
        process = USER_SETTINGS["process"]
        
        warehouses = soup.find_all('div', class_='warehouse-item')
        for wh in warehouses:
            name = wh.find('div', class_='warehouse-name')
            if name and warehouse in name.text:
                warehouse_id = wh.get('data-id')
                if warehouse_id:
                    process_url = f"https://job.ozon.ru/api/warehouse/{warehouse_id}/processes"
                    proc_response = session.get(process_url)
                    proc_data = proc_response.json()
                    
                    for proc in proc_data:
                        if process in proc.get('name', ''):
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
        print(f"Ошибка: {e}")
        return []

# ===== КЛАВИАТУРА =====
def get_main_keyboard():
    markup = ReplyKeyboardMarkup(resize_keyboard=True)
    btn1 = KeyboardButton("👤 Профиль")
    btn2 = KeyboardButton("📊 Статус")
    btn3 = KeyboardButton("⭐ Рейтинг")
    btn4 = KeyboardButton("⚙️ Настройки")
    btn5 = KeyboardButton("🔄 Обновить")
    markup.row(btn1, btn2)
    markup.row(btn3, btn4)
    markup.row(btn5)
    return markup

def get_profile_text(message):
    user = message.from_user
    now = datetime.now().strftime("%H:%M:%S")
    return (
        f"👤 Профиль\n\n"
        f"• Имя: {user.first_name}\n"
        f"• ID: {user.id}\n"
        f"• Склад: {USER_SETTINGS['warehouse']}\n"
        f"• Процесс: {USER_SETTINGS['process']}\n"
        f"• Мониторинг: {'✅ Активен' if USER_SETTINGS['monitoring_active'] else '❌ Отключен'}\n"
        f"• Найдено смен: {STATS['total_shifts']}\n"
        f"• Время: {now}"
    )

# ===== РЕЙТИНГ =====
def get_rating():
    try:
        if not OZON_TOKEN:
            return None
        headers = {
            'Cookie': f'__Secure-refresh-token={OZON_TOKEN}',
            'User-Agent': 'Mozilla/5.0'
        }
        response = requests.get("https://job.ozon.ru/profile/rating", headers=headers)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        level = soup.find('h1') or soup.find('div', class_='rating-level')
        level_text = level.text.strip() if level else "Не найден"
        
        points = soup.find('div', class_='rating-points')
        points_text = points.text.strip() if points else "Не найдены"
        
        return {'level': level_text, 'points': points_text}
    except Exception as e:
        print(f"Ошибка рейтинга: {e}")
        return None

# ===== МОНИТОРИНГ =====
async def monitor_shifts():
    global LAST_SHIFTS, CHAT_ID
    while True:
        try:
            current_shifts = set(await asyncio.to_thread(check_shifts))
            if current_shifts:
                STATS['total_shifts'] += len(current_shifts)
                new_shifts = current_shifts - LAST_SHIFTS
                if new_shifts and CHAT_ID and USER_SETTINGS['monitoring_active']:
                    await bot.send_message(
                        CHAT_ID,
                        f"🔔 НОВЫЕ СМЕНЫ!\n📍 {USER_SETTINGS['warehouse']}\n⚙️ {USER_SETTINGS['process']}\n📅 " + "\n".join([f"• {d}" for d in new_shifts])
                    )
                LAST_SHIFTS = current_shifts
            STATS['last_check'] = datetime.now().strftime("%H:%M:%S")
        except Exception as e:
            print(f"Ошибка мониторинга: {e}")
        await asyncio.sleep(CHECK_INTERVAL)

# ===== КОМАНДЫ =====
@bot.message_handler(commands=['start'])
async def start(message):
    global CHAT_ID
    CHAT_ID = message.chat.id
    await bot.send_message(
        message.chat.id,
        f"👋 Привет, {message.from_user.first_name}!\n📍 Слежу за сменами: {USER_SETTINGS['warehouse']} → {USER_SETTINGS['process']}",
        reply_markup=get_main_keyboard()
    )
    asyncio.create_task(monitor_shifts())

@bot.message_handler(func=lambda message: message.text == "👤 Профиль")
async def profile(message):
    await bot.send_message(message.chat.id, get_profile_text(message), reply_markup=get_main_keyboard())

@bot.message_handler(func=lambda message: message.text == "📊 Статус")
async def status_command(message):
    await bot.send_message(message.chat.id, "🔍 Проверяю наличие смен...", reply_markup=get_main_keyboard())
    shifts = await asyncio.to_thread(check_shifts)
    if shifts:
        await bot.send_message(
            message.chat.id,
            f"✅ Доступные смены:\n" + "\n".join([f"• {d}" for d in shifts]),
            reply_markup=get_main_keyboard()
        )
    else:
        await bot.send_message(message.chat.id, "📭 Смен сейчас нет", reply_markup=get_main_keyboard())

@bot.message_handler(func=lambda message: message.text == "⭐ Рейтинг")
async def rating_command(message):
    await bot.send_message(message.chat.id, "🔍 Загружаю рейтинг...", reply_markup=get_main_keyboard())
    if not OZON_TOKEN:
        await bot.send_message(message.chat.id, "❌ Токен Ozon не найден.", reply_markup=get_main_keyboard())
        return
    rating = await asyncio.to_thread(get_rating)
    if rating:
        await bot.send_message(
            message.chat.id,
            f"⭐ Рейтинг\n\n• Уровень: {rating['level']}\n• Баллы: {rating['points']}",
            reply_markup=get_main_keyboard()
        )
    else:
        await bot.send_message(message.chat.id, "❌ Не удалось получить рейтинг.", reply_markup=get_main_keyboard())

@bot.message_handler(func=lambda message: message.text == "⚙️ Настройки")
async def settings(message):
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("📍 Выбрать склад", callback_data="choose_warehouse"))
    markup.add(InlineKeyboardButton("⚙️ Выбрать процесс", callback_data="choose_process"))
    markup.add(InlineKeyboardButton(
        "🔔 Вкл/Выкл уведомления", 
        callback_data="toggle_monitoring"
    ))
    await bot.send_message(
        message.chat.id,
        f"⚙️ Настройки\n\n📍 Склад: {USER_SETTINGS['warehouse']}\n⚙️ Процесс: {USER_SETTINGS['process']}\n🔔 Уведомления: {'✅ Вкл' if USER_SETTINGS['monitoring_active'] else '❌ Выкл'}",
        reply_markup=markup
    )

@bot.message_handler(func=lambda message: message.text == "🔄 Обновить")
async def refresh(message):
    await bot.send_message(message.chat.id, "🔄 Обновляю...", reply_markup=get_main_keyboard())
    STATS['last_check'] = datetime.now().strftime("%H:%M:%S")
    await bot.send_message(message.chat.id, "✅ Готово!", reply_markup=get_main_keyboard())

# ===== ОБРАБОТКА КНОПОК НАСТРОЕК =====
@bot.callback_query_handler(func=lambda call: True)
async def callback_handler(call):
    if call.data == "toggle_monitoring":
        USER_SETTINGS['monitoring_active'] = not USER_SETTINGS['monitoring_active']
        status = "включен" if USER_SETTINGS['monitoring_active'] else "выключен"
        await bot.answer_callback_query(call.id, f"Мониторинг {status} ✅")
        await bot.edit_message_text(
            f"⚙️ Мониторинг {status}",
            call.message.chat.id,
            call.message.message_id
        )
    
    elif call.data == "choose_warehouse":
        # Просто показываем доступные склады (их немного)
        markup = InlineKeyboardMarkup()
        warehouses = ["Софьино", "Томилино", "Подольск", "Коледино"]
        for wh in warehouses:
            markup.add(InlineKeyboardButton(wh, callback_data=f"warehouse_{wh}"))
        await bot.edit_message_text(
            "📍 Выбери склад:",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=markup
        )
    
    elif call.data.startswith("warehouse_"):
        warehouse_name = call.data.replace("warehouse_", "")
        USER_SETTINGS['warehouse'] = warehouse_name
        
        # Показываем все процессы для выбранного склада
        markup = InlineKeyboardMarkup()
        for proc in ALL_PROCESSES:
            markup.add(InlineKeyboardButton(proc, callback_data=f"process_{proc}"))
        
        await bot.edit_message_text(
            f"✅ Склад: {warehouse_name}\n\nВыбери процесс:",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=markup
        )
    
    elif call.data.startswith("process_"):
        process_name = call.data.replace("process_", "")
        USER_SETTINGS['process'] = process_name
        
        await bot.edit_message_text(
            f"✅ Настройки обновлены!\n\n📍 Склад: {USER_SETTINGS['warehouse']}\n⚙️ Процесс: {USER_SETTINGS['process']}",
            call.message.chat.id,
            call.message.message_id
        )
        await bot.send_message(
            call.message.chat.id,
            "✅ Готово! Я продолжаю следить за сменами.",
            reply_markup=get_main_keyboard()
        )
    
    elif call.data == "choose_process":
        markup = InlineKeyboardMarkup()
        for proc in ALL_PROCESSES:
            markup.add(InlineKeyboardButton(proc, callback_data=f"process_{proc}"))
        await bot.edit_message_text(
            f"📍 Текущий склад: {USER_SETTINGS['warehouse']}\n\nВыбери процесс:",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=markup
        )

async def main():
    print("🤖 Бот запущен!")
    await bot.polling()

if __name__ == "__main__":
    asyncio.run(main())