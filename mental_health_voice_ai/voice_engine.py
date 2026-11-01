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
        # Check maximum amplitude and RMS volume (calibrated for Bluetooth headsets and laptop mic arrays)
        max_amp = float(np.max(np.abs(data)))
        rms = float(np.sqrt(np.mean(data**2)))
        if max_amp < 0.0008 or rms < 0.0002:
            print(f"[!] Audio is silent (max_amp={max_amp:.4f}, rms={rms:.4f}). Skipping Whisper.")
            return ""
    except Exception as e:
        print(f"[!] Audio energy check warning: {e}")

    model = get_whisper_model()
    # vad_filter=True discards non-speech and silence chunks
    # initial_prompt guides Whisper for natural Indian English conversation and emotional reflections
    segments, _ = model.transcribe(
        audio_path,
        beam_size=2,
        language="en",
        initial_prompt="Natural Indian English conversation, emotional reflection, mental health, thoughts, and feelings.",
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
    language_mode: str = "indian_english"
) -> str:
    """
    Sub-second neural speech synthesis via edge-tts (~0.35s).
    High-fidelity Indian English neural voices (Neerja Expressive, Prabhat, Jenny, Guy).
    Dynamically modulates prosodic rate and pitch based on user emotional state:
    - Distress / low wellness: -6% rate, -2Hz pitch (soothing grounding cadence)
    - Loneliness / mild strain: -3% rate, -1Hz pitch (warm intimate presence)
    - Balanced / calm: +0% rate, +0Hz pitch (natural conversational human rhythm)
    """
    import edge_tts
    out_filename = f"reply_fast_{uuid.uuid4().hex[:8]}.mp3"
    out_path = os.path.join(CACHE_DIR, out_filename)

    # Dynamic Prosodic Modulation for human warmth
    if wellness_score < 55 or dominant_state in ["Overwhelmed", "Exhausted", "Crisis Alert"]:
        rate = "-6%"
        pitch = "-2Hz"
    elif wellness_score < 68 or dominant_state in ["Lonely", "Reflective"]:
        rate = "-3%"
        pitch = "-1Hz"
    else:
        rate = "+0%"
        pitch = "+0Hz"

# Curated ChatGPT-Style Natural Voices (Indian English primary, distinct expressive personas)
AVAILABLE_VOICES = [
    {
        "id": "en-IN-NeerjaExpressiveNeural",
        "name": "Neerja",
        "label": "Neerja (Expressive)",
        "gender": "Female",
        "accent": "Indian English",
        "description": "Warm, empathetic and expressive tone",
        "sample_text": "Hello, I am your Arogya companion. I'm here to listen and reflect with you.",
        "default": True
    },
    {
        "id": "en-IN-PrabhatNeural",
        "name": "Prabhat",
        "label": "Prabhat (Grounded)",
        "gender": "Male",
        "accent": "Indian English",
        "description": "Calm, deep and grounding reassurance",
        "sample_text": "Take a gentle breath. I am right here with you whenever you are ready.",
        "default": False
    },
    {
        "id": "en-IN-NeerjaNeural",
        "name": "Neerja Soft",
        "label": "Neerja (Gentle)",
        "gender": "Female",
        "accent": "Indian English",
        "description": "Soft-spoken, peaceful and mindful presence",
        "sample_text": "You can speak freely here without any judgment. How are you feeling today?",
        "default": False
    },
    {
        "id": "en-US-JennyNeural",
        "name": "Jenny",
        "label": "Jenny (Conversational)",
        "gender": "Female",
        "accent": "Conversational English",
        "description": "Clear, friendly and upbeat companion",
        "sample_text": "Hi there! I am ready whenever you want to share what is on your mind.",
        "default": False
    },
    {
        "id": "en-US-GuyNeural",
        "name": "Guy",
        "label": "Guy (Thoughtful)",
        "gender": "Male",
        "accent": "Calm English",
        "description": "Thoughtful, gentle and steady presence",
        "sample_text": "I am here to support you. Let's take it one step at a time.",
        "default": False
    }
]

DEFAULT_VOICE = "en-IN-NeerjaExpressiveNeural"
VALID_VOICE_IDS = {v["id"] for v in AVAILABLE_VOICES}

async def generate_voice_preview(voice_id: str) -> Optional[str]:
    """Generates and caches a preview audio snippet for a given voice persona."""
    import edge_tts
    if voice_id not in VALID_VOICE_IDS:
        voice_id = DEFAULT_VOICE

    voice_meta = next((v for v in AVAILABLE_VOICES if v["id"] == voice_id), AVAILABLE_VOICES[0])
    preview_filename = f"preview_{voice_id}.mp3"
    preview_path = os.path.join(CACHE_DIR, preview_filename)

    if os.path.exists(preview_path) and os.path.getsize(preview_path) > 1000:
        return f"/audio/{preview_filename}"

    sample = voice_meta.get("sample_text", "Hello, I am your Arogya companion. I'm here to listen and reflect with you.")
    try:
        communicate = edge_tts.Communicate(sample, voice=voice_id, rate="+0%", pitch="+0Hz")
        await asyncio.wait_for(communicate.save(preview_path), timeout=8.0)
        return f"/audio/{preview_filename}"
    except Exception as e:
        print(f"[!] Voice preview generation notice: {e}")
        return None

async def synthesize_fast_speech(
    text: str,
    wellness_score: int = 75,
    dominant_state: str = "Calm",
    voice: Optional[str] = None,
    language_mode: str = "indian_english"
) -> str:
    """
    Sub-second neural speech synthesis via edge-tts (~0.35s).
    High-fidelity Indian English neural voices (Neerja Expressive, Prabhat, Jenny, Guy).
    Dynamically modulates prosodic rate and pitch based on user emotional state:
    - Distress / low wellness: -6% rate, -2Hz pitch (soothing grounding cadence)
    - Loneliness / mild strain: -3% rate, -1Hz pitch (warm intimate presence)
    - Balanced / calm: +0% rate, +0Hz pitch (natural conversational human rhythm)
    """
    import edge_tts
    out_filename = f"reply_fast_{uuid.uuid4().hex[:8]}.mp3"
    out_path = os.path.join(CACHE_DIR, out_filename)

    # Dynamic Prosodic Modulation for human warmth
    if wellness_score < 55 or dominant_state in ["Overwhelmed", "Exhausted", "Crisis Alert"]:
        rate = "-6%"
        pitch = "-2Hz"
    elif wellness_score < 68 or dominant_state in ["Lonely", "Reflective"]:
        rate = "-3%"
        pitch = "-1Hz"
    else:
        rate = "+0%"
        pitch = "+0Hz"

    target_voice = voice if (voice and voice in VALID_VOICE_IDS) else DEFAULT_VOICE

    try:
        communicate = edge_tts.Communicate(text, voice=target_voice, rate=rate, pitch=pitch)
        await asyncio.wait_for(communicate.save(out_path), timeout=8.0)
        return f"/audio/{out_filename}"
    except Exception as e:
        print(f"[!] Fast speech synthesis notice for {target_voice}: {e}")
        # Fallback to standard Neerja if expressive voice encounters delay
        if target_voice == "en-IN-NeerjaExpressiveNeural":
            try:
                communicate = edge_tts.Communicate(text, voice="en-IN-NeerjaNeural", rate=rate, pitch=pitch)
                await asyncio.wait_for(communicate.save(out_path), timeout=6.0)
                return f"/audio/{out_filename}"
            except Exception:
                pass
        return None

async def synthesize_speech(
    text: str,
    mode: str = "fast",
    wellness_score: int = 75,
    dominant_state: str = "Calm",
    language_mode: str = "indian_english",
    spoken_text: Optional[str] = None,
    voice: Optional[str] = None
) -> str:
    """
    Unified speech synthesis router:
    Synthesizes natural, human-like Indian English voice via Microsoft neural TTS.
    """
    active_text = spoken_text if (spoken_text and len(spoken_text.strip()) > 0) else text

    return await synthesize_fast_speech(
        active_text,
        wellness_score=wellness_score,
        dominant_state=dominant_state,
        voice=voice,
        language_mode="indian_english"
    )

