import logging
import asyncio
import aiohttp
import os
from data.config import IMGBB_API_KEY


class ImgBBUploadError(Exception):
    """Raised when imgbb upload fails."""
    pass


async def upload_file_to_imgbb(file_path: str) -> str:
    """
    Upload a local image file to imgbb and return the public URL.
    
    Args:
        file_path: Path to the image file (jpg, png, gif, etc.)
        
    Returns:
        The public imgbb URL string
        
    Raises:
        ImgBBUploadError: If upload fails or API key is not set
    """
    if not IMGBB_API_KEY:
        raise ImgBBUploadError("IMGBB_API_KEY not set in environment variables")
    
    if not os.path.isfile(file_path):
        raise ImgBBUploadError(f"File not found: {file_path}")
    
    with open(file_path, "rb") as f:
        file_data = f.read()
    
    return await upload_bytes_to_imgbb(file_data, os.path.basename(file_path))


async def upload_bytes_to_imgbb(file_data: bytes, filename: str = "image.jpg") -> str:
    """
    Upload image bytes directly to imgbb and return the public URL.
    
    Args:
        file_data: Image binary data
        filename: Filename for the upload
        
    Returns:
        The public imgbb URL string
        
    Raises:
        ImgBBUploadError: If upload fails or API key is not set
    """
    if not IMGBB_API_KEY:
        raise ImgBBUploadError("IMGBB_API_KEY not set in environment variables")
    
    url = "https://api.imgbb.com/1/upload"
    
    try:
        # Upload to imgbb with retry logic
        for attempt in range(3):
            try:
                async with aiohttp.ClientSession() as session:
                    data = aiohttp.FormData()
                    data.add_field("key", IMGBB_API_KEY)
                    data.add_field("image", file_data, filename=filename)
                    data.add_field("expiration", "0")  # no expiration
                    
                    async with session.post(url, data=data, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                        if resp.status == 200:
                            result = await resp.json()
                            if result.get("success"):
                                imgbb_url = result["data"]["url"]
                                logging.info(f"Successfully uploaded to imgbb: {filename}")
                                return imgbb_url
                            else:
                                error_msg = result.get("error", {}).get("message", "Unknown error")
                                raise ImgBBUploadError(f"imgbb API error: {error_msg}")
                        else:
                            raise ImgBBUploadError(f"HTTP {resp.status}: {await resp.text()}")
                            
            except asyncio.TimeoutError:
                if attempt < 2:
                    logging.warning(f"imgbb upload timeout (attempt {attempt + 1}/3), retrying...")
                    await asyncio.sleep(2 ** attempt)  # exponential backoff
                else:
                    raise ImgBBUploadError("imgbb upload timeout after 3 attempts")
            except Exception as e:
                if attempt < 2:
                    logging.warning(f"imgbb upload attempt {attempt + 1} failed: {e}, retrying...")
                    await asyncio.sleep(2 ** attempt)
                else:
                    raise ImgBBUploadError(f"imgbb upload failed: {e}")
                    
    except ImgBBUploadError:
        raise
    except Exception as e:
        raise ImgBBUploadError(f"Unexpected error uploading to imgbb: {e}")


async def upload_file_by_telegram_download(
    bot,
    file_id: str,
    filename: str = "image.jpg"
) -> str:
    """
    Download an image from Telegram using file_id and upload directly to imgbb.
    No temporary files are created - streams directly to memory.
    
    Args:
        bot: Aiogram Bot instance
        file_id: Telegram file_id of the photo
        filename: Optional filename for the imgbb upload
        
    Returns:
        The public imgbb URL
        
    Raises:
        ImgBBUploadError: If download or upload fails
    """
    try:
        # Download from Telegram to memory
        file = await bot.get_file(file_id)
        file_bytes = await bot.download_file(file.file_path)
        
        # Upload bytes directly to imgbb (no temp file needed)
        imgbb_url = await upload_bytes_to_imgbb(file_bytes.read(), filename)
        
        return imgbb_url
        
    except Exception as e:
        raise ImgBBUploadError(f"Failed to upload telegram file: {e}")
