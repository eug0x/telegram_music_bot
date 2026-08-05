import aiosqlite
import os
import asyncio
from rapidfuzz import fuzz
from core.config import logger
import core.config as Config
from core.utils.text import normalize_text, escape_like_pattern


def is_different_version(title: str) -> bool:
    title = title.lower()
    version_keywords = [
        'remix', 'mix', 'edit', 'vip',
        'live', 'acoustic', 'instrumental',
        'slowed', 'sped up', 'flip', 'cover',
        'intro', 'outro'
    ]
    for keyword in version_keywords:
        if keyword in title:
            return True
    return False


def _write_deleted_log_sync(log_message: str) -> None:
    try:
        with open(Config.DELETED_SONGS_LOG_PATH, 'a', encoding='utf-8') as f:
            f.write(log_message)
    except Exception as e:
        logger.error(f"Failed to write to deleted songs log: {e}")


async def init_db(db_name: str):
    async with aiosqlite.connect(db_name) as db:
        await db.execute("PRAGMA journal_mode=WAL")

        await db.execute("""
            CREATE TABLE IF NOT EXISTS songs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_id TEXT UNIQUE,
                file_unique_id TEXT UNIQUE,
                title TEXT,
                performer TEXT,
                normalized_title TEXT,
                normalized_performer TEXT,
                is_cached INTEGER DEFAULT 1
            )
        """)

        await db.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS songs_fts USING fts5(
                title,
                performer,
                normalized_title,
                normalized_performer,
                tokenize='unicode61'
            )
        """)

        migration_needed = False

        try:
            await db.execute("SELECT normalized_title FROM songs LIMIT 1")
        except aiosqlite.OperationalError:
            logger.warning(f"Migration ({db_name}): Adding column 'normalized_title'.")
            await db.execute("ALTER TABLE songs ADD COLUMN normalized_title TEXT")
            migration_needed = True

        try:
            await db.execute("SELECT normalized_performer FROM songs LIMIT 1")
        except aiosqlite.OperationalError:
            logger.warning(f"Migration ({db_name}): Adding column 'normalized_performer'.")
            await db.execute("ALTER TABLE songs ADD COLUMN normalized_performer TEXT")
            migration_needed = True

        try:
            await db.execute("SELECT is_cached FROM songs LIMIT 1")
        except aiosqlite.OperationalError:
            logger.warning(f"Migration ({db_name}): Adding column 'is_cached'.")
            await db.execute("ALTER TABLE songs ADD COLUMN is_cached INTEGER DEFAULT 1")

        fts_update_needed = migration_needed
        try:
            await db.execute("SELECT normalized_performer FROM songs_fts LIMIT 1")
        except aiosqlite.OperationalError:
            logger.warning(f"Migration ({db_name}): FTS5 index is outdated. Triggering rebuild...")
            fts_update_needed = True

        if fts_update_needed:
            await db.execute("DROP TABLE IF EXISTS songs_fts")
            await db.execute("""
                CREATE VIRTUAL TABLE songs_fts USING fts5(
                    title,
                    performer,
                    normalized_title,
                    normalized_performer,
                    tokenize='unicode61'
                )
            """)

            cursor = await db.execute("SELECT id, title, performer, normalized_title, normalized_performer FROM songs")
            rows = await cursor.fetchall()

            for row_id, title, performer, norm_title, norm_perf in rows:
                safe_title = title or "Unknown Title"
                safe_performer = performer or "Unknown Artist"

                n_title = norm_title or normalize_text(safe_title, strip_noise_words=True)
                n_perf = norm_perf or normalize_text(safe_performer, strip_noise_words=True)

                if not norm_title or not norm_perf:
                    await db.execute(
                        "UPDATE songs SET normalized_title = ?, normalized_performer = ? WHERE id = ?",
                        (n_title, n_perf, row_id)
                    )

                await db.execute(
                    """INSERT INTO songs_fts(rowid, title, performer, normalized_title, normalized_performer)
                       VALUES (?, ?, ?, ?, ?)""",
                    (row_id, safe_title, safe_performer, n_title, n_perf)
                )

            logger.info(f"Migration and FTS5 rebuild completed successfully for {db_name}!")

        await db.commit()
        logger.info(f"Database {db_name} is active and ready.")


async def save_audio_to_db(audio, db_name: str, title_threshold: int):
    title = audio.title or "Unknown Title"
    performer = audio.performer or "Unknown Artist"
    normalized_title = normalize_text(title, strip_noise_words=True)
    normalized_performer = normalize_text(performer, strip_noise_words=True)

    is_version_flag = is_different_version(title)

    async with aiosqlite.connect(db_name) as db:
        await db.execute("PRAGMA journal_mode=WAL")
        try:
            cursor = await db.execute(
                "SELECT id FROM songs WHERE file_unique_id = ?",
                (audio.file_unique_id,)
            )
            if await cursor.fetchone():
                return "duplicate_exact"

            if not is_version_flag:
                escaped_performer = escape_like_pattern(normalized_performer)
                artist_search_query = f"%{escaped_performer}%"
                cursor = await db.execute(
                    "SELECT title, normalized_title FROM songs WHERE performer LIKE ? ESCAPE '\\' LIMIT 200",
                    (artist_search_query,)
                )
                existing_songs = await cursor.fetchall()

                for existing_title, existing_norm_title in existing_songs:
                    title_score = fuzz.token_set_ratio(normalized_title, existing_norm_title or "")
                    if title_score >= title_threshold:
                        return "duplicate_fuzzy"

            cursor = await db.execute(
                """INSERT INTO songs (file_id, file_unique_id, title, performer, normalized_title, normalized_performer, is_cached)
                   VALUES (?, ?, ?, ?, ?, ?, 1)""",
                (audio.file_id, audio.file_unique_id, title, performer, normalized_title, normalized_performer)
            )
            last_id = cursor.lastrowid

            await db.execute(
                """INSERT INTO songs_fts(rowid, title, performer, normalized_title, normalized_performer)
                   VALUES (?, ?, ?, ?, ?)""",
                (last_id, title, performer, normalized_title, normalized_performer)
            )

            await db.commit()
            return True

        except aiosqlite.IntegrityError:
            return "duplicate_exact"
        except Exception as e:
            logger.error(f"Critical DB error ({db_name}) during save: {e}")
            return False


async def get_song_by_id(song_id: int, db_name: str):
    async with aiosqlite.connect(db_name) as db:
        cursor = await db.execute(
            "SELECT id, file_id, title, performer, is_cached FROM songs WHERE id = ?",
            (song_id,)
        )
        return await cursor.fetchone()


async def set_song_cached_flag(song_id: int, is_cached: int, db_name: str):
    async with aiosqlite.connect(db_name) as db:
        await db.execute(
            "UPDATE songs SET is_cached = ? WHERE id = ?",
            (is_cached, song_id)
        )
        await db.commit()


async def delete_song_by_id(song_id: int, db_name: str):
    async with aiosqlite.connect(db_name) as db:
        cursor = await db.execute("SELECT title, performer FROM songs WHERE id = ?", (song_id,))
        song_info = await cursor.fetchone()

        if db_name == Config.CHANNEL_DB_PATH and song_info:
            log_message = f"[{os.path.basename(db_name)}] Deleted: {song_info[1]} - {song_info[0]} (ID:{song_id})\n"
            await asyncio.to_thread(_write_deleted_log_sync, log_message)

        await db.execute("DELETE FROM songs_fts WHERE rowid = ?", (song_id,))
        await db.execute("DELETE FROM songs WHERE id = ?", (song_id,))
        await db.commit()
        logger.info(f"Removed bad key ID:{song_id} from {db_name}")
