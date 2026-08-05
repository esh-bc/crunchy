"""
╔══════════════════════════════════════════════════╗
║   SMART MESSAGE SENDER                           ║
║   Handles text / photo / video with captions     ║
║   Developer: @iam_eshh                           ║
╚══════════════════════════════════════════════════╝
"""

from telegram import Bot, InlineKeyboardMarkup, Message
from telegram.constants import ParseMode


async def send_rendered(
    bot: Bot,
    chat_id: int,
    rendered: dict,
    reply_markup: InlineKeyboardMarkup = None,
) -> Message:
    """
    Send a rendered message dict.  Handles text-only, photo, or video.
    """
    parse_mode = rendered.get("parse_mode") or ParseMode.HTML
    text       = rendered.get("content") or ""
    media_file = rendered.get("media_file")
    media_type = rendered.get("media_type")

    if media_file and media_type == "photo":
        return await bot.send_photo(
            chat_id=chat_id,
            photo=media_file,
            caption=text,
            parse_mode=parse_mode,
            reply_markup=reply_markup,
        )
    elif media_file and media_type == "video":
        return await bot.send_video(
            chat_id=chat_id,
            video=media_file,
            caption=text,
            parse_mode=parse_mode,
            reply_markup=reply_markup,
        )
    else:
        return await bot.send_message(
            chat_id=chat_id,
            text=text,
            parse_mode=parse_mode,
            reply_markup=reply_markup,
        )


async def edit_rendered(
    bot: Bot,
    chat_id: int,
    message_id: int,
    rendered: dict,
    reply_markup: InlineKeyboardMarkup = None,
):
    """Edit an existing message with rendered content."""
    parse_mode = rendered.get("parse_mode") or ParseMode.HTML
    text       = rendered.get("content") or ""

    await bot.edit_message_text(
        chat_id=chat_id,
        message_id=message_id,
        text=text,
        parse_mode=parse_mode,
        reply_markup=reply_markup,
    )
