import os
import logging
from typing import List, Tuple

from ..storage import get_db
from core.utils.text import normalize_text

logger = logging.getLogger(__name__)


def _build_fts_match_query(words: List[str]) -> str:

    terms = []
    for word in words:
        safe_word = word.replace('"', '')
        if not safe_word:
            continue
        terms.append(f'{safe_word}*')
    return " OR ".join(terms)


async def search_fts(query: str, db_name: str, limit: int = 500) -> List[Tuple]:

    q_clean = normalize_text(query, strip_noise_words=False)
    if not q_clean or len(q_clean) < 2:
        return []

    db_tag = os.path.basename(db_name).split('.')[0]

    words = q_clean.split()
    fts_query = _build_fts_match_query(words)
    if not fts_query:
        return []

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
