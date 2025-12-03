import os
import asyncio
import logging
import time
from dotenv import load_dotenv
from typing import List
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from core.yt_dlp_update import yt_dlp_manager
from logging.handlers import RotatingFileHandler
import sys

DATA_PATH = "data"
TEMP_PATH = "temp"
os.makedirs(TEMP_PATH, exist_ok=True)
LOG_FILE = os.path.join(DATA_PATH, "bot.log")
load_dotenv(dotenv_path=os.path.join(DATA_PATH, ".env"))

file_handler = RotatingFileHandler(
    LOG_FILE, 
    maxBytes=10*1024*1024,
    backupCount=3,
    encoding='utf-8'
)
file_handler.setFormatter(logging.Formatter(
    '[%(asctime)s] [%(levelname)s] %(message)s', 
    datefmt='%Y-%m-%d %H:%M:%S'
))
file_handler.setLevel(logging.ERROR)
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setFormatter(logging.Formatter(
    '[%(asctime)s] [%(levelname)s] %(message)s', 
    datefmt='%H:%M:%S'
))

logging.basicConfig(
    level=logging.INFO,
    handlers=[file_handler, console_handler]
)
logger = logging.getLogger(__name__)

BOT_TOKEN: str = os.getenv('BOT_TOKEN')
ALLOWED_CHAT_RAW = os.getenv('ALLOWED_CHAT_ID', '')
MAX_FILE_SIZE_MB: int = int(os.getenv('MAX_FILE_SIZE_MB'))
MAX_SONG_DURATION_MIN: int = int(os.getenv('MAX_SONG_DURATION_MIN', 15))
ALLOW_PRIVATE_CHAT: bool = os.getenv('ALLOW_PRIVATE_CHAT', 'false').lower() == 'true'
INFO_EXPIRATION_HOURS: int = int(os.getenv('INFO_EXPIRATION_HOURS', 10))
ANTI_SPAM_INTERVAL: int = int(os.getenv('ANTI_SPAM_INTERVAL'))
ANTI_SPAM_CALLBACK_INTERVAL: float = float(os.getenv('ANTI_SPAM_CALLBACK_INTERVAL', 1.0))
CONCURRENT_DOWNLOAD_LIMIT: int = int(os.getenv('CONCURRENT_DOWNLOAD_LIMIT', 5))
DB_FILE: str = os.getenv('DB_FILE', 'songs_cache.db')

MAX_FILE_SIZE_BYTES: int = MAX_FILE_SIZE_MB * 1024 * 1024
MAX_SONG_DURATION_SEC: int = MAX_SONG_DURATION_MIN * 60
DB_PATH = os.path.join(DATA_PATH, DB_FILE) 

BLOCKED_USER_IDS: List[int] = [int(i.strip()) for i in os.getenv('BLOCKED_USER_IDS', '').split(',') if i.strip()]

BOT_START_TIME = time.time()

if ALLOWED_CHAT_RAW.lower() == 'false':
    ALLOWED_CHAT_IDS: List[int] = []
    logger.info("Bot is restricted from all public chats (ALLOWED_CHAT_ID=false).")
elif ALLOWED_CHAT_RAW == '':
    ALLOWED_CHAT_IDS: List[int] = [0]
    logger.info("Bot is allowed in ALL public chats (ALLOWED_CHAT_ID is empty).")
else:
    try:
        ALLOWED_CHAT_IDS: List[int] = [int(i.strip()) for i in ALLOWED_CHAT_RAW.split(',') if i.strip()]
        logger.info(f"Bot is restricted to specific chats: {ALLOWED_CHAT_IDS}")
    except ValueError:
        ALLOWED_CHAT_IDS: List[int] = []
        logger.error(f"Invalid format for ALLOWED_CHAT_ID: {ALLOWED_CHAT_RAW}. Access restricted.")

try:
    YDL_EXECUTABLE_PATH = yt_dlp_manager.initialize()
    logger.info(f"yt-dlp executable is confirmed and ready at: {YDL_EXECUTABLE_PATH}")
except RuntimeError as e:
    logger.critical(f"FATAL ERROR: {e}")
    raise SystemExit(1) 

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
dp = Dispatcher()

download_semaphore = asyncio.Semaphore(CONCURRENT_DOWNLOAD_LIMIT)
dp['download_semaphore'] = download_semaphore