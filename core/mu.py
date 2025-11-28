import asyncio
import time
import os
import uuid
from typing import Dict, Any, List
from aiogram import types, F
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, InputMediaAudio
from core.config import dp, bot, CONCURRENT_DOWNLOAD_LIMIT
from aiogram.exceptions import TelegramBadRequest

from . import config
from . import data_manager
from . import strings
from . import youtube_downloader

dp = config.dp
bot = config.bot
logger = config.logger

song_data_storage = data_manager.song_data_storage
user_last_request_time = data_manager.user_last_request_time

BOT_START_TIME = config.BOT_START_TIME
ALLOWED_CHAT_IDS = config.ALLOWED_CHAT_IDS
ALLOW_PRIVATE_CHAT = config.ALLOW_PRIVATE_CHAT
BLOCKED_USER_IDS = config.BLOCKED_USER_IDS
ANTI_SPAM_INTERVAL = config.ANTI_SPAM_INTERVAL
MAX_SONG_DURATION_SEC = config.MAX_SONG_DURATION_SEC

cleanup_temp_files = youtube_downloader.cleanup_temp_files
search_multiple = youtube_downloader.search_multiple
download_by_url = youtube_downloader.download_by_url
get_dislikes = youtube_downloader.get_dislikes
format_number_dot = data_manager.format_number_dot
save_song_data = data_manager.save_song_data

@dp.message()
async def message_handler(message: types.Message):
    user_id = message.from_user.id

    if message.date.timestamp() < BOT_START_TIME:
        return

    is_private_chat = message.chat.type == 'private'
    is_allowed_group: bool = (
        0 in ALLOWED_CHAT_IDS
        or message.chat.id in ALLOWED_CHAT_IDS
    )

    if not ((is_private_chat and ALLOW_PRIVATE_CHAT) or is_allowed_group):
        return

    if user_id in BLOCKED_USER_IDS:
        logger.info(f"Blocked user {user_id} tried to use the bot.")
        return

    text = message.text or ""

    if not text.lower().startswith(strings.COMMAND_PREFIX):
        return

    now = time.time()
    if now - user_last_request_time.get(user_id, 0) < ANTI_SPAM_INTERVAL:
        return
    user_last_request_time[user_id] = now

    query = text[len(strings.COMMAND_PREFIX):].strip()

    if not query:
        return

    try:
        await message.delete()
    except Exception:
        pass

    status = await message.answer(strings.STATUS_SEARCHING)

    semaphore = dp['download_semaphore']

    try:
        async with semaphore:
            results = await search_multiple(query)

            if not results:
                raise Exception("NO_RESULTS")

            first = results[0]
            url = first.get("url") or first.get("webpage_url")
            if not url:
                raise Exception("NO_URL")

            info, file, thumb, base = await download_by_url(url)

            if not file:
                raise Exception("NO_AUDIO")

        with open(file, "rb") as f:
            audio = types.BufferedInputFile(f.read(), filename=os.path.basename(file))

        thumbnail = None
        if thumb:
            with open(thumb, "rb") as t:
                thumbnail = types.BufferedInputFile(t.read(), filename=os.path.basename(thumb))

        sender_name = message.from_user.full_name
        btn_text = strings.BUTTON_REQUESTER.format(sender_name)
        key = uuid.uuid4().hex[:8]

        song_data_storage[f"info_{key}"] = {
            "title": info.get("title"),
            "artist": info.get("uploader"),
            "thumb": thumb,
            "file": file,
            "base": base,
            "query": query,
            "url": url,
            "requester": user_id,
            "duration": info.get("duration"),
            "upload_date": info.get("upload_date"),
            "view_count": info.get("view_count"),
            "like_count": info.get("like_count"),
            "dislike_count": await get_dislikes(info.get("id")),
            "timestamp": time.time(),
        }
        save_song_data(song_data_storage)

        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=btn_text, callback_data=f"info_{key}"),
             InlineKeyboardButton(text=strings.BUTTON_NOT_RIGHT, callback_data=f"alt_{key}")]
        ])

        await status.delete()

        sent = await bot.send_audio(
            chat_id=message.chat.id,
            audio=audio,
            title=info.get("title"),
            performer=info.get("uploader"),
            thumbnail=thumbnail,
            reply_markup=kb,
            reply_to_message_id=message.reply_to_message.message_id if message.reply_to_message else None
        )

        song_data_storage[f"msg_{key}"] = sent.message_id
        save_song_data(song_data_storage)

        async def remove_not_right_button():
            await asyncio.sleep(60)
            try:
                current_entry = song_data_storage.get(f"info_{key}")
                if not current_entry:
                     return 

                current_kb = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text=strings.BUTTON_REQUESTER.format(message.from_user.full_name), callback_data=f"info_{key}")]
                ])
                await bot.edit_message_reply_markup(
                    chat_id=sent.chat.id,
                    message_id=sent.message_id,
                    reply_markup=current_kb
                )
            except Exception:
                pass

        asyncio.create_task(remove_not_right_button())
        cleanup_temp_files(base)

    except Exception as e:
        if 'base' in locals():
            cleanup_temp_files(base)

        await status.delete()
        msg_error = strings.ERROR_PREFIX

        error_str = str(e)
        if "LONG_AUDIO" in error_str:
            msg_error += strings.ERROR_LONG_AUDIO
        elif "TOO_LARGE" in error_str:
            msg_error += strings.ERROR_TOO_LARGE
        elif "NO_RESULTS" in error_str:
            msg_error += strings.ERROR_NO_RESULTS
        else:
            logger.error(f"Download/Search Error: {error_str}", exc_info=True)
            msg_error += error_str

        err = await message.answer(msg_error)
        await asyncio.sleep(5)
        try:
            await err.delete()
        except Exception:
            pass

        asyncio.create_task(remove_not_right_button())
        cleanup_temp_files(base)

    except Exception as e:
        if 'base' in locals():
            cleanup_temp_files(base)

        await status.delete()
        msg_error = strings.ERROR_PREFIX

        error_str = str(e)
        if "LONG_AUDIO" in error_str:
            msg_error += strings.ERROR_LONG_AUDIO
        elif "TOO_LARGE" in error_str:
            msg_error += strings.ERROR_TOO_LARGE
        elif "NO_RESULTS" in error_str:
            msg_error += strings.ERROR_NO_RESULTS
        else:
            logger.error(f"Download/Search Error: {error_str}", exc_info=True)
            msg_error += error_str

        err = await message.answer(msg_error)
        await asyncio.sleep(5)
        try:
            await err.delete()
        except Exception:
            pass

@dp.callback_query(F.data.startswith("alt_"))
async def show_alternatives(cq: CallbackQuery):
    key = cq.data[4:]
    entry = song_data_storage.get(f"info_{key}")

    if not entry:
        await cq.answer(strings.INFO_EXPIRED, show_alert=True)
        return

    if cq.from_user.id != entry.get("requester"):
        await cq.answer(strings.NOT_FOR_YOU, show_alert=True)
        return

    query = entry.get("query", "")
    if not query:
        await cq.answer("Error: Query not found in cache.", show_alert=True)
        return

    results = await search_multiple(query)
    btns = []
    count = 0

    for r in results:
        duration = r.get("duration", 0)
        if duration and duration > MAX_SONG_DURATION_SEC:
            continue

        video_id = r.get('id')
        if not video_id:
            continue

        title_short = (r.get("title") or strings.UNTITLED_SONG)[:40]
        btns.append([InlineKeyboardButton(text=title_short, callback_data=f"choose_{key}_{video_id}")])
        count += 1
        if count >= 10:
            break

    if not btns:
        await cq.answer("No suitable alternatives found.", show_alert=True)
        return

    btns.append([InlineKeyboardButton(text=strings.BUTTON_CANCEL, callback_data=f"cancel_{key}")])
    await cq.message.edit_reply_markup(reply_markup=InlineKeyboardMarkup(inline_keyboard=btns))
    await cq.answer()

@dp.callback_query(F.data.startswith("cancel_"))
async def cancel_alt(cq: CallbackQuery):
    key = cq.data[7:]
    entry = song_data_storage.get(f"info_{key}")

    if not entry:
        await cq.answer(strings.INFO_EXPIRED, show_alert=True)
        return

    if cq.from_user.id != entry.get("requester"):
        await cq.answer(strings.NOT_FOR_YOU, show_alert=True)
        return

    sender_name = cq.from_user.full_name
    btn_text = strings.BUTTON_REQUESTER.format(sender_name)

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=btn_text, callback_data=f"info_{key}"),
         InlineKeyboardButton(text=strings.BUTTON_NOT_RIGHT, callback_data=f"alt_{key}")]
    ])

    await cq.message.edit_reply_markup(reply_markup=kb)
    await cq.answer()

@dp.callback_query(F.data.startswith("choose_"))
async def choose_song(cq: CallbackQuery):
    parts = cq.data.split("_", 2)
    key = parts[1]
    video_id = parts[2]
    entry = song_data_storage.get(f"info_{key}")

    if not entry:
        await cq.answer(strings.INFO_EXPIRED, show_alert=True)
        return

    if cq.from_user.id != entry.get("requester"):
        await cq.answer(strings.NOT_FOR_YOU, show_alert=True)
        return

    base_old = entry.get("base")
    if base_old:
        cleanup_temp_files(base_old)

    await cq.message.edit_reply_markup(reply_markup=None)

    url = f"https://www.youtube.com/watch?v={video_id}"
    info = None
    file = None
    thumb = None
    base = None

    semaphore = dp['download_semaphore']

    try:
        async with semaphore:
            info, file, thumb, base = await download_by_url(url)
    except Exception as e:
        error_str = str(e)
        if "TOO_LARGE" in error_str:
            await cq.answer(strings.ERROR_TOO_LARGE, show_alert=True)
        elif "LONG_AUDIO" in error_str:
            await cq.answer(strings.ERROR_LONG_AUDIO, show_alert=True)
        else:
            logger.error(f"Download Error for alternative: {error_str}", exc_info=True)
            await cq.answer(f"Error: {error_str}", show_alert=True)
        
        sender_name = cq.from_user.full_name
        btn_text = strings.BUTTON_REQUESTER.format(sender_name)
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=btn_text, callback_data=f"info_{key}"),
             InlineKeyboardButton(text=strings.BUTTON_NOT_RIGHT, callback_data=f"alt_{key}")]
        ])
        try:
            await cq.message.edit_reply_markup(reply_markup=kb)
        except Exception:
            pass
        return

    if not file:
        cleanup_temp_files(base)
        await cq.answer("Error during download. No audio file found.", show_alert=True)
        return

    with open(file, "rb") as f:
        audio = types.BufferedInputFile(f.read(), filename=os.path.basename(file))

    thumbnail = None
    if thumb:
        with open(thumb, "rb") as t:
            thumbnail = types.BufferedInputFile(t.read(), filename=os.path.basename(thumb))

    sender_name = cq.from_user.full_name
    btn_text = strings.BUTTON_REQUESTER.format(sender_name)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=btn_text, callback_data=f"info_{key}")]
    ])

    try:
        await bot.edit_message_media(
            media=InputMediaAudio(media=audio, title=info.get("title"), performer=info.get("uploader"), thumbnail=thumbnail),
            chat_id=cq.message.chat.id,
            message_id=song_data_storage.get(f"msg_{key}"),
            reply_markup=kb
        )
    except TelegramBadRequest as e:
        cleanup_temp_files(base)
        logger.error(f"TelegramBadRequest when updating media: {e}")
        await cq.answer(strings.FAILED_TO_UPDATE.format(str(e)), show_alert=True)
        return

    song_data_storage[f"info_{key}"] = {
        "title": info.get("title"),
        "artist": info.get("uploader"),
        "thumb": thumb,
        "file": file,
        "base": base,
        "query": entry.get("query"), 
        "url": url,
        "requester": cq.from_user.id,
        "duration": info.get("duration"),
        "upload_date": info.get("upload_date"),
        "view_count": info.get("view_count"),
        "like_count": info.get("like_count"),
        "dislike_count": await get_dislikes(info.get("id")),
        "timestamp": time.time(),
    }
    save_song_data(song_data_storage)
    
    cleanup_temp_files(base) 
    
    await cq.answer(strings.SONG_UPDATED)

@dp.callback_query(F.data.startswith("info_"))
async def show_song_info(cq: CallbackQuery):
    key = cq.data
    data = song_data_storage.get(key)

    if not data:
        await cq.answer(strings.INFO_EXPIRED, show_alert=True)
        return

    views = format_number_dot(data.get("view_count"))
    likes = format_number_dot(data.get("like_count"))
    dislikes = format_number_dot(data.get("dislike_count"))

    msg = strings.get_song_info_message(data, views, likes, dislikes)

    await cq.answer(msg, show_alert=True)