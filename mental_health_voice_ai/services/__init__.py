"""
Services package: LLM routing, failover, and clinical deterministic scoring.
"""
from .llm_router import (
    get_groq_client,
    query_groq_llm,
    query_local_ollama,
    query_gemini_backup
)
from .clinical_scoring import (
    check_crisis_risk,
    compute_deterministic_wellness,
    generate_quick_session_title,
    PHQ9_QUESTIONS,
    GAD7_QUESTIONS,
    RESPONSE_SCALE,
    score_phq9,
    score_gad7
)

__all__ = [
    "get_groq_client",
    "query_groq_llm",
    "query_local_ollama",
    "query_gemini_backup",
    "check_crisis_risk",
    "compute_deterministic_wellness",
    "generate_quick_session_title",
    "PHQ9_QUESTIONS",
    "GAD7_QUESTIONS",
    "RESPONSE_SCALE",
    "score_phq9",
    "score_gad7"
]

