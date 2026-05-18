import os
import logging
import asyncio
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from openai import OpenAI
from gnews import GNews

# ---------- НАСТРОЙКИ ----------
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

SUPPORTED_COINS = ["BTC", "ETH", "SOL", "ADA", "DOT", "XRP", "DOGE", "MATIC", "BNB", "LTC"]

# ---------- ПОДКЛЮЧЕНИЕ К POSTGRESQL ----------
def get_db_connection():
    DATABASE_URL = os.getenv('DATABASE_URL')
    if not DATABASE_URL:
        raise Exception("DATABASE_URL не задан")
    return psycopg2.connect(DATABASE_URL)

def init_db():
    """Создаёт таблицу и добавляет недостающие колонки"""
    try:
        conn = get_db_connection()
        c = conn.cursor()
        
        # Создаём таблицу, если её нет
        c.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id BIGINT PRIMARY KEY,
                subscribed_until TIMESTAMP,
                trial_used BOOLEAN DEFAULT FALSE,
                trial_until TIMESTAMP
            )
        ''')
        
        # Добавляем колонку trial_used, если её нет
        try:
            c.execute("ALTER TABLE users ADD COLUMN trial_used BOOLEAN DEFAULT FALSE")
        except psycopg2.errors.DuplicateColumn:
            pass  # колонка уже существует
        
        # Добавляем колонку trial_until, если её нет
        try:
            c.execute("ALTER TABLE users ADD COLUMN trial_until TIMESTAMP")
        except psycopg2.errors.DuplicateColumn:
            pass  # колонка уже существует
        
        conn.commit()
        conn.close()
        logger.info("База данных готова (таблица и колонки созданы)")
    except Exception as e:
        logger.error(f"Ошибка инициализации БД: {e}")

def get_user_status(user_id):
    """Возвращает статус подписки и пробного периода"""
    try:
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("""
            SELECT subscribed_until, trial_used, trial_until 
            FROM users WHERE user_id = %s
        """, (user_id,))
        result = c.fetchone()
        conn.close()
        
        if result:
            subscribed_until = result[0]
            trial_used = result[1] or False
            trial_until = result[2]
            
            now = datetime.now()
            subscription_active = subscribed_until and now < subscribed_until
            trial_active = trial_until and now < trial_until
            
            return {
                'has_active_subscription': subscription_active,
                'has_active_trial': trial_active,
                'subscribed_until': subscribed_until,
                'trial_until': trial_until,
                'trial_used': trial_used
            }
        return {
            'has_active_subscription': False,
            'has_active_trial': False,
            'subscribed_until': None,
            'trial_until': None,
            'trial_used': False
        }
    except Exception as e:
        logger.error(f"Ошибка получения статуса: {e}")
        return None

def is_trial_used(user_id):
    status = get_user_status(user_id)
    return status['trial_used'] if status else False

def activate_trial(user_id):
    try:
        conn = get_db_connection()
        c = conn.cursor()
        until_date = datetime.now() + timedelta(days=3)
        c.execute("""
            INSERT INTO users (user_id, subscribed_until, trial_used, trial_until)
            VALUES (%s, %s, TRUE, %s)
            ON CONFLICT (user_id) DO UPDATE
            SET trial_used = TRUE,
                trial_until = EXCLUDED.trial_until,
                subscribed_until = NULL
        """, (user_id, None, until_date))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"Ошибка активации trial: {e}")
        return False

def is_subscribed(user_id):
    status = get_user_status(user_id)
    if not status:
        return False
    return status['has_active_subscription'] or status['has_active_trial']

def activate_subscription(user_id, duration_days=30):
    try:
        conn = get_db_connection()
        c = conn.cursor()
        until_date = datetime.now() + timedelta(days=duration_days)
        c.execute("""
            INSERT INTO users (user_id, subscribed_until, trial_used, trial_until)
            VALUES (%s, %s, FALSE, NULL)
            ON CONFLICT (user_id) DO UPDATE
            SET subscribed_until = EXCLUDED.subscribed_until,
                trial_used = FALSE,
                trial_until = NULL
        """, (user_id, until_date))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"Ошибка активации подписки: {e}")
        return False

# ---------- DEEPSEEK ----------
DEEPSEEK_API_KEY = os.getenv('DEEPSEEK_API_KEY')
deepseek_client = OpenAI(api_key=DEEPSEEK_API_KEY, base_url="https://api.deepseek.com/v1") if DEEPSEEK_API_KEY else None

# ---------- CRYPTOBOT ----------
CRYPTOBOT_TOKEN = os.getenv('CRYPTOBOT_TOKEN')
crypto = None
if CRYPTOBOT_TOKEN:
    try:
        from async_crypto_pay_api import CryptoPayApi
        crypto = CryptoPayApi(CRYPTOBOT_TOKEN)
    except ImportError:
        logger.warning("async-crypto-pay-api не установлен")
        crypto = None

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

# ---------- КЛАВИАТУРА ----------
def get_main_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 Анализ монеты", callback_data="start_analyze")],
        [InlineKeyboardButton("🎁 Пробный период (3 дня)", callback_data="trial_period")],
        [InlineKeyboardButton("💰 Подписка $10", callback_data="subscribe_now")],
        [InlineKeyboardButton("✅ Проверить оплату", callback_data="check_payment_now")],
        [InlineKeyboardButton("📅 Ежедневный отчёт", callback_data="daily_report")],
        [InlineKeyboardButton("✍️ Отзыв / предложение", callback_data="feedback_menu")]
    ])

# ---------- КОМАНДЫ И КНОПКИ ----------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    status = get_user_status(user.id)
    
    status_text = ""
    if status and status['has_active_subscription'] and status['subscribed_until']:
        until = status['subscribed_until'].strftime('%d.%m.%Y %H:%M')
        status_text = f"\n\n✅ *Подписка активна до:* {until}"
    elif status and status['has_active_trial'] and status['trial_until']:
        until = status['trial_until'].strftime('%d.%m.%Y %H:%M')
        status_text = f"\n\n🎁 *Пробный период активен до:* {until}"
    
    await update.message.reply_text(
        f"🚀 Привет, {user.first_name}!\n\n"
        "Я - Crypto Sentinel AI бот.\n"
        "Анализирую рынок с помощью DeepSeek + свежие новости.\n\n"
        f"🏠 *Главное меню:*{status_text}",
        parse_mode='Markdown',
        reply_markup=get_main_menu()
    )

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = update.effective_user.id

    # Главное меню
    if data == "main_menu":
        status = get_user_status(user_id)
        status_text = ""
        if status and status['has_active_subscription'] and status['subscribed_until']:
            until = status['subscribed_until'].strftime('%d.%m.%Y %H:%M')
            status_text = f"\n\n✅ *Подписка активна до:* {until}"
        elif status and status['has_active_trial'] and status['trial_until']:
            until = status['trial_until'].strftime('%d.%m.%Y %H:%M')
            status_text = f"\n\n🎁 *Пробный период активен до:* {until}"
        
        await query.edit_message_text(
            f"🏠 *Главное меню*{status_text}",
            parse_mode='Markdown',
            reply_markup=get_main_menu()
        )
        return

    # Пробный период
    if data == "trial_period":
        status = get_user_status(user_id)
        if not status:
            await query.edit_message_text(
                "❌ Ошибка. Попробуйте позже.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Главное меню", callback_data="main_menu")]])
            )
            return
        
        if status['trial_used'] and not status['has_active_trial']:
            await query.edit_message_text(
                "❌ Вы уже использовали пробный период.\n\nВернуться в главное меню:",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Главное меню", callback_data="main_menu")]])
            )
            return
        if status['has_active_trial']:
            await query.edit_message_text(
                f"🎁 Пробный период уже активен и действует до {status['trial_until'].strftime('%d.%m.%Y %H:%M')}.\n\n"
                "Вы можете приобрести подписку, она начнётся после окончания пробного периода.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("💰 Купить подписку", callback_data="subscribe_now")],
                    [InlineKeyboardButton("🔙 Главное меню", callback_data="main_menu")]
                ])
            )
            return
        if status['has_active_subscription']:
            await query.edit_message_text(
                "✅ У вас уже активна платная подписка. Пробный период не нужен.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Главное меню", callback_data="main_menu")]])
            )
            return
        
        activate_trial(user_id)
        new_status = get_user_status(user_id)
        if new_status and new_status['trial_until']:
            until = new_status['trial_until'].strftime('%d.%m.%Y %H:%M')
            await query.edit_message_text(
                f"🎁 Пробный период активирован на 3 дня!\nДействует до {until}\n\n"
                "Теперь вам доступен анализ монет.\n"
                "Вернуться в главное меню:",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Главное меню", callback_data="main_menu")]])
            )
        else:
            await query.edit_message_text(
                "🎁 Пробный период активирован на 3 дня!\n\n"
                "Вернуться в главное меню:",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Главное меню", callback_data="main_menu")]])
            )
        return

    # Подписка
    if data == "subscribe_now":
        status = get_user_status(user_id)
        if status and status['has_active_subscription']:
            await query.edit_message_text(
                f"✅ У вас уже активна платная подписка до {status['subscribed_until'].strftime('%d.%m.%Y %H:%M')}.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Главное меню", callback_data="main_menu")]])
            )
            return
        
        if not crypto:
            await query.edit_message_text(
                "⚠️ Система оплаты временно недоступна. Попробуйте позже.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Главное меню", callback_data="main_menu")]])
            )
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
            f"После оплаты нажмите '✅ Проверить оплату' в главном меню.\n\n"
            f"💡 *Важно:* Если у вас активен пробный период, платная подписка начнётся после его окончания.",
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Главное меню", callback_data="main_menu")]])
        )
        return

    # Проверка оплаты
    if data == "check_payment_now":
        invoice_id = context.user_data.get('pending_invoice_id')
        if not invoice_id:
            await query.edit_message_text(
                "Нет активного счёта. Используйте '💰 Подписка $10'",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Главное меню", callback_data="main_menu")]])
            )
            return
        if not crypto:
            await query.edit_message_text(
                "⚠️ Система оплаты недоступна",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Главное меню", callback_data="main_menu")]])
            )
            return
        invoices = await crypto.get_invoices(invoice_ids=[invoice_id])
        invoice = invoices[0]
        if invoice.status == "paid":
            activate_subscription(user_id)
            await query.edit_message_text(
                f"✅ Оплата получена! Подписка активна на 30 дней.\n\n"
                f"Вернуться в главное меню:",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Главное меню", callback_data="main_menu")]])
            )
        else:
            await query.edit_message_text(
                f"❌ Оплата не найдена. Статус: {invoice.status}\n\n"
                f"Попробуйте ещё раз позже.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Главное меню", callback_data="main_menu")]])
            )
        return

    # Ежедневный отчёт
    if data == "daily_report":
        if not is_subscribed(user_id):
            await query.edit_message_text(
                "❌ Ежедневные отчёты доступны только по подписке или пробному периоду.\n\n"
                "Вернуться в главное меню:",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Главное меню", callback_data="main_menu")]])
            )
            return
        await query.edit_message_text(
            "📅 Ежедневный отчёт скоро будет доступен. А пока используйте анализ монет.\n\n"
            "Вернуться в главное меню:",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Главное меню", callback_data="main_menu")]])
        )
        return

    # Отзывы
    if data == "feedback_menu":
        await query.edit_message_text(
            "✍️ Напишите свой отзыв или предложение в одном сообщении.\n"
            "За полезный отзыв мы дадим промокод на скидку 20% на следующий месяц!\n\n"
            "Вернуться в главное меню:",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Главное меню", callback_data="main_menu")]])
        )
        return

    # Выбор монеты
    if data == "start_analyze":
        if not is_subscribed(user_id):
            await query.edit_message_text(
                "❌ Анализ доступен только по подписке или пробному периоду.\n\n"
                "Вернуться в главное меню:",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Главное меню", callback_data="main_menu")]])
            )
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
            [InlineKeyboardButton("🔙 Главное меню", callback_data="main_menu")]
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

# ---------- ЗАГЛУШКИ КОМАНД ----------
async def coins_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"📊 Поддерживаемые монеты:\n{', '.join(SUPPORTED_COINS)}")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 *Crypto Sentinel AI Bot*\n\n"
        "Используйте /start для открытия главного меню с кнопками.\n"
        "Все функции доступны через кнопки.\n\n"
        "• Анализ монеты — доступен по подписке или пробному периоду\n"
        "• Пробный период — 3 дня бесплатно\n"
        "• Подписка — $10/месяц\n\n"
        "Статус подписки отображается в главном меню.",
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
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("coins", coins_command))
    app.add_handler(CallbackQueryHandler(button_callback))
    
    logger.info("Бот запущен с PostgreSQL!")
    print("Бот работает. Данные сохраняются в PostgreSQL.")
    app.run_polling()

if __name__ == '__main__':
    main()
