import logging
import os
import threading
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message
from pyromod import listen

from config import api_id, api_hash, bot_token
from one import register_pwwp_handlers
from two import register_cpwp_handlers
from three import register_appxwp_handlers

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")


# --- WEB HEALTH CHECK SERVER ---
def run_web():
    port = int(os.environ.get("PORT", 8080))
    try:
        from flask import Flask
        app = Flask(__name__)
        @app.route("/")
        def health():
            return "Bot running", 200
        app.run(host="0.0.0.0", port=port)
    except Exception:
        import http.server
        import socketserver
        handler = http.server.SimpleHTTPRequestHandler
        with socketserver.TCPServer(("", port), handler) as httpd:
            httpd.serve_forever()

threading.Thread(target=run_web, daemon=True).start()


# --- BOT CLIENT INITIALIZATION ---
bot = Client("techvjbot", api_id=api_id, api_hash=api_hash, bot_token=bot_token)


# --- COMMAND HANDLERS ---
@bot.on_message(filters.command(["start"]))
async def start(bot: Client, message: Message):
    await message.reply_text("**🎉 Bot Is Running... 🚀**\n\n**🧑‍💻 Use /help to see available extractors & instructions.**")

@bot.on_message(filters.command(["help"]))
async def help(bot: Client, message: Message):
    help_text = (
        "**📖 HOW THIS BOT WORKS & WHAT IT EXTRACTS 📖**\n\n"
        "<blockquote>This bot extracts course content (videos, PDFs, images, and notes) from supported education platforms and generates structured `.txt` files containing video streaming links and material URLs.</blockquote>\n\n"
        "--------------------------------------------------\n"
        "**🚀 1. Physics Wallah**\n"
        "<blockquote>• **Extracts:** Free preview batches & purchased batch content.</blockquote>\n"
        "<blockquote>• **How it works:** Requires your PW Auth Token or credentials to search, fetch, and list batch content & playable video stream URLs (`m3u8`).</blockquote>\n\n"
        "**📘 2. Classplus**\n"
        "<blockquote>• **Extracts:** Free store preview courses, unpurchased batch previews, & purchased courses.</blockquote>\n"
        "<blockquote>• **How it works:** Enter the app **ORG Code** + **Phone Number/OTP** or **Access Token**. It extracts video streams (`m3u8` / DRM / JW Player), notes (PDFs), and image assets.</blockquote>\n\n"
        "**📒 3. Appx**\n"
        "<blockquote>• **Extracts:** Free demo lectures, free course previews, & purchased user batches.</blockquote>\n"
        "<blockquote>• **How it works:** Works via Appx API using App Key/Token or User credentials to scrape full course folders recursively.</blockquote>\n"
        "--------------------------------------------------\n\n"
        "**👇 Choose your platform below to start extracting:**"
    )

    keyboard = [
        [InlineKeyboardButton("🚀 Physics Wallah 🚀", callback_data="pwwp")],
        [InlineKeyboardButton("📘 Classplus 📘", callback_data="cpwp")],
        [InlineKeyboardButton("📒 Appx 📒", callback_data="appxwp")]
    ]
    await message.reply_text(help_text, reply_markup=InlineKeyboardMarkup(keyboard))


# --- REGISTER ENGINE HANDLERS ---
register_pwwp_handlers(bot)
register_cpwp_handlers(bot)
register_appxwp_handlers(bot)


if __name__ == "__main__":
    bot.run()
