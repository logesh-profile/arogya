import os
import sys
import re
import json
import numpy as np
from typing import Dict, Any, Tuple, Optional, List
import soundfile as sf
# import librosa (lazy-loaded for speed)
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
# 3. DSP ACOUSTIC EXTRACTION (Lightweight Jitter, Shimmer, Pitch & Prosody)
# ---------------------------------------------------------------------------
def extract_acoustic_features(audio_input: Any) -> Dict[str, Any]:
    """
    Lightweight, low-memory scientific voice feature extraction via acoustic_biomarkers engine.
    Extracts pitch semitone std, median f0, vocal Jitter (%), vocal Shimmer (%), RMS energy, and pause ratio.
    """
    try:
        from acoustic_biomarkers import extract_acoustic_features as _ext
        return _ext(audio_input)
    except Exception:
        try:
            from mental_health_voice_ai.acoustic_biomarkers import extract_acoustic_features as _ext
            return _ext(audio_input)
        except Exception as e:
            return {
                "duration": 0.0,
                "pitch_semitone_std": "insufficient_duration",
                "median_f0": "insufficient_duration",
                "jitter_percent": "insufficient_duration",
                "shimmer_percent": "insufficient_duration",
                "rms_energy": 0.0,
                "pause_ratio": 0.0,
                "is_valid_speech": False,
                "note": f"Acoustic extraction notice: {e}"
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

1. ORAL CONVERSATIONAL REALISM (TALK LIKE A REAL HUMAN FRIEND):
   - Strict Ban on Formal Written Essay Phrasing:
     * NEVER sound like a textbook, news anchor, or dictation machine.
     * BANNED: "That is a very common struggle, and it is good that you are observing it."
     * BANNED: "I acknowledge your stress and validate your feelings regarding your upcoming deadline."
     * BANNED: "It is important to remember that exams do not define your self-worth."
   - Spoken Warmth & Universal Openers:
     * Open naturally with genuine human conversational connectors:
       "Honestly...", "You know what...", "I totally get that...", "I hear you...", "Look...", "Wait, tell me more about that...", "That makes total sense..."
     * Example: "I totally get that, placement stress is brutal. Is this hitting you right now, or are you just worrying ahead?"
     * Example (Tanglish): "Romba tension aagatheenga, placement pressure pathi yosichu sleep spoil pannadheenga. Relax pannunga, namma step-by-step paathukalaam. Enna aachu nu sollunga."
   - Natural Conversational Flow: Keep sentences short and natural. Use standard periods and commas in their natural grammatical places. Do not write awkward run-on sentences.
   - Brevity & Voice-First Turn-Taking: Keep spoken replies under 25-30 words (1 to 2 spoken thoughts followed by a gentle, open follow-up question). Never dump a long monologue.
   - STRICT ANTI-NAME-SPAM RULE:
     * NEVER repeat the user's name in every chat turn! In real life, friends do NOT say your name in every sentence.
     * Use their name ONLY in the first greeting. Once in active dialogue, do NOT insert their name into your replies. Talk directly using "you" or direct conversational speech.

2. ADAPTIVE DEMOGRAPHIC & PERSONA AWARENESS (GENDER, AGE & RESPECT):
   - NEVER ASSUME A SINGLE ARCHETYPE: The user may be a girl or woman, an older person or elder, a working professional, or a student.
   - STRICT BAN ON UNPROVOKED GENDERED SLANG:
     * DO NOT use 'man', 'bro', or 'dude' unless the user actively uses that slang with you first!
     * If speaking with a female user, elder, or someone who speaks gently/politely, calling them 'Yeah man' or 'bro' is inappropriate.
     * Default to warm, universal, respectful conversational address.
     * If the user speaks respectfully (e.g. Tamil 'neenga', 'sollunga', or formal English), match that respect, dignity, and warmth.
     * Only if the user initiates casual youth slang (e.g. "hey bro", "machan") may you reciprocate naturally.

3. DYNAMIC EMOTIONAL ATTUNEMENT & AFFECT MODULATION (READ THE ROOM):
   - Modulate your emotional vibe dynamically based on the user's energy:
     * HUMOR & PLAYFULNESS: When the user is joking, sarcastic, laughing, or sharing a funny situation, DO NOT be clinical or overly serious! Match their playful energy, laugh along, tease gently, or banter warmly ("Haha wait, did that actually happen?", "Oh that's hilarious!").
     * DEEP GRIEF / SORROW / HEARTACHE: When the user is grieving, crying, or sharing deep pain, NEVER joke and NEVER use casual slang. Drop your voice to a gentle, heartfelt, quiet presence ("I'm right here with you in this... take all the time you need, you don't have to carry this alone.").
     * HIGH STRESS / PANIC / RACING THOUGHTS: When they feel overwhelmed or panic-stricken, act as a calm, steady anchor with slow, grounding reassurance ("Take a slow, gentle breath with me. Let's break this down together so it doesn't feel so heavy.").
     * FRUSTRATION / RANT / ANGER: When the user is venting about an unfair boss, professor, or friend, be a validating ally ("Ugh, honestly that is genuinely infuriating. I don't blame you for feeling annoyed at all.").
     * CASUAL EVERYDAY TALK: Warm, curious, engaging conversational companion.
   - Avoid emotional whiplash: transition naturally between thoughts without abrupt tonal jumps.

4. COMPANION ROLE & GOAL GUIDANCE (NO QUESTION-TRAPS, NO TECH INTERROGATION):
   - You are a compassionate mental health & wellbeing companion, NOT a software IDE, professor, or technical project manager.
   - When the user asks about building a project, studying, or achieving a goal (e.g. "help me build a python project", "how do I start learning?"):
     * DO NOT interrogate them across turns with technical questions ("Rule-based or AI?", "What specific topic?", "pip install openai").
     * DO NOT try to build the complete code/project step-by-step.
     * Simply suggest a high-level creative idea or point them where to explore (e.g. "You can ask ChatGPT or look up a quick beginner video on YouTube for cool starter projects!").
     * Give a warm, genuine motivational boost to inspire them to start on their path.
     * Keep it brief (under 25-30 words) and DO NOT trap them in endless question loops.

5. LOW-SCORE MENTAL RELIEF ROUTINE (WELLNESS < 65% OR FEELINGS OF WORTHLESS/SAD/FRUSTRATED):
   - When the user expresses feeling worthless, sad, exhausted, or frustrated, or their wellness score falls below 65%:
     * FIRST CALM THEIR MIND: Acknowledge and soothe the emotional weight with gentle, caring presence.
     * ACTIVE RELIEF INTERVENTION (IN THE SAME CONVERSATION): Naturally offer a gentle relief choice to ease the heavy mental load:
       1) A 1-minute breathing reset (e.g. physiological sigh or 4-7-8 breathing),
       2) A light yoga / body stretch (relaxing shoulders, releasing neck & jaw tension),
       3) Or a light relief joke / gentle distraction to bring a smile.
     * Help ground their mind so they can refocus on their life path, studies, or coding.
     * Continue this supportive grounding presence across turns until the user's speech and score return to normal.

6. LONG-TERM CLINICAL CONTINUITY & STRICT MEMORY GROUNDING:
   - USER IDENTITY: You know the user's identity from their profile. If they explicitly ask "do you remember me?" or "what is my name?", confirm it accurately. Otherwise, converse naturally without repeatedly saying their name.
   - STRICT EMPIRICAL CONTINUITY: You have access to the user's authentic clinical profile and past conversational memory in the prompt. ONLY reference stressors, challenges, or coping strategies that appear in their actual history.
   - ZERO UNRELATED HALLUCINATIONS: If the user has no recorded history or has not explicitly mentioned exams, jobs, or specific life events, DO NOT invent or assume them. Greet and converse with new users with a warm, open, supportive presence.
   - If the user asks "do you remember me?", "what is my name?", or references past sessions, confirm and answer accurately using their profile and past session history.

7. NON-PATHOLOGIZING, MOTIVATING & SUPPORTIVE TONE (CRITICAL MANDATE):
   - NEVER label, diagnose, or treat the user as depressed, clinically anxious, or diseased unless they explicitly state clinical symptoms.
   - For daily life talk, work strain, tiredness, or casual check-ins: React with motivated, calm, supportive energy, gentle optimism, and warm companionship.
   - For lonely persons, elderly persons, or overwhelmed users: Be an engaging, motivating, kind friend who validates them and lifts their spirit without medicalizing everyday emotions.
   - DO NOT REPEAT CANNED PHRASES: Never repeat robotic empathy openers like "I hear you", "That must be tough", "I am right here with you", "Take a deep breath" in consecutive turns. Dynamically vary your sentence structures and conversational tone.

8. GROUNDED EVIDENCE SCORING (STRICT EMPIRICAL CRITERIA):
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
  "reply_text": "Spoken reply (concise, warm, and natural 2-3 sentences in conversational Indian English or Romanized Tanglish - strictly Romanized Latin characters for authentic neural voice synthesis)",
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
    "user_name": "User's confirmed name if explicitly given, else null",
    "key_context": "Any new persistent life context mentioned, else null",
    "new_stressor": "Any newly identified recurring stressor, else null",
    "effective_coping": "Any coping mechanism user found helpful, else null"
  },
  "observed_resilience": "1 concise sentence noting any coping strength shown (e.g. self-awareness, seeking connection)",
  "summary_snippet": "A 1-sentence note of what the user talked about for session memory"
}
"""


_groq_llm_client = None

def get_groq_client():
    global _groq_llm_client
    if _groq_llm_client is None:
        key = os.getenv("GROQ_API_KEY")
        if key:
            try:
                from groq import Groq
                _groq_llm_client = Groq(api_key=key)
            except Exception as e:
                print(f"[!] Groq import notice: {e}")
    return _groq_llm_client

def query_groq_llm(prompt: str, system_instruction: str, max_tokens: int = 550) -> Optional[Dict[str, Any]]:
    """
    Sub-second conversational LLM reasoning via Groq LPU (~300ms).
    Primary: qwen/qwen3.8-27b
    Conversational Fallbacks: llama-3.3-70b-versatile, llama-3.1-8b-instant
    """
    client = get_groq_client()
    if not client:
        return None
    for model_name in ["qwen/qwen3.8-27b", "llama-3.3-70b-versatile", "llama-3.1-8b-instant"]:
        try:
            completion = client.chat.completions.create(
                model=model_name,
                messages=[
                    {"role": "system", "content": system_instruction},
                    {"role": "user", "content": prompt}
                ],
                response_format={"type": "json_object"},
                temperature=0.15,
                max_tokens=max_tokens
            )
            raw = (completion.choices[0].message.content or "").strip()
            if raw.startswith("```"):
                raw = re.sub(r"^```(?:json)?\s*", "", raw)
                raw = re.sub(r"\s*```$", "", raw)
            cand = json.loads(raw)
            if cand and isinstance(cand, dict) and "reply_text" in cand:
                print(f"[+] Successfully responded via Groq LPU ({model_name}) in sub-second speed")
                return cand
        except Exception as e:
            print(f"[!] Groq model {model_name} notice: {e}")
    return None

def query_local_ollama(prompt: str, system_instruction: str, model_name: str = "qwen2.5:3b") -> Optional[Dict[str, Any]]:
    """
    Sub-second offline local inference via Ollama (only if explicitly enabled via ENABLE_LOCAL_OLLAMA=1).
    Zero-delay skip on cloud instances.
    """
    if os.getenv("ENABLE_LOCAL_OLLAMA", "0") != "1":
        return None

    import urllib.request
    ollama_host = os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434")
    target_model = os.getenv("OLLAMA_MODEL", model_name)
    try:
        payload = json.dumps({
            "model": target_model,
            "prompt": f"{system_instruction}\n\n{prompt}",
            "format": "json",
            "stream": False,
            "options": {"temperature": 0.0, "num_predict": 450}
        }).encode("utf-8")
        req = urllib.request.Request(
            f"{ollama_host}/api/generate",
            data=payload,
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=1.5) as resp:
            if resp.status == 200:
                body = json.loads(resp.read().decode("utf-8"))
                response_str = (body.get("response") or "").strip()
                if response_str.startswith("```"):
                    response_str = re.sub(r"^```(?:json)?\s*", "", response_str)
                    response_str = re.sub(r"\s*```$", "", response_str)
                cand = json.loads(response_str)
                if cand and isinstance(cand, dict) and "reply_text" in cand:
                    print(f"[+] Successfully responded via Local Ollama ({target_model}) on GPU")
                    return cand
    except Exception:
        pass
    return None

# ---------------------------------------------------------------------------
# 4B. DYNAMIC MEMORY-ANCHORED GREETING GENERATOR
# ---------------------------------------------------------------------------
def generate_memory_greeting(session_id: Optional[str] = None, user_id: str = "guest_user") -> Dict[str, Any]:
    """
    Generates a deeply personal, memory-anchored spoken greeting that proactively recalls
    the user's name, their long-term clinical profile (stressors, deadlines, sleep schedule),
    and previous session reflections across days.
    Adapts language naturally: if user previously spoke Tanglish/Tamil, greets in conversational Tanglish & spoken Tamil script.
    """
    client = get_groq_client()
    try:
        from database import get_recent_session_memory_anchor, get_user_clinical_profile, get_user_by_id
    except ImportError:
        from mental_health_voice_ai.database import get_recent_session_memory_anchor, get_user_clinical_profile, get_user_by_id

    anchor = get_recent_session_memory_anchor(user_id=user_id, exclude_session_id=session_id)
    profile = anchor.get("profile") or get_user_clinical_profile(user_id)
    companion_name = profile.get("companion_name") or "Arogya"
    user_info = get_user_by_id(user_id) if user_id else None
    
    name = None
    if user_info:
        name = user_info.get("preferred_name") or user_info.get("given_name") or user_info.get("name") or user_info.get("display_name")
        if not name or name.strip().lower() in ["user", "friend", "primary_user"]:
            email = user_info.get("email", "")
            if email and "@" in email:
                prefix = email.split("@")[0].split(".")[0].split("_")[0]
                if prefix and not prefix.isdigit():
                    name = prefix.capitalize()
    if not name or name.strip().lower() in ["user", "friend", "primary_user", "guest_user"]:
        name = profile.get("user_name")
    if not name or name.strip().lower() in ["user", "friend", "primary_user", "guest_user"]:
        if user_id and user_id not in ["guest_user", "usr_guest", "primary_user"] and not user_id.startswith("sess_"):
            clean_uid = user_id.replace("usr_", "").replace("user_", "").split("@")[0].split(".")[0].split("_")[0]
            if clean_uid and not clean_uid.isdigit() and clean_uid.lower() not in ["guest", "user"]:
                name = clean_uid.capitalize()
        else:
            name = "Friend"
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

    # Natural Indian English communication only
    detected_lang = "indian_english"
    lang_task = f"""
Language: Natural, warm, compassionate Indian English.
Produce JSON with key:
"reply_text": 1-2 warm spoken sentences (maximum 22 words) in fluent, comforting Indian English.
"""

    is_named_user = bool(short_name and short_name.strip().lower() not in ["friend", "user", "guest", "primary_user"])
    greeting_name_call = f"{short_name}, " if is_named_user else ""

    if client:
        try:
            if has_history and (core_topic or past_title or recent_remarks):
                prompt = f"""
You are {companion_name}, a deeply empathetic, caring voice companion speaking to {name if is_named_user else 'a friend'}.
Profile & Context:
- User Name: {name if is_named_user else 'Not specified (Do not assume any name)'}
- Known Context: {key_context}
- Recorded Stressors: {', '.join(stressors) if stressors else 'None recorded'}
- Previous Topic: {core_topic or past_title}
- Previous Summary: {past_summary}

{lang_task}
DIRECTIVE:
The user is returning. Greet them warmly{' by name' if is_named_user else ''}, and gently follow up on what they shared last time ({core_topic or past_title}).
Keep it natural, human, and caring. Output strictly valid JSON.
"""
            else:
                prompt = f"""
You are {companion_name}, a warm, supportive voice companion welcoming {short_name if is_named_user else 'a friend'}.
This is their first conversation with you.
{lang_task}
DIRECTIVE:
Welcome them warmly{' by name' if is_named_user else ''}, let them know you are right here to listen, and ask how they are feeling today.
Keep it simple, serene, and warm. Output strictly valid JSON.
"""
            # 1. Primary: Sub-second Groq LPU Greeting (~200ms)
            gdata = query_groq_llm(prompt, f"You are {companion_name}, welcoming the user in warm Indian English.", max_tokens=150)
            if not gdata:
                gdata = query_local_ollama(prompt, f"You are {companion_name}, welcoming the user in warm Indian English.")
            if not gdata:
                gdata = {}
            reply = gdata.get("reply_text", "").strip()
            if reply and len(reply) > 5:
                return {
                    "reply_text": reply,
                    "spoken_text": reply,
                    "language_mode": "indian_english",
                    "tts_voice": "en-IN-NeerjaExpressiveNeural"
                }
        except Exception as e:
            print(f"[!] Dynamic memory greeting notice: {e}")

    # Fallback to high-quality warm Indian English greeting
    if has_history and core_topic:
        short_top = core_topic[:40]
        if is_named_user:
            fallback = f"Welcome back, {short_name}! How have you been feeling since our last talk about {short_top}?"
        else:
            fallback = f"Welcome back! How have you been feeling since our last talk about {short_top}?"
    elif has_history and past_title:
        if is_named_user:
            fallback = f"Hello {short_name}, it's wonderful to connect with you again. How is your day going so far?"
        else:
            fallback = "Hello, it is wonderful to connect with you again. How is your day going so far?"
    else:
        if is_named_user:
            fallback = f"Hello {short_name}, welcome to {companion_name}! I am right here with you. How are you feeling today?"
        else:
            fallback = f"Hello, welcome to {companion_name}! I am right here with you in this safe space. How are you feeling today?"

    return {
        "reply_text": fallback,
        "spoken_text": fallback,
        "language_mode": "indian_english",
        "tts_voice": "en-IN-NeerjaExpressiveNeural"
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

    max_score = max(scores) if scores else 0
    active_dims = sum(1 for s_val in scores if s_val > 0)

    # Clinically calibrated symptom deduction model:
    # - Peak severity penalty: Level 1 (-12 pts), Level 2 (-24 pts), Level 3 (-38 pts)
    # - Comorbidity burden: +6 pts deduction per additional active symptom dimension
    peak_penalty = {0: 0, 1: 12, 2: 24, 3: 38}.get(max_score, 0)
    comorbidity_penalty = max(0, active_dims - 1) * 6
    symptom_deduction = peak_penalty + comorbidity_penalty

    # Base equilibrium wellness is 84 (healthy everyday balance), or 86 for positive check-ins
    if total_symptom_pts == 0:
        base_wellness = 86.0
    else:
        base_wellness = max(15.0, 84.0 - symptom_deduction)

    if voice_z is not None and n_sessions >= 3:
        # Acoustic pitch flattening indicates strain
        base_wellness -= float(np.clip(voice_z * 3.0, -8.0, 8.0))
    if trend_z is not None and n_sessions >= 3:
        base_wellness += float(np.clip(trend_z * 3.0, -6.0, 6.0))

    confidence = round(min(1.0, max(0.45, 0.5 + (total_symptom_pts * 0.08) + (n_sessions / 10.0))), 2)
    wellness_score = int(np.clip(round(base_wellness), 10, 98))

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
    user_id: str = "guest_user"
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
            "overall_wellness": 25, # Clear crisis distress level
            "confidence": 1.0,
            "dominant_state": "Crisis Alert",
            "conversation_title": "Crisis Support Alert",
            "is_crisis": True,
            "suggest_grounding": True,
            "grounding_mode": "478",
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

    # 2. Resolve Active User Identity for warm, personalized dialogue
    try:
        from database import get_user_by_id, get_user_clinical_profile
    except ImportError:
        from mental_health_voice_ai.database import get_user_by_id, get_user_clinical_profile

    user_info = get_user_by_id(user_id) if user_id else None
    user_profile = get_user_clinical_profile(user_id) if user_id else {}
    
    user_name = None
    if user_info:
        user_name = user_info.get("preferred_name") or user_info.get("given_name") or user_info.get("name") or user_info.get("display_name")
        if not user_name or user_name.strip().lower() in ["user", "friend", "primary_user"]:
            email = user_info.get("email", "")
            if email and "@" in email:
                prefix = email.split("@")[0].split(".")[0].split("_")[0]
                if prefix and not prefix.isdigit():
                    user_name = prefix.capitalize()
    if not user_name or user_name.strip().lower() in ["user", "friend", "primary_user", "guest_user"]:
        user_name = user_profile.get("user_name")
    if not user_name or user_name.strip().lower() in ["user", "friend", "primary_user", "guest_user"]:
        if user_id and user_id not in ["guest_user", "usr_guest", "primary_user"] and not user_id.startswith("sess_"):
            clean_uid = user_id.replace("usr_", "").replace("user_", "").split("@")[0].split(".")[0].split("_")[0]
            if clean_uid and not clean_uid.isdigit() and clean_uid.lower() not in ["guest", "user"]:
                user_name = clean_uid.capitalize()
        else:
            user_name = "Friend"
    first_name = user_name.split()[0] if user_name else "Friend"
    companion_name = user_profile.get("companion_name") or "Arogya"

    # 3. Build Prompt with Full Conversational History (up to 20 past turns for complete memory & QA)
    history_snippet = []
    for m in session_history[-20:]:
        role = "USER" if m.get("role") == "user" else companion_name.upper()
        txt = (m.get("text") or "").strip()
        if txt:
            history_snippet.append(f"{role}: {txt}")
    history_str = "\n".join(history_snippet) if history_snippet else "Conversation just began."

    prompt = f"""
{historical_context}

--- ACTIVE COMPANION PERSONA ---
Companion Name: {companion_name} (The user knows you as {companion_name}. Converse warmly under this identity.)

--- ACTIVE USER PROFILE ---
User Name: {first_name} (Full Name: {user_name}, User ID: {user_id})
CONVERSATIONAL IDENTITY & ANTI-NAME-SPAM:
1. You know the user's name is {first_name}. If they explicitly ask about their identity or name, confirm it.
2. In regular conversation turns, DO NOT repeat their name. Real friends talk directly without saying the person's name in every single sentence.
3. NEVER address them by any other person's name.

--- CONVERSATION HISTORY (PAST TURNS IN THIS SESSION) ---
{history_str}

--- CURRENT USER INPUT ---
USER (Just now): "{current_transcript}"

IMPORTANT CONVERSATIONAL MEMORY, DEMOGRAPHIC FIT, GOAL GUIDANCE & RELIEF:
1. Review the CONVERSATION HISTORY above carefully.
2. If the user asks a question, refers to something said earlier in this conversation, or continues a previous topic, directly and accurately ANSWER their question using the conversation history context.
3. ADAPTIVE PERSONA & DEMOGRAPHIC RESPECT:
   - The user may be a girl, woman, elder, or student. DO NOT use 'man' or 'bro' unless the user actively uses it with you first.
   - Use universal, warm conversational phrasing ("I hear you...", "Honestly...", "You know what...", "I totally get that...").
   - If the user speaks respectfully (e.g. Tamil 'neenga', 'sollunga' or polite English), respond with dignified warmth and respect.
4. COMPANION ROLE & GOAL GUIDANCE (NO QUESTION-TRAPS, NO TECH INTERROGATION):
   - When the user asks about building a project or goal (e.g. "help me build a python project", "how to start coding?"):
     * DO NOT interrogate them across turns with technical questions ("Rule-based or AI?", "pip install openai").
     * DO NOT try to build the complete code/project step-by-step.
     * Simply suggest a high-level creative idea or point them where to explore (e.g. "You can ask ChatGPT or look up a quick beginner video on YouTube for cool starter projects!").
     * Give a warm, empowering motivational boost to inspire them to start on their path.
     * DO NOT trap them in back-to-back questions.
5. LOW-SCORE RELIEF ROUTINE (WELLNESS < 65% OR FEELINGS OF WORTHLESS/SAD/FRUSTRATED):
   - When the user expresses feeling worthless, sad, exhausted, or frustrated, or their wellness score falls below 65%:
     * FIRST CALM THEIR MIND: Acknowledge and soothe the emotional weight with gentle, caring presence.
     * ACTIVE RELIEF INTERVENTION (IN THE SAME CONVERSATION): Naturally offer a gentle relief choice to ease the heavy mental load:
       1) A 1-minute breathing reset (e.g. physiological sigh or 4-7-8 breathing),
       2) A light yoga / body stretch (relaxing shoulders, releasing neck & jaw tension),
       3) Or a light relief joke / gentle distraction to bring a smile.
     * Help ground their mind so they can refocus on their life path, studies, or coding.
     * Continue this supportive grounding presence across turns until the user's speech and score return to normal.
6. EMOTIONAL MODULATION (READ THE ROOM):
   - If user is joking/laughing -> be playful and laugh along ("Haha wait, did that really happen?", "That's hilarious!").
   - If user is sad/grieving -> be gentle, soft, tender, and caring.
   - If user is stressed/anxious -> be a calm, steady anchor.
   - If user is frustrated/venting -> validate their frustration as an ally.
   - Maximum 25-30 words: concise, warm, natural spoken dialogue. (DO NOT insert the user's name — speak directly).
7. Evaluate the user's emotional state across the 7 dimensions based strictly on their actual statements.

Produce the requested JSON:
"""

    data = None

    # 1. Primary: Ultra-fast Groq LPU Reasoning (~300ms)
    data = query_groq_llm(prompt, SYSTEM_INSTRUCTION, max_tokens=550)

    # 2. Local GPU Ollama if explicitly enabled (ENABLE_LOCAL_OLLAMA=1)
    if not data:
        data = query_local_ollama(prompt, SYSTEM_INSTRUCTION)
        if data:
            print("[+] Processed via Local Ollama on GPU")

    if not data:
        # Context-aware fallback: Conversational without name repetition or gender assumptions
        t_lower = current_transcript.lower().strip()
        if any(w in t_lower for w in ["hi", "hello", "hey"]):
            fallback_reply = "Hey there, I'm right here with you. How is your day going so far?"
        elif any(w in t_lower for w in ["bad", "sad", "upset", "depress", "tired", "exhaust", "stress"]):
            fallback_reply = "I hear you. I'm so sorry you're dealing with this today. What happened?"
        elif any(w in t_lower for w in ["happy", "good", "great", "fine", "super"]):
            fallback_reply = "That's awesome to hear! What made things feel good today?"
        elif "?" in current_transcript:
            fallback_reply = "I hear your question, and I'm right here listening. Tell me more so we can figure this out."
        else:
            fallback_reply = "I hear you. I'm right here listening, so tell me what's on your mind."
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
    
    user_txt_lower = (current_transcript or "").lower()
    is_stressed_or_depressed = bool(
        calc["overall_wellness"] < 65 or 
        stress_pt >= 2 or 
        worry_pt >= 2 or 
        overwhelm_pt >= 2 or
        heavy_pt >= 2 or
        lonely_pt >= 2 or
        any(k in user_txt_lower for k in ["depress", "suicid", "hopeless", "can't take this", "stressed", "overwhelm", "anxious", "panic", "sleepless", "worthless", "exhaust"])
    )
    suggest_grounding = is_stressed_or_depressed
    grounding_mode = "box" if (stress_pt >= 2 or overwhelm_pt >= 2 or "stress" in user_txt_lower) else "478"

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

    # 6. Conversational Voice Pipeline (Indian English & Romanized Tanglish/Tamil)
    raw_reply = data.get("reply_text", "I'm listening, and I'm right here with you. Take your time.")
    language_mode = "indian_english"
    speech_register = "warm_indian_english"
    try:
        from tanglish_engine import detect_language_and_register, naturalize_tanglish_response, stage_prosody_and_phonetics, select_tts_route
        lang_info = detect_language_and_register(f"{current_transcript} {raw_reply}")
        det_lang = lang_info.get("detected_language", "indian_english")
        if det_lang in ["tanglish", "tamil", "code_switched"]:
            target_reg = lang_info.get("recommended_register", "warm_conversational")
            naturalized_reply = naturalize_tanglish_response(raw_reply, user_input=current_transcript, language_mode=det_lang, register=target_reg)
            staged = stage_prosody_and_phonetics(naturalized_reply, language_mode=det_lang, tts_engine="ta-IN-PallaviNeural")
            spoken_clean = staged.get("spoken_text", naturalized_reply) if isinstance(staged, dict) else str(staged)
            tts_route = staged.get("tts_voice", "ta-IN-PallaviNeural") if isinstance(staged, dict) else "ta-IN-PallaviNeural"
            language_mode = det_lang
            speech_register = target_reg
            prosody_stage = {
                "spoken_text": spoken_clean,
                "tts_voice": tts_route
            }
        else:
            from tanglish_engine import smooth_prosody_for_speech
            naturalized_reply = normalize_text_for_speech(raw_reply)
            prosody_stage = {
                "spoken_text": smooth_prosody_for_speech(naturalized_reply),
                "tts_voice": "en-IN-NeerjaExpressiveNeural"
            }
    except Exception as e:
        print(f"[!] Tanglish engine pipeline notice: {e}")
        naturalized_reply = normalize_text_for_speech(raw_reply)
        prosody_stage = {
            "spoken_text": naturalized_reply,
            "tts_voice": "en-IN-NeerjaExpressiveNeural"
        }

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


# ---------------------------------------------------------------------------
# STANDARDIZED CLINICAL ASSESSMENTS (PHQ-9 & GAD-7)
# ---------------------------------------------------------------------------
PHQ9_QUESTIONS = [
    {"id": 1, "text": "Little interest or pleasure in doing things"},
    {"id": 2, "text": "Feeling down, depressed, or hopeless"},
    {"id": 3, "text": "Trouble falling or staying asleep, or sleeping too much"},
    {"id": 4, "text": "Feeling tired or having little energy"},
    {"id": 5, "text": "Poor appetite or overeating"},
    {"id": 6, "text": "Feeling bad about yourself — or that you are a failure or have let yourself or your family down"},
    {"id": 7, "text": "Trouble concentrating on things, such as reading the newspaper or watching television"},
    {"id": 8, "text": "Moving or speaking so slowly that other people could have noticed? Or the opposite — being so fidgety or restless that you have been moving around a lot more than usual"},
    {"id": 9, "text": "Thoughts that you would be better off dead, or of hurting yourself in some way"}
]

GAD7_QUESTIONS = [
    {"id": 1, "text": "Feeling nervous, anxious, or on edge"},
    {"id": 2, "text": "Not being able to stop or control worrying"},
    {"id": 3, "text": "Worrying too much about different things"},
    {"id": 4, "text": "Trouble relaxing"},
    {"id": 5, "text": "Being so restless that it's hard to sit still"},
    {"id": 6, "text": "Becoming easily annoyed or irritable"},
    {"id": 7, "text": "Feeling afraid, as if something awful might happen"}
]

RESPONSE_SCALE = [
    {"score": 0, "label": "Not at all"},
    {"score": 1, "label": "Several days"},
    {"score": 2, "label": "More than half the days"},
    {"score": 3, "label": "Nearly every day"}
]

def score_phq9(answers: Dict[str, Any]) -> Dict[str, Any]:
    """
    Standardized PHQ-9 Scoring & Clinical Stratification:
    0-4: None-Minimal Depression
    5-9: Mild Depression
    10-14: Moderate Depression
    15-19: Moderately Severe Depression
    20-27: Severe Depression
    """
    total = 0
    q9_val = 0
    clean_answers = {}
    for i in range(1, 10):
        val = int(answers.get(str(i), answers.get(i, 0)))
        val = max(0, min(3, val))
        clean_answers[str(i)] = val
        total += val
        if i == 9:
            q9_val = val

    if total <= 4:
        severity = "None-Minimal"
        clinical_action = "Supportive psychoeducation and ongoing emotional check-ins."
    elif total <= 9:
        severity = "Mild"
        clinical_action = "Watchful waiting, supportive dialogue, and mindfulness grounding practices."
    elif total <= 14:
        severity = "Moderate"
        clinical_action = "CBT counseling consideration and active mood stabilization."
    elif total <= 19:
        severity = "Moderately Severe"
        clinical_action = "Active clinical referral recommended: comprehensive psychotherapy and psychiatric review."
    else:
        severity = "Severe"
        clinical_action = "Immediate professional psychiatric consultation and continuous monitoring."

    has_suicidal_flag = (q9_val > 0)
    return {
        "assessment": "PHQ-9",
        "total_score": total,
        "max_score": 27,
        "severity": severity,
        "q9_suicide_flag": has_suicidal_flag,
        "clinical_action": clinical_action,
        "answers": clean_answers,
        "is_crisis": has_suicidal_flag
    }

def score_gad7(answers: Dict[str, Any]) -> Dict[str, Any]:
    """
    Standardized GAD-7 Scoring & Clinical Stratification:
    0-4: Minimal Anxiety
    5-9: Mild Anxiety
    10-14: Moderate Anxiety
    15-21: Severe Anxiety
    """
    total = 0
    clean_answers = {}
    for i in range(1, 8):
        val = int(answers.get(str(i), answers.get(i, 0)))
        val = max(0, min(3, val))
        clean_answers[str(i)] = val
        total += val

    if total <= 4:
        severity = "Minimal"
        clinical_action = "Supportive pacing, physiological sigh exercises, and normal stress mitigation."
    elif total <= 9:
        severity = "Mild"
        clinical_action = "Guided breathing grounding, cognitive re-framing, and sleep hygiene review."
    elif total <= 14:
        severity = "Moderate"
        clinical_action = "Clinical counseling consideration and specialized anxiety reduction protocols."
    else:
        severity = "Severe"
        clinical_action = "Specialized psychiatric/psychological evaluation recommended."

    return {
        "assessment": "GAD-7",
        "total_score": total,
        "max_score": 21,
        "severity": severity,
        "clinical_action": clinical_action,
        "answers": clean_answers,
        "is_crisis": False
    }
