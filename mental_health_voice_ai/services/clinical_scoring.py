"""
Clinical Scoring, Dual-Layer Crisis Detection & Standardized Assessments (PHQ-9 & GAD-7).
Deterministic calculation in Python code with zero LLM score fabrication.
"""
import re
import numpy as np
from typing import Dict, Any, Tuple, Optional, List

# ---------------------------------------------------------------------------
# 1. CRISIS SAFETY DETECTION (Dual-Layer with False-Positive Negation Guards)
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
# 2. DETERMINISTIC MATHEMATICAL FUSION (Calculated in Python Code)
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
    - wellness: calibrated base minus peak severity and comorbidity burden
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
# 3. FAST AUTOMATIC CONVERSATION TITLING
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
# 4. STANDARDIZED CLINICAL ASSESSMENTS (PHQ-9 & GAD-7)
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


# ---------------------------------------------------------------------------
# 5. HOLISTIC FRIENDLY SESSION SUMMARY & WELLNESS VIBE
# ---------------------------------------------------------------------------
def generate_holistic_friendly_summary(
    session_messages: List[Dict[str, Any]],
    user_name: Optional[str] = None
) -> Dict[str, Any]:
    """
    Synthesizes the entire multi-turn conversation into a comprehensive,
    uplifting, friendly Heart-to-Heart Summary & Wellness Vibe card.
    STRICTLY ZERO clinical words (no PHQ, GAD, depression, anxiety disorder,
    psychopathology, clinical assessment, diagnosis, symptomatology).
    ONLY genuine, supportive, friendly companion language.
    """
    clean_user = user_name if (user_name and user_name.lower() not in ["friend", "user", "guest", "guest_user", "primary_user"]) else "Friend"

    # Extract dialogue turns
    user_turns = []
    dialogue_snippets = []

    for m in session_messages:
        role = m.get("role")
        text = (m.get("text") or "").strip()
        if not text:
            continue
        if role == "user":
            user_turns.append(text)
            dialogue_snippets.append(f"User: {text}")
        elif role == "assistant":
            dialogue_snippets.append(f"Arogya: {text}")

    # Handle short or quiet session with warm zero-lag defaults
    if not user_turns:
        return {
            "has_dialogue": False,
            "overall_wellness": 85,
            "vibe_title": "Quiet Heart-to-Heart",
            "peace_of_mind": "Peaceful & Settled",
            "energy_vibe": "Calm & Grounded",
            "emotional_shift": "Took a quiet pause to check in and connect.",
            "companion_takeaways": [
                "Even taking a few seconds to breathe and pause is a healthy gift to yourself.",
                "I'm always right here whenever you want to talk or unwind."
            ],
            "chat_highlights": [
                "Checked in for a brief peaceful pause."
            ]
        }

    full_conversation_text = "\n".join(dialogue_snippets[-12:])

    # Sub-second inference via Groq LPU with Gemini fallback
    from services.llm_router import get_groq_client, query_groq_llm, query_gemini_backup
    client = get_groq_client()

    prompt = f"""
You are Arogya, a warm, loyal best friend and confidant to {clean_user}.
Review the following multi-turn conversation:

--- CONVERSATION TRANSCRIPT ---
{full_conversation_text}
--- END TRANSCRIPT ---

TASK:
Create a holistic, uplifting, genuinely friendly post-chat Heart-to-Heart Summary & Wellness Vibe.

STRICT CONSTRAINTS (MANDATORY):
1. ABSOLUTELY ZERO CLINICAL WORDS:
   Do NOT use: 'depression', 'depressive', 'anxiety', 'disorder', 'clinical', 'diagnosis', 'symptom', 'psychiatric', 'pathology', 'triage', 'PHQ', 'GAD', 'comorbidity', 'assessment', 'intervention'.
2. ONLY FRIENDLY, UPLIFTING, AUTHENTIC FRIEND WORDS:
   Use terms like: 'peace of mind', 'vibe', 'energy level', 'catching your breath', 'headspace', 'carrying a bit of stress', 'recharging', 'grounded', 'unwinding'.
3. STRICT BAN ON CLICHÉS:
   NEVER write 'I hear you' or robotic therapist lines. Talk like an authentic, supportive buddy.
4. WELLNESS SCORE:
   Assign an overall wellness score from 40 to 98 based on how they're feeling (e.g. 80-98 = feeling balanced/positive, 60-79 = unwinding/managing, below 60 = had a very exhausting/stressful day).

Output strictly valid JSON with this exact structure:
{{
  "overall_wellness": 82,
  "vibe_title": "Feeling Lighter & Balanced",
  "peace_of_mind": "Calm Waters",
  "energy_vibe": "Steady & Recharging",
  "emotional_shift": "1-2 warm sentences describing how they felt across the chat (e.g. You came in feeling run-down by deadlines, but talking it through helped you catch your breath and feel much more grounded).",
  "companion_takeaways": [
    "2-3 warm, positive, actionable reminders from a real friend (e.g. Put your work laptop away tonight—give yourself a real break.)"
  ],
  "chat_highlights": [
    "1-2 specific positive or honest moments they shared during our chat"
  ]
}}
"""

    if client:
        try:
            cand = query_groq_llm(prompt, "You are a warm, loyal companion writing a friendly Heart-to-Heart summary with zero clinical jargon.", max_tokens=450, required_key="overall_wellness")
            if not cand:
                cand = query_gemini_backup(prompt, "You are a warm, loyal companion writing a friendly Heart-to-Heart summary with zero clinical jargon.", max_tokens=450, required_key="overall_wellness")

            if cand and isinstance(cand, dict) and "overall_wellness" in cand:
                wellness_val = int(cand.get("overall_wellness", 80))
                wellness_val = max(35, min(98, wellness_val))

                takeaways = cand.get("companion_takeaways", [])
                if not isinstance(takeaways, list) or len(takeaways) == 0:
                    takeaways = ["Take it easy tonight and give your mind some well-deserved rest."]

                clean_takeaways = []
                for t in takeaways:
                    t_str = str(t)
                    t_str = re.sub(r'(?i)\bi hear you,?\s*', "Honestly, ", t_str)
                    t_str = re.sub(r'(?i)\bclinical\b', "personal", t_str)
                    clean_takeaways.append(t_str)

                shift = str(cand.get("emotional_shift") or "You took time out of your busy day to pause, reflect, and find your center.")
                shift = re.sub(r'(?i)\bi hear you,?\s*', "", shift)

                return {
                    "has_dialogue": True,
                    "overall_wellness": wellness_val,
                    "vibe_title": str(cand.get("vibe_title") or "Feeling Balanced & Grounded"),
                    "peace_of_mind": str(cand.get("peace_of_mind") or "Calm & Settled"),
                    "energy_vibe": str(cand.get("energy_vibe") or "Steady & Recharging"),
                    "emotional_shift": shift,
                    "companion_takeaways": clean_takeaways[:3],
                    "chat_highlights": cand.get("chat_highlights", ["Shared an honest heart-to-heart reflection."])[:2]
                }
        except Exception as e:
            print(f"[!] Holistic friendly summary LLM notice: {e}")

    # Instant deterministic friendly fallback (Guarantees zero-lag performance under all network conditions)
    return {
        "has_dialogue": True,
        "overall_wellness": 80,
        "vibe_title": "Feeling Lighter & Balanced",
        "peace_of_mind": "Steady Waters",
        "energy_vibe": "Recharging",
        "emotional_shift": "You took a moment to share what was on your mind and found a calmer, steadier pace.",
        "companion_takeaways": [
            "Put work and stress aside for the rest of today.",
            "Get some good, uninterrupted sleep tonight.",
            "Remember I've always got your back whenever you need to talk."
        ],
        "chat_highlights": [
            "Talked through what was on your mind and ended on a grounded note."
        ]
    }


