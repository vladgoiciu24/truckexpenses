import os
import logging
import aiohttp
from datetime import datetime
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiohttp import web

# ==========================================
# НАСТРОЙКА ЛОГИРОВАНИЯ И ПЕРЕМЕННЫХ
# ==========================================
logging.basicConfig(level=logging.INFO)

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "8905023648:AAE_zcvaHwUj4WLlOcCsFleS8MEpQvLKWvY")
MAPS_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY", "AIzaSyC2HFdydohHT0E8KMoeK1ZUNTQfoJG_UKE")
SPREADSHEET_ID = "1ht6jCzLwQPf8tNnuroVEyqm51hMqqSChkdEhO3k1Ddo"

# Инициализация бота и диспетчера
bot = Bot(token=TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# ==========================================
# СОСТОЯНИЯ (FSM)
# ==========================================
class TripStates(StatesGroup):
    waiting_for_origin = State()
    waiting_for_destination = State()
    waiting_for_deadhead = State()
    waiting_for_gross = State()
    waiting_for_commission = State()

class ExpenseStates(StatesGroup):
    waiting_for_category = State()
    waiting_for_amount = State()
    waiting_for_description = State()

# ==========================================
# ФУНКЦИЯ СОХРАНЕНИЯ ДАННЫХ
# ==========================================
async def append_to_google_sheet(data_type: str, data: dict):
    """
    Функция отправки данных. 
    Сейчас записывает в системные логи Render, 
    готовая к подключению прямой отправки.
    """
    logging.info(f"DATA_EXPORT [{data_type.upper}]: {data}")
    return True

# ==========================================
# ОБРАБОТЧИКИ КОМАНД И КНОПОК
# ==========================================
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    kb = [
        [types.KeyboardButton(text="🚚 Добавить поездку"), types.KeyboardButton(text="💸 Добавить расход")],
        [types.KeyboardButton(text="📊 Статистика")]
    ]
    keyboard = types.ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)
    await message.answer(
        "Привет! Я твой персональный бот для учета поездок и расходов.\nВыбери нужное действие на клавиатуре:", 
        reply_markup=keyboard
    )

@dp.message(F.text == "📊 Статистика")
async def show_stats(message: types.Message):
    await message.answer(
        "📊 **Сводка по учету:**\n\n"
        "Все введенные данные успешно фиксируются. Скоро здесь появится детальная аналитика за текущий месяц!"
    )

# ==========================================
# СЦЕНАРИЙ ДОБАВЛЕНИЯ ПОЕЗДКИ
# ==========================================
@dp.message(F.text == "🚚 Добавить поездку")
async def start_trip(message: types.Message, state: FSMContext):
    await message.answer("Введи город отправления (Откуда):")
    await state.set_state(TripStates.waiting_for_origin)

@dp.message(TripStates.waiting_for_origin)
async def process_origin(message: types.Message, state: FSMContext):
    await state.update_data(origin=message.text)
    await message.answer("Введи город назначения (Куда):")
    await state.set_state(TripStates.waiting_for_destination)

@dp.message(TripStates.waiting_for_destination)
async def process_destination(message: types.Message, state: FSMContext):
    await state.update_data(destination=message.text)
    await message.answer("Сколько пустых миль (Deadhead miles)? (введи число):")
    await state.set_state(TripStates.waiting_for_deadhead)

@dp.message(TripStates.waiting_for_deadhead)
async def process_deadhead(message: types.Message, state: FSMContext):
    try:
        deadhead = float(message.text)
    except ValueError:
        await message.answer("Пожалуйста, введи корректное число для миль:")
        return
    await state.update_data(deadhead=deadhead)
    await message.answer("Введи общую сумму Гросс ($):")
    await state.set_state(TripStates.waiting_for_gross)

@dp.message(TripStates.waiting_for_gross)
async def process_gross(message: types.Message, state: FSMContext):
    try:
        gross = float(message.text)
    except ValueError:
        await message.answer("Пожалуйста, введи корректное число для суммы:")
        return
    await state.update_data(gross=gross)
    await message.answer("Введи сумму комиссии ($) (или 0):")
    await state.set_state(TripStates.waiting_for_commission)

@dp.message(TripStates.waiting_for_commission)
async def process_commission(message: types.Message, state: FSMContext):
    try:
        commission = float(message.text)
    except ValueError:
        await message.answer("Пожалуйста, введи корректное число для комиссии:")
        return
    
    data = await state.get_data()
    gross = data["gross"]
    net = gross - commission
    
    trip_data = {
        "type": "trip",
        "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "origin": data["origin"],
        "destination": data["destination"],
        "deadhead": data["deadhead"],
        "loaded_miles": 0, 
        "total_miles": data["deadhead"],
        "gross": gross,
        "commission": commission,
        "net": net
    }
    
    await append_to_google_sheet("trip", trip_data)
    await state.clear()
    
    await message.answer(
        f"✅ Поездка успешно сохранена!\n\n"
        f"📍 Маршрут: {trip_data['origin']} ➔ {trip_data['destination']}\n"
        f"💵 Гросс: ${gross}\n"
        f"📉 Комиссия: ${commission}\n"
        f"💰 Чистыми: ${net}"
    )

# ==========================================
# СЦЕНАРИЙ ДОБАВЛЕНИЯ РАСХОДА
# ==========================================
@dp.message(F.text == "💸 Добавить расход")
async def start_expense(message: types.Message, state: FSMContext):
    await message.answer("Введи категорию расхода (например: Топливо, Еда, Ремонт, Стоянка):")
    await state.set_state(ExpenseStates.waiting_for_category)

@dp.message(ExpenseStates.waiting_for_category)
async def process_expense_cat(message: types.Message, state: FSMContext):
    await state.update_data(category=message.text)
    await message.answer("Введи сумму расхода ($):")
    await state.set_state(ExpenseStates.waiting_for_amount)

@dp.message(ExpenseStates.waiting_for_amount)
async def process_expense_amount(message: types.Message, state: FSMContext):
    try:
        amount = float(message.text)
    except ValueError:
        await message.answer("Пожалуйста, введи числовую сумму:")
        return
    await state.update_data(amount=amount)
    await message.answer("Введи короткое описание (или отправь дефис '-'):")
    await state.set_state(ExpenseStates.waiting_for_description)

@dp.message(ExpenseStates.waiting_for_description)
async def process_expense_desc(message: types.Message, state: FSMContext):
    data = await state.get_data()
    expense_data = {
        "type": "expense",
        "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "category": data["category"],
        "amount": data["amount"],
        "description": message.text
    }
    
    await append_to_google_sheet("expense", expense_data)
    await state.clear()
    
    await message.answer(
        f"✅ Расход записан!\n\n"
        f"📂 Категория: {expense_data['category']}\n"
        f"💵 Сумма: ${expense_data['amount']}\n"
        f"📝 Описание: {expense_data['description']}"
    )

# ==========================================
# ВЕБ-СЕРВЕР ДЛЯ RENDER (24/7 UPTIME)
# ==========================================
async def handle_ping(request):
    return web.Response(text="Bot is running and active!")

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
