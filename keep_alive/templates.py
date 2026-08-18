# Giyu-Bot Keep-Alive Premium HTML Landing Template

HTML_PAGE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Giyu-Bot | Status Panel</title>
    <!-- Modern Typography -->
    <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600;800&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg-color: #030712;
            --container-bg: rgba(17, 24, 39, 0.7);
            --border-color: rgba(56, 189, 248, 0.3);
            --primary: #38bdf8;
            --primary-glow: rgba(56, 189, 248, 0.4);
            --text-main: #f8fafc;
            --text-sub: #94a3b8;
            --success: #10b981;
            --success-glow: rgba(16, 185, 129, 0.3);
            --danger: #ef4444;
        }

        * {
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }

        body {
            font-family: 'Outfit', sans-serif;
            background: radial-gradient(circle at 10% 20%, rgba(4, 21, 45, 1) 0%, rgba(3, 7, 18, 1) 90%);
            color: var(--text-main);
            display: flex;
            justify-content: center;
            align-items: center;
            min-height: 100vh;
            overflow: hidden;
            padding: 20px;
        }

        /* Water breathing background ripple effects */
        .water-waves {
            position: absolute;
            bottom: 0;
            left: 0;
            width: 100%;
            height: 150px;
            overflow: hidden;
            z-index: 1;
            opacity: 0.15;
            pointer-events: none;
        }

        /* Glassmorphism card container */
        .glass-card {
            background: var(--container-bg);
            backdrop-filter: blur(16px);
            -webkit-backdrop-filter: blur(16px);
            border: 1px solid var(--border-color);
            border-radius: 20px;
            padding: 40px;
            width: 100%;
            max-width: 520px;
            text-align: center;
            box-shadow: 0 20px 50px rgba(0, 0, 0, 0.5);
            z-index: 10;
            position: relative;
            transform: translateY(0);
            transition: transform 0.3s ease, box-shadow 0.3s ease;
        }

        .glass-card:hover {
            transform: translateY(-5px);
            box-shadow: 0 25px 60px rgba(56, 189, 248, 0.15);
        }

        /* Title styling */
        h1 {
            font-size: 2.5rem;
            font-weight: 800;
            background: linear-gradient(to right, #38bdf8, #0ea5e9, #0284c7);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            letter-spacing: 3px;
            text-transform: uppercase;
            margin-bottom: 5px;
        }

        .subtitle {
            font-size: 1rem;
            color: var(--text-sub);
            margin-bottom: 30px;
            letter-spacing: 1px;
            font-weight: 300;
        }

        /* Pulsing Health Badge */
        .status-badge {
            background: var(--success-glow);
            border: 1px solid var(--success);
            color: var(--success);
            padding: 8px 24px;
            border-radius: 50px;
            font-weight: 600;
            font-size: 0.9rem;
            display: inline-flex;
            align-items: center;
            gap: 8px;
            margin-bottom: 35px;
            box-shadow: 0 0 15px var(--success-glow);
            letter-spacing: 1px;
        }

        .pulse-dot {
            width: 8px;
            height: 8px;
            background-color: var(--success);
            border-radius: 50%;
            display: inline-block;
            animation: pulse 1.8s infinite;
        }

        @keyframes pulse {
            0% {
                transform: scale(0.9);
                opacity: 1;
            }
            50% {
                transform: scale(1.4);
                opacity: 0.4;
            }
            100% {
                transform: scale(0.9);
                opacity: 1;
            }
        }

        /* Grid of metric stats cards */
        .stats-grid {
            display: grid;
            grid-template-columns: 1fr;
            gap: 15px;
            margin-bottom: 30px;
        }

        .stat-card {
            background: rgba(15, 23, 42, 0.6);
            border: 1px solid rgba(255, 255, 255, 0.05);
            border-radius: 12px;
            padding: 15px 20px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            transition: background 0.2s ease;
        }

        .stat-card:hover {
            background: rgba(15, 23, 42, 0.8);
            border-color: rgba(56, 189, 248, 0.2);
        }

        .stat-label {
            color: var(--text-sub);
            font-size: 0.95rem;
            font-weight: 400;
        }

        .stat-value {
            font-weight: 600;
            font-size: 1.05rem;
            color: var(--text-main);
        }

        /* Quote box rotation styling */
        .quote-box {
            margin-top: 25px;
            padding-top: 25px;
            border-top: 1px solid rgba(255, 255, 255, 0.08);
            font-style: italic;
            color: var(--text-sub);
            font-size: 0.9rem;
            min-height: 50px;
            display: flex;
            align-items: center;
            justify-content: center;
            transition: opacity 0.5s ease;
        }

        /* Water wave animation graphic SVG */
        .wave-svg {
            position: absolute;
            bottom: 0;
            left: 0;
            width: 100%;
            height: 100px;
            fill: #0ea5e9;
        }
    </style>
</head>
<body>

    <div class="glass-card">
        <h1>Giyu Tomioka</h1>
        <div class="subtitle">Water Breathing Style: Status Panel</div>
        
        <div class="status-badge">
            <span class="pulse-dot"></span>
            <span id="system-status">SYSTEM ACTIVE</span>
        </div>
        
        <div class="stats-grid">
            <div class="stat-card">
                <span class="stat-label">Database Connection:</span>
                <span class="stat-value" id="db-status" style="color: {{ db_status_color }};">{{ db_status }}</span>
            </div>
            <div class="stat-card">
                <span class="stat-label">System Uptime:</span>
                <span class="stat-value" id="system-uptime">{{ uptime }}</span>
            </div>
            <div class="stat-card">
                <span class="stat-label">Style Form:</span>
                <span class="stat-value" style="color: var(--primary);">Eleventh Form: Dead Calm 🌊</span>
            </div>
        </div>
        
        <div class="quote-box" id="quote-container">
            "I am not disliked by people."
        </div>
    </div>

    <!-- Active dynamic polling script updates stats live -->
    <script>
        const quotes = [
            "\\\"I am not disliked by people.\\\"",
            "\\\"Feel the rage. The powerful, pure rage of not being able to forgive...\\\"",
            "\\\"Water Breathing, Eleventh Form: Dead Calm.\\\"",
            "\\\"Don't cry. Don't despair. Now is not the time for that.\\\"",
            "\\\"The weak have no rights or choices. Their only fate is to be relentlessly crushed by the strong!\\\""
        ];

        let quoteIndex = 0;
        setInterval(() => {
            const container = document.getElementById('quote-container');
            container.style.opacity = 0;
            setTimeout(() => {
                quoteIndex = (quoteIndex + 1) % quotes.length;
                container.innerHTML = quotes[quoteIndex];
                container.style.opacity = 1;
            }, 500);
        }, 8000);

        async function updateHealthStats() {
            try {
                const response = await fetch('/health');
                const data = await response.json();
                
                document.getElementById('system-uptime').innerText = data.uptime;
                
                const dbStatusEl = document.getElementById('db-status');
                dbStatusEl.innerText = data.database === 'connected' ? 'Connected' : 'Disconnected';
                dbStatusEl.style.color = data.database === 'connected' ? '#10b981' : '#ef4444';
            } catch (err) {
                console.error("Failed to fetch Giyu-Bot status updates:", err);
            }
        }

        // Poll every 5 seconds
        setInterval(updateHealthStats, 5000);
    </script>
</body>
</html>
"""
