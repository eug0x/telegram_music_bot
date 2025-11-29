import os
import json
import time
from typing import Dict, Any, Optional

from core import strings
from core.config import (
    logger, 
    SONGS_INFO_PATH, 
    INFO_EXPIRATION_HOURS, 
    DATA_PATH
)

song_data_storage: Dict[str, Any] = {}
user_last_request_time: Dict[int, float] = {}

def format_number_dot(num: Optional[int]) -> str:
    if not isinstance(num, int):
        return strings.UNKNOWN_VALUE
    return f"{num:,}".replace(",", ".")

def load_song_data() -> Dict[str, Any]:
    if os.path.exists(SONGS_INFO_PATH):
        with open(SONGS_INFO_PATH, "r", encoding="utf-8") as f:
            try:
                return json.load(f)
            except Exception as e:
                logger.error(f"Error loading {SONGS_INFO_PATH}: {e}")
                return {}
    return {}

def save_song_data(data: Dict[str, Any]):
    current_time = time.time()
    expiration_time_sec = INFO_EXPIRATION_HOURS * 3600
    keys_to_delete = []

    for key, value in data.items():
        if key.startswith("info_") and value.get("timestamp"):
            if current_time - value["timestamp"] > expiration_time_sec:
                keys_to_delete.append(key)
                msg_key = key.replace("info_", "msg_")
                if msg_key in data:
                    keys_to_delete.append(msg_key)

    for key in keys_to_delete:
        data.pop(key, None)

    if keys_to_delete:
        logger.info(f"Cleaned up {len(keys_to_delete)} expired keys from song data cache.")

    os.makedirs(DATA_PATH, exist_ok=True)
    with open(SONGS_INFO_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

song_data_storage.update(load_song_data())