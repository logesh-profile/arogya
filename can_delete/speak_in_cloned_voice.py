import os
import sys

# Ensure UTF-8 output on Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

import time
import torch
from f5_tts.api import F5TTS

chatbot_dir = os.path.dirname(os.path.abspath(__file__))
ref_audio = os.path.join(chatbot_dir, "voice_samples", "female1_ref_clean.wav")
ref_text = (
    "Innaikku naan solla pora indha seven strategies ungaloda communication skills-la implement "
    "pannikitteengana nichayama ungaloda pechu thiran next level pogumrathu ennoda promise."
)

output_dir = os.path.join(chatbot_dir, "voice_samples")
os.makedirs(output_dir, exist_ok=True)

# Cache model instance
_f5tts = None

def get_model():
    global _f5tts
    if _f5tts is None:
        device = "cuda" if torch.cuda.is_available() else "cpu"
        print(f"[*] Loading F5-TTS on {device}...")
        _f5tts = F5TTS(model="F5TTS_v1_Base", device=device)
        print("[*] F5-TTS Ready!")
    return _f5tts

def speak(text: str, filename: str = "cloned_speech.wav"):
    model = get_model()
    out_path = os.path.join(output_dir, filename)
    print(f"\n[*] Generating cloned speech for: \"{text}\"")
    start = time.time()
    model.infer(
        ref_file=ref_audio,
        ref_text=ref_text,
        gen_text=text,
        file_wave=out_path,
        speed=1.0,
        nfe_step=32,
        cfg_strength=2.0,
    )
    print(f"[✓] Generated in {time.time() - start:.2f}s -> {out_path}")
    return out_path

if __name__ == "__main__":
    if len(sys.argv) > 1:
        sentence = " ".join(sys.argv[1:])
    else:
        sentence = "Hello everyone! Thank you so much for being here today. It really means the world to me, and I love you all!"
    speak(sentence)
