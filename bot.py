import asyncio
import os
import requests
from bs4 import BeautifulSoup
import telebot
from telebot.async_telebot import AsyncTeleBot
from telebot.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from datetime import datetime
import json

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

# ===== ПЕРЕМЕННЫЕ ДЛЯ АВТОРИЗАЦИИ =====
auth_step = None
user_phone = None
auth_session = None

# ===== ЗАГОЛОВКИ ДЛЯ ЗАПРОСОВ (чтобы не было 403) =====
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
    "Origin": "https://job.ozon.ru",
    "Referer": "https://job.ozon.ru/"
}

# ===== ФУНКЦИЯ ДЛЯ РАБОТЫ С КУКАМИ =====
def save_cookies(cookies):
    try:
        with open('cookies.json', 'w') as f:
            json.dump(cookies, f)
        print("✅ Куки сохранены")
    except Exception as e:
        print(f"Ошибка сохранения кук: {e}")

def load_cookies():
    try:
        with open('cookies.json', 'r') as f:
            return json.load(f)
    except:
        return None

def get_session():
    session = requests.Session()
    cookies = load_cookies()
    if cookies:
        for name, value in cookies.items():
            session.cookies.set(name, value)
    if OZON_TOKEN:
        session.cookies.set('__Secure-refresh-token', OZON_TOKEN)
        session.cookies.set('__Secure-auth-token', OZON_TOKEN)
    return session

# ===== ФУНКЦИЯ ПОЛУЧЕНИЯ СМЕН =====
def get_all_shifts():
    try:
        session = get_session()
        response = session.get("https://job.ozon.ru", headers=HEADERS)
        
        if response.status_code != 200:
            print(f"Ошибка: статус {response.status_code}")
            return {}
        
        soup = BeautifulSoup(response.text, 'html.parser')
        warehouse = USER_SETTINGS["warehouse"]
        result = {}
        
        warehouses = soup.find_all('div', class_='warehouse-item')
        for wh in warehouses:
            name_elem = wh.find('div', class_='warehouse-name')
            if name_elem and warehouse in name_elem.text:
                warehouse_id = wh.get('data-id')
                if warehouse_id:
                    process_url = f"https://job.ozon.ru/api/warehouse/{warehouse_id}/processes"
                    proc_response = session.get(process_url, headers=HEADERS)
                    if proc_response.status_code == 200:
                        proc_data = proc_response.json()
                        for proc in proc_data:
                            proc_name = proc.get('name', '')
                            process_id = proc.get('id')
                            if process_id:
                                shifts_url = f"https://job.ozon.ru/api/process/{process_id}/shifts"
                                shifts_response = session.get(shifts_url, headers=HEADERS)
                                if shifts_response.status_code == 200:
                                    shifts_data = shifts_response.json()
                                    available = []
                                    for shift in shifts_data:
                                        if shift.get('available'):
                                            available.append({
                                                'date': shift.get('date', ''),
                                                'time_start': shift.get('time_start', ''),
                                                'time_end': shift.get('time_end', ''),
                                                'rate': shift.get('rate', '')
                                            })
                                    if available:
                                        result[proc_name] = available
                    break
        return result
    except Exception as e:
        print(f"Ошибка получения смен: {e}")
        return {}

def check_monitored_shifts():
    all_shifts = get_all_shifts()
    monitored = {}
    for process in USER_SETTINGS['processes']:
        if process in all_shifts:
            monitored[process] = all_shifts[process]
    return monitored

# ===== РЕЙТИНГ =====
def get_rating():
    try:
        session = get_session()
        response = session.get("https://job.ozon.ru/profile/rating", headers=HEADERS)
        if response.status_code != 200:
            return None
        soup = BeautifulSoup(response.text, 'html.parser')
        level = soup.find('h1')
        level_text = level.text.strip() if level else "Не найден"
        points = soup.find('div', class_='rating-points')
        points_text = points.text.strip() if points else "Не найдены"
        return {'level': level_text, 'points': points_text}
    except Exception as e:
        print(f"Ошибка рейтинга: {e}")
        return None

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
    token_status = "✅ Есть" if OZON_TOKEN or load_cookies() else "❌ Нет"
    return (
        f"👤 *Профиль*\n\n"
        f"• Имя: {user.first_name}\n"
        f"• ID: {user.id}\n"
        f"• Склад: {USER_SETTINGS['warehouse']}\n"
        f"• Процессы: {len(USER_SETTINGS['processes'])}\n"
        f"  {processes}\n"
        f"• Мониторинг: {'✅ Активен' if USER_SETTINGS['monitoring_active'] else '❌ Отключен'}\n"
        f"• Найдено смен: {STATS['total_shifts']}\n"
        f"• Авторизация: {token_status}\n"
        f"• Время: {now}"
    )

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
                                f"🔔 *НОВАЯ СМЕНА!*\n\n📍 {USER_SETTINGS['warehouse']}\n⚙️ {process}\n{shift_text}\n🏃‍♂️ Бери скорее!",
                                parse_mode="Markdown"
                            )
                    LAST_SHIFTS[process] = current_dates
            STATS['last_check'] = datetime.now().strftime("%H:%M:%S")
        except Exception as e:
            print(f"Ошибка мониторинга: {e}")
        await asyncio.sleep(CHECK_INTERVAL)

# ===== ПРИВЕТСТВИЕ =====
@bot.message_handler(commands=['start'])
async def start(message):
    global CHAT_ID
    CHAT_ID = message.chat.id
    user_name = message.from_user.first_name
    processes = ", ".join(USER_SETTINGS['processes'])
    has_auth = bool(OZON_TOKEN or load_cookies())
    auth_status = "✅ Авторизован" if has_auth else "❌ Не авторизован"
    welcome_text = (
        f"👋 *Добро пожаловать, {user_name}!*\n\n"
        f"Я — твой персональный помощник по сменам в Ozon Job.\n\n"
        f"📍 *Склад:* {USER_SETTINGS['warehouse']}\n"
        f"⚙️ *Отслеживаю:* {processes}\n"
        f"🔐 *Статус:* {auth_status}\n\n"
        f"📌 *Что я умею:*\n\n"
        f"👤 *Профиль* — Твои данные и настройки\n"
        f"📊 *Статус* — Смены по выбранным процессам\n"
        f"📋 *Все смены* — Все доступные смены на складе\n"
        f"⭐ *Рейтинг* — Твой рейтинг и баллы\n"
        f"⚙️ *Настройки* — Добавить/удалить процесс, вкл/выкл уведомления\n"
        f"🔄 *Обновить* — Обновить данные\n\n"
        f"🔑 *Чтобы бот видел смены и рейтинг:*\n"
        f"Напиши /login и войди в аккаунт Ozon Job\n"
        f"Или скопируй куки из браузера и отправь /setcookies\n\n"
        f"📢 Я автоматически пришлю уведомление, как только появится новая смена!"
    )
    await bot.send_message(
        message.chat.id,
        welcome_text,
        parse_mode="Markdown",
        reply_markup=get_main_keyboard()
    )
    asyncio.create_task(monitor_shifts())

# ===== АВТОРИЗАЦИЯ ЧЕРЕЗ ТЕЛЕФОН (/login) =====
@bot.message_handler(commands=['login'])
async def login_start(message):
    global auth_step, user_phone, auth_session
    auth_step = "phone"
    auth_session = requests.Session()
    await bot.send_message(
        message.chat.id,
        "📱 *Введи свой номер телефона*\n\nФормат: +7XXXXXXXXXX\n\nПример: +79001234567",
        parse_mode="Markdown"
    )

@bot.message_handler(func=lambda message: auth_step == "phone" and message.text.startswith('+7'))
async def login_phone(message):
    global auth_step, user_phone, auth_session
    user_phone = message.text.strip()
    auth_step = "code"
    try:
        response = auth_session.post(
            "https://job.ozon.ru/api/auth/send-code",
            json={"phone": user_phone},
            headers=HEADERS
        )
        if response.status_code == 200:
            await bot.send_message(
                message.chat.id,
                f"✅ Код отправлен на {user_phone}\n\nВведи код из СМС (только цифры):"
            )
        else:
            await bot.send_message(
                message.chat.id,
                f"❌ Ошибка: {response.status_code}\n\n{response.text[:200]}\n\nПопробуй /login заново"
            )
            auth_step = None
    except Exception as e:
        await bot.send_message(message.chat.id, f"❌ Ошибка: {e}\n\nПопробуй /login заново")
        auth_step = None

@bot.message_handler(func=lambda message: auth_step == "code" and message.text.isdigit())
async def login_code(message):
    global auth_step, OZON_TOKEN
    code = message.text.strip()
    try:
        response = auth_session.post(
            "https://job.ozon.ru/api/auth/verify-code",
            json={"phone": user_phone, "code": code},
            headers=HEADERS
        )
        if response.status_code == 200:
            cookies = auth_session.cookies.get_dict()
            save_cookies(cookies)
            OZON_TOKEN = cookies.get('__Secure-refresh-token', '')
            os.environ['OZON_TOKEN'] = OZON_TOKEN
            await bot.send_message(
                message.chat.id,
                "✅ *Авторизация успешна!*\n\nТеперь я могу видеть смены и рейтинг! 🎉",
                parse_mode="Markdown",
                reply_markup=get_main_keyboard()
            )
            auth_step = None
        else:
            await bot.send_message(
                message.chat.id,
                f"❌ Ошибка: {response.status_code}\n\n{response.text[:200]}\n\nПопробуй /login заново"
            )
            auth_step = None
    except Exception as e:
        await bot.send_message(message.chat.id, f"❌ Ошибка: {e}\n\nПопробуй /login заново")
        auth_step = None

# ===== АВТОРИЗАЦИЯ ЧЕРЕЗ КУКИ (/setcookies) =====
@bot.message_handler(commands=['setcookies'])
async def set_cookies(message):
    await bot.send_message(
        message.chat.id,
        "🍪 *Отправь куки в формате JSON*\n\n"
        "Как получить куки:\n"
        "1. Установи Firefox на телефон\n"
        "2. Установи расширение Cookie-Editor\n"
        "3. Зайди на job.ozon.ru и войди\n"
        "4. Нажми на расширение → Export → скопируй JSON\n"
        "5. Отправь JSON сюда\n\n"
        "Пример: {\"cookie1\":\"value1\",\"cookie2\":\"value2\"}",
        parse_mode="Markdown"
    )

@bot.message_handler(func=lambda message: message.text.startswith('{') and message.text.endswith('}'))
async def handle_cookies_json(message):
    global OZON_TOKEN
    try:
        cookies = json.loads(message.text)
        if isinstance(cookies, dict):
            save_cookies(cookies)
            OZON_TOKEN = cookies.get('__Secure-refresh-token', '')
            os.environ['OZON_TOKEN'] = OZON_TOKEN
            await bot.send_message(
                message.chat.id,
                "✅ *Куки сохранены!*\n\nТеперь я могу видеть смены и рейтинг! 🎉",
                parse_mode="Markdown",
                reply_markup=get_main_keyboard()
            )
        else:
            await bot.send_message(message.chat.id, "❌ Неверный формат. Отправь JSON объект.")
    except json.JSONDecodeError:
        await bot.send_message(message.chat.id, "❌ Неверный JSON. Попробуй ещё раз.")

# ===== КОМАНДЫ =====
@bot.message_handler(func=lambda message: message.text == "👤 Профиль")
async def profile(message):
    await bot.send_message(
        message.chat.id,
        get_profile_text(message),
        parse_mode="Markdown",
        reply_markup=get_main_keyboard()
    )

@bot.message_handler(func=lambda message: message.text == "📊 Статус")
async def status_command(message):
    await bot.send_message(message.chat.id, "🔍 Проверяю смены...", reply_markup=get_main_keyboard())
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
        await bot.send_message(
            message.chat.id,
            "📭 Нет смен по отслеживаемым процессам\n\n💡 Проверь авторизацию: /login или /setcookies",
            reply_markup=get_main_keyboard()
        )

@bot.message_handler(func=lambda message: message.text == "📋 Все смены")
async def all_shifts_command(message):
    await bot.send_message(message.chat.id, "🔍 Загружаю все смены...", reply_markup=get_main_keyboard())
    all_shifts = await asyncio.to_thread(get_all_shifts)
    if all_shifts:
        text = f"📋 *Все смены*\n📍 {USER_SETTINGS['warehouse']}\n\n"
        for process, shifts in all_shifts.items():
            is_monitored = process in USER_SETTINGS['processes']
            mark = "✅ " if is_monitored else "   "
            text += f"{mark}⚙️ *{process}*\n"
            for shift in shifts:
                time_str = f"{shift['time_start']} - {shift['time_end']}" if shift['time_start'] else "Время уточняется"
                text += f"  • 📅 {shift['date']} | ⏰ {time_str}\n"
            text += "\n"
        await bot.send_message(message.chat.id, text, parse_mode="Markdown", reply_markup=get_main_keyboard())
    else:
        await bot.send_message(
            message.chat.id,
            "📭 Нет доступных смен\n\n💡 Проверь авторизацию: /login или /setcookies",
            reply_markup=get_main_keyboard()
        )

@bot.message_handler(func=lambda message: message.text == "⭐ Рейтинг")
async def rating_command(message):
    await bot.send_message(message.chat.id, "🔍 Загружаю рейтинг...", reply_markup=get_main_keyboard())
    rating = await asyncio.to_thread(get_rating)
    if rating:
        await bot.send_message(
            message.chat.id,
            f"⭐ *Рейтинг*\n\n• Уровень: {rating['level']}\n• Баллы: {rating['points']}",
            parse_mode="Markdown",
            reply_markup=get_main_keyboard()
        )
    else:
        await bot.send_message(
            message.chat.id,
            "❌ Не удалось получить рейтинг.\n\n💡 Проверь авторизацию: /login или /setcookies",
            reply_markup=get_main_keyboard()
        )

@bot.message_handler(func=lambda message: message.text == "⚙️ Настройки")
async def settings(message):
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("➕ Добавить процесс", callback_data="add_process"))
    markup.add(InlineKeyboardButton("➖ Удалить процесс", callback_data="remove_process"))
    markup.add(InlineKeyboardButton("🔔 Вкл/Выкл уведомления", callback_data="toggle_monitoring"))
    processes = "\n  ".join(USER_SETTINGS['processes']) if USER_SETTINGS['processes'] else "❌ Нет"
    await bot.send_message(
        message.chat.id,
        f"⚙️ *Настройки*\n\n📍 Склад: {USER_SETTINGS['warehouse']}\n📋 Процессы:\n  {processes}\n🔔 Уведомления: {'✅ Вкл' if USER_SETTINGS['monitoring_active'] else '❌ Выкл'}",
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
        await bot.edit_message_text(f"⚙️ Мониторинг {status}", call.message.chat.id, call.message.message_id)
    elif call.data == "add_process":
        markup = InlineKeyboardMarkup()
        for proc in ALL_PROCESSES:
            if proc not in USER_SETTINGS['processes']:
                markup.add(InlineKeyboardButton(proc, callback_data=f"addproc_{proc}"))
        if not markup.keyboard:
            await bot.answer_callback_query(call.id, "Все процессы уже добавлены!")
            return
        await bot.edit_message_text("➕ Выбери процесс:", call.message.chat.id, call.message.message_id, reply_markup=markup)
    elif call.data.startswith("addproc_"):
        process = call.data.replace("addproc_", "")
        if process not in USER_SETTINGS['processes']:
            USER_SETTINGS['processes'].append(process)
        await bot.answer_callback_query(call.id, f"✅ {process} добавлен!")
        await bot.edit_message_text(f"✅ Процесс '{process}' добавлен!", call.message.chat.id, call.message.message_id)
        await settings(call.message)
    elif call.data == "remove_process":
        if not USER_SETTINGS['processes']:
            await bot.answer_callback_query(call.id, "Нет процессов!")
            return
        markup = InlineKeyboardMarkup()
        for proc in USER_SETTINGS['processes']:
            markup.add(InlineKeyboardButton(f"❌ {proc}", callback_data=f"removeproc_{proc}"))
        await bot.edit_message_text("➖ Выбери процесс для удаления:", call.message.chat.id, call.message.message_id, reply_markup=markup)
    elif call.data.startswith("removeproc_"):
        process = call.data.replace("removeproc_", "")
        if process in USER_SETTINGS['processes']:
            USER_SETTINGS['processes'].remove(process)
        await bot.answer_callback_query(call.id, f"❌ {process} удалён!")
        await bot.edit_message_text(f"❌ Процесс '{process}' удалён!", call.message.chat.id, call.message.message_id)
        await settings(call.message)

async def main():
    print("🤖 Бот запущен!")
    await bot.polling()

if __name__ == "__main__":
    asyncio.run(main())