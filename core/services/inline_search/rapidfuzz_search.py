import aiosqlite
from rapidfuzz import process, fuzz
from typing import List, Tuple
import os

async def search_rapidfuzz(query: str, db_name: str, limit: int = 10, cutoff: int = 65) -> List[Tuple[int,str,str,str,int,str]]:
    """
    Нечеткий поиск с Rapidfuzz. Использует cutoff=40 для максимального охвата,
    как в старой (рабочей) версии.
    Возвращает: (id, file_id, title, performer, is_cached, db_tag)
    """
    q = (query or "").strip().lower()
    if not q:
        return []

    async with aiosqlite.connect(db_name) as db:
        # ВАЖНО: Используем 'is_cached' (как в новой базе) вместо 'is_cached_audio' (как в старой базе).
        cursor = await db.execute("SELECT id, file_id, title, performer, is_cached FROM songs")
        rows = await cursor.fetchall()

    if not rows:
        return []

    candidates = []
    # candidates: [ (combined_string, id, file_id, title, performer, is_cached), ... ]
    for _id, file_id, title, performer, is_cached in rows:
        t = (title or "").lower()
        p = (performer or "").lower()
        combined = f"{p} - {t}".strip()
        candidates.append((combined, _id, file_id, title, performer, is_cached))

    dataset = [c[0] for c in candidates]
    db_tag = os.path.basename(db_name).split('.')[0]

    # cutoff=40 для максимальной "нечеткости", как в рабочем коде.
    matches = process.extract(
        q,
        dataset,
        scorer=fuzz.WRatio,
        limit=limit * 2, # Ищем в два раза больше, чтобы гарантировать нужное количество после фильтрации
        score_cutoff=cutoff
    )

    results = []
    used = set()
    
    for match_text, score, idx in matches:
        try:
            _, _id, file_id, title, performer, is_cached = candidates[idx]
        except Exception:
            continue
            
        key = (_id, file_id)
        if key in used:
            continue
            
        used.add(key)
        # Добавляем db_tag в конец
        results.append((_id, file_id, title, performer, is_cached, db_tag))
        
        if len(results) >= limit:
            break
            
    # Сортируем, чтобы кэшированные треки шли первыми (индекс 4)
    results.sort(key=lambda x: x[4], reverse=True)
    return results