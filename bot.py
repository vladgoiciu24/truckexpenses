import os
import logging
from datetime import datetime
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiohttp import web
from supabase import create_client, Client

logging.basicConfig(level=logging.INFO)

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "8905023648:AAE_zcvaHwUj4WLlOcCsFleS8MEpQvLKWvY")
MAPS_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY", "AIzaSyC2HFdydohHT0E8KMoeK1ZUNTQfoJG_UKE")

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

# Инициализация клиентов
bot = Bot(token=TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# Инициализация Supabase клиента (если ключи заданы)
supabase: Client = None
if SUPABASE_URL and SUPABASE_KEY:
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

class TripStates(StatesGroup):
    waiting_for_origin = State()
    waiting_for_destination = State()
    waiting_for_deadhead = State()
    waiting_for_loaded_miles = State()
    waiting_for_gross = State()
    waiting_for_commission = State()

class ExpenseStates(StatesGroup):
    waiting_for_amount = State()
    waiting_for_description = State()

def save_to_supabase(row_data: dict):
    if not supabase:
        logging.error("Supabase клиент не инициализирован (проверь переменные окружения SUPABASE_URL и SUPABASE_KEY)")
        return False
    try:
        response = supabase.table("truck_records").insert(row_data).execute()
        return True
    except Exception as e:
        logging.error(f"Ошибка сохранения в Supabase: {e}")
        return False

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    kb = [
        [types.KeyboardButton(text="🚚 Добавить поездку"), types.KeyboardButton(text="💸 Добавить расход")],
        [types.KeyboardButton(text="📊 Статус базы данных")]
    ]
    keyboard = types.ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)
    await message.answer("Бот готов! Все данные сохраняются в облачную базу Supabase 24/7. Выбирай действие:", reply_markup=keyboard)

@dp.message(F.text == "📊 Статус базы данных")
async def check_db_status(message: types.Message):
    if not supabase:
        await message.answer("⚠️ Ошибка: не настроены ключи подключения к Supabase на Render.")
        return
    try:
        res = supabase.table("truck_records").select("id", count="exact").execute()
        count = res.count if hasattr(res, 'count') else "много"
        await message.answer(f"✅ Подключение к Supabase стабильно!\nЗаписей в таблице: {count}")
    except Exception as e:
        await message.answer(f"⚠️ Ошибка соединения с базой: {e}")

# --- СЦЕНАРИЙ ПОЕЗДОК ---
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
        deadhead = float(message.text.replace(',', '.'))
    except ValueError:
        await message.answer("Введи число:")
        return
    await state.update_data(deadhead=deadhead)
    await message.answer("🚛 Грузовые мили (Loaded miles):")
    await state.set_state(TripStates.waiting_for_loaded_miles)

@dp.message(TripStates.waiting_for_loaded_miles)
async def process_loaded(message: types.Message, state: FSMContext):
    try:
        loaded = float(message.text.replace(',', '.'))
    except ValueError:
        await message.answer("Введи число:")
        return
    await state.update_data(loaded=loaded)
    await message.answer("💵 Сумма Гросс ($):")
    await state.set_state(TripStates.waiting_for_gross)

@dp.message(TripStates.waiting_for_gross)
async def process_gross(message: types.Message, state: FSMContext):
    try:
        gross = float(message.text.replace(',', '.'))
    except ValueError:
        await message.answer("Введи число:")
        return
    await state.update_data(gross=gross)
    await message.answer("📉 Комиссия ($) или 0:")
    await state.set_state(TripStates.waiting_for_commission)

@dp.message(TripStates.waiting_for_commission)
async def process_commission(message: types.Message, state: FSMContext):
    try:
        commission = float(message.text.replace(',', '.'))
    except ValueError:
        await message.answer("Введи число:")
        return
    
    data = await state.get_data()
    deadhead = data["deadhead"]
    loaded = data["loaded"]
    total = deadhead + loaded
    gross = data["gross"]
    net = gross - commission
    
    row_data = {
        "user_id": message.from_user.id,
        "type": "trip",
        "origin": data["origin"],
        "destination": data["destination"],
        "deadhead": deadhead,
        "loaded": loaded,
        "total_miles": total,
        "gross": gross,
        "commission": commission,
        "net": net,
        "category": None,
        "amount": None,
        "description": f"Trip from {data['origin']} to {data['destination']}"
    }
    
    success = save_to_supabase(row_data)
    await state.clear()
    
    if success:
        await message.answer(f"✅ Поездка сохранена в Supabase!\nМаршрут: {data['origin']} ➔ {data['destination']}\nЧистыми: ${net:.2f}")
    else:
        await message.answer("❌ Ошибка сохранения поездки в облачную базу.")

# --- СЦЕНАРИЙ РАСХОДОВ С КНОПКАМИ ---
@dp.message(F.text == "💸 Добавить расход")
async def start_expense(message: types.Message):
    builder = InlineKeyboardBuilder()
    builder.button(text="⛽ Топливо", callback_data="cat_Топливо")
    builder.button(text="🔧 Ремонт", callback_data="cat_Ремонт")
    builder.button(text="📦 Еквипент", callback_data="cat_Еквипент")
    builder.button(text="🛡️ Страховка", callback_data="cat_Страховка")
    builder.button(text="🛞 Трейлер", callback_data="cat_Трейлер")
    builder.button(text="🚛 Трак", callback_data="cat_Трак")
    builder.button(text="📌 Прочие расходы", callback_data="cat_Прочие")
    builder.adjust(2, 2, 2, 1)
    
    await message.answer("📂 Выбери категорию расхода:", reply_markup=builder.as_markup())

@dp.callback_query(F.data.startswith("cat_"))
async def process_category_callback(callback: types.CallbackQuery, state: FSMContext):
    category = callback.data.split("_", 1)[1]
    if category == "Прочие":
        category = "Прочие расходы"
    await state.update_data(category=category)
    
    await callback.message.edit_text(f"📂 Категория: <b>{category}</b>\n\n💵 Введи сумму расхода ($):", parse_mode="HTML")
    await state.set_state(ExpenseStates.waiting_for_amount)
    await callback.answer()

@dp.message(ExpenseStates.waiting_for_amount)
async def process_expense_amount(message: types.Message, state: FSMContext):
    try:
        amount = float(message.text.replace(',', '.'))
    except ValueError:
        await message.answer("⚠️ Пожалуйста, введи число (сумму):")
        return
    await state.update_data(amount=amount)
    await message.answer("📝 Введи описание (или напиши `-`):")
    await state.set_state(ExpenseStates.waiting_for_description)

@dp.message(ExpenseStates.waiting_for_description)
async def process_expense_description(message: types.Message, state: FSMContext):
    data = await state.get_data()
    row_data = {
        "user_id": message.from_user.id,
        "type": "expense",
        "origin": None,
        "destination": None,
        "deadhead": None,
        "loaded": None,
        "total_miles": None,
        "gross": None,
        "commission": None,
        "net": None,
        "category": data["category"],
        "amount": data["amount"],
        "description": message.text
    }
    
    success = save_to_supabase(row_data)
    await state.clear()
    
    if success:
        await message.answer(f"✅ Расход записан в Supabase!\nКатегория: {data['category']}\nСумма: ${data['amount']:.2f}\nОписание: {message.text}")
    else:
        await message.answer("❌ Ошибка сохранения расхода в облачную базу.")

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
