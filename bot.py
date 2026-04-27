import os
import logging
import asyncio
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from openai import OpenAI
from gnews import GNews

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

SUPPORTED_COINS = ["BTC", "ETH", "SOL", "ADA", "DOT", "XRP", "DOGE", "MATIC", "BNB", "LTC"]

DEEPSEEK_API_KEY = os.getenv('DEEPSEEK_API_KEY')
if DEEPSEEK_API_KEY:
    deepseek_client = OpenAI(api_key=DEEPSEEK_API_KEY, base_url="https://api.deepseek.com/v1")
else:
    deepseek_client = None
    logger.warning("DEEPSEEK_API_KEY не найден")

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

async def sentiment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отправляет клавиатуру с выбором монеты"""
    keyboard = []
    for i in range(0, len(SUPPORTED_COINS), 3):
        row = [InlineKeyboardButton(coin, callback_data=coin) for coin in SUPPORTED_COINS[i:i+3]]
        keyboard.append(row)
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "🔍 Выберите криптовалюту для анализа:",
        reply_markup=reply_markup
    )

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    coin = query.data

    await query.edit_message_text(f"🧠 Анализирую {coin}...\n📰 Получаю свежие новости...")

    news_text = await get_news(coin)

    await query.edit_message_text(f"🧠 Анализирую {coin} с учётом новостей...\n⏳ Подождите 15 секунд.")

    current_year = datetime.now().year
    prompt = f"""Сегодня {current_year} год.
Вот свежие новости о {coin}:
{news_text}

На основе этих новостей (если новостей нет — на основе общих рыночных принципов) напиши анализ настроений по {coin}. 
Формат:
📊 Настроение: [бычье/медвежье/нейтральное]
📈 Уверенность: [0-100]%
🔥 Ключевые факторы: (2-3 пункта)
💡 Краткий итог: (1 предложение)
Ответ на русском, до 500 символов. Не пиши про 2024 год как будущее."""

    try:
        response = deepseek_client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": "Ты криптоаналитик."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=500,
            temperature=0.7
        )
        ai_report = response.choices[0].message.content
        await query.edit_message_text(f"🤖 *Анализ {coin} (DeepSeek + новости):*\n\n{ai_report}", parse_mode='Markdown')
    except Exception as e:
        logger.error(f"Ошибка DeepSeek: {e}")
        await query.edit_message_text("⚠️ Ошибка нейросети. Попробуйте позже.")

async def subscribe(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("💰 Подписка $10/месяц\nСкоро будет доступна!")

async def daily(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📅 Ежедневный отчет будет доступен после подписки.")

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
    app.add_handler(CommandHandler("subscribe", subscribe))
    app.add_handler(CommandHandler("daily", daily))
    app.add_handler(CallbackQueryHandler(button_callback))
    logger.info("Бот запущен с кнопками!")
    print("Bot started")
    app.run_polling()

if __name__ == '__main__':
    main()
