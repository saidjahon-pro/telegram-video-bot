import os
import logging
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
import yt_dlp
from typing import Optional
from queue import Queue
from threading import Thread

# Logging sozlash
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# NAVBAT TIZIMI - Global Queue
download_queue = Queue(maxsize=100)  # Max 100 ta task navbatda
active_downloads = 0
MAX_CONCURRENT_DOWNLOADS = 3  # Bir vaqtda max 3 ta video yuklanadi

# Majburiy kanallar
REQUIRED_CHANNELS = [
    {"name": "Muallim GPT", "username": "@muallim_gpt", "url": "https://t.me/muallim_gpt"},
    {"name": "Meta Bilim", "username": "@meta_bilim", "url": "https://t.me/meta_bilim"}
]

# Tarjimalar
TRANSLATIONS = {
    'uz': {
        'welcome': "🎬 Video Yuklovchi Botga xush kelibsiz!\n\nInstagram, Facebook, TikTok, YouTube va boshqa platformalardan videolarni yuklab olishingiz mumkin.\n\n📌 Quyidagi tillardan birini tanlang:",
        'select_language': "🌐 Tilni tanlang:",
        'send_link': "📎 Iltimos, yuklamoqchi bo'lgan video linkini yuboring.\n\n✅ Qo'llab-quvvatlanadigan platformalar:\n• Instagram\n• Facebook\n• TikTok\n• YouTube\n• Pinterest\n• Twitter/X\n• Va boshqalar",
        'checking_subscription': "⏳ Obuna tekshirilmoqda...",
        'not_subscribed': "❌ Siz quyidagi kanallarga obuna bo'lmagansiz:\n\n",
        'subscribe_button': "✅ Obuna bo'ldim",
        'subscribe_first': "📢 Botdan foydalanish uchun avval kanallarga obuna bo'ling!",
        'downloading': "⬇️ Video yuklanmoqda... Iltimos kuting.",
        'in_queue': "⏳ Navbatda: {position}-o'rinda. Taxminan {time} daqiqa kutish.",
        'processing': "⚙️ Video qayta ishlanmoqda...",
        'sending': "📤 Video yuborilmoqda...",
        'success': "✅ Video muvaffaqiyatli yuklandi!",
        'error': "❌ Xatolik yuz berdi. Iltimos, qaytadan urinib ko'ring yoki boshqa link yuboring.",
        'invalid_link': "❌ Noto'g'ri link. Iltimos, to'g'ri video linkini yuboring.",
        'file_too_large': "❌ Video hajmi juda katta (50MB dan oshadi). Iltimos, boshqa video tanlang.",
        'queue_full': "⚠️ Navbat to'lgan. Iltimos, biroz kutib qaytadan urinib ko'ring.",
        'thanks_subscribe': "✅ Rahmat! Endi video linkini yuboring.",
        'channel_name': "Kanal:",
        'uzbek': "🇺🇿 O'zbek tili",
        'russian': "🇷🇺 Русский язык",
        'english': "🇬🇧 English"
    },
    'ru': {
        'welcome': "🎬 Добро пожаловать в бот для скачивания видео!\n\nВы можете скачивать видео с Instagram, Facebook, TikTok, YouTube и других платформ.\n\n📌 Выберите язык:",
        'select_language': "🌐 Выберите язык:",
        'send_link': "📎 Пожалуйста, отправьте ссылку на видео, которое хотите скачать.\n\n✅ Поддерживаемые платформы:\n• Instagram\n• Facebook\n• TikTok\n• YouTube\n• Pinterest\n• Twitter/X\n• И другие",
        'checking_subscription': "⏳ Проверка подписки...",
        'not_subscribed': "❌ Вы не подписаны на следующие каналы:\n\n",
        'subscribe_button': "✅ Я подписался",
        'subscribe_first': "📢 Подпишитесь на каналы, чтобы использовать бот!",
        'downloading': "⬇️ Загрузка видео... Пожалуйста, подождите.",
        'in_queue': "⏳ В очереди: {position} место. Примерно {time} минут ожидания.",
        'processing': "⚙️ Обработка видео...",
        'sending': "📤 Отправка видео...",
        'success': "✅ Видео успешно загружено!",
        'error': "❌ Произошла ошибка. Попробуйте еще раз или отправьте другую ссылку.",
        'invalid_link': "❌ Неверная ссылка. Пожалуйста, отправьте правильную ссылку на видео.",
        'file_too_large': "❌ Видео слишком большое (более 50MB). Пожалуйста, выберите другое видео.",
        'queue_full': "⚠️ Очередь заполнена. Пожалуйста, подождите и попробуйте позже.",
        'thanks_subscribe': "✅ Спасибо! Теперь отправьте ссылку на видео.",
        'channel_name': "Канал:",
        'uzbek': "🇺🇿 O'zbek tili",
        'russian': "🇷🇺 Русский язык",
        'english': "🇬🇧 English"
    },
    'en': {
        'welcome': "🎬 Welcome to Video Downloader Bot!\n\nYou can download videos from Instagram, Facebook, TikTok, YouTube and other platforms.\n\n📌 Choose your language:",
        'select_language': "🌐 Select language:",
        'send_link': "📎 Please send the video link you want to download.\n\n✅ Supported platforms:\n• Instagram\n• Facebook\n• TikTok\n• YouTube\n• Pinterest\n• Twitter/X\n• And more",
        'checking_subscription': "⏳ Checking subscription...",
        'not_subscribed': "❌ You are not subscribed to the following channels:\n\n",
        'subscribe_button': "✅ I subscribed",
        'subscribe_first': "📢 Subscribe to the channels to use the bot!",
        'downloading': "⬇️ Downloading video... Please wait.",
        'in_queue': "⏳ In queue: position {position}. Approximately {time} minutes wait.",
        'processing': "⚙️ Processing video...",
        'sending': "📤 Sending video...",
        'success': "✅ Video downloaded successfully!",
        'error': "❌ An error occurred. Please try again or send another link.",
        'invalid_link': "❌ Invalid link. Please send a valid video link.",
        'file_too_large': "❌ Video is too large (over 50MB). Please choose another video.",
        'queue_full': "⚠️ Queue is full. Please wait and try again later.",
        'thanks_subscribe': "✅ Thanks! Now send the video link.",
        'channel_name': "Channel:",
        'uzbek': "🇺🇿 O'zbek tili",
        'russian': "🇷🇺 Русский язык",
        'english': "🇬🇧 English"
    }
}

user_languages = {}

def get_text(user_id: int, key: str, **kwargs) -> str:
    """Foydalanuvchi tili bo'yicha matnni qaytaradi"""
    lang = user_languages.get(user_id, 'uz')
    text = TRANSLATIONS[lang].get(key, TRANSLATIONS['uz'][key])
    return text.format(**kwargs) if kwargs else text

async def check_subscription(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Foydalanuvchi kanalga obuna bo'lganligini tekshiradi"""
    user_id = update.effective_user.id
    
    for channel in REQUIRED_CHANNELS:
        try:
            member = await context.bot.get_chat_member(channel['username'], user_id)
            if member.status not in ['member', 'administrator', 'creator']:
                return False
        except Exception as e:
            logger.error(f"Obuna tekshirishda xatolik: {e}")
            return False
    
    return True

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Start buyrug'i"""
    keyboard = [
        [InlineKeyboardButton(TRANSLATIONS['uz']['uzbek'], callback_data='lang_uz')],
        [InlineKeyboardButton(TRANSLATIONS['ru']['russian'], callback_data='lang_ru')],
        [InlineKeyboardButton(TRANSLATIONS['en']['english'], callback_data='lang_en')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        TRANSLATIONS['uz']['welcome'],
        reply_markup=reply_markup
    )

async def language_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Til tanlash callback"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    lang = query.data.split('_')[1]
    user_languages[user_id] = lang
    
    await query.edit_message_text(
        text=get_text(user_id, 'send_link')
    )

async def show_subscription_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Obuna bo'lish xabarini ko'rsatadi"""
    user_id = update.effective_user.id
    
    message = get_text(user_id, 'not_subscribed')
    
    for i, channel in enumerate(REQUIRED_CHANNELS, 1):
        message += f"{i}. [{channel['name']}]({channel['url']})\n"
    
    message += f"\n{get_text(user_id, 'subscribe_first')}"
    
    keyboard = [[InlineKeyboardButton(
        get_text(user_id, 'subscribe_button'), 
        callback_data='check_subscription'
    )]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        message,
        reply_markup=reply_markup,
        parse_mode='Markdown',
        disable_web_page_preview=True
    )

async def check_subscription_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Obuna tekshirish callback"""
    query = update.callback_query
    user_id = update.effective_user.id
    
    await query.answer(get_text(user_id, 'checking_subscription'))
    
    if await check_subscription(update, context):
        await query.edit_message_text(
            text=get_text(user_id, 'thanks_subscribe') + "\n\n" + get_text(user_id, 'send_link')
        )
    else:
        await query.answer(
            get_text(user_id, 'subscribe_first'),
            show_alert=True
        )

async def download_video(url: str) -> Optional[str]:
    """Video yuklab olish"""
    try:
        ydl_opts = {
            'format': 'best[filesize<50M]/best',
            'outtmpl': 'downloads/%(id)s.%(ext)s',
            'quiet': True,
            'no_warnings': True,
            'extract_flat': False,
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            return filename
            
    except Exception as e:
        logger.error(f"Video yuklab olishda xatolik: {e}")
        return None

def process_queue():
    """Navbatdagi videolarni qayta ishlash (Background thread)"""
    global active_downloads
    
    while True:
        if not download_queue.empty() and active_downloads < MAX_CONCURRENT_DOWNLOADS:
            task = download_queue.get()
            active_downloads += 1
            
            # Taskni ishga tushirish
            asyncio.run(process_download_task(task))
            
            active_downloads -= 1
            download_queue.task_done()

async def process_download_task(task):
    """Bitta video yuklab olish taskini bajarish"""
    update, context, url, status_msg, user_id = task
    
    try:
        # Video yuklab olish
        video_path = await download_video(url)
        
        if not video_path:
            await status_msg.edit_text(get_text(user_id, 'error'))
            return
        
        # Fayl hajmini tekshirish
        file_size = os.path.getsize(video_path)
        if file_size > 50 * 1024 * 1024:
            os.remove(video_path)
            await status_msg.edit_text(get_text(user_id, 'file_too_large'))
            return
        
        # Yuborish
        await status_msg.edit_text(get_text(user_id, 'sending'))
        
        with open(video_path, 'rb') as video:
            await update.message.reply_video(
                video=video,
                caption=get_text(user_id, 'success'),
                supports_streaming=True
            )
        
        os.remove(video_path)
        await status_msg.delete()
        
    except Exception as e:
        logger.error(f"Xatolik: {e}")
        await status_msg.edit_text(get_text(user_id, 'error'))

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Xabarlarni qayta ishlash"""
    user_id = update.effective_user.id
    text = update.message.text
    
    if user_id not in user_languages:
        user_languages[user_id] = 'uz'
    
    if not text.startswith(('http://', 'https://')):
        await update.message.reply_text(get_text(user_id, 'invalid_link'))
        return
    
    if not await check_subscription(update, context):
        await show_subscription_message(update, context)
        return
    
    # Navbat to'lganligini tekshirish
    if download_queue.full():
        await update.message.reply_text(get_text(user_id, 'queue_full'))
        return
    
    # Navbat holatini ko'rsatish
    queue_size = download_queue.qsize()
    if queue_size > 0:
        wait_time = (queue_size + 1) * 2  # Har bir video ~2 daqiqa
        status_msg = await update.message.reply_text(
            get_text(user_id, 'in_queue', position=queue_size + 1, time=wait_time)
        )
    else:
        status_msg = await update.message.reply_text(get_text(user_id, 'downloading'))
    
    # Navbatga qo'shish
    task = (update, context, text, status_msg, user_id)
    download_queue.put(task)
    
    logger.info(f"Video navbatga qo'shildi. Navbat hajmi: {download_queue.qsize()}")

def main() -> None:
    """Botni ishga tushirish"""
    os.makedirs('downloads', exist_ok=True)
    
    token = os.environ.get('BOT_TOKEN')
    if not token:
        logger.error("BOT_TOKEN topilmadi!")
        return
    
    # Background queue processor thread
    queue_thread = Thread(target=process_queue, daemon=True)
    queue_thread.start()
    
    application = Application.builder().token(token).build()
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(language_callback, pattern='^lang_'))
    application.add_handler(CallbackQueryHandler(check_subscription_callback, pattern='^check_subscription$'))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    logger.info("Bot ishga tushdi! Navbat tizimi faol.")
    application.run_polling(drop_pending_updates=True)

if __name__ == '__main__':
    main()
