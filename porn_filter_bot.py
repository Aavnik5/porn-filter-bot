"""
Telegram Porn Filter Bot — Groq AI Powered
Fixed for Python 3.14
"""

import os
import base64
import asyncio
import aiohttp
import logging
import sys
from telegram import Update
from telegram.ext import (
    Application, MessageHandler, filters,
    ContextTypes, CommandHandler
)
from groq import Groq

# ── CONFIG ─────────────────────────────────────────────
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "YOUR_TOKEN")
GROQ_API_KEY       = os.environ.get("GROQ_API_KEY", "YOUR_GROQ_KEY")
WARN_LIMIT         = 2

logging.basicConfig(format="%(asctime)s — %(levelname)s — %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

groq_client = Groq(api_key=GROQ_API_KEY)
warns = {}

async def download_image(file_url: str) -> str:
    async with aiohttp.ClientSession() as session:
        async with session.get(file_url) as resp:
            return base64.b64encode(await resp.read()).decode("utf-8")

def check_image_with_groq(b64: str) -> bool:
    try:
        res = groq_client.chat.completions.create(
            model="meta-llama/llama-4-scout-17b-16e-instruct",
            messages=[{"role": "user", "content": [
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
                {"type": "text", "text": "Is this pornographic? Answer only SAFE or UNSAFE"}
            ]}],
            max_tokens=10, temperature=0
        )
        ans = res.choices[0].message.content.strip().upper()
        logger.info(f"Groq: {ans}")
        return "UNSAFE" in ans
    except Exception as e:
        logger.error(f"Groq error: {e}")
        return False

def add_warn(cid, uid):
    warns.setdefault(cid, {}).setdefault(uid, 0)
    warns[cid][uid] += 1
    return warns[cid][uid]

def get_warns(cid, uid):
    return warns.get(cid, {}).get(uid, 0)

def reset_warns(cid, uid):
    if cid in warns:
        warns[cid][uid] = 0

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg or not msg.photo:
        return
    cid = msg.chat_id
    uid = msg.from_user.id
    uname = f"@{msg.from_user.username}" if msg.from_user.username else msg.from_user.first_name
    try:
        f = await context.bot.get_file(msg.photo[-1].file_id)
        is_porn = check_image_with_groq(await download_image(f.file_path))
        if is_porn:
            await msg.delete()
            wc = add_warn(cid, uid)
            if wc >= WARN_LIMIT:
                await context.bot.ban_chat_member(cid, uid)
                reset_warns(cid, uid)
                await context.bot.send_message(cid, f"🚫 {uname} ban! Explicit content ({wc}/{WARN_LIMIT})")
            else:
                wm = await context.bot.send_message(cid, f"⚠️ {uname} Warning {wc}/{WARN_LIMIT} — Explicit content!")
                await asyncio.sleep(10)
                try: await wm.delete()
                except: pass
    except Exception as e:
        logger.error(f"Photo err: {e}")

async def handle_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg: return
    cid = msg.chat_id
    uid = msg.from_user.id
    uname = f"@{msg.from_user.username}" if msg.from_user.username else msg.from_user.first_name
    try:
        video = msg.video or msg.document
        if not video: return
        thumb = getattr(video, 'thumbnail', None) or getattr(video, 'thumb', None)
        if not thumb: return
        f = await context.bot.get_file(thumb.file_id)
        is_porn = check_image_with_groq(await download_image(f.file_path))
        if is_porn:
            await msg.delete()
            wc = add_warn(cid, uid)
            if wc >= WARN_LIMIT:
                await context.bot.ban_chat_member(cid, uid)
                reset_warns(cid, uid)
                await context.bot.send_message(cid, f"🚫 {uname} ban! Explicit video ({wc}/{WARN_LIMIT})")
            else:
                wm = await context.bot.send_message(cid, f"⚠️ {uname} Warning {wc}/{WARN_LIMIT} — Explicit video!")
                await asyncio.sleep(10)
                try: await wm.delete()
                except: pass
    except Exception as e:
        logger.error(f"Video err: {e}")

async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🛡️ Porn Filter Bot Active!\n/status — check karo")

async def status_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"✅ Active!\n🤖 Groq: ON\n⚠️ Warn Limit: {WARN_LIMIT}")

async def warns_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.reply_to_message:
        u = update.message.reply_to_message.from_user
        await update.message.reply_text(f"⚠️ {u.first_name}: {get_warns(update.message.chat_id, u.id)}/{WARN_LIMIT}")

async def resetwarns_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    m = await context.bot.get_chat_member(update.message.chat_id, update.message.from_user.id)
    if m.status not in ["administrator", "creator"]:
        return
    if update.message.reply_to_message:
        u = update.message.reply_to_message.from_user
        reset_warns(update.message.chat_id, u.id)
        await update.message.reply_text(f"✅ {u.first_name} warns reset!")

async def run_bot():
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("status", status_cmd))
    app.add_handler(CommandHandler("warns", warns_cmd))
    app.add_handler(CommandHandler("resetwarns", resetwarns_cmd))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.VIDEO, handle_video))
    app.add_handler(MessageHandler(filters.Document.VIDEO, handle_video))

    logger.info("🚀 Bot Starting...")
    await app.initialize()
    await app.start()
    await app.updater.start_polling(allowed_updates=Update.ALL_TYPES)
    await asyncio.Event().wait()

if __name__ == "__main__":
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(run_bot())
    finally:
        loop.close()
