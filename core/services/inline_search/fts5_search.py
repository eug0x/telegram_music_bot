import os
import logging
import re
from typing import List, Tuple

from ..storage import get_db

logger = logging.getLogger(__name__)


def _normalize_for_fts(text: str) -> str:
    if not text:
        return ""
    text = text.lower()
    text = re.sub(r'\[.*?\]|\(.*?\)|\{.*?\}', ' ', text)
    text = re.sub(r'[^\w\s]', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text


async def search_fts(query: str, db_name: str, limit: int = 500) -> List[Tuple]:

    q_clean = _normalize_for_fts(query)
    if not q_clean or len(q_clean) < 2:
        return []

    db_tag = os.path.basename(db_name).split('.')[0]

    words = q_clean.split()
    fts_query = " ".join(
        f'"{word}*"' if len(word) >= 5 else f'"{word}"'
        for word in words
    )

    sql = """
        SELECT 
            s.id, 
            s.file_id, 
            s.title, 
            s.performer, 
            s.is_cached
        FROM songs_fts fts
        JOIN songs s ON s.id = fts.rowid
        WHERE songs_fts MATCH ?
        ORDER BY s.is_cached DESC, rank
        LIMIT ?
    """

    async with get_db(db_name) as db:
        try:
            cursor = await db.execute(sql, (fts_query, limit))
            rows = await cursor.fetchall()
            result = [(*row, db_tag) for row in rows]
            
            if len(result) > 0:
                logger.debug(f"FTS5 {db_tag}: {len(result)} candidates for '{q_clean}'")
            return result

        except Exception as e:
            logger.exception(f"FTS5 search failed for {db_tag} (query: {q_clean}): {e}")
            return []