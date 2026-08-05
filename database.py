"""
╔══════════════════════════════════════════════════╗
║   DATABASE HANDLER — FULL ASYNC MONGODB          ║
║   Replaces SQLite with MongoDB via Motor         ║
║   Account health: stock → working → broken       ║
║   Developer: @iam_eshh                           ║
╚══════════════════════════════════════════════════╝
"""

import logging
import random
import string
from datetime import datetime

from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import ASCENDING, DESCENDING, IndexModel

from config import (
    MONGO_URI, MONGO_DB_NAME,
    DEFAULT_MESSAGES, DEFAULT_BUTTONS,
    DEFAULT_REFERRAL_POINTS, DEFAULT_REDEEM_COST,
    BOT_TOKEN,
)

logger = logging.getLogger(__name__)

# ─── MODULE-LEVEL CLIENT ─────────────────────────────────────────────────────
_client: AsyncIOMotorClient = None
_db = None


def get_db():
    return _db


# ─── AUTO-INCREMENT HELPER ───────────────────────────────────────────────────

async def _get_next_id(collection_name: str) -> int:
    """Atomic auto-increment using a counters collection."""
    result = await _db.counters.find_one_and_update(
        {"_id": collection_name},
        {"$inc": {"seq": 1}},
        upsert=True,
        return_document=True,
    )
    return result["seq"]


# ─── INIT ─────────────────────────────────────────────────────────────────────

async def init_db():
    """Connect to MongoDB and initialize indexes + defaults."""
    global _client, _db
    _client = AsyncIOMotorClient(MONGO_URI)
    _db = _client[MONGO_DB_NAME]

    # Verify connection
    await _client.admin.command("ping")
    logger.info("✅ Connected to MongoDB.")

    # Create indexes
    await _db.referrals.create_index("referred_id", unique=True)
    await _db.referrals.create_index("referrer_id")
    await _db.accounts.create_index([("status", ASCENDING), ("times_given", ASCENDING), ("_id", ASCENDING)])
    await _db.accounts.create_index("email", unique=True, sparse=True)
    await _db.redeems.create_index("user_id")
    await _db.logs.create_index("timestamp")
    await _db.redeem_codes.create_index("code", unique=True)
    await _db.code_redemptions.create_index(
        [("code", ASCENDING), ("user_id", ASCENDING)], unique=True
    )

    # ── Migration: add status field to existing accounts without it ──────────
    await _db.accounts.update_many(
        {"status": {"$exists": False}},
        {"$set": {"status": "stock", "times_given": 0}},
    )

    await _seed_defaults()
    logger.info("✅ Database ready.")


async def _seed_defaults():
    """Seed default settings and messages if not already present."""
    defaults = {
        "referral_points":    str(DEFAULT_REFERRAL_POINTS),
        "redeem_cost":        str(DEFAULT_REDEEM_COST),
        "proof_channel":      "",
        "owner_id":           "",
        "welcome_media":      "",
        "welcome_media_type": "",
        "bot_active":         "1",
        "bot_token":          BOT_TOKEN,  # stored so hosting change is seamless
    }
    for k, v in defaults.items():
        await _db.settings.update_one(
            {"_id": k},
            {"$setOnInsert": {"_id": k, "value": v}},
            upsert=True,
        )

    # Messages
    for key, content in DEFAULT_MESSAGES.items():
        await _db.messages.update_one(
            {"_id": key},
            {"$setOnInsert": {
                "_id": key, "key": key, "content": content,
                "media_file": None, "media_type": None,
                "parse_mode": "HTML", "entities": None,
            }},
            upsert=True,
        )

    # Buttons
    for key, label in DEFAULT_BUTTONS.items():
        await _db.buttons.update_one(
            {"_id": key},
            {"$setOnInsert": {
                "_id": key, "key": key, "label": label,
                "emoji_id": None, "style": None,
            }},
            upsert=True,
        )


# ─── USER FUNCTIONS ───────────────────────────────────────────────────────────

async def get_user(user_id: int) -> dict | None:
    return await _db.users.find_one({"_id": user_id})


async def upsert_user(user_id: int, username: str, first_name: str, last_name: str = ""):
    await _db.users.update_one(
        {"_id": user_id},
        {
            "$set": {
                "username":   username or "",
                "first_name": first_name or "",
                "last_name":  last_name or "",
            },
            "$setOnInsert": {
                "_id":        user_id,
                "user_id":    user_id,
                "points":     0,
                "referred_by": None,
                "join_date":  datetime.utcnow().isoformat(),
                "is_banned":  False,
            },
        },
        upsert=True,
    )


async def add_points(user_id: int, points: int):
    await _db.users.update_one(
        {"_id": user_id},
        {"$inc": {"points": points}},
    )


async def deduct_points(user_id: int, points: int) -> bool:
    result = await _db.users.find_one_and_update(
        {"_id": user_id, "points": {"$gte": points}},
        {"$inc": {"points": -points}},
    )
    return result is not None


async def get_user_points(user_id: int) -> int:
    doc = await _db.users.find_one({"_id": user_id}, {"points": 1})
    return doc["points"] if doc else 0


async def get_referral_count(user_id: int) -> int:
    return await _db.referrals.count_documents({"referrer_id": user_id})


async def add_referral(referrer_id: int, referred_id: int) -> bool:
    """Returns True if referral was new and valid."""
    try:
        await _db.referrals.insert_one({
            "referrer_id": referrer_id,
            "referred_id": referred_id,
            "date": datetime.utcnow().isoformat(),
        })
        await _db.users.update_one(
            {"_id": referred_id, "referred_by": None},
            {"$set": {"referred_by": referrer_id}},
        )
        return True
    except Exception:
        return False


async def get_leaderboard(limit: int = 10) -> list[dict]:
    pipeline = [
        {"$group": {"_id": "$referrer_id", "ref_count": {"$sum": 1}}},
        {"$sort": {"ref_count": DESCENDING}},
        {"$limit": limit},
        {"$lookup": {
            "from": "users",
            "localField": "_id",
            "foreignField": "_id",
            "as": "user",
        }},
        {"$unwind": {"path": "$user", "preserveNullAndEmptyArrays": True}},
        {"$project": {
            "user_id":    "$_id",
            "first_name": {"$ifNull": ["$user.first_name", "Unknown"]},
            "username":   {"$ifNull": ["$user.username", ""]},
            "ref_count":  1,
        }},
    ]
    cursor = _db.referrals.aggregate(pipeline)
    return await cursor.to_list(length=limit)


async def get_user_rank(user_id: int) -> int:
    my_refs = await get_referral_count(user_id)
    higher = await _db.referrals.aggregate([
        {"$group": {"_id": "$referrer_id", "count": {"$sum": 1}}},
        {"$match": {"count": {"$gt": my_refs}}},
        {"$count": "total"},
    ]).to_list(length=1)
    return (higher[0]["total"] if higher else 0) + 1


async def get_total_users() -> int:
    return await _db.users.count_documents({})


async def get_total_referrals() -> int:
    return await _db.referrals.count_documents({})


async def get_all_user_ids() -> list[int]:
    """Return all user IDs — used for broadcast."""
    cursor = _db.users.find({}, {"_id": 1})
    docs = await cursor.to_list(length=None)
    return [d["_id"] for d in docs]


# ─── ACCOUNT FUNCTIONS ────────────────────────────────────────────────────────
# Account status lifecycle:
#   "stock"   — freshly added, not yet tested
#   "working" — confirmed working by at least one user (priority delivery)
#   "broken"  — reported not working, permanently removed from pool

async def add_accounts_bulk(accounts: list[tuple[str, str]]) -> int:
    """Insert (email, password) tuples. Returns count of newly added."""
    added = 0
    for email, password in accounts:
        try:
            next_id = await _get_next_id("accounts")
            await _db.accounts.insert_one({
                "_id":         next_id,
                "email":       email.strip(),
                "password":    password.strip(),
                "added_date":  datetime.utcnow().isoformat(),
                "is_used":     False,
                "used_by":     None,
                "used_date":   None,
                "status":      "stock",   # health tracking
                "times_given": 0,         # how many users received this
            })
            added += 1
        except Exception:
            pass  # Duplicate email — skip
    return added


async def get_next_account() -> dict | None:
    """
    Deliver accounts in priority order:
      1. "working" — confirmed good, given to fewest users first
      2. "stock"   — untested fresh accounts
    Never deliver "broken" accounts.
    """
    # Priority 1: confirmed working, least-used first
    acc = await _db.accounts.find_one(
        {"status": "working"},
        sort=[("times_given", ASCENDING), ("_id", ASCENDING)],
    )
    if acc:
        return acc
    # Priority 2: fresh untested stock
    return await _db.accounts.find_one(
        {"status": {"$in": ["stock", None]}},
        sort=[("_id", ASCENDING)],
    )


async def increment_account_given(account_id: int, user_id: int):
    """Record that this account was given to a user."""
    await _db.accounts.update_one(
        {"_id": account_id},
        {
            "$inc": {"times_given": 1},
            "$set": {"is_used": True, "used_by": user_id, "used_date": datetime.utcnow().isoformat()},
        },
    )


async def mark_account_working(account_id: int):
    """
    User confirmed this account works.
    Keep it in the pool (is_used=False) so it can serve future users.
    """
    await _db.accounts.update_one(
        {"_id": account_id},
        {"$set": {"status": "working", "is_used": False}},
    )


async def mark_account_broken(account_id: int):
    """User reported this account doesn't work — remove from pool permanently."""
    await _db.accounts.update_one(
        {"_id": account_id},
        {"$set": {"status": "broken", "is_used": True}},
    )


# Keep for backward compatibility (legacy calls)
async def mark_account_used(account_id: int, user_id: int):
    await increment_account_given(account_id, user_id)


async def get_stock_count() -> int:
    """Count accounts available to deliver (working + untested stock)."""
    return await _db.accounts.count_documents(
        {"status": {"$in": ["stock", "working", None]}}
    )


async def clear_unused_accounts():
    """Delete only untested stock accounts (working confirmed ones are preserved)."""
    result = await _db.accounts.delete_many({"status": {"$in": ["stock", None]}})
    return result.deleted_count


# ─── REDEEM FUNCTIONS ─────────────────────────────────────────────────────────

async def create_redeem(user_id: int, account_id: int) -> int:
    next_id = await _get_next_id("redeems")
    await _db.redeems.insert_one({
        "_id":             next_id,
        "user_id":         user_id,
        "account_id":      account_id,
        "status":          "pending",
        "replacements":    0,
        "screenshot_file": None,
        "redeem_date":     datetime.utcnow().isoformat(),
        "proof_sent":      False,
    })
    return next_id


async def get_redeem(redeem_id: int) -> dict | None:
    return await _db.redeems.find_one({"_id": redeem_id})


async def update_redeem_status(redeem_id: int, status: str):
    await _db.redeems.update_one(
        {"_id": redeem_id},
        {"$set": {"status": status}},
    )


async def increment_replacements(redeem_id: int) -> int:
    result = await _db.redeems.find_one_and_update(
        {"_id": redeem_id},
        {"$inc": {"replacements": 1}},
        return_document=True,
    )
    return result["replacements"] if result else 0


async def set_redeem_screenshot(redeem_id: int, file_id: str):
    await _db.redeems.update_one(
        {"_id": redeem_id},
        {"$set": {
            "screenshot_file": file_id,
            "status":          "working",
            "proof_sent":      True,
        }},
    )


async def get_total_redeems() -> int:
    return await _db.redeems.count_documents({})


async def set_pending_screenshot(user_id: int, redeem_id: int, account_id: int):
    await _db.pending_screenshots.update_one(
        {"_id": user_id},
        {"$set": {
            "_id":        user_id,
            "user_id":    user_id,
            "redeem_id":  redeem_id,
            "account_id": account_id,
        }},
        upsert=True,
    )


async def get_pending_screenshot(user_id: int) -> dict | None:
    return await _db.pending_screenshots.find_one({"_id": user_id})


async def clear_pending_screenshot(user_id: int):
    await _db.pending_screenshots.delete_one({"_id": user_id})


# ─── CHANNEL FUNCTIONS ────────────────────────────────────────────────────────

async def add_channel(chat_id: str, username: str, title: str,
                      chan_type: str, invite_link: str = ""):
    await _db.channels.update_one(
        {"_id": chat_id},
        {"$set": {
            "_id":         chat_id,
            "chat_id":     chat_id,
            "username":    username or "",
            "title":       title or "",
            "type":        chan_type,
            "invite_link": invite_link or "",
            "added_date":  datetime.utcnow().isoformat(),
        }},
        upsert=True,
    )


async def remove_channel(chat_id: str):
    await _db.channels.delete_one({"_id": chat_id})


async def get_all_channels() -> list[dict]:
    cursor = _db.channels.find({})
    return await cursor.to_list(length=None)


# ─── SETTINGS FUNCTIONS ───────────────────────────────────────────────────────

async def get_setting(key: str, default=None):
    doc = await _db.settings.find_one({"_id": key})
    return doc["value"] if doc else default


async def set_setting(key: str, value: str):
    await _db.settings.update_one(
        {"_id": key},
        {"$set": {"_id": key, "value": value}},
        upsert=True,
    )


# ─── MESSAGE TEMPLATE FUNCTIONS ───────────────────────────────────────────────

async def get_message(key: str) -> dict:
    doc = await _db.messages.find_one({"_id": key})
    if doc:
        return doc
    return {
        "key": key, "content": DEFAULT_MESSAGES.get(key, ""),
        "media_file": None, "media_type": None, "parse_mode": "HTML",
    }


async def set_message(key: str, content: str = None, media_file: str = None,
                      media_type: str = None, parse_mode: str = "HTML"):
    await _db.messages.update_one(
        {"_id": key},
        {"$set": {
            "_id":        key,
            "key":        key,
            "content":    content,
            "media_file": media_file,
            "media_type": media_type,
            "parse_mode": parse_mode or "HTML",
        }},
        upsert=True,
    )


async def get_all_messages() -> list[dict]:
    cursor = _db.messages.find({}, sort=[("_id", ASCENDING)])
    return await cursor.to_list(length=None)


# ─── BUTTON FUNCTIONS ─────────────────────────────────────────────────────────

async def get_button(key: str) -> dict:
    doc = await _db.buttons.find_one({"_id": key})
    if doc:
        return doc
    return {"key": key, "label": DEFAULT_BUTTONS.get(key, key), "emoji_id": None, "style": None}


async def get_buttons_batch(keys: list) -> dict:
    """Fetch multiple buttons in ONE query. Returns {key: doc}."""
    docs = await _db.buttons.find({"_id": {"$in": keys}}).to_list(length=len(keys))
    result = {doc["_id"]: doc for doc in docs}
    for key in keys:
        if key not in result:
            result[key] = {"key": key, "label": DEFAULT_BUTTONS.get(key, key), "emoji_id": None, "style": None}
    return result


async def set_button(key: str, label: str, emoji_id: str = None, style: str = None):
    await _db.buttons.update_one(
        {"_id": key},
        {"$set": {
            "_id":      key,
            "key":      key,
            "label":    label,
            "emoji_id": emoji_id,
            "style":    style,
        }},
        upsert=True,
    )


# ─── ADMIN FUNCTIONS ──────────────────────────────────────────────────────────

async def is_admin(user_id: int) -> bool:
    owner = await get_setting("owner_id", "")
    if str(user_id) == str(owner):
        return True
    doc = await _db.admins.find_one({"_id": user_id})
    return doc is not None


async def add_admin(user_id: int, added_by: int):
    await _db.admins.update_one(
        {"_id": user_id},
        {"$setOnInsert": {
            "_id":        user_id,
            "user_id":    user_id,
            "added_by":   added_by,
            "added_date": datetime.utcnow().isoformat(),
        }},
        upsert=True,
    )


async def remove_admin(user_id: int):
    await _db.admins.delete_one({"_id": user_id})


async def get_all_admins() -> list[int]:
    cursor = _db.admins.find({}, {"_id": 1})
    docs = await cursor.to_list(length=None)
    return [d["_id"] for d in docs]


# ─── LOG FUNCTIONS ────────────────────────────────────────────────────────────

async def write_log(level: str, message: str):
    await _db.logs.insert_one({
        "level":     level,
        "message":   message,
        "timestamp": datetime.utcnow().isoformat(),
    })
    # Keep only last 500 logs
    count = await _db.logs.count_documents({})
    if count > 500:
        oldest = await _db.logs.find(
            {}, sort=[("timestamp", ASCENDING)]
        ).to_list(length=count - 500)
        ids = [d["_id"] for d in oldest]
        await _db.logs.delete_many({"_id": {"$in": ids}})


async def get_logs(limit: int = 100) -> list[dict]:
    cursor = _db.logs.find({}, sort=[("timestamp", DESCENDING)]).limit(limit)
    return await cursor.to_list(length=limit)


# ─── REDEMPTION CODE FUNCTIONS ────────────────────────────────────────────────

def _generate_code(length: int = 8) -> str:
    chars = string.ascii_uppercase + string.digits
    suffix = "".join(random.choices(chars, k=length))
    return f"CRUNCHY-{suffix}"


async def create_redeem_code(
    points_value: int,
    max_uses: int,
    created_by: int,
    custom_code: str = None,
) -> dict:
    code = custom_code or _generate_code()
    for _ in range(10):
        existing = await _db.redeem_codes.find_one({"code": code})
        if not existing:
            break
        code = _generate_code()

    next_id = await _get_next_id("redeem_codes")
    doc = {
        "_id":          next_id,
        "code":         code,
        "points_value": points_value,
        "max_uses":     max_uses,
        "current_uses": 0,
        "is_active":    True,
        "created_by":   created_by,
        "created_at":   datetime.utcnow().isoformat(),
    }
    await _db.redeem_codes.insert_one(doc)
    return doc


async def get_redeem_code(code: str) -> dict | None:
    return await _db.redeem_codes.find_one({"code": code.upper()})


async def get_all_redeem_codes(limit: int = 50) -> list[dict]:
    cursor = _db.redeem_codes.find({}, sort=[("_id", DESCENDING)]).limit(limit)
    return await cursor.to_list(length=limit)


async def use_redeem_code(code: str, user_id: int) -> dict:
    code = code.upper().strip()

    code_doc = await _db.redeem_codes.find_one({"code": code, "is_active": True})
    if not code_doc:
        return {"ok": False, "reason": "invalid", "points": 0}

    already = await _db.code_redemptions.find_one({"code": code, "user_id": user_id})
    if already:
        return {"ok": False, "reason": "already_used", "points": 0}

    if code_doc["current_uses"] >= code_doc["max_uses"]:
        return {"ok": False, "reason": "exhausted", "points": 0}

    updated = await _db.redeem_codes.find_one_and_update(
        {
            "code":         code,
            "is_active":    True,
            "current_uses": {"$lt": code_doc["max_uses"]},
        },
        {"$inc": {"current_uses": 1}},
        return_document=True,
    )
    if not updated:
        return {"ok": False, "reason": "exhausted", "points": 0}

    if updated["current_uses"] >= updated["max_uses"]:
        await _db.redeem_codes.update_one(
            {"code": code},
            {"$set": {"is_active": False}},
        )

    await _db.code_redemptions.insert_one({
        "code":        code,
        "user_id":     user_id,
        "redeemed_at": datetime.utcnow().isoformat(),
    })

    await add_points(user_id, updated["points_value"])
    return {"ok": True, "reason": "success", "points": updated["points_value"]}


async def delete_redeem_code(code_id: int):
    await _db.redeem_codes.delete_one({"_id": code_id})


async def deactivate_redeem_code(code_id: int):
    await _db.redeem_codes.update_one(
        {"_id": code_id},
        {"$set": {"is_active": False}},
    )
