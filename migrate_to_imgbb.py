#!/usr/bin/env python3
"""
Migration utilities: Upload existing card and guide images to imgbb.

This module provides async functions to be called during bot startup.
For each entry with a Telegram file_id but no imgbb URL:
  1. Downloads the image from Telegram
  2. Uploads to imgbb
  3. Saves the image_url to JSON

Can be run standalone or integrated into bot startup.
"""

import asyncio
import logging
import os
import sys
from pathlib import Path

from utils.cards import load_cards, set_card_image_url, save_cards
from utils.guides import load_guides, set_guide_image_url, save_guides
from utils.imgbb import upload_file_by_telegram_download, ImgBBUploadError


async def migrate_cards_to_imgbb(bot) -> dict:
    """
    Migrate all cards without imgbb URLs.
    
    Returns:
        dict with keys: migrated, skipped, failed
    """
    cards = load_cards()
    stats = {"migrated": 0, "skipped": 0, "failed": 0}
    
    if not cards:
        logging.info("No cards to migrate")
        return stats
    
    to_migrate = [c for c in cards if not c.get("image_url") and c.get("file_id")]
    
    if not to_migrate:
        logging.info("All cards already have imgbb URLs")
        return stats
    
    logging.info(f"Migrating {len(to_migrate)} cards to imgbb...")
    
    for i, card in enumerate(to_migrate, 1):
        filename = card.get("filename", "unknown")
        file_id = card.get("file_id")
        name = card.get("name", filename)
        
        try:
            logging.info(f"  [{i}/{len(to_migrate)}] Uploading: {name}...")
            url = await upload_file_by_telegram_download(
                bot, file_id, 
                filename=f"{name}_{file_id[-8:]}.jpg"
            )
            
            if set_card_image_url(filename, url):
                logging.info(f"    ✅ {name}")
                stats["migrated"] += 1
            else:
                logging.error(f"    ❌ Failed to save URL")
                stats["failed"] += 1
            
            await asyncio.sleep(0.3)  # Be nice to APIs
            
        except ImgBBUploadError as e:
            logging.warning(f"    ⚠️ {name}: {e}")
            stats["failed"] += 1
        except Exception as e:
            logging.error(f"    ❌ {name}: {e}")
            stats["failed"] += 1
    
    if stats["migrated"] > 0:
        logging.info(f"✅ Cards migration: {stats['migrated']} uploaded, {stats['failed']} failed")
    
    return stats


async def migrate_guides_to_imgbb(bot) -> dict:
    """
    Migrate all guides without imgbb URLs.
    
    Returns:
        dict with keys: migrated, skipped, failed
    """
    guides = load_guides()
    stats = {"migrated": 0, "skipped": 0, "failed": 0}
    
    if not guides:
        logging.info("No guides to migrate")
        return stats
    
    to_migrate = [g for g in guides if not g.get("image_url") and g.get("file_id")]
    
    if not to_migrate:
        logging.info("All guides already have imgbb URLs")
        return stats
    
    logging.info(f"Migrating {len(to_migrate)} guides to imgbb...")
    
    for i, guide in enumerate(to_migrate, 1):
        filename = guide.get("filename", "unknown")
        file_id = guide.get("file_id")
        name = guide.get("name", filename)
        
        try:
            logging.info(f"  [{i}/{len(to_migrate)}] Uploading: {name}...")
            url = await upload_file_by_telegram_download(
                bot, file_id, 
                filename=f"{name}_{file_id[-8:]}.jpg"
            )
            
            if set_guide_image_url(filename, url):
                logging.info(f"    ✅ {name}")
                stats["migrated"] += 1
            else:
                logging.error(f"    ❌ Failed to save URL")
                stats["failed"] += 1
            
            await asyncio.sleep(0.3)  # Be nice to APIs
            
        except ImgBBUploadError as e:
            logging.warning(f"    ⚠️ {name}: {e}")
            stats["failed"] += 1
        except Exception as e:
            logging.error(f"    ❌ {name}: {e}")
            stats["failed"] += 1
    
    if stats["migrated"] > 0:
        logging.info(f"✅ Guides migration: {stats['migrated']} uploaded, {stats['failed']} failed")
    
    return stats


async def migrate_all_to_imgbb(bot):
    """
    Migrate both cards and guides to imgbb.
    Call this during bot startup.
    """
    try:
        from data.config import IMGBB_API_KEY
        
        if not IMGBB_API_KEY:
            logging.warning("IMGBB_API_KEY not set, skipping imgbb migration")
            return
        
        cards_stats = await migrate_cards_to_imgbb(bot)
        guides_stats = await migrate_guides_to_imgbb(bot)
        
        total = cards_stats["migrated"] + guides_stats["migrated"]
        failed = cards_stats["failed"] + guides_stats["failed"]
        
        if total > 0:
            logging.info(f"📤 ImgBB migration complete: {total} uploaded, {failed} failed")
        
    except Exception as e:
        logging.error(f"Migration error: {e}")


# --- Standalone CLI support ---

async def main():
    """Run migration as standalone script."""
    from data.config import TOKEN, IMGBB_API_KEY
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    
    if not TOKEN:
        logging.error("BOT_TOKEN not set in environment!")
        return False
    
    if not IMGBB_API_KEY:
        logging.error("IMGBB_API_KEY not set in environment!")
        return False
    
    from aiogram import Bot
    
    bot = Bot(token=TOKEN)
    
    try:
        await migrate_all_to_imgbb(bot)
        return True
    except Exception as e:
        logging.error(f"Migration failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        await bot.session.close()


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
