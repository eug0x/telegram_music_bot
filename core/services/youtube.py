# core\services\youtube.py

import asyncio
import os
import uuid
import glob
import aiohttp
from typing import List, Dict, Any, Optional
from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError

from core.config import (
    logger,
    TEMP_PATH,
    MAX_SONG_DURATION_SEC,
    MAX_FILE_SIZE_BYTES
)

_GLOBAL_HTTP_SESSION = None

def get_http_session() -> aiohttp.ClientSession:
    global _GLOBAL_HTTP_SESSION
    if _GLOBAL_HTTP_SESSION is None:
        _GLOBAL_HTTP_SESSION = aiohttp.ClientSession()
    return _GLOBAL_HTTP_SESSION

def cleanup_temp_files(base: str):
    for f in glob.glob(f"{base}.*"):
        try:
            os.remove(f)
        except Exception as e:
            logger.warning(f"Failed to remove temp file {f}: {e}")

async def close_global_session():
    global _GLOBAL_HTTP_SESSION
    if _GLOBAL_HTTP_SESSION:
        await _GLOBAL_HTTP_SESSION.close()
        _GLOBAL_HTTP_SESSION = None

async def get_dislikes(video_id: str) -> Optional[int]:
    url = f"https://returnyoutubedislikeapi.com/votes?videoId={video_id}"
    try:
        session = get_http_session()
        
        async with session.get(url, timeout=3) as resp:
            
            if resp.status == 200:
                data = await resp.json()
                
                if data and isinstance(data, dict):
                    return data.get("dislikes")
                else:
                    logger.warning(f"API returned non-dictionary data or None for {video_id}.")
                    return None
            else:
                logger.warning(f"API status error for {video_id}: {resp.status}")
                return None
                
    except AttributeError as e:
        if "get" in str(e) and _GLOBAL_HTTP_SESSION is None:
            logger.error("HTTP Session not initialized! GLOBAL_HTTP_SESSION is None.")
            return None
        raise
        
    except aiohttp.ClientConnectorError as e:
        logger.warning(f"Failed to fetch dislikes for {video_id} (Connection Error): {e}")
    except asyncio.TimeoutError:
        logger.warning(f"Failed to fetch dislikes for {video_id} (Timeout)")
    except Exception as e:
        logger.warning(f"Unexpected error in get_dislikes for {video_id}: {e}")
    return None

async def search_multiple(query: str) -> List[Dict[str, Any]]:
    ydl_opts = {
        'quiet': True,
        'skip_download': True,
        'noplaylist': True,
        'extract_flat': True,
        'extractor_args': {'youtube': {'client': 'android'}},
        'encoding': 'utf-8',
        'postprocessors': [],
    }
    def search():
        with YoutubeDL(ydl_opts) as ydl: # type: ignore
            try:
                result = ydl.extract_info(f"ytsearch10:{query}", download=False) 
                return result.get("entries", [])
            except DownloadError:
                logger.error(f"yt-dlp search failed for query: {query}")
                return []
            except Exception as e:
                logger.error(f"Unexpected error during search: {e}")
                raise
    return await asyncio.to_thread(search)


async def download_by_url(url: str):
    info_opts = {
        'format': 'bestaudio/best',
        'noplaylist': True,
        'quiet': True,
        'extractor_args': {'youtube': {'client': 'android'}},
        'no_warnings': True,
        'skip_download': True,
        'encoding': 'utf-8',
        'postprocessors': [],
    }

    base = None

    def pre_check_and_download():

        with YoutubeDL(info_opts) as ydl: # type: ignore
            try:
                info = ydl.extract_info(url, download=False)
            except DownloadError as e:
                logger.error(f"yt-dlp pre-check failed for {url}: {e}")
                raise Exception("YT_DOWNLOAD_FAILED")
            except Exception:
                raise

            duration = info.get("duration")
            if duration is not None and duration > MAX_SONG_DURATION_SEC:
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
            'encoding': 'utf-8',
            'postprocessors': [
                {'key': 'FFmpegMetadata'}, 
            ]
        }

        with YoutubeDL(download_opts) as ydl: # type: ignore
            try:
                info = ydl.extract_info(url, download=True)
                base = os.path.splitext(ydl.prepare_filename(info))[0]
            except DownloadError as e:
                logger.error(f"yt-dlp download failed for {url}: {e}")
                raise Exception("YT_DOWNLOAD_FAILED")
            except Exception:
                raise

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

            temp_files_to_keep = [audio_file, thumb]
            for f in glob.glob(f"{base}.*"):
                if f not in temp_files_to_keep:
                    try:
                        os.remove(f)
                    except Exception as e:
                        logger.warning(f"Failed to remove leftover temp file {f}: {e}")
                        
            return info, audio_file, thumb, base

    try:
        return await asyncio.to_thread(pre_check_and_download)
    except Exception as e:
        logger.warning(f"Error during download for {url}: {e}. Attempting cleanup if base is known.")
        raise e