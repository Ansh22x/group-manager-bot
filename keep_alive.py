from http.server import BaseHTTPRequestHandler, HTTPServer
from threading import Thread
import os

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/plain')
        self.end_headers()
        self.wfile.write(b"Bot is alive!")
    
    # Silence the logs to keep your Render terminal clean
    def log_message(self, format, *args):
        pass

def run():
    # Render defaults to port 10000
    port = int(os.environ.get('PORT', 10000))
    server = HTTPServer(('0.0.0.0', port), Handler)
    server.serve_forever()

def keep_alive():
    t = Thread(target=run)
    t.daemon = True  # Allows thread to cleanly exit if needed
    t.start()
