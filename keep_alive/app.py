import os
import time
from flask import Flask, jsonify, render_template_string
from keep_alive.utils import get_uptime_string, check_database_connection, get_database_stats
from keep_alive.templates import HTML_PAGE

app = Flask("GiyuBotKeepAlive")

# Record server boot time
START_TIME = time.time()

@app.route('/')
def home():
    """Renders the HTML live status page dashboard"""
    db_connected, db_status = check_database_connection()
    db_status_color = "#10b981" if db_connected else "#ef4444"
    db_stats = get_database_stats()
    
    # Check configurations (badges)
    has_token = "Configured" if os.getenv("BOT_TOKEN") else "Missing"
    has_mistral = "Configured" if os.getenv("MISTRAL_API_KEY") else "Missing"
    has_db = "Configured" if os.getenv("DATABASE_URL") else "Missing"
    
    token_color = "#10b981" if os.getenv("BOT_TOKEN") else "#ef4444"
    mistral_color = "#10b981" if os.getenv("MISTRAL_API_KEY") else "#ef4444"
    db_color = "#10b981" if os.getenv("DATABASE_URL") else "#ef4444"

    return render_template_string(
        HTML_PAGE,
        db_status=db_status,
        db_status_color=db_status_color,
        uptime=get_uptime_string(START_TIME),
        chats_count=db_stats["chats"],
        users_count=db_stats["users"],
        lore_count=db_stats["lore"],
        triples_count=db_stats["triples"],
        token_status=has_token,
        token_color=token_color,
        mistral_status=has_mistral,
        mistral_color=mistral_color,
        db_config_status=has_db,
        db_config_color=db_color
    )

@app.route('/health')
def health():
    """API endpoint to retrieve live status metrics in JSON format"""
    db_connected, db_status = check_database_connection()
    db_stats = get_database_stats()
    
    return jsonify({
        "status": "healthy",
        "uptime": get_uptime_string(START_TIME),
        "database": db_status.lower(),
        "database_stats": db_stats,
        "environment": {
            "bot_token": bool(os.getenv("BOT_TOKEN")),
            "mistral_api_key": bool(os.getenv("MISTRAL_API_KEY")),
            "database_url": bool(os.getenv("DATABASE_URL"))
        },
        "timestamp": time.time()
    }), 200 if db_connected else 500
