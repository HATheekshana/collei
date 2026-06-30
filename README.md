# Collei Bot 🌿

A feature-rich Telegram bot for Genshin Impact character guides, builds, artifacts, and boss information with rich media support.

## Features

✨ **Rich Slideshows** - Display character cards and guides as beautiful interactive slideshows using Telegram's rich message format

🖼️ **Dual Image Storage** - Automatic fallback between ImgBB URLs and Telegram file_ids for reliable image delivery

🔍 **Smart Search** - Find characters, artifacts, and bosses with intelligent fuzzy matching and prefix search

⌨️ **Inline Queries** - Search directly from the compose box without opening a chat

📊 **Character Guides** - Access organized cards and guides for every character

⚔️ **Boss Information** - Get boss details and strategies at a glance

🏺 **Artifact Database** - Complete artifact set effects and bonuses

## Installation

### Prerequisites
- Python 3.11+
- Telegram Bot Token (from [@BotFather](https://t.me/botfather))
- ImgBB API Key (from [imgbb.com](https://imgbb.com/))
- Telegram Channel ID (for media backup storage)

### Setup

1. **Clone the repository**
```bash
git clone https://github.com/yourusername/collei.git
cd collei
```

2. **Create virtual environment**
```bash
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
```

3. **Install dependencies**
```bash
pip install -r requirements.txt
```

4. **Configure environment variables**

Create a `.env` file in the project root:
```env
BOT_TOKEN=your_bot_token_here
IMGBB_API_KEY=your_imgbb_api_key_here
MEDIA_CHANNEL=-1001234567890
LOG_CHAT_ID=-1001234567890
BOT_USERNAME=ColleiBot
```

**Required variables:**
- `BOT_TOKEN` - Telegram Bot API token
- `IMGBB_API_KEY` - ImgBB API key for image uploads
- `MEDIA_CHANNEL` - Telegram channel ID for media backup (use negative format)
- `LOG_CHAT_ID` - Chat ID for bot logs and notifications

5. **Prepare media files**

Organize your images in these directories:
```
cards/          # Character card images
guides/         # Character guide images  
artifacts/      # Artifact set images
```

6. **Start the bot**
```bash
python bot.py
```

## Usage

### User Commands

| Command | Description |
|---------|-------------|
| `/start` | Start the bot and get help |
| `/[character]` | Get character cards and guides (e.g., `/albedo`) |
| `/search [query]` | Search for characters, artifacts, or bosses |
| `/allcommands` | List all available character commands |
| `/addarti` | Get artifact information |
| `/bossimg` | Get boss information |

### Inline Queries

Type `@YourBotName [character]` in any chat to search without opening a conversation.

### Admin Commands

| Command | Description |
|---------|-------------|
| `/addcard [character]` | Add a new character card |
| `/addguide [character]` | Add a new character guide |
| `/delcard [character]` | Delete a character card |
| `/delguide [character]` | Delete a character guide |

## Project Structure

```
collei/
├── bot.py                    # Main bot entry point
├── init_metadata.py          # Initialize JSON metadata from local files
├── migrate_to_imgbb.py       # Auto-migrate images to ImgBB
├── requirements.txt          # Python dependencies
├── .env                      # Environment configuration (create this)
├── cards.json               # Character card metadata
├── guides.json              # Character guide metadata
├── bosses.json              # Boss information
│
├── cards/                   # Character card images
├── guides/                  # Character guide images
├── artifacts/               # Artifact set images
├── data/                    # Configuration and data lookups
│   ├── config.py           # Bot configuration constants
│   ├── aliases.py          # Character name aliases
│   └── search_items.py     # Searchable items database
├── handlers/                # Command and event handlers
│   ├── main.py             # Main command router
│   ├── inline.py           # Inline query handler
│   ├── media.py            # Media sending functions (rich slideshow)
│   ├── admin.py            # Admin artifact commands
│   ├── card_guide_admin.py # Admin card/guide management
│   └── boss_admin.py       # Admin boss commands
└── utils/                   # Utility modules
    ├── helper.py           # Helper functions (media resolution)
    ├── commands.py         # Bot command registration
    ├── search.py           # Search functionality
    ├── cards.py            # Card metadata management
    ├── guides.py           # Guide metadata management
    ├── artifacts.py        # Artifact lookups
    ├── bosses.py           # Boss lookups
    └── imgbb.py            # ImgBB upload operations
```

## Data Storage Architecture

### JSON Metadata Files

The bot uses JSON files to track images with dual storage:

**cards.json / guides.json structure:**
```json
[
  {
    "name": "Character Name",
    "filename": "filename.jpg",
    "character_key": "characterkey",
    "file_id": "AgACAgU...",           // Telegram backup
    "image_url": "https://i.ibb.co/..." // ImgBB primary
  }
]
```

### Image Storage Flow

1. **On Startup:**
   - `init_metadata.py` creates JSON files from local image directories
   - `sync_media_to_telegram()` uploads all images to Telegram channel, saves `file_id`
   - `migrate_all_to_imgbb()` uploads all images to ImgBB, saves `image_url`

2. **Rich Slideshow Display:**
   - `resolve_character_media()` fetches metadata from JSON
   - If `image_url` exists → uses ImgBB URL (public, fast)
   - If `image_url` missing → falls back to `file_id` (cached in Telegram)
   - Sends `<tg-slideshow>` HTML format via `sendRichMessage` API

3. **When Adding New Images** (`/addcard`, `/addguide`):
   - Saves to local file
   - Uploads to Telegram channel → saves `file_id`
   - Uploads to ImgBB → saves `image_url`
   - Stores both in JSON for fallback support

## Features in Detail

### Rich Slideshows 🎨

Character cards and guides are displayed as beautiful interactive slideshows:

```
🖼️ [Previous Image] [1/5] [Next Image] 🖼️
   Albedo
```

**Requirements:**
- All images must have ImgBB URLs (`image_url` field)
- Falls back to media group if any image missing `image_url`

### Dual Image Hosting

- **Primary (ImgBB):** Fast, public, reliable
- **Fallback (Telegram):** Private channel backup, unlimited storage

### Smart Search

- **Fuzzy matching** - Typos are forgiven
- **Prefix matching** - Type partial names
- **Token matching** - Search by multiple words
- **Scoring system** - Best matches first

## Configuration

### Bot Commands

Update available commands in Telegram:
```bash
python bot.py  # Automatically registers commands on startup
```

### Search Items

Edit `data/search_items.py` to add new searchable characters:
```python
SEARCH_ITEMS = {
    "albedo": "Albedo",
    "amber": "Amber",
    # ... add more
}
```

### Character Aliases

Edit `data/aliases.py` for command shortcuts:
```python
ALIASES = {
    "al": "albedo",
    "am": "amber",
}
```

## Troubleshooting

### Rich Slideshow Not Showing

1. **Check image_url field:**
   ```bash
   # Verify all entries have image_url in JSON
   grep -c "image_url" cards.json guides.json
   ```

2. **Check imgbb.py errors:**
   - Ensure `IMGBB_API_KEY` is set
   - Verify ImgBB API key is valid
   - Check rate limits (max 30 uploads/hour on free tier)

3. **Enable debug logging:**
   - Check bot logs for `send_media_slideshow` debug output
   - Logs show which condition is failing (URLs, file_ids, etc.)

### Images Not Uploading

1. **Verify file paths:**
   - Images must be in `cards/` or `guides/` folders
   - Use supported formats: `.jpg`, `.png`, `.gif`, `.webp`

2. **Check Telegram channel access:**
   ```bash
   # Verify MEDIA_CHANNEL is correct
   python -c "from data.config import MEDIA_CHANNEL; print(MEDIA_CHANNEL)"
   ```

3. **Check permissions:**
   - Bot must be admin in MEDIA_CHANNEL
   - Bot must have send_photo permission

### Search Not Finding Items

1. **Verify SEARCH_ITEMS:**
   ```bash
   # Check if character is in search_items.py
   grep -i "character_name" data/search_items.py
   ```

2. **Check character_key format:**
   - Must be lowercase, no spaces
   - Should match the key in cards.json

## Development

### Running Tests

```bash
# Check for syntax errors
python -m py_compile *.py handlers/*.py utils/*.py
```

### Adding New Features

1. Create handler in `handlers/`
2. Register router in `bot.py`
3. Add logging for debugging
4. Test with debug output enabled

### Code Organization

- **handlers/** - Telegram message/callback handlers
- **utils/** - Reusable business logic
- **data/** - Static configuration and lookup tables
- **migrate_to_imgbb.py** - Data migration utilities

## Dependencies

See `requirements.txt`:

```
aiogram>=3.0.0       # Telegram bot framework
aiohttp>=3.8.0       # Async HTTP client (for imgbb)
python-dotenv>=0.19  # Environment variable loading
```

## API Documentation

### ImgBB Integration

See `utils/imgbb.py` for complete upload handling:

- `upload_file_to_imgbb(file_path)` - Upload local file
- `upload_bytes_to_imgbb(file_data, filename)` - Upload binary data
- `upload_file_by_telegram_download(bot, file_id, filename)` - Download from Telegram and upload to ImgBB

### Media Resolution

See `utils/helper.py`:

- `resolve_character_media(bot, character_key)` - Get cards + guides with ImgBB URLs + Telegram file_ids
- `resolve_character_file_ids(bot, character_key)` - Get only Telegram file_ids (legacy)

### Rich Slideshow

See `handlers/media.py`:

- `send_media_slideshow(message, media_items, caption)` - Send rich slideshow or fallback to media group
- `_raw_api_request(bot, method, payload)` - Direct Telegram API calls

## Performance Tips

1. **Image Optimization:**
   - Use `.jpg` for photos (smaller size)
   - Use `.png` for images with transparency
   - Compress before uploading

2. **Rate Limiting:**
   - ImgBB free tier: 30 uploads/hour
   - Migration script includes 0.3s sleep between uploads
   - Search is cached locally (no API calls)

3. **Database:**
   - Metadata is loaded into memory on startup
   - Caching improves search speed
   - JSON files are read-only during operation

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes with clear commit messages
4. Test thoroughly
5. Submit a pull request

## License

MIT License - See LICENSE file for details

## Support

For issues, questions, or suggestions:
- Open a GitHub issue
- Check existing documentation
- Review bot logs for error details

## Credits

Built with ❤️ for Genshin Impact fans

- **Framework:** [aiogram](https://github.com/aiogram/aiogram)
- **Image Hosting:** [ImgBB](https://imgbb.com/)
- **Bot Platform:** [Telegram](https://telegram.org/)

---

**Made for Genshin Impact | Not affiliated with HoYoverse**
