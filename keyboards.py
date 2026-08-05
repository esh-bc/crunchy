"""
╔══════════════════════════════════════════════════╗
║   KEYBOARD BUILDER — COLOURED BUTTONS            ║
║   Bot API 9.4 (Feb 9 2026): 3 real colour styles ║
║     "primary" = blue                             ║
║     "success" = green                            ║
║     "danger"  = red                              ║
║   Premium emoji: icon_custom_emoji_id stored     ║
║   in MongoDB buttons collection (emoji_id field) ║
║   Developer: @iam_eshh                           ║
╚══════════════════════════════════════════════════╝
"""

import unicodedata
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from database import get_all_channels, get_button, get_buttons_batch, get_setting

# ── style normaliser ─────────────────────────────────────────────────────────
# Telegram Bot API 9.4 only accepts "primary", "success", "danger".
# Any other value causes a BadRequest.  Map everything to one of the three.
_STYLE_MAP = {
    "primary": "primary",
    "blue":    "primary",
    "success": "success",
    "green":   "success",
    "danger":  "danger",
    "red":     "danger",
    # legacy / unsupported values → nearest real equivalent
    "warning": "primary",
    "info":    "primary",
    "default": "primary",
    "link":    "primary",
    "light":   "primary",
    "dark":    "danger",
}

def _normalise(style: str | None) -> str:
    """Return a valid Telegram button style (never None — no grey buttons)."""
    if style is None:
        return "primary"
    return _STYLE_MAP.get(style.lower(), "primary")


def btn(label: str, callback: str = None, url: str = None,
        style: str = None, emoji_id: str = None) -> InlineKeyboardButton:
    """Public alias — use this when building buttons outside keyboards.py."""
    return _btn(label, callback=callback, url=url, style=style, emoji_id=emoji_id)


def _strip_leading_emoji(text: str) -> str:
    """
    Remove leading emoji/symbol characters (and the space after them) from a
    button label so they don't show alongside the premium icon_custom_emoji_id.
    Uses Unicode general-category: strips anything that isn't a Letter or Digit.
    """
    i = 0
    while i < len(text):
        cat = unicodedata.category(text[i])
        if cat.startswith(("L", "N")):   # Letter or Number → start of real text
            break
        i += 1
    return text[i:].lstrip()


def _btn(label: str, callback: str = None, url: str = None,
         style: str = None, emoji_id: str = None) -> InlineKeyboardButton:
    """
    Create a coloured InlineKeyboardButton.
    style is normalised to one of the three values Telegram actually accepts.
    emoji_id sets icon_custom_emoji_id (Bot API 9.4 premium emoji icon).
    When a premium emoji is set the static emoji prefix is stripped from the
    label so only the animated icon shows — not both.
    """
    kwargs: dict = {"style": _normalise(style)}
    clean_label = label
    if emoji_id and str(emoji_id).strip():
        kwargs["icon_custom_emoji_id"] = str(emoji_id).strip()
        clean_label = _strip_leading_emoji(label)

    if callback:
        return InlineKeyboardButton(clean_label, callback_data=callback, **kwargs)
    if url:
        return InlineKeyboardButton(clean_label, url=url, **kwargs)
    return InlineKeyboardButton(clean_label, callback_data="noop", **kwargs)


# ─── USER KEYBOARDS ───────────────────────────────────────────────────────────

async def welcome_keyboard(channels: list[dict]) -> InlineKeyboardMarkup:
    """Keyboard shown during channel verification."""
    rows = []
    for ch in channels:
        label = f"📢 {ch.get('title', 'Channel')}"
        link = ch.get("invite_link") or (
            f"https://t.me/{ch['username']}" if ch.get("username") else "#"
        )
        rows.append([_btn(label, url=link, style="primary")])
    v = await get_button("verify")
    rows.append([_btn(v["label"], callback="verify", style="success",
                      emoji_id=v.get("emoji_id"))])
    return InlineKeyboardMarkup(rows)


async def main_menu_keyboard() -> InlineKeyboardMarkup:
    """Main menu — every button has a colour and uses its stored premium emoji."""
    b = await get_buttons_batch(["withdraw", "refer", "leaderboard", "stock", "proof"])
    return InlineKeyboardMarkup([
        [
            _btn(b["withdraw"]["label"],    "withdraw",    style="success",
                 emoji_id=b["withdraw"].get("emoji_id")),
            _btn(b["refer"]["label"],       "refer",       style="primary",
                 emoji_id=b["refer"].get("emoji_id")),
        ],
        [
            _btn(b["leaderboard"]["label"], "leaderboard", style="primary",
                 emoji_id=b["leaderboard"].get("emoji_id")),
            _btn(b["stock"]["label"],       "stock",       style="success",
                 emoji_id=b["stock"].get("emoji_id")),
        ],
        [
            _btn(b["proof"]["label"],       "proof",       style="danger",
                 emoji_id=b["proof"].get("emoji_id")),
        ],
    ])


async def withdraw_keyboard(cost: int) -> InlineKeyboardMarkup:
    b = await get_buttons_batch(["confirm_redeem", "back"])
    cr, bk = b["confirm_redeem"], b["back"]
    return InlineKeyboardMarkup([
        [_btn(f"🎁 Redeem ({cost} pts)", "confirm_redeem", style="success",
              emoji_id=cr.get("emoji_id"))],
        [_btn(bk["label"], "main_menu",  style="primary",
              emoji_id=bk.get("emoji_id"))],
    ])


async def account_delivered_keyboard(redeem_id: int) -> InlineKeyboardMarkup:
    b = await get_buttons_batch(["working", "not_working"])
    w, nw = b["working"], b["not_working"]
    return InlineKeyboardMarkup([
        [
            _btn(w["label"],  f"working:{redeem_id}",     style="success",
                 emoji_id=w.get("emoji_id")),
            _btn(nw["label"], f"not_working:{redeem_id}", style="danger",
                 emoji_id=nw.get("emoji_id")),
        ]
    ])


async def working_keyboard(redeem_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [_btn("✅ Account confirmed!", "noop", style="success")]
    ])


async def back_keyboard(target: str = "main_menu") -> InlineKeyboardMarkup:
    bk = await get_button("back")   # single key — no batch needed
    return InlineKeyboardMarkup([
        [_btn(bk["label"], target, style="primary", emoji_id=bk.get("emoji_id"))]
    ])


async def refer_keyboard(referral_link: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [_btn(
            "📤 Share Referral Link",
            url=f"https://t.me/share/url?url={referral_link}&text=Join%20and%20get%20free%20Crunchyroll%20accounts!",
            style="primary",
        )],
        [_btn("◀️ Back", "main_menu", style="primary")],
    ])


async def leaderboard_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [_btn("🔄 Refresh", "leaderboard", style="success"),
         _btn("◀️ Back",    "main_menu",   style="primary")],
    ])


async def stock_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [_btn("◀️ Back", "main_menu", style="primary")],
    ])


# ─── ADMIN KEYBOARDS ──────────────────────────────────────────────────────────

async def admin_menu_keyboard() -> InlineKeyboardMarkup:
    """Main admin panel — every button coloured, none grey."""
    return InlineKeyboardMarkup([
        [
            _btn("📢 Channels",       "admin_channels",        style="primary"),
            _btn("📦 Accounts",       "admin_accounts",        style="success"),
        ],
        [
            _btn("✏️ Messages",       "admin_messages",        style="primary"),
            _btn("🔘 Buttons",        "admin_buttons",         style="primary"),
        ],
        [
            _btn("🎟 Gen Code",       "admin_gen_code",        style="success"),
            _btn("📣 Broadcast",      "admin_broadcast",       style="danger"),
        ],
        [
            _btn("➕ Add Admin",      "admin_quick_add_admin", style="primary"),
            _btn("👥 Admins",         "admin_admins",          style="primary"),
        ],
        [
            _btn("📸 Proof Channel",  "admin_proof",           style="primary"),
            _btn("⚙️ Bot Settings",   "admin_settings",        style="success"),
        ],
        [
            _btn("📋 Export Logs",    "admin_logs",            style="primary"),
            _btn("📊 System Info",    "admin_system",          style="success"),
        ],
    ])


async def channel_manager_keyboard(channels: list[dict]) -> InlineKeyboardMarkup:
    rows = []
    for ch in channels:
        name = ch.get("title") or ch.get("username") or ch["chat_id"]
        rows.append([
            _btn(f"📢 {name}", "noop",                      style="primary"),
            _btn("🗑 Remove",  f"del_channel:{ch['chat_id']}", style="danger"),
        ])
    rows.append([_btn("➕ Add Channel", "add_channel",  style="success")])
    rows.append([_btn("◀️ Back",        "admin_menu",   style="primary")])
    return InlineKeyboardMarkup(rows)


async def add_channel_type_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            _btn("🌐 Public Channel",  "add_chan_public",  style="primary"),
            _btn("🔒 Private Channel", "add_chan_private", style="primary"),
        ],
        [_btn("❌ Cancel", "admin_channels", style="danger")],
    ])


async def account_manager_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            _btn("📁 Upload TXT File",  "upload_accounts", style="success"),
            _btn("✏️ Manual Input",      "manual_accounts", style="primary"),
        ],
        [
            _btn("📊 View Stock Count", "view_stock",      style="primary"),
            _btn("🗑 Clear Stock",      "clear_accounts",  style="danger"),
        ],
        [_btn("◀️ Back", "admin_menu", style="primary")],
    ])


async def message_list_keyboard(messages: list[dict]) -> InlineKeyboardMarkup:
    rows = []
    nice_names = {
        "welcome":                    "🏠 Welcome Message",
        "channel_verify":             "📢 Channel Verify",
        "main_menu":                  "🏠 Main Menu",
        "withdraw":                   "🎫 Withdraw Message",
        "account_delivered":          "✅ Account Delivered",
        "refer":                      "🔗 Referral Message",
        "leaderboard":                "🏆 Leaderboard",
        "stock":                      "📦 Stock Message",
        "proof_caption":              "📸 Proof Caption",
        "screenshot_request":         "📸 Screenshot Request",
        "not_working":                "❌ Not Working",
        "no_replacements":            "⛔ No Replacements",
        "no_stock":                   "📭 No Stock",
        "insufficient_points":        "💔 Insufficient Points",
        "already_pending_screenshot": "⏳ Pending Screenshot",
        "admin_welcome":              "🛡️ Admin Welcome",
        "redeem_code_success":        "🎉 Code Redeemed",
        "redeem_code_invalid":        "❌ Invalid Code",
        "redeem_code_already_used":   "⚠️ Code Already Used",
        "redeem_code_exhausted":      "😔 Code Exhausted",
    }
    for msg in messages:
        label = nice_names.get(msg["key"], f"📝 {msg['key']}")
        rows.append([_btn(label, f"edit_msg:{msg['key']}", style="primary")])
    rows.append([_btn("◀️ Back", "admin_menu", style="primary")])
    return InlineKeyboardMarkup(rows)


async def button_list_keyboard() -> InlineKeyboardMarkup:
    from config import DEFAULT_BUTTONS
    rows = []
    for key in DEFAULT_BUTTONS:
        rows.append([_btn(f"🔘 {key}", f"edit_btn:{key}", style="primary")])
    rows.append([_btn("◀️ Back", "admin_menu", style="primary")])
    return InlineKeyboardMarkup(rows)


async def admin_manager_keyboard(admins: list[int]) -> InlineKeyboardMarkup:
    rows = []
    for uid in admins:
        rows.append([
            _btn(f"👤 {uid}", "noop",             style="primary"),
            _btn("❌ Remove", f"remove_admin:{uid}", style="danger"),
        ])
    rows.append([_btn("➕ Add Admin", "add_admin",  style="success")])
    rows.append([_btn("◀️ Back",      "admin_menu", style="primary")])
    return InlineKeyboardMarkup(rows)


async def confirm_keyboard(yes_cb: str, no_cb: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            _btn("✅ Yes, Confirm", yes_cb, style="success"),
            _btn("❌ Cancel",        no_cb,  style="danger"),
        ]
    ])


# ─── BOT SETTINGS KEYBOARD ────────────────────────────────────────────────────

async def bot_settings_keyboard(ref_pts: str, redeem_cost: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [_btn("🔑 Change Bot Token",               "admin_change_token",    style="danger")],
        [
            _btn(f"💎 Referral Pts: {ref_pts}",    "admin_set_ref_pts",     style="success"),
            _btn(f"💸 Redeem Cost: {redeem_cost}", "admin_set_redeem_cost", style="primary"),
        ],
        [_btn("◀️ Back", "admin_menu", style="primary")],
    ])


# ─── BROADCAST KEYBOARDS ──────────────────────────────────────────────────────

async def broadcast_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [_btn("📣 Send Broadcast Now", "broadcast_start", style="danger")],
        [_btn("◀️ Back",               "admin_menu",      style="primary")],
    ])


# ─── REDEEM CODE KEYBOARDS ────────────────────────────────────────────────────

async def gen_code_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            _btn("🎟 Generate New Code", "gen_code_start", style="success"),
            _btn("📋 View All Codes",    "list_codes",     style="primary"),
        ],
        [_btn("◀️ Back", "admin_menu", style="primary")],
    ])


async def code_list_keyboard(codes: list[dict]) -> InlineKeyboardMarkup:
    rows = []
    for c in codes:
        status = "✅" if c.get("is_active") else "🔴"
        label  = f"{status} {c['code']} • {c['points_value']}pts • {c['current_uses']}/{c['max_uses']}"
        rows.append([
            _btn(label,     "noop",                  style="primary"),
            _btn("🗑 Del",  f"del_code:{c['_id']}",  style="danger"),
        ])
    if not codes:
        rows.append([_btn("📭 No codes yet", "noop", style="primary")])
    rows.append([_btn("🎟 Generate New", "gen_code_start", style="success")])
    rows.append([_btn("◀️ Back",         "admin_gen_code", style="primary")])
    return InlineKeyboardMarkup(rows)
