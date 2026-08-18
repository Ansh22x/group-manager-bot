import os
import time
import logging
from threading import Thread
from flask import Flask, jsonify, render_template_string
from database.db_manager import DatabaseManager

logger = logging.getLogger(__name__)
app = Flask("GiyuBotKeepAlive")

# Track startup timestamp for uptime calculations
START_TIME = time.time()

# Gorgeous styled Water Breathing theme health monitor page
HTML_PAGE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Giyu-Bot | Health Monitor</title>
    <style>
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background-color: #0b1329;
            color: #f4f5f6;
            display: flex;
            justify-content: center;
            align-items: center;
            height: 100vh;
            margin: 0;
        }
        .container {
            background: rgba(28, 37, 65, 0.85);
            border-radius: 12px;
            padding: 30px;
            box-shadow: 0 8px 32px 0 rgba(0, 0, 0, 0.37);
            border: 2px solid #38bdf8;
            max-width: 500px;
            width: 100%;
            text-align: center;
        }
        h1 {
            color: #38bdf8;
            margin-bottom: 5px;
            font-size: 2.2rem;
            text-transform: uppercase;
            letter-spacing: 2px;
        }
        .subtitle {
            color: #94a3b8;
            margin-bottom: 25px;
            font-size: 0.95rem;
        }
        .status-badge {
            background-color: #10b981;
            color: white;
            padding: 8px 20px;
            border-radius: 50px;
            font-weight: bold;
            display: inline-block;
            margin-bottom: 25px;
            box-shadow: 0 0 15px rgba(16, 185, 129, 0.4);
        }
        .stats {
            text-align: left;
            background: #0f172a;
            padding: 15px 20px;
            border-radius: 8px;
            border-left: 4px solid #38bdf8;
        }
        .stat-item {
            margin: 10px 0;
            display: flex;
            justify-content: space-between;
        }
        .label {
            color: #94a3b8;
        }
        .value {
            font-weight: bold;
            color: #f8fafc;
        }
        .footer {
            margin-top: 25px;
            font-size: 0.8rem;
            color: #64748b;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>Giyu Tomioka</h1>
        <div class="subtitle">Water Breathing Style: Health Monitor</div>
        <div class="status-badge">🟢 SYSTEM ACTIVE</div>
        
        <div class="stats">
            <div class="stat-item">
                <span class="label">Database Connection:</span>
                <span class="value" style="color: {{ db_status_color }};">{{ db_status }}</span>
            </div>
            <div class="stat-item">
                <span class="label">System Uptime:</span>
                <span class="value">{{ uptime }}</span>
            </div>
            <div class="stat-item">
                <span class="label">Server Status:</span>
                <span class="value" style="color: #38bdf8;">Dead Calm 🌊</span>
            </div>
        </div>
        
        <div class="footer">
            Giyu-Bot is running and polling for group messages.
        </div>
    </div>
</body>
</html>
"""

def get_uptime_string() -> str:
    uptime_seconds = int(time.time() - START_TIME)
    days, remainder = divmod(uptime_seconds, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, seconds = divmod(remainder, 60)
    
    parts = []
    if days > 0:
        parts.append(f"{days}d")
    if hours > 0:
        parts.append(f"{hours}h")
    if minutes > 0:
        parts.append(f"{minutes}m")
    parts.append(f"{seconds}s")
    return " ".join(parts)

@app.route('/')
def home():
    # Test database link live health
    db = DatabaseManager()
    db_status = "Connected"
    db_status_color = "#10b981"
    
    try:
        conn = db.get_connection()
        with conn.cursor() as cur:
            cur.execute("SELECT 1;")
        db.release_connection(conn)
    except Exception:
        db_status = "Disconnected"
        db_status_color = "#ef4444"
        
    return render_template_string(
        HTML_PAGE,
        db_status=db_status,
        db_status_color=db_status_color,
        uptime=get_uptime_string()
    )

@app.route('/health')
def health():
    # REST Endpoint for ping utilities (Better Uptime, UptimeRobot, etc.)
    db = DatabaseManager()
    db_connected = False
    try:
        conn = db.get_connection()
        with conn.cursor() as cur:
            cur.execute("SELECT 1;")
        db.release_connection(conn)
        db_connected = True
    except Exception:
        pass
        
    return jsonify({
        "status": "healthy",
        "uptime": get_uptime_string(),
        "database": "connected" if db_connected else "disconnected",
        "timestamp": time.time()
    }), 200 if db_connected else 500

def run():
    port = int(os.environ.get('PORT', 10000))
    # Mute default routing logs of Werkzeug to keep console clean
    werkzeug_logger = logging.getLogger('werkzeug')
    werkzeug_logger.setLevel(logging.ERROR)
    
    logger.info(f"Keep-Alive Flask server running on port {port}...")
    app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)

def keep_alive():
    t = Thread(target=run)
    t.daemon = True
    t.start()
