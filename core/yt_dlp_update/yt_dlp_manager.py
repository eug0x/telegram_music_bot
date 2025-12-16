import os
import sys
import requests
import time
import shutil
import logging

logger = logging.getLogger(__name__)

YT_DLP_DIR = 'yt_dlp_bin'
EXPIRATION_SECONDS = 24 * 3600

if sys.platform.startswith("win"):
    YT_DLP_EXE_NAME = 'yt-dlp.exe'
    DOWNLOAD_URL = "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp.exe"
else:
    YT_DLP_EXE_NAME = 'yt-dlp'
    DOWNLOAD_URL = "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp"

YT_DLP_PATH = os.path.join(YT_DLP_DIR, YT_DLP_EXE_NAME)

def get_exe_path() -> str:
    return YT_DLP_PATH

def _download_yt_dlp() -> bool:
    os.makedirs(YT_DLP_DIR, exist_ok=True)
    logger.info(f"Downloading latest yt-dlp from: {DOWNLOAD_URL}")
    temp_path = YT_DLP_PATH + ".tmp"

    try:
        with requests.get(DOWNLOAD_URL, stream=True, timeout=30) as r:
            r.raise_for_status()
            with open(temp_path, 'wb') as f:
                shutil.copyfileobj(r.raw, f)

        os.replace(temp_path, YT_DLP_PATH)

        if not sys.platform.startswith("win"):
            os.chmod(YT_DLP_PATH, 0o755)

        logger.info(f"Successfully downloaded and saved: {YT_DLP_PATH}")
        return True
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to download yt-dlp: {e}")
    except Exception as e:
        logger.error(f"Error during file saving/renaming: {e}")
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)
    return False

def check_and_update() -> bool:
    logger.info("Starting yt-dlp executable check...")
    if not os.path.exists(YT_DLP_PATH):
        logger.warning(f"Executable not found at {YT_DLP_PATH}. Attempting download.")
        return _download_yt_dlp()

    try:
        mod_time = os.path.getmtime(YT_DLP_PATH)
        current_time = time.time()
        if current_time - mod_time > EXPIRATION_SECONDS:
            logger.info(f"Executable is older than {EXPIRATION_SECONDS // 3600} hours. Attempting update.")
            return _download_yt_dlp()
        logger.info("Executable is up-to-date and ready.")
        return True
    except OSError as e:
        logger.error(f"Error accessing file system for {YT_DLP_PATH}: {e}")
        return _download_yt_dlp()

def initialize() -> str:
    if check_and_update():
        return YT_DLP_PATH
    else:
        raise RuntimeError("Failed to ensure yt-dlp executable is ready. Cannot run the bot.")
