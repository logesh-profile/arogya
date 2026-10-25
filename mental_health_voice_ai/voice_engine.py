import os
import sys
import uuid
import re
import asyncio
from typing import Optional
import soundfile as sf

# Dynamic optional imports for cloud deployment / low-memory environments
try:
    import torch
    HAS_TORCH = True
except ImportError:
    torch = None
    HAS_TORCH = False

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
        try:
            from faster_whisper import WhisperModel
            device = "cuda" if (HAS_TORCH and torch and torch.cuda.is_available()) else "cpu"
            compute_type = "float16" if device == "cuda" else "int8"
            print(f"[*] Initializing faster-whisper on {device} ({compute_type})...")
            whisper_model = WhisperModel("base", device=device, compute_type=compute_type)
        except Exception as e:
            print(f"[!] Whisper model initialization notice: {e}")
            whisper_model = None
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
    Loads F5TTS instance on GPU for authentic reference voice cloning if available.
    """
    global f5tts_instance
    if f5tts_instance is None:
        try:
            from f5_tts.api import F5TTS
            device = "cuda" if (HAS_TORCH and torch and torch.cuda.is_available()) else "cpu"
            print(f"[*] Initializing F5-TTS Neural Voice on {device}...")
            f5tts_instance = F5TTS(model="F5TTS_v1_Base", device=device)
            print("[✓] F5-TTS initialized and ready.")
        except Exception as e:
            print(f"[!] F5-TTS unavailable on this server ({e}). Using Fast Neural voice.")
            f5tts_instance = None
    return f5tts_instance

def synthesize_cloned_speech(text: str, wellness_score: int = 75, dominant_state: str = "Calm") -> str:
    """
    Synthesizes speech using the user's exact reference cloned voice (F5-TTS).
    Matches generate_custom_speech.py parameters exactly for identical tone, accent & pitch.
    Optimized nfe_step=16 for high-fidelity voice cloning on RTX 3050.
    Dynamically modulates speed: slower and more grounded during distress/exhaustion.
    """
    f5tts = get_f5tts()
    out_filename = f"reply_cloned_{uuid.uuid4().hex[:8]}.wav"
    out_path = os.path.join(CACHE_DIR, out_filename)

    # Emotion-adaptive cloned speed
    if wellness_score < 55 or dominant_state in ["Overwhelmed", "Exhausted", "Crisis Alert"]:
        adaptive_speed = 0.88  # Soothing, slower, grounded
    elif wellness_score < 68 or dominant_state in ["Lonely", "Reflective"]:
        adaptive_speed = 0.94  # Gentle, attentive cadence
    else:
        adaptive_speed = 1.0   # Standard conversational speed

    f5tts.infer(
        ref_file=REF_AUDIO,
        ref_text=REF_TEXT,
        gen_text=text,
        file_wave=out_path,
        remove_silence=False,
        speed=adaptive_speed,
        nfe_step=16,
        cfg_strength=2.0
    )
    return f"/audio/{out_filename}"

async def synthesize_fast_speech(
    text: str,
    wellness_score: int = 75,
    dominant_state: str = "Calm",
    voice: Optional[str] = None,
    language_mode: str = "tanglish"
) -> str:
    """
    Sub-second neural speech synthesis via edge-tts (~0.4s).
    Intelligently routes:
    - Tamil / Tanglish / Code-Switched -> ta-IN-PallaviNeural (Native high-fidelity Tamil voice with natural cadence)
    - Indian English -> en-IN-NeerjaNeural
    Dynamically modulates prosodic rate and pitch based on user emotional state:
    - Distress / low wellness: -10% rate, -3Hz pitch (vagus grounding cadence)
    - Loneliness / mild strain: -5% rate, -1Hz pitch (warm intimate presence)
    - Balanced / calm: +3% rate, +0Hz pitch (fluid conversational rhythm)
    """
    import edge_tts
    out_filename = f"reply_fast_{uuid.uuid4().hex[:8]}.mp3"
    out_path = os.path.join(CACHE_DIR, out_filename)

    # Dynamic Prosodic Modulation
    if wellness_score < 55 or dominant_state in ["Overwhelmed", "Exhausted", "Crisis Alert"]:
        rate = "-10%"
        pitch = "-3Hz"
    elif wellness_score < 68 or dominant_state in ["Lonely", "Reflective"]:
        rate = "-5%"
        pitch = "-1Hz"
    else:
        rate = "+3%"
        pitch = "+0Hz"

    # Select Optimal Voice: ta-IN-PallaviNeural for Tamil/Tanglish, en-IN-NeerjaNeural for English
    if not voice:
        has_tamil_script = bool(re.search(r'[\u0B80-\u0BFF]', text))
        if has_tamil_script or language_mode in ["tanglish", "tamil", "code_switched"]:
            target_voice = "ta-IN-PallaviNeural"
        else:
            target_voice = "en-IN-NeerjaNeural"
    else:
        target_voice = voice

    communicate = edge_tts.Communicate(text, voice=target_voice, rate=rate, pitch=pitch)
    await communicate.save(out_path)
    return f"/audio/{out_filename}"

async def synthesize_speech(
    text: str,
    mode: str = "fast",
    wellness_score: int = 75,
    dominant_state: str = "Calm",
    language_mode: str = "tanglish",
    spoken_text: Optional[str] = None,
    voice: Optional[str] = None
) -> str:
    """
    Unified speech synthesis router:
    - 'fast': Native sub-second Tamil/English neural voice via edge-tts (0.35s - 0.45s)
    - 'cloned': Authentic reference cloned voice on RTX 3050 GPU via F5-TTS
    Uses 'spoken_text' (phonetically prepared with breath pauses & script representation)
    while the chat UI displays the clean conversational Tanglish 'text'.
    """
    active_text = spoken_text if (spoken_text and len(spoken_text.strip()) > 0) else text

    if mode == "cloned":
        f5tts = get_f5tts()
        if f5tts is not None and os.path.exists(REF_AUDIO):
            try:
                loop = asyncio.get_event_loop()
                # For F5-TTS (diffusion zero-shot model), use clean Tanglish Latin text
                cloned_text = text if not re.search(r'[\u0B80-\u0BFF]', text) else active_text
                return await loop.run_in_executor(None, synthesize_cloned_speech, cloned_text, wellness_score, dominant_state)
            except Exception as e:
                print(f"[!] Cloned speech synthesis notice: {e}, routing to Fast Neural voice")

    return await synthesize_fast_speech(
        active_text,
        wellness_score=wellness_score,
        dominant_state=dominant_state,
        voice=voice,
        language_mode=language_mode
    )

