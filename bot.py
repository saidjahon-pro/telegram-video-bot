import os
import logging
import json
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Updater, CommandHandler, MessageHandler, CallbackQueryHandler, Filters
import yt_dlp
from queue import Queue
from threading import Thread
import time
import requests
import re

# ================= LOGGING =================
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ================= LOCK (CONFLICT FIX) =================
LOCK_FILE = "/tmp/telegram_bot.lock"

# ================= CONFIG =================
ADMIN_ID = int(os.environ.get('ADMIN_ID', '0'))
BOT_TOKEN = os.environ.get('BOT_TOKEN')

# ================= STATS =================
stats = {
    'total_users': set(),
    'total_downloads': 0,
    'today_downloads': 0,
    'active_users_today': set(),
    'last_reset': datetime.now().date()
}

# ================= QUEUE =================
download_queue = Queue(maxsize=100)
active_downloads = 0
MAX_CONCURRENT_DOWNLOADS = 3

# ================= CHANNELS =================
REQUIRED_CHANNELS = [
    {"name": "Muallim GPT", "username": "@muallim_gpt", "url": "https://t.me/muallim_gpt"},
    {"name": "Meta Bilim", "username": "@meta_bilim", "url": "https://t.me/meta_bilim"}
]

def load_channels():
    global REQUIRED_CHANNELS
    if os.path.exists('channels.json'):
        try:
            with open('channels.json', 'r', encoding='utf-8') as f:
                REQUIRED_CHANNELS = json.load(f)
        except:
            pass

def save_channels():
    with open('channels.json', 'w', encoding='utf-8') as f:
        json.dump(REQUIRED_CHANNELS, f, indent=2, ensure_ascii=False)

def reset_daily_stats():
    today = datetime.now().date()
    if stats['last_reset'] != today:
        stats['today_downloads'] = 0
        stats['active_users_today'] = set()
        stats['last_reset'] = today

# ================= TRANSLATIONS =================
TRANSLATIONS = {
    'uz': {
        'welcome': "🎬 Video Yuklovchi Bot\n\nLink yuboring",
        'send_link': "📎 Video linkini yuboring",
        'not_subscribed': "❌ Kanalga obuna bo'lmadingiz:\n\n",
        'subscribe_button': "✅ Obuna bo'ldim",
        'downloading': "⬇️ Yuklanmoqda...",
        'in_queue': "⏳ Navbat: {position}. Kutish: ~{time} daq.",
        'success': "✅ Tayyor!",
        'error': "❌ Xatolik.",
        'invalid_link': "❌ Noto'g'ri link."
    }
}

user_languages = {}
user_data = {}

def get_text(user_id, key, **kwargs):
    lang = user_languages.get(user_id, 'uz')
    text = TRANSLATIONS[lang][key]
    return text.format(**kwargs) if kwargs else text

def is_admin(user_id):
    return user_id == ADMIN_ID

# ================= SNAP SAVE =================
def download_with_snapsave(url):
    try:
        r = requests.post(
            "https://snapsave.app/api/ajaxSearch",
            headers={"User-Agent": "Mozilla/5.0"},
            data={"q": url, "lang": "en"},
            timeout=30
        )
        if r.status_code != 200:
            return None
        html = r.json().get('data', '')
        links = re.findall(r'href="(https?://[^"]+\.mp4[^"]*)"', html)
        return links[0] if links else None
    except:
        return None

# ================= DOWNLOAD =================
def download_video(url):
    try:
        if any(x in url for x in ['instagram', 'facebook', 'tiktok']):
            video_url = download_with_snapsave(url)
            if not video_url:
                return None
            filename = f"downloads/{int(time.time())}.mp4"
            r = requests.get(video_url, stream=True, timeout=60)
            with open(filename, 'wb') as f:
                for c in r.iter_content(8192):
                    if c:
                        f.write(c)
            return filename
        else:
            ydl_opts = {'outtmpl': 'downloads/%(id)s.%(ext)s', 'quiet': True}
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                return ydl.prepare_filename(info)
    except:
        return None

# ================= QUEUE WORKER =================
def process_queue_worker(bot):
    global active_downloads
    while True:
        if not download_queue.empty() and active_downloads < MAX_CONCURRENT_DOWNLOADS:
            task = download_queue.get()
            active_downloads += 1
            try:
                process_download_task(task, bot)
            finally:
                active_downloads -= 1
                download_queue.task_done()
        time.sleep(1)

def process_download_task(task, bot):
    update, url, status_msg, user_id = task
    video_path = download_video(url)
    if not video_path:
        bot.edit_message_text(
            chat_id=update.effective_chat.id,
            message_id=status_msg.message_id,
            text=get_text(user_id, 'error')
        )
        return

    with open(video_path, 'rb') as v:
        bot.send_video(
            chat_id=update.effective_chat.id,
            video=v,
            caption=get_text(user_id, 'success')
        )

    os.remove(video_path)
    bot.delete_message(update.effective_chat.id, status_msg.message_id)

# ================= HANDLERS =================
def start(update, context):
    stats['total_users'].add(update.effective_user.id)
    update.message.reply_text(get_text(update.effective_user.id, 'send_link'))

def handle_message(update, context):
    user_id = update.effective_user.id
    text = update.message.text

    if not text.startswith("http"):
        update.message.reply_text(get_text(user_id, 'invalid_link'))
        return

    status = update.message.reply_text(get_text(user_id, 'downloading'))
    download_queue.put((update, text, status, user_id))

def error_handler(update, context):
    logger.error(context.error)

# ================= MAIN =================
def main():
    if os.path.exists(LOCK_FILE):
        logger.error("Bot allaqachon ishlayapti")
        return

    with open(LOCK_FILE, "w") as f:
        f.write(str(os.getpid()))

    os.makedirs('downloads', exist_ok=True)
    load_channels()

    updater = Updater(BOT_TOKEN, use_context=True)
    bot = updater.bot
    dp = updater.dispatcher

    Thread(target=process_queue_worker, args=(bot,), daemon=True).start()

    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_message))
    dp.add_error_handler(error_handler)

    updater.start_polling(drop_pending_updates=True, timeout=30, read_latency=5)
    updater.idle()

    if os.path.exists(LOCK_FILE):
        os.remove(LOCK_FILE)

if __name__ == "__main__":
    main()
