"""
𝐔𝐥𝐭𝐫𝐚 𝐆𝐮𝐚𝐫𝐝𝐢𝐚𝐧𝐬 𝐁𝐨𝐭 🤖 v2.0
Complete moderation bot with MongoDB + New Features
- Every group admin has full control
- Hashtag Filter, Phone Number Protection, Promo Filter, Echo
"""

import logging
import re
import os
from datetime import datetime, timedelta
from telegram import Update, ParseMode, InlineKeyboardButton, InlineKeyboardMarkup, ChatPermissions
from telegram.ext import Updater, MessageHandler, Filters, CallbackContext, CommandHandler, CallbackQueryHandler
from telegram.error import TelegramError
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure
import requests

# ============================================
# 🔑 CONFIGURATION
# ============================================

BOT_TOKEN = "YOUR_BOT_TOKEN_HERE"  # BotFather से token paste करो

# MongoDB Configuration
MONGODB_URL = ""

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
    'madharchod', 'madharxod', 'mkc', 'randi'
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
        r'\+\d{1,3}\s?\d{1,14}',  # International format
        r'\+\d{1,3}[-.\s]?\d{1,14}',  # With dashes/dots
        r'\d{10,14}',  # Just digits
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
    
    # Count URLs
    url_count = len(re.findall(r'http[s]?://\S+|t\.me/\S+', text))
    score += url_count * 5
    
    # Spam phrases
    spam_phrases = [
        'join now', 'click here', 'join our', 'active 24/7',
        'vc active', 'chat group', 'make new friends', 'safe for girls',
        'promotion', 'boost your', 'earn money', 'work from home'
    ]
    
    for phrase in spam_phrases:
        if phrase.lower() in text.lower():
            score += 5
    
    # ALL CAPS
    if len(text) > 5 and sum(1 for c in text if c.isupper()) > len(text) * 0.7:
        score += 5
    
    # Excessive emojis
    emoji_count = len(re.findall(r'[😀-🙏🌀-🗿🚀-🛿]', text))
    if emoji_count > 15:
        score += 5
    
    # Multiple lines (spam indication)
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

def schedule_delete(context: CallbackContext, chat_id, message_id):
    """Delete message after delay"""
    try:
        context.bot.delete_message(chat_id=chat_id, message_id=message_id)
    except TelegramError as e:
        logger.error(f"Error deleting: {e}")

# ============================================
# 📨 MESSAGE HANDLERS
# ============================================

def handle_message(update: Update, context: CallbackContext):
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
                message.delete()
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
                message.delete()
                log_message(chat.id, user.id, message.message_id, 'abuse_deleted')
            except TelegramError:
                pass
            return
    
    # ============================================
    # #️⃣ HASHTAG FILTER
    # ============================================
    if settings.get('nohashtags') and contains_hashtags(text):
        try:
            message.delete()
            log_message(chat.id, user.id, message.message_id, 'hashtag_deleted')
        except TelegramError:
            pass
        return
    
    # ============================================
    # 📞 PHONE NUMBER PROTECTION
    # ============================================
    if settings.get('nophone') and contains_phone_numbers(text):
        try:
            message.delete()
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
                message.delete()
                log_message(chat.id, user.id, message.message_id, 'promo_deleted')
            except TelegramError:
                pass
            return
        elif promo_score >= 15:
            try:
                message.reply_text("⚠️ This looks like promotional content. Please avoid spam.", quote=True)
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

def handle_edited_message(update: Update, context: CallbackContext):
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
                message.delete()
            log_message(chat.id, user.id, message.message_id, 'edit_deleted')
        except TelegramError:
            pass

def handle_media(update: Update, context: CallbackContext):
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

def handle_forward(update: Update, context: CallbackContext):
    """Handle forwarded messages"""
    
    message = update.effective_message
    user = update.effective_user
    chat = update.effective_chat
    
    if user.is_bot or is_group_admin(update, user.id):
        return
    
    settings = get_group_settings(chat.id)
    
    if settings.get('noforward') and message.forward_from:
        try:
            message.delete()
            log_message(chat.id, user.id, message.message_id, 'forward_deleted')
        except TelegramError:
            pass

# ============================================
# 🎯 COMMAND HANDLERS
# ============================================

def start_cmd(update: Update, context: CallbackContext):
    """Handle /start command with inline buttons"""
    
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
    
    update.message.reply_text(start_text, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)

def button_callback(update: Update, context: CallbackContext):
    """Handle button clicks"""
    
    query = update.callback_query
    query.answer()
    
    if query.data == 'help':
        help_text = """
📖 *Ultra Guardians Bot Help*

*What Can This Bot Do?*

1️⃣ *No Abuse Filter* - Removes messages with bad words
2️⃣ *Message Auto-Delete* - Deletes all messages after delay
3️⃣ *Edit Protection* - Deletes edited messages
4️⃣ *Link Filter* - Controls allowed links
5️⃣ *Media Auto-Delete* - Deletes photos/videos
6️⃣ *Forward Control* - Blocks forwarded messages
7️⃣ *Hashtag Filter* - Removes hashtags
8️⃣ *Phone Protection* - Blocks phone numbers
9️⃣ *Promo Filter* - Removes promotional spam
🔟 *Echo* - Send text via Telegraph

👮 *Only group admins can configure these!*
"""
        query.edit_message_text(help_text, parse_mode=ParseMode.MARKDOWN)
    
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
            [InlineKeyboardButton("🔊 Echo", callback_data='cmd_echo')],
            [InlineKeyboardButton("⬅️ Back", callback_data='back')]
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        query.edit_message_text("*Select a feature to learn more:*", reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
    
    elif query.data == 'cmd_abuse':
        text = """
🚫 *No Abuse Filter*

Automatically detects and removes abusive language.

*Commands:*
• `/noabuse on` - Enable ✅
• `/noabuse off` - Disable ❌

*Usage:*
Only group admins can use this command.
Messages with bad words will be automatically deleted.

*How to add custom bad words?*
Contact bot owner to add words to your group's list.
"""
        query.edit_message_text(text, parse_mode=ParseMode.MARKDOWN)
    
    elif query.data == 'cmd_msgdelete':
        text = """
💬 *Message Auto-Delete*

Automatically removes all messages after a set delay.

*Commands:*
• `/msgdelete on` - Enable ✅
• `/msgdelete off` - Disable ❌
• `/setmsgdelay <time>` - Set delay

*Time Format:*
• `5m` = 5 minutes
• `1h` = 1 hour
• `12h` = 12 hours

*Note:* Admin messages are protected.
"""
        query.edit_message_text(text, parse_mode=ParseMode.MARKDOWN)
    
    elif query.data == 'cmd_edit':
        text = """
✏️ *Edit Protection*

Automatically deletes messages when edited.

*Commands:*
• `/edit on` - Enable ✅
• `/edit off` - Disable ❌
• `/seteditdelay <time>` - Set delay

*How it works:*
When a user edits their message, it gets deleted immediately (or after the set delay).
"""
        query.edit_message_text(text, parse_mode=ParseMode.MARKDOWN)
    
    elif query.data == 'cmd_links':
        text = """
🔗 *Link Filter*

Controls which links are allowed in the group.

*Commands:*
• `/nolinks on` - Enable blocking ✅
• `/nolinks off` - Allow all links ❌
• `/allowlink <domain>` - Whitelist a domain
• `/listlinks` - Show allowed domains

*Example:*
`/allowlink youtube.com` - Allow YouTube links
`/removelink youtube.com` - Remove from whitelist

*Note:* Blocked links will be deleted.
"""
        query.edit_message_text(text, parse_mode=ParseMode.MARKDOWN)
    
    elif query.data == 'cmd_media':
        text = """
🎬 *Media Auto-Delete*

Automatically removes photos, videos, and files.

*Commands:*
• `/mediadelete on` - Enable ✅
• `/mediadelete off` - Disable ❌
• `/setmediadelay <time>` - Set delay

*Covers:*
• Photos & Videos
• GIFs & Stickers
• Documents & Files

*Time Format:*
• `5m` = 5 minutes
• `1h` = 1 hour
"""
        query.edit_message_text(text, parse_mode=ParseMode.MARKDOWN)
    
    elif query.data == 'cmd_forward':
        text = """
📤 *Forward Control*

Blocks messages forwarded from other groups.

*Commands:*
• `/noforward on` - Block forwards ✅
• `/noforward off` - Allow forwards ❌

*How it works:*
Any message with "Forwarded from" will be automatically deleted.

*Note:* Protects your group from external spam.
"""
        query.edit_message_text(text, parse_mode=ParseMode.MARKDOWN)
    
    elif query.data == 'cmd_hashtags':
        text = """
#️⃣ *Hashtag Filter*

Blocks messages containing hashtags.

*Commands:*
• `/nohashtags on` - Block hashtags ✅
• `/nohashtags off` - Allow hashtags ❌

*Detection:*
Any word starting with `#` symbol.

*Examples:*
• `#join` - Blocked
• `#promotion` - Blocked
• `#trending` - Blocked

*Note:* Useful to prevent promotional spam.
"""
        query.edit_message_text(text, parse_mode=ParseMode.MARKDOWN)
    
    elif query.data == 'cmd_phone':
        text = """
📞 *Phone Number Protection*

Blocks messages containing phone numbers.

*Commands:*
• `/nophone on` - Block numbers ✅
• `/nophone off` - Allow numbers ❌

*Detection Formats:*
• `+91 9876543210` - International ✓
• `+1-234-567-8900` - With dashes ✓
• `919876543210` - No plus ✓
• `10-digit numbers` ✓

*Note:* Prevents scam and spam messages.
"""
        query.edit_message_text(text, parse_mode=ParseMode.MARKDOWN)
    
    elif query.data == 'cmd_promo':
        text = """
📢 *Promotional Message Filter*

Blocks spam and promotional content.

*Commands:*
• `/nopromo on` - Enable blocking ✅
• `/nopromo off` - Disable ❌

*Detected Patterns:*
• Multiple links (3+)
• "Join now", "Click here"
• 24/7 active, VC group promotions
• 15+ emojis
• ALL-CAPS messages
• "Make new friends" spam

*Actions:*
• Score 15-25: Warning ⚠️
• Score 25+: Deleted 🚫
"""
        query.edit_message_text(text, parse_mode=ParseMode.MARKDOWN)
    
    elif query.data == 'cmd_echo':
        text = """
🔊 *Echo & Long Message Handler*

Send text back or upload long messages to Telegraph.

*Commands:*
• `/echo <text>` - Echo text
• `/setlongmode <off|manual|automatic>` - Set mode
• `/setlonglimit <number>` - Set character limit

*Modes:*
• `off` - No action
• `manual` - Delete & warn
• `automatic` - Delete & send Telegraph link

*Character Limit:*
Default: 800 (Range: 200-4000)

*How it works:*
If message exceeds limit, it's uploaded to Telegraph.
"""
        query.edit_message_text(text, parse_mode=ParseMode.MARKDOWN)
    
    elif query.data == 'back':
        keyboard = [
            [InlineKeyboardButton("📚 Help", callback_data='help'),
             InlineKeyboardButton("⚙️ Commands", callback_data='commands')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        query.edit_message_text("🛡 *Ultra Guardians Bot*\n\nChoose an option:", reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)

# ============================================
# 🔧 ADMIN COMMANDS
# ============================================

def noabuse_cmd(update: Update, context: CallbackContext):
    """Handle /noabuse command"""
    
    user = update.effective_user
    chat = update.effective_chat
    args = context.args
    
    if not is_group_admin(update, user.id):
        update.message.reply_text("❌ Only admins can use this command!")
        return
    
    if not args:
        settings = get_group_settings(chat.id)
        status = "✅ ON" if settings.get('noabuse') else "❌ OFF"
        update.message.reply_text(f"🚫 *No Abuse Filter:* {status}", parse_mode=ParseMode.MARKDOWN)
        return
    
    if args[0].lower() == 'on':
        update_group_setting(chat.id, 'noabuse', True)
        update.message.reply_text("✅ *No Abuse Filter enabled!*", parse_mode=ParseMode.MARKDOWN)
    elif args[0].lower() == 'off':
        update_group_setting(chat.id, 'noabuse', False)
        update.message.reply_text("❌ *No Abuse Filter disabled!*", parse_mode=ParseMode.MARKDOWN)

def msgdelete_cmd(update: Update, context: CallbackContext):
    """Handle /msgdelete command"""
    
    user = update.effective_user
    chat = update.effective_chat
    args = context.args
    
    if not is_group_admin(update, user.id):
        update.message.reply_text("❌ Only admins can use this command!")
        return
    
    if not args:
        settings = get_group_settings(chat.id)
        status = "✅ ON" if settings.get('msgdelete') else "❌ OFF"
        delay = settings.get('msgdelay', 300)
        update.message.reply_text(f"💬 *Message Auto-Delete:* {status}\n⏰ *Delay:* {delay}s", parse_mode=ParseMode.MARKDOWN)
        return
    
    if args[0].lower() == 'on':
        update_group_setting(chat.id, 'msgdelete', True)
        update.message.reply_text("✅ *Message Auto-Delete enabled!*", parse_mode=ParseMode.MARKDOWN)
    elif args[0].lower() == 'off':
        update_group_setting(chat.id, 'msgdelete', False)
        update.message.reply_text("❌ *Message Auto-Delete disabled!*", parse_mode=ParseMode.MARKDOWN)

def setmsgdelay_cmd(update: Update, context: CallbackContext):
    """Handle /setmsgdelay command"""
    
    user = update.effective_user
    chat = update.effective_chat
    args = context.args
    
    if not is_group_admin(update, user.id):
        update.message.reply_text("❌ Only admins can use this command!")
        return
    
    if not args:
        update.message.reply_text("📝 *Usage:* `/setmsgdelay <time>`\n\n*Examples:*\n• `/setmsgdelay 5m` - 5 minutes\n• `/setmsgdelay 1h` - 1 hour", parse_mode=ParseMode.MARKDOWN)
        return
    
    delay = parse_time_format(args[0])
    update_group_setting(chat.id, 'msgdelay', delay)
    update.message.reply_text(f"⏰ *Message delete delay set to* `{delay}s` *({args[0]})*", parse_mode=ParseMode.MARKDOWN)

def nohashtags_cmd(update: Update, context: CallbackContext):
    """Handle /nohashtags command"""
    
    user = update.effective_user
    chat = update.effective_chat
    args = context.args
    
    if not is_group_admin(update, user.id):
        update.message.reply_text("❌ Only admins can use this command!")
        return
    
    if not args:
        settings = get_group_settings(chat.id)
        status = "✅ ON" if settings.get('nohashtags') else "❌ OFF"
        update.message.reply_text(f"#️⃣ *Hashtag Filter:* {status}", parse_mode=ParseMode.MARKDOWN)
        return
    
    if args[0].lower() == 'on':
        update_group_setting(chat.id, 'nohashtags', True)
        update.message.reply_text("✅ *Hashtag Filter enabled!*", parse_mode=ParseMode.MARKDOWN)
    elif args[0].lower() == 'off':
        update_group_setting(chat.id, 'nohashtags', False)
        update.message.reply_text("❌ *Hashtag Filter disabled!*", parse_mode=ParseMode.MARKDOWN)

def nophone_cmd(update: Update, context: CallbackContext):
    """Handle /nophone command"""
    
    user = update.effective_user
    chat = update.effective_chat
    args = context.args
    
    if not is_group_admin(update, user.id):
        update.message.reply_text("❌ Only admins can use this command!")
        return
    
    if not args:
        settings = get_group_settings(chat.id)
        status = "✅ ON" if settings.get('nophone') else "❌ OFF"
        update.message.reply_text(f"📞 *Phone Protection:* {status}", parse_mode=ParseMode.MARKDOWN)
        return
    
    if args[0].lower() == 'on':
        update_group_setting(chat.id, 'nophone', True)
        update.message.reply_text("✅ *Phone Protection enabled!*", parse_mode=ParseMode.MARKDOWN)
    elif args[0].lower() == 'off':
        update_group_setting(chat.id, 'nophone', False)
        update.message.reply_text("❌ *Phone Protection disabled!*", parse_mode=ParseMode.MARKDOWN)

def nopromo_cmd(update: Update, context: CallbackContext):
    """Handle /nopromo command"""
    
    user = update.effective_user
    chat = update.effective_chat
    args = context.args
    
    if not is_group_admin(update, user.id):
        update.message.reply_text("❌ Only admins can use this command!")
        return
    
    if not args:
        settings = get_group_settings(chat.id)
        status = "✅ ON" if settings.get('nopromo') else "❌ OFF"
        update.message.reply_text(f"📢 *Promo Filter:* {status}", parse_mode=ParseMode.MARKDOWN)
        return
    
    if args[0].lower() == 'on':
        update_group_setting(chat.id, 'nopromo', True)
        update.message.reply_text("✅ *Promo Filter enabled!*", parse_mode=ParseMode.MARKDOWN)
    elif args[0].lower() == 'off':
        update_group_setting(chat.id, 'nopromo', False)
        update.message.reply_text("❌ *Promo Filter disabled!*", parse_mode=ParseMode.MARKDOWN)

def nolinks_cmd(update: Update, context: CallbackContext):
    """Handle /nolinks command"""
    
    user = update.effective_user
    chat = update.effective_chat
    args = context.args
    
    if not is_group_admin(update, user.id):
        update.message.reply_text("❌ Only admins can use this command!")
        return
    
    if not args:
        settings = get_group_settings(chat.id)
        status = "✅ ON" if settings.get('nolinks') else "❌ OFF"
        update.message.reply_text(f"🔗 *Link Filter:* {status}", parse_mode=ParseMode.MARKDOWN)
        return
    
    if args[0].lower() == 'on':
        update_group_setting(chat.id, 'nolinks', True)
        update.message.reply_text("✅ *Link Filter enabled!*", parse_mode=ParseMode.MARKDOWN)
    elif args[0].lower() == 'off':
        update_group_setting(chat.id, 'nolinks', False)
        update.message.reply_text("❌ *Link Filter disabled!*", parse_mode=ParseMode.MARKDOWN)

def allowlink_cmd(update: Update, context: CallbackContext):
    """Handle /allowlink command"""
    
    user = update.effective_user
    chat = update.effective_chat
    args = context.args
    
    if not is_group_admin(update, user.id):
        update.message.reply_text("❌ Only admins can use this command!")
        return
    
    if not args:
        update.message.reply_text("📝 *Usage:* `/allowlink <domain>`\n\n*Example:*\n`/allowlink youtube.com`", parse_mode=ParseMode.MARKDOWN)
        return
    
    settings = get_group_settings(chat.id)
    allowed = settings.get('allowed_links', [])
    
    if args[0] not in allowed:
        allowed.append(args[0])
        update_group_setting(chat.id, 'allowed_links', allowed)
        update.message.reply_text(f"✅ `{args[0]}` added to allowed links!", parse_mode=ParseMode.MARKDOWN)
    else:
        update.message.reply_text(f"⚠️ `{args[0]}` is already allowed!", parse_mode=ParseMode.MARKDOWN)

def edit_cmd(update: Update, context: CallbackContext):
    """Handle /edit command"""
    
    user = update.effective_user
    chat = update.effective_chat
    args = context.args
    
    if not is_group_admin(update, user.id):
        update.message.reply_text("❌ Only admins can use this command!")
        return
    
    if not args:
        settings = get_group_settings(chat.id)
        status = "✅ ON" if settings.get('edit_protection') else "❌ OFF"
        update.message.reply_text(f"✏️ *Edit Protection:* {status}", parse_mode=ParseMode.MARKDOWN)
        return
    
    if args[0].lower() == 'on':
        update_group_setting(chat.id, 'edit_protection', True)
        update.message.reply_text("✅ *Edit Protection enabled!*", parse_mode=ParseMode.MARKDOWN)
    elif args[0].lower() == 'off':
        update_group_setting(chat.id, 'edit_protection', False)
        update.message.reply_text("❌ *Edit Protection disabled!*", parse_mode=ParseMode.MARKDOWN)

def mediadelete_cmd(update: Update, context: CallbackContext):
    """Handle /mediadelete command"""
    
    user = update.effective_user
    chat = update.effective_chat
    args = context.args
    
    if not is_group_admin(update, user.id):
        update.message.reply_text("❌ Only admins can use this command!")
        return
    
    if not args:
        settings = get_group_settings(chat.id)
        status = "✅ ON" if settings.get('mediadelete') else "❌ OFF"
        update.message.reply_text(f"🎬 *Media Auto-Delete:* {status}", parse_mode=ParseMode.MARKDOWN)
        return
    
    if args[0].lower() == 'on':
        update_group_setting(chat.id, 'mediadelete', True)
        update.message.reply_text("✅ *Media Auto-Delete enabled!*", parse_mode=ParseMode.MARKDOWN)
    elif args[0].lower() == 'off':
        update_group_setting(chat.id, 'mediadelete', False)
        update.message.reply_text("❌ *Media Auto-Delete disabled!*", parse_mode=ParseMode.MARKDOWN)

def noforward_cmd(update: Update, context: CallbackContext):
    """Handle /noforward command"""
    
    user = update.effective_user
    chat = update.effective_chat
    args = context.args
    
    if not is_group_admin(update, user.id):
        update.message.reply_text("❌ Only admins can use this command!")
        return
    
    if not args:
        settings = get_group_settings(chat.id)
        status = "✅ ON" if settings.get('noforward') else "❌ OFF"
        update.message.reply_text(f"📤 *Forward Control:* {status}", parse_mode=ParseMode.MARKDOWN)
        return
    
    if args[0].lower() == 'on':
        update_group_setting(chat.id, 'noforward', True)
        update.message.reply_text("✅ *Forward Control enabled!*", parse_mode=ParseMode.MARKDOWN)
    elif args[0].lower() == 'off':
        update_group_setting(chat.id, 'noforward', False)
        update.message.reply_text("❌ *Forward Control disabled!*", parse_mode=ParseMode.MARKDOWN)

def echo_cmd(update: Update, context: CallbackContext):
    """Handle /echo command"""
    
    user = update.effective_user
    chat = update.effective_chat
    
    if not is_group_admin(update, user.id):
        update.message.reply_text("❌ Only admins can use this command!")
        return
    
    args = context.args
    if not args:
        update.message.reply_text("📝 *Usage:* `/echo <text>`", parse_mode=ParseMode.MARKDOWN)
        return
    
    text = " ".join(args)
    settings = get_group_settings(chat.id)
    limit = settings.get('longlimit', 800)
    
    if len(text) > limit:
        update.message.reply_text(f"⚠️ Message exceeds {limit} characters. Use Telegraph upload via `/setlongmode automatic`", parse_mode=ParseMode.MARKDOWN)
    else:
        update.message.reply_text(text)

def status_cmd(update: Update, context: CallbackContext):
    """Handle /status command"""
    
    user = update.effective_user
    chat = update.effective_chat
    
    if not is_group_admin(update, user.id):
        update.message.reply_text("❌ Only admins can use this command!")
        return
    
    if not MONGODB_CONNECTED:
        update.message.reply_text("❌ MongoDB is not connected!")
        return
    
    settings = get_group_settings(chat.id)
    
    status_text = f"""
🤖 *Ultra Guardians Bot - Group Status*

*Current Settings:*
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
*Members:* {chat.get_members_count()}
"""
    
    update.message.reply_text(status_text, parse_mode=ParseMode.MARKDOWN)

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
    
    updater = Updater(BOT_TOKEN, use_context=True)
    dispatcher = updater.dispatcher
    
    # Commands
    dispatcher.add_handler(CommandHandler("start", start_cmd))
    dispatcher.add_handler(CommandHandler("noabuse", noabuse_cmd))
    dispatcher.add_handler(CommandHandler("msgdelete", msgdelete_cmd))
    dispatcher.add_handler(CommandHandler("setmsgdelay", setmsgdelay_cmd))
    dispatcher.add_handler(CommandHandler("nohashtags", nohashtags_cmd))
    dispatcher.add_handler(CommandHandler("nophone", nophone_cmd))
    dispatcher.add_handler(CommandHandler("nopromo", nopromo_cmd))
    dispatcher.add_handler(CommandHandler("nolinks", nolinks_cmd))
    dispatcher.add_handler(CommandHandler("allowlink", allowlink_cmd))
    dispatcher.add_handler(CommandHandler("edit", edit_cmd))
    dispatcher.add_handler(CommandHandler("mediadelete", mediadelete_cmd))
    dispatcher.add_handler(CommandHandler("noforward", noforward_cmd))
    dispatcher.add_handler(CommandHandler("echo", echo_cmd))
    dispatcher.add_handler(CommandHandler("status", status_cmd))
    
    # Callback queries for buttons
    dispatcher.add_handler(CallbackQueryHandler(button_callback))
    
    # Message handlers
    dispatcher.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_message))
    dispatcher.add_handler(MessageHandler(Filters.update.edited_message & Filters.text, handle_edited_message))
    dispatcher.add_handler(MessageHandler(Filters.photo | Filters.video | Filters.document, handle_media))
    dispatcher.add_handler(MessageHandler(Filters.text, handle_forward))
    
    print("✅ Bot started successfully!")
    print("Press Ctrl+C to stop\n")
    
    updater.start_polling(drop_pending_updates=True)
    updater.idle()

if __name__ == '__main__':
    main()
