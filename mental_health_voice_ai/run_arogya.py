import os
import sys
import webbrowser
import time
import uvicorn

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

AI_DIR = os.path.dirname(os.path.abspath(__file__))
if AI_DIR not in sys.path:
    sys.path.insert(0, AI_DIR)

from database import init_db

def main():
    print("=" * 65)
    print("🌿 AROGYA • AI MENTAL HEALTH & VOICE COMPANION")
    print("=" * 65)
    print("[*] Initializing Database & Long-Term Memory...")
    init_db()

    url = "http://localhost:8000"
    print(f"[*] Starting Server at {url}")
    print("[*] Opening your browser automatically...")

    def open_browser():
        time.sleep(1.5)
        webbrowser.open(url)

    import threading
    threading.Thread(target=open_browser, daemon=True).start()

    print("[✓] Ready! Arogya will speak to you upon page connection.")
    print("=" * 65)

    uvicorn.run("app:app", host="127.0.0.1", port=8000, reload=True, app_dir=AI_DIR)

if __name__ == "__main__":
    main()
