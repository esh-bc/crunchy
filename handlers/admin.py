"""
╔══════════════════════════════════════════════════╗
║   ADMIN PANEL HANDLERS                           ║
║   NEW: Broadcast · Bot Settings · Token Change   ║
║   Account health tracking support               ║
║   Developer: @iam_eshh                           ║
╚══════════════════════════════════════════════════╝
"""

import asyncio
import html as html_module
import logging
import os
import psutil
import sys
import time
from datetime import datetime
from io import BytesIO

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, Bot, MessageEntity
from telegram.ext import ContextTypes
from telegram.constants import ParseMode
from telegram.error import TelegramError


# ─── PREMIUM EMOJI HELPER ────────────────────────────────────────────────────

def _utf16_len(text: str) -> int:
    """Return the UTF-16 code-unit length of a Python string."""
    return len(text.encode("utf-16-le")) // 2


def inject_custom_emoji_html(text: str, entities) -> str:
    """
    Replace characters at custom_emoji entity positions with
    <tg-emoji emoji-id="ID">char</tg-emoji> HTML tags so that
    the message can be sent with parse_mode=HTML and Telegram
    renders the premium animated emoji correctly.

    Telegram uses UTF-16 code-unit offsets; we convert carefully.
    Replacements are applied right-to-left so earlier offsets stay valid.
    """
    if not text or not entities:
        return text

    custom = [
        e for e in entities
        if getattr(e, "type", None) == MessageEntity.CUSTOM_EMOJI
        and getattr(e, "custom_emoji_id", None)
    ]
    if not custom:
        return text

    # Sort descending by offset so we replace from the end
    custom.sort(key=lambda e: e.offset, reverse=True)

    # Build a UTF-16 code-unit array for index mapping
    utf16_units = list(text.encode("utf-16-le"))  # raw bytes, 2 per unit

    for entity in custom:
        emoji_id = entity.custom_emoji_id
        # Convert UTF-16 offset/length to Python char indices
        try:
            prefix_bytes = bytes(utf16_units[: entity.offset * 2])
            prefix_str = prefix_bytes.decode("utf-16-le")
            start_idx = len(prefix_str)

            span_bytes = bytes(utf16_units[entity.offset * 2: (entity.offset + entity.length) * 2])
            emoji_char = span_bytes.decode("utf-16-le")
            end_idx = start_idx + len(emoji_char)

            replacement = f'<tg-emoji emoji-id="{emoji_id}">{emoji_char}</tg-emoji>'
            text = text[:start_idx] + replacement + text[end_idx:]
            # Rebuild UTF-16 units after mutation
            utf16_units = list(text.encode("utf-16-le"))
        except Exception:
            pass  # Leave this entity unchanged on any encoding error

    return text

import database as db
import keyboards as kb
from keyboards import btn
from templates import render
from sender import send_rendered
from config import BOT_VERSION, DEVELOPER, MAX_LOG_LINES

logger = logging.getLogger(__name__)

# ─── CONVERSATION STATES ─────────────────────────────────────────────────────
(
    STATE_IDLE,                 # 0
    STATE_AWAIT_CHANNEL_TYPE,   # 1
    STATE_AWAIT_PUBLIC_USERNAME,# 2
    STATE_AWAIT_PRIVATE_ID,     # 3
    STATE_AWAIT_ACCOUNTS_FILE,  # 4
    STATE_AWAIT_MANUAL_ACCOUNTS,# 5
    STATE_AWAIT_NEW_MESSAGE,    # 6
    STATE_AWAIT_NEW_BUTTON,     # 7
    STATE_AWAIT_PROOF_CHANNEL,  # 8
    STATE_AWAIT_NEW_ADMIN,      # 9
    STATE_AWAIT_EDIT_MSG_KEY,   # 10
    STATE_AWAIT_EDIT_BTN_KEY,   # 11
    STATE_AWAIT_CODE_POINTS,    # 12
    STATE_AWAIT_CODE_USES,      # 13
    STATE_AWAIT_BROADCAST_MSG,  # 14  NEW
    STATE_AWAIT_BOT_TOKEN,      # 15  NEW
    STATE_AWAIT_REF_POINTS,     # 16  NEW
    STATE_AWAIT_REDEEM_COST,    # 17  NEW
) = range(18)

BOT_START_TIME = time.time()


# ─── GUARD ────────────────────────────────────────────────────────────────────

async def _guard(update: Update) -> bool:
    user = update.effective_user
    if not await db.is_admin(user.id):
        if update.callback_query:
            await update.callback_query.answer("⛔ Access denied.", show_alert=True)
        elif update.message:
            await update.message.reply_text(
                "⛔ <b>Access Denied.</b>\nAdmin only.", parse_mode=ParseMode.HTML
            )
        return False
    return True


# ─── /admin ───────────────────────────────────────────────────────────────────

async def cmd_admin(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not await db.is_admin(user.id):
        await update.message.reply_text("⛔ <b>Access Denied.</b>", parse_mode=ParseMode.HTML)
        return

    total_users   = await db.get_total_users()
    stock         = await db.get_stock_count()
    total_redeems = await db.get_total_redeems()
    total_refs    = await db.get_total_referrals()

    rendered = await render(
        "admin_welcome", user,
        extra={
            "{total_users}":   str(total_users),
            "{stock}":         str(stock),
            "{total_redeems}": str(total_redeems),
            "{total_refs}":    str(total_refs),
        }
    )
    markup = await kb.admin_menu_keyboard()
    await send_rendered(ctx.bot, update.message.chat_id, rendered, markup)
    await db.write_log("INFO", f"Admin {user.id} opened admin panel")


async def cb_admin_menu(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not await _guard(update):
        return
    await query.answer()
    user = update.effective_user
    # Reset any lingering state
    ctx.user_data["admin_state"] = STATE_IDLE

    total_users   = await db.get_total_users()
    stock         = await db.get_stock_count()
    total_redeems = await db.get_total_redeems()
    total_refs    = await db.get_total_referrals()

    rendered = await render(
        "admin_welcome", user,
        extra={
            "{total_users}":   str(total_users),
            "{stock}":         str(stock),
            "{total_redeems}": str(total_redeems),
            "{total_refs}":    str(total_refs),
        }
    )
    markup = await kb.admin_menu_keyboard()
    try:
        await query.edit_message_text(
            text=rendered["content"],
            parse_mode=ParseMode.HTML,
            reply_markup=markup,
        )
    except Exception:
        await send_rendered(ctx.bot, query.message.chat_id, rendered, markup)


# ─── CHANNEL MANAGER ─────────────────────────────────────────────────────────

async def cb_admin_channels(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not await _guard(update):
        return
    await query.answer()

    channels = await db.get_all_channels()
    markup = await kb.channel_manager_keyboard(channels)
    count = len(channels)
    try:
        await query.edit_message_text(
            f"📢 <b>Channel Manager</b>\n\n"
            f"📌 <b>{count}</b> channel(s) currently required for verification.\n"
            f"Add or remove mandatory join channels.",
            parse_mode=ParseMode.HTML,
            reply_markup=markup,
        )
    except Exception:
        pass


async def cb_add_channel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not await _guard(update):
        return
    await query.answer()

    markup = await kb.add_channel_type_keyboard()
    try:
        await query.edit_message_text(
            "📢 <b>Add Channel</b>\n\nIs this a public or private channel?",
            parse_mode=ParseMode.HTML,
            reply_markup=markup,
        )
    except Exception:
        pass
    ctx.user_data["admin_state"] = STATE_AWAIT_CHANNEL_TYPE


async def cb_add_chan_public(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not await _guard(update):
        return
    await query.answer()

    ctx.user_data["chan_type"] = "public"
    ctx.user_data["admin_state"] = STATE_AWAIT_PUBLIC_USERNAME

    try:
        await query.edit_message_text(
            "📢 <b>Public Channel</b>\n\n"
            "Send the channel <b>username</b>\n"
            "Example: <code>@mychannel</code> or <code>mychannel</code>",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([
                [btn("❌ Cancel", "admin_channels", style="danger")]
            ]),
        )
    except Exception:
        pass


async def cb_add_chan_private(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not await _guard(update):
        return
    await query.answer()

    ctx.user_data["chan_type"] = "private"
    ctx.user_data["admin_state"] = STATE_AWAIT_PRIVATE_ID

    try:
        await query.edit_message_text(
            "🔒 <b>Private Channel</b>\n\n"
            "Send the channel <b>ID</b> (e.g. <code>-1001234567890</code>).\n\n"
            "💡 Make sure the bot is an <b>admin</b> in the channel!",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([
                [btn("❌ Cancel", "admin_channels", style="danger")]
            ]),
        )
    except Exception:
        pass


async def cb_del_channel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not await _guard(update):
        return

    chat_id = query.data.split(":", 1)[1]
    await db.remove_channel(chat_id)
    await query.answer("✅ Channel removed!", show_alert=True)

    channels = await db.get_all_channels()
    markup = await kb.channel_manager_keyboard(channels)
    try:
        await query.edit_message_text(
            f"📢 <b>Channel Manager</b>\n\n{len(channels)} channel(s) required.",
            parse_mode=ParseMode.HTML,
            reply_markup=markup,
        )
    except Exception:
        pass
    await db.write_log("INFO", f"Admin removed channel {chat_id}")


# ─── ACCOUNT MANAGER ─────────────────────────────────────────────────────────

async def cb_admin_accounts(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not await _guard(update):
        return
    await query.answer()

    stock = await db.get_stock_count()
    markup = await kb.account_manager_keyboard()
    try:
        await query.edit_message_text(
            f"📦 <b>Account Manager</b>\n\n"
            f"📊 Available stock: <code>{stock}</code> accounts\n\n"
            f"<i>Working accounts (confirmed by users) are prioritised in delivery.\n"
            f"Broken accounts are automatically discarded.</i>",
            parse_mode=ParseMode.HTML,
            reply_markup=markup,
        )
    except Exception:
        pass


async def cb_upload_accounts(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not await _guard(update):
        return
    await query.answer()
    ctx.user_data["admin_state"] = STATE_AWAIT_ACCOUNTS_FILE

    try:
        await query.edit_message_text(
            "📁 <b>Upload Accounts TXT</b>\n\n"
            "Send a <b>.txt</b> file with one account per line:\n"
            "<code>email:password</code>\n\n"
            "Example:\n"
            "<code>user@email.com:password123\n"
            "user2@email.com:pass456</code>",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([
                [btn("❌ Cancel", "admin_accounts", style="danger")]
            ]),
        )
    except Exception:
        pass


async def cb_manual_accounts(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not await _guard(update):
        return
    await query.answer()
    ctx.user_data["admin_state"] = STATE_AWAIT_MANUAL_ACCOUNTS

    try:
        await query.edit_message_text(
            "✏️ <b>Manual Account Input</b>\n\n"
            "Send accounts one per line in format:\n"
            "<code>email:password</code>\n\n"
            "Example:\n"
            "<code>user@email.com:password123\n"
            "user2@email.com:pass456</code>",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([
                [btn("❌ Cancel", "admin_accounts", style="danger")]
            ]),
        )
    except Exception:
        pass


async def cb_view_stock(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not await _guard(update):
        return
    stock = await db.get_stock_count()
    await query.answer(f"📦 Stock: {stock} accounts available", show_alert=True)


async def cb_clear_accounts(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not await _guard(update):
        return
    await query.answer()

    markup = await kb.confirm_keyboard("confirm_clear_accounts", "admin_accounts")
    try:
        await query.edit_message_text(
            "⚠️ <b>Clear Untested Stock?</b>\n\n"
            "This will delete all <b>fresh/untested</b> accounts.\n"
            "Confirmed-working accounts are preserved.",
            parse_mode=ParseMode.HTML,
            reply_markup=markup,
        )
    except Exception:
        pass


async def cb_confirm_clear_accounts(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not await _guard(update):
        return
    await query.answer()

    deleted = await db.clear_unused_accounts()
    stock = await db.get_stock_count()
    await query.edit_message_text(
        f"✅ <b>Stock cleared!</b>\n"
        f"🗑 Deleted: <code>{deleted}</code> untested accounts\n"
        f"📦 Working accounts remaining: <code>{stock}</code>",
        parse_mode=ParseMode.HTML,
        reply_markup=await kb.admin_menu_keyboard(),
    )
    await db.write_log("INFO", f"Admin cleared {deleted} untested accounts")


# ─── MESSAGE EDITOR ──────────────────────────────────────────────────────────

async def cb_admin_messages(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not await _guard(update):
        return
    await query.answer()

    messages = await db.get_all_messages()
    markup = await kb.message_list_keyboard(messages)
    try:
        await query.edit_message_text(
            "✏️ <b>Message Editor</b>\n\n"
            "All messages (including photos/captions) are stored in MongoDB.\n"
            "They survive hosting changes automatically.\n\n"
            "Select a message to edit:",
            parse_mode=ParseMode.HTML,
            reply_markup=markup,
        )
    except Exception:
        pass


async def cb_edit_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not await _guard(update):
        return
    await query.answer()

    key = query.data.split(":", 1)[1]
    ctx.user_data["editing_msg_key"] = key
    ctx.user_data["admin_state"]     = STATE_AWAIT_NEW_MESSAGE

    current = await db.get_message(key)
    # Escape the stored HTML so it shows as safe plain text in the preview.
    # Truncating raw HTML mid-tag produces invalid markup that Telegram rejects.
    raw_preview = current.get("content") or "(no text)"
    preview = html_module.escape(raw_preview)
    if len(preview) > 300:
        preview = preview[:300] + "…"

    media_info = ""
    if current.get("media_file"):
        media_info = f"\n📎 Current media: <b>{html_module.escape(current.get('media_type', 'unknown'))}</b>"

    prompt = (
        f"✏️ <b>Editing:</b> <code>{html_module.escape(key)}</code>\n\n"
        f"📝 <b>Current content:</b>\n<blockquote>{preview}</blockquote>"
        f"{media_info}\n\n"
        f"Send the new message (text, photo+caption, or video+caption).\n"
        f"Supports HTML formatting and placeholders."
    )
    markup = InlineKeyboardMarkup([[btn("❌ Cancel", "admin_messages", style="danger")]])

    try:
        await query.edit_message_text(prompt, parse_mode=ParseMode.HTML, reply_markup=markup)
    except Exception:
        # Fallback: send a fresh message (e.g. if the current message is media)
        try:
            await query.message.reply_text(prompt, parse_mode=ParseMode.HTML, reply_markup=markup)
        except Exception:
            pass


# ─── BUTTON EDITOR ────────────────────────────────────────────────────────────

async def cb_admin_buttons(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not await _guard(update):
        return
    await query.answer()

    markup = await kb.button_list_keyboard()
    try:
        await query.edit_message_text(
            "🔘 <b>Button Editor</b>\n\n"
            "Select a button to edit its label text.\n"
            "Changes are stored in MongoDB.",
            parse_mode=ParseMode.HTML,
            reply_markup=markup,
        )
    except Exception:
        pass


async def cb_edit_button(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not await _guard(update):
        return
    await query.answer()

    key = query.data.split(":", 1)[1]
    ctx.user_data["editing_btn_key"] = key
    ctx.user_data["admin_state"]     = STATE_AWAIT_NEW_BUTTON

    current = await db.get_button(key)
    current_emoji_id = current.get("emoji_id")
    # Render the emoji visually if we have an ID; Telegram ignores the inner char
    if current_emoji_id:
        emoji_preview = f' <tg-emoji emoji-id="{current_emoji_id}">⭐</tg-emoji>'
    else:
        emoji_preview = " <i>none</i>"
    try:
        await query.edit_message_text(
            f"🔘 <b>Editing Button:</b> <code>{key}</code>\n\n"
            f"📝 Current label: <code>{current.get('label', '')}</code>\n"
            f"🌟 Current premium emoji:{emoji_preview}\n\n"
            f"Send the new button label.\n\n"
            f"<b>To add a premium emoji icon:</b> just include a premium emoji "
            f"anywhere in your message — it will be detected automatically.\n\n"
            f"<b>To remove the emoji:</b> send label + <code>emoji_id:none</code>\n"
            f"<i>Sending only the label preserves the existing emoji.</i>",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([
                [btn("❌ Cancel", "admin_buttons", style="danger")]
            ]),
        )
    except Exception:
        pass


# ─── PROOF CHANNEL ───────────────────────────────────────────────────────────

async def cb_admin_proof(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not await _guard(update):
        return
    await query.answer()

    current = await db.get_setting("proof_channel", "Not set")
    ctx.user_data["admin_state"] = STATE_AWAIT_PROOF_CHANNEL

    try:
        await query.edit_message_text(
            f"📸 <b>Proof Channel</b>\n\n"
            f"📌 Current: <code>{current}</code>\n\n"
            f"Send the channel ID or @username where screenshots will be forwarded:",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([
                [btn("❌ Cancel", "admin_menu", style="danger")]
            ]),
        )
    except Exception:
        pass


# ─── ADMIN MANAGER ────────────────────────────────────────────────────────────

async def cb_admin_admins(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not await _guard(update):
        return
    await query.answer()

    admins = await db.get_all_admins()
    markup = await kb.admin_manager_keyboard(admins)
    try:
        await query.edit_message_text(
            f"👥 <b>Admin Manager</b>\n\n"
            f"📋 <b>{len(admins)}</b> admin(s) configured.\n"
            f"All admin IDs are stored in MongoDB.",
            parse_mode=ParseMode.HTML,
            reply_markup=markup,
        )
    except Exception:
        pass


async def cb_add_admin(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not await _guard(update):
        return
    await query.answer()
    ctx.user_data["admin_state"] = STATE_AWAIT_NEW_ADMIN

    try:
        await query.edit_message_text(
            "➕ <b>Add Admin</b>\n\n"
            "Send the Telegram <b>user ID</b> of the new admin:\n\n"
            "💡 Users can get their ID from @userinfobot",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([
                [btn("❌ Cancel", "admin_admins", style="danger")]
            ]),
        )
    except Exception:
        pass


async def cb_admin_quick_add_admin(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Quick Add Admin shortcut from main menu."""
    query = update.callback_query
    if not await _guard(update):
        return
    await query.answer()
    ctx.user_data["admin_state"] = STATE_AWAIT_NEW_ADMIN
    ctx.user_data["admin_add_return"] = "admin_menu"

    try:
        await query.edit_message_text(
            "➕ <b>Quick Add Admin</b>\n\n"
            "Send the Telegram <b>user ID</b> of the new admin:\n\n"
            "💡 Users can get their ID from @userinfobot\n"
            "🔐 They immediately gain full admin panel access.",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([
                [btn("❌ Cancel", "admin_menu", style="danger")]
            ]),
        )
    except Exception:
        pass


async def cb_remove_admin(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not await _guard(update):
        return

    uid = int(query.data.split(":", 1)[1])
    owner_id = await db.get_setting("owner_id", "")

    if str(uid) == str(owner_id):
        await query.answer("⛔ Cannot remove the owner!", show_alert=True)
        return

    await db.remove_admin(uid)
    await query.answer(f"✅ Admin {uid} removed.", show_alert=True)
    await db.write_log("INFO", f"Admin removed: {uid}")

    admins = await db.get_all_admins()
    markup = await kb.admin_manager_keyboard(admins)
    try:
        await query.edit_message_text(
            f"👥 <b>Admin Manager</b>\n\n{len(admins)} admin(s) configured.",
            parse_mode=ParseMode.HTML,
            reply_markup=markup,
        )
    except Exception:
        pass


# ─── BOT SETTINGS ─────────────────────────────────────────────────────────────

async def cb_admin_settings(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Bot-wide settings panel."""
    query = update.callback_query
    if not await _guard(update):
        return
    await query.answer()

    ref_pts   = await db.get_setting("referral_points", "10")
    redeem_cost = await db.get_setting("redeem_cost", "10")
    token_preview = (await db.get_setting("bot_token", ""))[:20] + "…"

    markup = await kb.bot_settings_keyboard(ref_pts, redeem_cost)
    try:
        await query.edit_message_text(
            f"⚙️ <b>Bot Settings</b>\n\n"
            f"🔑 <b>Bot Token:</b> <code>{token_preview}</code>\n"
            f"💎 <b>Referral Points:</b> <code>{ref_pts}</code> per referral\n"
            f"💸 <b>Redeem Cost:</b> <code>{redeem_cost}</code> points\n\n"
            f"<i>All settings are stored in MongoDB — safe across hosting changes.</i>",
            parse_mode=ParseMode.HTML,
            reply_markup=markup,
        )
    except Exception:
        pass


async def cb_admin_change_token(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Start the bot token change flow."""
    query = update.callback_query
    if not await _guard(update):
        return
    await query.answer()
    ctx.user_data["admin_state"] = STATE_AWAIT_BOT_TOKEN

    try:
        await query.edit_message_text(
            "🔑 <b>Change Bot Token</b>\n\n"
            "Send the new bot token from @BotFather:\n\n"
            "⚠️ <b>Warning:</b> The bot will validate and then restart automatically.\n"
            "All settings, users, and accounts remain intact in MongoDB.",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([
                [btn("❌ Cancel", "admin_settings", style="danger")]
            ]),
        )
    except Exception:
        pass


async def cb_admin_set_ref_pts(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Change referral points per referral."""
    query = update.callback_query
    if not await _guard(update):
        return
    await query.answer()
    ctx.user_data["admin_state"] = STATE_AWAIT_REF_POINTS

    current = await db.get_setting("referral_points", "10")
    try:
        await query.edit_message_text(
            f"💎 <b>Referral Points</b>\n\n"
            f"Current: <code>{current}</code> points per referral\n\n"
            f"Send the new value (e.g. <code>15</code>):",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([
                [btn("❌ Cancel", "admin_settings", style="danger")]
            ]),
        )
    except Exception:
        pass


async def cb_admin_set_redeem_cost(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Change account redeem cost."""
    query = update.callback_query
    if not await _guard(update):
        return
    await query.answer()
    ctx.user_data["admin_state"] = STATE_AWAIT_REDEEM_COST

    current = await db.get_setting("redeem_cost", "10")
    try:
        await query.edit_message_text(
            f"💸 <b>Redeem Cost</b>\n\n"
            f"Current: <code>{current}</code> points per account\n\n"
            f"Send the new value (e.g. <code>20</code>):",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([
                [btn("❌ Cancel", "admin_settings", style="danger")]
            ]),
        )
    except Exception:
        pass


# ─── BROADCAST ────────────────────────────────────────────────────────────────

async def cb_admin_broadcast(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Broadcast panel entry."""
    query = update.callback_query
    if not await _guard(update):
        return
    await query.answer()

    total = await db.get_total_users()
    markup = await kb.broadcast_menu_keyboard()
    try:
        await query.edit_message_text(
            f"📣 <b>Broadcast</b>\n\n"
            f"👥 Will reach: <code>{total}</code> users\n\n"
            f"Click <b>Send Broadcast Now</b> then send your message "
            f"(text, photo+caption, or video+caption).\n\n"
            f"⚠️ This cannot be undone. Use carefully.",
            parse_mode=ParseMode.HTML,
            reply_markup=markup,
        )
    except Exception:
        pass


async def cb_broadcast_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Set admin state to await broadcast message."""
    query = update.callback_query
    if not await _guard(update):
        return
    await query.answer()
    ctx.user_data["admin_state"] = STATE_AWAIT_BROADCAST_MSG

    try:
        await query.edit_message_text(
            "📣 <b>Compose Broadcast</b>\n\n"
            "Send your message now (text, photo+caption, or video+caption).\n\n"
            "💡 HTML formatting is supported.",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([
                [btn("❌ Cancel", "admin_broadcast", style="danger")]
            ]),
        )
    except Exception:
        pass


async def _do_broadcast(bot, user_ids: list[int], message) -> tuple[int, int]:
    """
    Send a Telegram message object to all user IDs.
    Returns (sent_count, failed_count).
    Rate-limited: 25 per second max (Telegram allows ~30).
    """
    sent = 0
    failed = 0
    sem = asyncio.Semaphore(20)  # max 20 concurrent sends

    async def _send_one(uid: int):
        nonlocal sent, failed
        async with sem:
            try:
                if message.photo:
                    await bot.send_photo(
                        chat_id=uid,
                        photo=message.photo[-1].file_id,
                        caption=message.caption or "",
                        parse_mode=ParseMode.HTML,
                    )
                elif message.video:
                    await bot.send_video(
                        chat_id=uid,
                        video=message.video.file_id,
                        caption=message.caption or "",
                        parse_mode=ParseMode.HTML,
                    )
                elif message.animation:
                    await bot.send_animation(
                        chat_id=uid,
                        animation=message.animation.file_id,
                        caption=message.caption or "",
                        parse_mode=ParseMode.HTML,
                    )
                elif message.text:
                    await bot.send_message(
                        chat_id=uid,
                        text=message.text,
                        parse_mode=ParseMode.HTML,
                    )
                sent += 1
            except TelegramError:
                failed += 1
            except Exception:
                failed += 1
            await asyncio.sleep(0.04)  # ~25/sec throttle

    await asyncio.gather(*[_send_one(uid) for uid in user_ids])
    return sent, failed


# ─── GENERATE REDEMPTION CODE ─────────────────────────────────────────────────

async def cb_admin_gen_code(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not await _guard(update):
        return
    await query.answer()

    try:
        await query.edit_message_text(
            "🎟 <b>Redemption Code Manager</b>\n\n"
            "Generate unique codes that users redeem with <code>/redeem CODE</code> "
            "to earn points instantly.\n\n"
            "• Each code has a configurable points value\n"
            "• Set max uses (1 = single use, 9999 = unlimited)\n"
            "• Users can only redeem each code once",
            parse_mode=ParseMode.HTML,
            reply_markup=await kb.gen_code_menu_keyboard(),
        )
    except Exception:
        pass


async def cb_gen_code_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not await _guard(update):
        return
    await query.answer()
    ctx.user_data["admin_state"] = STATE_AWAIT_CODE_POINTS

    try:
        await query.edit_message_text(
            "🎟 <b>Generate Redemption Code</b>\n\n"
            "📌 <b>Step 1 of 2</b>\n\n"
            "How many <b>points</b> should this code give per user?\n\n"
            "Send a number (e.g. <code>50</code>):",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([
                [btn("❌ Cancel", "admin_gen_code", style="danger")]
            ]),
        )
    except Exception:
        pass


async def cb_list_codes(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not await _guard(update):
        return
    await query.answer()

    codes = await db.get_all_redeem_codes(limit=25)
    markup = await kb.code_list_keyboard(codes)
    active_count = sum(1 for c in codes if c.get("is_active"))

    try:
        await query.edit_message_text(
            f"📋 <b>All Redemption Codes</b>\n\n"
            f"✅ Active: <code>{active_count}</code>  |  📦 Total: <code>{len(codes)}</code>\n\n"
            f"<i>Format: STATUS CODE • POINTS pts • USES/MAX</i>",
            parse_mode=ParseMode.HTML,
            reply_markup=markup,
        )
    except Exception:
        pass


async def cb_del_code(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not await _guard(update):
        return

    code_id = int(query.data.split(":", 1)[1])
    await db.delete_redeem_code(code_id)
    await query.answer("🗑 Code deleted!", show_alert=True)
    await db.write_log("INFO", f"Admin deleted redemption code ID {code_id}")

    codes = await db.get_all_redeem_codes(limit=25)
    markup = await kb.code_list_keyboard(codes)
    active_count = sum(1 for c in codes if c.get("is_active"))
    try:
        await query.edit_message_text(
            f"📋 <b>All Redemption Codes</b>\n\n"
            f"✅ Active: <code>{active_count}</code>  |  📦 Total: <code>{len(codes)}</code>\n\n"
            f"<i>Format: STATUS CODE • POINTS pts • USES/MAX</i>",
            parse_mode=ParseMode.HTML,
            reply_markup=markup,
        )
    except Exception:
        pass


# ─── LOGS ─────────────────────────────────────────────────────────────────────

async def cb_admin_logs(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not await _guard(update):
        return
    await query.answer("⏳ Generating log file…")

    logs = await db.get_logs(MAX_LOG_LINES)
    lines = []
    for log in reversed(logs):
        lines.append(f"[{log['timestamp']}] [{log['level']}] {log['message']}")

    content = "\n".join(lines) or "No logs available."
    buf = BytesIO(content.encode("utf-8"))
    buf.name = f"bot_logs_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"

    await ctx.bot.send_document(
        chat_id=query.message.chat_id,
        document=buf,
        filename=buf.name,
        caption="📋 <b>Bot Logs</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=await kb.admin_menu_keyboard(),
    )


# ─── SYSTEM INFO ──────────────────────────────────────────────────────────────

async def cb_admin_system(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not await _guard(update):
        return
    await query.answer()

    uptime_sec = int(time.time() - BOT_START_TIME)
    hours   = uptime_sec // 3600
    minutes = (uptime_sec % 3600) // 60
    secs    = uptime_sec % 60

    cpu = psutil.cpu_percent(interval=0.5)
    mem = psutil.virtual_memory()

    total_users   = await db.get_total_users()
    stock         = await db.get_stock_count()
    total_redeems = await db.get_total_redeems()
    total_refs    = await db.get_total_referrals()
    active_codes  = len([c for c in await db.get_all_redeem_codes(50) if c.get("is_active")])

    try:
        await query.edit_message_text(
            f"📊 <b>System Information</b>\n\n"
            f"🤖 <b>Version:</b> <code>{BOT_VERSION}</code>\n"
            f"👨‍💻 <b>Developer:</b> {DEVELOPER}\n\n"
            f"⏱ <b>Uptime:</b> {hours:02d}h {minutes:02d}m {secs:02d}s\n"
            f"💻 <b>CPU:</b> {cpu:.1f}%\n"
            f"🧠 <b>RAM:</b> {mem.percent:.1f}% "
            f"({mem.used // 1024 // 1024}MB / {mem.total // 1024 // 1024}MB)\n\n"
            f"📈 <b>Stats:</b>\n"
            f"👥 Users: <code>{total_users}</code>\n"
            f"📦 Stock: <code>{stock}</code>\n"
            f"🎫 Redeems: <code>{total_redeems}</code>\n"
            f"🔗 Referrals: <code>{total_refs}</code>\n"
            f"🎟 Active Codes: <code>{active_codes}</code>",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([
                [btn("🔄 Refresh", "admin_system", style="success")],
                [btn("◀️ Back",    "admin_menu",   style="primary")],
            ]),
        )
    except Exception:
        pass


# ─── NOOP ─────────────────────────────────────────────────────────────────────

async def cb_noop(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()


# ─── CENTRAL TEXT HANDLER ────────────────────────────────────────────────────

async def handle_admin_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Central text/media handler for all admin conversation states."""
    user = update.effective_user
    if not await db.is_admin(user.id):
        return

    state = ctx.user_data.get("admin_state", STATE_IDLE)
    text  = update.message.text.strip() if update.message and update.message.text else ""

    # ── Add public channel ────────────────────────────────────────────────────
    if state == STATE_AWAIT_PUBLIC_USERNAME:
        username = text.lstrip("@")
        try:
            chat = await ctx.bot.get_chat(f"@{username}")
            invite = f"https://t.me/{username}"
            await db.add_channel(str(chat.id), username, chat.title or username, "public", invite)
            await update.message.reply_text(
                f"✅ <b>Channel added!</b>\n\n"
                f"📢 <b>{chat.title or username}</b>\n"
                f"🆔 ID: <code>{chat.id}</code>",
                parse_mode=ParseMode.HTML,
                reply_markup=await kb.admin_menu_keyboard(),
            )
            await db.write_log("INFO", f"Admin added public channel @{username}")
        except Exception as e:
            await update.message.reply_text(
                f"❌ <b>Error:</b> {e}\n\nMake sure the bot is in the channel.",
                parse_mode=ParseMode.HTML,
            )
        ctx.user_data["admin_state"] = STATE_IDLE

    # ── Add private channel ───────────────────────────────────────────────────
    elif state == STATE_AWAIT_PRIVATE_ID:
        try:
            chat_id_val = int(text)
            chat = await ctx.bot.get_chat(chat_id_val)
            try:
                invite = await ctx.bot.export_chat_invite_link(chat_id_val)
            except Exception:
                invite = ""
            await db.add_channel(
                str(chat_id_val), "", chat.title or str(chat_id_val), "private", invite
            )
            await update.message.reply_text(
                f"✅ <b>Private channel added!</b>\n\n"
                f"📢 <b>{chat.title}</b>\n"
                f"🆔 ID: <code>{chat_id_val}</code>\n"
                f"🔗 Invite: {invite or 'Could not generate'}",
                parse_mode=ParseMode.HTML,
                reply_markup=await kb.admin_menu_keyboard(),
            )
            await db.write_log("INFO", f"Admin added private channel {chat_id_val}")
        except Exception as e:
            await update.message.reply_text(
                f"❌ <b>Error:</b> {e}\n\nMake sure the bot is admin in the channel.",
                parse_mode=ParseMode.HTML,
            )
        ctx.user_data["admin_state"] = STATE_IDLE

    # ── Manual accounts input ─────────────────────────────────────────────────
    elif state == STATE_AWAIT_MANUAL_ACCOUNTS:
        lines = text.split("\n")
        accounts = []
        errors   = []
        for line in lines:
            line = line.strip()
            if not line:
                continue
            if ":" in line:
                parts = line.split(":", 1)
                accounts.append((parts[0].strip(), parts[1].strip()))
            else:
                errors.append(line)

        if accounts:
            added = await db.add_accounts_bulk(accounts)
            stock = await db.get_stock_count()
            await update.message.reply_text(
                f"✅ <b>Accounts Added!</b>\n\n"
                f"➕ Added: <code>{added}</code>\n"
                f"📦 Total Stock: <code>{stock}</code>\n\n"
                + (f"⚠️ Invalid lines: {len(errors)}" if errors else ""),
                parse_mode=ParseMode.HTML,
                reply_markup=await kb.admin_menu_keyboard(),
            )
            await db.write_log("INFO", f"Admin added {added} accounts manually")
        else:
            await update.message.reply_text(
                "❌ No valid accounts found.\n\nFormat: <code>email:password</code> (one per line)",
                parse_mode=ParseMode.HTML,
            )
        ctx.user_data["admin_state"] = STATE_IDLE

    # ── Edit message ──────────────────────────────────────────────────────────
    elif state == STATE_AWAIT_NEW_MESSAGE:
        msg_key = ctx.user_data.get("editing_msg_key")
        if not msg_key:
            ctx.user_data["admin_state"] = STATE_IDLE
            return

        media_file = None
        media_type = None
        content    = text

        if update.message.photo:
            media_file = update.message.photo[-1].file_id
            media_type = "photo"
            # Inject <tg-emoji> tags from caption entities for premium emojis
            content = inject_custom_emoji_html(
                update.message.caption or "",
                update.message.caption_entities,
            )
        elif update.message.video:
            media_file = update.message.video.file_id
            media_type = "video"
            content = inject_custom_emoji_html(
                update.message.caption or "",
                update.message.caption_entities,
            )
        else:
            # Plain text — inject <tg-emoji> tags for any premium emojis in the text
            content = inject_custom_emoji_html(text, update.message.entities)

        await db.set_message(msg_key, content, media_file, media_type)
        await update.message.reply_text(
            f"✅ <b>Message updated!</b>\n🔑 Key: <code>{msg_key}</code>\n"
            f"<i>Saved to MongoDB — survives hosting changes.</i>",
            parse_mode=ParseMode.HTML,
            reply_markup=await kb.admin_menu_keyboard(),
        )
        await db.write_log("INFO", f"Admin updated message: {msg_key}")
        ctx.user_data["admin_state"] = STATE_IDLE
        ctx.user_data["editing_msg_key"] = None

    # ── Edit button ───────────────────────────────────────────────────────────
    elif state == STATE_AWAIT_NEW_BUTTON:
        btn_key = ctx.user_data.get("editing_btn_key")
        if not btn_key:
            ctx.user_data["admin_state"] = STATE_IDLE
            return

        # Parse the admin's message:
        #   - Auto-detect premium emoji from entities (custom_emoji_id extracted automatically)
        #   - Optional override: send label + newline + "emoji_id:none" to explicitly clear
        #   - If no premium emoji in the message and no override line, preserve existing emoji_id
        lines = text.split("\n", 1)
        label = lines[0].strip()
        existing = await db.get_button(btn_key)
        emoji_id = existing.get("emoji_id")  # default: preserve

        # Check for explicit emoji_id:none override on a second line
        explicit_clear = False
        if len(lines) > 1:
            second = lines[1].strip()
            if second.lower().startswith("emoji_id:"):
                raw_id = second.split(":", 1)[1].strip()
                if raw_id.lower() == "none":
                    explicit_clear = True
                    emoji_id = None

        if not explicit_clear:
            # Auto-extract custom emoji from the message entities
            entities = update.message.entities or []
            custom_entities = [
                e for e in entities
                if getattr(e, "type", None) == MessageEntity.CUSTOM_EMOJI
                and getattr(e, "custom_emoji_id", None)
            ]
            if custom_entities:
                emoji_id = custom_entities[0].custom_emoji_id

        await db.set_button(btn_key, label, emoji_id)
        if emoji_id:
            emoji_note = f"\n🌟 Premium emoji: <tg-emoji emoji-id=\"{emoji_id}\">⭐</tg-emoji>"
        else:
            emoji_note = ""
        await update.message.reply_text(
            f"✅ <b>Button updated!</b>\n"
            f"🔑 Key: <code>{btn_key}</code>\n"
            f"📝 Label: <code>{label}</code>"
            f"{emoji_note}",
            parse_mode=ParseMode.HTML,
            reply_markup=await kb.admin_menu_keyboard(),
        )
        await db.write_log(
            "INFO",
            f"Admin updated button: {btn_key} → label='{label}' emoji_id={emoji_id}"
        )
        ctx.user_data["admin_state"] = STATE_IDLE
        ctx.user_data["editing_btn_key"] = None

    # ── Set proof channel ─────────────────────────────────────────────────────
    elif state == STATE_AWAIT_PROOF_CHANNEL:
        channel_val = text.strip()
        await db.set_setting("proof_channel", channel_val)
        await update.message.reply_text(
            f"✅ <b>Proof channel set!</b>\n📸 Channel: <code>{channel_val}</code>",
            parse_mode=ParseMode.HTML,
            reply_markup=await kb.admin_menu_keyboard(),
        )
        await db.write_log("INFO", f"Admin set proof channel: {channel_val}")
        ctx.user_data["admin_state"] = STATE_IDLE

    # ── Add admin ─────────────────────────────────────────────────────────────
    elif state == STATE_AWAIT_NEW_ADMIN:
        try:
            new_id = int(text)
            await db.add_admin(new_id, user.id)
            ctx.user_data.pop("admin_add_return", None)
            await update.message.reply_text(
                f"✅ <b>Admin added!</b>\n"
                f"🆔 User ID: <code>{new_id}</code>\n"
                f"🔐 They now have full admin panel access.",
                parse_mode=ParseMode.HTML,
                reply_markup=await kb.admin_menu_keyboard(),
            )
            await db.write_log("INFO", f"Admin {user.id} added admin {new_id}")
        except ValueError:
            await update.message.reply_text(
                "❌ Invalid user ID. Send a numeric ID.", parse_mode=ParseMode.HTML
            )
        ctx.user_data["admin_state"] = STATE_IDLE

    # ── Change bot token ──────────────────────────────────────────────────────
    elif state == STATE_AWAIT_BOT_TOKEN:
        new_token = text.strip()
        # Validate the token by calling get_me
        try:
            test_bot = Bot(token=new_token)
            me = await test_bot.get_me()
            await test_bot.close()
        except Exception as e:
            await update.message.reply_text(
                f"❌ <b>Invalid token!</b>\n\nError: <code>{e}</code>\n\n"
                f"Double-check the token from @BotFather.",
                parse_mode=ParseMode.HTML,
            )
            return

        # Save to MongoDB
        await db.set_setting("bot_token", new_token)

        # Overwrite config.py BOT_TOKEN line so it persists as fallback too
        _patch_config_token(new_token)

        await update.message.reply_text(
            f"✅ <b>Token updated!</b>\n\n"
            f"🤖 Bot: @{me.username}\n"
            f"🔑 New token saved to MongoDB.\n\n"
            f"🔄 <b>Restarting bot now…</b>",
            parse_mode=ParseMode.HTML,
        )
        await db.write_log("INFO", f"Admin changed bot token → @{me.username}")
        ctx.user_data["admin_state"] = STATE_IDLE

        # Small delay so the message sends, then restart
        await asyncio.sleep(1.5)
        os.execv(sys.executable, [sys.executable] + sys.argv)

    # ── Set referral points ───────────────────────────────────────────────────
    elif state == STATE_AWAIT_REF_POINTS:
        try:
            pts = int(text)
            if pts <= 0:
                raise ValueError
            await db.set_setting("referral_points", str(pts))
            await update.message.reply_text(
                f"✅ <b>Referral points updated!</b>\n"
                f"💎 New value: <code>{pts}</code> points per referral",
                parse_mode=ParseMode.HTML,
                reply_markup=await kb.admin_menu_keyboard(),
            )
            await db.write_log("INFO", f"Admin set referral_points = {pts}")
        except (ValueError, TypeError):
            await update.message.reply_text(
                "❌ Please send a valid positive number.", parse_mode=ParseMode.HTML
            )
        ctx.user_data["admin_state"] = STATE_IDLE

    # ── Set redeem cost ───────────────────────────────────────────────────────
    elif state == STATE_AWAIT_REDEEM_COST:
        try:
            cost = int(text)
            if cost <= 0:
                raise ValueError
            await db.set_setting("redeem_cost", str(cost))
            await update.message.reply_text(
                f"✅ <b>Redeem cost updated!</b>\n"
                f"💸 New value: <code>{cost}</code> points per account",
                parse_mode=ParseMode.HTML,
                reply_markup=await kb.admin_menu_keyboard(),
            )
            await db.write_log("INFO", f"Admin set redeem_cost = {cost}")
        except (ValueError, TypeError):
            await update.message.reply_text(
                "❌ Please send a valid positive number.", parse_mode=ParseMode.HTML
            )
        ctx.user_data["admin_state"] = STATE_IDLE

    # ── Generate code: step 1 — points value ─────────────────────────────────
    elif state == STATE_AWAIT_CODE_POINTS:
        try:
            pts = int(text)
            if pts <= 0:
                raise ValueError("Points must be positive")
            ctx.user_data["code_points"] = pts
            ctx.user_data["admin_state"] = STATE_AWAIT_CODE_USES
            await update.message.reply_text(
                f"🎟 <b>Generate Redemption Code</b>\n\n"
                f"📌 <b>Step 2 of 2</b>\n\n"
                f"💎 Points value set: <code>{pts}</code>\n\n"
                f"How many times can this code be used?\n"
                f"• <code>1</code> = single use\n"
                f"• <code>10</code> = up to 10 users\n"
                f"• <code>9999</code> = unlimited",
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup([
                    [
                        btn("1️⃣ Single",     "code_uses_preset:1",    style="primary"),
                        btn("5️⃣ Five",       "code_uses_preset:5",    style="primary"),
                    ],
                    [
                        btn("🔟 Ten",        "code_uses_preset:10",   style="primary"),
                        btn("♾️ Unlimited",  "code_uses_preset:9999", style="success"),
                    ],
                    [btn("❌ Cancel", "admin_gen_code", style="danger")],
                ]),
            )
        except (ValueError, TypeError):
            await update.message.reply_text(
                "❌ Please send a valid positive number for points.",
                parse_mode=ParseMode.HTML,
            )

    # ── Generate code: step 2 — max uses (text) ──────────────────────────────
    elif state == STATE_AWAIT_CODE_USES:
        try:
            uses = int(text)
            if uses <= 0:
                raise ValueError
            await _finalize_code_generation(update, ctx, user, uses)
        except (ValueError, TypeError):
            await update.message.reply_text(
                "❌ Please send a valid positive number for max uses.",
                parse_mode=ParseMode.HTML,
            )

    # ── Broadcast message ─────────────────────────────────────────────────────
    elif state == STATE_AWAIT_BROADCAST_MSG:
        ctx.user_data["admin_state"] = STATE_IDLE

        user_ids = await db.get_all_user_ids()
        total = len(user_ids)
        if total == 0:
            await update.message.reply_text(
                "📭 No users to broadcast to.", parse_mode=ParseMode.HTML
            )
            return

        status_msg = await update.message.reply_text(
            f"📣 <b>Broadcasting…</b>\n\n"
            f"Sending to <code>{total}</code> users…",
            parse_mode=ParseMode.HTML,
        )

        sent, failed = await _do_broadcast(ctx.bot, user_ids, update.message)

        await status_msg.edit_text(
            f"📣 <b>Broadcast Complete!</b>\n\n"
            f"✅ Sent: <code>{sent}</code>\n"
            f"❌ Failed: <code>{failed}</code>\n"
            f"👥 Total: <code>{total}</code>",
            parse_mode=ParseMode.HTML,
            reply_markup=await kb.admin_menu_keyboard(),
        )
        await db.write_log(
            "INFO",
            f"Admin {user.id} broadcast: {sent} sent, {failed} failed out of {total}"
        )


async def handle_admin_doc(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Handle TXT file upload for bulk accounts."""
    user = update.effective_user
    if not await db.is_admin(user.id):
        return

    state = ctx.user_data.get("admin_state", STATE_IDLE)
    if state != STATE_AWAIT_ACCOUNTS_FILE:
        return

    doc = update.message.document
    if not doc or not doc.file_name.endswith(".txt"):
        await update.message.reply_text("❌ Please send a <b>.txt</b> file.", parse_mode=ParseMode.HTML)
        return

    file = await ctx.bot.get_file(doc.file_id)
    buf = BytesIO()
    await file.download_to_memory(buf)
    buf.seek(0)
    raw = buf.read().decode("utf-8", errors="ignore")

    lines = raw.strip().split("\n")
    accounts = []
    errors   = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        if ":" in line:
            parts = line.split(":", 1)
            accounts.append((parts[0].strip(), parts[1].strip()))
        else:
            errors.append(line)

    if accounts:
        added = await db.add_accounts_bulk(accounts)
        stock = await db.get_stock_count()
        await update.message.reply_text(
            f"✅ <b>Accounts Imported!</b>\n\n"
            f"📄 Parsed: <code>{len(lines)}</code> lines\n"
            f"➕ Added: <code>{added}</code> accounts\n"
            f"📦 Total Stock: <code>{stock}</code>\n"
            + (f"⚠️ Skipped invalid: <code>{len(errors)}</code>" if errors else ""),
            parse_mode=ParseMode.HTML,
            reply_markup=await kb.admin_menu_keyboard(),
        )
        await db.write_log("INFO", f"Admin imported {added} accounts from TXT file")
    else:
        await update.message.reply_text(
            "❌ No valid accounts found.\n\nFormat: <code>email:password</code>",
            parse_mode=ParseMode.HTML,
        )
    ctx.user_data["admin_state"] = STATE_IDLE


# ─── CODE USES PRESET CALLBACK ────────────────────────────────────────────────

async def cb_code_uses_preset(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not await _guard(update):
        return
    await query.answer()

    uses = int(query.data.split(":", 1)[1])
    await _finalize_code_generation(query, ctx, update.effective_user, uses)


async def _finalize_code_generation(update_or_query, ctx, user, uses: int):
    """Create the code and show it to the admin."""
    pts = ctx.user_data.pop("code_points", 10)
    ctx.user_data["admin_state"] = STATE_IDLE

    code_doc = await db.create_redeem_code(
        points_value=pts,
        max_uses=uses,
        created_by=user.id,
    )

    uses_label = "Unlimited (9999)" if uses >= 9999 else str(uses)

    result_msg = (
        f"🎉 <b>Redemption Code Generated!</b>\n\n"
        f"🎟 <b>Code:</b> <code>{code_doc['code']}</code>\n"
        f"💎 <b>Points:</b> <code>{pts}</code> per use\n"
        f"🔢 <b>Max Uses:</b> <code>{uses_label}</code>\n\n"
        f"📤 <b>Share with users:</b>\n"
        f"<code>/redeem {code_doc['code']}</code>\n\n"
        f"✅ Code is now active!"
    )

    markup = InlineKeyboardMarkup([
        [
            btn("🎟 Generate Another", "gen_code_start", style="success"),
            btn("📋 View All",          "list_codes",     style="primary"),
        ],
        [btn("◀️ Admin Menu", "admin_menu", style="primary")],
    ])

    await db.write_log(
        "INFO", f"Admin {user.id} generated code {code_doc['code']} ({pts}pts, {uses} uses)"
    )

    try:
        if hasattr(update_or_query, "edit_message_text"):
            await update_or_query.edit_message_text(
                result_msg, parse_mode=ParseMode.HTML, reply_markup=markup
            )
        else:
            await update_or_query.message.reply_text(
                result_msg, parse_mode=ParseMode.HTML, reply_markup=markup
            )
    except Exception:
        pass


# ─── HELPERS ──────────────────────────────────────────────────────────────────

def _patch_config_token(new_token: str):
    """Overwrite BOT_TOKEN line in config.py so the new token persists as fallback."""
    try:
        config_path = os.path.join(os.path.dirname(__file__), "..", "config.py")
        config_path = os.path.abspath(config_path)
        with open(config_path, "r", encoding="utf-8") as f:
            content = f.read()

        import re
        patched = re.sub(
            r'(BOT_TOKEN\s*=\s*os\.getenv\([^,]+,\s*")[^"]*(")',
            rf'\g<1>{new_token}\g<2>',
            content,
        )
        with open(config_path, "w", encoding="utf-8") as f:
            f.write(patched)
    except Exception as e:
        logger.warning(f"Could not patch config.py with new token: {e}")
