import aiosqlite
from rapidfuzz import process, fuzz
from typing import List, Tuple
import os

async def search_rapidfuzz(query: str, db_name: str, limit: int = 10, cutoff: int = 65) -> List[Tuple[int,str,str,str,int,str]]:

    q = (query or "").strip().lower()
    if not q:
        return []
    
    async with aiosqlite.connect(db_name) as db:
        cursor = await db.execute("SELECT id, file_id, title, performer, is_cached FROM songs")
        rows = await cursor.fetchall()

    if not rows:
        return []

    candidates = []
    for _id, file_id, title, performer, is_cached in rows:
        t = (title or "").lower()
        p = (performer or "").lower()
        combined = f"{p} - {t}".strip()
        candidates.append((combined, _id, file_id, title, performer, is_cached))

    dataset = [c[0] for c in candidates]
    db_tag = os.path.basename(db_name).split('.')[0]

    matches = process.extract(
        q,
        dataset,
        scorer=fuzz.WRatio,
        limit=limit * 2,
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
        results.append((_id, file_id, title, performer, is_cached, db_tag))
        
        if len(results) >= limit:
            break
            
    results.sort(key=lambda x: x[4], reverse=True)
    return results