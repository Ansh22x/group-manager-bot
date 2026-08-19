import os
import time
import logging
import urllib.request
from threading import Thread
from keep_alive.app import app

logger = logging.getLogger(__name__)

# Render automatically exposes this env var with the service's public URL
RENDER_URL = os.environ.get('RENDER_EXTERNAL_URL', '')
PING_INTERVAL_SECONDS = 10 * 60  # 10 minutes — well under Render's 15-min sleep threshold

def _self_ping():
    """
    Pings the bot's own /health endpoint every 10 minutes.
    Render free tier sleeps after 15 min of inactivity — this prevents that.
    """
    # Wait for Flask to fully start before first ping
    time.sleep(30)

    while True:
        if RENDER_URL:
            url = f"{RENDER_URL.rstrip('/')}/health"
        else:
            port = int(os.environ.get('PORT', 10000))
            url = f"http://localhost:{port}/health"

        try:
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "GiyuBot-KeepAlive/1.0"}
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                logger.info(f"Keep-alive ping → {url} [{resp.status}]")
        except Exception as e:
            logger.warning(f"Keep-alive ping failed: {e}")

        time.sleep(PING_INTERVAL_SECONDS)

def run():
    """Runs the Flask web server on the assigned port"""
    port = int(os.environ.get('PORT', 10000))
    
    # Silence verbose routing logs of Werkzeug to keep console logs clean
    werkzeug_logger = logging.getLogger('werkzeug')
    werkzeug_logger.setLevel(logging.ERROR)
    
    logger.info(f"Keep-Alive Flask server running on port {port}...")
    app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)

def keep_alive():
    """Starts the Flask server + self-pinger in background daemon threads"""
    # Flask server thread
    flask_thread = Thread(target=run, name="FlaskServer")
    flask_thread.daemon = True
    flask_thread.start()

    # Self-pinger thread — keeps Render from sleeping
    ping_thread = Thread(target=_self_ping, name="SelfPinger")
    ping_thread.daemon = True
    ping_thread.start()
    logger.info(f"Self-pinger started (interval: {PING_INTERVAL_SECONDS // 60} min, target: {RENDER_URL or 'localhost'})")
