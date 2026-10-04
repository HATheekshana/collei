import os
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")
# LOG_CHAT_ID may be unset in development; keep None when missing to avoid import-time errors
LOG_CHAT_ID = int(os.getenv("LOG_CHAT_ID")) if os.getenv("LOG_CHAT_ID") else None
# SUPPORT_CHAT_ID defaults to the same chat as LOG_CHAT_ID when not configured separately.
SUPPORT_CHAT_ID = int(os.getenv("LOG_CHAT_ID")) if os.getenv("LOG_CHAT_ID") else None
BOT_USERNAME = os.getenv("BOT_USERNAME")

# The bot now only accepts commands that are defined in search_items.py
# Special commands (start, addarti, allcommands) are always allowed
# All other commands are silently ignored

CARDS_FOLDER = "cards"
GUIDES_FOLDER = "guides"
BOSSES_FILE = "bosses.json"


# JSON file storing Abyss / Theatre / Stygian record images shown via the
# buttons under /next and /current
SPECIAL_MEDIA_FILE = "special_media.json"

# JSON file storing the current/next cycle id per category (abyss/theatre/
# stygian), used by /nabyss /ntheatre /nstygian and /pabyss /ptheatre /pstygian
CYCLE_STATE_FILE = "cycle_state.json"

# JSON file mapping each complaint forwarded to the support chat (keyed by
# the message id of the header the bot posts there) back to the original
# user/chat, so /answer knows who to reply to.
COMPLAINTS_FILE = "complaints.json"

# JSON file storing every private-chat user id / group id the bot has seen,
# used by /broadcast. (Was missing from config, which broke bot startup —
# added back here.)
BROADCAST_TARGETS_FILE = "broadcast_targets.json"

# JSON file storing user IDs blocked from using the bot.
BANNED_USERS_FILE = "banned_users.json"

# Telegram media channel for backup storage
MEDIA_CHANNEL = int(os.getenv("MEDIA_CHANNEL", "-1001234567890"))

# ImgBB API key for image uploads
IMGBB_API_KEY = os.getenv("IMGBB_API_KEY", "")

BOSS_IMAGE_CHANNEL = -1004339480119
ADMIN_IDS = {1675903713}

# URL of the admin panel web app's login page (Next.js app). The /admin
# command opens this as a Telegram Mini App button so it runs inside
# Telegram's WebApp view (real initData auth) instead of a plain browser tab.
ADMIN_PANEL_URL = os.getenv("ADMIN_PANEL_URL", "https://collei-web.vercel.app/admin/login")

# HoYoLab cookies for fetching banner data
HOYOLAB_COOKIES = os.getenv("HOYOLAB_COOKIES", "")
GENSHIN_SYNC_UID = os.getenv("GENSHIN_SYNC_UID")
GENSHIN_SYNC_REGION = os.getenv("GENSHIN_SYNC_REGION", "asia")