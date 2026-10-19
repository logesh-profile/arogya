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

print("=" * 60)
print("🚀 F5-TTS TANGLISH ZERO-SHOT VOICE CLONING")
print("=" * 60)

device = "cuda" if torch.cuda.is_available() else "cpu"
print(f"[*] Compute Device : {device}")
if device == "cuda":
    print(f"[*] GPU Name       : {torch.cuda.get_device_name(0)}")

chatbot_dir = os.path.dirname(os.path.abspath(__file__))
ref_audio = os.path.join(chatbot_dir, "voice_samples", "female1_ref_clean.wav")
ref_text = (
    "Innaikku naan solla pora indha seven strategies ungaloda communication skills-la implement "
    "pannikitteengana nichayama ungaloda pechu thiran next level pogumrathu ennoda promise."
)

output_dir = os.path.join(chatbot_dir, "voice_samples")
os.makedirs(output_dir, exist_ok=True)
output_wav = os.path.join(output_dir, "female1_tanglish_speech.wav")

# Tanglish speech text (translating Tamil script 'சார்பா' to phonetic 'saarba' so model pronounces it cleanly)
tanglish_text = (
    "Ellarkum eniya evening vanakkam.\n"
    "Nammaloda respected Chief Guest Mr. Rakesh, nammadiye esteemed Principal Mr. Mukesh, dedicated teachers, proud parents, and my dear friends. "
    "KRM Public School saarba, ivlo per present aayiruka unga ellaraiyum rumba warm and heartfelt-ah welcome panren.\n"
    "Namma school academic calendar-oda oru major milestone-ah celebrate panna thaan inraiku evening intha Annual Day function-la onna sendhirukom. "
    "Intha naal, nammadiye students-oda talent, hard work, and namma school-oda vibrant spirit-ah celebrate panra oru azhagana naal.\n"
    "Mr. Rakesh, neenga inraiku nammadiye Chief Guest-ah vanthu intha function-ah grace panna thaan rumba honored-ah feel panrom. "
    "Unga presence-ku rumba thanks. Nammadiye Principal Mr. Mukesh matrum intha mathiri events-ah possible aakura nammadiye teachers-kum enoda special thanks. "
    "Nammadiye dear parents, ungaloda endless support-kum, students-ah cheer panra-thuku vanthathukum rumba thanks.\n"
    "Aduthu ungalukaga spectacular performance lineup kaathutu iruku. "
    "So sit back, relax, and intha memorable evening-ah enjoy pannunga. Thank you, and welcome once again!"
)

print(f"\n[*] Generating Tanglish Speech for:\n{tanglish_text}")

print("\n[*] Initializing F5-TTS on GPU...")
start_init = time.time()
f5tts = F5TTS(model="F5TTS_v1_Base", device=device)
print(f"[✓] Initialized in {time.time() - start_init:.2f}s")

print("\n[*] Synthesizing Tanglish speech with Rashmika's voice & tone...")
start_infer = time.time()
wav, sr, spect = f5tts.infer(
    ref_file=ref_audio,
    ref_text=ref_text,
    gen_text=tanglish_text,
    file_wave=output_wav,
    remove_silence=False,
    speed=1.0,
    nfe_step=32,
    cfg_strength=2.0,
)

elapsed = time.time() - start_infer
print(f"\n[✓] Tanglish speech generation completed in {elapsed:.2f} seconds!")
print(f"\n🎉 FINAL TANGLISH AUDIO CREATED AT:")
print(f"   {output_wav}")
print("=" * 60)
