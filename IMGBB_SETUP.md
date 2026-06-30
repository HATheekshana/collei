# ImgBB Integration Setup Guide

This guide explains how to set up and use the imgbb image hosting integration with the Collei bot.

## What's New?

- **Rich slideshow support** - Images are now hosted on imgbb for better slideshow compatibility
- **Dual storage** - Images are uploaded to both Telegram (backup) and imgbb (primary)
- **Automatic fallback** - If imgbb is unavailable, the bot falls back to Telegram file_ids
- **Migration tool** - Script to upload all existing images to imgbb

## Prerequisites

1. **ImgBB Account**: Create a free account at https://imgbb.com
2. **ImgBB API Key**: Get your API key from https://api.imgbb.com
3. **Update .env file** with:
   ```
   BOT_TOKEN=your_telegram_bot_token
   IMGBB_API_KEY=your_imgbb_api_key
   MEDIA_CHANNEL=-1001234567890  # Your Telegram media channel ID
   ```

## Setup Steps

### 1. Get ImgBB API Key

1. Go to https://imgbb.com
2. Sign up for a free account (or log in)
3. Go to https://api.imgbb.com
4. Copy your API key

### 2. Update Environment Variables

Edit your `.env` file:
```env
IMGBB_API_KEY=your_api_key_here
MEDIA_CHANNEL=-1001234567890
```

### 3. Migrate Existing Images

Run the migration script to upload all existing card and guide images to imgbb:

```bash
python migrate_to_imgbb.py
```

This will:
- Download each image from Telegram
- Upload to imgbb
- Save the imgbb URL to the JSON files
- Display progress and results

**Note**: This may take a while if you have many images. The script respects rate limits.

## Usage

### Adding New Images

When admins use `/addcard` or `/addguide`:

```
Reply to a photo: /addcard Wriothesley
```

The bot will:
1. ✅ Upload to Telegram channel (backup storage)
2. ✅ Upload to imgbb (for rich slideshow)
3. ✅ Save both URLs to JSON
4. ✅ Notify admin with status

### Viewing Images

When users request character info, the bot will:
1. Try to send a **rich slideshow** with imgbb URLs
2. If that fails, fallback to **Telegram media group** with file_ids
3. Always ensure images are visible

## File Structure

```
utils/
  ├── imgbb.py           # ImgBB upload utilities
  ├── cards.py           # Updated with image_url support
  └── guides.py          # Updated with image_url support

handlers/
  └── card_guide_admin.py # Updated /add commands

data/
  └── config.py          # New config constants

migrate_to_imgbb.py      # Migration script (run once)
```

## JSON Format

Cards and guides now support both storage methods:

```json
{
  "name": "Wriothesley",
  "filename": "Wriothesley.jpg",
  "character_key": "wriothesley",
  "file_id": "AgAC...",           # Telegram backup
  "image_url": "https://imgbb.com/..." # Primary (rich slideshow)
}
```

## Troubleshooting

### ImgBB API Key Not Set
```
Error: IMGBB_API_KEY not set in environment variables
```
**Solution**: Add `IMGBB_API_KEY=your_key` to `.env` file

### Migration Fails
```
Error: Failed to upload to imgbb
```
**Solution**: 
- Check API key is valid
- Check internet connection
- Run again later (rate limits)

### Rich Slideshow Not Working
- Check imgbb URLs are valid: `https://imgbb.com/...`
- Bot falls back to Telegram file_ids automatically
- Check bot has access to send messages

## Performance Notes

- **ImgBB uploads**: ~1 image per second (rate limit friendly)
- **Migration time**: ~200 images = 3-5 minutes
- **Rich slideshow**: Loads faster than Telegram file_ids
- **Fallback**: Works instantly if imgbb unavailable

## Support

For issues:
1. Check logs: `python -u bot.py 2>&1`
2. Verify .env variables are set
3. Test migration script separately
4. Check ImgBB API status

## Optional: Automated Migration on Startup

To automatically migrate missing images when the bot starts, add to `bot.py`:

```python
# In your startup sequence:
from migrate_to_imgbb import migrate_cards, migrate_guides
await migrate_cards(bot)
await migrate_guides(bot)
```

This ensures all new images are uploaded to imgbb without manual intervention.
