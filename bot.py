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

# Admin ID
ADMIN_ID = int(os.environ.get('ADMIN_ID', '0'))

# Statistics
stats = {
    'total_users': set(),
    'total_downloads': 0,
    'today_downloads': 0,
    'active_users_today': set(),
    'last_reset': datetime.now().date()
}

# Queue
download_queue = Queue(maxsize=100)
active_downloads = 0
MAX_CONCURRENT_DOWNLOADS = 3

# Channels
REQUIRED_CHANNELS = [
    {"name": "Muallim GPT", "username": "@muallim_gpt", "url": "https://t.me/muallim_gpt"},
    {"name": "Meta Bilim", "username": "@meta_bilim", "url": "https://t.me/meta_bilim"}
]

def load_channels():
    global REQUIRED_CHANNELS
    try:
        if os.path.exists('channels.json'):
            with open('channels.json', 'r') as f:
                REQUIRED_CHANNELS = json.load(f)
    except:
        pass

def save_channels():
    try:
        with open('channels.json', 'w') as f:
            json.dump(REQUIRED_CHANNELS, f, indent=2)
    except Exception as e:
        logger.error(f"Save channels error: {e}")

def reset_daily_stats():
    today = datetime.now().date()
    if stats['last_reset'] != today:
        stats['today_downloads'] = 0
        stats['active_users_today'] = set()
        stats['last_reset'] = today

TRANSLATIONS = {
    'uz': {
        'welcome': "🎬 Video Yuklovchi Botga xush kelibsiz!\n\nInstagram, Facebook, TikTok, YouTube videolarini yuklab olishingiz mumkin.\n\n📌 Tilni tanlang:",
        'send_link': "📎 Video linkini yuboring.\n\n✅ Qo'llab-quvvatlanadigan:\n• Instagram • Facebook • TikTok\n• YouTube • Pinterest • Twitter/X",
        'not_subscribed': "❌ Kanalga obuna bo'lmadingiz:\n\n",
        'subscribe_button': "✅ Obuna bo'ldim",
        'downloading': "⬇️ Yuklanmoqda...",
        'in_queue': "⏳ Navbat: {position}. ~{time} daq.",
        'success': "✅ Tayyor!",
        'error': "❌ Xatolik.",
        'invalid_link': "❌ Noto'g'ri link.",
        'uzbek': "🇺🇿 O'zbek",
        'russian': "🇷🇺 Русский",
        'english': "🇬🇧 English"
    },
    'ru': {
        'welcome': "🎬 Добро пожаловать!\n\nСкачивайте видео.\n\n📌 Выберите язык:",
        'send_link': "📎 Отправьте ссылку.\n\n✅ Поддерживается:\n• Instagram • Facebook • TikTok\n• YouTube • Pinterest • Twitter/X",
        'not_subscribed': "❌ Не подписаны:\n\n",
        'subscribe_button': "✅ Подписался",
        'downloading': "⬇️ Загрузка...",
        'in_queue': "⏳ Очередь: {position}. ~{time} мин.",
        'success': "✅ Готово!",
        'error': "❌ Ошибка.",
        'invalid_link': "❌ Неверная ссылка.",
        'uzbek': "🇺🇿 O'zbek",
        'russian': "🇷🇺 Русский",
        'english': "🇬🇧 English"
    },
    'en': {
        'welcome': "🎬 Welcome!\n\nDownload videos.\n\n📌 Choose language:",
        'send_link': "📎 Send link.\n\n✅ Supported:\n• Instagram • Facebook • TikTok\n• YouTube • Pinterest • Twitter/X",
        'not_subscribed': "❌ Not subscribed:\n\n",
        'subscribe_button': "✅ Subscribed",
        'downloading': "⬇️ Downloading...",
        'in_queue': "⏳ Queue: {position}. ~{time} min.",
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

def get_text(user_id: int, key: str, **kwargs) -> str:
    lang = user_languages.get(user_id, 'uz')
    text = TRANSLATIONS[lang].get(key, TRANSLATIONS['uz'][key])
    return text.format(**kwargs) if kwargs else text

def is_admin(user_id: int) -> bool:
    return user_id == ADMIN_ID

def admin_panel(update: Update, context: CallbackContext) -> None:
    if not is_admin(update.effective_user.id):
        update.message.reply_text("❌ Sizda admin huquqi yo'q!")
        return
    
    reset_daily_stats()
    
    text = f"""👑 ADMIN PANEL

📊 Statistika:
├ Jami foydalanuvchilar: {len(stats['total_users'])}
├ Bugungi faol: {len(stats['active_users_today'])}
├ Jami yuklanganlar: {stats['total_downloads']}
└ Bugungi yuklanganlar: {stats['today_downloads']}

⚙️ Tizim:
├ Navbat: {download_queue.qsize()}/100
├ Faol yuklashlar: {active_downloads}/{MAX_CONCURRENT_DOWNLOADS}
└ Majburiy kanallar: {len(REQUIRED_CHANNELS)}

📅 {datetime.now().strftime('%d.%m.%Y %H:%M')}"""
    
    keyboard = [
        [InlineKeyboardButton("📢 Xabar yuborish", callback_data='admin_broadcast')],
        [InlineKeyboardButton("➕ Kanal qo'shish", callback_data='admin_add_channel')],
        [InlineKeyboardButton("➖ Kanal o'chirish", callback_data='admin_remove_channel')],
        [InlineKeyboardButton("📋 Kanallar ro'yxati", callback_data='admin_list_channels')],
        [InlineKeyboardButton("🔄 Yangilash", callback_data='admin_refresh')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    update.message.reply_text(text, reply_markup=reply_markup)

def admin_callback(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    query.answer()
    
    if not is_admin(query.from_user.id):
        query.answer("❌ Ruxsat yo'q!", show_alert=True)
        return
    
    data = query.data
    
    if data == 'admin_refresh':
        reset_daily_stats()
        text = f"""👑 ADMIN PANEL

📊 Statistika:
├ Jami: {len(stats['total_users'])}
├ Bugungi: {len(stats['active_users_today'])}
├ Yuklanganlar: {stats['total_downloads']}
└ Bugungi: {stats['today_downloads']}

⚙️ Tizim:
├ Navbat: {download_queue.qsize()}/100
├ Faol: {active_downloads}/{MAX_CONCURRENT_DOWNLOADS}
└ Kanallar: {len(REQUIRED_CHANNELS)}

📅 {datetime.now().strftime('%d.%m.%Y %H:%M')}"""
        
        keyboard = [
            [InlineKeyboardButton("📢 Xabar yuborish", callback_data='admin_broadcast')],
            [InlineKeyboardButton("➕ Kanal qo'shish", callback_data='admin_add_channel')],
            [InlineKeyboardButton("➖ Kanal o'chirish", callback_data='admin_remove_channel')],
            [InlineKeyboardButton("📋 Kanallar", callback_data='admin_list_channels')],
            [InlineKeyboardButton("🔄 Yangilash", callback_data='admin_refresh')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        query.edit_message_text(text, reply_markup=reply_markup)
    
    elif data == 'admin_broadcast':
        query.edit_message_text("📢 Keyingi xabaringizni yuboring, u barcha foydalanuvchilarga yuboriladi.")
        user_data[query.from_user.id] = {'waiting_broadcast': True}
    
    elif data == 'admin_list_channels':
        text = "📋 Majburiy kanallar:\n\n"
        for i, ch in enumerate(REQUIRED_CHANNELS, 1):
            text += f"{i}. {ch['name']} - {ch['username']}\n"
        query.edit_message_text(text)
    
    elif data == 'admin_add_channel':
        query.edit_message_text(
            "➕ Kanal qo'shish\n\nFormat:\nNom | @username | https://t.me/username\n\nMisol:\nYangi Kanal | @yangi | https://t.me/yangi"
        )
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
        query.edit_message_text("➖ O'chirish uchun tanlang:", reply_markup=reply_markup)
    
    elif data.startswith('remove_ch_'):
        idx = int(data.split('_')[2])
        if 0 <= idx < len(REQUIRED_CHANNELS):
            removed = REQUIRED_CHANNELS.pop(idx)
            save_channels()
            query.answer(f"✅ {removed['name']} o'chirildi!", show_alert=True)
            admin_callback(update, context)
        else:
            query.answer("❌ Xatolik!", show_alert=True)

def handle_admin_message(update: Update, context: CallbackContext) -> None:
    if not is_admin(update.effective_user.id):
        return
    
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
        
        update.message.reply_text(f"✅ Yuborildi!\n\n✓ Muvaffaqiyatli: {success}\n✗ Xatolik: {failed}")
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

def check_subscription(update: Update, context: CallbackContext) -> bool:
    user_id = update.effective_user.id
    for channel in REQUIRED_CHANNELS:
        try:
            member = context.bot.get_chat_member(channel['username'], user_id)
            if member.status not in ['member', 'administrator', 'creator']:
                return False
        except:
            return False
    return True

def start(update: Update, context: CallbackContext) -> None:
    user_id = update.effective_user.id
    stats['total_users'].add(user_id)
    
    keyboard = [
        [InlineKeyboardButton(TRANSLATIONS['uz']['uzbek'], callback_data='lang_uz')],
        [InlineKeyboardButton(TRANSLATIONS['ru']['russian'], callback_data='lang_ru')],
        [InlineKeyboardButton(TRANSLATIONS['en']['english'], callback_data='lang_en')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    update.message.reply_text(TRANSLATIONS['uz']['welcome'], reply_markup=reply_markup)

def language_callback(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    query.answer()
    user_id = query.from_user.id
    lang = query.data.split('_')[1]
    user_languages[user_id] = lang
    query.edit_message_text(text=get_text(user_id, 'send_link'))

def show_subscription_message(update: Update, context: CallbackContext) -> None:
    user_id = update.effective_user.id
    message = get_text(user_id, 'not_subscribed')
    for i, channel in enumerate(REQUIRED_CHANNELS, 1):
        message += f"{i}. [{channel['name']}]({channel['url']})\n"
    keyboard = [[InlineKeyboardButton(get_text(user_id, 'subscribe_button'), callback_data='check_subscription')]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    update.message.reply_text(message, reply_markup=reply_markup, parse_mode='Markdown', disable_web_page_preview=True)

def check_subscription_callback(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    user_id = query.from_user.id
    query.answer()
    if check_subscription(update, context):
        query.edit_message_text(text=get_text(user_id, 'send_link'))
    else:
        query.answer("❌ Obuna bo'lmadingiz!", show_alert=True)

def download_video(url: str) -> Optional[str]:
    try:
        ydl_opts = {
            'format': 'best[filesize<50M]/best',
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

def handle_message(update: Update, context: CallbackContext) -> None:
    user_id = update.effective_user.id
    
    if handle_admin_message(update, context):
        return
    
    text = update.message.text
    if user_id not in user_languages:
        user_languages[user_id] = 'uz'
    
    if not text.startswith(('http://', 'https://')):
        update.message.reply_text(get_text(user_id, 'invalid_link'))
        return
    
    if not check_subscription(update, context):
        show_subscription_message(update, context)
        return
    
    if download_queue.full():
        update.message.reply_text("⚠️ Navbat to'lgan.")
        return
    
    queue_size = download_queue.qsize()
    if queue_size > 0:
        wait_time = (queue_size + 1) * 2
        status_msg = update.message.reply_text(get_text(user_id, 'in_queue', position=queue_size + 1, time=wait_time))
    else:
        status_msg = update.message.reply_text(get_text(user_id, 'downloading'))
    
    task = (update, text, status_msg, user_id)
    download_queue.put(task)

def main() -> None:
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
    
    # Start queue worker
    queue_thread = Thread(target=process_queue_worker, args=(updater,), daemon=True)
    queue_thread.start()
    
    dispatcher.add_handler(CommandHandler("start", start))
    dispatcher.add_handler(CommandHandler("admin", admin_panel))
    dispatcher.add_handler(CallbackQueryHandler(language_callback, pattern='^lang_'))
    dispatcher.add_handler(CallbackQueryHandler(check_subscription_callback, pattern='^check_subscription$'))
    dispatcher.add_handler(CallbackQueryHandler(admin_callback, pattern='^admin_'))
    dispatcher.add_handler(CallbackQueryHandler(admin_callback, pattern='^remove_ch_'))
    dispatcher.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_message))
    
    logger.info("Bot ishga tushdi!")
    updater.start_polling()
    updater.idle()

if __name__ == '__main__':
    main()
