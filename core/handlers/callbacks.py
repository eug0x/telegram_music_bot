import time
import asyncio
import os
from functools import wraps
from typing import Dict, Any, Optional, Tuple
from aiogram import F
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, InputMediaAudio, FSInputFile, Message
from aiogram.exceptions import TelegramBadRequest
from core import strings
from core.config import dp, bot, logger, MAX_SONG_DURATION_SEC, ANTI_SPAM_CALLBACK_INTERVAL
from core.services.youtube import search_multiple, download_by_url, cleanup_temp_files, get_dislikes
from core.services.storage import (
  get_song_data,
  set_song_data,
  format_number_dot,
  user_last_request_time,
)


def check_callback_spam(func):
    @wraps(func)
    async def wrapper(cq: CallbackQuery, *args, **kwargs):
        user_id = cq.from_user.id
        now = time.time()

        if now - user_last_request_time.get(user_id, 0) < ANTI_SPAM_CALLBACK_INTERVAL:
            user_last_request_time[user_id] = now
            return

        user_last_request_time[user_id] = now
        return await func(cq, *args, **kwargs)
    return wrapper


async def safe_answer_callback(callback_query_id: str, text: str, show_alert: bool = False) -> None:
    try:
        await bot.answer_callback_query(
            callback_query_id=callback_query_id, text=text, show_alert=show_alert
        )
    except TelegramBadRequest as e:
        logger.warning(f"Failed to answer callback_query {callback_query_id}: {e}")


async def _check_access(cq: CallbackQuery, key: str) -> Optional[Tuple[Dict[str, Any], int]]:
  data_storage = await get_song_data(key)

  if not data_storage:
    asyncio.create_task(safe_answer_callback(cq.id, strings.INFO_EXPIRED, show_alert=True))
    return None

  entry: Optional[Dict[str, Any]] = data_storage.get(f"info_{key}")
  message_id: Optional[int] = data_storage.get(f"msg_{key}")
  if not isinstance(entry, dict) or not isinstance(message_id, int):
     asyncio.create_task(safe_answer_callback(cq.id, strings.INFO_EXPIRED, show_alert=True))
     return None

  if cq.from_user.id != entry.get("requester"):
    asyncio.create_task(safe_answer_callback(cq.id, strings.NOT_FOR_YOU, show_alert=True))
    return None

  return entry, message_id


@dp.callback_query(F.data.startswith("alt_"))
@check_callback_spam
async def show_alternatives(cq: CallbackQuery):
  key = cq.data[4:] # type: ignore
  result = await _check_access(cq, key)
  if not result:
    return
  entry, _ = result # type: ignore

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
  try:
    if cq.message:
      await cq.message.edit_reply_markup(reply_markup=InlineKeyboardMarkup(inline_keyboard=btns)) # type: ignore
  except (TelegramBadRequest, AttributeError, TypeError) as e:
    logger.warning(f"Failed to edit alt menu for {key}: {e}")
    pass
  await cq.answer()


@dp.callback_query(F.data.startswith("cancel_"))
@check_callback_spam
async def cancel_alt(cq: CallbackQuery):
  key = cq.data[7:] # type: ignore
  result = await _check_access(cq, key)
  if not result:
    return
  entry, _ = result # type: ignore

  sender_name = cq.from_user.full_name
  btn_text = strings.BUTTON_REQUESTER.format(sender_name)

  kb = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text=btn_text, callback_data=f"info_{key}"),
      InlineKeyboardButton(text=strings.BUTTON_NOT_RIGHT, callback_data=f"alt_{key}")]
  ])

  try:
    if cq.message:
      await cq.message.edit_reply_markup(reply_markup=kb) # type: ignore
  except (TelegramBadRequest, AttributeError, TypeError) as e:
    logger.warning(f"Failed to restore markup in cancel_alt for {key}: {e}")
    pass
  await cq.answer()


@dp.callback_query(F.data.startswith("choose_"))
@check_callback_spam
async def choose_song(cq: CallbackQuery):
  parts = cq.data.split("_", 2) # type: ignore
  key = parts[1]
  video_id = parts[2]

  result = await _check_access(cq, key)
  if not result:
    return
  entry, message_id = result # type: ignore

  temp_file_base = None

  old_temp_file_base = entry.get("base")
  if old_temp_file_base:
    await cleanup_temp_files(old_temp_file_base)

  try:
    if cq.message:
      await cq.message.edit_reply_markup(reply_markup=None) # type: ignore
  except (TelegramBadRequest, AttributeError, TypeError) as e:
    logger.warning(f"Failed to remove markup in choose_song start for {key}: {e}")
    pass

  url = f"https://www.youtube.com/watch?v={video_id}"
  semaphore = dp['download_semaphore']

  try:
    async with semaphore:
      info, file, thumb, temp_file_base = await download_by_url(url)
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
    try:
      if cq.message:
        await cq.message.edit_reply_markup(reply_markup=kb) # type: ignore
    except (TelegramBadRequest, AttributeError, TypeError) as edit_e:
      logger.warning(f"Failed to restore markup in choose_song error block for {key}: {edit_e}")
      pass
    return

  if not file:
    await cleanup_temp_files(temp_file_base)
    await cq.answer("Error during download. No audio file found.", show_alert=True)
    return

  thumbnail = None
  if thumb and os.path.exists(thumb):
      thumbnail = FSInputFile(thumb)

  sender_name = cq.from_user.full_name
  btn_text = strings.BUTTON_REQUESTER.format(sender_name)
  kb = InlineKeyboardMarkup(inline_keyboard=[
      [InlineKeyboardButton(text=btn_text, callback_data=f"info_{key}")]
  ])

  try:
      if cq.message and isinstance(cq.message, Message):
          await cq.message.edit_media(
              media=InputMediaAudio(
                  media=FSInputFile(file),
                  title=info.get("title"),
                  performer=info.get("uploader"),
                  thumbnail=thumbnail
              ),
              reply_markup=kb
          )
      else:
          logger.error("Message is inaccessible or not a valid Message object.")

  except TelegramBadRequest as e:
      await cleanup_temp_files(temp_file_base)
      logger.error(f"TelegramBadRequest when updating media: {e}")
      await cq.answer(strings.FAILED_TO_UPDATE.format(str(e)), show_alert=True)
      return

  new_song_data = {
    **entry,
    "title": info.get("title"), "artist": info.get("uploader"), "thumb": thumb,
    "file": file, "base": temp_file_base, "url": url, "requester": cq.from_user.id,
    "duration": info.get("duration"), "upload_date": info.get("upload_date"),
    "view_count": info.get("view_count") or 0,
    "like_count": info.get("like_count") or 0,
    "dislike_count": await get_dislikes(info.get("id")), "timestamp": time.time(),
  }
  await set_song_data(key, message_id, new_song_data)

  await cleanup_temp_files(temp_file_base)
  await cq.answer(strings.SONG_UPDATED)


@dp.callback_query(F.data.startswith("info_"))
@check_callback_spam
async def show_song_info(cq: CallbackQuery):
  key = cq.data[5:] # type: ignore
  data_storage = await get_song_data(key)

  if not data_storage:
    await cq.answer(strings.INFO_EXPIRED, show_alert=True)
    return

  data: Optional[Dict[str, Any]] = data_storage.get(cq.data) # type: ignore
  if not isinstance(data, dict):
    await cq.answer(strings.INFO_EXPIRED, show_alert=True)
    logger.warning(f"Info data is missing or invalid for key: {key}")
    return

  views = format_number_dot(data.get("view_count") or 0)
  likes = format_number_dot(data.get("like_count") or 0)
  dislikes = format_number_dot(data.get("dislike_count") or 0)

  msg = strings.get_song_info_message(data, views, likes, dislikes)

  MAX_ALERT_LENGTH = 200
  if len(msg) > MAX_ALERT_LENGTH:
    msg = msg[:MAX_ALERT_LENGTH - 3] + "..."

  await cq.answer(msg, show_alert=True)
