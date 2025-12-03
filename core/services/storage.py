import os
import json
import time
import sqlite3
from typing import Dict, Any, Optional, Tuple

from core import strings
from core.config import (
    logger, 
    DB_PATH, 
    INFO_EXPIRATION_HOURS, 
    DATA_PATH
)

song_data_storage: Dict[str, Any] = {}
user_last_request_time: Dict[int, float] = {}

def get_db_connection() -> sqlite3.Connection:
    os.makedirs(DATA_PATH, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    return conn

def initialize_db():
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
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
        conn.commit()
    except Exception as e:
        logger.critical(f"Error initializing SQLite database: {e}")
        raise
    finally:
        conn.close()

def format_number_dot(num: Optional[int]) -> str:
    if not isinstance(num, int):
        return strings.UNKNOWN_VALUE
    return f"{num:,}".replace(",", ".")

def set_song_data(cache_id: str, message_id: int, data: Dict[str, Any]):
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        
        full_info = data.copy()
        
        other_data = {
            k: v for k, v in full_info.items() if k not in (
                "title", "url", "file", "thumb", "requester", "duration", "timestamp"
            )
        }
        
        cursor.execute("""
            INSERT OR REPLACE INTO songs_cache (
                cache_id, message_id, title, url, file_path, thumb_path, 
                requester_id, duration, cached_at, other_data
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            cache_id,
            message_id,
            full_info.get("title"),
            full_info.get("url"),
            full_info.get("file"),
            full_info.get("thumb"),
            full_info.get("requester"),
            full_info.get("duration"),
            time.time(), 
            json.dumps(other_data)
        ))
        conn.commit()
    except Exception as e:
        logger.error(f"Error saving song data to DB for ID {cache_id}: {e}")
    finally:
        conn.close()

def get_song_data(cache_id: str) -> Optional[Dict[str, Any]]:
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM songs_cache WHERE cache_id = ?", (cache_id,))
        row = cursor.fetchone()
        
        if row:
            cols = [
                "cache_id", "message_id", "title", "url", "file", "thumb", 
                "requester", "duration", "timestamp", "other_data"
            ]
            
            result: Dict[str, Any] = dict(zip(cols, row))
            
            
            metadata = {
                "title": result.get("title"),
                "artist": json.loads(result["other_data"]).get("artist"),
                "thumb": result.get("thumb"),
                "file": result.get("file"),
                "query": json.loads(result["other_data"]).get("query"),
                "url": result.get("url"),
                "requester": result.get("requester"),
                "duration": result.get("duration"),
                "upload_date": json.loads(result["other_data"]).get("upload_date"),
                "view_count": json.loads(result["other_data"]).get("view_count"),
                "like_count": json.loads(result["other_data"]).get("like_count"),
                "dislike_count": json.loads(result["other_data"]).get("dislike_count"),
                "timestamp": result.get("timestamp")
            }
            
            return {
                f"info_{cache_id}": metadata,
                f"msg_{cache_id}": result.get("message_id")
            }
        
        return None
    except Exception as e:
        logger.error(f"Error retrieving song data from DB for ID {cache_id}: {e}")
        return None
    finally:
        conn.close()

def cleanup_expired_data():
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        
        expiration_time = time.time() - (INFO_EXPIRATION_HOURS * 3600)
        
        cursor.execute("DELETE FROM songs_cache WHERE cached_at < ?", (expiration_time,))
        deleted_count = cursor.rowcount
        conn.commit()
        
        if deleted_count > 0:
            logger.info(f"Cleaned up {deleted_count} expired entries from song data cache.")
            
    except Exception as e:
        logger.error(f"Error during database cleanup: {e}")
    finally:
        conn.close()

initialize_db()
