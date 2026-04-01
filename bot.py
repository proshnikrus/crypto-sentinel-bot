import os
import logging
import random
from datetime import datetime
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Список монет
SUPPORTED_COINS = ["BTC", "ETH", "SOL", "ADA", "DOT", "XRP", "DOGE", "MATIC", "BNB", "LTC"]

# ===== КОМАНДЫ =====
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await update.message.reply_text(
        f"🚀 Привет, {user.first_name}!\n\n"
        "Я - Crypto Sentinel AI бот.\n"
        "Используй /help чтобы увидеть команды."
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📋 Команды:\n"
        "/start - Начать\n"
        "/help - Помощь\n"
        "/coins - Список монет\n"
        "/sentiment BTC - Анализ монеты"
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
        
        # Отправляем сообщение о начале анализа
        await update.message.reply_text(f"🔍 Анализирую {coin}...")
        
        # Генерируем случайный отчет (демо)
        score = random.randint(30, 85)
        trend = "бычий" if score > 60 else "медвежий" if score < 40 else "нейтральный"
        
        report = f"""
📊 Отчет по {coin}
📅 {datetime.now().strftime('%d.%m.%Y %H:%M')}

Настроение: {trend} ({score}/100)

Ключевые темы:
• Обсуждение новостей {coin}
• Рыночные тренды
• Активность сообщества

💡 Это демо-версия. Реальный AI анализ скоро!
"""
        await update.message.reply_text(report)
        
    except Exception as e:
        logger.error(f"Ошибка: {e}")
        await update.message.reply_text("⚠️ Ошибка. Попробуйте позже.")

async def subscribe(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "💰 Подписка $10/месяц\n"
        "Скоро будет доступна!"
    )

async def daily(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📅 Ежедневный отчет будет доступен после подписки."
    )

# ===== ЗАПУСК =====
def main():
    TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
    
    if not TOKEN:
        logger.error("Токен не найден!")
        return
    
    app = Application.builder().token(TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("coins", coins_command))
    app.add_handler(CommandHandler("sentiment", sentiment))
    app.add_handler(CommandHandler("subscribe", subscribe))
    app.add_handler(CommandHandler("daily", daily))
    
    logger.info("Бот запущен!")
    print("Crypto Sentinel AI Bot - Running")
    
    app.run_polling()

if __name__ == '__main__':
    main()
