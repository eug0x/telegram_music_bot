import asyncio
import os
import logging
import sys
import aiohttp

sys.path.append(os.path.dirname(os.path.abspath(__file__))) 

from core.config import dp, bot, logger, CONCURRENT_DOWNLOAD_LIMIT 
from core.services.storage import song_data_storage
from core.services.youtube import GLOBAL_HTTP_SESSION, close_global_session

from core.handlers import messages, callbacks 


async def main():
    global GLOBAL_HTTP_SESSION
    if GLOBAL_HTTP_SESSION is None:
        GLOBAL_HTTP_SESSION = aiohttp.ClientSession()
    
    if not bot.token:
        logger.error("BOT_TOKEN is not set in the .env file. The bot cannot start.")
        return 

    logger.info(f"Start polling")
    logger.info(f"Loaded {len(song_data_storage)} cached songs.")
    
    try:
        await dp.start_polling(bot)
    finally:
        await close_global_session()
        logger.warning("Bot finished polling and closing session.")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.warning("Bot stopped!")