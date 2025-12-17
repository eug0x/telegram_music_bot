import asyncio
import logging
import os
from aiogram import Router, Bot
from aiogram.types import InlineQuery, InlineQueryResultCachedAudio
from aiogram.exceptions import TelegramBadRequest

from ..services.inline_search.fts5_search import search_fts
from ..services.inline_search.rapidfuzz_search import search_rapidfuzz

import core.config as Config

CHANNEL_ID = Config.CHANNEL_ID

router = Router()
logger = logging.getLogger(__name__)

async def combine_search_results(query: str):
    tasks = [
        search_fts(query, Config.CHANNEL_DB_PATH, limit=50),
        search_fts(query, Config.CHAT_DB_PATH, limit=50),
        search_rapidfuzz(query, Config.CHANNEL_DB_PATH, limit=50),
        search_rapidfuzz(query, Config.CHAT_DB_PATH, limit=50),
    ]
    
    all_results = await asyncio.gather(*tasks)
    
    unique_songs = {}
    final_list = []

    for results in all_results:
        for song in results:
            song_id, file_id, title, performer, is_cached, db_tag = song
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
                    'db_name': Config.CHANNEL_DB_PATH if db_tag == os.path.basename(Config.CHANNEL_DB_PATH).split('.')[0] else Config.CHAT_DB_PATH
                }
                unique_songs[unique_key] = song_data
                final_list.append(song_data)
    
    final_list.sort(key=lambda x: x['is_cached'], reverse=True)
    
    return final_list[:50]

@router.inline_query()
async def inline_music_search(inline_query: InlineQuery, bot: Bot):
    if inline_query.from_user.id in Config.BLOCKED_USER_IDS:
        await inline_query.answer([], is_personal=True, cache_time=300)
        return

    text = (inline_query.query or "").strip()
    if not text:
        await inline_query.answer([], is_personal=False, cache_time=5)
        return

    songs = await combine_search_results(text)

    cached_results = []
    
    for item in songs:
        song_id = item['song_id']
        file_id = item['file_id']
        title = item['title']
        performer = item['performer']
        is_cached = item['is_cached']
        db_tag = item['db_tag']
        unique_key = item['unique_key']
        
        title_display = title or "Song"
        performer_display = performer or ""

        if is_cached and file_id:
            try:
                cached = InlineQueryResultCachedAudio(
                    id=str(abs(hash(f"cached:{unique_key}:{file_id}"))),
                    audio_file_id=file_id,
                    title=f"[{db_tag.upper().replace('MUSIC_','').replace('_BASE','')}] {title_display}",
                    performer=performer_display,
                    caption=""
                )
                cached_results.append(cached)
            except Exception as e:
                logger.warning(
                    "Error creating InlineQueryResultCachedAudio for ID %s: %s. Track skipped.",
                    song_id, e
                )
                pass

    results = cached_results

    try:
        await inline_query.answer(results[:50], is_personal=False, cache_time=3600)
    except TelegramBadRequest as e:
        logger.error(f"inline.answer failed completely: {e}.")
        try:
            await inline_query.answer([], is_personal=False, cache_time=1)
        except Exception:
            logger.exception("Failed to send fallback empty inline answer.")