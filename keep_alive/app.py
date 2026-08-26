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
        total_coins=f"{db_stats['total_coins']:,}",
        daily_streaks_count=db_stats["daily_streaks_count"],
        warnings_count=db_stats["warnings_count"],
        sample_triples=db_stats["sample_triples"],
        sample_lore=db_stats["sample_lore"],
        personas_distribution=db_stats["personas_distribution"],
        bot_level=db_stats["bot_level"],
        bot_xp=db_stats["bot_xp"],
        bot_traits=db_stats["bot_traits"],
        bot_skills=db_stats["bot_skills"],
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

@app.route('/logs')
def logs():
    """Renders the last 150 lines of the bot log file"""
    log_path = 'bot.log'
    if not os.path.exists(log_path):
        return "Log file not found yet.", 404
        
    try:
        with open(log_path, 'r', encoding='utf-8', errors='ignore') as f:
            lines = f.readlines()
            last_lines = lines[-150:]
            return render_template_string(
                "<html><body style='background-color:#1e1e1e;color:#f1f1f1;padding:20px;'><h2 style='color:#10b981;'>Giyu-Bot Live System Logs</h2><pre style='background:#2d2d2d;padding:15px;border-radius:5px;overflow-x:auto;'>{{ content }}</pre></body></html>",
                content="".join(last_lines)
            )
    except Exception as e:
        return f"Failed to read logs: {e}", 500
