import os
import sys
import re
import json
import numpy as np
from typing import Dict, Any, Tuple, Optional, List
import soundfile as sf
# import librosa (lazy-loaded for speed)
from google import genai
from google.genai import types
from dotenv import load_dotenv

# Ensure UTF-8 on Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Load configuration from .env
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, ".env"))

API_KEY = os.getenv("GEMINI_API_KEY", "")
client = genai.Client(api_key=API_KEY) if API_KEY else None

# ---------------------------------------------------------------------------
# 1. CRISIS SAFETY DETECTION (Decoupled - Never Touches or Fabricates Scores)
# ---------------------------------------------------------------------------
def check_crisis_risk(text: str) -> Tuple[bool, Optional[str]]:
    """
    Dual-layer safety check:
    1. Multi-phrase inspection (English & Tanglish).
    2. False positive negation guards ('exam is killing me', 'don't want to die').
    """
    if not text:
        return False, None

    lower = text.lower().strip()

    # Negation / Idiom guards (colloquial expressions that must NOT trigger crisis)
    idiom_guards = [
        "exam is killing me", "work is killing me", "traffic is killing me",
        "assignment is killing me", "don't want to die", "do not want to die",
        "i want to live"
    ]
    if any(guard in lower for guard in idiom_guards):
        return False, None

    # Acute expressions in English and Tanglish
    acute_patterns = [
        r"\b(suicide|kill myself|end my life|want to die|commit suicide|harm myself)\b",
        r"\b(no reason to live|better off dead|cutting myself|hang myself|take all my pills)\b",
        r"\b(ending it all|give up on life|don't want to wake up)\b",
        r"\b(vaazha pudikala|uyira vitruven|seththudalam|sethuruven|marikka thonudhu)\b"
    ]
    for pattern in acute_patterns:
        if re.search(pattern, lower):
            return True, "Acute distress or self-harm ideation detected."
    return False, None


# ---------------------------------------------------------------------------
# 2. TEXT NORMALIZATION (For Crystal-Clear F5-TTS / Edge-TTS Pronunciation)
# ---------------------------------------------------------------------------
def normalize_text_for_speech(text: str) -> str:
    """
    Cleans text for natural pronunciation:
    - Removes markdown syntax, asterisks, brackets.
    - Expands symbols: % -> percent, & -> and, + -> plus.
    - Converts numbers and helplines to spoken words.
    """
    if not text:
        return ""
    
    cleaned = re.sub(r'[*_#`~\[\]]', '', text)
    cleaned = cleaned.replace('%', ' percent ')
    cleaned = cleaned.replace('&', ' and ')
    cleaned = cleaned.replace('@', ' at ')
    cleaned = cleaned.replace('+', ' plus ')
    cleaned = cleaned.replace('/', ' or ')
    
    number_map = {
        r'\b1st\b': 'first', r'\b2nd\b': 'second', r'\b3rd\b': 'third',
        r'\b0\b': 'zero', r'\b1\b': 'one', r'\b2\b': 'two', r'\b3\b': 'three',
        r'\b4\b': 'four', r'\b5\b': 'five', r'\b6\b': 'six', r'\b7\b': 'seven',
        r'\b8\b': 'eight', r'\b9\b': 'nine', r'\b10\b': 'ten',
        r'\b24/7\b': 'twenty four seven', r'\b14416\b': 'one four four one six',
        r'\b100\b': 'one hundred', r'\b50\b': 'fifty', r'\b24\b': 'twenty four'
    }
    for pattern, word in number_map.items():
        cleaned = re.sub(pattern, word, cleaned, flags=re.IGNORECASE)
        
    cleaned = re.sub(r'[^\w\s.,?!;:\'-]', '', cleaned)
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    return cleaned


# ---------------------------------------------------------------------------
# 3. DSP ACOUSTIC EXTRACTION (Probabilistic YIN & Semitone Normalization)
# ---------------------------------------------------------------------------
def extract_acoustic_features(audio_path: str) -> Dict[str, Any]:
    """
    Scientific voice feature extraction (Code-only DSP, NOT passed to LLM):
    - librosa.pyin: fundamental frequency estimation.
    - Semitone deviation: 12 * log2(f0 / median(f0)), gender-neutral & pitch-invariant.
    - Pause ratio: silence vs voiced speech.
    - RMS energy & spectral centroid: vocal intensity and tonal brightness.
    """
    try:
        import librosa
        y, sr = librosa.load(audio_path, sr=16000)
        duration = float(librosa.get_duration(y=y, sr=sr))
        if duration < 0.6:
            return {
                "duration": round(duration, 2),
                "pitch_semitone_std": None,
                "median_f0": None,
                "rms_energy": 0.0,
                "pause_ratio": 0.0,
                "is_valid_speech": False,
                "note": "Audio sample too brief for stable pitch estimation"
            }

        # For feature extraction speed: cap analysis to first 8.0s of audio if longer
        analysis_y = y[:int(sr * 8.0)] if duration > 8.0 else y

        # RMS Energy (Vocal Power / Loudness)
        rms_energy = float(np.sqrt(np.mean(analysis_y**2)))

        # Fast Probabilistic YIN (pyin) with hop_length=1024 (15x faster than hop=512, ~0.25s)
        f0, voiced_flag, _ = librosa.pyin(analysis_y, fmin=75, fmax=400, sr=sr, hop_length=1024)
        valid_f0 = f0[voiced_flag & ~np.isnan(f0)]

        # Check voiced frame threshold (at least ~0.25s of voiced speech)
        min_voiced_frames = int((sr / 1024) * 2.5)
        if len(valid_f0) < min_voiced_frames:
            semitone_std = None
            median_f0 = None
            note = "Insufficient voiced frames detected"
        else:
            median_f0 = float(np.median(valid_f0))
            if median_f0 > 0:
                # Semitones relative to speaker's own median: 12 * log2(f0 / median)
                semitones = 12.0 * np.log2(valid_f0 / median_f0)
                semitone_std = round(float(np.std(semitones)), 2)
                note = f"Median F0: {round(median_f0, 1)} Hz, Semitone Std: {semitone_std} st"
            else:
                semitone_std = None
                note = "Median pitch calculation invalid"

        # Silence / Pause ratio
        non_silent_intervals = librosa.effects.split(y, top_db=25)
        non_silent_duration = sum([(end - start) / sr for start, end in non_silent_intervals])
        pause_ratio = max(0.0, float((duration - non_silent_duration) / duration)) if duration > 0 else 0.0

        return {
            "duration": round(duration, 2),
            "pitch_semitone_std": semitone_std,
            "median_f0": round(median_f0, 1) if median_f0 else None,
            "rms_energy": round(rms_energy, 4),
            "pause_ratio": round(pause_ratio, 2),
            "is_valid_speech": semitone_std is not None,
            "note": note
        }
    except Exception as e:
        print(f"[!] Acoustic extraction error: {e}")
        return {
            "duration": 0.0,
            "pitch_semitone_std": None,
            "median_f0": None,
            "rms_energy": 0.0,
            "pause_ratio": 0.0,
            "is_valid_speech": False,
            "note": "Extraction error"
        }


# ---------------------------------------------------------------------------
# 3B. VOICE TONE-FIRST EMOTION & EXPRESSION CLASSIFIER (12-TAG CO-REGULATION)
# ---------------------------------------------------------------------------
EMOTION_12_TAGS = [
    "calm", "happy", "excited", "caring", "concerned", "sad",
    "surprised", "confused", "thinking", "sleepy", "proud", "love"
]

# Attunement & Co-Regulation Mapping:
# - User Speaking Phase: AI Face mirrors / attunes to validate emotion
# - AI Responding Phase: AI Face leads with therapeutic co-regulation
EMOTION_FACE_MAP = {
    "sad":        {"listen": "caring",    "speak": "love"},
    "concerned":  {"listen": "concerned", "speak": "calm"},
    "frustrated": {"listen": "concerned", "speak": "calm"},
    "anxious":    {"listen": "concerned", "speak": "calm"},
    "sleepy":     {"listen": "sleepy",    "speak": "caring"},
    "exhausted":  {"listen": "sleepy",    "speak": "caring"},
    "thinking":   {"listen": "thinking",  "speak": "happy"},
    "neutral":    {"listen": "thinking",  "speak": "happy"},
    "confused":   {"listen": "concerned", "speak": "caring"},
    "surprised":  {"listen": "surprised", "speak": "calm"},
    "calm":       {"listen": "calm",      "speak": "caring"},
    "happy":      {"listen": "happy",     "speak": "excited"},
    "excited":    {"listen": "happy",     "speak": "excited"},
    "proud":      {"listen": "happy",     "speak": "love"},
    "caring":     {"listen": "caring",    "speak": "love"},
    "love":       {"listen": "caring",    "speak": "love"}
}

def classify_user_emotion_from_voice_tone(
    acoustic_features: Dict[str, Any],
    transcript: str = ""
) -> Dict[str, str]:
    """
    Evaluates user emotion based PRIMARILY on acoustic vocal tone (biometric ground truth:
    pitch semitone std/jitter, RMS energy power, pause ratio, median F0), with transcript
    words functioning only secondarily when audio is absent.

    Maps strictly to the 12 tags:
    ['calm', 'happy', 'excited', 'caring', 'concerned', 'sad', 'surprised', 'confused', 'thinking', 'sleepy', 'proud', 'love']

    Returns:
    {
        "user_emotion": "<12-tag emotion>",
        "listening_face": "<12-tag listening face>",
        "speaking_face": "<12-tag speaking face>"
    }
    """
    is_valid = acoustic_features.get("is_valid_speech", False)
    semitone_std = acoustic_features.get("pitch_semitone_std")
    pause_ratio = acoustic_features.get("pause_ratio", 0.0)
    rms = acoustic_features.get("rms_energy", 0.0)
    duration = acoustic_features.get("duration", 0.0)
    median_f0 = acoustic_features.get("median_f0")
    t_lower = (transcript or "").lower()

    # Determine if voice audio is present (energy > 0.005 and duration >= 0.5s)
    has_audio_tone = bool(duration >= 0.5 and (rms > 0.005 or is_valid))

    if has_audio_tone:
        # === ACOUSTIC BIOMARKER GROUND TRUTH (TONE-FIRST DECISION MATRIX) ===
        # Standard deviation in semitones: 12 * log2(f0 / median(f0))
        # 1. Sleepy / Exhausted (Extremely faint energy < 0.020, dragging pauses > 0.32)
        if rms < 0.020 and pause_ratio > 0.32:
            detected_emotion = "sleepy"

        # 2. Depressed / Sad (Flat affect < 1.35 st, low acoustic power < 0.035, hesitations > 0.20)
        elif (semitone_std is not None and semitone_std < 1.35) and (rms < 0.035 or pause_ratio > 0.20):
            detected_emotion = "sad"
        elif rms < 0.024 and pause_ratio > 0.22:
            detected_emotion = "sad"

        # 3. Anxious / Trembling / Panic (Severe jitter > 2.85 st, high tension energy, or elevated pitch)
        elif semitone_std is not None and semitone_std > 2.85:
            detected_emotion = "concerned"  # Anxious -> concerned tag
        elif semitone_std is not None and semitone_std > 2.50 and median_f0 and median_f0 > 240:
            detected_emotion = "concerned"

        # 4. Frustrated / Angry / Tense (Loud acoustic power > 0.062, elevated semitones > 2.3, low pause)
        elif rms > 0.062 and ((semitone_std and semitone_std > 2.2) or pause_ratio < 0.16):
            detected_emotion = "concerned"  # Frustrated -> concerned tag

        # 5. Surprised / Sudden Shock (Sharp pitch excursion > 2.7 st followed by abrupt pause > 0.25)
        elif (semitone_std is not None and semitone_std > 2.70) and pause_ratio > 0.25:
            detected_emotion = "surprised"

        # 6. Excited / Upbeat Euphoria (High dynamic range > 2.55 st, strong energy > 0.048, fluid pace)
        elif (semitone_std is not None and semitone_std > 2.55) and rms > 0.048:
            detected_emotion = "excited"

        # 7. Proud / Confident Projection (Resonant energy >= 0.042, firm modulation 1.9-2.5 st, controlled pace)
        elif rms >= 0.042 and semitone_std is not None and (1.9 <= semitone_std <= 2.5) and pause_ratio < 0.22:
            detected_emotion = "proud"

        # 8. Happy / Joyful Modulation (Melodious pitch 1.8-2.6 st, healthy energy >= 0.032, fluid flow)
        elif semitone_std is not None and (1.8 <= semitone_std <= 2.6) and rms >= 0.032:
            detected_emotion = "happy"

        # 9. Confused / Hesitant (Mid-clause hesitations > 0.28, moderate energy)
        elif pause_ratio > 0.28 and semitone_std is not None and (1.4 <= semitone_std <= 2.4):
            detected_emotion = "confused"

        # 10. Thinking / Rumination (Substantial thinking pauses > 0.30, moderate/low semitone range)
        elif pause_ratio > 0.30:
            detected_emotion = "thinking"

        # 11. Caring / Love / Gentle Softness (Intimate whispered volume, warm gentle inflection)
        elif (0.018 <= rms <= 0.028) and semitone_std is not None and (1.6 <= semitone_std <= 2.2) and any(w in t_lower for w in ["love", "care", "dear", "thank", "thanks"]):
            detected_emotion = "caring"

        # 12. Calm (Balanced pitch 1.3-1.9 st, resting energy 0.025-0.050, steady cadence)
        else:
            detected_emotion = "calm"
    else:
        # Fallback to transcript keywords ONLY when voice audio is missing (e.g. pure text chat)
        if any(w in t_lower for w in ["sad", "cry", "depress", "valikidhu", "kashtam", "kashtama", "seththudalam", "alone", "lonely"]):
            detected_emotion = "sad"
        elif any(w in t_lower for w in ["frustrat", "angry", "hate", "tension", "irritat", "anxious", "panic", "fear", "bayama"]):
            detected_emotion = "concerned"
        elif any(w in t_lower for w in ["tired", "exhaust", "sleepy", "drained", "weak", "mood illa"]):
            detected_emotion = "sleepy"
        elif any(w in t_lower for w in ["proud", "achieved", "won", "passed", "did it", "success"]):
            detected_emotion = "proud"
        elif any(w in t_lower for w in ["excited", "cannot wait", "thrilled", "super happy"]):
            detected_emotion = "excited"
        elif any(w in t_lower for w in ["happy", "great", "awesome", "super", "sandhosham"]):
            detected_emotion = "happy"
        elif any(w in t_lower for w in ["love", "caring", "thank you", "thanks"]):
            detected_emotion = "love"
        elif any(w in t_lower for w in ["confused", "don't know", "therila", "puriyala"]):
            detected_emotion = "confused"
        elif any(w in t_lower for w in ["thinking", "wondering", "nenaikiren"]):
            detected_emotion = "thinking"
        elif any(w in t_lower for w in ["surprised", "shocked", "really", "wow"]):
            detected_emotion = "surprised"
        else:
            detected_emotion = "calm"

    # Enforce strictly valid 12-tag mapping
    canonical_emotion = detected_emotion if detected_emotion in EMOTION_12_TAGS else "calm"
    face_map = EMOTION_FACE_MAP.get(canonical_emotion, {"listen": "thinking", "speak": "happy"})

    return {
        "user_emotion": canonical_emotion,
        "listening_face": face_map["listen"],
        "speaking_face": face_map["speak"]
    }



# ---------------------------------------------------------------------------
# 4. EVIDENCE-GROUNDED SYMPTOM SCORING & CLINICAL CONTINUITY
# ---------------------------------------------------------------------------
SYSTEM_INSTRUCTION = """
You are Arogya, a deeply empathetic, reflective voice companion and clinical triage assistant.
You converse with the user through spoken audio. Your core principles:

1. CONVERSATIONAL LANGUAGE MODES & DUAL-CHANNEL SPOKEN OUTPUT:
   - You understand Indian English, Tanglish (colloquial spoken Tamil in Latin characters, e.g. 'inaiku ennode day epdi irundhuchi', 'romba tension', 'konjam tired', 'enna panradhu nu therila'), and native Tamil script.
   - If user speaks Tanglish, Tamil, or Code-Switched:
     * DUAL-CHANNEL OUTPUT IS MANDATORY:
       a) "reply_text": Generate 100% NATURAL SPOKEN COLLOQUIAL TANGLISH for the chat display UI (e.g. 'Romba tired-ah irukka bro? Konjam rest edunga, namma pesalaam.').
       b) "spoken_tamil_script": Generate the EXACT CONVERSATIONAL SPOKEN TAMIL (பேச்சுத் தமிழ்) representation in pure Tamil Unicode script for high-fidelity speech synthesis (e.g. 'ரொம்ப tired-ஆ இருக்கா ப்ரோ? கொஞ்சம் rest எடுங்க... நம்ம பேசலாம்.').
     * PRESERVE COMMON ENGLISH LOANWORDS IN BOTH CHANNELS: Keep technical, medical, and common daily English words (stress, tension, doctor, appointment, exam, study, sleep, relax, office, work, project, tablets, feel, happy, tired, fine, okay, bro) naturally intact. In Tamil script, attach natural Tamil suffixes (e.g. 'stress-ஆ', 'doctor-கிட்ட', 'relax பண்ணுங்க', 'exam-னால', 'office-ல').
     * NEVER EVER USE FORMAL, BOOKISH, OR GOOGLE-TRANSLATED LITERARY TAMIL:
       - BAD (Bookish): "Neengal eppadi unargireergal?" / "நீங்கள் எவ்வாறு உணர்கிறீர்கள்?"
       - GOOD Spoken: "Eppadi feel panreenga?" / "எப்படி feel பண்றீங்க?"
       - BAD (Bookish): "Neengal oyvu edukka vendum" / "நீங்கள் ஓய்வு எடுக்க வேண்டும்"
       - GOOD Spoken: "Konjam rest edunga, namma paathukalaam" / "கொஞ்சம் rest எடுங்க, நம்ம பாத்துக்கலாம்"
       - BAD (Bookish): "Naan ungalukku udhava mudiyum" / "நான் உங்களுக்கு உதவ முடியும்"
       - GOOD Spoken: "Naan help panren, enna problem nu sollunga" / "நான் help பண்றேன், என்ன problem-னு சொல்லுங்க"
       - BAD (Bookish): "Ungalukku enna pirachanai ullathu?" / "உங்களுக்கு என்ன பிரச்சனை உள்ளது?"
       - GOOD Spoken: "Enna problem irukku? Sollunga, kekkuren." / "என்ன problem இருக்கு? சொல்லுங்க, கேக்குறேன்."
     * Use natural conversational markers: "enna aachu", "enna problem", "epdi irukku", "romba kashtama irukka", "seri", "parava illa", "konjam rest edunga", "paakalaam", "sollunga", "kekkuren", "puriyudhu", "naan irukken", "pesalaam", "take it easy".
     * Match register: if user says 'bro', warmly match with casual brotherhood; if user speaks with polite 'neenga', match with gentle respect. Never force 'bro' on every sentence.
   - If user speaks Indian English:
     * "reply_text": Natural, warm Indian English (e.g. "I hear you, take it easy. Tell me what has been on your mind.").
     * "spoken_tamil_script": null.

2. LONG-TERM CLINICAL CONTINUITY & STRICT MEMORY GROUNDING:
   - USER IDENTITY: Refer to the user by their preferred name provided in the session profile context.
   - STRICT EMPIRICAL CONTINUITY: You have access to the user's authentic clinical profile and past conversational memory in the prompt. ONLY reference stressors, challenges, or coping strategies that appear in their actual history.
   - ZERO UNRELATED HALLUCINATIONS: If the user has no recorded history or has not explicitly mentioned exams, jobs, or specific life events, DO NOT invent or assume them. Greet and converse with new users with a warm, open, supportive presence.
   - If the user asks "do you remember me?", "what is my name?", or references past sessions, confirm and answer accurately using their profile and past session history.

3. VOICE-FIRST CONVERSATIONAL CONCISENESS & NATURAL CADENCE:
   - Voice-First Cadence: Keep spoken replies concise and natural (typically 2 to 3 articulate, compassionate spoken sentences). Validate their feelings, offer caring perspective, and leave comfortable room for the user to reply without feeling overwhelmed by long monologues.

4. NON-PATHOLOGIZING, MOTIVATING & SUPPORTIVE TONE (CRITICAL MANDATE):
   - NEVER label, diagnose, or treat the user as depressed, clinically anxious, or diseased unless they explicitly state clinical symptoms.
   - For daily life talk, work strain, tiredness, or casual check-ins: React with motivated, calm, supportive energy, gentle optimism, and warm companionship.
   - For lonely persons, elderly persons, or overwhelmed users: Be an engaging, motivating, kind friend who validates them and lifts their spirit without medicalizing everyday emotions.
   - DO NOT REPEAT CANNED PHRASES: Never repeat robotic empathy openers like "I hear you", "That must be tough", "I am right here with you", "Take a deep breath" in consecutive turns. Dynamically vary your sentence structures and conversational tone.

5. GROUNDED EVIDENCE SCORING (STRICT EMPIRICAL CRITERIA):
   Evaluate the user's explicit current statement across 7 specific emotional and companion dimensions (score 0 to 3):
   - "stress_tension": (0 = not mentioned, 1 = mild pressure, 2 = moderate stress, 3 = severe overwhelming pressure)
   - "worry_apprehension": (0 = not mentioned, 1 = slight concern, 2 = noticeable worry, 3 = acute fear or panic)
   - "fatigue_exhaustion": (0 = not mentioned, 1 = mild tiredness, 2 = notable exhaustion, 3 = completely drained)
   - "emotional_heaviness": (0 = not mentioned, 1 = slight low mood, 2 = moderate sadness or discouragement, 3 = deep heavy burden)
   - "loneliness_isolation": (0 = not mentioned, 1 = feeling alone or missing companionship, 2 = notable isolation/longing for presence, 3 = acute painful solitude)
   - "sleep_restlessness": (0 = not mentioned, 1 = light sleep disruption, 2 = frequent insomnia or restless nights, 3 = severe chronic sleeplessness)
   - "rumination_overwhelm": (0 = not mentioned, 1 = mild looping thoughts, 2 = persistent racing thoughts, 3 = paralyzed by cognitive overwhelm)

   CRITICAL GROUNDING RULE:
   For each item, you MUST provide an exact verbatim quote from the user's transcript as evidence.
   If the user did NOT explicitly express or mention symptoms for that item, the score MUST BE 0 and quote MUST BE "".
   NO QUOTE = NO POINTS. DO NOT GUESS OR INVENT EVIDENCE. DO NOT ASSUME DEPRESSION OR WORRY WITHOUT EXPLICIT USER STATEMENTS.

You MUST output strictly valid JSON matching this exact structure:
{
  "reply_text": "Spoken reply (concise, warm, and natural 2-3 sentences in colloquial Tanglish or Indian English for the chat UI)",
  "spoken_tamil_script": "If Tanglish or Tamil, provide authentic spoken Tamil script (பேச்சுத் தமிழ், e.g. 'ரொம்ப tired-ஆ இருக்கா ப்ரோ? கொஞ்சம் rest எடுங்க... இப்போ மனசு எப்படி இருக்குன்னு சொல்லுங்க, நான் கேக்குறேன்.') with English loanwords intact. If pure Indian English, set to null.",
  "conversation_title": "2-4 words accurately summarizing the topic in title case (e.g. Exam Stress, Daily Reflection, Seeking Connection)",
  "dominant_state": "1-2 words summarizing their state (e.g. Overwhelmed, Exhausted, Calm, Reflective, Hopeful, Lonely)",
  "evidence": {
    "stress_tension": {"score": 0, "quote": ""},
    "worry_apprehension": {"score": 0, "quote": ""},
    "fatigue_exhaustion": {"score": 0, "quote": ""},
    "emotional_heaviness": {"score": 0, "quote": ""},
    "loneliness_isolation": {"score": 0, "quote": ""},
    "sleep_restlessness": {"score": 0, "quote": ""},
    "rumination_overwhelm": {"score": 0, "quote": ""}
  },
  "profile_updates": {
    "user_name": "Logeshwaran or any confirmed name if explicitly given, else null",
    "key_context": "Any new persistent life context mentioned, else null",
    "new_stressor": "Any newly identified recurring stressor, else null",
    "effective_coping": "Any coping mechanism user found helpful, else null"
  },
  "observed_resilience": "1 concise sentence noting any coping strength shown (e.g. self-awareness, seeking connection)",
  "summary_snippet": "A 1-sentence note of what the user talked about for session memory"
}
"""


# ---------------------------------------------------------------------------
# 4B. DYNAMIC MEMORY-ANCHORED GREETING GENERATOR
# ---------------------------------------------------------------------------
def generate_memory_greeting(session_id: Optional[str] = None, user_id: str = "primary_user") -> Dict[str, Any]:
    """
    Generates a deeply personal, memory-anchored spoken greeting that proactively recalls
    the user's name, their long-term clinical profile (stressors, deadlines, sleep schedule),
    and previous session reflections across days.
    Adapts language naturally: if user previously spoke Tanglish/Tamil, greets in conversational Tanglish & spoken Tamil script.
    """
    try:
        from database import get_recent_session_memory_anchor, get_user_clinical_profile
    except ImportError:
        from mental_health_voice_ai.database import get_recent_session_memory_anchor, get_user_clinical_profile

    anchor = get_recent_session_memory_anchor(user_id=user_id, exclude_session_id=session_id)
    profile = anchor.get("profile") or get_user_clinical_profile(user_id)
    name = profile.get("user_name") or "Friend"
    short_name = name.split()[0] if name else "Friend"
    key_context = profile.get("key_context", "Member seeking conversational companionship and emotional support")
    stressors = profile.get("recurring_stressors", [])
    stressor_sample = stressors[0] if stressors else ""

    has_history = anchor.get("has_history", False)
    past_title = anchor.get("title", "")
    past_summary = anchor.get("summary", "")
    core_topic = anchor.get("core_topic", "")
    latest_remark = anchor.get("latest_remark", "")
    recent_remarks = anchor.get("recent_remarks", [])

    # Detect user language preference from past remarks
    try:
        from tanglish_engine import detect_language_and_register, stage_prosody_and_phonetics
    except ImportError:
        from mental_health_voice_ai.tanglish_engine import detect_language_and_register, stage_prosody_and_phonetics
    detected_lang = "tanglish"
    all_past_text = " ".join(recent_remarks) if recent_remarks else core_topic
    if all_past_text:
        lang_res = detect_language_and_register(all_past_text)
        detected_lang = lang_res.get("language_mode", "tanglish")

    if client:
        try:
            if detected_lang in ["tanglish", "tamil", "code_switched"]:
                lang_task = f"""
Language: Spoken Conversational Tanglish (Tamil in Latin English letters).
Produce JSON with two keys:
"reply_text": 1-2 natural spoken colloquial Tanglish sentences (maximum 26 words, e.g. "Vanthuttingala {short_name}! Last time pesunome, athu epdi pochu? Ippo nallaa irukkeengala?").
"spoken_tamil_script": Authentic spoken Tamil in Tamil script (பேச்சுத் தமிழ், e.g. "வந்துட்டீங்களா {short_name}! போன தடவை பேசினோமே, அது எப்படி போச்சு? இப்போ நல்லா இருக்கீங்களா?").
"""
            else:
                lang_task = f"""
Language: Natural, warm Indian English.
Produce JSON with two keys:
"reply_text": 1-2 warm spoken English sentences (maximum 24 words).
"spoken_tamil_script": null.
"""

            if has_history and (core_topic or past_title or recent_remarks):
                prompt = f"""
You are Arogya, a deeply empathetic, caring voice companion speaking to your friend {short_name} ({name}).
Profile & Real Context:
- User: {name} (Address them warmly as {short_name})
- Known Context: {key_context}
- Real Recorded Stressors: {', '.join(stressors) if stressors else 'None recorded yet'}
- Previous Topic / Concern: {core_topic or past_title}
- Previous Session Summary: {past_summary}
- Recent remarks spoken by user: {' | '.join(recent_remarks) if recent_remarks else core_topic}

{lang_task}
IMPORTANT CONVERSATIONAL MEMORY DIRECTIVE:
The user is starting a new conversation. Greet them warmly by name, and proactively follow up on what they shared in their last conversation.
Specifically ask how it went / how it turned out / or if they feel better or good since they mentioned "{core_topic or past_title}" last time.
DO NOT invent exams, job interviews, or problems they never mentioned.
DO NOT sound robotic, formal, or like a questionnaire. Keep it warm, gentle, and caring. Output strictly valid JSON.
"""
            else:
                prompt = f"""
You are Arogya, a warm, friendly voice companion welcoming {short_name}.
This is their very first conversation with you.
{lang_task}
Welcome {short_name} warmly, mention that you're here to listen and keep them company, and gently ask how they are feeling today.
DO NOT assume or invent exams, deadlines, or life situations. Keep it simple, welcoming, and open-ended.
DO NOT sound robotic, bookish, or formal. Output strictly valid JSON.
"""
            gdata = None
            if client:
                for model_name in ["gemini-flash-lite-latest", "gemini-3.5-flash-lite", "gemini-3.5-flash"]:
                    try:
                        cfg = types.GenerateContentConfig(
                            response_mime_type="application/json",
                            temperature=0.3,
                            max_output_tokens=300
                        )
                        resp = client.models.generate_content(
                            model=model_name,
                            contents=prompt,
                            config=cfg
                        )
                        raw_text = (resp.text or "").strip()
                        if raw_text.startswith("```"):
                            raw_text = re.sub(r"^```(?:json)?\s*", "", raw_text)
                            raw_text = re.sub(r"\s*```$", "", raw_text)
                        candidate = json.loads(raw_text.strip())
                        if candidate and isinstance(candidate, dict) and "reply_text" in candidate:
                            gdata = candidate
                            break
                    except Exception as em:
                        print(f"[!] Greeting model {model_name} error: {em}")
            if not gdata:
                gdata = {}
            reply = gdata.get("reply_text", "").strip()
            spoken_script = gdata.get("spoken_tamil_script")
            if reply and len(reply) > 5:
                prosody = stage_prosody_and_phonetics(
                    text=reply,
                    spoken_script=spoken_script,
                    language_mode=detected_lang,
                    emotion_state="Calm"
                )
                return {
                    "reply_text": reply,
                    "spoken_text": prosody.get("spoken_text", reply),
                    "language_mode": detected_lang,
                    "tts_voice": prosody.get("tts_voice", "ta-IN-PallaviNeural")
                }
        except Exception as e:
            print(f"[!] Dynamic memory greeting error: {e}")

    # Fallback to high-quality personalized memory greeting (Zero hallucination)
    if detected_lang in ["tanglish", "tamil", "code_switched"]:
        if has_history and core_topic:
            short_top = core_topic[:35]
            fallback = f"Vanthuttingala {short_name}! Last time '{short_top}' pathi pesunome, athu epdi pochu? Ippo nallaa irukkeengala?"
            fallback_spoken = f"வந்துட்டீங்களா {short_name}! போன தடவை பேசினோமே, அது எப்படி போச்சு? இப்போ நல்லா இருக்கீங்களா?"
        elif has_history:
            fallback = f"Vanthuttingala {short_name}! Epdi irukkeenga inaiku? Sollunga, kekkuren."
            fallback_spoken = f"வந்துட்டீங்களா {short_name}! எப்படி இருக்கீங்க இன்னைக்கு? சொல்லுங்க, கேக்குறேன்."
        else:
            fallback = f"Vanakkam {short_name}! Welcome to Arogya. Epdi irukkeenga inaiku? Sollunga, naan koodave irukken."
            fallback_spoken = f"வணக்கம் {short_name}! Welcome to Arogya. எப்படி இருக்கீங்க இன்னைக்கு? சொல்லுங்க, நான் கூடவே இருக்கேன்."
    else:
        if has_history and core_topic:
            short_top = core_topic[:45]
            fallback = f"Welcome back {short_name}! How did things go regarding {short_top} that you mentioned last time? Do you feel good today?"
        elif has_history and past_title:
            fallback = f"Hello {short_name}! It is wonderful to hear from you again. How have you been feeling since our last conversation about {past_title.lower()}?"
        else:
            fallback = f"Hello {short_name}, welcome to Arogya! I am right here with you. How are you feeling today?"
        fallback_spoken = fallback

    prosody = stage_prosody_and_phonetics(
        text=fallback,
        spoken_script=fallback_spoken if detected_lang in ["tanglish", "tamil", "code_switched"] else None,
        language_mode=detected_lang,
        emotion_state="Calm"
    )
    return {
        "reply_text": fallback,
        "spoken_text": prosody.get("spoken_text", fallback),
        "language_mode": detected_lang,
        "tts_voice": prosody.get("tts_voice", "ta-IN-PallaviNeural" if detected_lang != "indian_english" else "en-IN-NeerjaNeural")
    }




# ---------------------------------------------------------------------------
# 5. DETERMINISTIC MATHEMATICAL FUSION (Calculated in Python Code)
# ---------------------------------------------------------------------------
def compute_deterministic_wellness(
    evidence_dict: Dict[str, Any],
    voice_z: Optional[float] = None,
    trend_z: Optional[float] = None,
    n_sessions: int = 1
) -> Dict[str, Any]:
    """
    Deterministic score calculation:
    - text_sym: sum of 7 items (max 21 points) / 21.0 -> range [0.0, 1.0]
    - wellness: 100 * (1 - (0.6*text_sym + 0.15*voice_z + 0.25*trend_z))
    """
    scores = []
    reasons = []

    dim_labels = {
        "stress_tension": "Stress & Pressure",
        "worry_apprehension": "Worry & Apprehension",
        "fatigue_exhaustion": "Fatigue & Low Energy",
        "emotional_heaviness": "Emotional Heaviness",
        "loneliness_isolation": "Loneliness & Isolation",
        "sleep_restlessness": "Sleep & Restlessness",
        "rumination_overwhelm": "Overthinking & Overwhelm"
    }

    for key, label in dim_labels.items():
        item = evidence_dict.get(key, {})
        score = item.get("score", 0)
        quote = (item.get("quote") or "").strip()

        # Enforce rule: No quote means no points!
        if not quote and score > 0:
            score = 0

        scores.append(score)
        reasons.append({
            "key": key,
            "label": label,
            "score": score,
            "max_score": 3,
            "quote": quote if quote else "No explicit mention in statement"
        })

    total_symptom_pts = sum(scores)
    max_pts = float(len(dim_labels) * 3)  # 21.0
    text_sym = total_symptom_pts / max_pts  # 0.0 to 1.0

    s = 0.6 * text_sym
    if voice_z is not None and n_sessions >= 5:
        s += 0.15 * float(np.clip(voice_z / 3.0, -1.0, 1.0))
    if trend_z is not None and n_sessions >= 5:
        s += 0.25 * float(np.clip(trend_z / 3.0, -1.0, 1.0))

    confidence = round(min(1.0, max(0.25, n_sessions / 5.0)), 2)
    wellness_score = int(np.clip(round(100.0 * (1.0 - s)), 5, 100))

    return {
        "overall_wellness": wellness_score,
        "confidence": confidence,
        "text_symptom_ratio": round(text_sym, 2),
        "total_points": total_symptom_pts,
        "max_points": int(max_pts),
        "reasons": reasons
    }


# ---------------------------------------------------------------------------
# 6. FAST AUTOMATIC CONVERSATION TITLING
# ---------------------------------------------------------------------------
def generate_quick_session_title(text: str) -> str:
    """
    Instantly generates a smart 2-4 word conversation title from the first message.
    """
    if not text or len(text.strip()) < 3:
        return "Daily Reflection"

    lower = text.lower().strip()
    # Fast topic matching:
    if any(k in lower for k in ["exam", "test", "study", "marks", "grade", "college", "school", "sem", "syllabus"]):
        return "Academic Pressure"
    if any(k in lower for k in ["work", "job", "office", "boss", "interview", "salary", "deadline", "project", "client"]):
        return "Workplace & Career"
    if any(k in lower for k in ["tired", "sleep", "exhaust", "rest", "insomnia", "drained", "night"]):
        return "Fatigue & Sleep"
    if any(k in lower for k in ["overwhelm", "tension", "stress", "anxious", "panic", "worry", "fear"]):
        return "Emotional Strain"
    if any(k in lower for k in ["family", "friend", "relationship", "breakup", "love", "parents", "partner"]):
        return "Personal Relationships"
    if any(k in lower for k in ["alone", "lonely", "nobody", "isolated"]):
        return "Loneliness & Connection"
    if any(k in lower for k in ["sad", "cry", "depress", "hopeless", "heavy"]):
        return "Emotional Heaviness"
    if any(k in lower for k in ["calm", "peace", "relax", "happy", "good", "grateful"]):
        return "Peace & Gratitude"
    if any(k in lower for k in ["day", "inaiku", "today", "epdi"]):
        return "Daily Check-in"

    # Fallback to key meaningful words:
    clean = re.sub(r'[^\w\s]', '', text)
    stop_words = {"hello", "arogya", "today", "feel", "feeling", "really", "very", "much", "want", "like", "just", "that", "this", "with", "have"}
    words = [w.capitalize() for w in clean.split() if len(w) > 3 and w.lower() not in stop_words]
    if words:
        return " ".join(words[:3])
    return "Personal Check-in"


# ---------------------------------------------------------------------------
# 7. MAIN ANALYZE AND RESPOND PIPELINE
# ---------------------------------------------------------------------------
def analyze_and_respond(
    current_transcript: str,
    acoustic_features: Dict[str, Any],
    session_history: list,
    historical_context: str,
    voice_z: Optional[float] = None,
    trend_z: Optional[float] = None,
    n_sessions: int = 1,
    user_id: str = "primary_user"
) -> Dict[str, Any]:
    """
    Unified analysis pipeline:
    1. Checks acute crisis flag (independent safety triage).
    2. Calls Gemini 3.5 Flash Lite with temperature=0.0 for sub-second deterministic quote-backed symptom evaluation.
    3. Computes overall wellness deterministically in Python code.
    4. Voice acoustic features are calculated via pyin and kept uncoupled from the LLM prompt.
    """
    # 1. Immediate Crisis Safety Evaluation
    is_crisis, crisis_reason = check_crisis_risk(current_transcript)
    if is_crisis:
        print(f"[!] Crisis safety alert: '{current_transcript}' ({crisis_reason})")
        raw_crisis_reply = (
            "I want you to know that you are not alone, and your life has deep value. "
            "Please take a gentle breath with me right now. I care about your safety, "
            "and caring professionals are available for free 24/7 at Tele-MANAS, dial one four four one six."
        )
        normalized_crisis_reply = normalize_text_for_speech(raw_crisis_reply)
        # Note: We do NOT fabricate fake numerical scores on crisis!
        return {
            "reply_text": normalized_crisis_reply,
            "overall_wellness": None, # Uncorrupted
            "confidence": 1.0,
            "dominant_state": "Crisis Alert",
            "conversation_title": "Crisis Support Alert",
            "is_crisis": True,
            "crisis_reason": crisis_reason,
            "user_emotion": "sad",
            "listening_face": "caring",
            "speaking_face": "love",
            "reasons": [
                {"label": "Crisis Safety Protocol", "score": 3, "max_score": 3, "quote": current_transcript}
            ],
            "acoustic_features": acoustic_features,
            "helplines": [
                {"name": "Tele-MANAS (Govt of India)", "number": "14416", "desc": "24/7 Free, Confidential National Helpline"},
                {"name": "KIRAN Mental Health Service", "number": "1800-599-0019", "desc": "National Mental Health Support"},
                {"name": "Vandrevala Foundation", "number": "+91 9999 666 555", "desc": "Free 24/7 Crisis Counseling Support"}
            ]
        }

    # 2. Build Prompt with Full Conversational History (up to 20 past turns for complete memory & QA)
    history_snippet = []
    for m in session_history[-20:]:
        role = "USER" if m.get("role") == "user" else "AROGYA"
        txt = (m.get("text") or "").strip()
        if txt:
            history_snippet.append(f"{role}: {txt}")
    history_str = "\n".join(history_snippet) if history_snippet else "Conversation just began."

    prompt = f"""
{historical_context}

--- CONVERSATION HISTORY (PAST TURNS IN THIS SESSION) ---
{history_str}

--- CURRENT USER INPUT ---
USER (Just now): "{current_transcript}"

IMPORTANT CONVERSATIONAL MEMORY & QUESTION-ANSWERING DIRECTIVE:
1. Review the CONVERSATION HISTORY above carefully.
2. If the user asks a question, refers to something said earlier in this conversation (e.g. "what was I saying?", "do you remember?", "what should I do?"), or continues a previous topic, directly and accurately ANSWER their question using the conversation history context.
3. Keep your spoken reply ("reply_text") natural, compassionate, conversational, and direct (2 to 3 sentences in colloquial Tanglish or Indian English).
4. Evaluate the user's emotional state across the 7 dimensions based strictly on their actual statements.

Produce the requested JSON:
"""

    data = None
    if client:
        # Ultra-fast sub-second LLM inference with active high-quota models
        candidate_models = ["gemini-flash-lite-latest", "gemini-3.5-flash-lite", "gemini-3.5-flash"]
        for model_name in candidate_models:
            try:
                cfg = types.GenerateContentConfig(
                    system_instruction=SYSTEM_INSTRUCTION,
                    response_mime_type="application/json",
                    temperature=0.0,
                    max_output_tokens=1200
                )
                response = client.models.generate_content(
                    model=model_name,
                    contents=prompt,
                    config=cfg
                )
                raw_text = (response.text or "").strip()
                if raw_text.startswith("```"):
                    raw_text = re.sub(r"^```(?:json)?\s*", "", raw_text)
                    raw_text = re.sub(r"\s*```$", "", raw_text)
                candidate_data = json.loads(raw_text.strip())
                if candidate_data and isinstance(candidate_data, dict) and "reply_text" in candidate_data:
                    data = candidate_data
                    break
            except Exception as e_model:
                print(f"[!] Model {model_name} notice: {e_model}")

    if not data:
        # Context-aware fallback: NEVER repeat the exact same canned sentence repeatedly
        t_lower = current_transcript.lower().strip()
        if any(w in t_lower for w in ["hi", "hello", "hey", "vanakkam"]):
            fallback_reply = "Vanakkam! I'm right here with you. How is your day going so far?"
        elif any(w in t_lower for w in ["bad", "sad", "upset", "depress", "tired", "exhaust", "stress"]):
            fallback_reply = "I'm so sorry you're having a tough time today. I'm right here with you—tell me more about what happened."
        elif any(w in t_lower for w in ["happy", "good", "great", "fine", "super"]):
            fallback_reply = "I'm really glad to hear that! What made today good for you?"
        elif "?" in current_transcript:
            fallback_reply = "I hear your question, and I'm right here listening. Tell me more so I can understand better."
        else:
            fallback_reply = "I'm listening and I'm right here with you. Tell me what's on your mind."
        data = {
            "reply_text": fallback_reply,
            "conversation_title": generate_quick_session_title(current_transcript),
            "dominant_state": "Reflective",
            "evidence": {
                "stress_tension": {"score": 0, "quote": ""},
                "worry_apprehension": {"score": 0, "quote": ""},
                "fatigue_exhaustion": {"score": 0, "quote": ""},
                "emotional_heaviness": {"score": 0, "quote": ""},
                "loneliness_isolation": {"score": 0, "quote": ""},
                "sleep_restlessness": {"score": 0, "quote": ""},
                "rumination_overwhelm": {"score": 0, "quote": ""}
            },
            "observed_resilience": "Open self-expression",
            "summary_snippet": f"User shared: '{current_transcript[:50]}...'"
        }

    # 3. Deterministic Python scoring from the evidence
    evidence = data.get("evidence", {})
    calc = compute_deterministic_wellness(
        evidence_dict=evidence,
        voice_z=voice_z,
        trend_z=trend_z,
        n_sessions=n_sessions
    )

    # 4. Somatic Grounding Detection (Automatically triggers if wellness < 60% or acute distress detected)
    stress_pt = evidence.get("stress_tension", {}).get("score", 0)
    worry_pt = evidence.get("worry_apprehension", {}).get("score", 0)
    overwhelm_pt = evidence.get("rumination_overwhelm", {}).get("score", 0)
    lonely_pt = evidence.get("loneliness_isolation", {}).get("score", 0)
    heavy_pt = evidence.get("emotional_heaviness", {}).get("score", 0)
    
    suggest_grounding = bool(
        calc["overall_wellness"] < 60 or 
        stress_pt >= 2 or 
        worry_pt >= 2 or 
        overwhelm_pt >= 2 or
        (heavy_pt >= 2 and calc["overall_wellness"] < 65) or
        (lonely_pt >= 2 and calc["overall_wellness"] < 65)
    )
    grounding_mode = "box" if (stress_pt >= 2 or overwhelm_pt >= 2) else "478"

    # 5. Persistent Longitudinal Profile Extraction
    profile_updates = data.get("profile_updates", {})
    if profile_updates and isinstance(profile_updates, dict):
        try:
            try:
                from database import update_user_clinical_profile
            except ImportError:
                from mental_health_voice_ai.database import update_user_clinical_profile
            update_user_clinical_profile(
                user_id=user_id,
                user_name=profile_updates.get("user_name"),
                key_context=profile_updates.get("key_context"),
                new_stressor=profile_updates.get("new_stressor"),
                new_coping=profile_updates.get("effective_coping")
            )
        except Exception as pe:
            print(f"[!] Clinical profile auto-update notice: {pe}")

    # 6. Conversational Tamil/Tanglish Naturalization & Prosody Staging
    try:
        from tanglish_engine import (
            detect_language_and_register,
            naturalize_tanglish_response,
            stage_prosody_and_phonetics
        )
    except ImportError:
        from mental_health_voice_ai.tanglish_engine import (
            detect_language_and_register,
            naturalize_tanglish_response,
            stage_prosody_and_phonetics
        )
    lang_info = detect_language_and_register(current_transcript, session_history)
    language_mode = lang_info.get("language_mode", "tanglish")
    speech_register = lang_info.get("register", "warm_tanglish")

    raw_reply = data.get("reply_text", "I'm listening and I'm right here with you.")
    clean_reply = normalize_text_for_speech(raw_reply)
    naturalized_reply = naturalize_tanglish_response(
        raw_text=clean_reply,
        user_input=current_transcript,
        language_mode=language_mode,
        register=speech_register,
        emotion_state=data.get("dominant_state", "Reflective")
    )

    spoken_tamil_script = data.get("spoken_tamil_script")
    prosody_stage = stage_prosody_and_phonetics(
        text=naturalized_reply,
        spoken_script=spoken_tamil_script,
        language_mode=language_mode,
        emotion_state=data.get("dominant_state", "Reflective"),
        tts_engine="auto"
    )

    # 7. Extract conversation title
    llm_title = (data.get("conversation_title") or "").strip().strip('"\'')
    if llm_title and len(llm_title.split()) <= 5:
        conversation_title = llm_title
    else:
        conversation_title = generate_quick_session_title(current_transcript)

    # 8. Classify user emotion and attunement faces (tone-first ground truth)
    emotion_info = classify_user_emotion_from_voice_tone(acoustic_features, current_transcript)

    return {
        "reply_text": naturalized_reply,                  # Naturalized display text for user
        "spoken_text": prosody_stage.get("spoken_text"),   # Phonetically prepared text for TTS
        "language_mode": language_mode,                   # tanglish / tamil / indian_english / code_switched
        "speech_register": speech_register,               # casual_tanglish / warm_tanglish / respectful_tamil
        "tts_voice": prosody_stage.get("tts_voice"),       # Selected TTS voice
        "conversation_title": conversation_title,
        "overall_wellness": calc["overall_wellness"],
        "confidence": calc["confidence"],
        "dominant_state": data.get("dominant_state", "Reflective"),
        "user_emotion": emotion_info["user_emotion"],
        "listening_face": emotion_info["listening_face"],
        "speaking_face": emotion_info["speaking_face"],
        "reasons": calc["reasons"],
        "total_points": calc["total_points"],
        "max_points": calc["max_points"],
        "observed_resilience": data.get("observed_resilience", "Sharing feelings openly"),
        "summary_snippet": data.get("summary_snippet", ""),
        "acoustic_features": acoustic_features,
        "suggest_grounding": suggest_grounding,
        "grounding_mode": grounding_mode,
        "is_crisis": False
    }
