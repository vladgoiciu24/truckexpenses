import logging
import asyncio
from aiohttp import web
from aiogram import Bot, Dispatcher, F, Router
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from supabase import create_client, Client

# Настройка логирования
logging.basicConfig(level=logging.INFO)

# Конфигурация
TELEGRAM_TOKEN = "8905023648:AAE_zcvaHwUj4WLlOcCsFleS8MEpQvLKWvY"
SUPABASE_URL = "https://ooerygxpdhhvpueoclgs.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im9vZXJ5Z3hwZGhodnB1ZW9jbGdzIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc5MTM0NDc4NywiZXhwIjoyMTA2OTIwNzg3fQ.AQUWaeOHOUNR7g_H1kalDooLuyY_aPV8JdwQOm3R8a4"
PORT = 10000

# Инициализация Supabase
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

bot = Bot(token=TELEGRAM_TOKEN)
router = Router()

# Состояния FSM
class RecordState(StatesGroup):
    expense_category = State()
    expense_amount = State()
    expense_desc = State()
    
    trip_deadhead = State()
    trip_loaded = State()
    trip_gross = State()
    trip_desc = State()

def main_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💸 Добавить расход", callback_data="add_expense")],
        [InlineKeyboardButton(text="🚛 Добавить поездку", callback_data="add_trip")]
    ])

@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "🚛 Бот готов к работе! Выбирай действие:",
        reply_markup=main_menu()
    )

# --- РАСХОДЫ ---
@router.callback_query(F.data == "add_expense")
async def process_expense(callback: CallbackQuery, state: FSMContext):
    await state.set_state(RecordState.expense_category)
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⛽ Топливо", callback_data="exp_Топливо")],
        [InlineKeyboardButton(text="🛠 Ремонт", callback_data="exp_Ремонт")],
        [InlineKeyboardButton(text="🧰 Еквипент", callback_data="exp_Еквипент")],
        [InlineKeyboardButton(text="🛡 Страховка", callback_data="exp_Страховка")],
        [InlineKeyboardButton(text="🅿️ Трейлер", callback_data="exp_Трейлер")],
        [InlineKeyboardButton(text="🚛 Трак", callback_data="exp_Трак")],
        [InlineKeyboardButton(text="📦 Прочие расходы", callback_data="exp_Прочие")]
    ])
    await callback.message.edit_text("📁 Выбери категорию расхода:", reply_markup=keyboard)
    await callback.answer()

@router.callback_query(F.data.startswith("exp_"))
async def expense_category_chosen(callback: CallbackQuery, state: FSMContext):
    category = callback.data.replace("exp_", "", 1)
    await state.update_data(category=category)
    await state.set_state(RecordState.expense_amount)
    await callback.message.edit_text(f"📁 Категория: {category}\n\n💵 Введи сумму расхода ($):")
    await callback.answer()

@router.message(RecordState.expense_amount)
async def expense_amount_entered(message: Message, state: FSMContext):
    try:
        amount = float(message.text.replace(",", "."))
    except ValueError:
        await message.answer("❌ Неверный формат. Введи число (например, 150 или 45.50):")
        return
    
    await state.update_data(amount=amount)
    await state.set_state(RecordState.expense_desc)
    await message.answer("📝 Введи описание (или напиши `-`):")

@router.message(RecordState.expense_desc)
async def expense_desc_entered(message: Message, state: FSMContext):
    desc = message.text if message.text != "-" else ""
    data = await state.get_data()
    
    record_data = {
        "user_id": str(message.from_user.id),
        "record_type": "expense",
        "category": str(data["category"]),
        "amount": float(data["amount"]),
        "description": str(desc)
    }
    
    try:
        supabase.table("truck_records").insert(record_data).execute()
        await message.answer("✅ Расход успешно сохранен в базу!", reply_markup=main_menu())
    except Exception as e:
        logging.error(f"Supabase error (expense): {e}")
        await message.answer(f"❌ Ошибка сохранения расхода: {e}")
    
    await state.clear()


# --- ПОЕЗДКИ ---
@router.callback_query(F.data == "add_trip")
async def process_trip(callback: CallbackQuery, state: FSMContext):
    await state.set_state(RecordState.trip_deadhead)
    await callback.message.edit_text("🚛 Введи пустые мили (Deadhead miles) или 0:")
    await callback.answer()

@router.message(RecordState.trip_deadhead)
async def trip_deadhead_entered(message: Message, state: FSMContext):
    try:
        deadhead = float(message.text.replace(",", "."))
    except ValueError:
        await message.answer("❌ Введи число для пустых миль:")
        return
    
    await state.update_data(deadhead=deadhead)
    await state.set_state(RecordState.trip_loaded)
    await message.answer("🚚 Введи грузовые мили (Loaded miles):")

@router.message(RecordState.trip_loaded)
async def trip_loaded_entered(message: Message, state: FSMContext):
    try:
        loaded = float(message.text.replace(",", "."))
    except ValueError:
        await message.answer("❌ Введи число для груженых миль:")
        return
    
    await state.update_data(loaded=loaded)
    await state.set_state(RecordState.trip_gross)
    await message.answer("💰 Введи сумму Гросс ($):")

@router.message(RecordState.trip_gross)
async def trip_gross_entered(message: Message, state: FSMContext):
    try:
        gross = float(message.text.replace(",", "."))
    except ValueError:
        await message.answer("❌ Введи число для суммы Гросс:")
        return
    
    data = await state.get_data()
    deadhead = data["deadhead"]
    loaded = data["loaded"]
    
    total_miles = deadhead + loaded
    commission = round(gross * 0.12, 2)
    net = round(gross - commission, 2)
    
    await state.update_data(gross=gross, total_miles=total_miles, commission=commission, net=net)
    await state.set_state(RecordState.trip_desc)
    await message.answer(
        f"📊 Автоматический расчет:\n"
        f"• Всего миль: {total_miles}\n"
        f"• Гросс: ${gross:.2f}\n"
        f"• Комиссия (12%): ${commission:.2f}\n"
        f"• Чистыми (Net): ${net:.2f}\n\n"
        f"📝 Введи примечание к рейсу (или напиши `-`):"
    )

@router.message(RecordState.trip_desc)
async def trip_desc_entered(message: Message, state: FSMContext):
    desc = message.text if message.text != "-" else ""
    data = await state.get_data()
    
    record_data = {
        "user_id": str(message.from_user.id),
        "record_type": "trip",
        "deadhead": float(data["deadhead"]),
        "loaded": float(data["loaded"]),
        "total_miles": float(data["total_miles"]),
        "gross": float(data["gross"]),
        "commission": float(data["commission"]),
        "net": float(data["net"]),
        "description": str(desc)
    }
    
    try:
        supabase.table("truck_records").insert(record_data).execute()
        await message.answer(
            f"✅ Поездка успешно сохранена!\n"
            f"Net: ${data['net']:.2f} (Гросс: ${data['gross']:.2f} минус комиссия 12%)",
            reply_markup=main_menu()
        )
    except Exception as e:
        logging.error(f"Supabase error (trip): {e}")
        await message.answer(f"❌ Ошибка сохранения поездки: {e}")
    
    await state.clear()


# Health check для Render
async def handle(request):
    return web.Response(text="Bot is running!")

async def web_server():
    app = web.Application()
    app.router.add_get("/", handle)
    runner = web.AppRunner(app)
    await runner.setup()
    tcpsite = web.TCPSite(runner, "0.0.0.0", PORT)
    await tcpsite.start()

async def main():
    dp = Dispatcher()
    dp.include_router(router)
    
    await bot.delete_webhook(drop_pending_updates=True)
    
    await asyncio.gather(
        web_server(),
        dp.start_polling(bot)
    )

if __name__ == "__main__":
    asyncio.run(main())
