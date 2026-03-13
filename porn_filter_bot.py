"""
Telegram Porn Filter Bot — Groq AI Powered
==========================================
Yeh bot automatically pornographic images detect karke delete karta hai!

Requirements:
pip install python-telegram-bot groq aiohttp

Setup:
1. TELEGRAM_BOT_TOKEN = BotFather se lo
2. GROQ_API_KEY = console.groq.com se lo
3. Bot ko group mein add karo aur Admin banao
"""

import os
import base64
import asyncio
import aiohttp
import logging
from telegram import Update, Message
from telegram.ext import (
    Application, MessageHandler, filters,
    ContextTypes, CommandHandler
)
from groq import Groq

# ── CONFIGURATION ──────────────────────────────────────


TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
# Warn limit — kitni warnings ke baad ban
WARN_LIMIT = 2

# ── LOGGING ────────────────────────────────────────────
logging.basicConfig(
    format="%(asctime)s — %(name)s — %(levelname)s — %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ── GROQ CLIENT ────────────────────────────────────────
groq_client = Groq(api_key=GROQ_API_KEY)

# ── WARN TRACKER (In-memory) ───────────────────────────
# Format: {chat_id: {user_id: warn_count}}
warns = {}

# ── IMAGE DOWNLOAD ─────────────────────────────────────
async def download_image(file_url: str) -> str:
    """Image download karke base64 mein convert karo"""
    async with aiohttp.ClientSession() as session:
        async with session.get(file_url) as resp:
            image_data = await resp.read()
            return base64.b64encode(image_data).decode("utf-8")

# ── GROQ AI IMAGE CHECK ────────────────────────────────
def check_image_with_groq(base64_image: str) -> bool:
    """
    Groq AI se check karo — image pornographic hai ya nahi
    Returns: True = porn detected, False = safe
    """
    try:
        response = groq_client.chat.completions.create(
            model="meta-llama/llama-4-scout-17b-16e-instruct",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{base64_image}"
                            }
                        },
                        {
                            "type": "text",
                            "text": """Analyze this image strictly for content moderation.

Answer ONLY with one word:
- "UNSAFE" if the image contains: nudity, explicit sexual content, pornographic material, genitals, sexual acts
- "SAFE" if the image is normal/appropriate

Single word answer only: SAFE or UNSAFE"""
                        }
                    ]
                }
            ],
            max_tokens=10,
            temperature=0
        )

        answer = response.choices[0].message.content.strip().upper()
        logger.info(f"Groq response: {answer}")
        return "UNSAFE" in answer

    except Exception as e:
        logger.error(f"Groq API error: {e}")
        return False  # Error pe safe assume karo

# ── WARN SYSTEM ────────────────────────────────────────
def add_warn(chat_id: int, user_id: int) -> int:
    """Warning add karo aur current count return karo"""
    if chat_id not in warns:
        warns[chat_id] = {}
    if user_id not in warns[chat_id]:
        warns[chat_id][user_id] = 0
    warns[chat_id][user_id] += 1
    return warns[chat_id][user_id]

def get_warns(chat_id: int, user_id: int) -> int:
    """Current warn count get karo"""
    return warns.get(chat_id, {}).get(user_id, 0)

def reset_warns(chat_id: int, user_id: int):
    """Warns reset karo"""
    if chat_id in warns and user_id in warns[chat_id]:
        warns[chat_id][user_id] = 0

# ── PHOTO HANDLER ──────────────────────────────────────
async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Har photo ko scan karo"""
    message: Message = update.message
    if not message or not message.photo:
        return

    chat_id   = message.chat_id
    user_id   = message.from_user.id
    user_name = message.from_user.first_name or "User"
    username  = f"@{message.from_user.username}" if message.from_user.username else user_name

    try:
        # Best quality photo lo
        photo = message.photo[-1]
        file  = await context.bot.get_file(photo.file_id)

        # Download aur base64 convert
        logger.info(f"Scanning image from {username} in chat {chat_id}")
        b64_image = await download_image(file.file_path)

        # Groq AI se check karo
        is_porn = check_image_with_groq(b64_image)

        if is_porn:
            # ── Delete karo
            await message.delete()
            logger.warning(f"Porn detected! Deleted from {username}")

            # ── Warn do
            warn_count = add_warn(chat_id, user_id)

            if warn_count >= WARN_LIMIT:
                # Ban karo
                await context.bot.ban_chat_member(chat_id, user_id)
                reset_warns(chat_id, user_id)
                await context.bot.send_message(
                    chat_id,
                    f"🚫 {username} ko ban kar diya gaya!\n"
                    f"Reason: Repeatedly sharing explicit content.\n"
                    f"({warn_count}/{WARN_LIMIT} warnings)"
                )
                logger.warning(f"Banned {username} ({user_id})")
            else:
                # Warn message bhejo
                warn_msg = await context.bot.send_message(
                    chat_id,
                    f"⚠️ {username} — Warning {warn_count}/{WARN_LIMIT}\n"
                    f"Explicit content allowed nahi hai!\n"
                    f"{'Agli baar ban ho jaoge! 🚫' if warn_count == WARN_LIMIT - 1 else ''}"
                )
                # 10 second baad warn message bhi delete karo
                await asyncio.sleep(10)
                await warn_msg.delete()

        else:
            logger.info(f"Image safe from {username}")

    except Exception as e:
        logger.error(f"Error handling photo: {e}")

# ── VIDEO HANDLER ──────────────────────────────────────
async def handle_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Videos ke liye thumbnail check karo"""
    message: Message = update.message
    if not message:
        return

    # Video thumbnail hai toh check karo
    video = message.video or message.document
    if not video:
        return

    user_name = message.from_user.first_name or "User"
    username  = f"@{message.from_user.username}" if message.from_user.username else user_name
    chat_id   = message.chat_id
    user_id   = message.from_user.id

    try:
        # Thumbnail check karo agar available hai
        thumb = None
        if hasattr(video, 'thumbnail') and video.thumbnail:
            thumb = video.thumbnail
        elif hasattr(video, 'thumb') and video.thumb:
            thumb = video.thumb

        if thumb:
            file      = await context.bot.get_file(thumb.file_id)
            b64_image = await download_image(file.file_path)
            is_porn   = check_image_with_groq(b64_image)

            if is_porn:
                await message.delete()
                warn_count = add_warn(chat_id, user_id)

                if warn_count >= WARN_LIMIT:
                    await context.bot.ban_chat_member(chat_id, user_id)
                    reset_warns(chat_id, user_id)
                    await context.bot.send_message(
                        chat_id,
                        f"🚫 {username} ban! Explicit video sharing not allowed!"
                    )
                else:
                    warn_msg = await context.bot.send_message(
                        chat_id,
                        f"⚠️ {username} — Warning {warn_count}/{WARN_LIMIT}\n"
                        f"Explicit videos allowed nahi hain!"
                    )
                    await asyncio.sleep(10)
                    await warn_msg.delete()

    except Exception as e:
        logger.error(f"Error handling video: {e}")

# ── COMMANDS ───────────────────────────────────────────
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Bot start karo"""
    await update.message.reply_text(
        "🛡️ Porn Filter Bot Active!\n\n"
        "Main automatically explicit content scan karta hun aur delete karta hun.\n\n"
        "Commands:\n"
        "/warns @username — Warnings check karo\n"
        "/resetwarns @username — Warns reset karo (admin only)\n"
        "/status — Bot status check karo"
    )

async def warns_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Kisi ki warnings check karo"""
    if update.message.reply_to_message:
        user    = update.message.reply_to_message.from_user
        chat_id = update.message.chat_id
        count   = get_warns(chat_id, user.id)
        await update.message.reply_text(
            f"⚠️ {user.first_name} ke warnings: {count}/{WARN_LIMIT}"
        )
    else:
        await update.message.reply_text(
            "Kisi ke message pe reply karke /warns likho!"
        )

async def resetwarns_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Warns reset karo — sirf admin kar sakta hai"""
    # Admin check
    chat_id = update.message.chat_id
    user_id = update.message.from_user.id
    member  = await context.bot.get_chat_member(chat_id, user_id)

    if member.status not in ["administrator", "creator"]:
        await update.message.reply_text("❌ Sirf admins yeh kar sakte hain!")
        return

    if update.message.reply_to_message:
        target = update.message.reply_to_message.from_user
        reset_warns(chat_id, target.id)
        await update.message.reply_text(
            f"✅ {target.first_name} ke warns reset ho gaye!"
        )

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Bot status"""
    await update.message.reply_text(
        "✅ Bot Active!\n"
        "🤖 Groq AI: Connected\n"
        "🛡️ Image Filter: ON\n"
        "📹 Video Filter: ON\n"
        f"⚠️ Warn Limit: {WARN_LIMIT}"
    )

# ── MAIN ───────────────────────────────────────────────
def main():
    """Bot start karo"""
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # Handlers
    app.add_handler(CommandHandler("start",      start_command))
    app.add_handler(CommandHandler("warns",      warns_command))
    app.add_handler(CommandHandler("resetwarns", resetwarns_command))
    app.add_handler(CommandHandler("status",     status_command))

    # Photo + Video handlers
    app.add_handler(MessageHandler(filters.PHOTO,    handle_photo))
    app.add_handler(MessageHandler(filters.VIDEO,    handle_video))
    app.add_handler(MessageHandler(filters.Document.VIDEO, handle_video))

    logger.info("🚀 Porn Filter Bot Starting...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
