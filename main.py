import asyncio
import os
import logging
import sys
import aiohttp

sys.path.append(os.path.dirname(os.path.abspath(__file__))) 

from core.config import dp, bot, logger, CONCURRENT_DOWNLOAD_LIMIT 
from core.services import storage 
from core.services.youtube import close_global_session 
from core.handlers import messages, callbacks 

async def main():
    
    if not bot.token:
        logger.error("BOT_TOKEN is not set in the .env file. The bot cannot start.")
        return 

    storage.cleanup_expired_data()
    
    logger.info(f"Start polling")
    
    try:
        await dp.start_polling(bot)
    finally:
        await close_global_session() # Використовуємо функцію закриття
        logger.warning("Bot finished polling and closing session.")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.warning("Bot stopped!")