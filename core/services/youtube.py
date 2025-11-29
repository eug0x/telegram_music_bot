import asyncio
import os
import uuid
import glob
import aiohttp
from typing import List, Dict, Any, Optional

from yt_dlp import YoutubeDL

from core.config import (
    logger,
    TEMP_PATH,
    YDL_EXECUTABLE_PATH,
    MAX_SONG_DURATION_SEC,
    MAX_FILE_SIZE_BYTES
)

def cleanup_temp_files(base: str):
    for f in glob.glob(f"{base}.*"):
        try:
            os.remove(f)
        except Exception as e:
            logger.warning(f"Failed to remove temp file {f}: {e}")

async def get_dislikes(video_id: str) -> Optional[int]:
    url = f"https://returnyoutubedislikeapi.com/votes?videoId={video_id}"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=3) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data.get("dislikes")
    except Exception as e:
        logger.warning(f"Failed to fetch dislikes for {video_id}: {e}")
        return None

async def search_multiple(query: str) -> List[Dict[str, Any]]:
    ydl_opts = {
        'quiet': True,
        'skip_download': True,
        'noplaylist': True,
        'extract_flat': True,
        'extractor_args': {'youtube': {'client': 'android'}},
        'executable': YDL_EXECUTABLE_PATH, 
    }
    def search():
        with YoutubeDL(ydl_opts) as ydl:
            result = ydl.extract_info(f"ytsearch10:{query}", download=False) 
            return result.get("entries", [])
    return await asyncio.to_thread(search)


async def download_by_url(url: str):
    info_opts = {
        'format': 'bestaudio/best',
        'noplaylist': True,
        'quiet': True,
        'extractor_args': {'youtube': {'client': 'android'}},
        'no_warnings': True,
        'skip_download': True,
        'executable': YDL_EXECUTABLE_PATH,
    }

    def pre_check_and_download():
        base = None

        with YoutubeDL(info_opts) as ydl:
            try:
                info = ydl.extract_info(url, download=False)
            except Exception:
                raise

            if info.get("duration") and info['duration'] > MAX_SONG_DURATION_SEC:
                raise Exception("LONG_AUDIO")

            filesize_estimate = info.get('filesize') or info.get('filesize_approx')

            if filesize_estimate is not None and filesize_estimate > MAX_FILE_SIZE_BYTES:
                raise Exception("TOO_LARGE_PRECHECK")

        unique_id = uuid.uuid4().hex
        download_opts = {
            'format': 'bestaudio/best',
            'noplaylist': True,
            'quiet': True,
            'outtmpl': os.path.join(TEMP_PATH, f'{unique_id}.%(ext)s'),
            'writethumbnail': True,
            'extractor_args': {'youtube': {'client': 'android'}},
            'no_warnings': True,
            'executable': YDL_EXECUTABLE_PATH,
        }

        with YoutubeDL(download_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            base = os.path.splitext(ydl.prepare_filename(info))[0]
            audio_file = None

            for ext in ['mp3', 'm4a', 'webm', 'opus', 'ogg']:
                candidate = f"{base}.{ext}"
                if os.path.exists(candidate):
                    audio_file = candidate
                    break

            if audio_file and not audio_file.endswith('.mp3'):
                new_mp3 = f"{base}.mp3"
                if os.path.exists(new_mp3):
                    os.remove(new_mp3)
                os.rename(audio_file, new_mp3)
                audio_file = new_mp3

            thumb = None
            for ext in ['jpg','jpeg','png','webp']:
                candidate = f"{base}.{ext}"
                if os.path.exists(candidate):
                    thumb = candidate
                    break

            if audio_file and os.path.getsize(audio_file) > MAX_FILE_SIZE_BYTES:
                cleanup_temp_files(base)
                raise Exception("TOO_LARGE_POSTCHECK")

            return info, audio_file, thumb, base

    try:
        return await asyncio.to_thread(pre_check_and_download)
    except Exception as e:
        if 'base' in locals() and base:
             cleanup_temp_files(base)
        raise e