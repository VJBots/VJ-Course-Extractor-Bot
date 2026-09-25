import logging
import re
from base64 import b64decode
from typing import Dict, Optional
from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad
from pyrogram import Client, filters
from pyrogram.types import Message
from pyromod.exceptions import ListenerTimeout

from config import auth_users

def is_authorized(user_id: int) -> bool:
    return bool(auth_users and user_id in auth_users)

async def ask_user(bot: Client, m: Message, editable: Message, text: str, user_id: int, timeout: int = 120) -> Optional[str]:
    await editable.edit(text)
    try:
        msg = await bot.listen(chat_id=m.chat.id, filters=filters.user(user_id), timeout=timeout)
        val = (msg.text or "").strip()
        try:
            await msg.delete(True)
        except Exception:
            pass
        return val
    except ListenerTimeout:
        await editable.edit("**Timeout! You took too long to respond.**")
        return None
    except Exception as e:
        logging.exception("Error during input listener:")
        await editable.edit(f"**Error:** `{e}`")
        return None

def extract_url_from_video_details(item: Dict) -> str:
    v_details = item.get("videoDetails") or {}
    url = (
        v_details.get("videoUrl") or v_details.get("embedCode") or v_details.get("mediaUrl") or
        v_details.get("streamUrl") or v_details.get("hlsUrl") or v_details.get("mpdUrl") or
        v_details.get("downloadUrl") or v_details.get("url") or v_details.get("fileUrl") or
        item.get("videoUrl") or item.get("mediaUrl") or item.get("streamUrl") or
        item.get("hlsUrl") or item.get("mpdUrl") or item.get("url") or ""
    )
    if url and ("<" in url or "iframe" in url.lower() or "src=" in url.lower()):
        match = re.search(r'src=["\'](https?://[^"\']+)["\']', url)
        if match:
            return match.group(1)
        match_any = re.search(r'https?://[^"\'\s<>]+', url)
        return match_any.group(0) if match_any else url
    return url

def appx_decrypt(enc: str) -> str:
    if not enc:
        return ""
    try:
        enc_bytes = b64decode(enc.split(":")[0])
        if not enc_bytes:
            return ""
        key = b"638udh3829162018"
        iv = b"fedcba9876543210"
        cipher = AES.new(key, AES.MODE_CBC, iv)
        return unpad(cipher.decrypt(enc_bytes), AES.block_size).decode("utf-8")
    except Exception:
        return ""
      
