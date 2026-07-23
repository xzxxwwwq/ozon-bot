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
    "processes": ["Производство непрофиль"],
    "monitoring_active": True
}

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
LAST_SHIFTS = {}
CHAT_ID = None
STATS = {"total_shifts": 0, "last_check": None}

# ===== ФУНКЦИЯ ПОЛУЧЕНИЯ ВСЕХ СМЕН =====
def get_all_shifts():
    """Получает все доступные смены на складе"""
    try:
        session = requests.Session()
        response = session.get("https://job.ozon.ru")
        soup = BeautifulSoup(response.text, 'html.parser')
        
        warehouse = USER_SETTINGS["warehouse"]
        result = {}
        
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
                        proc_name = proc.get('name', '')
                        process_id = proc.get('id')
                        if process_id:
                            shifts_url = f"https://job.ozon.ru/api/process/{process_id}/shifts"
                            shifts_response = session.get(shifts_url)
                            shifts_data = shifts_response.json()
                            
                            available = []
                            for shift in shifts_data:
                                if shift.get('available'):
                                    date = shift.get('date', '')
                                    time_start = shift.get('time_start', '')
                                    time_end = shift.get('time_end', '')
                                    rate = shift.get('rate', '')
                                    available.append({
                                        'date': date,
                                        'time_start': time_start,
                                        'time_end': time_end,
                                        'rate': rate
                                    })
                            if available:
                                result[proc_name] = available
                    break
        return result
    except Exception as e:
        print(f"Ошибка получения смен: {e}")
        return {}

def check_monitored_shifts():
    """Проверяет смены только для отслеживаемых процессов"""
    all_shifts = get_all_shifts()
    monitored = {}
    for process in USER_SETTINGS['processes']:
        if process in all_shifts:
            monitored[process] = all_shifts[process]
    return monitored

# ===== КЛАВИАТУРА =====
def get_main_keyboard():
    markup = ReplyKeyboardMarkup(resize_keyboard=True)
    btn1 = KeyboardButton("👤 Профиль")
    btn2 = KeyboardButton("📊 Статус")
    btn3 = KeyboardButton("📋 Все смены")
    btn4 = KeyboardButton("⭐ Рейтинг")
    btn5 = KeyboardButton("⚙️ Настройки")
    btn6 = KeyboardButton("🔄 Обновить")
    markup.row(btn1, btn2)
    markup.row(btn3, btn4)
    markup.row(btn5, btn6)
    return markup

def get_profile_text(message):
    user = message.from_user
    now = datetime.now().strftime("%H:%M:%S")
    processes = "\n  ".join(USER_SETTINGS['processes']) if USER_SETTINGS['processes'] else "Нет"
    return (
        f"👤 Профиль\n\n"
        f"• Имя: {user.first_name}\n"
        f"• ID: {user.id}\n"
        f"• Склад: {USER_SETTINGS['warehouse']}\n"
        f"• Процессы: {len(USER_SETTINGS['processes'])}\n"
        f"  {processes}\n"
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
    global LAST_SHIFTS, CHAT_ID, STATS
    while True:
        try:
            all_shifts = await asyncio.to_thread(check_monitored_shifts)
            
            if all_shifts:
                for process, shifts in all_shifts.items():
                    current_dates = {s['date'] for s in shifts}
                    old_dates = LAST_SHIFTS.get(process, set())
                    new_dates = current_dates - old_dates
                    
                    if new_dates and CHAT_ID and USER_SETTINGS['monitoring_active']:
                        STATS['total_shifts'] += len(new_dates)
                        shift_text = ""
                        for shift in shifts:
                            if shift['date'] in new_dates:
                                time_str = f"{shift['time_start']} - {shift['time_end']}" if shift['time_start'] else "Время уточняется"
                                shift_text += f"  • 📅 {shift['date']} | ⏰ {time_str}\n"
                        
                        if shift_text:
                            await bot.send_message(
                                CHAT_ID,
                                f"🔔 *НОВАЯ СМЕНА!*\n\n"
                                f"📍 Склад: {USER_SETTINGS['warehouse']}\n"
                                f"⚙️ Процесс: {process}\n"
                                f"{shift_text}\n"
                                f"🏃‍♂️ Бери скорее!",
                                parse_mode="Markdown"
                            )
                    
                    LAST_SHIFTS[process] = current_dates
            
            STATS['last_check'] = datetime.now().strftime("%H:%M:%S")
            
        except Exception as e:
            print(f"Ошибка мониторинга: {e}")
        
        await asyncio.sleep(CHECK_INTERVAL)

# ===== КОМАНДЫ =====
@bot.message_handler(commands=['start'])
async def start(message):
    global CHAT_ID
    CHAT_ID = message.chat.id
    processes = ", ".join(USER_SETTINGS['processes'])
    await bot.send_message(
        message.chat.id,
        f"👋 Привет, {message.from_user.first_name}!\n\n"
        f"📍 Слежу за сменами:\n"
        f"• Склад: {USER_SETTINGS['warehouse']}\n"
        f"• Процессы: {processes}\n\n"
        f"📌 Используй кнопки ниже",
        reply_markup=get_main_keyboard()
    )
    asyncio.create_task(monitor_shifts())

@bot.message_handler(func=lambda message: message.text == "👤 Профиль")
async def profile(message):
    await bot.send_message(message.chat.id, get_profile_text(message), reply_markup=get_main_keyboard())

@bot.message_handler(func=lambda message: message.text == "📊 Статус")
async def status_command(message):
    await bot.send_message(message.chat.id, "🔍 Проверяю отслеживаемые смены...", reply_markup=get_main_keyboard())
    all_shifts = await asyncio.to_thread(check_monitored_shifts)
    
    if all_shifts:
        text = "✅ *Отслеживаемые смены:*\n\n"
        for process, shifts in all_shifts.items():
            text += f"⚙️ *{process}*\n"
            for shift in shifts:
                time_str = f"{shift['time_start']} - {shift['time_end']}" if shift['time_start'] else "Время уточняется"
                text += f"  • 📅 {shift['date']} | ⏰ {time_str}\n"
            text += "\n"
        await bot.send_message(message.chat.id, text, parse_mode="Markdown", reply_markup=get_main_keyboard())
    else:
        await bot.send_message(message.chat.id, "📭 Нет смен по отслеживаемым процессам", reply_markup=get_main_keyboard())

@bot.message_handler(func=lambda message: message.text == "📋 Все смены")
async def all_shifts_command(message):
    await bot.send_message(message.chat.id, "🔍 Загружаю все доступные смены...", reply_markup=get_main_keyboard())
    all_shifts = await asyncio.to_thread(get_all_shifts)
    
    if all_shifts:
        text = f"📋 *Все доступные смены*\n📍 {USER_SETTINGS['warehouse']}\n\n"
        for process, shifts in all_shifts.items():
            # Отмечаем, отслеживается ли процесс
            is_monitored = process in USER_SETTINGS['processes']
            mark = "✅ " if is_monitored else "   "
            text += f"{mark}⚙️ *{process}*"
            if is_monitored:
                text += " (отслеживается)"
            text += "\n"
            for shift in shifts:
                time_str = f"{shift['time_start']} - {shift['time_end']}" if shift['time_start'] else "Время уточняется"
                text += f"  • 📅 {shift['date']} | ⏰ {time_str}\n"
            text += "\n"
        await bot.send_message(message.chat.id, text, parse_mode="Markdown", reply_markup=get_main_keyboard())
    else:
        await bot.send_message(message.chat.id, "📭 Нет доступных смен на складе", reply_markup=get_main_keyboard())

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
    markup.add(InlineKeyboardButton("➕ Добавить процесс", callback_data="add_process"))
    markup.add(InlineKeyboardButton("➖ Удалить процесс", callback_data="remove_process"))
    markup.add(InlineKeyboardButton("🔔 Вкл/Выкл уведомления", callback_data="toggle_monitoring"))
    
    processes = "\n  ".join(USER_SETTINGS['processes']) if USER_SETTINGS['processes'] else "❌ Нет"
    await bot.send_message(
        message.chat.id,
        f"⚙️ *Настройки*\n\n"
        f"📍 Склад: {USER_SETTINGS['warehouse']}\n"
        f"📋 Процессы:\n  {processes}\n"
        f"🔔 Уведомления: {'✅ Вкл' if USER_SETTINGS['monitoring_active'] else '❌ Выкл'}",
        parse_mode="Markdown",
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
        await bot.edit_message_text(
            f"✅ Склад изменён на: {warehouse_name}",
            call.message.chat.id,
            call.message.message_id
        )
        await bot.send_message(
            call.message.chat.id,
            "✅ Готово!",
            reply_markup=get_main_keyboard()
        )
    
    elif call.data == "add_process":
        markup = InlineKeyboardMarkup()
        for proc in ALL_PROCESSES:
            if proc not in USER_SETTINGS['processes']:
                markup.add(InlineKeyboardButton(proc, callback_data=f"addproc_{proc}"))
        if not markup.keyboard:
            await bot.answer_callback_query(call.id, "Все процессы уже добавлены!")
            return
        await bot.edit_message_text(
            "➕ Выбери процесс для добавления:",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=markup
        )
    
    elif call.data.startswith("addproc_"):
        process = call.data.replace("addproc_", "")
        if process not in USER_SETTINGS['processes']:
            USER_SETTINGS['processes'].append(process)
        await bot.answer_callback_query(call.id, f"✅ {process} добавлен!")
        await bot.edit_message_text(
            f"✅ Процесс '{process}' добавлен!",
            call.message.chat.id,
            call.message.message_id
        )
        await settings(call.message)
    
    elif call.data == "remove_process":
        if not USER_SETTINGS['processes']:
            await bot.answer_callback_query(call.id, "Нет процессов для удаления!")
            return
        markup = InlineKeyboardMarkup()
        for proc in USER_SETTINGS['processes']:
            markup.add(InlineKeyboardButton(f"❌ {proc}", callback_data=f"removeproc_{proc}"))
        await bot.edit_message_text(
            "➖ Выбери процесс для удаления:",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=markup
        )
    
    elif call.data.startswith("removeproc_"):
        process = call.data.replace("removeproc_", "")
        if process in USER_SETTINGS['processes']:
            USER_SETTINGS['processes'].remove(process)
        await bot.answer_callback_query(call.id, f"❌ {process} удалён!")
        await bot.edit_message_text(
            f"❌ Процесс '{process}' удалён!",
            call.message.chat.id,
            call.message.message_id
        )
        await settings(call.message)

async def main():
    print("🤖 Бот запущен!")
    await bot.polling()

if __name__ == "__main__":
    asyncio.run(main())