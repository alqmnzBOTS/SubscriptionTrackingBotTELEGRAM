# Бот создан для некоммерческого использования
# Автор: Ваше Имя (GitHub: alqmnzBOTS)

import os
import logging
from datetime import datetime, timedelta, date
import csv
import asyncio
from typing import List, Tuple

from aiogram import Bot, Dispatcher, types, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.utils.keyboard import ReplyKeyboardBuilder, InlineKeyboardBuilder
from aiogram.types import FSInputFile, InlineKeyboardButton, InlineKeyboardMarkup
from dotenv import load_dotenv
from pyexpat.errors import messages
from sqlalchemy import create_engine, Column, Integer, String, Float, Date, Enum
from sqlalchemy.orm import sessionmaker, declarative_base, Session
from sqlalchemy.exc import SQLAlchemyError
import enum

# Конфигурация и настройка
load_dotenv()

# Константа имени создателя на GitHub
CREATOR_GITHUB = "alqmnzBOTS"

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Инициализация бота
bot = Bot(token=os.getenv("BOT_TOKEN"))
dp = Dispatcher(storage=MemoryStorage())

# База данных (SQLite с SQLAlchemy)
Base = declarative_base()

class Period(enum.Enum):
    MONTHLY = 'monthly'
    YEARLY = 'yearly'

class Subscription(Base):
    __tablename__ = "subscriptions"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, index=True)
    name = Column(String(100), nullable=False)
    amount = Column(Float, nullable=False)
    period = Column(Enum(Period), nullable=False)
    next_payment = Column(Date, nullable=False)

# Инициализация БД
engine = create_engine('sqlite:///subscriptions.db')
Base.metadata.create_all(engine)
Session = sessionmaker(bind=engine)

# FSM (Finite State Machine) для добавления подписок
class AddSubscription(StatesGroup):
    NAME = State()
    AMOUNT = State()
    PERIOD = State()
    NEXT_PAYMENT = State()

# Вспомогательные функции
def calculate_monthly_cost(amount: float, period: Period) -> float:
    """Рассчитывает месячную стоимость подписки"""
    return amount if period == Period.MONTHLY else amount / 12

async def get_user_subscriptions(user_id: int) -> List[Subscription]:
    """Возвращает все подписки пользователя"""
    with Session() as session:
        return session.query(Subscription).filter(Subscription.user_id == user_id).all()

async def save_subscription(user_id: int, data: dict) -> None:
    """Сохраняет подписку в БД"""
    with Session() as session:
        subscription = Subscription(
            user_id=user_id,
            name=data['name'],
            amount=data['amount'],
            period=data['period'],
            next_payment=data['next_payment']
        )
        session.add(subscription)
        session.commit()

def generate_monthly_report(subscriptions: List[Subscription]) -> str:
    """Генерирует текстовый отчет за месяц"""
    report = "📊 Отчет за текущий месяц:\n\n"
    total_monthly = 0.0

    for sub in subscriptions:
        monthly_cost = calculate_monthly_cost(sub.amount, sub.period)
        total_monthly += monthly_cost

        # Показываем только актуальные подписки
        if sub.next_payment.month == datetime.now().month:
            report += f"• {sub.name}: {monthly_cost:.2f} ₽/мес\n"

    report += f"\n💳 Итого в месяц: {total_monthly:.2f} ₽"
    return report

async def export_to_csv(user_id: int) -> str:
    """Экспортируем данные в CSV-файл"""
    filename = f"subscriptions_{user_id}.csv"
    subscriptions = await get_user_subscriptions(user_id)

    with open(filename, 'w', newline='', encoding='utf-8') as file:
        writer = csv.writer(file)
        writer.writerow(['Название', 'Сумма', 'Период', 'След. списание'])

        for sub in subscriptions:
            writer.writerow([
                sub.name,
                sub.amount,
                sub.period.value,
                sub.next_payment.strftime("%Y-%m-%d")
            ])
    return filename

async def check_pending_payments():
    """Проверяет предстояящие платежи и отправляет уведомления"""
    now = datetime.now().date()
    tomorrow = now + timedelta(days=1)

    with Session() as session:
        subscriptions = session.query(Subscription).filter(
            Subscription.next_payment == tomorrow
        ).all()

        for sub in subscriptions:
            message = (
                f"🔔 Напоминание о платеже!\n\n"
                f"Завтра ({tomorrow.strftime('%d.%m.%Y')}) будет списано:\n"
                f"• {sub.name}: {sub.amount} ₽"
            )
            await bot.send_message(sub.user_id, message)

# Планироващик задач
async def scheduler():
    """Запускает фоновые задачи"""
    while True:
        now = datetime.now()

        # Проверка в 10:00 каждый день
        if now.hour == 10 and now.minute == 0:
            await check_pending_payments()

        # Отправка отчётов 1-го числа каждого месяца
        if now.day == 1 and now.hour == 9 and now.minute == 0:
            with Session() as session:
                users = session.query(Subscription.user_id).distinct().all()
                for user_id in users:
                    subscriptions = await get_user_subscriptions(user_id[0])
                    if subscriptions:
                        report = generate_monthly_report(subscriptions)
                        await bot.send_message(user_id[0], report)
        await asyncio.sleep(60)

# Обработчики команд
@dp.message(F.text == "/start")
async def cmd_start(message: types.Message):
    """Приветственное сообщение"""
    welcome_text = (
        f"👋 Привет, {message.from_user.first_name}!\n"
        "Я помогу отслеживать твои подписки (Netflix, Spotify и др.)\n\n"
        "✨ Возможности:\n"
        "- Добавлять и удалять подписки\n"
        "- Напоминать о предстоящих платежах\n"
        "- Показывать общие расходы\n"
        "- Формировать месячные отчеты\n"
        "- Экспортировать данные в CSV\n\n"
        f"⚠️ Бот создан для некоммерческого использования\n"
        f"Создатель: github.com/{CREATOR_GITHUB}\n\n"
        "Используй команды:\n"
        "/add - добавить подписку\n"
        "/delete - удалить подписку\n"
        "/list - мои подписки\n"
        "/total - общая сумма\n"
        "/report - отчет за месяц\n"
        "/export - экспорт данных"
    )
    await message.answer(welcome_text)

@dp.message(F.text == "/add")
async def cmd_add(message: types.Message, state: FSMContext):
    """Начало процесса добавления подписки"""
    await message.answer("Введи название подписки (например, Netflix):")
    await state.set_state(AddSubscription.NAME)

@dp.message(AddSubscription.NAME)
async def process_name(message: types.Message, state: FSMContext):
    """Обработка названия подписки"""
    await state.update_data(name=message.text)
    await message.answer("Введи стоимость подписки (например, 599):")
    await state.set_state(AddSubscription.AMOUNT)

@dp.message(AddSubscription.AMOUNT)
async def process_amount(message: types.Message, state: FSMContext):
    """Обработка стоимости подписки"""
    try:
        amount = float(message.text.replace(',', '.'))
        if amount <= 0:
            raise ValueError
        await state.update_data(amount=amount)

        # Клавиатура для выбора периода
        builder = ReplyKeyboardBuilder()
        builder.add(types.KeyboardButton(text="Ежемесячно"))
        builder.add(types.KeyboardButton(text="Ежегодно"))
        builder.adjust(2)

        await message.answer(
            "Выбери период оплаты:",
            reply_markup=builder.as_markup(resize_keyboard=True)
        )
        await state.set_state(AddSubscription.PERIOD)
    except ValueError:
        await message.answer("Пожалуйста, введи корректную сумму (число больше 0):")

@dp.message(AddSubscription.PERIOD)
async def process_period(message: types.Message, state: FSMContext):
    """Обработка периода подписки"""
    period_map = {
        "ежемесячно": Period.MONTHLY,
        "ежегодно": Period.YEARLY
    }

    period = period_map.get(message.text.lower())
    if not period:
        await message.answer("Пожалуйста, выбери вариант из клавиатуры:")
        return

    await state.update_data(period=period)
    await message.answer(
        "Введи дату следующего платежа в формате ГГГГ-ММ-ДД\n(например, 2023-12-01):",
        reply_markup=types.ReplyKeyboardRemove()
    )
    await state.set_state(AddSubscription.NEXT_PAYMENT)

@dp.message(AddSubscription.NEXT_PAYMENT)
async def process_next_payment(message: types.Message, state: FSMContext):
    """Обработка даты платежа и сохранение подписки"""
    try:
        payment_date = datetime.strptime(message.text, "%Y-%m-%d").date()
        if payment_date < date.today():
            await message.answer("Дата не может быть в прошлом! Введи корректную дату:")
            return

        data = await state.get_data()
        await save_subscription(message.from_user.id, data | {"next_payment": payment_date})
        await message.answer(
            f"✅ Подписка {data['name']} успешно добавлена!\n"
            f"Следующий платеж: {payment_date.strftime('%d.%m.%Y')}"
        )
        await state.clear()
    except ValueError:
        await message.answer("Неверный формат даты! Используй формат ГГГГ-ММ-ДД:")

@dp.message(F.text == "/list")
async def cmd_list(message: types.Message):
    """Показывает все подписки пользователя"""
    subscriptions = await get_user_subscriptions(message.from_user.id)
    if not subscriptions:
        await message.answer("У тебя пока нет активных подписок")
        return

    response = "📋 Твои подписки:\n\n"
    for sub in subscriptions:
        period = "мес" if sub.period == Period.MONTHLY else "год"
        response += (
            f"• {sub.name}: {sub.amount} ₽/{period}\n"
            f"  След. платеж: {sub.next_payment.strftime('%d.%m.%Y')}\n\n"
        )
    await message.answer(response)

@dp.message(F.text == "/total")
async def cmd_total(message: types.Message):
    """Рассчитывает общую сумму подписок"""
    subscriptions = await get_user_subscriptions(message.from_user.id)
    if not subscriptions:
        await message.answer("У тебя пока нет активных подписок.")
        return

    total_monthly = sum(
        calculate_monthly_cost(sub.amount, sub.period)
        for sub in subscriptions
    )

    await message.answer(
        f"💳 Общая сумма всех подписок:\n"
        f"• В месяц: {total_monthly:.2f} ₽\n"
        f"• В год: {total_monthly * 12:.2f} ₽"
    )

@dp.message(F.text == "/report")
async def cmd_report(message: types.Message):
    """Генерирует месячный отчёт"""
    subscriptions = await get_user_subscriptions(message.from_user.id)
    if not subscriptions:
        await message.answer("У тебя пока нет активных подписок")
        return

    report = generate_monthly_report(subscriptions)
    await message.answer(report)

@dp.message(F.text == "/delete")
async def cmd_delete(message: types.Message):
    """Показывает подписки для удаления"""
    subscriptions = await get_user_subscriptions(message.from_user.id)
    if not subscriptions:
        await message.answer("У тебя пока нет активных подписок для удаления")
        return
    builder = InlineKeyboardBuilder()
    for sub in subscriptions:
        builder.add(types.InlineKeyboardButton(
            text=f"{sub.name} - {sub.amount}₽",
            callback_data=f"delete_{sub.id}"
        ))
    builder.adjust(1)

    await message.answer(
        "Выбери подписку для удаления:",
        reply_markup=builder.as_markup()
    )

@dp.callback_query(F.data.startswith("delete_"))
async def delete_subscription(callback: types.CallbackQuery):
    """Обрабатывает удаление подписки"""
    sub_id = int(callback.data.split("_")[1])

    with Session() as session:
        subscription = session.get(Subscription, sub_id)

        # Проверяем, что подписка принадлежит пользователю
        if subscription and subscription.user_id == callback.from_user.id:
            session.delete(subscription)
            session.commit()
            await callback.message.edit_text(
                f"❌ Подписка {subscription.name} успешно удалена!"
            )
        else:
            await callback.answer("Подписка не найдена или недоступна", show_alert=True)

    await callback.answer()

@dp.message(F.text == "/export")
async def cmd_export(message: types.Message):
    """Экспортируем данные в CSV"""
    try:
        filename = await export_to_csv(message.from_user.id)
        file = FSInputFile(filename)
        await message.answer_document(file, caption="Твои подписки в формате CVS")
        os.remove(filename) # Удаляем временный файл
    except Exception as e:
        logger.error(f"Export error: {e}")
        await message.answer("Произошла ошибка при эскпорте данных. Попробуй позже.")

# Запуск приложения
async def main():
    """Основная функция запуска"""
    logger.info("Starting bot...")
    asyncio.create_task(scheduler())
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
