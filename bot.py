import os
import logging
import asyncio
import sqlite3
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from openai import OpenAI
from gnews import GNews

# ---------- НАСТРОЙКИ ----------
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

SUPPORTED_COINS = ["BTC", "ETH", "SOL", "ADA", "DOT", "XRP", "DOGE", "MATIC", "BNB", "LTC"]

# ---------- БАЗА ДАННЫХ ----------
def init_db():
    conn = sqlite3.connect('subscriptions.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        subscribed_until TEXT,
        trial_used BOOLEAN DEFAULT 0
    )''')
    conn.commit()
    conn.close()

def is_trial_used(user_id):
    conn = sqlite3.connect('subscriptions.db')
    c = conn.cursor()
    c.execute("SELECT trial_used FROM users WHERE user_id=?", (user_id,))
    result = c.fetchone()
    conn.close()
    return result and result[0] == 1

def activate_trial(user_id):
    conn = sqlite3.connect('subscriptions.db')
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO users (user_id, trial_used, subscribed_until) VALUES (?, 1, ?)",
              (user_id, (datetime.now() + timedelta(days=3)).isoformat()))
    conn.commit()
    conn.close()

def is_subscribed(user_id):
    conn = sqlite3.connect('subscriptions.db')
    c = conn.cursor()
    c.execute("SELECT subscribed_until FROM users WHERE user_id=?", (user_id,))
    result = c.fetchone()
    conn.close()
    if result and result[0]:
        return datetime.now() < datetime.fromisoformat(result[0])
    return False

def activate_subscription(user_id):
    conn = sqlite3.connect('subscriptions.db')
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO users (user_id, subscribed_until) VALUES (?, ?)",
              (user_id, (datetime.now() + timedelta(days=30)).isoformat()))
    conn.commit()
    conn.close()

# ---------- DEEPSEEK ----------
DEEPSEEK_API_KEY = os.getenv('DEEPSEEK_API_KEY')
deepseek_client = OpenAI(api_key=DEEPSEEK_API_KEY, base_url="https://api.deepseek.com/v1") if DEEPSEEK_API_KEY else None

# ---------- CRYPTOBOT ----------
CRYPTOBOT_TOKEN = os.getenv('CRYPTOBOT_TOKEN')
crypto = None
if CRYPTOBOT_TOKEN:
    from async_crypto_pay_api import CryptoPayApi
    crypto = CryptoPayApi(CRYPTOBOT_TOKEN)

# ---------- НОВОСТИ ----------
async def get_news(coin: str) -> str:
    try:
        google_news = GNews(language='ru', period='7d', max_results=3)
        news = await asyncio.to_thread(google_news.get_news, f"{coin} криптовалюта новости")
        if not news:
            return "Новости не найдены."
        snippets = []
        for item in news[:3]:
            title = item.get('title', '')
            description = item.get('description', '')
            snippets.append(f"• {title}: {description[:150]}")
        return "\n".join(snippets) if snippets else "Новости не найдены."
    except Exception as e:
        logger.error(f"GNews ошибка: {e}")
        return "Не удалось получить новости."

async def get_analysis(coin: str, news: str) -> str:
    current_year = datetime.now().year
    prompt = f"""Сегодня {current_year} год.
Вот свежие новости о {coin}:
{news}

На основе этих новостей (если новостей нет — на основе рыночных принципов) напиши анализ настроений по {coin}. 
Формат:
📊 Настроение: [бычье/медвежье/нейтральное]
📈 Уверенность: [0-100]%
🔥 Ключевые факторы: (2-3 пункта)
💡 Краткий итог: (1 предложение)

Ответ на русском, до 500 символов. Не давай конкретных инвестиционных советов."""
    
    try:
        response = deepseek_client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": "Ты криптоаналитик, даёшь только факты."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=500,
            temperature=0.7
        )
        return response.choices[0].message.content
    except Exception as e:
        logger.error(f"DeepSeek ошибка: {e}")
        return "⚠️ Ошибка анализа. Попробуйте позже."

async def get_sell_suggestion(coin: str) -> str:
    prompt = f"""Дай краткую рекомендацию по возможной продаже {coin}. 
Укажи вероятные уровни (+15-20%) и временной горизонт (2-4 недели). 
Обязательно добавь дисклеймер: "⚠️ Не является инвестиционной рекомендацией." 
Ответ до 300 символов на русском."""
    try:
        response = deepseek_client.chat.completions.create(
            model="deepseek-chat",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=300
        )
        return response.choices[0].message.content
    except:
        return "⚠️ Рекомендация недоступна.\n\n⚠️ Не является инвестиционной рекомендацией."

# ---------- КОМАНДЫ ----------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await update.message.reply_text(
        f"🚀 Привет, {user.first_name}!\n\n"
        "Я - Crypto Sentinel AI бот.\n"
        "Анализирую рынок с помощью DeepSeek + свежие новости.\n\n"
        "🏠 *Главное меню:*",
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📊 Анализ монеты", callback_data="start_analyze")],
            [InlineKeyboardButton("🎁 Пробный период (3 дня)", callback_data="trial_period")],
            [InlineKeyboardButton("💰 Подписка $10", callback_data="subscribe_now")],
            [InlineKeyboardButton("✅ Проверить оплату", callback_data="check_payment_now")],
            [InlineKeyboardButton("📅 Ежедневный отчёт", callback_data="daily_report")],
            [InlineKeyboardButton("✍️ Отзыв / предложение", callback_data="feedback_menu")]
        ])
    )

# ---------- ОБРАБОТЧИК КНОПОК ----------
async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = update.effective_user.id

    # Главное меню
    if data == "main_menu":
        await query.edit_message_text(
            "🏠 *Главное меню*",
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📊 Анализ монеты", callback_data="start_analyze")],
                [InlineKeyboardButton("🎁 Пробный период (3 дня)", callback_data="trial_period")],
                [InlineKeyboardButton("💰 Подписка $10", callback_data="subscribe_now")],
                [InlineKeyboardButton("✅ Проверить оплату", callback_data="check_payment_now")],
                [InlineKeyboardButton("📅 Ежедневный отчёт", callback_data="daily_report")],
                [InlineKeyboardButton("✍️ Отзыв / предложение", callback_data="feedback_menu")]
            ])
        )
        return

    # Пробный период
    if data == "trial_period":
        if is_trial_used(user_id):
            await query.edit_message_text("❌ Вы уже использовали пробный период.")
        else:
            activate_trial(user_id)
            await query.edit_message_text(
                "🎁 Пробный период активирован на 3 дня!\n"
                "Теперь вам доступны анализ монет и ежедневные отчёты.\n\n"
                "Вернитесь в главное меню: /start"
            )
        return

    # Подписка
    if data == "subscribe_now":
        if is_subscribed(user_id):
            await query.edit_message_text("✅ У вас уже активна подписка.")
            return
        if not crypto:
            await query.edit_message_text("⚠️ Система оплаты временно недоступна. Попробуйте позже.")
            return
        
        invoice = await crypto.create_invoice(
            currency_type="fiat",
            fiat="USD",
            amount=10,
            expires_in=3600
        )
        context.user_data['pending_invoice_id'] = invoice.invoice_id
        await query.edit_message_text(
            f"💰 Подписка на месяц — $10\n\n"
            f"Оплатите по ссылке:\n{invoice.bot_invoice_url}\n\n"
            f"После оплаты нажмите '✅ Проверить оплату' в главном меню."
        )
        return

    # Проверка оплаты
    if data == "check_payment_now":
        invoice_id = context.user_data.get('pending_invoice_id')
        if not invoice_id:
            await query.edit_message_text("Нет активного счёта. Используйте '💰 Подписка $10'")
            return
        
        invoices = await crypto.get_invoices(invoice_ids=[invoice_id])
        invoice = invoices[0]
        if invoice.status == "paid":
            activate_subscription(user_id)
            until_date = (datetime.now() + timedelta(days=30)).strftime('%d.%m.%Y')
            await query.edit_message_text(
                f"✅ Оплата получена! Подписка активна до {until_date}.\n"
                f"Теперь вам доступны все функции бота."
            )
        else:
            await query.edit_message_text(f"❌ Оплата не найдена. Статус: {invoice.status}")
        return

    # Ежедневный отчёт
    if data == "daily_report":
        if not is_subscribed(user_id) and not is_trial_used(user_id):
            await query.edit_message_text("❌ Ежедневные отчёты доступны только по подписке или пробному периоду.")
        else:
            await query.edit_message_text("📅 Ежедневный отчёт скоро будет доступен. А пока используйте анализ монет.")
        return

    # Отзывы
    if data == "feedback_menu":
        await query.edit_message_text(
            "✍️ Напишите свой отзыв или предложение в одном сообщении.\n"
            "За полезный отзыв мы дадим промокод на скидку 20% на следующий месяц!"
        )
        return

    # Выбор монеты
    if data == "start_analyze":
        if not is_subscribed(user_id) and not is_trial_used(user_id):
            await query.edit_message_text("❌ Анализ доступен только по подписке или пробному периоду.")
            return
        
        keyboard = []
        for i in range(0, len(SUPPORTED_COINS), 3):
            row = [InlineKeyboardButton(coin, callback_data=f"analyze_{coin}") for coin in SUPPORTED_COINS[i:i+3]]
            keyboard.append(row)
        keyboard.append([InlineKeyboardButton("🔙 Главное меню", callback_data="main_menu")])
        await query.edit_message_text("🔍 Выберите криптовалюту:", reply_markup=InlineKeyboardMarkup(keyboard))
        return

    # Анализ монеты
    if data.startswith("analyze_"):
        coin = data.split("_")[1]
        await query.edit_message_text(f"🧠 Анализирую {coin}...\n📰 Получаю свежие новости...")
        news = await get_news(coin)
        await query.edit_message_text(f"🧠 Анализирую {coin} с учётом новостей...\n⏳ 10-15 секунд.")
        analysis = await get_analysis(coin, news)
        context.user_data['last_analysis'] = analysis
        context.user_data['last_coin'] = coin
        
        keyboard = [
            [InlineKeyboardButton("📅 Примерная продажа", callback_data="sell_advice")],
            [InlineKeyboardButton("🔙 Главное меню", callback_data="main_menu")]
        ]
        await query.edit_message_text(
            f"🤖 *Анализ {coin} (DeepSeek + новости):*\n\n{analysis}",
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

    # Примерная продажа
    if data == "sell_advice":
        coin = context.user_data.get('last_coin', 'BTC')
        await query.edit_message_text(f"📊 Генерирую рекомендацию по продаже {coin}...")
        suggestion = await get_sell_suggestion(coin)
        keyboard = [
            [InlineKeyboardButton("🔙 К анализу", callback_data="back_to_analysis")],
            [InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu")]
        ]
        await query.edit_message_text(
            f"💡 *Рекомендация по {coin}:*\n\n{suggestion}",
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

    # Назад к анализу
    if data == "back_to_analysis":
        coin = context.user_data.get('last_coin', 'BTC')
        analysis = context.user_data.get('last_analysis', 'Анализ недоступен')
        keyboard = [
            [InlineKeyboardButton("📅 Примерная продажа", callback_data="sell_advice")],
            [InlineKeyboardButton("🔙 Главное меню", callback_data="main_menu")]
        ]
        await query.edit_message_text(
            f"🤖 *Анализ {coin}:*\n\n{analysis}",
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

# ---------- ЗАГЛУШКИ КОМАНД (чтобы не ломались) ----------
async def coins_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"📊 Поддерживаемые монеты:\n{', '.join(SUPPORTED_COINS)}")

async def trial(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if is_trial_used(user_id):
        await update.message.reply_text("❌ Вы уже использовали пробный период.")
    else:
        activate_trial(user_id)
        await update.message.reply_text("🎁 Пробный период активирован на 3 дня!")

async def subscribe(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if is_subscribed(user_id):
        await update.message.reply_text("✅ У вас уже активна подписка.")
        return
    if not crypto:
        await update.message.reply_text("⚠️ Система оплаты временно недоступна.")
        return
    
    invoice = await crypto.create_invoice(
        currency_type="fiat",
        fiat="USD",
        amount=10,
        expires_in=3600
    )
    context.user_data['pending_invoice_id'] = invoice.invoice_id
    await update.message.reply_text(
        f"💰 Подписка на месяц — $10\n\n"
        f"Оплатите по ссылке:\n{invoice.bot_invoice_url}\n\n"
        f"После оплаты нажмите /check_payment"
    )

async def check_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    invoice_id = context.user_data.get('pending_invoice_id')
    if not invoice_id:
        await update.message.reply_text("Нет активного счёта. Используйте /subscribe")
        return
    
    invoices = await crypto.get_invoices(invoice_ids=[invoice_id])
    invoice = invoices[0]
    if invoice.status == "paid":
        activate_subscription(user_id)
        until_date = (datetime.now() + timedelta(days=30)).strftime('%d.%m.%Y')
        await update.message.reply_text(
            f"✅ Оплата получена! Подписка активна до {until_date}."
        )
    else:
        await update.message.reply_text(f"❌ Оплата не найдена. Статус: {invoice.status}")

async def daily(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_subscribed(user_id) and not is_trial_used(user_id):
        await update.message.reply_text("❌ Ежедневные отчёты доступны только по подписке или пробному периоду.")
    else:
        await update.message.reply_text("📅 Ежедневный отчёт скоро будет доступен.")

async def feedback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "✍️ Напишите свой отзыв в одном сообщении.\n"
        "За полезный отзыв мы дадим промокод на скидку 20%!"
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 *Crypto Sentinel AI Bot*\n\n"
        "Используйте /start для открытия главного меню с кнопками.\n"
        "Все функции доступны через кнопки. Команды в чат вводить не нужно.\n\n"
        "Доступные действия:\n"
        "• Анализ любой монеты из списка\n"
        "• Рекомендация по продаже (не финсовет)\n"
        "• Пробный период 3 дня\n"
        "• Подписка $10/месяц\n"
        "• Ежедневные отчёты (скоро)",
        parse_mode='Markdown'
    )

# ---------- ЗАПУСК ----------
def main():
    init_db()
    TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
    if not TOKEN:
        logger.error("Токен не найден")
        return
    
    app = Application.builder().token(TOKEN).build()
    
    # Команды (оставлены для совместимости, но всё управление через кнопки)
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("coins", coins_command))
    app.add_handler(CommandHandler("trial", trial))
    app.add_handler(CommandHandler("subscribe", subscribe))
    app.add_handler(CommandHandler("check_payment", check_payment))
    app.add_handler(CommandHandler("daily", daily))
    app.add_handler(CommandHandler("feedback", feedback))
    
    # Главный обработчик кнопок
    app.add_handler(CallbackQueryHandler(button_callback))
    
    logger.info("Бот запущен с полным кнопочным меню!")
    print("Бот работает. Всё управление через кнопки.")
    app.run_polling()

if __name__ == '__main__':
    main()
