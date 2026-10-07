import os
import logging
import csv
from datetime import datetime
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiohttp import web

logging.basicConfig(level=logging.INFO)

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "8905023648:AAE_zcvaHwUj4WLlOcCsFleS8MEpQvLKWvY")
MAPS_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY", "AIzaSyC2HFdydohHT0E8KMoeK1ZUNTQfoJG_UKE")

bot = Bot(token=TOKEN)
dp = Dispatcher(storage=MemoryStorage())

CSV_FILE = "truck_data.csv"

# Инициализация CSV файла, если его нет
def init_csv():
    if not os.path.exists(CSV_FILE):
        with open(CSV_FILE, mode="w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["Date", "Type", "Origin", "Destination", "Deadhead", "Loaded", "TotalMiles", "Gross", "Commission", "Net", "Category", "Description"])

init_csv()

class TripStates(StatesGroup):
    waiting_for_origin = State()
    waiting_for_destination = State()
    waiting_for_deadhead = State()
    waiting_for_loaded_miles = State()
    waiting_for_gross = State()
    waiting_for_commission = State()

class ExpenseStates(StatesGroup):
    waiting_for_category = State()
    waiting_for_amount = State()
    waiting_for_description = State()

def save_row(row_data):
    with open(CSV_FILE, mode="a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(row_data)

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    kb = [
        [types.KeyboardButton(text="🚚 Добавить поездку"), types.KeyboardButton(text="💸 Добавить расход")],
        [types.KeyboardButton(text="📊 Выгрузить отчет (CSV)")]
    ]
    keyboard = types.ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)
    await message.answer("Бот готов к работе без всяких блокировок Google! Выбирай действие:", reply_markup=keyboard)

@dp.message(F.text == "📊 Выгрузить отчет (CSV)")
async def export_csv(message: types.Message):
    if os.path.exists(CSV_FILE) and os.path.getsize(CSV_FILE) > 0:
        file = types.FSInputFile(CSV_FILE)
        await message.answer_document(file, caption="📂 Твоя актуальная база данных учета")
    else:
        await message.answer("⚠️ База данных пока пуста.")

# Сценарий поездки
@dp.message(F.text == "🚚 Добавить поездку")
async def start_trip(message: types.Message, state: FSMContext):
    await message.answer("📍 Введи город отправления (Откуда):")
    await state.set_state(TripStates.waiting_for_origin)

@dp.message(TripStates.waiting_for_origin)
async def process_origin(message: types.Message, state: FSMContext):
    await state.update_data(origin=message.text)
    await message.answer("🎯 Введи город назначения (Куда):")
    await state.set_state(TripStates.waiting_for_destination)

@dp.message(TripStates.waiting_for_destination)
async def process_destination(message: types.Message, state: FSMContext):
    await state.update_data(destination=message.text)
    await message.answer("🛣️ Пустые мили (Deadhead):")
    await state.set_state(TripStates.waiting_for_deadhead)

@dp.message(TripStates.waiting_for_deadhead)
async def process_deadhead(message: types.Message, state: FSMContext):
    try:
        deadhead = float(message.text)
    except ValueError:
        await message.answer("Введи число:")
        return
    await state.update_data(deadhead=deadhead)
    await message.answer("🚛 Грузовые мили (Loaded miles):")
    await state.set_state(TripStates.waiting_for_loaded_miles)

@dp.message(TripStates.waiting_for_loaded_miles)
async def process_loaded(message: types.Message, state: FSMContext):
    try:
        loaded = float(message.text)
    except ValueError:
        await message.answer("Введи число:")
        return
    await state.update_data(loaded=loaded)
    await message.answer("💵 Сумма Гросс ($):")
    await state.set_state(TripStates.waiting_for_gross)

@dp.message(TripStates.waiting_for_gross)
async def process_gross(message: types.Message, state: FSMContext):
    try:
        gross = float(message.text)
    except ValueError:
        await message.answer("Введи число:")
        return
    await state.update_data(gross=gross)
    await message.answer("📉 Комиссия ($) или 0:")
    await state.set_state(TripStates.waiting_for_commission)

@dp.message(TripStates.waiting_for_commission)
async def process_commission(message: types.Message, state: FSMContext):
    try:
        commission = float(message.text)
    except ValueError:
        await message.answer("Введи число:")
        return
    
    data = await state.get_data()
    deadhead = data["deadhead"]
    loaded = data["loaded"]
    total = deadhead + loaded
    gross = data["gross"]
    net = gross - commission
    
    row = [
        datetime.now().strftime("%Y-%m-%d %H:%M"),
        "trip",
        data["origin"],
        data["destination"],
        deadhead,
        loaded,
        total,
        gross,
        commission,
        net,
        "",
        ""
    ]
    save_row(row)
    await state.clear()
    
    await message.answer(f"✅ Поездка сохранена!\nМаршрут: {data['origin']} ➔ {data['destination']}\nЧистыми: ${net}")

# Сценарий расхода
@dp.message(F.text == "💸 Добавить расход")
async def start_expense(message: types.Message, state: FSMContext):
    await message.answer("📂 Категория расхода (Топливо, Еда, Ремонт...):")
    await state.set_state(ExpenseStates.waiting_for_category)

@dp.message(ExpenseStates.waiting_for_category)
async def process_cat(message: types.Message, state: FSMContext):
    await state.update_data(category=message.text)
    await message.answer("💵 Сумма расхода ($):")
    await state.set_state(ExpenseStates.waiting_for_amount)

@dp.message(ExpenseStates.waiting_for_amount)
async def process_amt(message: types.Message, state: FSMContext):
    try:
        amount = float(message.text)
    except ValueError:
        await message.answer("Введи число:")
        return
    await state.update_data(amount=amount)
    await message.answer("📝 Описание (или '-'):")
    await state.set_state(ExpenseStates.waiting_for_description)

@dp.message(ExpenseStates.waiting_for_description)
async def process_desc(message: types.Message, state: FSMContext):
    data = await state.get_data()
    row = [
        datetime.now().strftime("%Y-%m-%d %H:%M"),
        "expense",
        "", "", 0, 0, 0, 0, 0, 0,
        data["category"],
        message.text
    ]
    save_row(row)
    await state.clear()
    await message.answer(f"✅ Расход записан: ${data['amount']} ({data['category']})")

async def handle_ping(request):
    return web.Response(text="Bot is active!")

async def web_server():
    app = web.Application()
    app.router.add_get("/", handle_ping)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", 10000))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()

async def main():
    await web_server()
    await dp.start_polling(bot)

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
