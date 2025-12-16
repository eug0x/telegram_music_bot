import asyncio
import time
import os
import uuid
from aiogram import types, F
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile
from aiogram.exceptions import TelegramBadRequest
from core import strings
from core.config import (
    dp, bot, logger,
    BOT_START_TIME, ALLOWED_CHAT_IDS, ALLOW_PRIVATE_CHAT,
    BLOCKED_USER_IDS, ANTI_SPAM_INTERVAL, ENABLE_INLINE_SEARCH,
    CHAT_DB_PATH,
    FUZZY_DUPLICATE_THRESHOLD
)
from core.services.youtube import search_multiple, download_by_url, cleanup_temp_files, get_dislikes
from core.services.storage import (
    user_last_request_time,
    set_song_data,
    get_song_data
)

class BotProcessingError(Exception): pass
class NoResultsError(BotProcessingError): pass
class NoUrlError(BotProcessingError): pass
class NoAudioError(BotProcessingError): pass
class AudioTooLongError(BotProcessingError): pass
class AudioTooLargeError(BotProcessingError): pass


if ENABLE_INLINE_SEARCH:
    from core.services.inline_search.database import save_audio_to_db


async def remove_not_right_button(sent_message, key, full_name):
    await asyncio.sleep(60)
    try:
        current_data = get_song_data(key)
        if not current_data:
            return

        current_entry = current_data.get(f"info_{key}")
        if not current_entry:
            return

        current_kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=strings.BUTTON_REQUESTER.format(full_name), callback_data=f"info_{key}")]
        ])
        await bot.edit_message_reply_markup(
            chat_id=sent_message.chat.id,
            message_id=sent_message.message_id,
            reply_markup=current_kb
        )
    except Exception:
        pass


@dp.message()
async def message_handler(message: types.Message):
    user_id = message.from_user.id
    base = None
    key = None
    status = None

    if message.date.timestamp() < BOT_START_TIME: return
    
    is_private_chat = message.chat.type == 'private'
    is_allowed_group: bool = (0 in ALLOWED_CHAT_IDS or message.chat.id in ALLOWED_CHAT_IDS)

    if is_private_chat:
        if not ALLOW_PRIVATE_CHAT:
            return
            
    elif not is_allowed_group:
        return

    if user_id in BLOCKED_USER_IDS:
        logger.info(f"Blocked user {user_id} tried to use the bot.")
        return

    text = message.text or ""
    if not text.lower().startswith(strings.COMMAND_PREFIX): return

    now = time.time()
    if now - user_last_request_time.get(user_id, 0) < ANTI_SPAM_INTERVAL: return
    user_last_request_time[user_id] = now

    query = text[len(strings.COMMAND_PREFIX):].strip()
    if not query: return

    try:
        await message.delete()
    except Exception:
        pass

    status = await message.answer(strings.STATUS_SEARCHING)

    semaphore = dp['download_semaphore']

    try:
        async with semaphore:
            results = await search_multiple(query)

            if not results: raise NoResultsError("NO_RESULTS")

            first = results[0]
            url = first.get("url") or first.get("webpage_url")
            if not url: raise NoUrlError("NO_URL")

            info, file, thumb, base = await download_by_url(url)

            if not file: raise NoAudioError("NO_AUDIO")
            
        audio = FSInputFile(file, filename=os.path.basename(file))

        thumbnail = None
        if thumb:
            thumbnail = FSInputFile(thumb, filename=os.path.basename(thumb))

        sender_name = message.from_user.full_name
        key = uuid.uuid4().hex[:8]

        song_data = {
            "title": info.get("title"), "artist": info.get("uploader"), "thumb": thumb,
            "file": file, "base": base, "query": query, "url": url,
            "requester": user_id, "duration": info.get("duration"), "upload_date": info.get("upload_date"),
            "view_count": info.get("view_count"), "like_count": info.get("like_count"),
            "dislike_count": await get_dislikes(info.get("id")), "timestamp": time.time(),
        }
        set_song_data(key, 0, song_data)

        btn_text = strings.BUTTON_REQUESTER.format(sender_name)
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=btn_text, callback_data=f"info_{key}"),
             InlineKeyboardButton(text=strings.BUTTON_NOT_RIGHT, callback_data=f"alt_{key}")]
        ])

        await status.delete()

        sent = await bot.send_audio(
            chat_id=message.chat.id, audio=audio, title=info.get("title"),
            performer=info.get("uploader"), thumbnail=thumbnail, reply_markup=kb,
            reply_to_message_id=message.reply_to_message.message_id if message.reply_to_message else None
        )

        if ENABLE_INLINE_SEARCH and sent.audio:
            try:
                await save_audio_to_db(sent.audio, CHAT_DB_PATH, FUZZY_DUPLICATE_THRESHOLD)
            except Exception as e:
                logger.error(f"Failed to save song to DB: {e}")

        set_song_data(key, sent.message_id, song_data)

        asyncio.create_task(remove_not_right_button(sent, key, message.from_user.full_name))

    except NoResultsError:
        msg_error = strings.ERROR_PREFIX + strings.ERROR_NO_RESULTS
    except NoUrlError:
        msg_error = strings.ERROR_PREFIX + strings.ERROR_NO_RESULTS
    except NoAudioError:
        msg_error = strings.ERROR_PREFIX + strings.ERROR_NO_RESULTS
    except TelegramBadRequest as e:
        error_str = str(e)
        if "audio is too long" in error_str:
             msg_error = strings.ERROR_PREFIX + strings.ERROR_LONG_AUDIO
        elif "File is too big" in error_str:
             msg_error = strings.ERROR_PREFIX + strings.ERROR_TOO_LARGE
        else:
             logger.error(f"Telegram API Error: {error_str}", exc_info=True)
             msg_error = strings.ERROR_PREFIX + error_str
    except Exception as e:
        error_str = str(e)
        if "LONG_AUDIO" in error_str:
             msg_error = strings.ERROR_PREFIX + strings.ERROR_LONG_AUDIO
        elif "TOO_LARGE" in error_str:
             msg_error = strings.ERROR_PREFIX + strings.ERROR_TOO_LARGE
        else:
            logger.error(f"Download/Search Error: {error_str}", exc_info=True)
            msg_error = strings.ERROR_PREFIX + error_str

    else:
        return

    finally:
        if status:
            try: await status.delete()
            except: pass
        if base:
            cleanup_temp_files(base)

    err = await message.answer(msg_error)
    await asyncio.sleep(5)
    try: await err.delete()
    except Exception: pass


@dp.message(F.audio)
async def direct_audio_handler(message: types.Message):
    if not ENABLE_INLINE_SEARCH:
        return

    user_id = message.from_user.id

    if message.date.timestamp() < BOT_START_TIME: return
    
    is_private_chat = message.chat.type == 'private'
    is_allowed_group: bool = (0 in ALLOWED_CHAT_IDS or message.chat.id in ALLOWED_CHAT_IDS)

    if is_private_chat:
        if not ALLOW_PRIVATE_CHAT:
            return
            
    elif not is_allowed_group:
        return

    if user_id in BLOCKED_USER_IDS:
        logger.info(f"Blocked user {user_id} tried to use the bot.")
        return

    try:
        result = await save_audio_to_db(message.audio, CHAT_DB_PATH, FUZZY_DUPLICATE_THRESHOLD)
        
        if result == True:
            logger.info(f"Audio saved to DB (direct upload): {message.audio.performer} - {message.audio.title}")
        elif result and result.startswith("duplicate"):
            logger.info(f"Audio skipped (duplicate): {message.audio.performer} - {message.audio.title}")

    except Exception as e:
        logger.error(f"Error saving direct audio to DB: {e}")