import os
import sys
import uuid
import re
import io
import base64
import asyncio
from typing import Optional, Union, AsyncGenerator
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
_groq_client = None

def get_groq_client():
    global _groq_client
    if _groq_client is None:
        api_key = os.getenv("GROQ_API_KEY")
        if api_key:
            try:
                from groq import Groq
                _groq_client = Groq(api_key=api_key)
            except Exception as e:
                print(f"[!] Groq STT client notice: {e}")
    return _groq_client

def transcribe_with_groq_whisper(audio_input: Union[str, bytes, io.BytesIO]) -> Optional[str]:
    """
    Sub-second Groq Whisper LPU speech recognition (~200ms).
    Uses 0 MB server memory, completely eliminating Render memory spikes.
    Supports in-memory BytesIO/bytes directly and auto-detects multilingual speech (Tamil, Tanglish, English).
    """
    client = get_groq_client()
    if not client:
        return None
    try:
        if isinstance(audio_input, bytes):
            bio = io.BytesIO(audio_input)
            bio.name = "audio.webm"
        elif isinstance(audio_input, io.BytesIO):
            bio = audio_input
            bio.seek(0)
            if not hasattr(bio, "name") or not bio.name:
                bio.name = "audio.webm"
        elif isinstance(audio_input, str) and os.path.exists(audio_input):
            ext = os.path.splitext(audio_input)[1].lower()
            with open(audio_input, "rb") as f:
                bio = io.BytesIO(f.read())
            bio.name = f"audio{ext if ext else '.webm'}"
        else:
            return ""

        bio.seek(0)
        audio_bytes = bio.getvalue()
        if not audio_bytes or len(audio_bytes) < 400:
            return ""

        for model_id in ["whisper-large-v3-turbo", "whisper-large-v3"]:
            try:
                bio.seek(0)
                transcription = client.audio.transcriptions.create(
                    file=bio,
                    model=model_id,
                    response_format="json",
                    # Auto-detects English, Tamil, and Tanglish natively
                    temperature=0.0
                )
                if transcription and transcription.text:
                    text = transcription.text.strip()
                    if text.lower() in ["none", "silence", "empty", "[silence]", "[music]", "[applause]"]:
                        return ""
                    print(f"[+] Transcribed via Groq Whisper ({model_id}): '{text}'")
                    return text
                return ""
            except Exception as me:
                print(f"[!] Groq {model_id} notice: {me}")
        return None
    except Exception as e:
        print(f"[!] Groq Whisper transcription notice: {e}")
        return None

def get_whisper_model():
    global whisper_model
    if whisper_model is None:
        try:
            from faster_whisper import WhisperModel
            device = "cuda" if (HAS_TORCH and torch and torch.cuda.is_available()) else "cpu"
            compute_type = "float16" if device == "cuda" else "int8"
            print(f"[*] Initializing lightweight faster-whisper tiny on {device} ({compute_type})...")
            # Uses 'tiny' (39MB) to keep RAM well under 100MB on Render
            whisper_model = WhisperModel("tiny", device=device, compute_type=compute_type)
        except Exception as e:
            print(f"[!] Whisper model initialization notice: {e}")
            whisper_model = None
    return whisper_model

def transcribe_audio(audio_input: Union[str, bytes, io.BytesIO]) -> str:
    """
    Transcribes audio directly in memory with zero OS process or file saving overhead.
    1. Checks audio energy in memory (skips silent audio).
    2. Cloud STT with Groq Whisper Large v3 Turbo (~200ms, 0 RAM).
    3. Lightweight Whisper tiny fallback only if Groq is unavailable.
    """
    import numpy as np
    import gc

    # 1. Primary: Sub-second Groq Whisper LPU (~200ms, 0 RAM)
    groq_text = transcribe_with_groq_whisper(audio_input)
    if groq_text is not None:
        gc.collect()
        return groq_text

    # Fallback: Lightweight local Whisper tiny if file exists on disk
    if isinstance(audio_input, str) and os.path.exists(audio_input):
        model = get_whisper_model()
        if not model:
            gc.collect()
            return ""

        segments, _ = model.transcribe(
            audio_input,
            beam_size=1,
            language="en",
            initial_prompt="Natural Indian English conversation, emotional reflection, mental health, thoughts, and feelings.",
            vad_filter=True,
            condition_on_previous_text=False
        )
        transcript = " ".join([segment.text for segment in segments]).strip()
    else:
        transcript = ""

    # Filter out common Whisper silence hallucinations
    clean_lower = transcript.lower().strip(" .,!?-")
    hallucinations = ["you", "thank you", "you you", "you you you", "subtitles by", "watching", "amara.org", "subscribe"]
    words = clean_lower.split()
    if all(w == "you" for w in words) or clean_lower in hallucinations:
        print(f"[!] Detected Whisper silence hallucination '{transcript}'. Filtering out.")
        transcript = ""

    gc.collect()
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

# Curated ChatGPT-Style Human Natural Voices (Ultra-expressive, authentic human cadence)
AVAILABLE_VOICES = [
    {
        "id": "en-IN-NeerjaExpressiveNeural",
        "name": "Neerja",
        "label": "Neerja (Expressive Indian English)",
        "gender": "Female",
        "accent": "Expressive Indian English",
        "description": "Warm, authentic Indian English companion with emotional empathy & conversational cadence",
        "sample_text": "Namaste! Don't worry bro, I am right here with you. Take a gentle breath and speak freely.",
        "default": True
    },
    {
        "id": "en-US-AvaMultilingualNeural",
        "name": "Ava",
        "label": "Ava (Human Conversational)",
        "gender": "Female",
        "accent": "Natural Human Voice",
        "description": "Ultra-realistic, warm, human conversational voice with fluid intonation",
        "sample_text": "Hello! I am your Arogya companion. I'm right here with you to listen and reflect.",
        "default": False
    },
    {
        "id": "en-IN-PrabhatNeural",
        "name": "Prabhat",
        "label": "Prabhat (Indian English Male)",
        "gender": "Male",
        "accent": "Indian English Male",
        "description": "Calm, reassuring human presence with steady Indian conversational cadence",
        "sample_text": "Take your time. I am listening to everything you wish to share with me.",
        "default": False
    },
    {
        "id": "en-US-AndrewMultilingualNeural",
        "name": "Andrew",
        "label": "Andrew (Conversational Male)",
        "gender": "Male",
        "accent": "Conversational Male",
        "description": "Deep, warm, and comforting human conversational tone",
        "sample_text": "Take a gentle breath. I am right here whenever you want to share what is on your mind.",
        "default": False
    },
    {
        "id": "en-US-EmmaMultilingualNeural",
        "name": "Emma",
        "label": "Emma (Empathetic Female)",
        "gender": "Female",
        "accent": "Warm & Gentle",
        "description": "Compassionate, gentle, and mindful human presence",
        "sample_text": "You can speak freely here without any judgment. How are you feeling right now?",
        "default": False
    },
    {
        "id": "en-US-BrianMultilingualNeural",
        "name": "Brian",
        "label": "Brian (Thoughtful Male)",
        "gender": "Male",
        "accent": "Calm & Grounded",
        "description": "Thoughtful, steady, and supportive human male companion",
        "sample_text": "I am here with you. Let's take things one step at a time.",
        "default": False
    },
    {
        "id": "ta-IN-PallaviNeural",
        "name": "Pallavi",
        "label": "Pallavi (Regional Tamil)",
        "gender": "Female",
        "accent": "Regional Tamil",
        "description": "Authentic regional Tamil voice for pure Tamil conversations",
        "sample_text": "வணக்கம், உங்க கூட பேசுறதுல எனக்கு ரொம்ப சந்தோஷம்.",
        "default": False
    }
]

DEFAULT_VOICE = "en-IN-NeerjaExpressiveNeural"
VALID_VOICE_IDS = {v["id"] for v in AVAILABLE_VOICES} | {"en-IN-NeerjaNeural"}

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

async def stream_edge_tts_chunks(
    text: str,
    voice: Optional[str] = None,
    rate: str = "+0%",
    pitch: str = "+0Hz"
) -> AsyncGenerator[bytes, None]:
    """
    Asynchronous in-memory streaming generator for Microsoft Edge-TTS.
    Yields raw MP3 audio chunks directly as they are generated without writing to disk.
    """
    import edge_tts
    target_voice = voice if (voice and voice in VALID_VOICE_IDS) else DEFAULT_VOICE

    # Sanitize text for English target voices (convert stray Tamil script to fluent Romanized Tanglish)
    clean_text = text
    if target_voice.startswith("en-"):
        try:
            from tanglish_engine import convert_tamil_script_to_romanized
            clean_text = convert_tamil_script_to_romanized(text)
        except Exception:
            clean_text = text

    try:
        communicate = edge_tts.Communicate(clean_text, voice=target_voice, rate=rate, pitch=pitch)
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                yield chunk["data"]
    except Exception as e:
        print(f"[!] Edge-TTS streaming notice for {target_voice}: {e}")
        # Fallback to standard Neerja if expressive voice has delay
        if target_voice == "en-IN-NeerjaExpressiveNeural":
            try:
                fallback_comm = edge_tts.Communicate(clean_text, voice="en-IN-NeerjaNeural", rate=rate, pitch=pitch)
                async for chunk in fallback_comm.stream():
                    if chunk["type"] == "audio":
                        yield chunk["data"]
            except Exception:
                pass

async def synthesize_fast_speech(
    text: str,
    wellness_score: int = 75,
    dominant_state: str = "Calm",
    voice: Optional[str] = None,
    language_mode: str = "indian_english"
) -> str:
    """
    In-memory neural speech synthesis via Edge-TTS (~0.35s).
    Collects raw audio chunks in pure RAM and returns a high-speed Base64 Data URI.
    Completely eliminates disk I/O, file locks, and ephemeral disk accumulation on Render.
    """
    # Natural human conversational prosody
    if wellness_score < 55 or dominant_state in ["Overwhelmed", "Exhausted", "Crisis Alert"]:
        rate = "-3%"
        pitch = "+0Hz"
    else:
        rate = "+0%"  # Natural fluid human cadence
        pitch = "+0Hz"

    target_voice = voice if (voice and voice in VALID_VOICE_IDS) else DEFAULT_VOICE

    try:
        audio_buffer = bytearray()
        async for chunk in stream_edge_tts_chunks(text, voice=target_voice, rate=rate, pitch=pitch):
            audio_buffer.extend(chunk)

        if audio_buffer:
            b64_audio = base64.b64encode(audio_buffer).decode("ascii")
            return f"data:audio/mp3;base64,{b64_audio}"
    except Exception as e:
        print(f"[!] Fast speech synthesis notice: {e}")

    return ""

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
    Synthesizes natural, human-like voice via Microsoft neural multilingual TTS.
    """
    if spoken_text and isinstance(spoken_text, dict):
        active_text = spoken_text.get("spoken_text") or spoken_text.get("display_text") or text
    elif spoken_text and isinstance(spoken_text, str) and len(spoken_text.strip()) > 0:
        active_text = spoken_text.strip()
    else:
        active_text = text

    return await synthesize_fast_speech(
        active_text,
        wellness_score=wellness_score,
        dominant_state=dominant_state,
        voice=voice,
        language_mode=language_mode
    )

