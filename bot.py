import os
import logging
import asyncio
import aiohttp
from datetime import datetime, timedelta
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# ===== НАСТРОЙКИ =====
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Список поддерживаемых монет
SUPPORTED_COINS = ["BTC", "ETH", "SOL", "ADA", "DOT", "XRP", "DOGE", "MATIC", "BNB", "LTC"]

# ===== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ =====
async def fetch_twitter_data(coin: str) -> list:
    """Получение данных о твитах (заглушка - в реальности подключаем Twitter API)"""
    # Здесь будет реальный сбор данных
    # Пока возвращаем демо-данные
    demo_tweets = [
        f"${coin} looking bullish today! Expecting breakout soon. #crypto",
        f"Concerns about {coin} regulation are growing. Be cautious.",
        f"Major exchange added {coin} trading pairs. Positive news!",
        f"{coin} technical analysis shows resistance at current levels.",
        f"Institutional investors accumulating {coin}. Long-term bullish."
    ]
    return demo_tweets

async def analyze_with_ai(tweets: list, coin: str) -> dict:
    """Анализ твитов с помощью AI (OpenAI)"""
    try:
        # Проверяем наличие API ключа
        api_key = os.getenv('OPENAI_API_KEY')
        
        if not api_key:
            logger.warning("OPENAI_API_KEY не установлен. Использую демо-режим.")
            return generate_demo_analysis(coin)
        
        # Формируем промпт для OpenAI
        tweets_text = "\n".join([f"- {tweet}" for tweet in tweets[:20]])  # Берем первые 20 твитов
        
        prompt = f"""Ты — опытный криптоаналитик. Проанализируй следующие твиты о {coin} и дай краткий отчет:

Твиты:
{tweets_text}

Проанализируй и верни ответ в формате JSON:
{{
    "sentiment_score": число от 0 до 100,
    "trend": "бычий/медвежий/нейтральный",
    "key_themes": ["тема1", "тема2", "тема3"],
    "summary": "краткое резюме на русском",
    "confidence": число от 0 до 100
}}"""

        # Вызов OpenAI API (будет реализован позже)
        # Пока возвращаем демо-данные
        return generate_demo_analysis(coin)
        
    except Exception as e:
        logger.error(f"Ошибка AI анализа: {e}")
        return generate_demo_analysis(coin)

def generate_demo_analysis(coin: str) -> dict:
    """Генерация демо-анализа (временная функция)"""
    import random
    score = random.randint(30, 85)
    
    return {
        "sentiment_score": score,
        "trend": "бычий" if score > 60 else "медвежий" if score < 40 else "нейтральный",
        "key_themes": [
            f"Обсуждение ETF {coin}",
            "Регуляторные новости",
            "Крупные переводы на биржи"
        ],
        "summary": f"Настроения по {coin} преимущественно {'позитивные' if score > 60 else 'негативные' if score < 40 else 'нейтральные'}. Рекомендуется {'рассмотреть накопление' if score > 60 else 'проявить осторожность' if score < 40 else 'сохранять позиции'}.",
        "confidence": random.randint(70, 95)
    }

# ===== КОМАНДЫ БОТА =====
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start"""
    user = update.effective_user
    await update.message.reply_html(
        f"🚀 <b>Привет, {user.mention_html()}!</b>\n\n"
        "Я - <b>Crypto Sentinel AI</b> - бот для анализа настроений на крипторынке.\n\n"
        "📊 <b>Что я умею:</b>\n"
        "• Анализировать настроения по криптовалютам\n"
        "• Давать ежедневные сводки\n"
        "• Показывать ключевые тренды\n\n"
        "🔍 <b>Примеры команд:</b>\n"
        "<code>/sentiment BTC</code> - анализ для Bitcoin\n"
        "<code>/sentiment ETH</code> - анализ для Ethereum\n"
        "<code>/coins</code> - список доступных монет\n"
        "<code>/help</code> - все команды\n\n"
        "⚡ <i>Бот в активной разработке. Функции добавляются ежедневно!</i>"
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /help"""
    help_text = (
        "🤖 <b>Crypto Sentinel AI - Список команд</b>\n\n"
        "<b>Основные команды:</b>\n"
        "/start - Начать работу с ботом\n"
        "/help - Показать это сообщение\n"
        "/coins - Показать список доступных монет\n\n"
        "<b>Аналитика:</b>\n"
        "/sentiment [монета] - Анализ настроений\n"
        "  Пример: <code>/sentiment BTC</code>\n"
        "/daily - Ежедневный отчет (скоро)\n\n"
        "<b>Подписка:</b>\n"
        "/subscribe - Информация о подписке (скоро)\n\n"
        "<i>Бот анализирует данные из Twitter и генерирует отчеты с помощью AI.</i>"
    )
    await update.message.reply_html(help_text)

async def coins_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать список поддерживаемых монет"""
    coins_list = "\n".join([f"• {coin}" for coin in SUPPORTED_COINS])
    await update.message.reply_html(
        f"📊 <b>Поддерживаемые монеты:</b>\n\n{coins_list}\n\n"
        f"<i>Всего: {len(SUPPORTED_COINS)} монет</i>\n\n"
        "Используйте: <code>/sentiment [монета]</code>"
    )

async def sentiment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Анализ настроений для криптовалюты"""
    try:
        # Получаем аргумент (название монеты)
        if not context.args:
            await update.message.reply_html(
                "⚠️ <b>Укажите монету</b>\n"
                "Пример: <code>/sentiment BTC</code>\n"
                "Список монет: /coins"
            )
            return
            
        coin = context.args[0].upper()
        
        # Проверяем валидность монеты
        if coin not in SUPPORTED_COINS:
            await update.message.reply_html(
                f"❌ <b>Монета {coin} не поддерживается.</b>\n\n"
                f"Доступные монеты: /coins"
            )
            return
        
        # Отправляем сообщение о начале анализа
        processing_msg = await update.message.reply_html(
            f"🔍 <b>Анализирую {coin}...</b>\n"
            "Сбор данных из Twitter...\n"
            "<i>Это займет 10-15 секунд.</i>"
        )
        
        # 1. Собираем данные
        tweets = await fetch_twitter_data(coin)
        
        # 2. Анализируем с AI
        analysis = await analyze_with_ai(tweets, coin)
        
        # 3. Форматируем отчет
        report_date = datetime.now().strftime("%d.%m.%Y %H:%M")
        trend_emoji = "📈" if analysis["trend"] == "бычий" else "📉" if analysis["trend"] == "медвежий" else "➡️"
        
        themes_text = "\n".join([f"• {theme}" for theme in analysis["key_themes"]])
        
        report = f"""
{trend_emoji} <b>Отчет по {coin}</b>
📅 <i>{report_date}</i>

<b>Общий настрой:</b> {analysis["trend"].upper()} ({analysis["sentiment_score"]}/100)
<b>Уверенность анализа:</b> {analysis["confidence"]}%

<b>Ключевые темы:</b>
{themes_text}

<b>Резюме AI:</b>
{analysis["summary"]}

<b>Методология:</b>
Анализ {len(tweets)} твитов, AI-обработка

🔮 <i>Это демо-версия. Реальный AI анализ будет подключен в течение 24 часов.</i>
"""
        
        # Удаляем сообщение "анализирую" и отправляем отчет
        await processing_msg.delete()
        await update.message.reply_html(report)
        
    except Exception as e:
        logger.error(f"Ошибка в sentiment: {e}", exc_info=True)
        await update.message.reply_text("⚠️ Произошла ошибка при анализе. Попробуйте позже.")

async def subscribe(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Информация о подписке"""
    await update.message.reply_html(
        "💰 <b>Система подписки (скоро!)</b>\n\n"
        "🔄 <b>В разработке:</b>\n"
        "• Подписка за $10/месяц\n"
        "• Ежедневные автоматические отчеты\n"
        "• Расширенный анализ по 50+ монетам\n"
        "• Персональные алерты\n"
        "• Доступ к историческим данным\n\n"
        "⏳ <i>Функция будет доступна в течение 48 часов. Следите за обновлениями!</i>\n\n"
        "📢 <b>Для первых 20 подписчиков:</b> 50% скидка!"
    )

async def daily(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ежедневный отчет"""
    await update.message.reply_html(
        "📅 <b>Ежедневный отчет</b>\n\n"
        "Эта функция находится в активной разработке.\n\n"
        "⚡ <b>Что будет:</b>\n"
        "• Автоматическая рассылка в 9:00 UTC\n"
        "• Анализ 10+ криптовалют\n"
        "• Итоги предыдущего дня\n"
        "• Прогноз на сегодня\n\n"
        "⏳ <i>Будет доступно после запуска системы подписки.</i>\n\n"
        "А пока используйте: <code>/sentiment BTC</code>"
    )

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик ошибок"""
    logger.error(f"Ошибка: {context.error}", exc_info=True)
    try:
        await update.message.reply_text("⚠️ Произошла ошибка. Попробуйте еще раз через минуту.")
    except:
        pass

# ===== ОСНОВНАЯ ФУНКЦИЯ =====
def main():
    """Запуск бота"""
    # Получаем токен из переменных окружения
    TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
    
    if not TOKEN:
        logger.error("❌ Токен бота не найден!")
        logger.info("Добавьте переменную окружения TELEGRAM_BOT_TOKEN на Render.com")
        return
    
    # Создаем приложение
    app = Application.builder().token(TOKEN).build()
    
    # Добавляем обработчики команд
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("coins", coins_command))
    app.add_handler(CommandHandler("sentiment", sentiment))
    app.add_handler(CommandHandler("subscribe", subscribe))
    app.add_handler(CommandHandler("daily", daily))
    
    # Обработчик ошибок
    app.add_error_handler(error_handler)
    
    # Запускаем бота
    logger.info("🤖 Бот запускается...")
    print("=" * 50)
    print("🤖 Crypto Sentinel AI Bot")
    print(f"🚀 Запущено: {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}")
    print(f"📊 Монет: {len(SUPPORTED_COINS)}")
    print("=" * 50)
    
    # Для Render используем polling
    app.run_polling(
        drop_pending_updates=True,
        allowed_updates=Update.ALL_TYPES,
    )

if __name__ == '__main__':
    main()
