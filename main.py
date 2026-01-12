# main.py

import asyncio
import os
import logging
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from core.config import dp, bot, logger, CONCURRENT_DOWNLOAD_LIMIT, ENABLE_INLINE_SEARCH, CHAT_DB_PATH, CHANNEL_DB_PATH
from core.services import storage
from core.services.youtube import close_global_session
from core.handlers import messages, callbacks
from core.handlers.channel_posts import router as channel_router
from core.yt_dlp_update.yt_dlp_manager import initialize as initialize_yt_dlp 

if ENABLE_INLINE_SEARCH:
    from core.handlers.inline_mode import router as inline_router
    from core.services.inline_search.database import init_db as init_inline_db


async def main():
    logger.info("Starting bot initialization...")
    
    if not bot.token:
        logger.error("BOT_TOKEN is not set in the .env file. The bot cannot start.")
        return

    try:
        if not initialize_yt_dlp():
            logger.critical("FATAL: Failed to ensure yt-dlp package is ready. Aborting.")
            return
    except RuntimeError as e:
        logger.critical(f"FATAL: yt-dlp initialization failed: {e}")
        return
        
    if ENABLE_INLINE_SEARCH:
        try:
            logger.info("Inline Search module enabled. Initializing databases...")
            await init_inline_db(CHANNEL_DB_PATH)
            await init_inline_db(CHAT_DB_PATH)
            dp.include_router(inline_router)
            logger.info("Inline router registered successfully.")
        except Exception as e:
            logger.critical(f"FATAL ERROR during Inline Search initialization: {e}")
            
    dp.include_router(channel_router)
    logger.info("Channel indexing router registered successfully.")
            
    storage.cleanup_expired_data()
    
    logger.info(f"Starting polling with {CONCURRENT_DOWNLOAD_LIMIT} concurrent download limit.")
    
    try:
        await dp.start_polling(bot)
    finally:
        await close_global_session()
        logger.warning("Bot finished polling and closing global HTTP session.")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.warning("Bot stopped!")
    except Exception as e:
        logger.critical(f"Critical error during bot runtime: {e}")