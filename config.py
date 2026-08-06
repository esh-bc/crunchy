"""
╔══════════════════════════════════════════════════╗
║   CRUNCHYROLL REFERRAL BOT - CONFIGURATION       ║
║   Developer: @iam_eshh                           ║
║   Bot API: 10.2 (July 2026)                      ║
╚══════════════════════════════════════════════════╝
"""

import os
from dotenv import load_dotenv

load_dotenv()

# ─── BOT TOKEN ───────────────────────────────────────────────────────────────
# Set your token from @BotFather here or in .env
BOT_TOKEN = os.getenv("BOT_TOKEN", "8825885438:AAEGPjnkmlHJB8z1AI_AA2aDwDvzalNfKmM")

# ─── OWNER ID ────────────────────────────────────────────────────────────────
# Your Telegram user ID (super-admin). Get it from @userinfobot
OWNER_ID_DEFAULT = os.getenv("OWNER_ID", "8264404281")

# ─── MONGODB ─────────────────────────────────────────────────────────────────
# MongoDB connection URL — set here or in .env
MONGO_URI = os.getenv(
    "MONGO_URI",
    "mongodb+srv://Esh:1234567890ukwhat@cluster0.mnbnc7a.mongodb.net/?appName=Cluster0"
)
MONGO_DB_NAME = "crunchyroll_bot"

# ─── BOT VERSION ─────────────────────────────────────────────────────────────
BOT_VERSION = "3.1.0"
DEVELOPER = "@iam_eshh"
BOT_NAME = "Crunchyroll Referral Bot"

# ─── DEFAULT POINTS PER REFERRAL ─────────────────────────────────────────────
DEFAULT_REFERRAL_POINTS = 10
DEFAULT_REDEEM_COST = 10

# ─── ACCOUNT REPLACE LIMIT ───────────────────────────────────────────────────
MAX_REPLACEMENTS = 3

# ─── WEB SERVER (for Render + UptimeRobot) ───────────────────────────────────
WEB_HOST = "0.0.0.0"
WEB_PORT = int(os.getenv("PORT", 8080))

# ─── LOGS LIMIT ──────────────────────────────────────────────────────────────
MAX_LOG_LINES = 100

# ─── BUTTON STYLES (Bot API 9.4 - Feb 9 2026) ────────────────────────────────
# Telegram only supports exactly THREE colour styles on InlineKeyboardButton.
# Anything else (warning, info, default, link …) is INVALID and causes a
# BadRequest from the Telegram servers.
class ButtonStyle:
    PRIMARY = "primary"   # Blue  — links, navigation, general actions
    SUCCESS = "success"   # Green — positive / confirm / working
    DANGER  = "danger"    # Red   — destructive / cancel / not-working

# ─── DEFAULT MESSAGE TEMPLATES ───────────────────────────────────────────────
DEFAULT_MESSAGES = {
    "welcome": (
        "🎌 <b>Welcome to {first_name}'s Crunchyroll Hub!</b>\n\n"
        "🍿 Get <b>FREE Crunchyroll Premium</b> accounts by referring friends!\n\n"
        "👤 <b>Your ID:</b> <code>{user_id}</code>\n"
        "💎 <b>Your Points:</b> <code>{points}</code>\n"
        "📦 <b>Stock Available:</b> <code>{stock}</code> accounts\n\n"
        "🔗 <b>Your Referral Link:</b>\n"
        "<code>{referral_link}</code>\n\n"
        "✨ Refer friends to earn points and redeem premium accounts!"
    ),
    "channel_verify": (
        "📢 <b>Join Required Channels!</b>\n\n"
        "To access the bot, please join all the channels below:\n\n"
        "{channels_list}\n\n"
        "After joining, click <b>✅ Verify</b> below!"
    ),
    "main_menu": (
        "🏠 <b>Main Menu</b>\n\n"
        "👋 Hey <b>{first_name}</b>! What would you like to do?\n\n"
        "💎 <b>Points:</b> <code>{points}</code>\n"
        "📦 <b>Stock:</b> <code>{stock}</code> accounts"
    ),
    "withdraw": (
        "🎫 <b>Redeem Crunchyroll Account</b>\n\n"
        "💎 <b>Your Points:</b> <code>{points}</code>\n"
        "💸 <b>Cost:</b> <code>{cost}</code> points\n\n"
        "Click <b>🎁 Redeem Now</b> to get your account!"
    ),
    "account_delivered": (
        "✅ <b>Your Crunchyroll Account!</b>\n\n"
        "📧 <b>Email:</b> <code>{email}</code>\n"
        "🔑 <b>Password:</b> <code>{password}</code>\n\n"
        "⚠️ <b>Instructions:</b>\n"
        "• Change password after login\n"
        "• Don't share this account\n"
        "• Log in at crunchyroll.com\n\n"
        "Is the account working?"
    ),
    "refer": (
        "🔗 <b>Your Referral Panel</b>\n\n"
        "👥 <b>Total Referrals:</b> <code>{total_refs}</code>\n"
        "💎 <b>Points Earned:</b> <code>{points}</code>\n"
        "🏆 <b>Your Rank:</b> <code>#{rank}</code>\n\n"
        "📤 <b>Share your link:</b>\n"
        "<code>{referral_link}</code>\n\n"
        "💡 Earn <b>{points_per_ref}</b> points per referral!"
    ),
    "leaderboard": (
        "🏆 <b>Top Referrers</b>\n\n"
        "{leaderboard_list}\n\n"
        "👤 <b>Your Rank:</b> #{your_rank}\n"
        "👥 <b>Your Referrals:</b> {your_refs}"
    ),
    "stock": (
        "📦 <b>Account Stock</b>\n\n"
        "🎫 <b>Available Accounts:</b> <code>{stock}</code>\n"
        "💎 <b>Redeem Cost:</b> <code>{cost}</code> points\n\n"
        "Stock is updated regularly. Check back often!"
    ),
    "proof_caption": (
        "✅ <b>Working Account Proof</b>\n\n"
        "👤 <b>User:</b> {mention}\n"
        "🆔 <b>ID:</b> <code>{user_id}</code>\n"
        "📅 <b>Date:</b> {date}\n"
        "💎 <b>Points Spent:</b> {cost}"
    ),
    "screenshot_request": (
        "📸 <b>Upload Screenshot</b>\n\n"
        "Please send a screenshot of the working account to confirm redemption.\n\n"
        "⚠️ Until you submit the screenshot, you cannot redeem another account."
    ),
    "not_working": (
        "❌ <b>Account Not Working</b>\n\n"
        "We're giving you a replacement account. Replacements left: <code>{left}</code>"
    ),
    "no_replacements": (
        "⚠️ <b>Maximum Replacements Reached</b>\n\n"
        "You've used all {max} replacement attempts.\n"
        "Please contact support if you're still having issues."
    ),
    "no_stock": (
        "😔 <b>Out of Stock</b>\n\n"
        "No accounts are available right now.\n"
        "Please check back later or refer more friends!"
    ),
    "insufficient_points": (
        "💔 <b>Not Enough Points</b>\n\n"
        "💎 <b>Your Points:</b> <code>{points}</code>\n"
        "💸 <b>Required:</b> <code>{cost}</code> points\n\n"
        "Keep referring to earn more points! 🚀"
    ),
    "already_pending_screenshot": (
        "📸 <b>Pending Screenshot</b>\n\n"
        "You have a pending screenshot submission.\n"
        "Please send your screenshot first before redeeming another account."
    ),
    "admin_welcome": (
        "🛡️ <b>Admin Panel</b>\n\n"
        "Welcome, <b>{first_name}</b>!\n\n"
        "📊 <b>Quick Stats:</b>\n"
        "👥 Total Users: <code>{total_users}</code>\n"
        "📦 Stock: <code>{stock}</code> accounts\n"
        "🎫 Total Redeems: <code>{total_redeems}</code>\n"
        "💎 Total Referrals: <code>{total_refs}</code>"
    ),
    "redeem_code_success": (
        "🎉 <b>Code Redeemed!</b>\n\n"
        "🎟 <b>Code:</b> <code>{code}</code>\n"
        "💎 <b>Points Earned:</b> +<code>{points}</code>\n\n"
        "Your new total: <code>{total_points}</code> points 🚀"
    ),
    "redeem_code_invalid": (
        "❌ <b>Invalid Code</b>\n\n"
        "The code <code>{code}</code> is not valid or has already been used.\n\n"
        "Double-check the code and try again!"
    ),
    "redeem_code_already_used": (
        "⚠️ <b>Code Already Used</b>\n\n"
        "You have already redeemed the code <code>{code}</code>.\n\n"
        "Each code can only be used once per user."
    ),
    "redeem_code_exhausted": (
        "😔 <b>Code Exhausted</b>\n\n"
        "The code <code>{code}</code> has reached its maximum uses.\n\n"
        "Ask the admin for a new code!"
    ),
}

# ─── DEFAULT BUTTON LABELS ────────────────────────────────────────────────────
DEFAULT_BUTTONS = {
    "join_channel": "📢 Join Channel",
    "verify": "✅ Verify Membership",
    "withdraw": "🎫 Redeem Account",
    "refer": "🔗 Refer & Earn",
    "leaderboard": "🏆 Leaderboard",
    "stock": "📦 Check Stock",
    "proof": "📸 Proof Wall",
    "working": "✅ Working!",
    "not_working": "❌ Not Working",
    "back": "◀️ Back",
    "confirm_redeem": "🎁 Redeem Now",
}
