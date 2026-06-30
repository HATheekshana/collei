import os
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")
# LOG_CHAT_ID may be unset in development; keep None when missing to avoid import-time errors
LOG_CHAT_ID = int(os.getenv("LOG_CHAT_ID")) if os.getenv("LOG_CHAT_ID") else None
BOT_USERNAME = os.getenv("BOT_USERNAME")

# The bot now only accepts commands that are defined in search_items.py
# Special commands (start, addarti, allcommands) are always allowed
# All other commands are silently ignored

CARDS_FOLDER = "cards"
GUIDES_FOLDER = "guides"
ARTIFACTS_FOLDER = "artifacts"
ARTIFACTS_INFO_FILE = os.path.join(ARTIFACTS_FOLDER, "info.json")
BOSSES_FILE = "bosses.json"

# JSON files for cards and guides metadata
CARDS_FILE = "cards.json"
GUIDES_FILE = "guides.json"

# Telegram media channel for backup storage
MEDIA_CHANNEL = int(os.getenv("MEDIA_CHANNEL", "-1001234567890"))

# ImgBB API key for image uploads
IMGBB_API_KEY = os.getenv("IMGBB_API_KEY", "")

BOSS_IMAGE_CHANNEL = -1004339480119
ADMIN_IDS = {1675903713}