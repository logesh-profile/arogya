import json
import time
import socket
import threading
import sys
from http.server import HTTPServer, BaseHTTPRequestHandler
import urllib.request

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
    except Exception:
        pass

# ---------------------------------------------------------------------------
# 12 FACS EMOTIONS SUPPORTED BY ESP32 CLAUDE FACE
# ---------------------------------------------------------------------------
VALID_EMOTIONS = {
    "calm", "happy", "excited", "caring", "concerned", "sad",
    "surprised", "confused", "thinking", "sleepy", "proud", "love"
}

EMOTION_MAP = {
    # Positive / Gratitude
    "happy": "happy",
    "joy": "happy",
    "grateful": "happy",
    "excited": "excited",
    "thrilled": "excited",
    "proud": "proud",
    "love": "love",
    "caring": "caring",
    # Processing / Neutral
    "thinking": "thinking",
    "listening": "thinking",
    "neutral": "calm",
    "calm": "calm",
    "reflective": "calm",
    # Surprised
    "surprised": "surprised",
    "shocked": "surprised",
    # Sad / Distress
    "sad": "sad",
    "depressed": "sad",
    "apology": "concerned",
    "concerned": "concerned",
    "anxious": "concerned",
    "confused": "confused",
    "sleepy": "sleepy",
    "tired": "sleepy"
}

state = {
    "emotion": "calm",
    "activity": "idle",
    "keyword": "CALM",
    "last_update": time.time()
}
lock = threading.Lock()
MIN_HOLD = 0.8  # 800ms anti-overlap buffer

def normalize_emotion(emotion: str) -> str:
    raw = str(emotion).strip().lower()
    return EMOTION_MAP.get(raw, "calm" if raw not in VALID_EMOTIONS else raw)

def update_face(emotion: str, activity: str = "idle"):
    global state
    now = time.time()
    clean_emotion = normalize_emotion(emotion)
    clean_activity = str(activity).strip().lower()
    
    with lock:
        # Anti-flooding / minimum dwell time (prevents OLED frame buffer corruption)
        if clean_emotion != state["emotion"] and (now - state["last_update"]) < MIN_HOLD:
            return False
        state["emotion"] = clean_emotion
        state["activity"] = clean_activity
        state["keyword"] = clean_emotion.upper()
        state["last_update"] = now
        print(f"[BRIDGE] >>> State: {state['emotion']} | Activity: {state['activity']}", flush=True)
        return True

class ExpressionHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        # Suppress noisy HTTP access logs to keep terminal output clean
        pass

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        if self.path in ["/api/expression", "/expression"]:
            with lock:
                payload = json.dumps(state).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
        elif self.path == "/":
            with lock:
                curr_state = dict(state)
            info = {
                "status": "online",
                "service": "ESP32 Robot Face Wi-Fi Bridge",
                "current_state": curr_state,
                "endpoints": {
                    "get_expression": "/api/expression",
                    "post_expression": "/api/expression"
                }
            }
            payload = json.dumps(info, indent=2).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        if self.path in ["/api/expression", "/expression", "/api/face", "/update"]:
            try:
                length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(length) if length > 0 else b"{}"
                data = json.loads(body.decode("utf-8")) if body else {}
                emo = data.get("emotion") or data.get("face") or state["emotion"]
                act = data.get("activity") or state["activity"]
                updated = update_face(emo, act)
                res = json.dumps({"status": "ok", "updated": updated, "state": state}).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Content-Length", str(len(res)))
                self.end_headers()
                self.wfile.write(res)
            except Exception as e:
                self.send_response(400)
                self.end_headers()
        else:
            self.send_response(404)
            self.end_headers()

def get_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"

def get_all_ips():
    ips = []
    try:
        hostname = socket.gethostname()
        for ip in socket.gethostbyname_ex(hostname)[2]:
            if not ip.startswith("127.") and not ip.startswith("169.254."):
                ips.append(ip)
    except Exception:
        pass
    primary = get_ip()
    if primary not in ips and not primary.startswith("127.") and not primary.startswith("169.254."):
        ips.insert(0, primary)
    return ips if ips else [primary]

if __name__ == "__main__":
    ip = get_ip()
    all_ips = get_all_ips()
    server = HTTPServer(("0.0.0.0", 5000), ExpressionHandler)
    print("=" * 60, flush=True)
    print(f">> BRIDGE ONLINE: http://{ip}:5000/api/expression", flush=True)
    print(f">> PLEASE SEND THIS IP TO YOUR FRIEND: {ip}", flush=True)
    if len(all_ips) > 1:
        print(f">> ALTERNATIVE NETWORK IPs DETECTED: {', '.join(all_ips)}", flush=True)
    print("=" * 60, flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[!] Bridge stopped.")
