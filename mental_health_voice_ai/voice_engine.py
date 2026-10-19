import os
import sys
import uuid
import asyncio
import torch
import soundfile as sf
from faster_whisper import WhisperModel
from f5_tts.api import F5TTS

# Ensure UTF-8 on Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Ensure paths
AI_DIR = os.path.dirname(os.path.abspath(__file__))
CHATBOT_DIR = os.path.dirname(AI_DIR)
CACHE_DIR = os.path.join(AI_DIR, "audio_cache")
os.makedirs(CACHE_DIR, exist_ok=True)

REF_AUDIO = os.path.join(CHATBOT_DIR, "voice_samples", "female1_ref_clean.wav")
REF_TEXT = (
    "Innaikku naan solla pora indha seven strategies ungaloda communication skills-la implement "
    "pannikitteengana nichayama ungaloda pechu thiran next level pogumrathu ennoda promise."
)

# Global Model instances
whisper_model = None
f5tts_instance = None

def get_whisper_model():
    global whisper_model
    if whisper_model is None:
        device = "cuda" if torch.cuda.is_available() else "cpu"
        compute_type = "float16" if device == "cuda" else "int8"
        try:
            print(f"[*] Initializing faster-whisper on {device} ({compute_type})...")
            whisper_model = WhisperModel("base", device=device, compute_type=compute_type)
        except Exception as e:
            print(f"[!] Falling back to CPU whisper: {e}")
            whisper_model = WhisperModel("base", device="cpu", compute_type="int8")
    return whisper_model

def transcribe_audio(audio_path: str) -> str:
    """
    Transcribes audio file to text using faster-whisper with VAD (Voice Activity Detection)
    to prevent silence hallucinations like 'You You You' or 'Thank you'.
    """
    import numpy as np
    try:
        data, sr = sf.read(audio_path)
        if len(data) == 0:
            return ""
        # Check maximum amplitude and RMS volume
        max_amp = float(np.max(np.abs(data)))
        rms = float(np.sqrt(np.mean(data**2)))
        if max_amp < 0.008 or rms < 0.002:
            print(f"[!] Audio is silent (max_amp={max_amp:.4f}, rms={rms:.4f}). Skipping Whisper.")
            return ""
    except Exception as e:
        print(f"[!] Audio energy check warning: {e}")

    model = get_whisper_model()
    # vad_filter=True discards non-speech and silence chunks
    # initial_prompt guides Whisper for Indian English & conversational Tanglish loanwords
    segments, _ = model.transcribe(
        audio_path,
        beam_size=5,
        language="en",
        initial_prompt="Indian English conversation, Tanglish, inaiku ennode day epdi irundhuchi, romba stress, tension, seri, yaar, enna aachu, eppadi irukkeenga.",
        vad_filter=True,
        condition_on_previous_text=False
    )
    transcript = " ".join([segment.text for segment in segments]).strip()

    # Filter out common Whisper silence hallucinations
    clean_lower = transcript.lower().strip(" .,!?-")
    hallucinations = ["you", "thank you", "you you", "you you you", "subtitles by", "watching", "amara.org", "subscribe"]
    # Check if text is just repeating 'you'
    words = clean_lower.split()
    if all(w == "you" for w in words) or clean_lower in hallucinations:
        print(f"[!] Detected Whisper silence hallucination '{transcript}'. Filtering out.")
        return ""

    return transcript


def get_f5tts():
    """
    Loads F5TTS instance on RTX 3050 GPU for authentic reference voice cloning.
    """
    global f5tts_instance
    if f5tts_instance is None:
        device = "cuda" if torch.cuda.is_available() else "cpu"
        print(f"[*] Initializing F5-TTS Neural Voice on {device} for exact cloned voice...")
        f5tts_instance = F5TTS(model="F5TTS_v1_Base", device=device)
        print("[✓] F5-TTS initialized and ready.")
    return f5tts_instance

def synthesize_cloned_speech(text: str) -> str:
    """
    Synthesizes speech using the user's exact reference cloned voice (F5-TTS).
    Matches generate_custom_speech.py parameters exactly for identical tone, accent & pitch.
    Optimized nfe_step=8 for lightning-fast voice synthesis (~1.9s on RTX 3050).
    """
    f5tts = get_f5tts()
    out_filename = f"reply_cloned_{uuid.uuid4().hex[:8]}.wav"
    out_path = os.path.join(CACHE_DIR, out_filename)

    f5tts.infer(
        ref_file=REF_AUDIO,
        ref_text=REF_TEXT,
        gen_text=text,
        file_wave=out_path,
        remove_silence=False,
        speed=1.0,
        nfe_step=16,
        cfg_strength=2.0
    )
    return f"/audio/{out_filename}"

async def synthesize_fast_speech(text: str) -> str:
    """
    Ultra-fast neural speech synthesis via edge-tts (sub-second latency ~0.4s).
    Uses Indian English neural voice (en-IN-NeerjaNeural).
    """
    import edge_tts
    out_filename = f"reply_fast_{uuid.uuid4().hex[:8]}.mp3"
    out_path = os.path.join(CACHE_DIR, out_filename)
    communicate = edge_tts.Communicate(text, voice="en-IN-NeerjaNeural", rate="+6%")
    await communicate.save(out_path)
    return f"/audio/{out_filename}"

async def synthesize_speech(text: str, mode: str = "cloned") -> str:
    """
    Synthesizes speech based on mode:
    - 'fast': Instant sub-second Indian neural voice (~0.4s)
    - 'cloned': Authentic reference cloned voice on RTX 3050 GPU (~1.9s)
    """
    if mode == "fast":
        try:
            return await synthesize_fast_speech(text)
        except Exception as e:
            print(f"[!] Fast speech failed: {e}, falling back to cloned")
    
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, synthesize_cloned_speech, text)

