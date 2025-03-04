from bale import Bot, Message
import requests
import logging
import asyncio
from datetime import datetime, time
import pytz

# تنظیم لاگ‌گذاری
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# توکن بات بله
TOKEN = "1382589839:NpmhsP2ikPpx2kSZ74uLyYVv6kkv9QwCKbLncAgR"

# آدرس وب‌سرویس
API_TSETMC_URL = "https://brsapi.ir/FreeTsetmcBourseApi/TsetmcApi.php"
API_USER_URL = "https://brsapi.ir/FreeTsetmcBourseApi/TsetmcApi_User.php"
API_KEY = "FreeuqqEPm1Qg18y3OiFnwMvyLhIQ802"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 6.1; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json, text/plain, */*"
}

client = Bot(token=TOKEN)

# تنظیمات زمانی (منطقه زمانی ایران)
IRAN_TZ = pytz.timezone("Asia/Tehran")

# لیست صندوق‌های طلا
GOLD_FUNDS = ["عیار", "طلا", "کهربا", "مثقال", "گوهر", "زر", "گنج", "جواهر", "نفیس", "ناب", "آلتون", "تابش", "زرفام", "درخشان", "لیان", "زروان", "قیراط", "آتش"]

# ذخیره پرتفوی و واچ‌لیست کاربران
portfolios = {}  # {user_id: [symbol1, symbol2, ...]}
watchlists = {}  # {user_id: {symbol: {"price_condition": float, "condition": str}}}
cache = {}  # کش داده‌های API برای کاهش درخواست‌ها

def get_remaining_requests():
    try:
        response = requests.get(API_USER_URL, headers=HEADERS, params={"key": API_KEY})
        if response.status_code == 200:
            data = response.json()
            usage = data.get("today_usage_count_main", "0/100")
            used, total = map(int, usage.split("/"))
            return total - used
        return "نامشخص"
    except Exception as e:
        logging.error(f"خطا در گرفتن تعداد درخواست‌ها: {e}")
        return "نامشخص"

async def fetch_fund_data():
    try:
        params = {"key": API_KEY}
        response = requests.get(API_TSETMC_URL, headers=HEADERS, params=params)
        if response.status_code == 200:
            data = response.json()
            if isinstance(data, list):
                for fund in data:
                    cache[fund.get("l18", "")] = fund
                return data
        return None
    except Exception as e:
        logging.error(f"خطا در دریافت داده‌ها: {e}")
        return None

def format_fund_info(fund):
    symbol = fund.get("l18", "نامشخص")
    price = safe_float(fund.get("pl", 0))
    price_change = safe_float(fund.get("plc", 0))
    price_percent = safe_float(fund.get("plp", 0))
    volume = safe_float(fund.get("tvol", 0))
    return (
        f"{symbol}:\n"
        f"آخرین قیمت: {price:,} ({'+' if price_change >= 0 else ''}{price_change:,} - {price_percent:.2f}%)\n"
        f"حجم معاملات: {volume:,}\n"
        "-----\n"
    )

def safe_float(value):
    return float(value) if value is not None and isinstance(value, (int, float, str)) else 0

async def portfolio_report(user_id):
    if user_id not in portfolios or not portfolios[user_id]:
        return "پرتفوی شما خالیه! با /setportfolio نمادها رو وارد کنید."
    await fetch_fund_data()
    result = f"وضعیت پرتفوی شما ({datetime.now(IRAN_TZ).strftime('%H:%M')}):\n"
    for symbol in portfolios[user_id]:
        fund = cache.get(symbol)
        if fund:
            result += format_fund_info(fund)
        else:
            result += f"{symbol}: داده‌ای پیدا نشد!\n-----\n"
    return result

async def watchlist_report(user_id):
    if user_id not in watchlists or not watchlists[user_id]:
        return "واچ‌لیست شما خالیه! با /setwatchlist نمادها رو وارد کنید."
    await fetch_fund_data()
    result = f"وضعیت واچ‌لیست شما ({datetime.now(IRAN_TZ).strftime('%H:%M')}):\n"
    for symbol, details in watchlists[user_id].items():
        fund = cache.get(symbol)
        if fund:
            result += format_fund_info(fund)
    return result

async def check_watchlist_alerts(user_id):
    if user_id not in watchlists or not watchlists[user_id]:
        return None
    await fetch_fund_data()
    alerts = []
    for symbol, details in watchlists[user_id].items():
        fund = cache.get(symbol)
        if fund:
            price = safe_float(fund.get("pl", 0))
            target = details["price_condition"]
            condition = details["condition"]
            if (condition == "equal" and price == target) or \
               (condition == "above" and price > target) or \
               (condition == "below" and price < target):
                alerts.append(f"هشدار: {symbol} به قیمت {price:,} رسید (شرط: {condition} {target:,})")
    return "\n".join(alerts) if alerts else None

async def periodic_tasks():
    while True:
        now = datetime.now(IRAN_TZ).time()
        if time(9, 0) <= now <= time(15, 0):
            for user_id in portfolios:
                report = await portfolio_report(user_id)
                await client.send_message(user_id, report)
            for user_id in watchlists:
                alert = await check_watchlist_alerts(user_id)
                if alert:
                    await client.send_message(user_id, alert)
        await asyncio.sleep(1800)  # هر نیم ساعت

@client.event
async def on_ready():
    logging.info(f"بات {client.user.username} آماده‌ست!")
    asyncio.create_task(periodic_tasks())

@client.event
async def on_message(message: Message):
    user_id = message.author.id
    content = message.content.strip()

    if content == "/start":
        await message.reply("سلام! دستورات:\n"
                            "/setportfolio نمادها (مثال: عیار طلا)\n"
                            "/setwatchlist نماد شرط قیمت (مثال: عیار equal 1000)\n"
                            "/portfolio وضعیت پرتفوی\n"
                            "/watchlist وضعیت واچ‌لیست\n"
                            "یا اسم نماد رو بفرستید.")
    
    elif content.startswith("/setportfolio"):
        symbols = content.split()[1:]
        portfolios[user_id] = symbols
        await message.reply(f"پرتفوی شما تنظیم شد: {', '.join(symbols)}")
    
    elif content.startswith("/setwatchlist"):
        parts = content.split()
        if len(parts) < 4:
            await message.reply("فرمت: /setwatchlist نماد شرط قیمت (مثال: عیار equal 1000)")
            return
        symbol, condition, price = parts[1], parts[2], parts[3]
        if condition not in ["equal", "above", "below"]:
            await message.reply("شرط باید equal، above یا below باشه!")
            return
        watchlists.setdefault(user_id, {})[symbol] = {"price_condition": float(price), "condition": condition}
        await message.reply(f"واچ‌لیست تنظیم شد: {symbol} {condition} {price}")
    
    elif content == "/portfolio":
        report = await portfolio_report(user_id)
        await message.reply(report)
    
    elif content == "/watchlist":
        report = await watchlist_report(user_id)
        await message.reply(report)
    
    else:
        await fetch_fund_data()
        fund = cache.get(content)
        if fund:
            await message.reply(format_fund_info(fund))
        else:
            await message.reply(f"نماد '{content}' پیدا نشد!")

client.run()