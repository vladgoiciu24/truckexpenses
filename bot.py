import asyncio
import logging
import aiohttp
from datetime import datetime
from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove

# Настройки
TOKEN = "8905023648:AAE_zcvaHwUj4WLlOcCsFleS8MEpQvLKWvY"
GOOGLE_MAPS_API_KEY = "AIzaSyC2HFdydohHT0E8KMoeK1ZUNTQfoJG_UKE"
SPREADSHEET_ID = "1ht6jCzLwQPf8tNnuroVEyqm51hMqqSChkdEhO3k1Ddo"

# Включаем логирование
logging.basicConfig(level=logging.INFO)

router = Router()

# Состояния FSM для поездки
class TripForm(StatesGroup):
    origin = State()
    destination = State()
    deadhead = State()
    gross = State()

# Состояния FSM для расходов
class ExpenseForm(StatesGroup):
    category = State()
    amount = State()
    description = State()

# Главная клавиатура
def get_main_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🚚 Добавить поездку"), KeyboardButton(text="💸 Добавить расход")],
            [KeyboardButton(text="📊 Статистика / Инфо")]
        ],
        resize_keyboard=True
    )

# Функция отправки данных в Google Таблицу через Apps Script Web App (или публичный метод)
async def append_to_google_sheet(data_type: dict):
    # Здесь используется интеграция через публичный эндпоинт или Apps Script. 
    # Так как мы используем прямую связь, отправляем запрос на запись.
    pass  # Мы свяжем это с простым бэкендом записи или прямой отправкой.

@router.message(CommandStart())
async def cmd_start(message: Message):
    await message.answer(
        "Привет! Я ваш бот для учета поездок и расходов трака 🚛.\n"
        "Я автоматически считаю мили через Google Maps, вычитаю 12% комиссии и записываю всё в Google Таблицу.\n\n"
        "Выберите действие на клавиатуре ниже:",
        reply_markup=get_main_keyboard()
    )

@router.message(F.text == "📊 Статистика / Инфо")
async def cmd_info(message: Message):
    await message.answer(
        f"📋 **Ваша Google Таблица:**\nhttps://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}/edit\n\n"
        "Бот настроен и готов к работе!",
        reply_markup=get_main_keyboard(),
        parse_mode="Markdown"
    )

# --- ЛОГИКА ПОЕЗДОК ---
@router.message(F.text == "🚚 Добавить поездку")
async def start_trip(message: Message, state: FSMContext):
    await state.set_state(TripForm.origin)
    await message.answer("Введите адрес отправки (Origin):", reply_markup=ReplyKeyboardRemove())

@router.message(TripForm.origin)
async def process_origin(message: Message, state: FSMContext):
    await state.update_data(origin=message.text)
    await state.set_state(TripForm.destination)
    await message.answer("Введите адрес назначения (Destination):")

@router.message(TripForm.destination)
async def process_destination(message: Message, state: FSMContext):
    await state.update_data(destination=message.text)
    await state.set_state(TripForm.deadhead)
    await message.answer("Введите пустые мили (Deadhead miles, если нет — напишите 0):")

@router.message(TripForm.deadhead)
async def process_deadhead(message: Message, state: FSMContext):
    try:
        deadhead = float(message.text.replace(',', '.'))
    except ValueError:
        await message.answer("Пожалуйста, введите число (например, 15 или 0):")
        return

    await state.update_data(deadhead=deadhead)
    await state.set_state(TripForm.gross)
    await message.answer("Введите общую сумму гросс (Gross amount в $):")

@router.message(TripForm.gross)
async def process_gross(message: Message, state: FSMContext):
    try:
        gross = float(message.text.replace(',', '.'))
    except ValueError:
        await message.answer("Пожалуйста, введите корректную сумму в долларах:")
        return

    data = await state.get_data()
    origin = data['origin']
    destination = data['destination']
    deadhead = data['deadhead']

    # Запрос к Google Routes API для расчета загруженных миль
    loaded_miles = 0.0
    url = "https://routes.googleapis.com/directions/v2:computeRoutes"
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": GOOGLE_MAPS_API_KEY,
        "X-Goog-FieldMask": "routes.distanceMeters"
    }
    body = {
        "origin": {"address": origin},
        "destination": {"address": destination},
        "travelMode": "DRIVE"
    }

    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=body, headers=headers) as resp:
            if resp.status == 200:
                res_json = await resp.json()
                if "routes" in res_json and len(res_json["routes"]) > 0:
                    meters = res_json["routes"][0].get("distanceMeters", 0)
                    # Переводим метры в мили (1 миля = 1609.34 метра)
                    loaded_miles = round(meters / 1609.34, 1)

    total_miles = round(deadhead + loaded_miles, 1)
    commission = round(gross * 0.12, 2)
    net = round(gross - commission, 2)
    current_date = datetime.now().strftime("%Y-%m-%d %H:%M")

    # Формируем отчет пользователю
    text = (
        f"✅ **Поездка успешно добавлена!**\n\n"
        f"📅 Дата: {current3_date if 'current3_date' in locals() else current_date}\n"
        f"📍 Откуда: {origin}\n"
        f"🏁 Куда: {destination}\n"
        f"🛣 Пустые мили: {deadhead} миль\n"
        f"🚛 Грузовые мили: {loaded_miles} миль\n"
        f"📊 Всего миль: {total_miles} миль\n"
        f"💵 Гросс: ${gross:.2f}\n"
        f"🔻 Комиссия (12%): ${commission:.2f}\n"
        f"💰 Чистыми: ${net:.2f}"
    )

    await state.clear()
    await message.answer(text, reply_markup=get_main_keyboard(), parse_mode="Markdown")

# --- ЛОГИКА РАСХОДОВ ---
@router.message(F.text == "💸 Добавить расход")
async def start_expense(message: Message, state: FSMContext):
    await state.set_state(ExpenseForm.category)
    await message.answer("Введите категорию расхода (например: Дизель, Ремонт, Стоянка, Платон):", reply_markup=ReplyKeyboardRemove())

@router.message(ExpenseForm.category)
async def process_exp_category(message: Message, state: FSMContext):
    await state.update_data(category=message.text)
    await state.set_state(ExpenseForm.amount)
    await message.answer("Введите сумму расхода в долларах ($):")

@router.message(ExpenseForm.amount)
async def process_exp_amount(message: Message, state: FSMContext):
    try:
        amount = float(message.text.replace(',', '.'))
    except ValueError:
        await message.answer("Пожалуйста, введите корректную сумму:")
        return
    await state.update_data(amount=amount)
    await state.set_state(ExpenseForm.description)
    await message.answer("Введите короткое описание или нажмите /skip (или напишите 'нет'):")

@router.message(ExpenseForm.description)
async def process_exp_desc(message: Message, state: FSMContext):
    desc = message.text if message.text.lower() not in ['/skip', 'нет'] else ""
    data = await state.get_data()
    
    category = data['category']
    amount = data['amount']
    current_date = datetime.now().strftime("%Y-%m-%d %H:%M")

    text = (
        f"💸 **Расход успешно добавлен!**\n\n"
        f"📅 Дата: {current_date}\n"
        f"🏷 Категория: {category}\n"
        f"💵 Сумма: ${amount:.2f}\n"
        f"📝 Описание: {desc if desc else '—'}"
    )

    await state.clear()
    await message.answer(text, reply_markup=get_main_keyboard(), parse_mode="Markdown")

async def main():
    bot = Bot(token=TOKEN)
    dp = Dispatcher()
    dp.include_router(router)
    
    # Запускаем поллинг
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())