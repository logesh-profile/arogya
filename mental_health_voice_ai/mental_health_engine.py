import os
import sys
import re
import json
import numpy as np
from typing import Dict, Any, Tuple, Optional, List
import soundfile as sf
import librosa
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
    """
    try:
        y, sr = librosa.load(audio_path, sr=16000)
        duration = float(librosa.get_duration(y=y, sr=sr))
        if duration < 0.6:
            return {
                "duration": round(duration, 2),
                "pitch_semitone_std": None,
                "pause_ratio": 0.0,
                "is_valid_speech": False,
                "note": "Audio sample too brief for stable pitch estimation"
            }

        # Probabilistic YIN (pyin) for robust fundamental frequency tracking
        f0, voiced_flag, _ = librosa.pyin(y, fmin=75, fmax=400, sr=sr)
        valid_f0 = f0[voiced_flag & ~np.isnan(f0)]

        # Check voiced frame threshold (at least ~0.35s of voiced speech)
        min_voiced_frames = int((sr / 512) * 3)
        if len(valid_f0) < min_voiced_frames:
            semitone_std = None
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
            "pause_ratio": round(pause_ratio, 2),
            "is_valid_speech": semitone_std is not None,
            "note": note
        }
    except Exception as e:
        print(f"[!] Acoustic extraction error: {e}")
        return {
            "duration": 0.0,
            "pitch_semitone_std": None,
            "pause_ratio": 0.0,
            "is_valid_speech": False,
            "note": "Extraction error"
        }


# ---------------------------------------------------------------------------
# 4. EVIDENCE-GROUNDED SYMPTOM SCORING & CLINICAL CONTINUITY
# ---------------------------------------------------------------------------
SYSTEM_INSTRUCTION = """
You are Arogya, a deeply empathetic, reflective voice companion.
You converse with the user through spoken audio. Your core principles:

1. BILINGUAL CONVERSATION (INDIAN ENGLISH & TANGLISH):
   - Flawlessly understand Indian English and Tanglish (Tamil in Latin script, e.g. 'inaiku ennode day epdi irundhuchi', 'romba tension', 'konjam tired').
   - If the user speaks Tanglish, reply warmly in natural conversational Tanglish or Indian English.
   - Speak like an attentive, wise friend. Never give generic boilerplate.

2. LONG-TERM CLINICAL CONTINUITY & STRICT MEMORY GROUNDING:
   - USER IDENTITY: Refer to the user by their preferred name provided in the session profile context.
   - STRICT EMPIRICAL CONTINUITY: You have access to the user's authentic clinical profile and past conversational memory in the prompt. ONLY reference stressors, challenges, or coping strategies that appear in their actual history.
   - ZERO UNRELATED HALLUCINATIONS: If the user has no recorded history or has not explicitly mentioned exams, jobs, or specific life events, DO NOT invent or assume them. Greet and converse with new users with a warm, open, supportive presence.
   - If the user asks "do you remember me?", "what is my name?", or references past sessions, confirm and answer accurately using their profile and past session history.

3. REAL HUMAN CONVERSATIONAL DEPTH & SPOKEN FLOW:
   - Avoid curt, clipped 1-sentence answers. In a real conversation, when a friend shares lots of thoughts or feelings, speak thoroughly and warmly to completion (typically 3 to 5 articulate, compassionate, and meaningful sentences).
   - Reflect back what they expressed, validate their emotions, offer caring perspective, connect with their ongoing journey, and keep the dialogue alive with a natural conversational flow.

4. GROUNDED EVIDENCE SCORING (STRICT EMPIRICAL CRITERIA):
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
   NO QUOTE = NO POINTS. DO NOT GUESS OR INVENT EVIDENCE.

You MUST output strictly valid JSON matching this exact structure:
{
  "reply_text": "Spoken reply (thorough, comprehensive, and warm 3-5 sentences in natural English or Tanglish, validating their feelings, addressing everything they said, and speaking to the end)",
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
def generate_memory_greeting(session_id: Optional[str] = None, user_id: str = "primary_user") -> str:
    """
    Generates a deeply personal, memory-anchored spoken greeting that proactively recalls
    the user's name, their long-term clinical profile (stressors, deadlines, sleep schedule),
    and previous session reflections across days.
    """
    from database import get_recent_session_memory_anchor, get_user_clinical_profile

    anchor = get_recent_session_memory_anchor(user_id=user_id)
    profile = anchor.get("profile") or get_user_clinical_profile(user_id)
    name = profile.get("user_name") or "Friend"
    short_name = name.split()[0] if name else "Friend"
    key_context = profile.get("key_context", "Member seeking conversational companionship and emotional support")
    stressors = profile.get("recurring_stressors", [])
    stressor_sample = stressors[0] if stressors else ""

    has_history = anchor.get("has_history", False)
    past_title = anchor.get("title", "")
    past_summary = anchor.get("summary", "")
    recent_remarks = anchor.get("recent_remarks", [])

    if client:
        try:
            if has_history and (past_title or past_summary or recent_remarks):
                prompt = f"""
You are Arogya, a deeply empathetic, caring voice companion speaking to your friend {short_name} ({name}).
Profile & Real Context:
- User: {name} (Address them as {short_name})
- Known Context: {key_context}
- Real Recorded Stressors: {', '.join(stressors) if stressors else 'None recorded yet'}
- Past Session Title: {past_title}
- Past Session Summary: {past_summary}
- Recent remarks spoken by user: {' | '.join(recent_remarks) if recent_remarks else 'None recorded'}

Task: Generate a genuine, caring welcome-back greeting in 1-2 natural spoken sentences (maximum 28 words).
Naturally check back in based STRICTLY on what they actually shared in their previous session.
DO NOT invent exams, job interviews, or problems they never mentioned.
Do NOT sound robotic or formal. Speak directly as spoken text with no markdown, asterisks, or quotes.
"""
            else:
                prompt = f"""
You are Arogya, a warm, friendly voice companion welcoming {short_name}.
This is their very first conversation with you.
Task: Generate a warm, reassuring first-welcome greeting in 1-2 natural spoken sentences (maximum 22 words).
Welcome {short_name} warmly, mention that you're here to listen and keep them company, and gently ask how they are feeling today.
DO NOT assume or invent exams, deadlines, or life situations. Keep it simple, welcoming, and open-ended.
Do NOT sound robotic. Speak directly as spoken text with no markdown, asterisks, or quotes.
"""
            resp = client.models.generate_content(
                model="gemini-3.5-flash-lite",
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0.3,
                )
            )
            raw = (resp.text or "").strip().strip('"\'')
            if raw and len(raw) > 10:
                return normalize_text_for_speech(raw)
        except Exception as e:
            print(f"[!] Dynamic memory greeting error: {e}")

    # Fallback to high-quality personalized memory greeting (Zero hallucination)
    if has_history and past_title:
        fallback = f"Hello {short_name}! It is wonderful to hear from you again. How have you been feeling since our last conversation about {past_title.lower()}?"
    elif has_history and stressor_sample:
        fallback = f"Hello {short_name}! It is wonderful to hear from you again. How have you been feeling since we last spoke?"
    else:
        fallback = f"Hello {short_name}, welcome to Arogya! I am here to listen, support, and keep you company whenever you need a friendly space. How are you feeling today?"
    return normalize_text_for_speech(fallback)



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

    # 2. Build Prompt (Pure Transcript + Conversational Context, NO contaminated voice heuristics)
    history_snippet = []
    for m in session_history[-4:]:
        history_snippet.append(f"{m['role'].upper()}: {m['text']}")
    history_str = "\n".join(history_snippet) if history_snippet else "Conversation just began."

    prompt = f"""
{historical_context}

--- CURRENT DIALOGUE ---
{history_str}
USER (Just now): "{current_transcript}"

Evaluate the emotional statement based strictly on the user's explicit words.
Produce the requested JSON:
"""

    try:
        # LLM inference with gemini-3.5-flash-lite at temperature=0.0 for sub-second, zero-hallucination response
        response = client.models.generate_content(
            model="gemini-3.5-flash-lite",
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_INSTRUCTION,
                response_mime_type="application/json",
                temperature=0.0,
            )
        )
        data = json.loads(response.text)
    except Exception as e:
        print(f"[!] Primary model notice: {e}, attempting fallback...")
        try:
            response = client.models.generate_content(
                model="gemini-flash-latest",
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM_INSTRUCTION,
                    response_mime_type="application/json",
                    temperature=0.0,
                )
            )
            data = json.loads(response.text)
        except Exception as e2:
            print(f"[!] Fallback LLM error: {e2}")
            data = {
                "reply_text": "I hear you, and I am right here with you. Take a soft breath. Tell me what has been on your mind.",
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
            from database import update_user_clinical_profile
            update_user_clinical_profile(
                user_id=user_id,
                user_name=profile_updates.get("user_name"),
                key_context=profile_updates.get("key_context"),
                new_stressor=profile_updates.get("new_stressor"),
                new_coping=profile_updates.get("effective_coping")
            )
        except Exception as pe:
            print(f"[!] Clinical profile auto-update notice: {pe}")

    # 6. Spoken text normalization
    raw_reply = data.get("reply_text", "I'm listening and I'm right here with you.")
    spoken_reply = normalize_text_for_speech(raw_reply)

    # 7. Extract conversation title
    llm_title = (data.get("conversation_title") or "").strip().strip('"\'')
    if llm_title and len(llm_title.split()) <= 5:
        conversation_title = llm_title
    else:
        conversation_title = generate_quick_session_title(current_transcript)

    return {
        "reply_text": spoken_reply,
        "conversation_title": conversation_title,
        "overall_wellness": calc["overall_wellness"],
        "confidence": calc["confidence"],
        "dominant_state": data.get("dominant_state", "Reflective"),
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
