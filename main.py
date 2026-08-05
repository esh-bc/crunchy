"""
╔══════════════════════════════════════════════════╗
║   CRUNCHYROLL REFERRAL BOT — MAIN ENTRY          ║
║   Bot API: 10.2 (July 2026)                      ║
║   Database: MongoDB (Motor async driver)         ║
║   Token read from DB on startup (hosting-safe)   ║
║   Developer: @iam_eshh                           ║
╚══════════════════════════════════════════════════╝
"""

import asyncio
import logging
import sys
import os

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
)

import database as db
from config import BOT_TOKEN, BOT_VERSION, DEVELOPER
from owner_setup import ensure_owner
from webserver import start_webserver
from handlers.user import (
    cmd_start,
    cmd_redeem,
    cb_verify,
    cb_main_menu,
    cb_withdraw,
    cb_confirm_redeem,
    cb_working,
    cb_not_working,
    cb_refer,
    cb_leaderboard,
    cb_stock,
    cb_proof,
    handle_screenshot,
)
from handlers.admin import (
    cmd_admin,
    cb_admin_menu,
    cb_admin_channels,
    cb_add_channel,
    cb_add_chan_public,
    cb_add_chan_private,
    cb_del_channel,
    cb_admin_accounts,
    cb_upload_accounts,
    cb_manual_accounts,
    cb_view_stock,
    cb_clear_accounts,
    cb_confirm_clear_accounts,
    cb_admin_messages,
    cb_edit_message,
    cb_admin_buttons,
    cb_edit_button,
    cb_admin_proof,
    cb_admin_admins,
    cb_add_admin,
    cb_admin_quick_add_admin,
    cb_remove_admin,
    cb_admin_logs,
    cb_admin_system,
    # Code generation
    cb_admin_gen_code,
    cb_gen_code_start,
    cb_list_codes,
    cb_del_code,
    cb_code_uses_preset,
    # Broadcast (NEW)
    cb_admin_broadcast,
    cb_broadcast_start,
    # Bot settings (NEW)
    cb_admin_settings,
    cb_admin_change_token,
    cb_admin_set_ref_pts,
    cb_admin_set_redeem_cost,
    # Misc
    cb_noop,
    handle_admin_text,
    handle_admin_doc,
    STATE_IDLE,
)

# ─── LOGGING ─────────────────────────────────────────────────────────────────

os.makedirs("data", exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("data/bot.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger(__name__)

# Reduce noise from libraries
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("telegram").setLevel(logging.WARNING)
logging.getLogger("motor").setLevel(logging.WARNING)


# ─── SMART TEXT ROUTER ───────────────────────────────────────────────────────

async def route_text(update: Update, ctx):
    """
    Route incoming text/photo/doc to the correct handler
    based on admin conversation state, or handle as screenshot.
    """
    user = update.effective_user
    if not user:
        return

    admin_state = ctx.user_data.get("admin_state", STATE_IDLE)

    # Admin states (text input)
    if admin_state != STATE_IDLE and await db.is_admin(user.id):
        if update.message and update.message.document:
            await handle_admin_doc(update, ctx)
        else:
            await handle_admin_text(update, ctx)
        return

    # Regular user — screenshot submission
    if update.message and (update.message.photo or update.message.document):
        pending = await db.get_pending_screenshot(user.id)
        if pending:
            await handle_screenshot(update, ctx)
            return

    # Otherwise ignore
    return


# ─── BOT SETUP ───────────────────────────────────────────────────────────────

async def post_init(app: Application):
    """Run after bot initialises (DB is already connected at this point)."""
    await ensure_owner()

    me = await app.bot.get_me()
    logger.info(f"Bot started: @{me.username} (v{BOT_VERSION})")
    logger.info(f"Developer: {DEVELOPER}")

    await db.write_log("INFO", f"Bot started — v{BOT_VERSION} — @{me.username}")
    logger.info("✅ Bot fully ready.")


def build_app(token: str) -> Application:
    app = (
        Application.builder()
        .token(token)
        .post_init(post_init)
        .build()
    )

    # ── Commands ─────────────────────────────────────────────────────────────
    app.add_handler(CommandHandler("start",  cmd_start))
    app.add_handler(CommandHandler("admin",  cmd_admin))
    app.add_handler(CommandHandler("redeem", cmd_redeem))

    # ── User Callbacks ────────────────────────────────────────────────────────
    app.add_handler(CallbackQueryHandler(cb_verify,         pattern="^verify$"))
    app.add_handler(CallbackQueryHandler(cb_main_menu,      pattern="^main_menu$"))
    app.add_handler(CallbackQueryHandler(cb_withdraw,       pattern="^withdraw$"))
    app.add_handler(CallbackQueryHandler(cb_confirm_redeem, pattern="^confirm_redeem$"))
    app.add_handler(CallbackQueryHandler(cb_working,        pattern="^working:"))
    app.add_handler(CallbackQueryHandler(cb_not_working,    pattern="^not_working:"))
    app.add_handler(CallbackQueryHandler(cb_refer,          pattern="^refer$"))
    app.add_handler(CallbackQueryHandler(cb_leaderboard,    pattern="^leaderboard$"))
    app.add_handler(CallbackQueryHandler(cb_stock,          pattern="^stock$"))
    app.add_handler(CallbackQueryHandler(cb_proof,          pattern="^proof$"))

    # ── Admin Core ────────────────────────────────────────────────────────────
    app.add_handler(CallbackQueryHandler(cb_admin_menu,             pattern="^admin_menu$"))
    app.add_handler(CallbackQueryHandler(cb_admin_channels,         pattern="^admin_channels$"))
    app.add_handler(CallbackQueryHandler(cb_add_channel,            pattern="^add_channel$"))
    app.add_handler(CallbackQueryHandler(cb_add_chan_public,         pattern="^add_chan_public$"))
    app.add_handler(CallbackQueryHandler(cb_add_chan_private,        pattern="^add_chan_private$"))
    app.add_handler(CallbackQueryHandler(cb_del_channel,            pattern="^del_channel:"))
    app.add_handler(CallbackQueryHandler(cb_admin_accounts,         pattern="^admin_accounts$"))
    app.add_handler(CallbackQueryHandler(cb_upload_accounts,        pattern="^upload_accounts$"))
    app.add_handler(CallbackQueryHandler(cb_manual_accounts,        pattern="^manual_accounts$"))
    app.add_handler(CallbackQueryHandler(cb_view_stock,             pattern="^view_stock$"))
    app.add_handler(CallbackQueryHandler(cb_clear_accounts,         pattern="^clear_accounts$"))
    app.add_handler(CallbackQueryHandler(cb_confirm_clear_accounts, pattern="^confirm_clear_accounts$"))
    app.add_handler(CallbackQueryHandler(cb_admin_messages,         pattern="^admin_messages$"))
    app.add_handler(CallbackQueryHandler(cb_edit_message,           pattern="^edit_msg:"))
    app.add_handler(CallbackQueryHandler(cb_admin_buttons,          pattern="^admin_buttons$"))
    app.add_handler(CallbackQueryHandler(cb_edit_button,            pattern="^edit_btn:"))
    app.add_handler(CallbackQueryHandler(cb_admin_proof,            pattern="^admin_proof$"))
    app.add_handler(CallbackQueryHandler(cb_admin_admins,           pattern="^admin_admins$"))
    app.add_handler(CallbackQueryHandler(cb_add_admin,              pattern="^add_admin$"))
    app.add_handler(CallbackQueryHandler(cb_admin_quick_add_admin,  pattern="^admin_quick_add_admin$"))
    app.add_handler(CallbackQueryHandler(cb_remove_admin,           pattern="^remove_admin:"))
    app.add_handler(CallbackQueryHandler(cb_admin_logs,             pattern="^admin_logs$"))
    app.add_handler(CallbackQueryHandler(cb_admin_system,           pattern="^admin_system$"))

    # ── Redemption Codes ──────────────────────────────────────────────────────
    app.add_handler(CallbackQueryHandler(cb_admin_gen_code,   pattern="^admin_gen_code$"))
    app.add_handler(CallbackQueryHandler(cb_gen_code_start,   pattern="^gen_code_start$"))
    app.add_handler(CallbackQueryHandler(cb_list_codes,       pattern="^list_codes$"))
    app.add_handler(CallbackQueryHandler(cb_del_code,         pattern="^del_code:"))
    app.add_handler(CallbackQueryHandler(cb_code_uses_preset, pattern="^code_uses_preset:"))

    # ── Broadcast (NEW) ───────────────────────────────────────────────────────
    app.add_handler(CallbackQueryHandler(cb_admin_broadcast, pattern="^admin_broadcast$"))
    app.add_handler(CallbackQueryHandler(cb_broadcast_start, pattern="^broadcast_start$"))

    # ── Bot Settings (NEW) ────────────────────────────────────────────────────
    app.add_handler(CallbackQueryHandler(cb_admin_settings,       pattern="^admin_settings$"))
    app.add_handler(CallbackQueryHandler(cb_admin_change_token,   pattern="^admin_change_token$"))
    app.add_handler(CallbackQueryHandler(cb_admin_set_ref_pts,    pattern="^admin_set_ref_pts$"))
    app.add_handler(CallbackQueryHandler(cb_admin_set_redeem_cost,pattern="^admin_set_redeem_cost$"))

    # ── Noop ──────────────────────────────────────────────────────────────────
    app.add_handler(CallbackQueryHandler(cb_noop, pattern="^noop"))

    # ── Message Router ────────────────────────────────────────────────────────
    app.add_handler(MessageHandler(
        filters.TEXT | filters.PHOTO | filters.Document.ALL,
        route_text,
    ))

    return app


# ─── MAIN ─────────────────────────────────────────────────────────────────────

async def main():
    # ── Step 1: Connect to MongoDB first ─────────────────────────────────────
    # This must happen before building the Application so we can read the
    # bot token from the database (enables seamless hosting migration).
    logger.info("🍃 Connecting to MongoDB…")
    await db.init_db()
    logger.info("✅ MongoDB connected and ready.")

    # ── Step 2: Read token (DB overrides config.py for hosting-safe operation) ─
    db_token = await db.get_setting("bot_token", "")
    token = db_token if db_token else BOT_TOKEN

    if not token or token == "YOUR_BOT_TOKEN_HERE":
        logger.error("❌ No BOT_TOKEN found! Set it in config.py or via the admin panel.")
        sys.exit(1)

    # ── Step 3: Build and start the Application ───────────────────────────────
    app = build_app(token)

    web_runner = await start_webserver()

    logger.info(f"🚀 Starting Crunchyroll Referral Bot v{BOT_VERSION}")
    logger.info(f"👨‍💻 Developer: {DEVELOPER}")
    logger.info(f"🍃 Database: MongoDB")

    async with app:
        await app.start()
        await app.updater.start_polling(
            allowed_updates=Update.ALL_TYPES,
            drop_pending_updates=True,
        )
        logger.info("✅ Bot is polling for updates…")

        try:
            await asyncio.Event().wait()
        except (KeyboardInterrupt, SystemExit):
            pass

        await app.updater.stop()
        await app.stop()

    await web_runner.cleanup()
    logger.info("Bot stopped.")


if __name__ == "__main__":
    asyncio.run(main())
