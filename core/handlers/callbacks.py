import time
import asyncio
import os
from aiogram import F, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, InputMediaAudio, BufferedInputFile
from aiogram.exceptions import TelegramBadRequest
from core import strings
from core.config import dp, bot, logger, MAX_SONG_DURATION_SEC, ANTI_SPAM_CALLBACK_INTERVAL
from core.services.youtube import search_multiple, download_by_url, cleanup_temp_files, get_dislikes
from core.services.storage import (
    song_data_storage, 
    save_song_data, 
    format_number_dot, 
    user_last_request_time,
)

def check_callback_spam(func):
    async def wrapper(cq: CallbackQuery):
        user_id = cq.from_user.id
        now = time.time()
        
        if now - user_last_request_time.get(user_id, 0) < ANTI_SPAM_CALLBACK_INTERVAL:
            
            user_last_request_time[user_id] = now
            
            return

        user_last_request_time[user_id] = now 
        
        await func(cq)

    return wrapper

def _check_access(cq: CallbackQuery, key: str):
    entry = song_data_storage.get(f"info_{key}")

    if not entry:
        asyncio.create_task(bot.answer_callback_query(
            callback_query_id=cq.id, 
            text=strings.INFO_EXPIRED, 
            show_alert=True
        ))
        return None

    if cq.from_user.id != entry.get("requester"):
        asyncio.create_task(bot.answer_callback_query(
            callback_query_id=cq.id, 
            text=strings.NOT_FOR_YOU, 
            show_alert=True
        ))
        return None

    return entry

@dp.callback_query(F.data.startswith("alt_"))
@check_callback_spam
async def show_alternatives(cq: CallbackQuery):
    key = cq.data[4:]
    entry = _check_access(cq, key)
    if not entry:
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
@check_callback_spam
async def cancel_alt(cq: CallbackQuery):
    key = cq.data[7:]
    entry = _check_access(cq, key)
    if not entry:
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
@check_callback_spam
async def choose_song(cq: CallbackQuery):
    parts = cq.data.split("_", 2)
    key = parts[1]
    video_id = parts[2]
    entry = _check_access(cq, key)
    if not entry:
        return

    base = None
    
    base_old = entry.get("base")
    if base_old:
        cleanup_temp_files(base_old)

    await cq.message.edit_reply_markup(reply_markup=None)

    url = f"https://www.youtube.com/watch?v={video_id}"
    semaphore = dp['download_semaphore']

    try:
        async with semaphore:
            info, file, thumb, base = await download_by_url(url)
    except Exception as e:
        error_str = str(e)
        if "TOO_LARGE" in error_str: await cq.answer(strings.ERROR_TOO_LARGE, show_alert=True)
        elif "LONG_AUDIO" in error_str: await cq.answer(strings.ERROR_LONG_AUDIO, show_alert=True)
        else:
            logger.error(f"Download Error for alternative: {error_str}", exc_info=True)
            await cq.answer(f"Error: {error_str}", show_alert=True)
        
        sender_name = cq.from_user.full_name
        btn_text = strings.BUTTON_REQUESTER.format(sender_name)
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=btn_text, callback_data=f"info_{key}"),
             InlineKeyboardButton(text=strings.BUTTON_NOT_RIGHT, callback_data=f"alt_{key}")]
        ])
        try: await cq.message.edit_reply_markup(reply_markup=kb)
        except Exception: pass
        return

    if not file:
        cleanup_temp_files(base)
        await cq.answer("Error during download. No audio file found.", show_alert=True)
        return

    with open(file, "rb") as f:
        audio = BufferedInputFile(f.read(), filename=os.path.basename(file))

    thumbnail = None
    if thumb:
        with open(thumb, "rb") as t:
            thumbnail = BufferedInputFile(t.read(), filename=os.path.basename(thumb))

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
        **entry,
        "title": info.get("title"), "artist": info.get("uploader"), "thumb": thumb, 
        "file": file, "base": base, "url": url, "requester": cq.from_user.id,
        "duration": info.get("duration"), "upload_date": info.get("upload_date"),
        "view_count": info.get("view_count"), "like_count": info.get("like_count"),
        "dislike_count": await get_dislikes(info.get("id")), "timestamp": time.time(),
    }
    save_song_data(song_data_storage)
    
    cleanup_temp_files(base)
    await cq.answer(strings.SONG_UPDATED)


@dp.callback_query(F.data.startswith("info_"))
@check_callback_spam
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