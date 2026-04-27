import os
import logging
import asyncio
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from openai import OpenAI
from gnews import GNews

# ---------- Настройки ----------
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

SUPPORTED_COINS = ["BTC", "ETH", "SOL", "ADA", "DOT", "XRP", "DOGE", "MATIC", "BNB", "LTC"]

# ---------- DeepSeek ----------
DEEPSEEK_API_KEY = os.getenv('DEEPSEEK_API_KEY')
deepseek_client = OpenAI(api_key=DEEPSEEK_API_KEY, base_url="https://api.deepseek.com/v1") if DEEPSEEK_API_KEY else None

# ---------- GNews (бесплатный поиск новостей) ----------
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
        logger.error(f"Ошибка GNews: {e}")
        return "Не удалось получить новости."

# ---------- Анализ через DeepSeek ----------
async def get_analysis(coin: str, news: str) -> str:
    current_year = datetime.now().year
    prompt = f"""Сегодня {current_year} год.
Вот свежие новости о {coin}:
{news}

На основе этих новостей (а если новостей нет — на основе общих рыночных принципов) напиши анализ настроений по {coin}. 
Формат:
📊 Настроение: [бычье/медвежье/нейтральное]
📈 Уверенность: [0-100]%
🔥 Ключевые факторы: (2-3 пункта)
💡 Краткий итог: (1 предложение)

Ответ на русском, до 500 символов. Не пиши про 2024 год как будущее. Не давай конкретных инвестиционных рекомендаций — только анализ."""
    
    try:
        response = deepseek_client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": "Ты криптоаналитик, даёшь только факты и вероятности, без советов."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=500,
            temperature=0.7
        )
        return response.choices[0].message.content
    except Exception as e:
        logger.error(f"DeepSeek ошибка: {e}")
        return "⚠️ Не удалось получить анализ. Попробуйте позже."

# ---------- Рекомендация по продаже (только уровни, не дата) ----------
async def get_sell_suggestion(coin: str, analysis_text: str = "") -> str:
    current_year = datetime.now().year
    prompt = f"""Ты криптоаналитик. На основе общего анализа для {coin} (или рыночных принципов) дай краткую рекомендацию по возможной продаже.
Не называй конкретных дат, а укажи:
- Примерный уровень цены для фиксации прибыли (например, +15-20% от текущей)
- Временной горизонт (например, 2-4 недели при сохранении тренда)
- Условия, при которых продажа может быть оправдана (пробой поддержки, негативные новости)
Обязательно добавь дисклеймер: "⚠️ Не является инвестиционной рекомендацией. Торговля криптовалютами сопряжена с высоким риском."

Ответ до 400 символов на русском.

Вот дополнительный контекст (может быть пустой): {analysis_text[:300]}"""
    
    try:
        response = deepseek_client.chat.completions.create(
            model="deepseek-chat",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=400,
            temperature=0.7
        )
        return response.choices[0].message.content
    except Exception as e:
        logger.error(f"Sell suggestion error: {e}")
        return "⚠️ Рекомендация временно недоступна.\n\n⚠️ Не является инвестиционной рекомендацией."

# ---------- Команды бота ----------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await update.message.reply_text(
        f"🚀 Привет, {user.first_name}!\n\n"
        "Я - Crypto Sentinel AI бот.\n"
        "Анализирую настроения крипторынка с помощью DeepSeek + свежие новости.\n\n"
        "/help - список команд"
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📋 Команды:\n"
        "/start - Начать\n"
        "/help - Помощь\n"
        "/coins - Список монет\n"
        "/sentiment - Анализ (выбрать монету из кнопок)\n"
        "/daily - Ежедневный отчет (скоро)\n"
        "/subscribe - Подписка (скоро)"
    )

async def coins_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    coins_list = ", ".join(SUPPORTED_COINS)
    await update.message.reply_text(f"📊 Поддерживаемые монеты:\n{coins_list}")

# ---------- Отправка клавиатуры выбора монет ----------
async def sentiment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = []
    for i in range(0, len(SUPPORTED_COINS), 3):
        row = [InlineKeyboardButton(coin, callback_data=f"analyze_{coin}") for coin in SUPPORTED_COINS[i:i+3]]
        keyboard.append(row)
    await update.message.reply_text(
        "🔍 Выберите криптовалюту для анализа:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# ---------- Обработчик всех нажатий на кнопки ----------
async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    # Главное меню
    if data == "main_menu":
        keyboard = [
            [InlineKeyboardButton("📊 Анализ монеты", callback_data="start_analyze")],
            [InlineKeyboardButton("📅 Ежедневный отчёт", callback_data="daily_report")],
            [InlineKeyboardButton("💰 Подписка", callback_data="subscription_info")]
        ]
        await query.edit_message_text(
            "🏠 *Главное меню*",
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

    # Начать выбор монеты
    if data == "start_analyze":
        keyboard = []
        for i in range(0, len(SUPPORTED_COINS), 3):
            row = [InlineKeyboardButton(coin, callback_data=f"analyze_{coin}") for coin in SUPPORTED_COINS[i:i+3]]
            keyboard.append(row)
        await query.edit_message_text(
            "🔍 Выберите криптовалюту:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

    # Ежедневный отчёт (заглушка)
    if data == "daily_report":
        await query.edit_message_text(
            "📅 Ежедневный отчёт появится после подключения подписки.\nСкоро!",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Назад", callback_data="main_menu")]])
        )
        return

    # Подписка (заглушка)
    if data == "subscription_info":
        await query.edit_message_text(
            "💰 Подписка $10/месяц.\nДоступ к ежедневным отчётам и расширенным рекомендациям.\n"
            "Способ оплаты: CryptoBot (скоро).",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Назад", callback_data="main_menu")]])
        )
        return

    # Анализ монеты (кнопка analyze_BTC и т.д.)
    if data.startswith("analyze_"):
        coin = data.split("_")[1]
        # Сохраняем выбранную монету в данных пользователя
        context.user_data['selected_coin'] = coin
        await query.edit_message_text(f"🧠 Анализирую {coin}...\n📰 Получаю свежие новости...")
        news = await get_news(coin)
        await query.edit_message_text(f"🧠 Анализирую {coin} с учётом новостей...\n⏳ Подождите 15-20 секунд.")
        analysis = await get_analysis(coin, news)
        # Сохраняем анализ, чтобы потом использовать для продажи
        context.user_data['last_analysis'] = analysis
        # Показываем результат и кнопки
        keyboard = [
            [InlineKeyboardButton("📅 Примерная продажа", callback_data=f"sell_{coin}")],
            [InlineKeyboardButton("🔙 Главное меню", callback_data="main_menu")]
        ]
        await query.edit_message_text(
            f"🤖 *Анализ {coin} (DeepSeek + новости):*\n\n{analysis}",
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

    # Кнопка "Примерная продажа"
    if data.startswith("sell_"):
        coin = data.split("_")[1]
        last_analysis = context.user_data.get('last_analysis', '')
        await query.edit_message_text(f"📊 Генерирую рекомендацию по возможной продаже {coin}...\n⏳ Несколько секунд.")
        suggestion = await get_sell_suggestion(coin, last_analysis)
        keyboard = [
            [InlineKeyboardButton("🔙 К анализу", callback_data=f"back_to_{coin}")],
            [InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu")]
        ]
        await query.edit_message_text(
            f"💡 *Рекомендация по {coin} (не точная дата):*\n\n{suggestion}",
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

    # Назад к анализу (после продажи)
    if data.startswith("back_to_"):
        coin = data.split("_")[2]  # back_to_BTC
        analysis = context.user_data.get('last_analysis', 'Анализ недоступен')
        keyboard = [
            [InlineKeyboardButton("📅 Примерная продажа", callback_data=f"sell_{coin}")],
            [InlineKeyboardButton("🔙 Главное меню", callback_data="main_menu")]
        ]
        await query.edit_message_text(
            f"🤖 *Анализ {coin} (DeepSeek + новости):*\n\n{analysis}",
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

# ---------- Заглушки для /daily и /subscribe ----------
async def daily(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📅 Ежедневный отчёт появится после настройки подписки.")

async def subscribe(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("💰 Подписка $10/месяц. Скоро будет доступна.")

# ---------- Основной запуск ----------
def main():
    TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
    if not TOKEN:
        logger.error("Токен не найден")
        return
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("coins", coins_command))
    app.add_handler(CommandHandler("sentiment", sentiment))
    app.add_handler(CommandHandler("daily", daily))
    app.add_handler(CommandHandler("subscribe", subscribe))
    app.add_handler(CallbackQueryHandler(button_callback))
    logger.info("Бот запущен с меню!")
    print("Бот работает...")
    app.run_polling()

if __name__ == '__main__':
    main()
