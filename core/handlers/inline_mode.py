import asyncio
import logging
from cachetools import TTLCache
from aiogram import Router, Bot
from aiogram.types import InlineQuery, InlineQueryResultCachedAudio
from aiogram.exceptions import TelegramBadRequest

from ..services.inline_search.fts5_search import search_fts
from ..services.inline_search.rapidfuzz_search import search_rapidfuzz

import core.config as Config

user_throttle = TTLCache(maxsize=1000, ttl=0.5)

CHANNEL_ID = Config.CHANNEL_ID
router = Router()
logger = logging.getLogger(__name__)


async def combine_search_results(query: str):
    clean_query = query.strip()
    if not clean_query:
        return []

    fts_tasks = [
        search_fts(clean_query, Config.CHANNEL_DB_PATH, limit=500),
        search_fts(clean_query, Config.CHAT_DB_PATH, limit=500),
    ]
    fts_results = await asyncio.gather(*fts_tasks)

    fts_channel = fts_results[0] if fts_results else []
    fts_chat = fts_results[1] if len(fts_results) > 1 else []

    fuzzy_tasks = [
        search_rapidfuzz(clean_query, fts_channel, limit=100, cutoff=35),
        search_rapidfuzz(clean_query, fts_chat, limit=100, cutoff=35),
    ]
    all_results = await asyncio.gather(*fuzzy_tasks)

    unique_songs = {}
    final_list = []

    for results in all_results:
        for song in results:
            song_id, file_id, title, performer, is_cached, db_tag, score = song
            unique_key = f"{db_tag}:{song_id}"

            if unique_key not in unique_songs:
                song_data = {
                    'song_id': song_id,
                    'file_id': file_id,
                    'title': title,
                    'performer': performer,
                    'is_cached': is_cached,
                    'db_tag': db_tag,
                    'unique_key': unique_key,
                    'score': score,
                    'db_name': Config.CHANNEL_DB_PATH if db_tag.startswith('channel') else Config.CHAT_DB_PATH
                }
                unique_songs[unique_key] = song_data
                final_list.append(song_data)

    final_list.sort(
        key=lambda x: (
            x['is_cached'],
            x['score'],
            1 if x['db_name'] == Config.CHAT_DB_PATH else 0
        ),
        reverse=True
    )

    return final_list[:50]


@router.inline_query()
async def inline_music_search(inline_query: InlineQuery, bot: Bot):
    user_id = inline_query.from_user.id

    if user_id in user_throttle:
        return
    user_throttle[user_id] = True

    if user_id in Config.BLOCKED_USER_IDS:
        await inline_query.answer([], is_personal=True, cache_time=300)
        return

    text = (inline_query.query or "").strip()
    if not text:
        await inline_query.answer([], is_personal=False, cache_time=5)
        return

    songs = await combine_search_results(text)
    cached_results = []

    for item in songs:
        if not item.get('file_id'):
            continue

        try:
            cached = InlineQueryResultCachedAudio(
                id=str(abs(hash(f"cached:{item['unique_key']}:{item['file_id']}"))),
                audio_file_id=item['file_id'],
                title=f"[{item['db_tag'].upper()}] {item['title'] or 'Song'}",
                performer=item['performer'] or "",
                caption=""
            )
            cached_results.append(cached)
        except Exception as e:
            logger.warning("Failed to create InlineQueryResultCachedAudio: %s", e)

    try:
        await inline_query.answer(cached_results[:50], is_personal=False, cache_time=3600)
    except TelegramBadRequest as e:
        logger.error(f"inline.answer failed: {e}")
        await inline_query.answer([], is_personal=False, cache_time=1)