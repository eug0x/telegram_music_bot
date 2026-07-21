from rapidfuzz import process, fuzz
from typing import List, Tuple

async def search_rapidfuzz(
    query: str, 
    fts_results: List[Tuple], 
    limit: int = 100, 
    cutoff: int = 35
) -> List[Tuple]:
    
    q = (query or "").strip().lower()
    if not q or not fts_results:
        return []

    candidates = []
    for row in fts_results:
        song_id, file_id, title, performer, is_cached, db_tag = row[:6]
        t = (title or "").lower()
        p = (performer or "").lower()
        combined = f"{p} - {t}".strip("- ")
        
        candidates.append((combined, row))

    if not candidates:
        return []

    dataset = [c[0] for c in candidates]

    matches = process.extract(
        q,
        dataset,
        scorer=fuzz.WRatio,         
        limit=limit,
        score_cutoff=cutoff
    )

    results = []
    for match_text, score, idx in matches:
        original_row = candidates[idx][1]
        results.append((*original_row, score)) 

    return results