import os

_TEMPLATE_PATH = os.path.join(os.path.dirname(__file__), "templates", "dashboard.html")

def _load_html_page() -> str:
    try:
        with open(_TEMPLATE_PATH, "r", encoding="utf-8") as f:
            return f.read()
    except Exception:
        return "<html><body><h1>Giyu-Bot Server Active</h1></body></html>"

HTML_PAGE = _load_html_page()
