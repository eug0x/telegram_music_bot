import os
import json
import time
import asyncio
import aiosqlite
from typing import Dict, Any, Optional
from cachetools import TTLCache
from contextlib import asynccontextmanager

from core.config import (
    logger,
    DB_PATH,
    INFO_EXPIRATION_HOURS,
    DATA_PATH
)

song_data_storage: TTLCache = TTLCache(maxsize=5000, ttl=3600)
user_last_request_time: TTLCache = TTLCache(maxsize=1000, ttl=60)

@asynccontextmanager
async def get_db(db_path: str):
    db = await aiosqlite.connect(db_path)
    await db.execute("PRAGMA journal_mode=WAL")
    try:
        yield db
    finally:
        await db.close()


async def initialize_db():
    await asyncio.to_thread(os.makedirs, DATA_PATH, exist_ok=True)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS songs_cache (
                cache_id TEXT PRIMARY KEY,
                message_id INTEGER,
                title TEXT,
                url TEXT,
                file_path TEXT,
                thumb_path TEXT,
                requester_id INTEGER,
                duration INTEGER,
                cached_at REAL,
                other_data TEXT
            )
        """)
        await db.execute("PRAGMA journal_mode=WAL")
        await db.commit()


async def set_song_data(cache_id: str, message_id: int, data: Dict[str, Any]):
    other_data = {k: v for k, v in data.items() if k not in (
        "title", "url", "file", "thumb", "requester", "duration", "timestamp"
    )}

    async with get_db(DB_PATH) as db:
        await db.execute("""
            INSERT OR REPLACE INTO songs_cache (
                cache_id, message_id, title, url, file_path, thumb_path,
                requester_id, duration, cached_at, other_data
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            cache_id, message_id, data.get("title"), data.get("url"),
            data.get("file"), data.get("thumb"), data.get("requester"),
            data.get("duration"), time.time(), json.dumps(other_data)
        ))
        await db.commit()

    song_data_storage[cache_id] = data


async def get_song_data(cache_id: str) -> Optional[Dict[str, Any]]:
    if cache_id in song_data_storage:
        data = song_data_storage[cache_id]
        return {f"info_{cache_id}": data, f"msg_{cache_id}": 0}

    async with get_db(DB_PATH) as db:
        async with db.execute("SELECT * FROM songs_cache WHERE cache_id = ?", (cache_id,)) as cursor:
            row = await cursor.fetchone()
            if row:
                other = json.loads(row[9])
                metadata = {
                    "title": row[2],
                    "artist": other.get("artist"),
                    "thumb": row[5],
                    "file": row[4],
                    "query": other.get("query"),
                    "url": row[3],
                    "requester": row[6],
                    "duration": row[7],
                    "upload_date": other.get("upload_date"),
                    "view_count": other.get("view_count"),
                    "like_count": other.get("like_count"),
                    "dislike_count": other.get("dislike_count"),
                    "timestamp": row[8]
                }
                song_data_storage[cache_id] = metadata
                return {f"info_{cache_id}": metadata, f"msg_{cache_id}": row[1]}
    return None


async def cleanup_expired_data():
    async with get_db(DB_PATH) as db:
        expiration_time = time.time() - (INFO_EXPIRATION_HOURS * 3600)
        cursor = await db.execute("DELETE FROM songs_cache WHERE cached_at < ?", (expiration_time,))
        await db.commit()
        if cursor.rowcount > 0:
            logger.info(f"Cleaned up {cursor.rowcount} expired entries.")


def format_number_dot(number: int) -> str:
    return f"{number:,}".replace(",", ".")
