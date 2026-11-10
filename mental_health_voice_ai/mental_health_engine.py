"""
Arogya Master Engine Facade & Multimodal Conversational Orchestrator.
Decoupled into modular services:
- services.llm_router: Sub-second Groq LPU routing, Gemini Flash Lite backup & local Ollama
- services.clinical_scoring: Dual-layer crisis safety, deterministic scoring, PHQ-9 & GAD-7
- prompts.companion_persona: Real human friendship, adaptive slang mirroring & tone attunement
"""
import os
import sys
import time
import re
import json
import numpy as np
from typing import Dict, Any, Tuple, Optional, List
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

# Import decoupled service modules
from services.llm_router import (
    get_groq_client,
    query_groq_llm,
    query_local_ollama,
    query_gemini_backup
)
from services.clinical_scoring import (
    check_crisis_risk,
    compute_deterministic_wellness,
    generate_quick_session_title,
    generate_holistic_friendly_summary,
    PHQ9_QUESTIONS,
    GAD7_QUESTIONS,
    RESPONSE_SCALE,
    score_phq9,
    score_gad7
)
from prompts.companion_persona import (
    SYSTEM_INSTRUCTION,
    FAST_VOICE_SYSTEM_INSTRUCTION,
    EMOTION_12_TAGS,
    EMOTION_FACE_MAP,
    normalize_text_for_speech,
    classify_user_emotion_from_voice_tone,
    generate_memory_greeting,
    generate_proactive_silence_opener
)


# ---------------------------------------------------------------------------
# DSP ACOUSTIC EXTRACTION (Lightweight Jitter, Shimmer, Pitch & Prosody)
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
# MASTER MULTIMODAL ORCHESTRATOR: ANALYZE AND RESPOND
# ---------------------------------------------------------------------------
def analyze_and_respond(
    current_transcript: str,
    acoustic_features: Dict[str, Any],
    session_history: list,
    historical_context: str,
    voice_z: Optional[float] = None,
    trend_z: Optional[float] = None,
    n_sessions: int = 1,
    user_id: str = "guest_user",
    fast_voice_mode: bool = False
) -> Dict[str, Any]:
    """
    Unified analysis pipeline:
    1. Checks acute crisis flag (independent safety triage).
    2. Calls Groq LPU (or Gemini Flash Lite backup) for sub-second quote-backed symptom evaluation.
    3. Computes overall wellness deterministically in Python code.
    4. Evaluates vocal biomarkers and emotion face tags for co-regulation.
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
        return {
            "reply_text": normalized_crisis_reply,
            "overall_wellness": 25,
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

    # 2. Resolve Active User Identity
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
    has_real_name = bool(user_name and user_name.strip().lower() not in ["friend", "user", "guest", "guest_user", "primary_user"])
    first_name = user_name.split()[0] if has_real_name else None
    companion_name = user_profile.get("companion_name") or "Arogya"

    # Detect language of current input
    has_tamil_script = bool(re.search(r'[\u0B80-\u0BFF]', current_transcript))
    is_tanglish_marker = False
    try:
        from tanglish_engine import detect_language_and_register
        lang_det = detect_language_and_register(current_transcript)
        if lang_det.get("detected_language") in ["tanglish", "tamil", "code_switched"]:
            is_tanglish_marker = True
    except Exception:
        pass

    if has_tamil_script:
        lang_directive = "LANGUAGE DIRECTIVE: The user communicated in Tamil script. Respond directly in natural, spoken colloquial Tamil script (e.g. அப்படி எல்லாம் பேசாதீங்க, நீங்க ஒண்ணும் worthless இல்ல. என்ன ஆச்சுன்னு சொல்லுங்க). Use spoken Tamil, never bookish or archaic Tamil."
    elif is_tanglish_marker:
        lang_directive = "LANGUAGE DIRECTIVE: The user communicated in Romanized Tanglish. Respond in natural Romanized Tanglish (e.g. Apdi laam pesadheenga, worthless laam illa. Enna aachu nu sollunga) using English Latin alphabet only, with ZERO Tamil Unicode characters so the neural voice reads it smoothly."
    else:
        lang_directive = "LANGUAGE DIRECTIVE: The user communicated in English. Respond in warm, natural conversational Indian English."

    # 3. Build Prompt with Full Conversational History
    history_snippet = []
    for m in session_history[-20:]:
        role = "USER" if m.get("role") == "user" else companion_name.upper()
        txt = (m.get("text") or "").strip()
        if txt:
            history_snippet.append(f"{role}: {txt}")
    history_str = "\n".join(history_snippet) if history_snippet else "Conversation just began."

    user_id_line = f"User Name: {first_name} (Full Name: {user_name}, User ID: {user_id})" if has_real_name else "User Name: Unspecified (Talk directly using 'you'. NEVER call them 'Friend' or use fake names)"

    prompt = f"""
{historical_context}

--- ACTIVE COMPANION PERSONA ---
Companion Name: {companion_name} (The user knows you as {companion_name}. Converse warmly under this identity.)

--- ACTIVE USER PROFILE ---
{user_id_line}
CONVERSATIONAL IDENTITY & ANTI-NAME-SPAM:
1. {"You know the user's name is " + first_name + ". If they explicitly ask about their identity, confirm it." if has_real_name else "The user's name is unspecified. NEVER address the user as 'Friend' or use generic filler names."}
2. In regular conversation turns, DO NOT repeat their name. Real friends talk directly without saying the person's name in every single sentence.
3. NEVER address them by any other person's name.

--- CONVERSATION HISTORY (PAST TURNS IN THIS SESSION) ---
{history_str}

--- CURRENT USER INPUT ---
USER (Just now): "{current_transcript}"

IMPORTANT CONVERSATIONAL MEMORY, DEMOGRAPHIC FIT, GOAL GUIDANCE & ZERO-CLICHÉ RULES:
1. Review the CONVERSATION HISTORY above carefully.
2. If the user asks a question, refers to something said earlier in this conversation, or continues a previous topic, directly and accurately ANSWER their question using the conversation history context.
3. {lang_directive}
4. ZERO HARDCODED / HALLUCINATED ASSUMPTIONS:
   - DO NOT make up details about their life (e.g. "in our batch", "your manager", "your exams", "your team", "your partner") UNLESS the user explicitly stated it in their message or profile history!
   - Ground your reply strictly in what was actually stated.
5. REAL COMMON HUMAN SOLIDARITY & ZERO AI CLICHÉS:
   - STRICT BAN: NEVER say "I hear you", "I hear that", "I hear what you're saying", "Grab a glass of water, take a breath", "weighing on you", "capable person", "you have so much to offer", "heavy feelings", "I acknowledge your struggle".
   - ELIMINATE QUESTION FATIGUE: DO NOT end every turn with a question! Real friends speak in natural statements, reactions, opinions, banter, and comfort. DO NOT repeatedly ask about their day ("how was your day", "what's on your mind"). When discussing a topic, react naturally to that context instead of interrogating.
   - If user is down or self-critical: Push back immediately with loyal friendly solidarity ("Hey, stop right there. Don't say that about yourself—you are definitely not worthless.").
6. ADAPTIVE PERSONA & NATURAL SLANG MIRRORING:
   - Talk like a trusted friend, buddy, or relative, not a stiff bot or therapist.
   - If the user uses casual slang ("yeah man", "buddy", "bro", "machan", "dude"), reciprocate naturally ("Haha yeah man!", "Anytime buddy, I've got your back", "Totally bro").
   - Use warm, natural phrasing ("Honestly...", "You know what...", "I totally get that...", "Look..."). NEVER use "I hear you".
   - If the user speaks respectfully (e.g. Tamil 'neenga', 'sollunga' or polite English), respond with dignified warmth and respect.
7. COMPANION ROLE & GOAL GUIDANCE (NO QUESTION-TRAPS, NO TECH INTERROGATION):
   - When the user asks about building a project or goal (e.g. "help me build a python project", "how to start coding?"):
     * DO NOT interrogate them across turns with technical questions ("Rule-based or AI?", "pip install openai").
     * DO NOT try to build the complete code/project step-by-step.
     * Simply suggest a high-level creative idea or point them where to explore (e.g. "You can ask ChatGPT or look up a quick beginner video on YouTube for cool starter projects!").
     * Give a warm, empowering motivational boost to inspire them to start on their path.
     * DO NOT trap them in back-to-back questions.
8. EMOTIONAL MODULATION (READ THE ROOM):
   - If user is joking/laughing -> be playful and laugh along ("Haha wait, did that really happen?", "That's hilarious!").
   - If user is sad/grieving -> be gentle, soft, tender, and caring.
   - If user is stressed/anxious -> be a calm, steady anchor.
   - If user is frustrated/venting -> validate their frustration as an ally.
   - Maximum 25-30 words: concise, warm, natural spoken dialogue. (DO NOT insert the user's name — speak directly).
9. Evaluate the user's emotional state across the 7 dimensions based strictly on their actual statements.

Produce the requested JSON:
"""

    data = None
    target_instruction = FAST_VOICE_SYSTEM_INSTRUCTION if fast_voice_mode else SYSTEM_INSTRUCTION
    target_tokens = 160 if fast_voice_mode else 650

    # 1. Primary: Ultra-fast Groq LPU Reasoning (~300-500ms via Qwen/Llama)
    data = query_groq_llm(prompt, target_instruction, max_tokens=target_tokens)

    # 2. Local GPU Ollama if explicitly enabled (ENABLE_LOCAL_OLLAMA=1)
    if not data:
        data = query_local_ollama(prompt, target_instruction)
        if data:
            print("[+] Processed via Local Ollama on GPU")

    # 3. Cloud Secondary LLM Backup (Gemini Flash Lite via google-genai)
    if not data:
        data = query_gemini_backup(prompt, target_instruction, max_tokens=target_tokens)

    if not data:
        # Context-aware fallback: Conversational without name repetition
        t_lower = current_transcript.lower().strip()
        has_tam = bool(re.search(r'[\u0B80-\u0BFF]', current_transcript))
        user_used_bro = any(w in t_lower.split() for w in ["bro", "man", "machan", "dude"])
        user_polite_tamil = any(w in t_lower for w in ["neenga", "sollunga", "ammal", "vanakkam", "nandri"])

        if has_tam:
            if any(w in t_lower for w in ["worthless", "kashtam", "valikidhu", "kavala"]):
                fallback_reply = "அப்படி எல்லாம் பேசாதீங்க, நீங்க ஒண்ணும் worthless இல்ல. என்ன ஆச்சுன்னு சொல்லுங்க, நான் கேக்குறேன்."
            elif any(w in t_lower for w in ["bayama", "payam", "anxiety", "tension"]):
                fallback_reply = "நான் உங்க கூட இருக்கேன். பயப்படாதீங்க, என்ன செய்யலாம் என்று நாம சேர்ந்து யோசிப்போம்."
            else:
                fallback_reply = "வணக்கம், என்ன ஆச்சுன்னு சொல்லுங்க, நான் உங்க கூட இருக்கேன்."
        elif user_polite_tamil:
            fallback_reply = "Tension aagadheenga, enna aachu nu sollunga, naan unga kooda irukken."
        elif any(w in t_lower for w in ["tanglish", "romba", "irukku", "panren", "aachu", "therila"]):
            if user_used_bro:
                fallback_reply = "Worry pannadheenga bro. Enna aachu nu sollunga, namma paathukalam."
            else:
                fallback_reply = "Tension aagadheenga, enna aachu nu sollunga, naan unga kooda irukken."
        elif any(w in t_lower for w in ["build", "chatbot", "project", "learn", "roadmap", "prepare for", "internship"]):
            fallback_reply = "Start with a simple prototype or check a beginner walkthrough on YouTube to get moving. You've got this!"
        elif any(w in t_lower for w in ["hi", "hello", "hey"]):
            fallback_reply = "Hey there, how's your day going so far?"
        elif any(w in t_lower for w in ["worthless", "failure", "useless", "good for nothing"]):
            fallback_reply = "Hey, stop right there. Don't say that about yourself—you are definitely not worthless. Talk to me, what happened today?"
        elif any(w in t_lower for w in ["bad", "sad", "upset", "depress", "tired", "exhaust", "stress", "panic"]):
            fallback_reply = "Honestly, that sounds really rough. Talk to me, what happened?"
        elif any(w in t_lower for w in ["happy", "good", "great", "fine", "super", "haha", "joke", "won"]):
            fallback_reply = "That's awesome! Glad to hear things are feeling good."
        elif "?" in current_transcript:
            fallback_reply = "That's a good question. Let's figure this out together."
        else:
            fallback_reply = "I'm right here. Tell me what's going on."
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
    if fast_voice_mode:
        user_w = data.get("overall_wellness", 75)
        user_state = data.get("dominant_state", "Calm")
        calc = {
            "overall_wellness": user_w,
            "confidence": 1.0,
            "dominant_state": user_state,
            "dominant_emotion": user_state.lower(),
            "total_points": 0,
            "max_points": 21,
            "reasons": []
        }
        evidence = data.get("evidence", {})
    else:
        evidence = data.get("evidence", {})
        calc = compute_deterministic_wellness(
            evidence_dict=evidence,
            voice_z=voice_z,
            trend_z=trend_z,
            n_sessions=n_sessions
        )

    # 4. Somatic Grounding Detection
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
    if profile_updates and isinstance(profile_updates, dict) and user_id and user_id not in ["guest_user", "usr_guest"]:
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

    # 6. Conversational Voice Pipeline
    raw_reply = data.get("reply_text", "I'm listening, and I'm right here with you. Take your time.")

    # Sanitize accidental AI clichés & HR therapy phrases
    # STRICT BAN ON "I hear you" / "I hear that" / "I hear how..."
    raw_reply = re.sub(r'(?i)\bi hear you,?\s*', "Honestly, ", raw_reply)
    raw_reply = re.sub(r'(?i)\bi hear that,?\s*', "That definitely sounds ", raw_reply)
    raw_reply = re.sub(r"(?i)\bi hear what you(?:'?re| are) saying,?\s*", "I get it, ", raw_reply)
    raw_reply = re.sub(r'(?i)\bi hear how (?:hard|difficult|rough|exhausting|heavy)\b', "That sounds really rough", raw_reply)
    raw_reply = re.sub(r'(?i)\bi hear\b', "I see", raw_reply)
    raw_reply = re.sub(r'(?i)\bwhat(?:\'?s| is) weighing on you\b', "what's been going on", raw_reply)
    raw_reply = re.sub(r'(?i)\bweighing on you\b', "bothering you", raw_reply)
    raw_reply = re.sub(r'(?i)\bgrab a glass of water,?\s*(?:and\s*)?take a (?:slow )?breath\b', "take a moment for yourself", raw_reply)
    raw_reply = re.sub(r'(?i)\bgrab some water and take a breath\b', "take a moment", raw_reply)
    raw_reply = re.sub(r'(?i)\bcapable person\b', "strong person", raw_reply)
    raw_reply = re.sub(r'(?i)\byou have so much to offer\b', "you have so much going for you", raw_reply)
    raw_reply = re.sub(r'(?i)\bheavy feelings\b', "rough time", raw_reply)
    raw_reply = re.sub(r'(?i)\bwould you like to try a (?:quick )?breathing reset\b', "let's take a calm pause together", raw_reply)
    raw_reply = re.sub(r'(?i)\bin our batch\b', "in college", raw_reply)

    language_mode = "indian_english"
    speech_register = "warm_indian_english"
    try:
        from tanglish_engine import detect_language_and_register, naturalize_tanglish_response, stage_prosody_and_phonetics, select_tts_route
        lang_info = detect_language_and_register(f"{current_transcript} {raw_reply}")
        det_lang = lang_info.get("detected_language", "indian_english")
        has_tamil = bool(re.search(r'[\u0B80-\u0BFF]', raw_reply) or re.search(r'[\u0B80-\u0BFF]', current_transcript))

        if has_tamil or det_lang == "tamil":
            target_reg = lang_info.get("recommended_register", "warm_conversational")
            staged = stage_prosody_and_phonetics(raw_reply, language_mode="tamil", tts_engine="ta-IN-PallaviNeural")
            spoken_clean = staged.get("spoken_text", raw_reply) if isinstance(staged, dict) else str(staged)
            tts_route = "ta-IN-PallaviNeural"
            naturalized_reply = raw_reply
            language_mode = "tamil"
            speech_register = target_reg
            prosody_stage = {
                "spoken_text": spoken_clean,
                "tts_voice": tts_route
            }
        elif det_lang in ["tanglish", "code_switched"]:
            target_reg = lang_info.get("recommended_register", "warm_conversational")
            naturalized_reply = naturalize_tanglish_response(raw_reply, user_input=current_transcript, language_mode=det_lang, register=target_reg)
            staged = stage_prosody_and_phonetics(naturalized_reply, language_mode=det_lang, tts_engine="en-IN-NeerjaExpressiveNeural")
            spoken_clean = staged.get("spoken_text", naturalized_reply) if isinstance(staged, dict) else str(staged)
            tts_route = "en-IN-NeerjaExpressiveNeural"
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
        "reply_text": naturalized_reply,
        "spoken_text": prosody_stage.get("spoken_text"),
        "language_mode": language_mode,
        "speech_register": speech_register,
        "tts_voice": prosody_stage.get("tts_voice"),
        "conversation_title": conversation_title,
        "overall_wellness": calc["overall_wellness"],
        "confidence": calc["confidence"],
        "dominant_state": data.get("dominant_state", "Reflective"),
        "user_emotion": emotion_info["user_emotion"],
        "listening_face": emotion_info["listening_face"],
        "speaking_face": emotion_info["speaking_face"],
        "reasons": calc.get("reasons", []),
        "total_points": calc.get("total_points", 0),
        "max_points": calc.get("max_points", 21),
        "observed_resilience": data.get("observed_resilience", "Sharing feelings openly"),
        "summary_snippet": data.get("summary_snippet", ""),
        "acoustic_features": acoustic_features,
        "suggest_grounding": suggest_grounding,
        "grounding_mode": grounding_mode,
        "is_crisis": False
    }


# Re-export all functions & constants for 100% backward compatibility
__all__ = [
    "BASE_DIR",
    "check_crisis_risk",
    "normalize_text_for_speech",
    "extract_acoustic_features",
    "EMOTION_12_TAGS",
    "EMOTION_FACE_MAP",
    "classify_user_emotion_from_voice_tone",
    "SYSTEM_INSTRUCTION",
    "get_groq_client",
    "query_groq_llm",
    "query_local_ollama",
    "query_gemini_backup",
    "generate_memory_greeting",
    "compute_deterministic_wellness",
    "generate_quick_session_title",
    "analyze_and_respond",
    "PHQ9_QUESTIONS",
    "GAD7_QUESTIONS",
    "RESPONSE_SCALE",
    "score_phq9",
    "score_gad7",
    "generate_proactive_silence_opener",
    "generate_holistic_friendly_summary"
]
