# Giyu-Bot Keep-Alive Premium HTML Landing Template

HTML_PAGE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Giyu-Bot | Core Control Hub</title>
    <!-- Modern Typography -->
    <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700;800&family=Fira+Code:wght@400;500&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg-color: #030712;
            --container-bg: rgba(17, 24, 39, 0.65);
            --border-color: rgba(56, 189, 248, 0.15);
            --primary: #38bdf8;
            --primary-glow: rgba(56, 189, 248, 0.25);
            --text-main: #f8fafc;
            --text-sub: #94a3b8;
            --success: #10b981;
            --success-glow: rgba(16, 185, 129, 0.15);
            --danger: #ef4444;
            --danger-glow: rgba(239, 68, 68, 0.15);
            --card-bg: rgba(15, 23, 42, 0.4);
        }

        * {
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }

        body {
            font-family: 'Outfit', sans-serif;
            background: radial-gradient(circle at 50% 50%, rgba(4, 28, 60, 1) 0%, rgba(3, 7, 18, 1) 100%);
            color: var(--text-main);
            min-height: 100vh;
            display: flex;
            justify-content: center;
            align-items: center;
            padding: 40px 20px;
        }

        .dashboard-container {
            width: 100%;
            max-width: 1100px;
            background: var(--container-bg);
            backdrop-filter: blur(20px);
            -webkit-backdrop-filter: blur(20px);
            border: 1px solid var(--border-color);
            border-radius: 24px;
            padding: 40px;
            box-shadow: 0 30px 80px rgba(0, 0, 0, 0.6), 0 0 50px rgba(56, 189, 248, 0.05);
            position: relative;
            overflow: hidden;
        }

        /* Water wave animation background overlay */
        .waves-bg {
            position: absolute;
            bottom: 0;
            left: 0;
            width: 100%;
            height: 120px;
            opacity: 0.05;
            pointer-events: none;
            z-index: 1;
        }

        /* Header styling */
        header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            border-bottom: 1px solid rgba(255, 255, 255, 0.08);
            padding-bottom: 25px;
            margin-bottom: 35px;
            z-index: 10;
            position: relative;
        }

        .brand h1 {
            font-size: 2.2rem;
            font-weight: 800;
            letter-spacing: 2px;
            background: linear-gradient(135deg, #60a5fa, #38bdf8, #0ea5e9);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            text-transform: uppercase;
        }

        .brand p {
            color: var(--text-sub);
            font-size: 0.95rem;
            margin-top: 4px;
            font-weight: 300;
        }

        .status-badge {
            background: var(--success-glow);
            border: 1px solid var(--success);
            color: var(--success);
            padding: 8px 20px;
            border-radius: 50px;
            font-weight: 600;
            font-size: 0.85rem;
            display: flex;
            align-items: center;
            gap: 10px;
            box-shadow: 0 0 20px rgba(16, 185, 129, 0.2);
            letter-spacing: 1px;
        }

        .pulse-dot {
            width: 8px;
            height: 8px;
            background-color: var(--success);
            border-radius: 50%;
            animation: pulse 1.8s infinite;
        }

        @keyframes pulse {
            0% { transform: scale(0.9); opacity: 1; }
            50% { transform: scale(1.4); opacity: 0.4; }
            100% { transform: scale(0.9); opacity: 1; }
        }

        /* KPI Cards Grid */
        .kpi-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
            gap: 20px;
            margin-bottom: 35px;
            z-index: 10;
            position: relative;
        }

        .kpi-card {
            background: var(--card-bg);
            border: 1px solid rgba(255, 255, 255, 0.05);
            border-radius: 16px;
            padding: 24px;
            display: flex;
            flex-direction: column;
            justify-content: space-between;
            transition: all 0.3s ease;
            position: relative;
        }

        .kpi-card:hover {
            transform: translateY(-4px);
            background: rgba(15, 23, 42, 0.65);
            border-color: var(--border-color);
            box-shadow: 0 10px 30px rgba(56, 189, 248, 0.08);
        }

        .kpi-label {
            color: var(--text-sub);
            font-size: 0.85rem;
            font-weight: 500;
            text-transform: uppercase;
            letter-spacing: 1px;
            margin-bottom: 15px;
        }

        .kpi-value {
            font-size: 2rem;
            font-weight: 700;
            color: var(--text-main);
            line-height: 1;
        }

        .kpi-desc {
            font-size: 0.75rem;
            color: var(--text-sub);
            margin-top: 8px;
            font-weight: 300;
        }

        /* Main Workspace Split Layout */
        .dashboard-body {
            display: grid;
            grid-template-columns: 1.2fr 1.8fr;
            gap: 25px;
            z-index: 10;
            position: relative;
        }

        @media (max-width: 900px) {
            .dashboard-body {
                grid-template-columns: 1fr;
            }
        }

        /* Columns panels container */
        .panel {
            background: rgba(15, 23, 42, 0.3);
            border: 1px solid rgba(255, 255, 255, 0.03);
            border-radius: 16px;
            padding: 25px;
        }

        .panel-title {
            font-size: 1.1rem;
            font-weight: 600;
            margin-bottom: 20px;
            color: var(--primary);
            letter-spacing: 1px;
            display: flex;
            align-items: center;
            gap: 8px;
        }

        /* Environment / Status List */
        .status-list {
            display: flex;
            flex-direction: column;
            gap: 15px;
        }

        .status-item {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding-bottom: 12px;
            border-bottom: 1px solid rgba(255, 255, 255, 0.04);
        }

        .status-item:last-child {
            border-bottom: none;
            padding-bottom: 0;
        }

        .status-name {
            font-size: 0.9rem;
            color: var(--text-sub);
        }

        .status-val {
            font-size: 0.9rem;
            font-weight: 600;
        }

        .badge {
            padding: 4px 10px;
            border-radius: 6px;
            font-size: 0.75rem;
            font-weight: 600;
            text-transform: uppercase;
        }

        .badge-green {
            background: var(--success-glow);
            border: 1px solid var(--success);
            color: var(--success);
        }

        .badge-red {
            background: var(--danger-glow);
            border: 1px solid var(--danger);
            color: var(--danger);
        }

        /* Terminal console log simulator */
        .terminal-container {
            background: #020617;
            border: 1px solid rgba(255, 255, 255, 0.05);
            border-radius: 12px;
            padding: 15px;
            font-family: 'Fira Code', monospace;
            font-size: 0.8rem;
            color: #38bdf8;
            max-height: 250px;
            overflow-y: auto;
            box-shadow: inset 0 2px 8px rgba(0, 0, 0, 0.8);
        }

        .terminal-line {
            margin-bottom: 6px;
            line-height: 1.4;
            white-space: pre-wrap;
        }

        .terminal-time {
            color: #64748b;
            margin-right: 8px;
        }

        .terminal-tag {
            color: #10b981;
            margin-right: 6px;
        }

        /* Quotes Player */
        .quote-panel {
            margin-top: 25px;
            background: rgba(56, 189, 248, 0.03);
            border: 1px solid rgba(56, 189, 248, 0.08);
            border-radius: 12px;
            padding: 18px;
            text-align: center;
            min-height: 80px;
            display: flex;
            flex-direction: column;
            justify-content: center;
            transition: opacity 0.5s ease;
        }

        .quote-text {
            font-style: italic;
            font-size: 0.9rem;
            color: var(--text-main);
            line-height: 1.5;
        }

        .quote-author {
            font-size: 0.75rem;
            color: var(--primary);
            margin-top: 8px;
            font-weight: 500;
            text-transform: uppercase;
        }
    </style>
</head>
<body>

    <div class="dashboard-container">
        <!-- SVG wave graphic underlay -->
        <svg class="waves-bg" viewBox="0 24 150 28" preserveAspectRatio="none" shape-rendering="auto">
            <defs>
                <path id="gentle-wave" d="M-160 44c30 0 58-18 88-18s58 18 88 18 58-18 88-18 58 18 88 18v44h-352z" />
            </defs>
            <g class="parallax">
                <use xlink:href="#gentle-wave" x="48" y="0" fill="rgba(56, 189, 248, 0.3)" />
                <use xlink:href="#gentle-wave" x="48" y="3" fill="rgba(56, 189, 248, 0.2)" />
                <use xlink:href="#gentle-wave" x="48" y="5" fill="rgba(56, 189, 248, 0.1)" />
            </g>
        </svg>

        <header>
            <div class="brand">
                <h1>Giyu Tomioka</h1>
                <p>Water Breathing Style • System Control Panel & Keep-Alive Panel</p>
            </div>
            <div class="status-badge">
                <span class="pulse-dot"></span>
                <span>ONLINE / ACTIVE</span>
            </div>
        </header>

        <!-- 4 Column KPI Stats Board -->
        <section class="kpi-grid">
            <div class="kpi-card">
                <div class="kpi-label">Active Groups</div>
                <div class="kpi-value" id="kpi-chats">{{ chats_count }}</div>
                <div class="kpi-desc">Chats running the bot</div>
            </div>
            <div class="kpi-card">
                <div class="kpi-label">Logged Members</div>
                <div class="kpi-value" id="kpi-users">{{ users_count }}</div>
                <div class="kpi-desc">Total user profiles stored</div>
            </div>
            <div class="kpi-card">
                <div class="kpi-label">Memory Lore</div>
                <div class="kpi-value" id="kpi-lore">{{ lore_count }}</div>
                <div class="kpi-desc">RAG vector chunks loaded</div>
            </div>
            <div class="kpi-card">
                <div class="kpi-label">KG Relations</div>
                <div class="kpi-value" id="kpi-triples">{{ triples_count }}</div>
                <div class="kpi-desc">Knowledge Graph connections</div>
            </div>
        </section>

        <!-- Main splits section -->
        <section class="dashboard-body">
            <!-- Left panel: environment and connectivity audits -->
            <div class="panel">
                <div class="panel-title">
                    ⚡ Server Audit Logs
                </div>
                <div class="status-list">
                    <div class="status-item">
                        <span class="status-name">Database Conn:</span>
                        <span class="status-val" id="db-status" style="color: {{ db_status_color }};">{{ db_status }}</span>
                    </div>
                    <div class="status-item">
                        <span class="status-name">System Uptime:</span>
                        <span class="status-val" id="uptime-val">{{ uptime }}</span>
                    </div>
                    <div class="status-item">
                        <span class="status-name">Bot Token:</span>
                        <span class="badge" style="background: {{ token_color }}; border: 1px solid {{ token_color }}; color: #fff;">{{ token_status }}</span>
                    </div>
                    <div class="status-item">
                        <span class="status-name">Mistral AI API:</span>
                        <span class="badge" style="background: {{ mistral_color }}; border: 1px solid {{ mistral_color }}; color: #fff;">{{ mistral_status }}</span>
                    </div>
                    <div class="status-item">
                        <span class="status-name">Supabase Connection:</span>
                        <span class="badge" style="background: {{ db_config_color }}; border: 1px solid {{ db_config_color }}; color: #fff;">{{ db_config_status }}</span>
                    </div>
                    <div class="status-item">
                        <span class="status-name">Water Breathing Form:</span>
                        <span class="status-val" style="color: var(--primary);">11th: Dead Calm</span>
                    </div>
                </div>

                <!-- Quote component panel -->
                <div class="quote-panel" id="quote-box">
                    <div class="quote-text" id="quote-text">"I am not disliked by people."</div>
                    <div class="quote-author">Giyu Tomioka</div>
                </div>
            </div>

            <!-- Right panel: live terminal logging emulator screen -->
            <div class="panel">
                <div class="panel-title">
                    📟 Live System Activity Console
                </div>
                <div class="terminal-container" id="terminal-screen">
                    <!-- Loaded dynamically via JS simulation logs -->
                    <div class="terminal-line"><span class="terminal-time">[15:30:11]</span><span class="terminal-tag">[SYSTEM]</span>Water Breathing Boot Sequence Initiated...</div>
                    <div class="terminal-line"><span class="terminal-time">[15:30:12]</span><span class="terminal-tag">[DATABASE]</span>Establishing connection to Supabase pooler...</div>
                    <div class="terminal-line"><span class="terminal-time">[15:30:13]</span><span class="terminal-tag">[DATABASE]</span>Database pooler handshake completed successfully.</div>
                    <div class="terminal-line"><span class="terminal-time">[15:30:14]</span><span class="terminal-tag">[AI_AGENT]</span>Configured autonomous ReAct completion loop.</div>
                    <div class="terminal-line"><span class="terminal-time">[15:30:15]</span><span class="terminal-tag">[SYSTEM]</span>Giyu-Bot is active and polling for chat updates.</div>
                </div>
            </div>
        </section>
    </div>

    <!-- Active dynamic updates & simulated logger JS -->
    <script>
        const quotes = [
            "\"I am not disliked by people.\"",
            "\"Feel the rage. The powerful, pure rage of not being able to forgive...\"",
            "\"Water Breathing, Eleventh Form: Dead Calm.\"",
            "\"Don't cry. Don't despair. Now is not the time for that.\"",
            "\"The weak have no rights or choices. Their only fate is to be relentlessly crushed by the strong!\""
        ];

        let quoteIndex = 0;
        setInterval(() => {
            const panel = document.getElementById('quote-box');
            panel.style.opacity = 0;
            setTimeout(() => {
                quoteIndex = (quoteIndex + 1) % quotes.length;
                document.getElementById('quote-text').innerText = quotes[quoteIndex];
                panel.style.opacity = 1;
            }, 500);
        }, 7000);

        // Simulated Logs generator to make the dashboard feel alive and interactive
        const logTemplates = [
            ["DATABASE", "SELECT COUNT(*) FROM chat_history executed (0.012s)"],
            ["AI_AGENT", "Similarity search completed on vector bot_lore space"],
            ["SYSTEM", "YouTube extractor bypassed bot signatures successfully"],
            ["DATABASE", "Inserted 1 warning row in warnings database table"],
            ["AI_AGENT", "Knowledge Graph retrieved 3 relations for entity 'giyu'"],
            ["SYSTEM", "Processed /play audio download task cleanly"],
            ["DATABASE", "Cleared old session tokens from database cache"],
            ["SYSTEM", "Memory usage stable at 144MB - CPU usage: 1.2%"]
        ];

        const terminalScreen = document.getElementById('terminal-screen');
        
        function appendSimulatedLog() {
            const time = new Date().toLocaleTimeString();
            const logItem = logTemplates[Math.floor(Math.random() * logTemplates.length)];
            const line = document.createElement('div');
            line.className = "terminal-line";
            line.innerHTML = `<span class="terminal-time">[${time}]</span><span class="terminal-tag">[${logItem[0]}]</span>${logItem[1]}`;
            terminalScreen.appendChild(line);
            terminalScreen.scrollTop = terminalScreen.scrollHeight;

            // Cap the terminal buffer lines at 25 items
            if (terminalScreen.children.length > 25) {
                terminalScreen.removeChild(terminalScreen.firstChild);
            }
        }
        setInterval(appendSimulatedLog, 6000);

        // Actual health endpoint data polling
        async function fetchSystemUpdates() {
            try {
                const response = await fetch('/health');
                const data = await response.json();
                
                document.getElementById('uptime-val').innerText = data.uptime;
                
                const dbStatusEl = document.getElementById('db-status');
                dbStatusEl.innerText = data.database === 'connected' ? 'Connected' : 'Disconnected';
                dbStatusEl.style.color = data.database === 'connected' ? '#10b981' : '#ef4444';
                
                if (data.database_stats) {
                    document.getElementById('kpi-chats').innerText = data.database_stats.chats;
                    document.getElementById('kpi-users').innerText = data.database_stats.users;
                    document.getElementById('kpi-lore').innerText = data.database_stats.lore;
                    document.getElementById('kpi-triples').innerText = data.database_stats.triples;
                }
            } catch (err) {
                console.error("Dashboard Status Polling Error:", err);
            }
        }
        setInterval(fetchSystemUpdates, 5000);
    </script>
</body>
</html>
"""
