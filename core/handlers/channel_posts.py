import os
from aiogram import Router, F, Bot
from aiogram.types import Message
from aiogram.exceptions import TelegramBadRequest
from core.config import logger, MUSIC_STORAGE_CHANNEL_ID, CHANNEL_DB_PATH, FUZZY_DUPLICATE_THRESHOLD
from core.services.inline_search.database import save_audio_to_db


router = Router()

if MUSIC_STORAGE_CHANNEL_ID != 0:
    router.message.filter(F.chat.id == MUSIC_STORAGE_CHANNEL_ID)

@router.channel_post(F.audio)
async def handle_new_audio_post(message: Message, bot: Bot):
    if MUSIC_STORAGE_CHANNEL_ID == 0 or MUSIC_STORAGE_CHANNEL_ID == -1:
        return

    if not message.audio:
        return

    audio = message.audio

    try:
        file = await bot.get_file(audio.file_id)
        file_path = file.file_path or ''

        if not file_path.lower().endswith('.mp3'):
            logger.warning(
                f"❌ NOT MP3. DELETING {message.message_id}. File path: {file_path}"
            )
            await message.delete()
            return

    except TelegramBadRequest as e:
        logger.error(
            f"❌ API error during file_id verification {audio.file_id}: {e}. DELETING {message.message_id}."
        )
        await message.delete()
        return

    result = await save_audio_to_db(audio, CHANNEL_DB_PATH, FUZZY_DUPLICATE_THRESHOLD)

    log_message = f"[{audio.performer} - {audio.title}] | MSG_ID: {message.message_id} | Result: {result}"

    if result is True:
        logger.info(f"✅ Successfully indexed: {log_message}")

    elif result == "duplicate_exact":
        logger.warning(f"⚠️ Exact duplicate found: DELETING {log_message}")
        await message.delete()

    elif result == "duplicate_fuzzy":
        logger.warning(f"⚠️ Fuzzy duplicate found: DELETING {log_message}")
        await message.delete()

    elif result == "error":
        logger.error(f"❌ Indexing error: {log_message}")

    else:
        logger.error(f"❌ Unknown indexing result: {log_message}")