import os
import time
import logging
import subprocess
import sys

logger = logging.getLogger(__name__)

EXPIRATION_SECONDS = 24 * 3600 

LAST_UPDATE_TIMESTAMP_FILE = 'data/yt_dlp_last_update.txt'

def _update_yt_dlp_package() -> bool:
    logger.info("Attempting to update yt-dlp via pip...")
    try:
        command = [sys.executable, "-m", "pip", "install", "--upgrade", "yt-dlp"]
        
        result = subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True
        )
        logger.info(f"yt-dlp package updated successfully: {result.stdout}")
        
        try:
            with open(LAST_UPDATE_TIMESTAMP_FILE, 'w') as f:
                f.write(str(int(time.time())))
            logger.debug(f"Updated timestamp file: {LAST_UPDATE_TIMESTAMP_FILE}")
        except Exception as e:
            logger.error(f"Failed to write update timestamp: {e}")
            
        return True
    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to update yt-dlp via pip. Stderr: {e.stderr} Stdout: {e.stdout}")
        return False
    except FileNotFoundError:
        logger.error("pip command not found. Ensure pip is correctly installed.")
        return False
    except Exception as e:
        logger.error(f"An unexpected error occurred during pip update: {e}")
        return False

def check_and_update_needed() -> bool:
    try:
        if not os.path.exists(LAST_UPDATE_TIMESTAMP_FILE):
            logger.info("Update timestamp file not found. Update is needed.")
            return True
        
        with open(LAST_UPDATE_TIMESTAMP_FILE, 'r') as f:
            last_update_time = int(f.read().strip())
        
        current_time = int(time.time())
        if current_time - last_update_time > EXPIRATION_SECONDS:
            logger.info(f"Last update was over {EXPIRATION_SECONDS // 3600} hours ago. Update is needed.")
            return True
        
        logger.info("yt-dlp check interval not yet expired. No update needed.")
        return False
    except Exception as e:
        logger.warning(f"Error checking update timestamp, forcing update attempt: {e}")
        return True

def initialize() -> bool:
    if check_and_update_needed():
        _update_yt_dlp_package() 
        
    try:
        import yt_dlp
        logger.info("yt-dlp package is available.")
        return True
    except ImportError:
        logger.error("The 'yt-dlp' package is not installed and cannot be imported.")
        logger.info("Attempting one final installation of yt-dlp since import failed...")
        if _update_yt_dlp_package():
             try:
                 import yt_dlp 
                 return True
             except ImportError:
                 pass
             
        raise RuntimeError("Failed to ensure yt-dlp package is ready. Cannot run the bot.")