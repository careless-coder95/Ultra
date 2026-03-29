"""
𝐔𝐥𝐭𝐫𝐚 𝐆𝐮𝐚𝐫𝐝𝐢𝐚𝐧𝐬 𝐁𝐨𝐭 🤖 v2.0 (Updated for python-telegram-bot 20.1)
"""

import logging
import re
import os
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import (
    Application, 
    MessageHandler, 
    filters,
    ContextTypes, 
    CommandHandler, 
    CallbackQueryHandler
)
from telegram.error import TelegramError
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure

# ============================================
# 🔑 CONFIGURATION
# ============================================

BOT_TOKEN = "YOUR_BOT_TOKEN_HERE"  # BotFather से token paste करो

# MongoDB Configuration
MONGODB_URL = "mongodb+srv://username:password@cluster.mongodb.net/ultra_guardians"

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ============================================
# 🗄️ MONGODB CONNECTION
# ============================================

try:
    client = MongoClient(MONGODB_URL, serverSelectionTimeoutMS=5000)
    client.admin.command('ping')
    db = client['ultra_guardians']
    
    groups_config = db['groups_config']
    bad_words_collection = db['bad_words']
    message_logs = db['message_logs']
    
    logger.info("✅ MongoDB connected successfully!")
    MONGODB_CONNECTED = True
    
except ConnectionFailure:
    logger.error("❌ MongoDB connection failed!")
    MONGODB_CONNECTED = False

# ============================================
# 🛡️ DEFAULT GROUP SETTINGS
# ============================================

DEFAULT_SETTINGS = {
    'noabuse': True,
    'msgdelete': True,
    'msgdelay': 300,
    'biolink': False,
    'edit_protection': True,
    'edit_delay': 0,
    'nolinks': False,
    'allowed_links': ['t.me', 'telegram.me'],
    'mediadelete': False,
    'mediadelay': 600,
    'noforward': False,
    'nohashtags': False,
    'nophone': False,
    'nopromo': False,
    'longmode': 'automatic',
    'longlimit': 800,
}

DEFAULT_BAD_WORDS = [
    'badword1', 'badword2', 'galiword1', 'galiword2'
]

# ============================================
# 📊 MONGODB FUNCTIONS
# ============================================

def get_group_settings(group_id):
    """Group की settings retrieve करो"""
    if not MONGODB_CONNECTED:
        return DEFAULT_SETTINGS
    
    settings = groups_config.find_one({'group_id': group_id})
    if not settings:
        settings = {'group_id': group_id, **DEFAULT_SETTINGS}
        groups_config.insert_one(settings)
    return settings

def update_group_setting(group_id, key, value):
    """Group setting update करो"""
    if not MONGODB_CONNECTED:
        return False
    
    groups_config.update_one(
        {'group_id': group_id},
        {'$set': {key: value}},
        upsert=True
    )
    return True

def get_bad_words(group_id):
    """Group के bad words list लाओ"""
    if not MONGODB_CONNECTED:
        return DEFAULT_BAD_WORDS
    
    words = bad_words_collection.find_one({'group_id': group_id})
    if not words:
        words = {'group_id': group_id, 'words': DEFAULT_BAD_WORDS}
        bad_words_collection.insert_one(words)
    return words.get('words', DEFAULT_BAD_WORDS)

def log_message(group_id, user_id, message_id, action):
    """Message log करो"""
    if not MONGODB_CONNECTED:
        return False
    
    message_logs.insert_one({
        'group_id': group_id,
        'user_id': user_id,
        'message_id': message_id,
        'action': action,
        'timestamp': datetime.now()
    })
    return True

# ============================================
# 🔧 HELPER FUNCTIONS
# ============================================

def is_group_admin(update: Update, user_id):
    """Check if user is group admin"""
    try:
        member = update.effective_chat.get_member(user_id)
        return member.status in ['administrator', 'creator']
    except:
        return False

def contains_link(text):
    """Check for links"""
    if not text:
        return False
    
    link_patterns = [
        r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+',
        r'(?:https?://)?(?:www\.)?(?:t\.me|telegram\.me)/\S+',
        r'(?:https?://)?(?:www\.)?(?:instagram\.com|fb\.com|youtube\.com|twitter\.com|tiktok\.com)/\S+'
    ]
    
    for pattern in link_patterns:
        if re.search(pattern, text, re.IGNORECASE):
            return True
    return False

def contains_bad_word(text, bad_words_list):
    """Check for bad words"""
    if not text:
        return False
    
    lower_text = text.lower()
    for word in bad_words_list:
        if word.lower() in lower_text:
            return True
    return False

def contains_hashtags(text):
    """Check for hashtags"""
    return bool(re.search(r'#\w+', text))

def contains_phone_numbers(text):
    """Check for phone numbers"""
    phone_patterns = [
        r'\+\d{1,3}\s?\d{1,14}',
        r'\+\d{1,3}[-.\s]?\d{1,14}',
        r'\d{10,14}',
    ]
    
    for pattern in phone_patterns:
        if re.search(pattern, text):
            return True
    return False

def is_promotional(text):
    """Check for promotional content - returns score"""
    score = 0
    
    if not text:
        return score
    
    url_count = len(re.findall(r'http[s]?://\S+|t\.me/\S+', text))
    score += url_count * 5
    
    spam_phrases = [
        'join now', 'click here', 'join our', 'active 24/7',
        'vc active', 'chat group', 'make new friends', 'safe for girls',
        'promotion', 'boost your', 'earn money', 'work from home'
    ]
    
    for phrase in spam_phrases:
        if phrase.lower() in text.lower():
            score += 5
    
    if len(text) > 5 and sum(1 for c in text if c.isupper()) > len(text) * 0.7:
        score += 5
    
    emoji_count = len(re.findall(r'[😀-🙏🌀-🗿🚀-🛿]', text))
    if emoji_count > 15:
        score += 5
    
    if text.count('\n') > 3:
        score += 3
    
    return score

def parse_time_format(time_str):
    """Convert time format to seconds"""
    if not time_str:
        return 300
    
    time_str = time_str.lower().strip()
    
    if time_str.endswith('m'):
        return int(time_str[:-1]) * 60
    elif time_str.endswith('h'):
        return int(time_str[:-1]) * 3600
    elif time_str.endswith('s'):
        return int(time_str[:-1])
    else:
        try:
            return int(time_str)
        except:
            return 300

async def schedule_delete(context: ContextTypes.DEFAULT_TYPE, chat_id, message_id):
    """Delete message after delay"""
    try:
        await context.bot.delete_message(chat_id=chat_id, message_id=message_id)
    except TelegramError as e:
        logger.error(f"Error deleting: {e}")

# ============================================
# 📨 MESSAGE HANDLERS
# ============================================

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Main message handler"""
    
    message = update.effective_message
    user = update.effective_user
    chat = update.effective_chat
    
    if user.is_bot:
        return
    
    if is_group_admin(update, user.id):
        return
    
    settings = get_group_settings(chat.id)
    text = message.text or message.caption or ""
    
    # ============================================
    # 🔗 LINK FILTER
    # ============================================
    if settings.get('nolinks') and contains_link(text):
        allowed_links = settings.get('allowed_links', ['t.me'])
        is_allowed = any(link in text.lower() for link in allowed_links)
        
        if not is_allowed:
            try:
                await message.delete()
                log_message(chat.id, user.id, message.message_id, 'link_deleted')
            except TelegramError:
                pass
            return
    
    # ============================================
    # 🚫 NO ABUSE FILTER
    # ============================================
    if settings.get('noabuse'):
        bad_words = get_bad_words(chat.id)
        if contains_bad_word(text, bad_words):
            try:
                await message.delete()
                log_message(chat.id, user.id, message.message_id, 'abuse_deleted')
            except TelegramError:
                pass
            return
    
    # ============================================
    # #️⃣ HASHTAG FILTER
    # ============================================
    if settings.get('nohashtags') and contains_hashtags(text):
        try:
            await message.delete()
            log_message(chat.id, user.id, message.message_id, 'hashtag_deleted')
        except TelegramError:
            pass
        return
    
    # ============================================
    # 📞 PHONE NUMBER PROTECTION
    # ============================================
    if settings.get('nophone') and contains_phone_numbers(text):
        try:
            await message.delete()
            log_message(chat.id, user.id, message.message_id, 'phone_deleted')
        except TelegramError:
            pass
        return
    
    # ============================================
    # 📢 PROMOTIONAL MESSAGE FILTER
    # ============================================
    if settings.get('nopromo'):
        promo_score = is_promotional(text)
        
        if promo_score >= 25:
            try:
                await message.delete()
                log_message(chat.id, user.id, message.message_id, 'promo_deleted')
            except TelegramError:
                pass
            return
        elif promo_score >= 15:
            try:
                await message.reply_text("⚠️ This looks like promotional content. Please avoid spam.", quote=True)
            except TelegramError:
                pass
    
    # ============================================
    # ⏰ MESSAGE AUTO-DELETE
    # ============================================
    if settings.get('msgdelete'):
        delay = settings.get('msgdelay', 300)
        try:
            context.job_queue.run_once(
                callback=lambda ctx: schedule_delete(ctx, chat.id, message.message_id),
                when=delay
            )
        except Exception:
            pass

async def handle_edited_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle edited messages"""
    
    message = update.edited_message
    user = update.effective_user
    chat = update.effective_chat
    
    if user.is_bot or is_group_admin(update, user.id):
        return
    
    settings = get_group_settings(chat.id)
    
    if settings.get('edit_protection'):
        try:
            delay = settings.get('edit_delay', 0)
            if delay > 0:
                context.job_queue.run_once(
                    callback=lambda ctx: schedule_delete(ctx, chat.id, message.message_id),
                    when=delay
                )
            else:
                await message.delete()
            log_message(chat.id, user.id, message.message_id, 'edit_deleted')
        except TelegramError:
            pass

async def handle_media(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle media messages"""
    
    message = update.effective_message
    user = update.effective_user
    chat = update.effective_chat
    
    if user.is_bot or is_group_admin(update, user.id):
        return
    
    settings = get_group_settings(chat.id)
    
    if settings.get('mediadelete'):
        delay = settings.get('mediadelay', 600)
        try:
            context.job_queue.run_once(
                callback=lambda ctx: schedule_delete(ctx, chat.id, message.message_id),
                when=delay
            )
        except Exception:
            pass

async def handle_forward(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle forwarded messages"""
    
    message = update.effective_message
    user = update.effective_user
    chat = update.effective_chat
    
    if user.is_bot or is_group_admin(update, user.id):
        return
    
    settings = get_group_settings(chat.id)
    
    if settings.get('noforward') and message.forward_from:
        try:
            await message.delete()
            log_message(chat.id, user.id, message.message_id, 'forward_deleted')
        except TelegramError:
            pass

# ============================================
# 🎯 COMMAND HANDLERS
# ============================================

async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command"""
    
    keyboard = [
        [InlineKeyboardButton("📚 Help", callback_data='help'),
         InlineKeyboardButton("⚙️ Commands", callback_data='commands')],
        [InlineKeyboardButton("➕ Add Me To Group", url=f"https://t.me/{context.bot.username}?startgroup=true")]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    start_text = """
🛡 Hello 𝐒 𝐓 𝚨 𝐑 𝐊 ᥫ᭡! 👋  
I'm 𝐔𝐥𝐭𝐫𝐚 𝐆𝐮𝐚𝐫𝐝𝐢𝐚𝐧𝐬 𝐁𝐨𝐭 🤖, your group's security bot keeping chats clean and safe.

📣 Stay informed with instant alerts.  
✅ Add me now and I'll start protecting your group!

*Note:* Only group admins can configure settings.
"""
    
    await update.message.reply_text(start_text, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle button clicks"""
    
    query = update.callback_query
    await query.answer()
    
    if query.data == 'help':
        help_text = """
📖 *Ultra Guardians Bot Help*

*Features:*
1️⃣ No Abuse Filter - Removes bad words
2️⃣ Message Auto-Delete - Deletes after delay
3️⃣ Edit Protection - Deletes edited messages
4️⃣ Link Filter - Controls allowed links
5️⃣ Media Auto-Delete - Deletes photos/videos
6️⃣ Forward Control - Blocks forwarded messages
7️⃣ Hashtag Filter - Removes hashtags
8️⃣ Phone Protection - Blocks phone numbers
9️⃣ Promo Filter - Removes spam
🔟 Echo - Send text via Telegraph

👮 *Only group admins can configure!*
"""
        await query.edit_message_text(help_text, parse_mode=ParseMode.MARKDOWN)
    
    elif query.data == 'commands':
        keyboard = [
            [InlineKeyboardButton("🚫 Abuse Filter", callback_data='cmd_abuse')],
            [InlineKeyboardButton("💬 Message Delete", callback_data='cmd_msgdelete')],
            [InlineKeyboardButton("✏️ Edit Protection", callback_data='cmd_edit')],
            [InlineKeyboardButton("🔗 Link Filter", callback_data='cmd_links')],
            [InlineKeyboardButton("🎬 Media Delete", callback_data='cmd_media')],
            [InlineKeyboardButton("📤 Forward Control", callback_data='cmd_forward')],
            [InlineKeyboardButton("#️⃣ Hashtag Filter", callback_data='cmd_hashtags')],
            [InlineKeyboardButton("📞 Phone Protection", callback_data='cmd_phone')],
            [InlineKeyboardButton("📢 Promo Filter", callback_data='cmd_promo')],
            [InlineKeyboardButton("⬅️ Back", callback_data='back')]
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text("*Select a feature:*", reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
    
    elif query.data == 'cmd_abuse':
        text = """
🚫 *No Abuse Filter*

Removes abusive language automatically.

*Commands:*
`/noabuse on` - Enable ✅
`/noabuse off` - Disable ❌

*How:*
Bad words are auto-deleted.
Only admins can configure.
"""
        await query.edit_message_text(text, parse_mode=ParseMode.MARKDOWN)
    
    elif query.data == 'back':
        keyboard = [
            [InlineKeyboardButton("📚 Help", callback_data='help'),
             InlineKeyboardButton("⚙️ Commands", callback_data='commands')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text("🛡 *Ultra Guardians Bot*\n\nChoose an option:", reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)

# ============================================
# 🔧 ADMIN COMMANDS
# ============================================

async def noabuse_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /noabuse command"""
    
    user = update.effective_user
    chat = update.effective_chat
    args = context.args
    
    if not is_group_admin(update, user.id):
        await update.message.reply_text("❌ Only admins can use this!")
        return
    
    if not args:
        settings = get_group_settings(chat.id)
        status = "✅ ON" if settings.get('noabuse') else "❌ OFF"
        await update.message.reply_text(f"🚫 No Abuse Filter: {status}", parse_mode=ParseMode.MARKDOWN)
        return
    
    if args[0].lower() == 'on':
        update_group_setting(chat.id, 'noabuse', True)
        await update.message.reply_text("✅ No Abuse Filter enabled!", parse_mode=ParseMode.MARKDOWN)
    elif args[0].lower() == 'off':
        update_group_setting(chat.id, 'noabuse', False)
        await update.message.reply_text("❌ No Abuse Filter disabled!", parse_mode=ParseMode.MARKDOWN)

async def msgdelete_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /msgdelete command"""
    
    user = update.effective_user
    chat = update.effective_chat
    args = context.args
    
    if not is_group_admin(update, user.id):
        await update.message.reply_text("❌ Only admins can use this!")
        return
    
    if not args:
        settings = get_group_settings(chat.id)
        status = "✅ ON" if settings.get('msgdelete') else "❌ OFF"
        delay = settings.get('msgdelay', 300)
        await update.message.reply_text(f"💬 Message Auto-Delete: {status}\n⏰ Delay: {delay}s", parse_mode=ParseMode.MARKDOWN)
        return
    
    if args[0].lower() == 'on':
        update_group_setting(chat.id, 'msgdelete', True)
        await update.message.reply_text("✅ Message Auto-Delete enabled!", parse_mode=ParseMode.MARKDOWN)
    elif args[0].lower() == 'off':
        update_group_setting(chat.id, 'msgdelete', False)
        await update.message.reply_text("❌ Message Auto-Delete disabled!", parse_mode=ParseMode.MARKDOWN)

async def setmsgdelay_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /setmsgdelay command"""
    
    user = update.effective_user
    chat = update.effective_chat
    args = context.args
    
    if not is_group_admin(update, user.id):
        await update.message.reply_text("❌ Only admins can use this!")
        return
    
    if not args:
        await update.message.reply_text("Usage: `/setmsgdelay 5m` or `/setmsgdelay 1h`", parse_mode=ParseMode.MARKDOWN)
        return
    
    delay = parse_time_format(args[0])
    update_group_setting(chat.id, 'msgdelay', delay)
    await update.message.reply_text(f"⏰ Delay set to {delay}s ({args[0]})", parse_mode=ParseMode.MARKDOWN)

async def nohashtags_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /nohashtags command"""
    
    user = update.effective_user
    chat = update.effective_chat
    args = context.args
    
    if not is_group_admin(update, user.id):
        await update.message.reply_text("❌ Only admins can use this!")
        return
    
    if not args:
        settings = get_group_settings(chat.id)
        status = "✅ ON" if settings.get('nohashtags') else "❌ OFF"
        await update.message.reply_text(f"#️⃣ Hashtag Filter: {status}", parse_mode=ParseMode.MARKDOWN)
        return
    
    if args[0].lower() == 'on':
        update_group_setting(chat.id, 'nohashtags', True)
        await update.message.reply_text("✅ Hashtag Filter enabled!", parse_mode=ParseMode.MARKDOWN)
    elif args[0].lower() == 'off':
        update_group_setting(chat.id, 'nohashtags', False)
        await update.message.reply_text("❌ Hashtag Filter disabled!", parse_mode=ParseMode.MARKDOWN)

async def nophone_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /nophone command"""
    
    user = update.effective_user
    chat = update.effective_chat
    args = context.args
    
    if not is_group_admin(update, user.id):
        await update.message.reply_text("❌ Only admins can use this!")
        return
    
    if not args:
        settings = get_group_settings(chat.id)
        status = "✅ ON" if settings.get('nophone') else "❌ OFF"
        await update.message.reply_text(f"📞 Phone Protection: {status}", parse_mode=ParseMode.MARKDOWN)
        return
    
    if args[0].lower() == 'on':
        update_group_setting(chat.id, 'nophone', True)
        await update.message.reply_text("✅ Phone Protection enabled!", parse_mode=ParseMode.MARKDOWN)
    elif args[0].lower() == 'off':
        update_group_setting(chat.id, 'nophone', False)
        await update.message.reply_text("❌ Phone Protection disabled!", parse_mode=ParseMode.MARKDOWN)

async def nopromo_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /nopromo command"""
    
    user = update.effective_user
    chat = update.effective_chat
    args = context.args
    
    if not is_group_admin(update, user.id):
        await update.message.reply_text("❌ Only admins can use this!")
        return
    
    if not args:
        settings = get_group_settings(chat.id)
        status = "✅ ON" if settings.get('nopromo') else "❌ OFF"
        await update.message.reply_text(f"📢 Promo Filter: {status}", parse_mode=ParseMode.MARKDOWN)
        return
    
    if args[0].lower() == 'on':
        update_group_setting(chat.id, 'nopromo', True)
        await update.message.reply_text("✅ Promo Filter enabled!", parse_mode=ParseMode.MARKDOWN)
    elif args[0].lower() == 'off':
        update_group_setting(chat.id, 'nopromo', False)
        await update.message.reply_text("❌ Promo Filter disabled!", parse_mode=ParseMode.MARKDOWN)

async def nolinks_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /nolinks command"""
    
    user = update.effective_user
    chat = update.effective_chat
    args = context.args
    
    if not is_group_admin(update, user.id):
        await update.message.reply_text("❌ Only admins can use this!")
        return
    
    if not args:
        settings = get_group_settings(chat.id)
        status = "✅ ON" if settings.get('nolinks') else "❌ OFF"
        await update.message.reply_text(f"🔗 Link Filter: {status}", parse_mode=ParseMode.MARKDOWN)
        return
    
    if args[0].lower() == 'on':
        update_group_setting(chat.id, 'nolinks', True)
        await update.message.reply_text("✅ Link Filter enabled!", parse_mode=ParseMode.MARKDOWN)
    elif args[0].lower() == 'off':
        update_group_setting(chat.id, 'nolinks', False)
        await update.message.reply_text("❌ Link Filter disabled!", parse_mode=ParseMode.MARKDOWN)

async def edit_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /edit command"""
    
    user = update.effective_user
    chat = update.effective_chat
    args = context.args
    
    if not is_group_admin(update, user.id):
        await update.message.reply_text("❌ Only admins can use this!")
        return
    
    if not args:
        settings = get_group_settings(chat.id)
        status = "✅ ON" if settings.get('edit_protection') else "❌ OFF"
        await update.message.reply_text(f"✏️ Edit Protection: {status}", parse_mode=ParseMode.MARKDOWN)
        return
    
    if args[0].lower() == 'on':
        update_group_setting(chat.id, 'edit_protection', True)
        await update.message.reply_text("✅ Edit Protection enabled!", parse_mode=ParseMode.MARKDOWN)
    elif args[0].lower() == 'off':
        update_group_setting(chat.id, 'edit_protection', False)
        await update.message.reply_text("❌ Edit Protection disabled!", parse_mode=ParseMode.MARKDOWN)

async def mediadelete_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /mediadelete command"""
    
    user = update.effective_user
    chat = update.effective_chat
    args = context.args
    
    if not is_group_admin(update, user.id):
        await update.message.reply_text("❌ Only admins can use this!")
        return
    
    if not args:
        settings = get_group_settings(chat.id)
        status = "✅ ON" if settings.get('mediadelete') else "❌ OFF"
        await update.message.reply_text(f"🎬 Media Auto-Delete: {status}", parse_mode=ParseMode.MARKDOWN)
        return
    
    if args[0].lower() == 'on':
        update_group_setting(chat.id, 'mediadelete', True)
        await update.message.reply_text("✅ Media Auto-Delete enabled!", parse_mode=ParseMode.MARKDOWN)
    elif args[0].lower() == 'off':
        update_group_setting(chat.id, 'mediadelete', False)
        await update.message.reply_text("❌ Media Auto-Delete disabled!", parse_mode=ParseMode.MARKDOWN)

async def noforward_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /noforward command"""
    
    user = update.effective_user
    chat = update.effective_chat
    args = context.args
    
    if not is_group_admin(update, user.id):
        await update.message.reply_text("❌ Only admins can use this!")
        return
    
    if not args:
        settings = get_group_settings(chat.id)
        status = "✅ ON" if settings.get('noforward') else "❌ OFF"
        await update.message.reply_text(f"📤 Forward Control: {status}", parse_mode=ParseMode.MARKDOWN)
        return
    
    if args[0].lower() == 'on':
        update_group_setting(chat.id, 'noforward', True)
        await update.message.reply_text("✅ Forward Control enabled!", parse_mode=ParseMode.MARKDOWN)
    elif args[0].lower() == 'off':
        update_group_setting(chat.id, 'noforward', False)
        await update.message.reply_text("❌ Forward Control disabled!", parse_mode=ParseMode.MARKDOWN)

async def status_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /status command"""
    
    user = update.effective_user
    chat = update.effective_chat
    
    if not is_group_admin(update, user.id):
        await update.message.reply_text("❌ Only admins can use this!")
        return
    
    if not MONGODB_CONNECTED:
        await update.message.reply_text("❌ MongoDB is not connected!")
        return
    
    settings = get_group_settings(chat.id)
    
    status_text = f"""
🤖 *Ultra Guardians Bot - Status*

*Settings:*
🚫 No Abuse: {'✅' if settings.get('noabuse') else '❌'}
💬 Message Delete: {'✅' if settings.get('msgdelete') else '❌'}  ({settings.get('msgdelay', 300)}s)
✏️ Edit Protection: {'✅' if settings.get('edit_protection') else '❌'}
🔗 Link Filter: {'✅' if settings.get('nolinks') else '❌'}
🎬 Media Delete: {'✅' if settings.get('mediadelete') else '❌'}
📤 Forward Control: {'✅' if settings.get('noforward') else '❌'}
#️⃣ Hashtag Filter: {'✅' if settings.get('nohashtags') else '❌'}
📞 Phone Protection: {'✅' if settings.get('nophone') else '❌'}
📢 Promo Filter: {'✅' if settings.get('nopromo') else '❌'}

*Group:* {chat.title}
"""
    
    await update.message.reply_text(status_text, parse_mode=ParseMode.MARKDOWN)

# ============================================
# 🚀 MAIN FUNCTION
# ============================================

def main():
    """Start the bot"""
    
    if BOT_TOKEN == "YOUR_BOT_TOKEN_HERE":
        print("❌ Bot token not configured!")
        return
    
    print("""
    ╔════════════════════════════════════╗
    ║ 🤖 Ultra Guardians Bot v2.0 🛡️     ║
    ║     Starting Up...                  ║
    ╚════════════════════════════════════╝
    """)
    
    app = Application.builder().token(BOT_TOKEN).build()
    
    # Commands
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("noabuse", noabuse_cmd))
    app.add_handler(CommandHandler("msgdelete", msgdelete_cmd))
    app.add_handler(CommandHandler("setmsgdelay", setmsgdelay_cmd))
    app.add_handler(CommandHandler("nohashtags", nohashtags_cmd))
    app.add_handler(CommandHandler("nophone", nophone_cmd))
    app.add_handler(CommandHandler("nopromo", nopromo_cmd))
    app.add_handler(CommandHandler("nolinks", nolinks_cmd))
    app.add_handler(CommandHandler("edit", edit_cmd))
    app.add_handler(CommandHandler("mediadelete", mediadelete_cmd))
    app.add_handler(CommandHandler("noforward", noforward_cmd))
    app.add_handler(CommandHandler("status", status_cmd))
    
    # Callbacks
    app.add_handler(CallbackQueryHandler(button_callback))
    
    # Message handlers
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(MessageHandler(filters.UPDATE.EDITED_MESSAGE & filters.TEXT, handle_edited_message))
    app.add_handler(MessageHandler(filters.PHOTO | filters.VIDEO | filters.Document.ALL, handle_media))
    app.add_handler(MessageHandler(filters.TEXT, handle_forward))
    
    print("✅ Bot started!")
    print("Press Ctrl+C to stop\n")
    
    app.run_polling()

if __name__ == '__main__':
    main()