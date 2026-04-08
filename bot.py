import os
import logging
import asyncio
from datetime import datetime
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
import google.generativeai as genai

# Настройка логирования
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Список монет
SUPPORTED_COINS = ["BTC", "ETH", "SOL", "ADA", "DOT", "XRP", "DOGE", "MATIC", "BNB", "LTC"]

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await update.message.reply_text(
        f"🚀 Привет, {user.first_name}!\n\n"
        "Я - Crypto Sentinel AI бот.\n"
        "Анализирую настроения крипторынка с помощью нейросети Gemini.\n\n"
        "Используй /help чтобы увидеть команды."
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📋 Команды:\n"
        "/start - Начать\n"
        "/help - Помощь\n"
        "/coins - Список монет\n"
        "/sentiment BTC - Анализ монеты (реальная нейросеть)\n"
        "/daily - Ежедневный отчет (скоро)\n"
        "/subscribe - Подписка (скоро)"
    )

async def coins_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    coins_list = ", ".join(SUPPORTED_COINS)
    await update.message.reply_text(f"📊 Поддерживаемые монеты:\n{coins_list}")

async def sentiment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        if not context.args:
            await update.message.reply_text("Укажите монету: /sentiment BTC")
            return
        
        coin = context.args[0].upper()
        
        if coin not in SUPPORTED_COINS:
            await update.message.reply_text(f"Монета {coin} не поддерживается. Список: /coins")
            return
        
        processing_msg = await update.message.reply_text(f"🧠 Анализирую {coin} с помощью нейросети Gemini...\n⏳ Это займёт 10-15 секунд.")
        
        # Получаем API ключ из переменных окружения
        api_key = os.getenv('GEMINI_API_KEY')
        
        if not api_key:
            await processing_msg.edit_text("⚠️ API ключ Gemini не настроен. Добавьте переменную GEMINI_API_KEY в Render.")
            return
        
        # Настраиваем Gemini
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-2.0-flash-exp')
        
        prompt = f"""Ты — криптоаналитик. Напиши краткий анализ настроений по криптовалюте {coin} на основе рыночных трендов и новостей. Используй эмодзи. Формат ответа:

📊 Настроение: [бычье/медвежье/нейтральное]
📈 Уверенность: [0-100]%
🔥 Ключевые факторы: (2-3 пункта)
💡 Краткий итог: (1 предложение)

Ответ должен быть на русском, дружелюбным и информативным. Не более 500 символов."""
        
        try:
            response = await asyncio.to_thread(
                model.generate_content,
                prompt
            )
            
            ai_report = response.text
            
            await processing_msg.delete()
            await update.message.reply_text(f"🤖 *AI анализ {coin} (Gemini):*\n\n{ai_report}", parse_mode='Markdown')
            
        except Exception as e:
            logger.error(f"Ошибка Gemini: {e}")
            await processing_msg.edit_text(f"⚠️ Ошибка нейросети. Попробуйте позже.")
        
    except Exception as e:
        logger.error(f"Ошибка: {e}")
        await update.message.reply_text("⚠️ Ошибка. Попробуйте позже.")

async def subscribe(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("💰 Подписка $10/месяц\nСкоро будет доступна!")

async def daily(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📅 Ежедневный отчет будет доступен после подписки.")

def main():
    TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
    
    if not TOKEN:
        logger.error("Токен Telegram не найден!")
        return
    
    app = Application.builder().token(TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("coins", coins_command))
    app.add_handler(CommandHandler("sentiment", sentiment))
    app.add_handler(CommandHandler("subscribe", subscribe))
    app.add_handler(CommandHandler("daily", daily))
    
    logger.info("Бот запущен с Gemini AI!")
    print("Crypto Sentinel AI Bot - Running with Gemini")
    
    app.run_polling()

if __name__ == '__main__':
    main()
