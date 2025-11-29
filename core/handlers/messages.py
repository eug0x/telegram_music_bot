import asyncio
import time
import os
import uuid
from aiogram import types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, BufferedInputFile

from core import strings 
from core.config import (
    dp, bot, logger, 
    BOT_START_TIME, ALLOWED_CHAT_IDS, ALLOW_PRIVATE_CHAT, 
    BLOCKED_USER_IDS, ANTI_SPAM_INTERVAL
)
from core.services.youtube import search_multiple, download_by_url, cleanup_temp_files, get_dislikes
from core.services.storage import (
    song_data_storage, user_last_request_time, 
    save_song_data
)


async def remove_not_right_button(sent_message, key, full_name):
    await asyncio.sleep(60)
    try:
        current_entry = song_data_storage.get(f"info_{key}")
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

    if message.date.timestamp() < BOT_START_TIME: return
    is_private_chat = message.chat.type == 'private'
    is_allowed_group: bool = (0 in ALLOWED_CHAT_IDS or message.chat.id in ALLOWED_CHAT_IDS)
    if not ((is_private_chat and ALLOW_PRIVATE_CHAT) or is_allowed_group): return
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

            if not results: raise Exception("NO_RESULTS")

            first = results[0]
            url = first.get("url") or first.get("webpage_url")
            if not url: raise Exception("NO_URL")

            info, file, thumb, base = await download_by_url(url)

            if not file: raise Exception("NO_AUDIO")

        with open(file, "rb") as f:
            audio = BufferedInputFile(f.read(), filename=os.path.basename(file))

        thumbnail = None
        if thumb:
            with open(thumb, "rb") as t:
                thumbnail = BufferedInputFile(t.read(), filename=os.path.basename(thumb))

        sender_name = message.from_user.full_name
        key = uuid.uuid4().hex[:8]
        
        song_data_storage[f"info_{key}"] = {
            "title": info.get("title"), "artist": info.get("uploader"), "thumb": thumb, 
            "file": file, "base": base, "query": query, "url": url, 
            "requester": user_id, "duration": info.get("duration"), "upload_date": info.get("upload_date"),
            "view_count": info.get("view_count"), "like_count": info.get("like_count"),
            "dislike_count": await get_dislikes(info.get("id")), "timestamp": time.time(),
        }
        save_song_data(song_data_storage)

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

        song_data_storage[f"msg_{key}"] = sent.message_id
        save_song_data(song_data_storage)
        
        asyncio.create_task(remove_not_right_button(sent, key, message.from_user.full_name))

    except Exception as e:
        await status.delete()
        msg_error = strings.ERROR_PREFIX
        error_str = str(e)
        
        if "LONG_AUDIO" in error_str: msg_error += strings.ERROR_LONG_AUDIO
        elif "TOO_LARGE" in error_str: msg_error += strings.ERROR_TOO_LARGE
        elif "NO_RESULTS" in error_str or "NO_URL" in error_str or "NO_AUDIO" in error_str:
            msg_error += strings.ERROR_NO_RESULTS
        else:
            logger.error(f"Download/Search Error: {error_str}", exc_info=True)
            msg_error += error_str
        
        err = await message.answer(msg_error)
        await asyncio.sleep(5)
        try: await err.delete()
        except Exception: pass

    finally:
        if base:
            cleanup_temp_files(base)