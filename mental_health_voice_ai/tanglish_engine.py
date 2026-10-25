"""
Arogya Conversational Tamil & Tanglish Naturalizer Engine
==========================================================
Transforms formal, translated, or bookish Tamil into authentic, spoken colloquial Tamil / Tanglish.
Provides language & register classification, prosodic boundary staging, and dual-TTS phonetic preparation.
Zero external package dependencies (pure Python standard library for ultra-fast <2ms execution & zero VRAM).
"""

import re
from typing import Dict, Any, Tuple, Optional, List

# Common English technical, mental health, and daily life loanwords that Tamil speakers naturally use in English
ENGLISH_LOANWORDS = {
    "stress", "stressed", "relax", "relaxed", "relaxing", "tired", "tension", "tensed",
    "doctor", "appointment", "hospital", "clinic", "medicine", "tablets", "therapy",
    "exam", "test", "interview", "college", "school", "office", "work", "project", "deadline",
    "client", "meeting", "manager", "boss", "salary", "job", "career", "study", "syllabus",
    "feel", "feeling", "feelings", "mood", "happy", "sad", "upset", "depressed", "depression",
    "panic", "anxiety", "anxious", "overwhelmed", "overthinking", "burnout", "exhausted",
    "sleep", "sleeping", "insomnia", "rest", "break", "leave", "holiday", "weekend",
    "family", "friend", "friends", "partner", "parents", "relationship", "breakup",
    "problem", "issue", "situation", "step", "steps", "plan", "future", "mind", "heart",
    "okay", "fine", "cool", "super", "great", "nice", "proper", "normal", "hectic",
    "actually", "definitely", "sure", "ready", "comfortable", "simple", "easy", "help",
    "call", "message", "chat", "talk", "listen", "focus", "peace", "calm", "safe", "space",
    "breath", "breathing", "exercise", "walk", "tea", "coffee", "music", "sleep schedule",
    "bro", "sir", "mam"
}

# Common Tamil spoken roots and colloquial marker stems
TAMIL_MARKERS = {
    "romba", "konjam", "irukku", "irukken", "irukka", "irundhuchi", "irundhadhu", "irundha",
    "panren", "pannunga", "pannanum", "pannalaam", "panradhu", "panna", "panniten", "paakalaam",
    "sollunga", "sollu", "solren", "sonna", "sonnanga", "kekkudhu", "kekren", "kekkalaam",
    "puriyudhu", "puriyala", "purinjikitten", "theriyum", "therila", "theriyala",
    "seri", "sari", "aama", "illa", "illai", "illama", "parava", "paravalla", "paravayla",
    "enna", "eppadi", "epdi", "yen", "enga", "yaaru", "eppo", "ippo", "appo", "apram",
    "naan", "enakku", "ennoda", "enna", "neenga", "ungalukku", "ungala", "ungakitta", "unga",
    "namma", "nammaloda", "namakku", "avan", "ava", "avanga", "edhuvum", "onnum", "ellarum",
    "bayama", "kashtama", "valikidhu", "kavala", "aachu", "aayiduchi", "pochu", "podhum",
    "venum", "venam", "thoonudhu", "moolai", "udambu", "manasu", "nenachu", "pesa", "pesalaam",
    "vaanga", "ponga", "kooda", "mattum", "thaan", "koodave", "madhiri", "pola", "aiyo"
}

# Bookish / Literary written patterns -> Spoken Colloquial Tamil/Tanglish transformations
COLLOQUIAL_TRANSFORMS = [
    # Verb: To be / feeling
    (r"\bneengal eppadi unargireergal\b", "eppadi feel panreenga"),
    (r"\beppadi unargireergal\b", "eppadi feel panreenga"),
    (r"\beppadi irukkireergal\b", "eppadi irukkeenga"),
    (r"\bnaan nandraaga irukkiren\b", "naan nalla irukken"),
    (r"\bnandraaga irukkireergala\b", "nalla irukkeengala"),
    (r"\bnandraaga irukku\b", "nalla irukku"),
    (r"\bnandraga\b", "nalla"),
    
    # Needs / Should do
    (r"\bseiya vendum\b", "pannanum"),
    (r"\bseiya mudiyum\b", "panna mudiyum"),
    (r"\bseiya mudiyuma\b", "panna mudiyuma"),
    (r"\bseiya vendam\b", "panna venam"),
    (r"\bseigiren\b", "panren"),
    (r"\bseiyungal\b", "pannunga"),
    (r"\bseivom\b", "pannalaam"),
    (r"\bseivadhu\b", "panradhu"),
    (r"\bennai seiya virumbugireergal\b", "ippo enna panna poringa"),
    (r"\benna seiya virumbugireergal\b", "ippo enna panna thonudhu"),
    (r"\bvirumbugireergal\b", "panna poringa"),
    
    # Rest & Coping
    (r"\boyvu edukka vendum\b", "konjam rest edunga"),
    (r"\boivu edukka vendum\b", "konjam rest edunga"),
    (r"\boyvu edungal\b", "konjam rest edunga"),
    (r"\boivu edungal\b", "konjam rest edunga"),
    (r"\bkavalai padaatheergal\b", "tension aagadheenga, worry pannadheenga"),
    (r"\bkavalai padadheenga\b", "tension aagadheenga"),
    (r"\bthannambikkaiudan irungal\b", "namma step-by-step paathukalaam"),
    (r"\bpayappada thevaiyillai\b", "bayapadadheenga"),
    (r"\bpayappadatheergal\b", "bayapadadheenga"),
    
    # Helping & Presence
    (r"\bnaan ungalukku udhava mudiyum\b", "naan help panren"),
    (r"\budhava mudiyum\b", "help panren"),
    (r"\budhavi seiyugiren\b", "help panren"),
    (r"\budhavi venduma\b", "help venuma"),
    (r"\bnaan ingu irukkiren\b", "naan unga kooda irukken"),
    (r"\bnaan ungaludan irukkiren\b", "naan unga kooda irukken"),
    (r"\bmaruthuvarai parkka vendum\b", "doctor-ah consult pannanum"),
    (r"\bmaruthuvarai santhikka vendum\b", "doctor-ah paakkanum"),
    
    # Problems & Understanding
    (r"\bungalukku enna pirachanai ullathu\b", "enna problem irukku"),
    (r"\benna pirachanai\b", "enna problem"),
    (r"\bpirachanai\b", "problem"),
    (r"\benakku purigiradhu\b", "enakku puriyudhu"),
    (r"\bpurigiradhu\b", "puriyudhu"),
    (r"\btherigiradhu\b", "theriyudhu"),
    (r"\btheriyavillai\b", "therila"),
    (r"\bpuriyavillai\b", "puriyala"),
    
    # Pronoun & Polite forms
    (r"\bneengal\b", "neenga"),
    (r"\bungalukku\b", "ungalukku"),
    (r"\bungaludaya\b", "ungaloda"),
    (r"\bennudaya\b", "ennoda"),
    (r"\bippodhu\b", "ippo"),
    (r"\bappodhu\b", "appo"),
    (r"\bpinbu\b", "apram"),
    (r"\binraiku\b", "inaiku"),
    (r"\bindha naalil\b", "inaiku"),
    (r"\bpesuvom\b", "pesalaam"),
    (r"\bparppom\b", "paakalaam"),
    (r"\bvazhthukkal\b", "valthukkal"),
    (r"\bvaazhga\b", "valga")
]


# ==============================================================================
# 1. LANGUAGE & REGISTER DETECTION
# ==============================================================================
def detect_language_and_register(text: str, history: Optional[List[dict]] = None) -> Dict[str, Any]:
    """
    Classifies the user's language mode and conversational register:
    - language_mode: 'tanglish' | 'tamil' | 'indian_english' | 'code_switched'
    - register: 'casual_tanglish' | 'warm_tanglish' | 'respectful_tamil' | 'indian_english'
    - has_casual_markers: bool (user used 'bro', 'da', 'machan', 'pa', etc.)
    """
    if not text or not text.strip():
        return {
            "language_mode": "indian_english",
            "register": "indian_english",
            "has_casual_markers": False,
            "confidence": 0.5
        }

    clean_text = text.strip()
    words = [re.sub(r'[^\w]', '', w.lower()) for w in clean_text.split() if w.strip()]

    # 1. Check for native Tamil script Unicode block: U+0B80 to U+0BFF
    has_tamil_script = bool(re.search(r'[\u0B80-\u0BFF]', clean_text))
    if has_tamil_script:
        # Check if mixed with English words
        has_english_words = any(w in ENGLISH_LOANWORDS or (len(w) > 3 and re.match(r'^[a-z]+$', w)) for w in words)
        return {
            "language_mode": "code_switched" if has_english_words else "tamil",
            "register": "warm_tanglish" if has_english_words else "respectful_tamil",
            "has_casual_markers": any(w in ["bro", "da", "pa", "machan"] for w in words),
            "confidence": 0.95
        }

    # 2. Count Tanglish markers vs English words
    tamil_marker_hits = sum(1 for w in words if w in TAMIL_MARKERS)
    casual_hits = sum(1 for w in words if w in ["bro", "da", "machan", "pa", "thala", "mame"])
    english_hits = sum(1 for w in words if w in ENGLISH_LOANWORDS or w in {"the", "i", "my", "to", "and", "is", "for", "with", "you", "me", "very", "today", "feel", "feeling"})

    total_words = max(1, len(words))
    tamil_ratio = tamil_marker_hits / total_words

    # Classify language mode
    if tamil_marker_hits >= 2 or tamil_ratio >= 0.22:
        if english_hits >= 2:
            language_mode = "code_switched"
        else:
            language_mode = "tanglish"
    elif any(marker in clean_text.lower() for marker in ["romba", "irukku", "enna aachu", "panren", "pannunga", "puriyudhu", "sollunga"]):
        language_mode = "tanglish"
    else:
        # Check historical context if available
        hist_tamil = False
        if history:
            recent_user_msgs = [m.get("text", "") for m in history[-2:] if m.get("role") == "user"]
            for h in recent_user_msgs:
                h_words = [re.sub(r'[^\w]', '', w.lower()) for w in h.split()]
                if any(w in TAMIL_MARKERS for w in h_words):
                    hist_tamil = True
                    break
        language_mode = "tanglish" if hist_tamil and tamil_marker_hits >= 1 else "indian_english"

    # Determine Register / Formality
    has_casual = casual_hits > 0
    if language_mode in ["tanglish", "code_switched"]:
        if has_casual:
            register = "casual_tanglish"
        elif any(w in ["neenga", "sollunga", "pannunga", "edunga"] for w in words):
            register = "respectful_tamil"
        else:
            register = "warm_tanglish"
    else:
        register = "indian_english"

    return {
        "language_mode": language_mode,
        "register": register,
        "has_casual_markers": has_casual,
        "confidence": round(min(0.99, max(0.6, (tamil_marker_hits + 1) / total_words)), 2)
    }


# ==============================================================================
# 2. CONVERSATIONAL TAMIL/TANGLISH NATURALIZER
# ==============================================================================
def naturalize_tanglish_response(
    raw_text: str,
    user_input: str = "",
    language_mode: str = "tanglish",
    register: str = "warm_tanglish",
    emotion_state: str = "Calm"
) -> str:
    """
    Transforms formal or mechanically translated responses into natural, spoken colloquial Tamil/Tanglish.
    - Eliminates literary diglossia (seiya vendum -> pannanum, etc.)
    - Context-dependent warmth (preserves respect, adds empathetic touch)
    - Never spams slang or 'bro' unless contextually appropriate
    - Preserves English technical and mental health terms cleanly
    """
    if not raw_text or not raw_text.strip():
        return raw_text

    text = raw_text.strip()

    # If pure Indian English is detected, preserve English natural cadence
    if language_mode == "indian_english" and register == "indian_english":
        # Keep clean, conversational Indian English
        text = re.sub(r'\bdo not worry\b', "don't worry", text, flags=re.IGNORECASE)
        text = re.sub(r'\bi am here for you\b', "I'm right here with you", text, flags=re.IGNORECASE)
        return text

    # Step 1: Apply Colloquial Spoken Tamil Phrase Replacements
    for pattern, replacement in COLLOQUIAL_TRANSFORMS:
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)

    # Step 2: Tone and Slang Calibration
    # Only add 'bro' or casual warmth if the user explicitly used casual markers AND it's casual_tanglish
    user_words = set(re.sub(r'[^\w\s]', '', user_input.lower()).split())
    user_used_bro = bool({"bro", "da", "machan", "pa"} & user_words)

    # Clean double 'bro' if LLM generated too many
    bro_count = len(re.findall(r'\bbro\b', text, flags=re.IGNORECASE))
    if bro_count > 1:
        # Keep only the first occurrence
        parts = re.split(r'\b(bro)\b', text, flags=re.IGNORECASE)
        new_parts = []
        found_first = False
        for p in parts:
            if p.lower() == "bro":
                if not found_first:
                    new_parts.append(p)
                    found_first = True
                else:
                    # remove subsequent 'bro'
                    pass
            else:
                new_parts.append(p)
        text = "".join(new_parts)

    # If user used formal 'neenga' / 'sir', ensure we DO NOT add 'bro'
    if not user_used_bro and register == "respectful_tamil":
        text = re.sub(r'\bbro\b,?\s*', '', text, flags=re.IGNORECASE)

    # Step 3: Polish sentence flow & conversational connectors
    text = re.sub(r'\s+,', ',', text)
    text = re.sub(r'\s+\.', '.', text)
    text = re.sub(r'\s+', ' ', text).strip()

    return text


# ==============================================================================
# 3. PROSODY AND PHONETIC PREPARATION
# ==============================================================================
def select_tts_route(language_mode: str, voice_mode: str = "fast") -> str:
    """
    Selects the optimal TTS engine based on user preference and language mode:
    - 'cloned' -> 'f5_tts' (Local GPU Diffusion on RTX 3050)
    - 'fast' + (tanglish / tamil / code_switched) -> 'edge_tamil' (ta-IN-PallaviNeural)
    - 'fast' + indian_english -> 'edge_english' (en-IN-NeerjaNeural)
    """
    if voice_mode == "cloned":
        return "f5_tts"
    if language_mode in ["tanglish", "tamil", "code_switched"]:
        return "edge_tamil"
    return "edge_english"


def stage_prosody_and_phonetics(
    text: str,
    language_mode: str = "tanglish",
    emotion_state: str = "Calm",
    tts_engine: str = "auto"
) -> Dict[str, str]:
    """
    Prepares text for TTS synthesis:
    - display_text: Beautiful, natural colloquial text shown to the user on the chat stream.
    - spoken_text: Phonetically staged text with breath pauses and intonation tailored for the target TTS engine.
    - tts_voice: The exact voice identifier to be used (e.g. 'ta-IN-PallaviNeural' or 'en-IN-NeerjaNeural').
    """
    if tts_engine == "auto":
        tts_engine = select_tts_route(language_mode)

    clean_display = re.sub(r'[*_#`~\[\]]', '', text)
    clean_display = re.sub(r'\s+', ' ', clean_display).strip()

    # Prosodic pacing adjustments based on emotion
    # Overwhelmed / Distress -> add gentle pause markers (ellipsis / commas) for slower cadence
    if emotion_state in ["Overwhelmed", "Exhausted", "Crisis Alert", "Tense"]:
        pause_marker = "... "
    elif emotion_state in ["Lonely", "Reflective"]:
        pause_marker = ", "
    else:
        pause_marker = ". "

    # Sentence boundary pacing
    spaced_sentences = re.sub(r'([.?!])\s+', r'\1 ', clean_display)

    if tts_engine == "edge_tamil":
        # Native Tamil Voice: ta-IN-PallaviNeural
        # Converts colloquial Tanglish to spoken Tamil script with preserved English loanwords!
        spoken_script = transliterate_tanglish_to_spoken_tamil(clean_display)
        # Add natural intonation pauses for PallaviNeural
        spoken_text = spoken_script.replace(". ", pause_marker).replace("! ", ". ")
        return {
            "display_text": clean_display,
            "spoken_text": spoken_text,
            "tts_voice": "ta-IN-PallaviNeural"
        }

    elif tts_engine == "f5_tts":
        # Local Cloned Diffusion TTS on RTX 3050 GPU
        # Formats phonetic Latin Tanglish with natural pause markers
        spoken_text = clean_display
        spoken_text = re.sub(r'\b([A-Za-z]+)-ah\b', r'\1 aa', spoken_text)
        spoken_text = re.sub(r'\b([A-Za-z]+)-la\b', r'\1 la', spoken_text)
        spoken_text = spoken_text.replace(". ", pause_marker)
        return {
            "display_text": clean_display,
            "spoken_text": spoken_text,
            "tts_voice": "F5TTS_v1_Base"
        }

    else:
        # Indian English Voice: en-IN-NeerjaNeural
        spoken_text = clean_display.replace(". ", pause_marker)
        return {
            "display_text": clean_display,
            "spoken_text": spoken_text,
            "tts_voice": "en-IN-NeerjaNeural"
        }


# ==============================================================================
# 4. SPOKEN TANGLISH TO TAMIL SCRIPT CONVERTER (For Native ta-IN-PallaviNeural)
# ==============================================================================
# Comprehensive lexical dictionary of conversational Tanglish terms -> authentic spoken Tamil script
SPOKEN_LEXICON = {
    # Pronouns & People
    "naan": "நான்", "nan": "நான்", "enakku": "எனக்கு", "ennoda": "என்னோட", "enna": "என்ன",
    "neenga": "நீங்க", "neengal": "நீங்க", "ungalukku": "உங்களுக்கு", "ungaloda": "உங்களோட", "unga": "உங்க",
    "namma": "நம்ம", "nammaloda": "நம்மளோட", "namakku": "நமக்கு",
    "avan": "அவன்", "ava": "அவ", "avanga": "அவங்க", "ellarum": "எல்லாரும்", "bro": "ப்ரோ",
    "thala": "தலை", "machan": "மச்சான்", "pa": "பா",
    
    # Question words & State
    "enna aachu": "என்ன ஆச்சு", "enna aayiduchi": "என்ன ஆயிடுச்சு", "enna problem": "என்ன problem",
    "eppadi": "எப்படி", "epdi": "எப்படி", "eppadi feel panreenga": "எப்படி feel பண்றீங்க",
    "eppadi irukkeenga": "எப்படி இருக்கீங்க", "epdi irukkeenga": "எப்படி இருக்கீங்க",
    "enga": "எங்க", "eppo": "எப்போ", "ippo": "இப்போ", "appo": "அப்போ", "yen": "ஏன்", "yaaru": "யாரு",
    "edhuvum": "எதுவும்", "onnum": "ஒண்ணும்",
    
    # Emotional & Sensory
    "romba": "ரொம்ப", "konjam": "கொஞ்சம்", "kavala": "கவலை", "bayama": "பயமா", "kashtama": "கஷ்டமா",
    "bayapadadheenga": "பயப்படாதீங்க", "tension aagadheenga": "tension ஆகாதீங்க",
    "manasu": "மனசு", "udambu": "உடம்பு", "moolai": "மூளை", "valikidhu": "வலிக்குது",
    "thookam": "தூக்கம்", "nimmathi": "நிம்மதி", "sandhosham": "சந்தோஷம்",
    
    # Verbs & Connectors
    "seri": "சரி", "sari": "சரி", "aama": "ஆமா", "illa": "இல்ல", "illai": "இல்லை",
    "parava illa": "பரவா இல்ல", "paravalla": "பரவால்ல",
    "panren": "பண்றேன்", "pannunga": "பண்ணுங்க", "pannanum": "பண்ணனும்", "pannalaam": "பண்ணலாம்",
    "panradhu": "பண்றது", "panna": "பண்ண", "panniten": "பண்ணிட்டேன்",
    "irukku": "இருக்கு", "irukka": "இருக்கா", "irukken": "இருக்கேன்", "irundhuchi": "இருந்துச்சு", "irundha": "இருந்தா",
    "sollunga": "சொல்லுங்க", "sollu": "சொல்லு", "solren": "சொல்றேன்",
    "puriyudhu": "புரியுது", "puriyala": "புரியல", "purinjukitten": "புரிஞ்சுகிட்டேன்",
    "theriyum": "தெரியும்", "therila": "தெரியல", "theriyala": "தெரியல",
    "venum": "வேணும்", "venam": "வேணாம்", "kekkuren": "கேக்குறேன்", "kekkudhu": "கேக்குது",
    "edunga": "எடுங்க", "paakalaam": "பாக்கலாம்", "paathukalaam": "பாத்துக்கலாம்",
    "pesalaam": "பேசலாம்", "vaanga": "வாங்க", "ponga": "போங்க", "apram": "அப்றம்",
    "thaan": "தான்", "mattum": "மட்டும்", "kooda": "கூட", "madhiri": "மாதிரி", "pola": "போல",
    "inaiku": "இன்னைக்கு", "naalaiku": "நாளைக்கு", "nalla": "நல்லா", "aiyo": "ஐயோ",
    "take it easy": "take it easy", "step by step": "step by step"
}

def transliterate_tanglish_to_spoken_tamil(text: str) -> str:
    """
    Intelligently converts conversational Tanglish phrases into spoken Tamil script,
    while carefully keeping English loanwords (e.g. stress, exam, doctor, relax) intact.
    This allows ta-IN-PallaviNeural to pronounce Tamil syllables with native rhythm and intonation!
    """
    out = text

    # Sort lexicon by phrase length descending so multi-word idioms match first
    sorted_lex = sorted(SPOKEN_LEXICON.items(), key=lambda x: len(x[0]), reverse=True)

    for tanglish_phrase, tamil_val in sorted_lex:
        # Word boundary match case-insensitively
        pattern = r'(?i)\b' + re.escape(tanglish_phrase) + r'\b'
        out = re.sub(pattern, tamil_val, out)

    # Clean up hyphenated suffixes like 'stress-ah' -> 'stress-ஆ'
    suffix_map = {
        r'-ah\b': '-ஆ',
        r'-la\b': '-ல',
        r'-ku\b': '-க்கு',
        r'-oda\b': '-ஓட',
        r'-nu\b': '-னு'
    }
    for suff_pat, suff_val in suffix_map.items():
        out = re.sub(r'(?i)' + suff_pat, suff_val, out)

    return out
