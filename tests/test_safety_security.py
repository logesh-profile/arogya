import os
import sys
import pytest
from fastapi.testclient import TestClient

# Ensure mental_health_voice_ai is on sys.path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_DIR = os.path.join(BASE_DIR, "mental_health_voice_ai")
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from mental_health_voice_ai.app import app
from mental_health_voice_ai.database import (
    switch_or_create_local_user,
    revoke_auth_session,
    create_session,
    save_message,
    init_db
)
from mental_health_voice_ai.services.clinical_scoring import (
    score_phq9,
    score_gad7,
    compute_deterministic_wellness
)

@pytest.fixture(scope="session", autouse=True)
def setup_database():
    init_db()

@pytest.fixture
def client():
    return TestClient(app)

# ---------------------------------------------------------------------------
# 1. TEST UNAUTHENTICATED REQUESTS REJECTED (401)
# ---------------------------------------------------------------------------
def test_unauthenticated_requests_rejected(client):
    """Verifies that private endpoints strictly reject unauthenticated requests with HTTP 401."""
    # List sessions without auth
    res = client.get("/api/sessions")
    assert res.status_code == 401
    assert "Authentication required" in res.json().get("detail", "")

    # Create session without auth
    res = client.post("/api/sessions")
    assert res.status_code == 401

    # Access specific session without auth
    res = client.get("/api/sessions/sess_arbitrary_test")
    assert res.status_code == 401

    # Access analytics summary without auth
    res = client.get("/api/analytics/summary")
    assert res.status_code == 401

    # Access doctor summary without auth
    res = client.get("/api/clinical/report/doctor-summary")
    assert res.status_code == 401


# ---------------------------------------------------------------------------
# 2. TEST INVALID, EXPIRED, AND REVOKED SESSIONS REJECTED (401)
# ---------------------------------------------------------------------------
def test_invalid_and_revoked_sessions_rejected(client):
    """Verifies that invalid, forged, revoked, or query-param session tokens are rejected."""
    # Forged bearer token
    res = client.get("/api/sessions", headers={"Authorization": "Bearer forged_invalid_session_token_12345"})
    assert res.status_code == 401

    # Query-param token leakage is rejected (no tokens allowed in URLs)
    res = client.get("/api/sessions?token=forged_token_in_url")
    assert res.status_code == 401

    # Create a real authenticated user and token
    user_data = switch_or_create_local_user("test_user_alpha")
    token = user_data["session_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Should succeed while active
    res = client.get("/api/sessions", headers=headers)
    assert res.status_code == 200
    assert isinstance(res.json(), list)

    # Revoke session
    revoke_auth_session(token)

    # Subsequent request with revoked token must fail with 401
    res = client.get("/api/sessions", headers=headers)
    assert res.status_code == 401


# ---------------------------------------------------------------------------
# 3. TEST STRICT USER ISOLATION (CROSS-USER 403 FORBIDDEN)
# ---------------------------------------------------------------------------
def test_user_isolation_prevent_cross_user_access(client):
    """Verifies that User A cannot view, change, delete, or inspect User B's sessions or reports."""
    # User A creates a session
    user_a_data = switch_or_create_local_user("user_alpha_101")
    token_a = user_a_data["session_token"]
    user_a_id = user_a_data["user"]["id"]
    headers_a = {"Authorization": f"Bearer {token_a}"}

    res_sess = client.post("/api/sessions", headers=headers_a)
    assert res_sess.status_code == 200
    sess_id = res_sess.json()["session_id"]

    # Save a confidential dialogue message into User A's session
    save_message(sess_id, "user", "I have confidential feelings to discuss.", user_id=user_a_id)

    # User B logs in
    user_b_data = switch_or_create_local_user("user_bravo_202")
    token_b = user_b_data["session_token"]
    headers_b = {"Authorization": f"Bearer {token_b}"}

    # User B tries to view User A's session -> Must be 403 Forbidden
    res_b_view = client.get(f"/api/sessions/{sess_id}", headers=headers_b)
    assert res_b_view.status_code == 403
    assert "Access forbidden" in res_b_view.json()["detail"]

    # User B tries to rename User A's session -> Must be 403 Forbidden
    res_b_patch = client.patch(f"/api/sessions/{sess_id}", data={"title": "Hacked Title"}, headers=headers_b)
    assert res_b_patch.status_code == 403

    # User B tries to delete User A's session -> Must be 403 Forbidden
    res_b_del = client.delete(f"/api/sessions/{sess_id}", headers=headers_b)
    assert res_b_del.status_code == 403

    # User B tries to download User A's reflection report -> Must be 403 Forbidden
    res_b_rep = client.get(f"/api/sessions/{sess_id}/report", headers=headers_b)
    assert res_b_rep.status_code == 403

    # User B tries to download User A's doctor summary report -> Must be 403 Forbidden
    res_b_doc = client.get(f"/api/clinical/report/doctor-summary?session_id={sess_id}", headers=headers_b)
    assert res_b_doc.status_code == 403

    # User A can view their own session
    res_a_view = client.get(f"/api/sessions/{sess_id}", headers=headers_a)
    assert res_a_view.status_code == 200


# ---------------------------------------------------------------------------
# 4. TEST PHQ-9 & GAD-7 SCORING RESILIENCE (VALID, MISSING, INVALID)
# ---------------------------------------------------------------------------
def test_phq9_scoring_handles_valid_missing_and_invalid():
    """Verifies PHQ-9 scoring handles valid answers, omitted questions, and corrupt string types without crashing."""
    # 1. Valid standard answers
    valid_answers = {"1": 2, "2": 3, "3": 1, "4": 0, "5": 1, "6": 2, "7": 1, "8": 0, "9": 0}
    res = score_phq9(valid_answers)
    assert res["total_score"] == 10
    assert res["severity"] == "Moderate"
    assert res["q9_suicide_flag"] is False

    # 2. Suicide Item 9 flag trigger
    suicide_answers = {"1": 1, "9": 2}
    res_suicide = score_phq9(suicide_answers)
    assert res_suicide["q9_suicide_flag"] is True
    assert res_suicide["is_crisis"] is True

    # 3. Missing answers (partial/empty dict)
    res_empty = score_phq9({})
    assert res_empty["total_score"] == 0
    assert res_empty["severity"] == "None-Minimal"
    assert res_empty["q9_suicide_flag"] is False

    # 4. Invalid types (string garbage, None, out-of-range numbers)
    corrupt_answers = {
        "1": "invalid_string",
        "2": None,
        "3": 999,  # Should clamp to max 3
        "4": -10,  # Should clamp to min 0
        "9": "not_a_number"
    }
    res_corrupt = score_phq9(corrupt_answers)
    assert res_corrupt["total_score"] == 3  # Only question 3 clamped to 3
    assert res_corrupt["severity"] == "None-Minimal"
    assert res_corrupt["q9_suicide_flag"] is False


def test_gad7_scoring_handles_valid_missing_and_invalid():
    """Verifies GAD-7 scoring handles valid answers, omitted questions, and corrupt string types without crashing."""
    # 1. Valid standard answers
    valid_answers = {"1": 2, "2": 2, "3": 3, "4": 1, "5": 2, "6": 1, "7": 1}
    res = score_gad7(valid_answers)
    assert res["total_score"] == 12
    assert res["severity"] == "Moderate"

    # 2. Missing answers (empty dict)
    res_empty = score_gad7({})
    assert res_empty["total_score"] == 0
    assert res_empty["severity"] == "Minimal"

    # 3. Corrupt inputs
    corrupt_answers = {"1": "abc", "2": [1, 2], "3": 50, "4": -5}
    res_corrupt = score_gad7(corrupt_answers)
    assert res_corrupt["total_score"] == 3  # Item 3 clamped to 3


# ---------------------------------------------------------------------------
# 5. TEST LLM MALFORMED EVIDENCE & RESILIENCE
# ---------------------------------------------------------------------------
def test_malformed_llm_evidence_resilience():
    """Verifies that malformed LLM responses (integers, strings, None) do not crash deterministic wellness calculation."""
    # Completely corrupt evidence dictionary
    corrupt_evidence = {
        "stress_tension": 2,  # integer instead of {"score": 2, "quote": "..."}
        "worry_apprehension": "high",
        "fatigue_exhaustion": None,
        "emotional_heaviness": {"score": "not_an_int", "quote": "I am so tired"}
    }
    calc = compute_deterministic_wellness(corrupt_evidence)
    assert "overall_wellness" in calc
    assert isinstance(calc["overall_wellness"], (int, float))
    assert 0 <= calc["overall_wellness"] <= 100
    assert "total_points" in calc
    assert "reasons" in calc

    # Enforces Quote-Grounded rule: No quote = 0 points
    unquoted_evidence = {
        "stress_tension": {"score": 3, "quote": ""}
    }
    calc_unquoted = compute_deterministic_wellness(unquoted_evidence)
    # The stress dimension must have been forced to score 0 because quote was empty
    stress_reason = next(r for r in calc_unquoted["reasons"] if r["key"] == "stress_tension")
    assert stress_reason["score"] == 0


# ---------------------------------------------------------------------------
# 6. TEST XSS ESCAPING IN DOCTOR SUMMARY
# ---------------------------------------------------------------------------
def test_xss_prevention_in_doctor_summary(client):
    """Verifies user-provided values in doctor summary are escaped and not interpreted as HTML."""
    user_data = switch_or_create_local_user("user_xss_test")
    token = user_data["session_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Submit assessment with potential script in payload
    payload = {
        "assessment_type": "phq9",
        "answers": {"1": 1, "2": 1, "9": 0},
    }
    client.post("/api/clinical/assessment", json=payload, headers=headers)

    # Request doctor summary HTML
    res = client.get("/api/clinical/report/doctor-summary", headers=headers)
    assert res.status_code == 200
    html_content = res.text

    # Raw script tags or executable HTML must NOT appear unescaped
    assert "<script>alert" not in html_content
    assert 'onerror="alert' not in html_content
    # The document must be well-formed HTML
    assert "<!DOCTYPE html>" in html_content
    assert "Arogya • Clinical Summary & Triage Report" in html_content
