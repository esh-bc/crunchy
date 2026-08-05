# Crunchyroll Referral Bot

A Telegram referral bot that gives users free Crunchyroll Premium accounts in exchange for earning points by referring friends. Admins manage channels, accounts, buttons, and messages via an in-chat admin panel.

## Run

```
cd crunchyroll
pip install -r requirements.txt
python3 main.py
```

## Stack

- Python 3.12, python-telegram-bot ≥ 22.3, Bot API 10.2
- MongoDB via Motor (async driver)
- GitHub Actions workflow for hosting (`.github/workflows/main.yml`)

## Key files

- `main.py` — entry point, registers all handlers
- `config.py` — BOT_TOKEN, OWNER_ID, MONGO_URI, default messages/buttons
- `database.py` — all MongoDB operations (users, buttons, messages, accounts, codes)
- `keyboards.py` — all InlineKeyboardMarkup builders; fetches emoji_id from DB
- `handlers/admin.py` — admin panel: message editor, button editor, broadcast, etc.
- `handlers/user.py` — /start, verify, redeem, refer, leaderboard, stock, proof
- `sender.py` — smart message sender (text / photo / video)
- `templates.py` — placeholder rendering ({first_name}, {points}, etc.)

## Premium emoji support (custom fix)

### Buttons (`icon_custom_emoji_id`)
- Each button doc in MongoDB has an `emoji_id` field (default `null`)
- All keyboards that pull buttons from DB now pass `emoji_id` to `_btn()` → sets `icon_custom_emoji_id` on the button
- To set a premium emoji on a button via admin panel → 🔘 Buttons → select button → send:
  ```
  Button Label
  emoji_id:5368324170671202286
  ```
  To remove: send label + `emoji_id:none`. Label-only sends preserve the existing emoji.

### Messages (`<tg-emoji>` HTML)
- When an admin updates a message template and includes premium (custom) emojis, the bot extracts the `custom_emoji` MessageEntity objects, converts them to `<tg-emoji emoji-id="ID">char</tg-emoji>` HTML tags, and stores that HTML.
- Messages are sent with `parse_mode=HTML`, which renders `<tg-emoji>` as the animated premium emoji.
- Works for both text messages and photo/video captions.

## User preferences

_Populate as you build._
