import time
from flask import Flask, jsonify, render_template_string
from keep_alive.utils import get_uptime_string, check_database_connection
from keep_alive.templates import HTML_PAGE

app = Flask("GiyuBotKeepAlive")

# Record server boot time
START_TIME = time.time()

@app.route('/')
def home():
    """Renders the HTML live status page dashboard"""
    db_connected, db_status = check_database_connection()
    db_status_color = "#10b981" if db_connected else "#ef4444"
    
    return render_template_string(
        HTML_PAGE,
        db_status=db_status,
        db_status_color=db_status_color,
        uptime=get_uptime_string(START_TIME)
    )

@app.route('/health')
def health():
    """API endpoint to retrieve live status metrics in JSON format"""
    db_connected, db_status = check_database_connection()
    
    return jsonify({
        "status": "healthy",
        "uptime": get_uptime_string(START_TIME),
        "database": db_status.lower(),
        "timestamp": time.time()
    }), 200 if db_connected else 500
