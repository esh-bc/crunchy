"""
╔══════════════════════════════════════════════════╗
║   OWNER SETUP — runs inside post_init            ║
║   Sets OWNER_ID from .env / config into the DB   ║
║   Developer: @iam_eshh                           ║
╚══════════════════════════════════════════════════╝
"""

import logging
import database as db
from config import OWNER_ID_DEFAULT

logger = logging.getLogger(__name__)


async def ensure_owner():
    """
    Persist the owner ID to DB on every startup so the admin panel
    always reflects whatever is set in the environment or config.py.

    Priority:
      1. OWNER_ID env var  (set at runtime / hosting dashboard)
      2. OWNER_ID_DEFAULT in config.py  (fallback hardcoded value)
    """
    # OWNER_ID_DEFAULT already resolves os.getenv("OWNER_ID", "8264404281")
    # so this always has a non-empty value as long as config.py is correct.
    owner = OWNER_ID_DEFAULT.strip()

    if not owner:
        logger.warning("⚠️  No OWNER_ID configured! Set OWNER_ID in .env or config.py to access /admin")
        return

    db_owner = await db.get_setting("owner_id", "")

    if db_owner != owner:
        await db.set_setting("owner_id", owner)
        logger.info(f"✅ Owner ID updated in DB: {owner}")
    else:
        logger.info(f"👑 Owner already set: {owner}")
