"""
╔══════════════════════════════════════════════════╗
║   TEMPLATE ENGINE — DYNAMIC PLACEHOLDERS         ║
║   Developer: @iam_eshh                           ║
╚══════════════════════════════════════════════════╝
"""

from telegram import User
from database import (
    get_user_points, get_referral_count, get_stock_count,
    get_message, get_setting
)


async def build_referral_link(bot_username: str, user_id: int) -> str:
    return f"https://t.me/{bot_username}?start=ref_{user_id}"


def _mention(user: User) -> str:
    return f'<a href="tg://user?id={user.id}">{user.first_name}</a>'


async def render(key: str, user: User = None, bot_username: str = "",
                 extra: dict = None) -> dict:
    """
    Render a message template with all placeholders resolved.
    Returns dict with: content, media_file, media_type, parse_mode
    """
    msg = await get_message(key)
    text = msg.get("content") or ""

    if user:
        ref_link = await build_referral_link(bot_username, user.id)
        points   = await get_user_points(user.id)
        refs     = await get_referral_count(user.id)
        stock    = await get_stock_count()

        placeholders = {
            "{first_name}":    user.first_name or "",
            "{last_name}":     user.last_name or "",
            "{username}":      f"@{user.username}" if user.username else user.first_name,
            "{user_id}":       str(user.id),
            "{mention}":       _mention(user),
            "{referral_link}": ref_link,
            "{points}":        str(points),
            "{stock}":         str(stock),
            "{total_refs}":    str(refs),
        }
        for ph, val in placeholders.items():
            text = text.replace(ph, val)

    if extra:
        for ph, val in extra.items():
            text = text.replace(ph, str(val))

    return {
        "content":    text,
        "media_file": msg.get("media_file"),
        "media_type": msg.get("media_type"),
        "parse_mode": msg.get("parse_mode") or "HTML",
    }


async def render_text(template: str, user: User = None, bot_username: str = "",
                      extra: dict = None) -> str:
    """Render an arbitrary template string (not from DB)."""
    text = template

    if user:
        ref_link = await build_referral_link(bot_username, user.id)
        points   = await get_user_points(user.id)
        refs     = await get_referral_count(user.id)
        stock    = await get_stock_count()

        placeholders = {
            "{first_name}":    user.first_name or "",
            "{last_name}":     user.last_name or "",
            "{username}":      f"@{user.username}" if user.username else user.first_name,
            "{user_id}":       str(user.id),
            "{mention}":       _mention(user),
            "{referral_link}": ref_link,
            "{points}":        str(points),
            "{stock}":         str(stock),
            "{total_refs}":    str(refs),
        }
        for ph, val in placeholders.items():
            text = text.replace(ph, val)

    if extra:
        for ph, val in extra.items():
            text = text.replace(ph, str(val))

    return text
