"""
Arogya Conversational Companion Persona, Speech Normalization & Tone Attunement.
Designed for genuine human friendship, slang mirroring, and anti-question fatigue.
"""
import os
import sys
import re
import json
from typing import Dict, Any, Optional, List

# ---------------------------------------------------------------------------
# 1. TEXT NORMALIZATION (For Crystal-Clear F5-TTS / Edge-TTS Pronunciation)
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
    cleaned = re.sub(r'\s*[—–]\s*', ', ', cleaned)
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
# 2. VOICE TONE-FIRST EMOTION & EXPRESSION CLASSIFIER (12-TAG CO-REGULATION)
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
    """
    is_valid = acoustic_features.get("is_valid_speech", False)
    semitone_std = acoustic_features.get("pitch_semitone_std")
    pause_ratio = acoustic_features.get("pause_ratio", 0.0)
    rms = acoustic_features.get("rms_energy", 0.0)
    duration = acoustic_features.get("duration", 0.0)
    median_f0 = acoustic_features.get("median_f0")
    t_lower = (transcript or "").lower()

    # Determine if voice audio is valid speech (energy >= 0.015, duration >= 0.5s, is_valid_speech == True)
    has_audio_tone = bool(duration >= 0.5 and is_valid and rms >= 0.015)

    if has_audio_tone:
        # === ACOUSTIC BIOMARKER GROUND TRUTH (TONE-FIRST DECISION MATRIX) ===
        if rms < 0.020 and pause_ratio > 0.32:
            detected_emotion = "sleepy"
        elif (semitone_std is not None and semitone_std < 1.35) and (rms < 0.035 or pause_ratio > 0.20):
            detected_emotion = "sad"
        elif rms < 0.024 and pause_ratio > 0.22:
            detected_emotion = "sad"
        elif semitone_std is not None and semitone_std > 2.85:
            detected_emotion = "concerned"
        elif semitone_std is not None and semitone_std > 2.50 and median_f0 and median_f0 > 240:
            detected_emotion = "concerned"
        elif rms > 0.062 and ((semitone_std and semitone_std > 2.2) or pause_ratio < 0.16):
            detected_emotion = "concerned"
        elif (semitone_std is not None and semitone_std > 2.70) and pause_ratio > 0.25:
            detected_emotion = "surprised"
        elif (semitone_std is not None and semitone_std > 2.55) and rms > 0.048:
            detected_emotion = "excited"
        elif rms >= 0.042 and semitone_std is not None and (1.9 <= semitone_std <= 2.5) and pause_ratio < 0.22:
            detected_emotion = "proud"
        elif semitone_std is not None and (1.8 <= semitone_std <= 2.6) and rms >= 0.032:
            detected_emotion = "happy"
        elif pause_ratio > 0.28 and semitone_std is not None and (1.4 <= semitone_std <= 2.4):
            detected_emotion = "confused"
        elif pause_ratio > 0.30:
            detected_emotion = "thinking"
        elif (0.018 <= rms <= 0.028) and semitone_std is not None and (1.6 <= semitone_std <= 2.2) and any(w in t_lower for w in ["love", "care", "dear", "thank", "thanks"]):
            detected_emotion = "caring"
        else:
            detected_emotion = "calm"
    else:
        # Fallback to transcript keywords ONLY when voice audio is missing
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

    canonical_emotion = detected_emotion if detected_emotion in EMOTION_12_TAGS else "calm"
    face_map = EMOTION_FACE_MAP.get(canonical_emotion, {"listen": "thinking", "speak": "happy"})

    return {
        "user_emotion": canonical_emotion,
        "listening_face": face_map["listen"],
        "speaking_face": face_map["speak"]
    }


# ---------------------------------------------------------------------------
# 3. SYSTEM INSTRUCTION (Natural Friend Persona & Anti-Interrogation Grounding)
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
       "Honestly...", "You know what...", "I totally get that...", "Look...", "Wait...", "That makes total sense..."
     * STRICT BAN: NEVER say "I hear you", "I hear that", "I hear what you're saying", or "I hear how...". This is a canned AI therapist cliché.
     * Example: "I totally get that, placement stress is brutal. You've been carrying a lot today."
     * Example (Tanglish): "Romba tension aagatheenga, placement pressure pathi yosichu sleep spoil pannadheenga. Relax pannunga, namma step-by-step paathukalaam."
   - Natural Conversational Flow: Keep sentences short and natural. Use standard periods and commas in their natural grammatical places. Do not write awkward run-on sentences.
   - Brevity & Voice-First Turn-Taking: Keep spoken replies under 25-30 words.
     * ZERO COMPULSIVE TURN-ENDING QUESTIONS: Real friends do NOT interrogate each other at the end of every sentence.
     * Speak primarily in natural statements, opinions, banter, solidarity, and reactions. Only ask a question occasionally when you genuinely need to know something.
   - STRICT ANTI-NAME-SPAM RULE:
     * NEVER repeat the user's name in every chat turn! In real life, friends do NOT say your name in every sentence.
     * Use their name ONLY in the first greeting. Once in active dialogue, do NOT insert their name into your replies. Talk directly using "you" or direct conversational speech.

2. ADAPTIVE PERSONA & NATURAL SLANG MIRRORING (REAL FRIEND / CLOSED ONES VIBE):
   - TALK LIKE A REAL TRUSTED FRIEND, RELATIVE, OR CONFIDANT:
     * The user should feel like they are talking to an authentic, loyal friend, buddy, or close one—NEVER a stiff customer-service bot, therapist, or HR counselor.
   - NATURAL SLANG & VIBE MIRRORING:
     * If the user speaks casually or uses friendly slang like "yeah man", "nice man!", "thanks buddy", "bro", "machan", "dude", or invites casual familiarity, RECIPROCATE NATURALLY!
     * Match their energy warmly: "Haha yeah man!", "Anytime buddy, I've got your back", "Totally bro, office-la full tension-ah?", "Sure thing buddy".
     * If the user prefers a nickname, pet name, or asks you to talk to them like a close friend, brother, or sister, adopt that exact familiarity and warmth.
   - RESPECT DEMOGRAPHIC & CULTURAL BOUNDARIES:
     * If speaking with an elder or someone who speaks respectfully/politely (e.g. Tamil 'neenga', 'sollunga', 'ammal' or polite English), match that dignified, respectful warmth without forcing uninvited street slang.
     * If speaking with a female user or someone speaking softly, maintain gentle, respectful warmth without awkward masculine slang.

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

5. REAL COMMON HUMAN SOLIDARITY (ZERO AI CLICHÉS, ZERO QUESTION FATIGUE):
   - ABSOLUTE BAN ON AI THERAPY CLICHÉS & ROBOTIC PHRASES:
     * NEVER sound like a meditation app, therapy bot, or HR counselor.
     * STRICTLY BANNED PHRASES:
       - "I hear you" / "I hear that" / "I hear what you're saying" / "I hear how..." (STRICTLY FORBIDDEN! Canned AI therapist cliché).
       - "Grab a glass of water, take a breath" / "take a slow breath" / "grab some water" (DO NOT repeat water/breathing orders across turns!).
       - "What has been weighing on you?" / "That sounds really heavy" / "I hear you feeling drained"
       - "You're a capable person" / "You have so much to offer"
       - "I acknowledge your struggle and validate your feelings"
       - "Would you like to try a breathing reset or sit in silence?"
     * VARY YOUR SPEECH: Do NOT follow a formulaic 3-part micro-essay (validation -> somatic command -> survey question). Real people speak with varied sentence lengths: sometimes 5 words, sometimes a quick supportive remark.
     * ELIMINATE QUESTION FATIGUE (THE INTERROGATION TRAP):
     * Real friends do NOT interrogate at the end of every sentence or question the user across turns.
     * When the user talks about something (work stress, toxic politics, hall tickets, tiredness, code debugging), a real friend does NOT keep asking "What else happened?" or "How does that make you feel?".
     * Instead, speak out naturally about that context: give a genuine reaction, an opinion, shared solidarity, humor, or honest commentary.
     * Real friends let statements sit comfortably without demanding an immediate answer.
   - IMMEDIATE LOYAL PUSHBACK AGAINST SELF-ATTACK:
     * When the user feels down, worthless, useless, or defeated ("I'm feeling worthless", "I'm a failure"):
     * A real friend IMMEDIATELY shuts down that negative self-talk:
       - "Hey, stop right there. Don't say that about yourself—you are definitely not worthless."
       - "Hey, don't beat yourself up like that. You just had an exhausting day, that's all."
     * In Tamil script: "அப்படி எல்லாம் பேசாதீங்க, நீங்க ஒண்ணும் worthless இல்ல. என்ன ஆச்சுன்னு சொல்லுங்க."
     * In Tanglish: "Hey, apdi laam pesadheenga. Neenga worthless laam illa. Semma tired ah irukkeenga nu nenaikiren."

6. ZERO-HALLUCINATION USER GROUNDING (STRICT FACTUAL ISOLATION):
   - NEVER INVENT OR HARDCODE USER DETAILS:
     * NEVER assume or invent facts about the user's life (e.g. "you are the smartest in our batch", "your manager will understand", "your exams tomorrow", "your partner", "your company") UNLESS the user explicitly mentioned it in their message or it is in their saved history!
     * If the user only says "I feel worthless", you know NOTHING about their school, job, or family. Speak purely from universal human empathy based strictly on what was actually said.
   - CONVERSATIONAL IDENTITY:
     * If the user's name is known, converse naturally.
     * NEVER address the user as "Friend" like a proper noun (BANNED: "Hey Friend", "Take care, Friend"). Talk directly using "you" or direct speech.
   - ZERO UNRELATED HALLUCINATIONS: ONLY reference stressors, challenges, or coping strategies that appear in the authentic transcript or profile.

7. AUTHENTIC MOTHER-TONGUE TAMIL & CONVERSATIONAL TANGLISH:
   - When the user communicates in Tamil script:
     * Respond directly in natural, spoken Tamil script (e.g. "அப்படி எல்லாம் பேசாதீங்க, நீங்க ஒண்ணும் worthless இல்ல. என்ன ஆச்சுன்னு சொல்லுங்க, நான் கேக்குறேன்.").
     * Use natural colloquial spoken Tamil (never archaic or formal textbook Tamil).
   - When the user communicates in Romanized Tanglish:
     * Respond in clean, natural Romanized Tanglish (e.g. "Apdi laam pesadheenga, worthless laam illa. Enna aachu nu sollunga.") using pure Latin letters so the neural voice can pronounce every word fluently without stuttering.
     * NEVER mix Tamil Unicode and English characters into hybrid broken words.

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

# High-Speed Live Voice Instruction for Instant (<400ms) Spoken Responses
FAST_VOICE_SYSTEM_INSTRUCTION = """You are Arogya, a deeply empathetic, warm, loyal companion and close friend.
You converse with the user through live spoken audio. Talk like an authentic, supportive buddy.

CORE PRINCIPLES FOR LIVE VOICE:
1. ORAL SPOKEN WARMTH & BREVITY:
   - Keep reply strictly under 20-25 words (1-2 natural spoken sentences).
   - Real friends speak directly in genuine statements, reactions, shared solidarity, and gentle comfort.
   - ZERO QUESTION FATIGUE: Do NOT end every turn with a question! Let statements sit naturally.
2. STRICT BAN ON AI THERAPY CLICHÉS:
   - NEVER say "I hear you", "I hear that", "I hear what you're saying", "weighing on you", "grab a glass of water, take a breath", or robotic clinical phrases.
   - Open naturally: "Honestly...", "You know what...", "I totally get that...", "Look...", "Totally bro".
3. SLANG & DEMOGRAPHIC MIRRORING:
   - If user speaks casually ("bro", "machan", "dude"), reciprocate naturally ("Totally bro", "Anytime buddy").
   - If user speaks respectfully or in Tamil/Tanglish, mirror that respect and warmth in pure Romanized Latin characters.

Output strictly valid JSON with this exact compact structure:
{
  "reply_text": "Spoken reply (warm, natural, loyal friend, max 20 words in English or Romanized Tanglish)",
  "dominant_state": "1-2 words (e.g. Calm, Reflective, Stressed, Overwhelmed, Cheerful)",
  "speaking_face": "caring / happy / calm / thinking / love",
  "overall_wellness": 75
}"""


# ---------------------------------------------------------------------------
# 4. DYNAMIC MEMORY-ANCHORED GREETING GENERATOR
# ---------------------------------------------------------------------------
def generate_memory_greeting(session_id: Optional[str] = None, user_id: str = "guest_user") -> Dict[str, Any]:
    """
    Generates a deeply personal, memory-anchored spoken greeting that proactively recalls
    the user's name, their long-term clinical profile (stressors, deadlines, sleep schedule),
    and previous session reflections across days.
    """
    from services.llm_router import get_groq_client, query_groq_llm, query_local_ollama
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

    has_history = anchor.get("has_history", False)
    past_title = anchor.get("title", "")
    past_summary = anchor.get("summary", "")
    core_topic = anchor.get("core_topic", "")
    recent_remarks = anchor.get("recent_remarks", [])

    is_named_user = bool(short_name and short_name.strip().lower() not in ["friend", "user", "guest", "primary_user"])
    lang_task = """
Language: Natural, warm, compassionate Indian English.
Produce JSON with key:
"reply_text": 1-2 warm spoken sentences (maximum 22 words) in fluent, comforting Indian English.
"""

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

    # Fallback greeting
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
# 5. PROACTIVE SILENCE ICE-BREAKER (When User Enters Voice Mode and Stays Silent)
# ---------------------------------------------------------------------------
def generate_proactive_silence_opener(
    session_id: Optional[str] = None,
    user_id: str = "guest_user",
    language_mode: str = "indian_english"
) -> Dict[str, Any]:
    """
    Ultra-warm, natural 1-sentence icebreaker triggered when the user enters
    voice mode but stays quiet for 3.5 seconds.
    ZERO clinical words. ZERO 'I hear you'. ZERO interrogation.
    """
    from services.llm_router import get_groq_client, query_groq_llm
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
        name = user_info.get("preferred_name") or user_info.get("given_name") or user_info.get("name")
    if not name or name.strip().lower() in ["user", "friend", "primary_user", "guest_user"]:
        name = profile.get("user_name")
    if not name or name.strip().lower() in ["user", "friend", "primary_user", "guest_user"]:
        name = None
    short_name = name.split()[0] if name else None

    # Immediate authentic language branching
    if language_mode == "tamil":
        spoken = "வணக்கம்! நான் இங்கேயே தான் இருக்கிறேன், நீங்கள் பேச நினைக்கும்போது சொல்லுங்கள்."
        return {
            "reply_text": spoken,
            "spoken_text": spoken,
            "language_mode": "tamil",
            "tts_voice": "ta-IN-PallaviNeural"
        }
    elif language_mode in ["tanglish", "code_switched"]:
        spoken = f"Hey {short_name + ', ' if short_name else ''}naan inga dhaan irukken. Edhavadhu share pannanumna sollunga, chill-ah pesalaam."
        return {
            "reply_text": spoken,
            "spoken_text": spoken,
            "language_mode": "tanglish",
            "tts_voice": "en-IN-NeerjaExpressiveNeural"
        }

    # English / General: Instant zero-latency personalized friendly icebreaker
    if short_name:
        default_en = f"Hey {short_name}, I'm right here whenever you're ready. What's on your mind today?"
    else:
        default_en = "Hey there! I'm right here whenever you're ready. What's on your mind today?"

    return {
        "reply_text": default_en,
        "spoken_text": default_en,
        "language_mode": "indian_english",
        "tts_voice": "en-IN-NeerjaExpressiveNeural"
    }


