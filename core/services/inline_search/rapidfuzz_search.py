from rapidfuzz import fuzz
from typing import List, Tuple

def _combined_score(query: str, candidate: str) -> float:
    if not query or not candidate:
        return 0.0
    scores = (
        fuzz.partial_ratio(query, candidate),
        fuzz.token_set_ratio(query, candidate),
        fuzz.WRatio(query, candidate),
    )
    return max(scores)


async def search_rapidfuzz(
    query: str,
    fts_results: List[Tuple],
    limit: int = 100,
    cutoff: int = 35
) -> List[Tuple]:

    q = (query or "").strip().lower()
    if not q or not fts_results:
        return []

    scored = []
    for row in fts_results:
        song_id, file_id, title, performer, is_cached, db_tag = row[:6]
        t = (title or "").lower()
        p = (performer or "").lower()
        combined_text = f"{p} - {t}".strip("- ")

        score = _combined_score(q, combined_text)

        if q in combined_text:
            score = max(score, 90.0)

        if score >= cutoff:
            scored.append((score, row))

    if not scored:
        return []

    scored.sort(key=lambda x: x[0], reverse=True)
    scored = scored[:limit]

    results = []
    for score, row in scored:
        results.append((*row, score))

    return results
