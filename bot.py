import os
import logging
import asyncio
from datetime import datetime, timedelta
from aiohttp import web
from aiogram import Bot, Dispatcher, F, Router
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from supabase import create_client, Client
from geopy.geocoders import Nominatim
from geopy.distance import geodesic

logging.basicConfig(level=logging.INFO)

TELEGRAM_TOKEN = "8905023648:AAE_zcvaHwUj4WLlOcCsFleS8MEpQvLKWvY"
SUPABASE_URL = "https://ooerygxpdhhvpueoclgs.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im9vZXJ5Z3hwZGhodnB1ZW9jbGdzIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc5MTM0NDc4NywiZXhwIjoyMTA2OTIwNzg3fQ.AQUWaeOHOUNR7g_H1kalDooLuyY_aPV8JdwQOm3R8a4"
PORT = 10000

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
geolocator = Nominatim(user_agent="truck_expenses_bot_2026")

bot = Bot(token=TELEGRAM_TOKEN)
router = Router()

class RecordState(StatesGroup):
    expense_category = State()
    expense_amount = State()
    expense_desc = State()
    
    trip_origin = State()
    trip_destination = State()
    trip_deadhead = State()
    trip_gross = State()
    trip_desc = State()

def main_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💸 Добавить расход", callback_data="add_expense")],
        [InlineKeyboardButton(text="🚛 Добавить поездку", callback_data="add_trip")],
        [InlineKeyboardButton(text="📊 Статистика за неделю", callback_data="week_stats")]
    ])

@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "🚛 Бот запущен! Автоматический расчет миль и $/mile активен. Выбирай действие:",
        reply_markup=main_menu()
    )

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

@router.callback_query(F.data == "add_trip")
async def process_trip(callback: CallbackQuery, state: FSMContext):
    await state.set_state(RecordState.trip_origin)
    await callback.message.edit_text("📍 Введи адрес отправления (например: `Seattle, WA`):")
    await callback.answer()

@router.message(RecordState.trip_origin)
async def trip_origin_entered(message: Message, state: FSMContext):
    await state.update_data(origin=message.text)
    await state.set_state(RecordState.trip_destination)
    await message.answer("🏁 Введи адрес назначения (например: `Portland, OR`):")

@router.message(RecordState.trip_destination)
async def trip_destination_entered(message: Message, state: FSMContext):
    await state.update_data(destination=message.text)
    await state.set_state(RecordState.trip_deadhead)
    await message.answer("🚛 Введи пустые мили (Deadhead miles) если есть, или напиши `0`:")

@router.message(RecordState.trip_deadhead)
async def trip_deadhead_entered(message: Message, state: FSMContext):
    try:
        deadhead = float(message.text.replace(",", "."))
    except ValueError:
        await message.answer("❌ Введи число для пустых миль (например, 0 или 45):")
        return
    
    await state.update_data(deadhead=deadhead)
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
    origin_str = data["origin"]
    destination_str = data["destination"]
    deadhead = data["deadhead"]
    
    loaded = 0.0
    try:
        loc1 = geolocator.geocode(origin_str.strip(), country_codes="us")
        loc2 = geolocator.geocode(destination_str.strip(), country_codes="us")
        
        if loc1 and loc2:
            coords1 = (loc1.latitude, loc1.longitude)
            coords2 = (loc2.latitude, loc2.longitude)
            straight_miles = geodesic(coords1, coords2).miles
            loaded = round(straight_miles * 1.2, 1)
        else:
            loaded = 100.0
    except Exception as e:
        logging.error(f"Geocoding error: {e}")
        loaded = 100.0

    total_miles = round(deadhead + loaded, 1)
    commission = round(gross * 0.12, 2)
    net = round(gross - commission, 2)
    rate_per_mile = round(gross / total_miles, 2) if total_miles > 0 else 0.0
    
    await state.update_data(
        loaded=loaded, 
        total_miles=total_miles, 
        gross=gross, 
        commission=commission, 
        net=net,
        rate_per_mile=rate_per_mile
    )
    await state.set_state(RecordState.trip_desc)
    await message.answer(
        f"📊 Автоматический расчет:\n"
        f"• Маршрут: {origin_str} ➡️ {destination_str}\n"
        f"• Пустые: {deadhead} | Груженые: {loaded}\n"
        f"• Всего миль: {total_miles}\n"
        f"• Гросс: ${gross:.2f}\n"
        f"• Ставка за милю: ${rate_per_mile:.2f}/mi\n"
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
        "origin": str(data["origin"]),
        "destination": str(data["destination"]),
        "deadhead": float(data["deadhead"]),
        "loaded": float(data["loaded"]),
        "total_miles": float(data["total_miles"]),
        "gross": float(data["gross"]),
        "commission": float(data["commission"]),
        "net": float(data["net"]),
        "rate_per_mile": float(data["rate_per_mile"]),
        "description": str(desc)
    }
    
    try:
        supabase.table("truck_records").insert(record_data).execute()
        total_m = data['total_miles']
        rate_m = data['rate_per_mile']
        net_v = data['net']
        await message.answer(
            f"✅ Поездка сохранена!\nВсего миль: {total_m} | Ставка: ${rate_m:.2f}/mi \vert{} Net:${net_v:.2f}",
            reply_markup=main_menu()
        )
    except Exception as e:
        logging.error(f"Supabase error (trip): {e}")
        await message.answer(f"❌ Ошибка сохранения поездки: {e}")
    
    await state.clear()

@router.callback_query(F.data == "week_stats")
async def show_week_stats(callback: CallbackQuery):
    try:
        now = datetime.utcnow()
        start_of_week = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
        
        response = supabase.table("truck_records").select("*").gte("created_at", start_of_week.isoformat()).execute()
        records = response.data
        
        if not records:
            await callback.message.edit_text(
                "📊 **Статистика за текущую неделю:**\nЗаписей пока нет.",
                reply_markup=main_menu(),
                parse_mode="Markdown"
            )
            await callback.answer()
            return

        total_gross = 0.0
        total_net = 0.0
        total_expenses = 0.0
        total_miles = 0.0
        trips_count = 0
        expenses_breakdown = {}

        for r in records:
            if r.get("record_type") == "trip":
                total_gross += float(r.get("gross", 0) or 0)
                total_net += float(r.get("net", 0) or 0)
                total_miles += float(r.get("total_miles", 0) or 0)
                trips_count += 1
            elif r.get("record_type") == "expense":
                amount = float(r.get("amount", 0) or 0)
                total_expenses += amount
                cat = r.get("category", "Прочие")
                expenses_breakdown[cat] = expenses_breakdown.get(cat, 0.0) + amount

        avg_rate = round(total_gross / total_miles, 2) if total_miles > 0 else 0.0
        profit_after_expenses = total_net - total_expenses

        exp_text = "".join([f"  • {cat}: ${amt:.2f}\n" for cat, amt in expenses_breakdown.items()]) or "  • Нет расходов\n"

        report = (
            f"📊 **Статистика за текущую неделю:**\n\n"
            f"🚛 Рейсов: {trips_count} | Общий пробег: {total_miles:.1f} миль\n"
            f"💰 Гросс: **${total_gross:.2f}**\n"
            f"📉 Средняя ставка: **${avg_rate:.2f}/mi**\n"
            f"💵 Чистыми (Net после 12%): **${total_net:.2f}**\n\n"
            f"🛠 **Расходы:**\n{exp_text}"
            f"📦 Всего расходов: **${total_expenses:.2f}**\n\n"
            f"💎 **Итого на руках (Net - Расходы):** **${profit_after_expenses:.2f}**"
        )

        await callback.message.edit_text(report, reply_markup=main_menu(), parse_mode="Markdown")
        await callback.answer()
    except Exception as e:
        logging.error(f"Stats error: {e}")
        await callback.message.edit_text(f"❌ Ошибка при получении статистики: {e}", reply_markup=main_menu())
        await callback.answer()

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
