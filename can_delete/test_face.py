import sys
import json
import urllib.request
import time

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

URL = "http://127.0.0.1:5000/api/expression"

VALID_EMOTIONS = [
    "calm", "happy", "excited", "caring", "concerned", "sad",
    "surprised", "confused", "thinking", "sleepy", "proud", "love"
]

def send_state(emotion: str, activity: str = "idle"):
    try:
        payload = json.dumps({"emotion": emotion, "activity": activity}).encode("utf-8")
        req = urllib.request.Request(
            URL,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=1.0) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            print(f"[OK] Sent -> Emotion: {emotion.upper()} | Activity: {activity.upper()} (Updated: {data.get('updated')})")
    except Exception as e:
        print(f"[ERROR] Could not connect to bridge at {URL}: {e}")

def main():
    print("=" * 60)
    print("ESP32 ROBOT FACE LIVE TESTER")
    print("=" * 60)
    print("Available Emotions:")
    print("  " + ", ".join(VALID_EMOTIONS))
    print("\nCommands:")
    print("  Type any emotion (e.g. 'happy', 'sad', 'thinking', 'excited')")
    print("  Type 'spk 1' or 'speaking' to test mouth movement")
    print("  Type 'spk 0' or 'idle' to stop mouth movement")
    print("  Type 'exit' to quit\n")

    if len(sys.argv) > 1:
        arg = sys.argv[1].lower()
        if arg in ["spk1", "speaking", "speak"]:
            send_state("happy", "speaking")
        elif arg in ["spk0", "idle", "stop"]:
            send_state("calm", "idle")
        elif arg in VALID_EMOTIONS:
            send_state(arg, "idle")
        else:
            send_state(arg, "idle")
        return

    while True:
        try:
            cmd = input("Enter emotion or command > ").strip().lower()
            if not cmd:
                continue
            if cmd in ["exit", "quit", "q"]:
                break
            if cmd in ["spk 1", "spk1", "speaking", "speak"]:
                send_state("happy", "speaking")
            elif cmd in ["spk 0", "spk0", "idle", "stop"]:
                send_state("calm", "idle")
            elif cmd in VALID_EMOTIONS:
                send_state(cmd, "idle")
            else:
                print(f"[?] Unknown emotion '{cmd}'. Try one of: {', '.join(VALID_EMOTIONS)}")
        except (KeyboardInterrupt, EOFError):
            print("\nExiting.")
            break

if __name__ == "__main__":
    main()
