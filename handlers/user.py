"""
╔══════════════════════════════════════════════════╗
║   USER HANDLERS                                  ║
║   /start, verify, main menu, withdraw, refer     ║
║   Account health: stock → working → broken       ║
║   Developer: @iam_eshh                           ║
╚══════════════════════════════════════════════════╝
"""

import logging
from datetime import datetime
from telegram import Update
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

import database as db
import keyboards as kb
from templates import render, build_referral_link, render_text
from sender import send_rendered
from config import MAX_REPLACEMENTS

logger = logging.getLogger(__name__)


async def _reply_rendered(query, bot, rendered: dict, markup=None):
    """
    Smart reply: if the rendered content has a media file (photo/video) always
    send a new message via send_rendered so the media is shown.
    For text-only content, try to edit the existing message in place first
    (cleaner UX), falling back to a new message if the edit fails.
    """
    if rendered.get("media_file"):
        await send_rendered(bot, query.message.chat_id, rendered, markup)
    else:
        try:
            await query.edit_message_text(
                text=rendered["content"],
                parse_mode=ParseMode.HTML,
                reply_markup=markup,
            )
        except Exception:
            await send_rendered(bot, query.message.chat_id, rendered, markup)


async def check_membership(bot, user_id: int, channels: list[dict]) -> list[dict]:
    """Return channels the user hasn't joined yet."""
    missing = []
    for ch in channels:
        try:
            member = await bot.get_chat_member(
                chat_id=ch["chat_id"], user_id=user_id
            )
            if member.status in ("left", "kicked", "banned"):
                missing.append(ch)
        except Exception:
            missing.append(ch)
    return missing


# ─── /start ───────────────────────────────────────────────────────────────────

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await db.upsert_user(user.id, user.username, user.first_name, user.last_name or "")
    await db.write_log("INFO", f"User {user.id} (@{user.username}) started the bot")

    # Handle referral
    args = ctx.args
    if args:
        arg = args[0]
        if arg.startswith("ref_"):
            try:
                referrer_id = int(arg.split("_")[1])
                if referrer_id != user.id:
                    existing = await db.get_user(user.id)
                    if existing and existing.get("referred_by") is None:
                        await db.add_referral(referrer_id, user.id)
                        pts = int(await db.get_setting("referral_points", "10"))
                        await db.add_points(referrer_id, pts)
                        await db.write_log(
                            "INFO",
                            f"Referral: {referrer_id} referred {user.id}, awarded {pts} pts"
                        )
                        try:
                            await ctx.bot.send_message(
                                chat_id=referrer_id,
                                text=(
                                    f"🎉 <b>New Referral!</b>\n\n"
                                    f"<b>{user.first_name}</b> joined using your link!\n"
                                    f"You earned <b>+{pts}</b> points 💎"
                                ),
                                parse_mode=ParseMode.HTML,
                            )
                        except Exception:
                            pass
            except (ValueError, IndexError):
                pass

    # Check channel membership
    channels = await db.get_all_channels()
    if channels:
        missing = await check_membership(ctx.bot, user.id, channels)
        if missing:
            await _send_verify(update, ctx, missing)
            return

    await _send_welcome(update, ctx)


async def _send_verify(update: Update, ctx: ContextTypes.DEFAULT_TYPE, missing: list[dict]):
    user = update.effective_user

    channels_text = ""
    for i, ch in enumerate(missing, 1):
        name = ch.get("title") or ch.get("username") or "Channel"
        channels_text += f"  {i}. <b>{name}</b>\n"

    rendered = await render("channel_verify", user, ctx.bot.username,
                            extra={"{channels_list}": channels_text})
    markup = await kb.welcome_keyboard(missing)

    msg = update.message or update.callback_query.message
    await send_rendered(ctx.bot, msg.chat_id, rendered, markup)


async def _send_welcome(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    rendered = await render("welcome", user, ctx.bot.username)
    markup = await kb.main_menu_keyboard()

    msg = update.message or (update.callback_query and update.callback_query.message)
    if msg:
        await send_rendered(ctx.bot, msg.chat_id, rendered, markup)


# ─── /redeem <CODE> ───────────────────────────────────────────────────────────

async def cmd_redeem(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await db.upsert_user(user.id, user.username, user.first_name, user.last_name or "")

    if not ctx.args:
        await update.message.reply_text(
            "🎟 <b>Redeem a Code</b>\n\n"
            "Usage: <code>/redeem YOUR_CODE</code>\n\n"
            "Example: <code>/redeem CRUNCHY-ABC12345</code>",
            parse_mode=ParseMode.HTML,
            reply_markup=await kb.back_keyboard("main_menu"),
        )
        return

    code = ctx.args[0].strip().upper()
    result = await db.use_redeem_code(code, user.id)

    if result["ok"]:
        new_points = await db.get_user_points(user.id)
        rendered = await render(
            "redeem_code_success", user, ctx.bot.username,
            extra={
                "{code}":         code,
                "{points}":       str(result["points"]),
                "{total_points}": str(new_points),
            },
        )
        await send_rendered(ctx.bot, update.message.chat_id, rendered,
                            await kb.back_keyboard("main_menu"))
        await db.write_log("INFO", f"User {user.id} redeemed code {code} for {result['points']} pts")

    elif result["reason"] == "already_used":
        rendered = await render(
            "redeem_code_already_used", user, ctx.bot.username,
            extra={"{code}": code},
        )
        await send_rendered(ctx.bot, update.message.chat_id, rendered,
                            await kb.back_keyboard("main_menu"))

    elif result["reason"] == "exhausted":
        rendered = await render(
            "redeem_code_exhausted", user, ctx.bot.username,
            extra={"{code}": code},
        )
        await send_rendered(ctx.bot, update.message.chat_id, rendered,
                            await kb.back_keyboard("main_menu"))

    else:  # invalid
        rendered = await render(
            "redeem_code_invalid", user, ctx.bot.username,
            extra={"{code}": code},
        )
        await send_rendered(ctx.bot, update.message.chat_id, rendered,
                            await kb.back_keyboard("main_menu"))


# ─── VERIFY CALLBACK ─────────────────────────────────────────────────────────

async def cb_verify(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = update.effective_user

    channels = await db.get_all_channels()
    if channels:
        missing = await check_membership(ctx.bot, user.id, channels)
        if missing:
            channels_text = ""
            for i, ch in enumerate(missing, 1):
                name = ch.get("title") or ch.get("username") or "Channel"
                channels_text += f"  {i}. <b>{name}</b>\n"

            rendered = await render("channel_verify", user, ctx.bot.username,
                                    extra={"{channels_list}": channels_text})
            markup = await kb.welcome_keyboard(missing)
            await _reply_rendered(query, ctx.bot, rendered, markup)
            return

    rendered = await render("welcome", user, ctx.bot.username)
    markup = await kb.main_menu_keyboard()
    await _reply_rendered(query, ctx.bot, rendered, markup)


# ─── MAIN MENU ────────────────────────────────────────────────────────────────

async def cb_main_menu(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = update.effective_user

    rendered = await render("main_menu", user, ctx.bot.username)
    markup = await kb.main_menu_keyboard()
    await _reply_rendered(query, ctx.bot, rendered, markup)


# ─── WITHDRAW ─────────────────────────────────────────────────────────────────

async def cb_withdraw(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = update.effective_user

    cost = int(await db.get_setting("redeem_cost", "10"))
    rendered = await render("withdraw", user, ctx.bot.username,
                            extra={"{cost}": str(cost)})
    markup = await kb.withdraw_keyboard(cost)

    await _reply_rendered(query, ctx.bot, rendered, markup)


async def cb_confirm_redeem(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = update.effective_user

    # Check pending screenshot
    pending = await db.get_pending_screenshot(user.id)
    if pending:
        rendered = await render("already_pending_screenshot", user)
        markup = await kb.back_keyboard("main_menu")
        await _reply_rendered(query, ctx.bot, rendered, markup)
        return

    cost = int(await db.get_setting("redeem_cost", "10"))
    stock = await db.get_stock_count()

    if stock == 0:
        rendered = await render("no_stock", user)
        markup = await kb.back_keyboard("main_menu")
        await _reply_rendered(query, ctx.bot, rendered, markup)
        return

    points = await db.get_user_points(user.id)
    if points < cost:
        rendered = await render("insufficient_points", user,
                                extra={"{cost}": str(cost)})
        markup = await kb.back_keyboard("main_menu")
        await _reply_rendered(query, ctx.bot, rendered, markup)
        return

    await _deliver_account(query, ctx, user, cost, first_time=True)


async def _deliver_account(query, ctx, user, cost: int, first_time: bool = True):
    """
    Deliver the best available account.
    Priority: confirmed working → untested stock.
    Validates account data before delivery.
    """
    account = await db.get_next_account()

    # Skip accounts with missing/malformed credentials (up to 5 attempts)
    attempts = 0
    while account and attempts < 5:
        if account.get("email") and account.get("password") and ":" not in account["email"]:
            break  # valid
        # Malformed — mark broken and try next
        await db.mark_account_broken(account["_id"])
        account = await db.get_next_account()
        attempts += 1

    if not account:
        rendered = await render("no_stock", user)
        markup = await kb.back_keyboard("main_menu")
        await _reply_rendered(query, ctx.bot, rendered, markup)
        return

    if first_time:
        success = await db.deduct_points(user.id, cost)
        if not success:
            rendered = await render("insufficient_points", user,
                                    extra={"{cost}": str(cost)})
            markup = await kb.back_keyboard("main_menu")
            await _reply_rendered(query, ctx.bot, rendered, markup)
            return

    # Record delivery
    await db.increment_account_given(account["_id"], user.id)
    redeem_id = await db.create_redeem(user.id, account["_id"])
    await db.set_pending_screenshot(user.id, redeem_id, account["_id"])

    # Show account status badge
    status_badge = "✅ <b>Verified working!</b> " if account.get("status") == "working" else ""

    email, password = account["email"], account["password"]
    rendered = await render(
        "account_delivered", user,
        extra={"{email}": email, "{password}": password, "{redeem_id}": str(redeem_id)}
    )

    # Prepend status badge to content if it's a verified account
    if status_badge and rendered["content"]:
        rendered["content"] = status_badge + "\n" + rendered["content"]

    markup = await kb.account_delivered_keyboard(redeem_id)

    await _reply_rendered(query, ctx.bot, rendered, markup)

    await db.write_log(
        "INFO",
        f"Account delivered to user {user.id}, account={account['_id']} "
        f"(status={account.get('status','stock')}), redeem_id={redeem_id}"
    )


async def cb_working(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("🎉 Great! Please send your screenshot now.")
    user = update.effective_user

    _, redeem_id = query.data.split(":")
    redeem_id = int(redeem_id)

    await db.update_redeem_status(redeem_id, "screenshot_pending")

    # Mark account as confirmed working → it re-enters the pool for future users
    pending = await db.get_pending_screenshot(user.id)
    if pending:
        await db.mark_account_working(pending["account_id"])
        await db.write_log(
            "INFO",
            f"User {user.id} confirmed account {pending['account_id']} working — back in pool"
        )

    rendered = await render("screenshot_request", user)
    await _reply_rendered(query, ctx.bot, rendered)


async def cb_not_working(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = update.effective_user

    _, redeem_id = query.data.split(":")
    redeem_id = int(redeem_id)

    replacements = await db.increment_replacements(redeem_id)

    if replacements >= MAX_REPLACEMENTS:
        await query.answer("❌ No more replacements available.")
        rendered = await render("no_replacements", user,
                                extra={"{max}": str(MAX_REPLACEMENTS)})
        markup = await kb.back_keyboard("main_menu")
        await _reply_rendered(query, ctx.bot, rendered, markup)
        await db.clear_pending_screenshot(user.id)
        return

    # Mark current account as broken — permanently removed from pool
    pending = await db.get_pending_screenshot(user.id)
    if pending:
        await db.mark_account_broken(pending["account_id"])
        await db.write_log(
            "INFO",
            f"User {user.id} reported account {pending['account_id']} broken — discarded"
        )

    await query.answer("🔄 Discarding broken account, getting you a replacement…")
    left = MAX_REPLACEMENTS - replacements
    rendered = await render("not_working", user, extra={"{left}": str(left)})
    await _reply_rendered(query, ctx.bot, rendered)

    # Clear old pending so _deliver_account doesn't block on it
    await db.clear_pending_screenshot(user.id)

    cost = int(await db.get_setting("redeem_cost", "10"))
    await _deliver_account(query, ctx, user, cost, first_time=False)


async def handle_screenshot(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Handle screenshot photo submission."""
    user = update.effective_user
    pending = await db.get_pending_screenshot(user.id)
    if not pending:
        return

    photo = update.message.photo[-1] if update.message.photo else None
    if not photo:
        await update.message.reply_text(
            "📸 Please send a <b>photo</b> as your screenshot.",
            parse_mode=ParseMode.HTML,
        )
        return

    file_id = photo.file_id
    redeem_id = pending["redeem_id"]

    await db.set_redeem_screenshot(redeem_id, file_id)
    await db.clear_pending_screenshot(user.id)

    await update.message.reply_text(
        "✅ <b>Screenshot received!</b>\n\nThank you for confirming. Enjoy your account! 🎌",
        parse_mode=ParseMode.HTML,
        reply_markup=await kb.main_menu_keyboard(),
    )

    # Forward proof to proof channel
    proof_channel = await db.get_setting("proof_channel", "")
    if proof_channel:
        try:
            caption_rendered = await render(
                "proof_caption", user,
                extra={
                    "{date}": datetime.now().strftime("%Y-%m-%d %H:%M"),
                    "{cost}": str(await db.get_setting("redeem_cost", "10")),
                }
            )
            await ctx.bot.send_photo(
                chat_id=proof_channel,
                photo=file_id,
                caption=caption_rendered["content"],
                parse_mode=ParseMode.HTML,
            )
        except Exception as e:
            logger.error(f"Failed to send proof to channel: {e}")

    await db.write_log("INFO", f"Screenshot received from user {user.id}, redeem_id={redeem_id}")


# ─── REFER ────────────────────────────────────────────────────────────────────

async def cb_refer(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = update.effective_user

    ref_link = await build_referral_link(ctx.bot.username, user.id)
    refs = await db.get_referral_count(user.id)
    rank = await db.get_user_rank(user.id)
    pts_per_ref = await db.get_setting("referral_points", "10")

    rendered = await render(
        "refer", user, ctx.bot.username,
        extra={
            "{referral_link}":  ref_link,
            "{total_refs}":     str(refs),
            "{rank}":           str(rank),
            "{points_per_ref}": str(pts_per_ref),
        }
    )
    markup = await kb.refer_keyboard(ref_link)
    await _reply_rendered(query, ctx.bot, rendered, markup)


# ─── LEADERBOARD ──────────────────────────────────────────────────────────────

async def cb_leaderboard(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = update.effective_user

    top = await db.get_leaderboard(10)
    rank = await db.get_user_rank(user.id)
    my_refs = await db.get_referral_count(user.id)

    medals = ["🥇", "🥈", "🥉"] + ["🏅"] * 7
    lines = []
    for i, entry in enumerate(top):
        medal = medals[i] if i < len(medals) else f"{i+1}."
        name  = entry.get("first_name") or f"User {entry['user_id']}"
        count = entry.get("ref_count", 0)
        lines.append(f"{medal} <b>{name}</b> — {count} referrals")

    lb_text = "\n".join(lines) if lines else "No data yet. Be the first! 🚀"

    rendered = await render(
        "leaderboard", user, ctx.bot.username,
        extra={
            "{leaderboard_list}": lb_text,
            "{your_rank}":        str(rank),
            "{your_refs}":        str(my_refs),
        }
    )
    markup = await kb.leaderboard_keyboard()
    await _reply_rendered(query, ctx.bot, rendered, markup)


# ─── STOCK ────────────────────────────────────────────────────────────────────

async def cb_stock(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = update.effective_user

    cost = await db.get_setting("redeem_cost", "10")
    rendered = await render("stock", user, ctx.bot.username,
                            extra={"{cost}": cost})
    markup = await kb.stock_keyboard()
    await _reply_rendered(query, ctx.bot, rendered, markup)


# ─── PROOF ────────────────────────────────────────────────────────────────────

async def cb_proof(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    proof_channel = await db.get_setting("proof_channel", "")
    if not proof_channel:
        await query.answer("📸 No proof channel configured yet!", show_alert=True)
        return

    if proof_channel.startswith("@"):
        url = f"https://t.me/{proof_channel[1:]}"
    elif proof_channel.startswith("-100"):
        url = f"https://t.me/c/{proof_channel[4:]}/"
    else:
        url = f"https://t.me/{proof_channel}"

    from keyboards import btn
    markup = InlineKeyboardMarkup([
        [btn("📸 View Proof Wall", url=url,       style="primary")],
        [btn("◀️ Back",            "main_menu",   style="primary")],
    ])

    await query.edit_message_text(
        "📸 <b>Proof Wall</b>\n\nView working account screenshots from real users!",
        parse_mode=ParseMode.HTML,
        reply_markup=markup,
    )
