import os
import logging
import json
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Updater, CommandHandler, MessageHandler, CallbackQueryHandler, Filters, CallbackContext
import yt_dlp
from typing import Optional
from queue import Queue
from threading import Thread
import time

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

ADMIN_ID = int(os.environ.get('ADMIN_ID', '0'))

stats = {
    'total_users': set(),
    'total_downloads': 0,
    'today_downloads': 0,
    'active_users_today': set(),
    'last_reset': datetime.now().date()
}

download_queue = Queue(maxsize=100)
active_downloads = 0
MAX_CONCURRENT_DOWNLOADS = 3

REQUIRED_CHANNELS = [
    {"name": "Muallim GPT", "username": "@muallim_gpt", "url": "https://t.me/muallim_gpt"},
    {"name": "Meta Bilim", "username": "@meta_bilim", "url": "https://t.me/meta_bilim"}
]

def load_channels():
    global REQUIRED_CHANNELS
    try:
        if os.path.exists('channels.json'):
            with open('channels.json', 'r', encoding='utf-8') as f:
                REQUIRED_CHANNELS = json.load(f)
    except:
        pass

def save_channels():
    try:
        with open('channels.json', 'w', encoding='utf-8') as f:
            json.dump(REQUIRED_CHANNELS, f, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.error(f"Save error: {e}")

def reset_daily_stats():
    today = datetime.now().date()
    if stats['last_reset'] != today:
        stats['today_downloads'] = 0
        stats['active_users_today'] = set()
        stats['last_reset'] = today

TRANSLATIONS = {
    'uz': {
        'welcome': "🎬 Video Yuklovchi Bot\n\nInstagram, TikTok, YouTube va boshqa platformalardan video yuklab oling.\n\nTilni tanlang:",
        'send_link': "📎 Video linkini yuboring\n\nQollab-quvvatlanadigan:\nInstagram, Facebook, TikTok, YouTube, Pinterest, Twitter",
        'not_subscribed': "❌ Kanalga obuna bo'lmadingiz:\n\n",
        'subscribe_button': "✅ Obuna bo'ldim",
        'downloading': "⬇️ Yuklanmoqda...",
        'in_queue': "⏳ Navbat: {position}. Kutish: ~{time} daq.",
        'success': "✅ Tayyor!",
        'error': "❌ Xatolik.",
        'invalid_link': "❌ Noto'g'ri link.",
        'uzbek': "🇺🇿 O'zbek",
        'russian': "🇷🇺 Русский",
        'english': "🇬🇧 English"
    },
    'ru': {
        'welcome': "🎬 Бот для скачивания видео\n\nСкачивайте с Instagram, TikTok, YouTube.\n\nВыберите язык:",
        'send_link': "📎 Отправьте ссылку\n\nПоддерживается:\nInstagram, Facebook, TikTok, YouTube, Pinterest, Twitter",
        'not_subscribed': "❌ Не подписаны:\n\n",
        'subscribe_button': "✅ Подписался",
        'downloading': "⬇️ Загрузка...",
        'in_queue': "⏳ Очередь: {position}. Ожидание: ~{time} мин.",
        'success': "✅ Готово!",
        'error': "❌ Ошибка.",
        'invalid_link': "❌ Неверная ссылка.",
        'uzbek': "🇺🇿 O'zbek",
        'russian': "🇷🇺 Русский",
        'english': "🇬🇧 English"
    },
    'en': {
        'welcome': "🎬 Video Downloader Bot\n\nDownload from Instagram, TikTok, YouTube.\n\nChoose language:",
        'send_link': "📎 Send link\n\nSupported:\nInstagram, Facebook, TikTok, YouTube, Pinterest, Twitter",
        'not_subscribed': "❌ Not subscribed:\n\n",
        'subscribe_button': "✅ Subscribed",
        'downloading': "⬇️ Downloading...",
        'in_queue': "⏳ Queue: {position}. Wait: ~{time} min.",
        'success': "✅ Done!",
        'error': "❌ Error.",
        'invalid_link': "❌ Invalid link.",
        'uzbek': "🇺🇿 O'zbek",
        'russian': "🇷🇺 Русский",
        'english': "🇬🇧 English"
    }
}

user_languages = {}
user_data = {}

def get_text(user_id, key, **kwargs):
    lang = user_languages.get(user_id, 'uz')
    text = TRANSLATIONS[lang].get(key, TRANSLATIONS['uz'][key])
    return text.format(**kwargs) if kwargs else text

def is_admin(user_id):
    return user_id == ADMIN_ID

def admin_panel(update, context):
    if not is_admin(update.effective_user.id):
        update.message.reply_text("❌ Ruxsat yo'q!")
        return
    
    reset_daily_stats()
    
    text = f"👑 ADMIN PANEL\n\n📊 Statistika:\nJami: {len(stats['total_users'])}\nBugungi: {len(stats['active_users_today'])}\nYuklanganlar: {stats['total_downloads']}\nBugungi: {stats['today_downloads']}\n\n⚙️ Tizim:\nNavbat: {download_queue.qsize()}/100\nFaol: {active_downloads}/{MAX_CONCURRENT_DOWNLOADS}\nKanallar: {len(REQUIRED_CHANNELS)}\n\n📅 {datetime.now().strftime('%d.%m.%Y %H:%M')}"
    
    keyboard = [
        [InlineKeyboardButton("📢 Broadcast", callback_data='admin_broadcast')],
        [InlineKeyboardButton("➕ Kanal qo'shish", callback_data='admin_add_channel')],
        [InlineKeyboardButton("➖ Kanal o'chirish", callback_data='admin_remove_channel')],
        [InlineKeyboardButton("📋 Kanallar", callback_data='admin_list_channels')],
        [InlineKeyboardButton("🔄 Yangilash", callback_data='admin_refresh')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    update.message.reply_text(text, reply_markup=reply_markup)

def admin_callback(update, context):
    query = update.callback_query
    query.answer()
    
    if not is_admin(query.from_user.id):
        query.answer("❌ Ruxsat yo'q!", show_alert=True)
        return
    
    data = query.data
    
    if data == 'admin_refresh':
        reset_daily_stats()
        text = f"👑 ADMIN PANEL\n\n📊 Statistika:\nJami: {len(stats['total_users'])}\nBugungi: {len(stats['active_users_today'])}\nYuklanganlar: {stats['total_downloads']}\nBugungi: {stats['today_downloads']}\n\n⚙️ Tizim:\nNavbat: {download_queue.qsize()}/100\nFaol: {active_downloads}/{MAX_CONCURRENT_DOWNLOADS}\nKanallar: {len(REQUIRED_CHANNELS)}\n\n📅 {datetime.now().strftime('%d.%m.%Y %H:%M')}"
        
        keyboard = [
            [InlineKeyboardButton("📢 Broadcast", callback_data='admin_broadcast')],
            [InlineKeyboardButton("➕ Kanal qo'shish", callback_data='admin_add_channel')],
            [InlineKeyboardButton("➖ Kanal o'chirish", callback_data='admin_remove_channel')],
            [InlineKeyboardButton("📋 Kanallar", callback_data='admin_list_channels')],
            [InlineKeyboardButton("🔄 Yangilash", callback_data='admin_refresh')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        query.edit_message_text(text, reply_markup=reply_markup)
    
    elif data == 'admin_broadcast':
        query.edit_message_text("📢 Keyingi xabaringizni yuboring")
        user_data[query.from_user.id] = {'waiting_broadcast': True}
    
    elif data == 'admin_list_channels':
        text = "📋 Kanallar:\n\n"
        for i, ch in enumerate(REQUIRED_CHANNELS, 1):
            text += f"{i}. {ch['name']} - {ch['username']}\n"
        query.edit_message_text(text)
    
    elif data == 'admin_add_channel':
        query.edit_message_text("➕ Format:\nNom | @username | https://t.me/username")
        user_data[query.from_user.id] = {'waiting_add_channel': True}
    
    elif data == 'admin_remove_channel':
        if not REQUIRED_CHANNELS:
            query.answer("Kanallar yo'q!", show_alert=True)
            return
        
        keyboard = []
        for i, ch in enumerate(REQUIRED_CHANNELS):
            keyboard.append([InlineKeyboardButton(f"❌ {ch['name']}", callback_data=f'remove_ch_{i}')])
        keyboard.append([InlineKeyboardButton("◀️ Orqaga", callback_data='admin_refresh')])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        query.edit_message_text("➖ Tanlang:", reply_markup=reply_markup)
    
    elif data.startswith('remove_ch_'):
        idx = int(data.split('_')[2])
        if 0 <= idx < len(REQUIRED_CHANNELS):
            removed = REQUIRED_CHANNELS.pop(idx)
            save_channels()
            query.answer(f"✅ {removed['name']} o'chirildi!", show_alert=True)
            admin_callback(update, context)

def handle_admin_message(update, context):
    if not is_admin(update.effective_user.id):
        return False
    
    user_id = update.effective_user.id
    
    if user_data.get(user_id, {}).get('waiting_broadcast'):
        user_data[user_id] = {}
        text = update.message.text
        update.message.reply_text("📤 Yuborilmoqda...")
        
        success = 0
        failed = 0
        for uid in stats['total_users']:
            try:
                context.bot.send_message(chat_id=uid, text=text)
                success += 1
            except:
                failed += 1
        
        update.message.reply_text(f"✅ Yuborildi!\n\nMuvaffaqiyatli: {success}\nXatolik: {failed}")
        return True
    
    if user_data.get(user_id, {}).get('waiting_add_channel'):
        user_data[user_id] = {}
        
        try:
            parts = update.message.text.split('|')
            if len(parts) != 3:
                update.message.reply_text("❌ Noto'g'ri format!")
                return True
            
            name = parts[0].strip()
            username = parts[1].strip()
            url = parts[2].strip()
            
            REQUIRED_CHANNELS.append({"name": name, "username": username, "url": url})
            save_channels()
            update.message.reply_text(f"✅ {name} qo'shildi!")
        except Exception as e:
            update.message.reply_text(f"❌ Xatolik: {e}")
        return True
    
    return False

def check_subscription(update, context):
    user_id = update.effective_user.id
    for channel in REQUIRED_CHANNELS:
        try:
            member = context.bot.get_chat_member(channel['username'], user_id)
            if member.status not in ['member', 'administrator', 'creator']:
                return False
        except:
            return False
    return True

def start(update, context):
    user_id = update.effective_user.id
    stats['total_users'].add(user_id)
    
    keyboard = [
        [InlineKeyboardButton(TRANSLATIONS['uz']['uzbek'], callback_data='lang_uz')],
        [InlineKeyboardButton(TRANSLATIONS['ru']['russian'], callback_data='lang_ru')],
        [InlineKeyboardButton(TRANSLATIONS['en']['english'], callback_data='lang_en')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    update.message.reply_text(TRANSLATIONS['uz']['welcome'], reply_markup=reply_markup)

def language_callback(update, context):
    query = update.callback_query
    query.answer()
    user_id = query.from_user.id
    lang = query.data.split('_')[1]
    user_languages[user_id] = lang
    query.edit_message_text(text=get_text(user_id, 'send_link'))

def show_subscription_message(update, context):
    user_id = update.effective_user.id
    message = get_text(user_id, 'not_subscribed')
    for i, channel in enumerate(REQUIRED_CHANNELS, 1):
        message += f"{i}. [{channel['name']}]({channel['url']})\n"
    keyboard = [[InlineKeyboardButton(get_text(user_id, 'subscribe_button'), callback_data='check_subscription')]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    update.message.reply_text(message, reply_markup=reply_markup, parse_mode='Markdown', disable_web_page_preview=True)

def check_subscription_callback(update, context):
    query = update.callback_query
    user_id = query.from_user.id
    query.answer()
    if check_subscription(update, context):
        query.edit_message_text(text=get_text(user_id, 'send_link'))
    else:
        query.answer("❌ Obuna bo'lmadingiz!", show_alert=True)

import requests
import re
import time

def download_with_snapsave(url):
    """SnapSave API orqali video yuklab olish"""
    try:
        api_url = "https://snapsave.app/api/ajaxSearch"
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'application/json',
            'Content-Type': 'application/x-www-form-urlencoded'
        }
        
        data = {
            'q': url,
            'lang': 'en'
        }
        
        response = requests.post(api_url, headers=headers, data=data, timeout=30)
        
        if response.status_code != 200:
            return None
            
        result = response.json()
        html = result.get('data', '')
        
        # Video linkni topish
        video_urls = re.findall(r'href="(https?://[^"]+\.mp4[^"]*)"', html)
        
        if video_urls:
            return video_urls[0]
        
        return None
        
    except Exception as e:
        logger.error(f"SnapSave error: {e}")
        return None

def download_video(url):
    try:
        # Instagram, Facebook, TikTok uchun SnapSave
        if any(domain in url for domain in ['instagram.com', 'instagr.am', 'facebook.com', 'fb.watch', 'tiktok.com']):
            video_url = download_with_snapsave(url)
            
            if video_url:
                response = requests.get(video_url, stream=True, timeout=60)
                
                if response.status_code != 200:
                    return None
                
                filename = f"downloads/{int(time.time())}.mp4"
                
                with open(filename, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                
                return filename
            
            return None
        
        # Boshqa platformalar uchun yt-dlp
        else:
            ydl_opts = {
                'format': 'best',
                'outtmpl': 'downloads/%(id)s.%(ext)s',
                'quiet': True,
                'no_warnings': True,
            }
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                filename = ydl.prepare_filename(info)
                return filename
    
    except Exception as e:
        logger.error(f"Download error: {e}")
        return None

def process_queue_worker(context):
    global active_downloads
    while True:
        if not download_queue.empty() and active_downloads < MAX_CONCURRENT_DOWNLOADS:
            task = download_queue.get()
            active_downloads += 1
            process_download_task(task, context)
            active_downloads -= 1
            download_queue.task_done()
        time.sleep(1)

def process_download_task(task, context):
    update, url, status_msg, user_id = task
    try:
        video_path = download_video(url)
        if not video_path:
            context.bot.edit_message_text(chat_id=update.effective_chat.id, message_id=status_msg.message_id, text=get_text(user_id, 'error'))
            return
        
        file_size = os.path.getsize(video_path)
        if file_size > 50 * 1024 * 1024:
            os.remove(video_path)
            context.bot.edit_message_text(chat_id=update.effective_chat.id, message_id=status_msg.message_id, text="❌ Video hajmi katta (>50MB)")
            return
        
        with open(video_path, 'rb') as video:
            context.bot.send_video(chat_id=update.effective_chat.id, video=video, caption=get_text(user_id, 'success'))
        
        os.remove(video_path)
        context.bot.delete_message(chat_id=update.effective_chat.id, message_id=status_msg.message_id)
        
        stats['total_downloads'] += 1
        stats['today_downloads'] += 1
        stats['active_users_today'].add(user_id)
        
    except Exception as e:
        logger.error(f"Error: {e}")
        try:
            context.bot.edit_message_text(chat_id=update.effective_chat.id, message_id=status_msg.message_id, text=get_text(user_id, 'error'))
        except:
            pass

def handle_message(update, context):
    user_id = update.effective_user.id
    
    if handle_admin_message(update, context):
        return
    
    text = update.message.text
    if user_id not in user_languages:
        user_languages[user_id] = 'uz'
    
    if not text.startswith(('http://', 'https://')):
        update.message.reply_text(get_text(user_id, 'invalid_link'))
        return
    
    # Instagram bloklanishi
    if 'instagram.com' in text or 'instagr.am' in text:
        lang = user_languages.get(user_id, 'uz')
        if lang == 'uz':
            msg = "⚠️ Instagram videolarini yuklab olish vaqtincha ishlamayapti.\n\nIltimos, TikTok, YouTube yoki boshqa platformadan foydalaning."
        elif lang == 'ru':
            msg = "⚠️ Загрузка из Instagram временно недоступна.\n\nИспользуйте TikTok, YouTube или другие платформы."
        else:
            msg = "⚠️ Instagram downloads are temporarily unavailable.\n\nPlease use TikTok, YouTube or other platforms."
        update.message.reply_text(msg)
        return
    
    if not check_subscription(update, context):
        show_subscription_message(update, context)
        return
    
    if download_queue.full():
        update.message.reply_text("⚠️ Navbat to'lgan")
        return
    
    queue_size = download_queue.qsize()
    if queue_size > 0:
        wait_time = (queue_size + 1) * 2
        status_msg = update.message.reply_text(get_text(user_id, 'in_queue', position=queue_size + 1, time=wait_time))
    else:
        status_msg = update.message.reply_text(get_text(user_id, 'downloading'))
    
    task = (update, text, status_msg, user_id)
    download_queue.put(task)

def error_handler(update, context):
    logger.error(f"Update {update} caused error {context.error}")

def main():
    os.makedirs('downloads', exist_ok=True)
    load_channels()
    
    token = os.environ.get('BOT_TOKEN')
    if not token:
        logger.error("BOT_TOKEN topilmadi!")
        return
    
    if ADMIN_ID == 0:
        logger.warning("ADMIN_ID sozlanmagan!")
    
    updater = Updater(token=token, use_context=True)
    dispatcher = updater.dispatcher
    
    queue_thread = Thread(target=process_queue_worker, args=(updater,), daemon=True)
    queue_thread.start()
    
    dispatcher.add_error_handler(error_handler)
    dispatcher.add_handler(CommandHandler("start", start))
    dispatcher.add_handler(CommandHandler("admin", admin_panel))
    dispatcher.add_handler(CallbackQueryHandler(language_callback, pattern='^lang_'))
    dispatcher.add_handler(CallbackQueryHandler(check_subscription_callback, pattern='^check_subscription$'))
    dispatcher.add_handler(CallbackQueryHandler(admin_callback, pattern='^admin_'))
    dispatcher.add_handler(CallbackQueryHandler(admin_callback, pattern='^remove_ch_'))
    dispatcher.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_message))
    
    logger.info("Bot ishga tushdi!")
    updater.start_polling(drop_pending_updates=True)
    updater.idle()

if __name__ == '__main__':
    main()
