import aiosqlite
import logging
import os
import re
from rapidfuzz import fuzz
import core.config as Config

def normalize_string(text: str) -> str:
    if not text:
        return ""
    text = text.lower()
    text = re.sub(r'\[.*?\]|\(.*?\)|\{.*?\}', ' ', text)
    noise_words = [r'm/v', r'official', r'video', r'audio', r'hd', r'hq', r'remastered', r'version', r'lyrics']
    for word in noise_words:
        text = re.sub(r'\b' + word + r'\b', ' ', text)
    text = re.sub(r'[^\w\s]', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text

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

async def init_db(db_name: str):
    async with aiosqlite.connect(db_name) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS songs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_id TEXT UNIQUE,
                file_unique_id TEXT UNIQUE,
                title TEXT,
                performer TEXT,
                normalized_title TEXT,
                is_cached INTEGER DEFAULT 1
            )
        """)
        try:
            await db.execute("SELECT normalized_title FROM songs LIMIT 1")
        except aiosqlite.OperationalError:
            logging.warning(f"Migration ({db_name}): Adding column 'normalized_title'.")
            await db.execute("ALTER TABLE songs ADD COLUMN normalized_title TEXT")
        
        try:
            await db.execute("SELECT is_cached FROM songs LIMIT 1")
        except aiosqlite.OperationalError:
            logging.warning(f"Migration ({db_name}): Adding column 'is_cached'.")
            await db.execute("ALTER TABLE songs ADD COLUMN is_cached INTEGER DEFAULT 1")
            
        logging.info(f"Database {db_name} is up to date.")
        await db.commit()

async def save_audio_to_db(audio, db_name: str, title_threshold: int):
    title = audio.title or "Unknown Title"
    performer = audio.performer or "Unknown Artist"
    
    normalized_title = normalize_string(title)
    
    is_version_flag = is_different_version(title)

    async with aiosqlite.connect(db_name) as db:
        try:
            cursor = await db.execute(
                "SELECT id FROM songs WHERE file_unique_id = ?",
                (audio.file_unique_id,)
            )
            if await cursor.fetchone():
                return "duplicate_exact"
            
            if not is_version_flag:
                artist_search_query = f"%{normalize_string(performer)}%"
                cursor = await db.execute(
                    "SELECT title, normalized_title FROM songs WHERE performer LIKE ? LIMIT 200",
                    (artist_search_query,)
                )
                existing_songs = await cursor.fetchall()
                
                for existing_title, existing_norm_title in existing_songs:
                    title_score = fuzz.token_set_ratio(normalized_title, existing_norm_title)
                    
                    if title_score >= title_threshold:
                        logging.warning(
                            f"Fuzzy duplicate found in {db_name}: '{title}' ({title_score}%) "
                            f"is similar to '{existing_title}'."
                        )
                        return "duplicate_fuzzy"
            
            await db.execute(
                "INSERT INTO songs (file_id, file_unique_id, title, performer, normalized_title, is_cached) VALUES (?, ?, ?, ?, ?, 1)",
                (audio.file_id, audio.file_unique_id, title, performer, normalized_title)
            )
            await db.commit()
            return True
        except aiosqlite.IntegrityError:
            logging.warning(f"Attempt to add duplicate in {db_name}: {title}. Ignored.")
            return "duplicate_exact"
        except Exception as e:
            logging.error(f"Critical DB error ({db_name}) during save: {e}")
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
            try:
                with open(Config.DELETED_SONGS_LOG_PATH, 'a', encoding='utf-8') as f:
                    f.write(log_message)
            except Exception as e:
                logging.error(f"Failed to write to deleted songs log: {e}")

        await db.execute("DELETE FROM songs_fts WHERE rowid = ?", (song_id,))
        await db.execute("DELETE FROM songs WHERE id = ?", (song_id,))
        await db.commit()
        logging.info(f"Removed bad key ID:{song_id} from {db_name}")