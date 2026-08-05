# core/services/youtube.py

import asyncio
import os
import uuid
import glob
import aiohttp
from aiohttp import ClientTimeout
from typing import List, Dict, Any, Optional, Tuple
from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError, match_filter_func

from core.config import (
    logger,
    TEMP_PATH,
    MAX_SONG_DURATION_SEC,
    DEFAULT_HTTP_HEADERS,
    MAX_FILE_SIZE_BYTES
)

_GLOBAL_HTTP_SESSION: Optional[aiohttp.ClientSession] = None

SEARCH_TIMEOUT_SEC = 20.0
DOWNLOAD_TIMEOUT_SEC = 120.0
DISLIKES_API_TIMEOUT_SEC = 3.0

AUDIO_EXTENSIONS = ("mp3", "m4a", "webm", "opus", "ogg")
THUMBNAIL_EXTENSIONS = ("jpg", "jpeg", "png", "webp")


class YTDLPLogger:
    def debug(self, msg):
        logger.debug(msg)

    def warning(self, msg):
        logger.warning(f"[yt-dlp WARNING] {msg}")

    def error(self, msg):
        logger.error(f"[yt-dlp ERROR] {msg}")

    def info(self, msg):
        logger.info(f"[yt-dlp INFO] {msg}")


# HTTP-session

def get_http_session() -> aiohttp.ClientSession:
    global _GLOBAL_HTTP_SESSION
    if _GLOBAL_HTTP_SESSION is None:
        raise RuntimeError("HTTP Session is not initialized! Call init_http_session() in main.py")
    return _GLOBAL_HTTP_SESSION


def init_http_session() -> None:
    global _GLOBAL_HTTP_SESSION
    if _GLOBAL_HTTP_SESSION is None:
        _GLOBAL_HTTP_SESSION = aiohttp.ClientSession()
        logger.info("Global HTTP session initialized.")


async def close_global_session() -> None:
    global _GLOBAL_HTTP_SESSION
    if _GLOBAL_HTTP_SESSION:
        await _GLOBAL_HTTP_SESSION.close()
        _GLOBAL_HTTP_SESSION = None


def _cleanup_temp_files_sync(temp_file_base: str) -> None:
    for f in glob.glob(f"{temp_file_base}.*"):
        try:
            os.remove(f)
        except OSError as e:
            logger.warning(f"Failed to remove temp file {f}: {e}")


async def cleanup_temp_files(temp_file_base: str) -> None:
    if not temp_file_base:
        return
    await asyncio.to_thread(_cleanup_temp_files_sync, temp_file_base)


# yt-dlp options

def _base_ydl_opts() -> Dict[str, Any]:
    return {
        'logger': YTDLPLogger(),
        'verbose': True,
        'quiet': False,
        'noplaylist': True,
        'cookiefile': 'data/cookies.txt',
        'encoding': 'utf-8',
        'postprocessors': [],
    }


def _enable_node_js_runtime(opts: Dict[str, Any]) -> Dict[str, Any]:
    opts['js_runtimes'] = {'node': {}}
    return opts


def _enable_android_client(opts: Dict[str, Any]) -> Dict[str, Any]:
    opts['extractor_args'] = {'youtube': {'client': 'android'}}
    opts['no_warnings'] = True
    opts['http_headers'] = DEFAULT_HTTP_HEADERS
    return opts


def _search_ydl_opts() -> Dict[str, Any]:
    opts = _base_ydl_opts()
    opts.update({
        'skip_download': True,
        'extract_flat': True,
    })
    return _enable_node_js_runtime(opts)


def _precheck_ydl_opts() -> Dict[str, Any]:
    duration_filter = match_filter_func(f'duration < {MAX_SONG_DURATION_SEC}')
    opts = _base_ydl_opts()
    opts.update({
        'format': 'bestaudio/best',
        'skip_download': True,
        'match_filter': duration_filter,
    })
    opts = _enable_node_js_runtime(opts)
    return _enable_android_client(opts)


def _download_ydl_opts(outtmpl: str) -> Dict[str, Any]:
    duration_filter = match_filter_func(f'duration < {MAX_SONG_DURATION_SEC}')
    opts = _base_ydl_opts()
    opts.update({
        'format': 'bestaudio/best',
        'outtmpl': outtmpl,
        'writethumbnail': True,
        'match_filter': duration_filter,
    })
    opts = _enable_node_js_runtime(opts)
    opts = _enable_android_client(opts)
    return opts


# Dislikes API

async def get_dislikes(video_id: str) -> Optional[int]:
    url = f"https://returnyoutubedislikeapi.com/votes?videoId={video_id}"
    try:
        session = get_http_session()
    except RuntimeError:
        logger.error("HTTP Session not initialized! GLOBAL_HTTP_SESSION is None.")
        return None

    try:
        timeout_settings = ClientTimeout(total=DISLIKES_API_TIMEOUT_SEC)
        async with session.get(url, timeout=timeout_settings) as resp:
            if resp.status != 200:
                logger.warning(f"API status error for {video_id}: {resp.status}")
                return None

            data = await resp.json()
            if not isinstance(data, dict):
                logger.warning(f"API returned non-dictionary data or None for {video_id}.")
                return None

            return data.get("dislikes")

    except aiohttp.ClientConnectorError as e:
        logger.warning(f"Failed to fetch dislikes for {video_id} (Connection Error): {e}")
    except asyncio.TimeoutError:
        logger.warning(f"Failed to fetch dislikes for {video_id} (Timeout)")
    except Exception as e:
        logger.warning(f"Unexpected error in get_dislikes for {video_id}: {e}")
    return None


# Search

def _run_search(query: str) -> List[Dict[str, Any]]:
    refined_query = f"{query} official music video"
    with YoutubeDL(_search_ydl_opts()) as ydl:  # type: ignore
        try:
            result = ydl.extract_info(f"ytsearch10:{refined_query}", download=False)
            entries = (result or {}).get("entries", [])

            if not entries:
                return []

            valid_entries = []
            has_overlong_tracks = False

            for entry in entries:
                duration = entry.get("duration")
                if duration and duration > MAX_SONG_DURATION_SEC:
                    has_overlong_tracks = True
                    continue

                valid_entries.append(entry)

            if not valid_entries and has_overlong_tracks:
                raise Exception("SEARCH_ALL_TOO_LONG")

            return valid_entries

        except DownloadError:
            logger.error(f"yt-dlp search failed for query: {query}")
            return []


async def search_multiple(query: str) -> List[Dict[str, Any]]:
    try:
        return await asyncio.wait_for(
            asyncio.to_thread(_run_search, query),
            timeout=SEARCH_TIMEOUT_SEC,
        )
    except asyncio.TimeoutError:
        logger.error(f"Search timed out for query: {query}")
        return []


# Download

def _precheck_duration_and_size(url: str) -> None:
    with YoutubeDL(_precheck_ydl_opts()) as ydl:  # type: ignore
        info = ydl.extract_info(url, download=False)

    duration = info.get("duration")
    if duration is not None and duration > MAX_SONG_DURATION_SEC:
        raise Exception("LONG_AUDIO")

    filesize_estimate = info.get('filesize') or info.get('filesize_approx')
    if filesize_estimate is not None and filesize_estimate > MAX_FILE_SIZE_BYTES:
        raise Exception("TOO_LARGE_PRECHECK")


def _locate_downloaded_file(temp_file_base: str, extensions: Tuple[str, ...]) -> Optional[str]:
    for ext in extensions:
        candidate = f"{temp_file_base}.{ext}"
        if os.path.exists(candidate):
            return candidate
    return None


def _normalize_to_mp3(audio_file: str) -> str:
    if audio_file.endswith('.mp3'):
        return audio_file

    file_base, _ = os.path.splitext(audio_file)
    new_mp3 = f"{file_base}.mp3"
    if os.path.exists(new_mp3):
        os.remove(new_mp3)
    os.rename(audio_file, new_mp3)
    return new_mp3


def _run_download(url: str) -> Tuple[Dict[str, Any], Optional[str], Optional[str], str]:
    _precheck_duration_and_size(url)

    unique_id = uuid.uuid4().hex
    temp_file_base = os.path.join(TEMP_PATH, unique_id)

    try:
        with YoutubeDL(_download_ydl_opts(f'{temp_file_base}.%(ext)s')) as ydl:  # type: ignore
            info = ydl.extract_info(url, download=True)
            temp_file_base = os.path.splitext(ydl.prepare_filename(info))[0]

        audio_file = _locate_downloaded_file(temp_file_base, AUDIO_EXTENSIONS)
        if audio_file:
            audio_file = _normalize_to_mp3(audio_file)

        thumb = _locate_downloaded_file(temp_file_base, THUMBNAIL_EXTENSIONS)

        if audio_file and os.path.getsize(audio_file) > MAX_FILE_SIZE_BYTES:
            raise Exception("TOO_LARGE_POSTCHECK")

        return info, audio_file, thumb, temp_file_base
    except Exception:
        _cleanup_temp_files_sync(temp_file_base)
        raise


async def download_by_url(url: str):
    try:
        return await asyncio.wait_for(
            asyncio.to_thread(_run_download, url),
            timeout=DOWNLOAD_TIMEOUT_SEC,
        )
    except asyncio.TimeoutError:
        raise Exception("YT_DOWNLOAD_TIMEOUT")
    except Exception as e:
        logger.warning(f"Error during download for {url}: {e}")
        raise
