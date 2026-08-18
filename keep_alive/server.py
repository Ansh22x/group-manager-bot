import os
import logging
from threading import Thread
from keep_alive.app import app

logger = logging.getLogger(__name__)

def run():
    """Runs the Flask web server on the assigned port"""
    port = int(os.environ.get('PORT', 10000))
    
    # Silence verbose routing logs of Werkzeug to keep console logs clean
    werkzeug_logger = logging.getLogger('werkzeug')
    werkzeug_logger.setLevel(logging.ERROR)
    
    logger.info(f"Keep-Alive Flask server running on port {port}...")
    app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)

def keep_alive():
    """Starts the Flask server in a background daemon thread"""
    t = Thread(target=run)
    t.daemon = True
    t.start()
