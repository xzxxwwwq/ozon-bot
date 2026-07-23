import asyncio
import os
import re
from playwright.async_api import async_playwright
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

async def check_shifts():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=['--no-sandbox'])
        context = await browser.new_context(viewport={'width': 390, 'height': 844})
        page = await context.new_page()
        
        try:
            await page.goto("https://job.ozon.ru")
            await page.wait_for_timeout(3000)
            
            if "/login" in page.url:
                await page.locator('input[type="tel"]').fill(PHONE)
                await page.locator('button:has-text("Продолжить")').click()
                await page.wait_for_timeout(5000)
                
                if AUTH_CODE:
                    await page.locator('input[type="text"]').fill(AUTH_CODE)
                    await page.locator('button:has-text("Подтвердить")').click()
                    await page.wait_for_timeout(5000)
                    await page.goto("https://job.ozon.ru")
                    await page.wait_for_timeout(3000)
            
            await page.wait_for_timeout(2000)
            warehouses = await page.locator('.warehouse-item').all()
            for wh in warehouses:
                name = await wh.locator('.warehouse-name').text_content()
                if WAREHOUSE in name:
                    await wh.click()
                    break
            
            await page.wait_for_timeout(2000)
            processes = await page.locator('.process-item').all()
            for proc in processes:
                name = await proc.locator('.process-name').text_content()
                if PROCESS in name:
                    await proc.click()
                    break
            
            await page.wait_for_timeout(2000)
            day_cells = await page.locator('.day-cell').all()
            available = []
            for cell in day_cells:
                classes = await cell.get_attribute('class')
                if 'available' in classes:
                    date_text = await cell.text_content()
                    date_num = re.search(r'\d+', date_text)
                    if date_num:
                        available.append(date_num.group())
            
            await browser.close()
            return available
            
        except Exception as e:
            print(f"Ошибка: {e}")
            await browser.close()
            return []

async def monitor_shifts():
    global LAST_SHIFTS, CHAT_ID
    while True:
        try:
            current_shifts = set(await check_shifts())
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