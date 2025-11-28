import asyncio
import os
import logging
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__))) 

from core.config import dp, bot, logger 
from core.mu import song_data_storage 

from core import mu 

if __name__ == "__main__":
    if not bot.token:
        logger.error("BOT_TOKEN is not set in the .env file. The bot cannot start.")
    else:
        logger.info(f"Start polling")
        logger.info(f"Loaded {len(song_data_storage)} cached songs.")
        asyncio.run(dp.start_polling(bot))