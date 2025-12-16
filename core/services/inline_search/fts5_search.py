import os
import aiosqlite
import re
import logging
from sqlite3 import OperationalError
from typing import List, Tuple

logger = logging.getLogger(__name__)

def _sanitize_for_fts(q: str) -> str:
    if not q:
        return ""
    s = re.sub(r'[^\w\s]', ' ', q).strip()
    return re.sub(r'\s+', ' ', s)

async def ensure_fts_populated(db: aiosqlite.Connection):
    await db.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS songs_fts 
        USING fts5(title, performer, tokenize='trigram')
    """)
    
    cur = await db.execute("SELECT count(*) FROM songs_fts")
    row = await cur.fetchone()
    cnt = (row[0] if row else 0) or 0
    
    if cnt == 0:
        await db.execute("DELETE FROM songs_fts")
        await db.execute("""
            INSERT INTO songs_fts(rowid, title, performer)
            SELECT id, title, performer FROM songs 
            WHERE title IS NOT NULL OR performer IS NOT NULL
        """)
        await db.commit()

async def search_fts(query: str, db_name: str, limit: int = 50) -> List[Tuple[int,str,str,str,int,str]]:
    q = _sanitize_for_fts(query)
    if not q or len(q) < 2: # Не ищем по 1 букве
        return []

    async with aiosqlite.connect(db_name) as db:
        try:
            await ensure_fts_populated(db)
            db_tag = os.path.basename(db_name).split('.')[0]

            sql = """
                SELECT s.id, s.file_id, s.title, s.performer, s.is_cached
                FROM songs s
                JOIN songs_fts ON songs_fts.rowid = s.id
                WHERE songs_fts MATCH ?
                ORDER BY songs_fts.rank, s.is_cached DESC
                LIMIT ?
            """
            
            cursor = await db.execute(sql, (q, limit))
            rows = await cursor.fetchall()
            
            results = [row + (db_tag,) for row in rows]
            return results
            
        except OperationalError as e:
            if "no such table: songs_fts" in str(e):
                await ensure_fts_populated(db)
                return await search_fts(query, db_name, limit)
            logger.exception(f"FTS Error: {e}")
            return []
        except Exception as e:
            logger.exception(f"Search failed: {e}")
            return []