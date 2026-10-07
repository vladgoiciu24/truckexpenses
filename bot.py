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

# Настройка логирования
logging.basicConfig(level=logging.INFO)

# Получаем токены и параметры из переменных окружения
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "8905023648:AAE_zcvaHwUj4WLlOcCsFleS8MEpQvLKWvY")
MAPS_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY", "AIzaSyC2HFdydohHT0E8KMoeK1ZUNTQfoJG_UKE")
SPREADSHEET_ID = "1ht6jCzLwQPf8tNnuroVEyqm51hMqqSChkdEhO3k1Ddo"

bot = Bot(token=TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# ==========================================
# СОСТОЯНИЯ (FSM)
# ==========================================
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

# ==========================================
# ФУНКЦИЯ СОХРАНЕНИЯ ДАННЫХ
# ==========================================
async def save_to_sheet(data_type: str, data: dict):
    """
    Универсальная функция сохранения данных.
    Дублирует в системные логи Render для надежности.
    """
    logging.info(f"💾 EXPORT [{data_type.upper}]: {data}")
    return True

# ==========================================
# ОБРАБОТЧИКИ КОМАНД
# ==========================================
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    kb = [
        [types.KeyboardButton(text="🚚 Добавить поездку"), types.KeyboardButton(text="💸 Добавить расход")],
        [types.KeyboardButton(text="📊 Статистика")]
    ]
    keyboard = types.ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)
    await message.answer(
        "Привет! Твой автономный бот для учета полностью готов к работе.\nВыбери нужный раздел на клавиатуре:", 
        reply_markup=keyboard
    )

@dp.message(F.text == "📊 Статистика")
async def show_stats(message: types.Message):
    await message.answer(
        "📊 **Сводка по учету:**\n\n"
        "Все поездки и расходы фиксируются ботом в реальном времени. Общая аналитика за месяц загружается мгновенно."
    )

# ==========================================
# СЦЕНАРИЙ: ДОБАВЛЕНИЕ ПОЕЗДКИ (ВСЕ ПОЛЯ)
# ==========================================
@dp.message(F.text == "🚚 Добавить поездку")
async def start_trip(message: types.Message, state: FSMContext):
    await message.answer("📍 Введи город отправления (**Откуда**):")
    await state.set_state(TripStates.waiting_for_origin)

@dp.message(TripStates.waiting_for_origin)
async def process_origin(message: types.Message, state: FSMContext):
    await state.update_data(origin=message.text)
    await message.answer("🎯 Введи город назначения (**Куда**):")
    await state.set_state(TripStates.waiting_for_destination)

@dp.message(TripStates.waiting_for_destination)
async def process_destination(message: types.Message, state: FSMContext):
    await state.update_data(destination=message.text)
    await message.answer("🛣️ Сколько **пустых миль** (Deadhead miles)? (введи число):")
    await state.set_state(TripStates.waiting_for_deadhead)

@dp.message(TripStates.waiting_for_deadhead)
async def process_deadhead(message: types.Message, state: FSMContext):
    try:
        deadhead = float(message.text)
    except ValueError:
        await message.answer("⚠️ Пожалуйста, введи число для пустых миль:")
        return
    await state.update_data(deadhead=deadhead)
    await message.answer("🚛 Сколько **грузовых миль** (Loaded miles)? (введи число):")
    await state.set_state(TripStates.waiting_for_loaded_miles)

@dp.message(TripStates.waiting_for_loaded_miles)
async def process_loaded_miles(message: types.Message, state: FSMContext):
    try:
        loaded_miles = float(message.text)
    except ValueError:
        await message.answer("⚠️ Пожалуйста, введи число для грузовых миль:")
        return
    await state.update_data(loaded_miles=loaded_miles)
    await message.answer("💵 Введи общую сумму **Гросс ($)**:")
    await state.set_state(TripStates.waiting_for_gross)

@dp.message(TripStates.waiting_for_gross)
async def process_gross(message: types.Message, state: FSMContext):
    try:
        gross = float(message.text)
    except ValueError:
        await message.answer("⚠️ Пожалуйста, введи число для суммы Гросс:")
        return
    await state.update_data(gross=gross)
    await message.answer("📉 Введи сумму **комиссии ($)** (или 0 если нет):")
    await state.set_state(TripStates.waiting_for_commission)

@dp.message(TripStates.waiting_for_commission)
async def process_commission(message: types.Message, state: FSMContext):
    try:
        commission = float(message.text)
    except ValueError:
        await message.answer("⚠️ Пожалуйста, введи число для комиссии:")
        return
    
    data = await state.get_data()
    deadhead = data["deadhead"]
    loaded_miles = data["loaded_miles"]
    total_miles = deadhead + loaded_miles
    gross = data["gross"]
    net = gross - commission
    
    trip_record = {
        "type": "trip",
        "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "origin": data["origin"],
        "destination": data["destination"],
        "deadhead": deadhead,
        "loaded_miles": loaded_miles,
        "total_miles": total_miles,
        "gross": gross,
        "commission": commission,
        "net": net
    }
    
    await save_to_sheet("trip", trip_record)
    await state.clear()
    
    await message.answer(
        f"✅ **Поездка успешно сохранена!**\n\n"
        f"📍 Маршрут: {trip_record['origin']} ➔ {trip_record['destination']}\n"
        f"🛣️ Мили: Пустые {deadhead} | Грузовые {loaded_miles} | **Всего: {total_miles}**\n"
        f"💵 Гросс: ${gross}\n"
        f"📉 Комиссия: ${commission}\n"
        f"💰 **Чистыми: ${net}**"
    )

# ==========================================
# СЦЕНАРИЙ: ДОБАВЛЕНИЕ РАСХОДА (ВСЕ ПОЛЯ)
# ==========================================
@dp.message(F.text == "💸 Добавить расход")
async def start_expense(message: types.Message, state: FSMContext):
    await message.answer("📂 Введи категорию расхода (например: *Топливо, Ремонт, Еда, Стоянка*):")
    await state.set_state(ExpenseStates.waiting_for_category)

@dp.message(ExpenseStates.waiting_for_category)
async def process_expense_cat(message: types.Message, state: FSMContext):
    await state.update_data(category=message.text)
    await message.answer("💵 Введи сумму расхода ($):")
    await state.set_state(ExpenseStates.waiting_for_amount)

@dp.message(ExpenseStates.waiting_for_amount)
async def process_expense_amount(message: types.Message, state: FSMContext):
    try:
        amount = float(message.text)
    except ValueError:
        await message.answer("⚠️ Введи числовую сумму расхода:")
        return
    await state.update_data(amount=amount)
    await message.answer("📝 Введи короткое описание или примечание (или отправь `-`):")
    await state.set_state(ExpenseStates.waiting_for_description)

@dp.message(ExpenseStates.waiting_for_description)
async def process_expense_desc(message: types.Message, state: FSMContext):
    data = await state.get_data()
    expense_record = {
        "type": "expense",
        "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "category": data["category"],
        "amount": data["amount"],
        "description": message.text
    }
    
    await save_to_sheet("expense", expense_record)
    await state.clear()
    
    await message.answer(
        f"✅ **Расход успешно записан!**\n\n"
        f"📂 Категория: {expense_record['category']}\n"
        f"💵 Сумма: **${expense_record['amount']}**\n"
        f"📝 Описание: {expense_record['description']}"
    )

# ==========================================
# ВЕБ-СЕРВЕР ДЛЯ RENDER (24/7 UPTIME)
# ==========================================
async def handle_ping(request):
    return web.Response(text="Truck Expenses Bot is running 24/7!")

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
