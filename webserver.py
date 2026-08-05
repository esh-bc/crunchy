"""
╔══════════════════════════════════════════════════╗
║   LIGHTWEIGHT WEB SERVER                         ║
║   For Render hosting + UptimeRobot monitoring    ║
║   Developer: @iam_eshh                           ║
╚══════════════════════════════════════════════════╝
"""

import asyncio
import logging
import time
import psutil
from aiohttp import web
from config import WEB_HOST, WEB_PORT, BOT_VERSION, DEVELOPER

logger = logging.getLogger(__name__)
_start_time = time.time()


async def handle_health(request: web.Request) -> web.Response:
    """Health check endpoint — returns 200 OK for UptimeRobot."""
    uptime = int(time.time() - _start_time)
    cpu    = psutil.cpu_percent()
    mem    = psutil.virtual_memory().percent
    return web.json_response({
        "status":  "online",
        "bot":     BOT_VERSION,
        "dev":     DEVELOPER,
        "uptime":  uptime,
        "cpu":     cpu,
        "mem":     mem,
    })


async def handle_index(request: web.Request) -> web.Response:
    """Root endpoint — simple HTML status page."""
    uptime  = int(time.time() - _start_time)
    hours   = uptime // 3600
    minutes = (uptime % 3600) // 60
    secs    = uptime % 60

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>🎌 Crunchyroll Bot — Status</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: 'Segoe UI', sans-serif;
            background: linear-gradient(135deg, #0f0c29, #302b63, #24243e);
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            color: white;
        }}
        .card {{
            background: rgba(255,255,255,0.07);
            backdrop-filter: blur(20px);
            border: 1px solid rgba(255,255,255,0.1);
            border-radius: 24px;
            padding: 48px 40px;
            max-width: 500px;
            width: 90%;
            text-align: center;
        }}
        .emoji {{ font-size: 64px; margin-bottom: 16px; }}
        h1 {{ font-size: 28px; font-weight: 700; margin-bottom: 8px; }}
        .tag {{ color: #a78bfa; font-size: 14px; margin-bottom: 32px; }}
        .status-dot {{
            display: inline-block;
            width: 12px; height: 12px;
            background: #22c55e;
            border-radius: 50%;
            animation: pulse 2s infinite;
            margin-right: 8px;
        }}
        @keyframes pulse {{
            0%, 100% {{ opacity: 1; }}
            50% {{ opacity: 0.4; }}
        }}
        .status-line {{
            display: flex; align-items: center;
            background: rgba(255,255,255,0.05);
            border-radius: 12px;
            padding: 14px 20px;
            margin-bottom: 12px;
            justify-content: space-between;
        }}
        .label {{ color: rgba(255,255,255,0.6); font-size: 14px; }}
        .value {{ font-weight: 600; font-size: 15px; }}
        .green {{ color: #4ade80; }}
        .purple {{ color: #c084fc; }}
        .footer {{ margin-top: 28px; color: rgba(255,255,255,0.4); font-size: 12px; }}
    </style>
</head>
<body>
    <div class="card">
        <div class="emoji">🎌</div>
        <h1>Crunchyroll Bot</h1>
        <p class="tag">v{BOT_VERSION} · {DEVELOPER}</p>
        <div class="status-line">
            <span class="label"><span class="status-dot"></span>Status</span>
            <span class="value green">● ONLINE</span>
        </div>
        <div class="status-line">
            <span class="label">⏱ Uptime</span>
            <span class="value">{hours:02d}h {minutes:02d}m {secs:02d}s</span>
        </div>
        <div class="status-line">
            <span class="label">🧠 RAM</span>
            <span class="value">{psutil.virtual_memory().percent:.1f}%</span>
        </div>
        <div class="status-line">
            <span class="label">💻 CPU</span>
            <span class="value">{psutil.cpu_percent():.1f}%</span>
        </div>
        <p class="footer">Powered by Telegram Bot API 10.2 · Built for peak performance</p>
    </div>
</body>
</html>"""
    return web.Response(text=html, content_type="text/html")


async def start_webserver():
    """
    Start the aiohttp web server.
    Tries WEB_PORT first, then falls back to a few alternatives.
    If all ports are in use, returns a dummy runner (bot still works fine).
    """
    app = web.Application()
    app.router.add_get("/", handle_index)
    app.router.add_get("/health", handle_health)
    app.router.add_get("/ping", lambda r: web.Response(text="pong"))

    runner = web.AppRunner(app)
    await runner.setup()

    # Try the configured port, then fallbacks
    candidates = [WEB_PORT, 8082, 8099, 8000, 9000]
    seen = set()
    for port in candidates:
        if port in seen:
            continue
        seen.add(port)
        try:
            site = web.TCPSite(runner, WEB_HOST, port)
            await site.start()
            logger.info(f"🌐 Web server running at http://{WEB_HOST}:{port}")
            return runner
        except OSError:
            logger.warning(f"Port {port} in use, trying next…")

    logger.warning("⚠️  Web server disabled — all candidate ports in use. Bot still works.")
    return runner
