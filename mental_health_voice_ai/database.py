import os
import sqlite3
import json
import secrets
import uuid
import hmac
import hashlib
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
import numpy as np

AUTH_SECRET = os.getenv("SESSION_SECRET", "arogya_clinical_voice_companion_secret_2026_secure").encode("utf-8")

DB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
DB_PATH = os.path.join(DB_DIR, "mental_health.db")

def get_connection():
    os.makedirs(DB_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_connection()
    cursor = conn.cursor()

    # Users table for Google OAuth 2.0 and profile persistence
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            google_id TEXT UNIQUE,
            email TEXT,
            name TEXT,
            given_name TEXT,
            picture TEXT,
            created_at TIMESTAMP,
            last_login TIMESTAMP
        )
    """)

    # User Auth Web Sessions (HTTP-Only Cookie mapping)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_sessions (
            session_token TEXT PRIMARY KEY,
            user_id TEXT,
            created_at TIMESTAMP,
            expires_at TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    """)

    # Sessions table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            session_id TEXT PRIMARY KEY,
            title TEXT,
            created_at TIMESTAMP,
            last_active TIMESTAMP,
            overall_wellness INTEGER DEFAULT 75,
            dominant_emotion TEXT DEFAULT 'Calm',
            summary TEXT DEFAULT '',
            user_id TEXT DEFAULT 'primary_user'
        )
    """)

    # Messages table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT,
            role TEXT,
            text TEXT,
            timestamp TIMESTAMP,
            audio_path TEXT,
            speech_metrics_json TEXT,
            FOREIGN KEY (session_id) REFERENCES sessions (session_id)
        )
    """)

    # Mental health evaluation records
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS mental_health_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT,
            timestamp TIMESTAMP,
            overall_wellness INTEGER,
            confidence REAL DEFAULT 0.5,
            stress_level INTEGER DEFAULT 0,
            anxiety_index INTEGER DEFAULT 0,
            mood_balance INTEGER DEFAULT 0,
            vocal_vitality INTEGER DEFAULT 0,
            voice_semitone_std REAL,
            dominant_state TEXT DEFAULT 'Reflective',
            reasons_json TEXT DEFAULT '[]',
            sentiment TEXT DEFAULT 'Neutral',
            key_concerns TEXT DEFAULT '[]',
            strengths TEXT DEFAULT '[]',
            clinical_insights TEXT DEFAULT '',
            FOREIGN KEY (session_id) REFERENCES sessions (session_id)
        )
    """)

    # Attempt migration if columns missing
    try:
        cursor.execute("ALTER TABLE sessions ADD COLUMN user_id TEXT DEFAULT 'primary_user'")
    except Exception: pass
    try:
        cursor.execute("UPDATE sessions SET user_id = 'primary_user' WHERE user_id IS NULL OR user_id = ''")
    except Exception: pass
    try:
        cursor.execute("ALTER TABLE users ADD COLUMN preferred_name TEXT")
    except Exception: pass
    try:
        cursor.execute("ALTER TABLE users ADD COLUMN onboarding_completed INTEGER DEFAULT 0")
    except Exception: pass
    try:
        cursor.execute("ALTER TABLE mental_health_records ADD COLUMN confidence REAL DEFAULT 0.5")
    except Exception: pass
    try:
        cursor.execute("ALTER TABLE mental_health_records ADD COLUMN reasons_json TEXT DEFAULT '[]'")
    except Exception: pass
    try:
        cursor.execute("ALTER TABLE mental_health_records ADD COLUMN voice_semitone_std REAL")
    except Exception: pass
    try:
        cursor.execute("ALTER TABLE mental_health_records ADD COLUMN dominant_state TEXT DEFAULT 'Reflective'")
    except Exception: pass

    # User clinical profile table (Persistent Cross-Session Memory)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_clinical_profile (
            user_id TEXT PRIMARY KEY,
            user_name TEXT DEFAULT 'Friend',
            key_context TEXT DEFAULT '',
            recurring_stressors TEXT DEFAULT '[]',
            effective_coping TEXT DEFAULT '[]',
            baseline_wellness REAL DEFAULT 75.0,
            last_updated TIMESTAMP
        )
    """)

    # Seed default primary profile
    cursor.execute("SELECT user_id, user_name FROM user_clinical_profile WHERE user_id = 'primary_user'")
    row = cursor.fetchone()
    now = datetime.now().isoformat()
    if not row:
        cursor.execute("""
            INSERT INTO user_clinical_profile (user_id, user_name, key_context, recurring_stressors, effective_coping, baseline_wellness, last_updated)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            "primary_user",
            "Friend",
            "Seeking conversational companionship and emotional support",
            json.dumps([]),
            json.dumps([]),
            75.0,
            now
        ))
    elif row["user_name"] == "Friend" or not row["user_name"]:
        cursor.execute("""
            UPDATE user_clinical_profile 
            SET user_name = 'Friend',
                key_context = 'Seeking conversational companionship and emotional support',
                recurring_stressors = ?,
                effective_coping = ?
            WHERE user_id = 'primary_user'
        """, (
            json.dumps([]),
            json.dumps([])
        ))

    # Ensure default primary_user exists in users table
    cursor.execute("SELECT id FROM users WHERE id = 'primary_user'")
    if not cursor.fetchone():
        cursor.execute("""
            INSERT INTO users (id, google_id, email, name, given_name, picture, created_at, last_login)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            "primary_user",
            "primary_user_google",
            "logeshwaran@example.com",
            "Logeshwaran",
            "Logeshwaran",
            "",
            now,
            now
        ))

    conn.commit()
    conn.close()

# ---------------------------------------------------------------------------
# USER MANAGEMENT & GOOGLE AUTHENTICATION HELPERS
# ---------------------------------------------------------------------------
def _enrich_user_dict(row) -> Optional[Dict[str, Any]]:
    if not row:
        return None
    user = dict(row)
    pref = user.get("preferred_name")
    given = user.get("given_name")
    full = user.get("name")
    user["display_name"] = pref or given or full or "User"
    user["onboarding_completed"] = bool(user.get("onboarding_completed", 0))
    return user

def upsert_google_user(google_id: str, email: str, name: str, given_name: str = "", picture: str = "") -> Dict[str, Any]:
    conn = get_connection()
    cursor = conn.cursor()
    now = datetime.now().isoformat()
    cursor.execute("SELECT * FROM users WHERE google_id = ? OR (email = ? AND email != '')", (google_id, email))
    row = cursor.fetchone()
    is_new = False
    if row:
        user_id = row["id"]
        cursor.execute("""
            UPDATE users 
            SET google_id = ?, email = ?, name = ?, given_name = ?, picture = ?, last_login = ?
            WHERE id = ?
        """, (google_id, email, name, given_name or name, picture, now, user_id))
    else:
        is_new = True
        user_id = f"usr_{uuid.uuid4().hex[:12]}"
        pref_name = given_name or name or "User"
        cursor.execute("""
            INSERT INTO users (id, google_id, email, name, given_name, preferred_name, picture, onboarding_completed, created_at, last_login)
            VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?, ?)
        """, (user_id, google_id, email, name, given_name or name, pref_name, picture, now, now))

    # Ensure individual clinical memory profile exists for this user_id
    cursor.execute("SELECT user_id, user_name FROM user_clinical_profile WHERE user_id = ?", (user_id,))
    prof_row = cursor.fetchone()
    if not prof_row:
        display_name = given_name or name or "Friend"
        cursor.execute("""
            INSERT INTO user_clinical_profile (user_id, user_name, key_context, recurring_stressors, effective_coping, baseline_wellness, last_updated)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            user_id,
            display_name,
            f"{display_name}'s personal reflections and emotional wellbeing journey",
            json.dumps([]),
            json.dumps([]),
            75.0,
            now
        ))

    conn.commit()
    cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    user_data = _enrich_user_dict(cursor.fetchone())
    conn.close()
    if user_data:
        user_data["is_new_user"] = is_new
    return user_data

def update_user_preferred_name(user_id: str, preferred_name: str) -> Dict[str, Any]:
    """Updates user preferred name during 1-time onboarding and syncs clinical memory profile."""
    conn = get_connection()
    cursor = conn.cursor()
    clean_name = preferred_name.strip() if preferred_name else "Friend"
    cursor.execute("""
        UPDATE users 
        SET preferred_name = ?, onboarding_completed = 1
        WHERE id = ?
    """, (clean_name, user_id))
    cursor.execute("""
        UPDATE user_clinical_profile 
        SET user_name = ?
        WHERE user_id = ?
    """, (clean_name, user_id))
    conn.commit()
    cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    user_data = _enrich_user_dict(cursor.fetchone())
    conn.close()
    return user_data or {}

def switch_or_create_local_user(username: str) -> Dict[str, Any]:
    """
    Creates or logs in a local named user profile for multi-account testing and offline usage.
    Establishes complete memory and chat history isolation per user profile.
    """
    clean_name = username.strip() if username else "Friend"
    safe_slug = "".join(c.lower() if c.isalnum() else "_" for c in clean_name).strip("_")
    if not safe_slug:
        safe_slug = "user"
    user_id = f"usr_{safe_slug}"

    now = datetime.now().isoformat()
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    existing = cursor.fetchone()

    if not existing:
        cursor.execute("""
            INSERT INTO users (id, google_id, email, name, given_name, preferred_name, picture, onboarding_completed, created_at, last_login)
            VALUES (?, NULL, ?, ?, ?, ?, '', 1, ?, ?)
        """, (user_id, f"{safe_slug}@local.ai", clean_name, clean_name.split()[0], clean_name, now, now))
    else:
        cursor.execute("UPDATE users SET last_login = ? WHERE id = ?", (now, user_id))

    conn.commit()
    cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    user_dict = _enrich_user_dict(cursor.fetchone())
    conn.close()

    # Ensure clinical profile exists with correct name
    update_user_clinical_profile(user_id=user_id, user_name=clean_name)

    # Create new session token
    session_token = create_auth_session(user_id=user_id)
    return {
        "user": user_dict,
        "session_token": session_token
    }

def get_all_profiles() -> List[Dict[str, Any]]:
    """Returns a list of all distinct user profiles for quick switching."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, given_name, preferred_name, email, picture, last_login FROM users ORDER BY last_login DESC")
    rows = cursor.fetchall()
    conn.close()
    return [_enrich_user_dict(r) for r in rows]

def create_auth_session(user_id: str, expires_days: int = 90) -> str:
    conn = get_connection()
    cursor = conn.cursor()
    now = datetime.now()
    expires = now + timedelta(days=expires_days)
    
    nonce = secrets.token_hex(16)
    exp_ts = int(expires.timestamp())
    raw_payload = f"{user_id}:{exp_ts}:{nonce}"
    sig = hmac.new(AUTH_SECRET, raw_payload.encode("utf-8"), hashlib.sha256).hexdigest()
    token = f"{raw_payload}:{sig}"

    cursor.execute("""
        INSERT OR REPLACE INTO user_sessions (session_token, user_id, created_at, expires_at)
        VALUES (?, ?, ?, ?)
    """, (token, user_id, now.isoformat(), expires.isoformat()))
    conn.commit()
    conn.close()
    return token

def get_user_by_session_token(token: str) -> Optional[Dict[str, Any]]:
    if not token or not isinstance(token, str):
        return None
    token = token.strip()
    
    conn = get_connection()
    cursor = conn.cursor()
    now = datetime.now().isoformat()
    
    # 1. Direct active session lookup in SQLite
    cursor.execute("""
        SELECT u.* FROM users u
        JOIN user_sessions s ON u.id = s.user_id
        WHERE s.session_token = ? AND s.expires_at > ?
    """, (token, now))
    row = cursor.fetchone()
    if row:
        conn.close()
        return _enrich_user_dict(row)

    # 2. Cryptographic signature verification fallback (survives database restarts or ephemeral clears)
    try:
        parts = token.split(":")
        if len(parts) == 4:
            user_id, exp_ts_str, nonce, sig = parts
            exp_ts = int(exp_ts_str)
            if datetime.now().timestamp() < exp_ts:
                expected_sig = hmac.new(AUTH_SECRET, f"{user_id}:{exp_ts_str}:{nonce}".encode("utf-8"), hashlib.sha256).hexdigest()
                if hmac.compare_digest(sig, expected_sig):
                    cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
                    u_row = cursor.fetchone()
                    if not u_row:
                        # Auto-restore user row if ephemeral db restarted
                        clean_name = user_id.replace("usr_", "").capitalize() or "Friend"
                        cursor.execute("""
                            INSERT INTO users (id, name, given_name, preferred_name, email, onboarding_completed, created_at, last_login)
                            VALUES (?, ?, ?, ?, '', 1, ?, ?)
                        """, (user_id, clean_name, clean_name, clean_name, now, now))
                        conn.commit()
                        cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
                        u_row = cursor.fetchone()

                    if u_row:
                        # Re-index into user_sessions
                        exp_dt = datetime.fromtimestamp(exp_ts)
                        cursor.execute("""
                            INSERT OR REPLACE INTO user_sessions (session_token, user_id, created_at, expires_at)
                            VALUES (?, ?, ?, ?)
                        """, (token, user_id, now, exp_dt.isoformat()))
                        conn.commit()
                        conn.close()
                        return _enrich_user_dict(u_row)
    except Exception as e:
        print(f"[!] Token verification notice: {e}")

    conn.close()
    return None

def revoke_auth_session(token: str) -> bool:
    if not token:
        return False
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM user_sessions WHERE session_token = ?", (token,))
    conn.commit()
    conn.close()
    return True

def get_user_by_id(user_id: str) -> Optional[Dict[str, Any]]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    return _enrich_user_dict(row)

# ---------------------------------------------------------------------------
# SESSION PERSISTENCE & MULTI-USER ISOLATION
# ---------------------------------------------------------------------------
def create_session(session_id: str, title: str = "New Reflection", user_id: str = "primary_user") -> Dict[str, Any]:
    conn = get_connection()
    cursor = conn.cursor()
    now = datetime.now().isoformat()
    cursor.execute("""
        INSERT INTO sessions (session_id, title, created_at, last_active, overall_wellness, dominant_emotion, summary, user_id)
        VALUES (?, ?, ?, ?, NULL, 'Awaiting Reflection', 'New reflection started.', ?)
    """, (session_id, title, now, now, user_id))
    conn.commit()
    conn.close()
    return {
        "session_id": session_id,
        "title": title,
        "created_at": now,
        "overall_wellness": None,
        "dominant_emotion": "Awaiting Reflection",
        "user_id": user_id
    }

def get_all_sessions(user_id: Optional[str] = None) -> List[Dict[str, Any]]:
    conn = get_connection()
    cursor = conn.cursor()
    if user_id:
        cursor.execute("""
            SELECT session_id, title, created_at, last_active, overall_wellness, dominant_emotion, summary, user_id
            FROM sessions
            WHERE user_id = ?
            ORDER BY last_active DESC
        """, (user_id,))
    else:
        cursor.execute("""
            SELECT session_id, title, created_at, last_active, overall_wellness, dominant_emotion, summary, user_id
            FROM sessions
            ORDER BY last_active DESC
        """)
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def get_session(session_id: str, user_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
    conn = get_connection()
    cursor = conn.cursor()
    if user_id:
        cursor.execute("SELECT * FROM sessions WHERE session_id = ? AND user_id = ?", (session_id, user_id))
    else:
        cursor.execute("SELECT * FROM sessions WHERE session_id = ?", (session_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

def update_session_meta(session_id: str, title: Optional[str] = None, wellness: Optional[int] = None, emotion: Optional[str] = None, summary: Optional[str] = None):
    conn = get_connection()
    cursor = conn.cursor()
    now = datetime.now().isoformat()

    updates = ["last_active = ?"]
    params = [now]

    if title:
        updates.append("title = ?")
        params.append(title)
    if wellness is not None:
        updates.append("overall_wellness = ?")
        params.append(wellness)
    if emotion:
        updates.append("dominant_emotion = ?")
        params.append(emotion)
    if summary:
        updates.append("summary = ?")
        params.append(summary)

    params.append(session_id)
    cursor.execute(f"UPDATE sessions SET {', '.join(updates)} WHERE session_id = ?", params)
    conn.commit()
    conn.close()

def rename_session(session_id: str, new_title: str, user_id: Optional[str] = None) -> bool:
    conn = get_connection()
    cursor = conn.cursor()
    if user_id:
        cursor.execute("UPDATE sessions SET title = ? WHERE session_id = ? AND user_id = ?", (new_title.strip(), session_id, user_id))
    else:
        cursor.execute("UPDATE sessions SET title = ? WHERE session_id = ?", (new_title.strip(), session_id))
    conn.commit()
    conn.close()
    return True

def delete_session(session_id: str, user_id: Optional[str] = None) -> bool:
    conn = get_connection()
    cursor = conn.cursor()
    if user_id:
        cursor.execute("SELECT session_id FROM sessions WHERE session_id = ? AND user_id = ?", (session_id, user_id))
        if not cursor.fetchone():
            conn.close()
            return False
    cursor.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
    cursor.execute("DELETE FROM mental_health_records WHERE session_id = ?", (session_id,))
    cursor.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))
    conn.commit()
    conn.close()
    return True

def save_message(session_id: str, role: str, text: str, audio_path: Optional[str] = None, speech_metrics: Optional[Dict[str, Any]] = None, user_id: Optional[str] = None):

    conn = get_connection()
    cursor = conn.cursor()
    now = datetime.now().isoformat()
    metrics_str = json.dumps(speech_metrics) if speech_metrics else None

    # Guarantee session exists in sessions table for foreign key and history integrity
    target_user = user_id or 'primary_user'
    cursor.execute("""
        INSERT OR IGNORE INTO sessions (session_id, title, created_at, last_active, user_id)
        VALUES (?, 'Check-in', ?, ?, ?)
    """, (session_id, now, now, target_user))

    cursor.execute("""
        INSERT INTO messages (session_id, role, text, timestamp, audio_path, speech_metrics_json)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (session_id, role, text, now, audio_path, metrics_str))

    if user_id:
        cursor.execute("UPDATE sessions SET last_active = ?, user_id = COALESCE(user_id, ?) WHERE session_id = ?", (now, user_id, session_id))
    else:
        cursor.execute("UPDATE sessions SET last_active = ? WHERE session_id = ?", (now, session_id))
    conn.commit()
    conn.close()

def get_session_messages(session_id: str) -> List[Dict[str, Any]]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT role, text, timestamp, audio_path, speech_metrics_json
        FROM messages
        WHERE session_id = ?
        ORDER BY id ASC
    """, (session_id,))
    rows = cursor.fetchall()
    conn.close()

    result = []
    for row in rows:
        item = dict(row)
        if item.get("speech_metrics_json"):
            try:
                item["speech_metrics"] = json.loads(item["speech_metrics_json"])
            except Exception:
                item["speech_metrics"] = None
        else:
            item["speech_metrics"] = None
        result.append(item)
    return result

def save_mental_health_record(record: Dict[str, Any]):
    conn = get_connection()
    cursor = conn.cursor()
    now = datetime.now().isoformat()
    cursor.execute("""
        INSERT INTO mental_health_records (
            session_id, timestamp, overall_wellness, confidence, stress_level, anxiety_index,
            mood_balance, vocal_vitality, voice_semitone_std, dominant_state, reasons_json,
            sentiment, key_concerns, strengths, clinical_insights
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        record.get("session_id"),
        now,
        record.get("overall_wellness"),
        record.get("confidence", 0.5),
        record.get("stress_level", 0),
        record.get("anxiety_index", 0),
        record.get("mood_balance", 0),
        record.get("vocal_vitality", 0),
        record.get("voice_semitone_std"),
        record.get("dominant_state", "Reflective"),
        json.dumps(record.get("reasons", [])),
        record.get("dominant_state", "Neutral"),
        json.dumps(record.get("key_concerns", [])),
        json.dumps(record.get("strengths", [])),
        record.get("observed_resilience", "")
    ))
    conn.commit()
    conn.close()

def get_latest_mental_health_record(session_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
    conn = get_connection()
    cursor = conn.cursor()
    if session_id:
        cursor.execute("""
            SELECT * FROM mental_health_records
            WHERE session_id = ?
            ORDER BY id DESC LIMIT 1
        """, (session_id,))
    else:
        cursor.execute("""
            SELECT * FROM mental_health_records
            ORDER BY id DESC LIMIT 1
        """)
    row = cursor.fetchone()
    conn.close()
    if not row:
        return None
    d = dict(row)
    try:
        d["reasons"] = json.loads(d["reasons_json"]) if d.get("reasons_json") else []
    except Exception:
        d["reasons"] = []
    try:
        d["key_concerns"] = json.loads(d["key_concerns"]) if d.get("key_concerns") else []
    except Exception:
        d["key_concerns"] = []
    try:
        d["strengths"] = json.loads(d["strengths"]) if d.get("strengths") else []
    except Exception:
        d["strengths"] = []
    return d

def get_session_count(user_id: Optional[str] = None) -> int:
    conn = get_connection()
    cursor = conn.cursor()
    if user_id:
        cursor.execute("SELECT COUNT(*) FROM sessions WHERE user_id = ?", (user_id,))
    else:
        cursor.execute("SELECT COUNT(*) FROM sessions")
    count = cursor.fetchone()[0]
    conn.close()
    return count

def get_user_baseline_stats(user_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Computes running baseline statistics (mean and standard deviation)
    from historical records to calculate z-scores in code.
    Filters by user_id if provided.
    """
    conn = get_connection()
    cursor = conn.cursor()
    if user_id:
        cursor.execute("""
            SELECT r.overall_wellness, r.voice_semitone_std
            FROM mental_health_records r
            JOIN sessions s ON r.session_id = s.session_id
            WHERE s.user_id = ? AND r.overall_wellness IS NOT NULL
            ORDER BY r.id DESC LIMIT 30
        """, (user_id,))
    else:
        cursor.execute("""
            SELECT overall_wellness, voice_semitone_std
            FROM mental_health_records
            WHERE overall_wellness IS NOT NULL
            ORDER BY id DESC LIMIT 30
        """)
    rows = cursor.fetchall()
    conn.close()

    if not rows or len(rows) < 3:
        return {"wellness_mean": 75.0, "wellness_std": 10.0, "voice_mean": None, "voice_std": None}

    wellness_vals = [r["overall_wellness"] for r in rows if r["overall_wellness"] is not None]
    voice_vals = [r["voice_semitone_std"] for r in rows if r["voice_semitone_std"] is not None]

    w_mean = float(np.mean(wellness_vals)) if wellness_vals else 75.0
    w_std = float(np.std(wellness_vals)) if len(wellness_vals) > 1 and np.std(wellness_vals) > 0 else 10.0

    v_mean = float(np.mean(voice_vals)) if len(voice_vals) >= 3 else None
    v_std = float(np.std(voice_vals)) if len(voice_vals) >= 3 and np.std(voice_vals) > 0 else None

    return {
        "wellness_mean": w_mean,
        "wellness_std": w_std,
        "voice_mean": v_mean,
        "voice_std": v_std
    }

def get_aggregated_mental_health_insights(session_id: Optional[str] = None, user_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Computes cumulative average mental health score and compiles verbatim reasons
    across all exchanges within the session and across all conversations for this user.
    """
    conn = get_connection()
    cursor = conn.cursor()

    # 1. Fetch all records for this session
    session_records = []
    if session_id:
        cursor.execute("""
            SELECT * FROM mental_health_records
            WHERE session_id = ?
            ORDER BY id ASC
        """, (session_id,))
        session_records = [dict(r) for r in cursor.fetchall()]

    # 2. Fetch historical records across sessions for this user
    if user_id:
        cursor.execute("""
            SELECT r.overall_wellness, r.dominant_state, r.voice_semitone_std
            FROM mental_health_records r
            JOIN sessions s ON r.session_id = s.session_id
            WHERE s.user_id = ? AND r.overall_wellness IS NOT NULL
            ORDER BY r.id DESC LIMIT 100
        """, (user_id,))
    else:
        cursor.execute("""
            SELECT overall_wellness, dominant_state, voice_semitone_std
            FROM mental_health_records
            WHERE overall_wellness IS NOT NULL
            ORDER BY id DESC LIMIT 100
        """)
    all_time_rows = [dict(r) for r in cursor.fetchall()]
    conn.close()

    active_records = session_records if session_records else []
    
    # Calculate Session Average Wellness
    session_wellness_vals = [r["overall_wellness"] for r in active_records if r.get("overall_wellness") is not None]
    if session_wellness_vals:
        session_avg = int(round(float(np.mean(session_wellness_vals))))
    else:
        session_avg = None

    # Calculate All-Time Global Average Wellness
    all_wellness_vals = [r["overall_wellness"] for r in all_time_rows if r.get("overall_wellness") is not None]
    all_time_avg = int(round(float(np.mean(all_wellness_vals)))) if all_wellness_vals else None

    # Calculate Confidence based on exchanges and sessions
    n_exchanges = len(active_records)
    n_all_time = len(all_wellness_vals)
    if n_exchanges == 0 and n_all_time == 0:
        confidence = 0.0
    else:
        confidence = round(min(1.0, max(0.35, (n_exchanges * 0.15) + (n_all_time * 0.04))), 2)

    # Compile Reasons & Quotes Across All Exchanges
    dim_map = {
        "stress_tension": {"label": "Stress & Pressure", "scores": [], "quotes": []},
        "worry_apprehension": {"label": "Worry & Apprehension", "scores": [], "quotes": []},
        "fatigue_exhaustion": {"label": "Fatigue & Low Energy", "scores": [], "quotes": []},
        "emotional_heaviness": {"label": "Emotional Heaviness", "scores": [], "quotes": []},
        "loneliness_isolation": {"label": "Loneliness & Isolation", "scores": [], "quotes": []},
        "sleep_restlessness": {"label": "Sleep & Restlessness", "scores": [], "quotes": []},
        "rumination_overwhelm": {"label": "Overthinking & Overwhelm", "scores": [], "quotes": []}
    }

    dominant_states = []
    semitones = []

    for rec in active_records:
        if rec.get("dominant_state"):
            dominant_states.append(rec["dominant_state"])
        if rec.get("voice_semitone_std") is not None:
            semitones.append(rec["voice_semitone_std"])

        try:
            reasons = json.loads(rec.get("reasons_json", "[]"))
        except Exception:
            reasons = []

        for r in reasons:
            k = r.get("key")
            label = r.get("label", "")
            matched_key = None
            if k in dim_map:
                matched_key = k
            else:
                for d_k, d_v in dim_map.items():
                    if d_v["label"].lower() in label.lower() or label.lower() in d_v["label"].lower():
                        matched_key = d_k
                        break

            if matched_key:
                score = r.get("score", 0)
                dim_map[matched_key]["scores"].append(score)
                q = (r.get("quote") or "").strip()
                if q and q.lower() not in ["no explicit mention in statement", "no explicit mention", ""]:
                    if q not in dim_map[matched_key]["quotes"]:
                        dim_map[matched_key]["quotes"].append(q)

    # Build compiled reasons
    compiled_reasons = []
    for key, data in dim_map.items():
        scores = data["scores"]
        quotes = data["quotes"]
        if scores:
            avg_score = round(float(np.mean(scores)), 1)
        else:
            avg_score = 0.0

        if quotes:
            clean_quotes = [q.strip('\"\'') for q in quotes if q.strip('\"\'')]
            quote_display = " • ".join([f'"{cq}"' for cq in clean_quotes]) if clean_quotes else "No explicit mention across conversations"
        else:
            quote_display = "No explicit mention across conversations"

        compiled_reasons.append({
            "key": key,
            "label": data["label"],
            "score": avg_score,
            "max_score": 3,
            "quote": quote_display,
            "quote_count": len(quotes)
        })

    # Most common dominant state
    if dominant_states:
        from collections import Counter
        most_common_state = Counter(dominant_states).most_common(1)[0][0]
    else:
        most_common_state = "Reflective"

    avg_semitone = round(float(np.mean(semitones)), 2) if semitones else None

    # Status badge text
    if session_avg is None:
        badge_text = "Awaiting Reflection"
    elif session_avg >= 70:
        badge_text = "Grounded & Balanced"
    elif session_avg >= 50:
        badge_text = "Mild Emotional Strain"
    elif session_avg >= 35:
        badge_text = "Elevated Pressure"
    else:
        badge_text = "High Distress"

    return {
        "session_id": session_id,
        "overall_wellness": session_avg,
        "all_time_wellness": all_time_avg,
        "confidence": confidence,
        "dominant_state": most_common_state,
        "wellness_badge": badge_text,
        "reasons": compiled_reasons,
        "voice_semitone_std": avg_semitone,
        "total_reflections": n_exchanges,
        "all_time_reflections": n_all_time,
        "note": f"Cumulative average across {n_exchanges} reflection{'s' if n_exchanges != 1 else ''} (All-Time Baseline: {all_time_avg}/100)"
    }

def get_session_report(session_id: str, user_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
    sess = get_session(session_id, user_id=user_id)
    if not sess:
        return None
    messages = get_session_messages(session_id)
    aggregated = get_aggregated_mental_health_insights(session_id, user_id=user_id)

    return {
        "session_id": session_id,
        "title": sess.get("title", "Check-in"),
        "created_at": sess.get("created_at"),
        "overall_wellness": aggregated.get("overall_wellness") if aggregated.get("overall_wellness") is not None else sess.get("overall_wellness"),
        "all_time_wellness": aggregated.get("all_time_wellness"),
        "confidence": aggregated.get("confidence", 0.5),
        "dominant_state": aggregated.get("dominant_state", sess.get("dominant_emotion", "Reflective")),
        "reasons": aggregated.get("reasons", []),
        "voice_semitone_std": aggregated.get("voice_semitone_std"),
        "observed_resilience": sess.get("summary", "Open reflective dialogue"),
        "total_reflections": aggregated.get("total_reflections", 0),
        "transcript": [{"role": m["role"], "text": m["text"], "timestamp": m["timestamp"]} for m in messages]
    }

def get_user_clinical_profile(user_id: str = "primary_user") -> Dict[str, Any]:
    """
    Retrieves the persistent longitudinal clinical profile, recurring stressors,
    and effective coping mechanisms across all sessions for a specific user.
    Strictly isolated per user_id.
    """
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT user_id, user_name, key_context, recurring_stressors, effective_coping, baseline_wellness, last_updated
        FROM user_clinical_profile
        WHERE user_id = ?
    """, (user_id,))
    row = cursor.fetchone()

    # Look up actual registered user record for accurate display name
    cursor.execute("SELECT name, given_name, preferred_name FROM users WHERE id = ?", (user_id,))
    user_row = cursor.fetchone()
    conn.close()

    resolved_name = "Friend"
    if user_row:
        resolved_name = user_row["preferred_name"] or user_row["given_name"] or user_row["name"] or "Friend"

    if not row:
        return {
            "user_id": user_id,
            "user_name": resolved_name,
            "key_context": "Member seeking conversational companionship and emotional support",
            "recurring_stressors": [],
            "effective_coping": ["Guided box breathing (4-4-4-4)", "Gentle mindful reflection", "Empathetic companion dialogue"],
            "baseline_wellness": 75.0,
            "last_updated": datetime.now().isoformat()
        }

    d = dict(row)
    if not d.get("user_name") or d.get("user_name") in ["Friend", "User"]:
        d["user_name"] = resolved_name

    try:
        d["recurring_stressors"] = json.loads(d["recurring_stressors"]) if d.get("recurring_stressors") else []
    except Exception:
        d["recurring_stressors"] = []
    try:
        d["effective_coping"] = json.loads(d["effective_coping"]) if d.get("effective_coping") else []
    except Exception:
        d["effective_coping"] = []
    return d

def update_user_clinical_profile(
    user_id: str = "primary_user",
    user_name: Optional[str] = None,
    key_context: Optional[str] = None,
    new_stressor: Optional[str] = None,
    new_coping: Optional[str] = None,
    baseline_wellness: Optional[float] = None
) -> Dict[str, Any]:
    """
    Updates or appends clinical memory entities (name, recurring stressors, effective coping, context notes).
    Ensures strict per-user isolation without hardcoded names.
    """
    curr = get_user_clinical_profile(user_id)
    stressors = curr.get("recurring_stressors", [])
    coping = curr.get("effective_coping", [])
    context = curr.get("key_context", "")

    if new_stressor and isinstance(new_stressor, str) and len(new_stressor.strip()) > 3:
        clean_s = new_stressor.strip()
        if not any(clean_s.lower() in s.lower() or s.lower() in clean_s.lower() for s in stressors):
            stressors.append(clean_s)

    if new_coping and isinstance(new_coping, str) and len(new_coping.strip()) > 3:
        clean_c = new_coping.strip()
        if not any(clean_c.lower() in c.lower() or c.lower() in clean_c.lower() for c in coping):
            coping.append(clean_c)

    if key_context and isinstance(key_context, str) and len(key_context.strip()) > 3:
        context = key_context.strip()

    name = user_name.strip() if (user_name and isinstance(user_name, str) and len(user_name.strip()) > 1) else curr.get("user_name", "Friend")
    b_well = baseline_wellness if baseline_wellness is not None else curr.get("baseline_wellness", 75.0)
    now = datetime.now().isoformat()

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO user_clinical_profile (user_id, user_name, key_context, recurring_stressors, effective_coping, baseline_wellness, last_updated)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(user_id) DO UPDATE SET
            user_name = excluded.user_name,
            key_context = excluded.key_context,
            recurring_stressors = excluded.recurring_stressors,
            effective_coping = excluded.effective_coping,
            baseline_wellness = excluded.baseline_wellness,
            last_updated = excluded.last_updated
    """, (user_id, name, context, json.dumps(stressors), json.dumps(coping), b_well, now))
    conn.commit()
    conn.close()

    return get_user_clinical_profile(user_id)

def get_recent_session_memory_anchor(user_id: str = "primary_user", exclude_session_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Retrieves the most recent meaningful session topic, user quotes, and recurring stressors
    for memory-anchored greeting recall across days.
    Ensures strict per-user isolation: only inspects sessions and messages belonging to user_id.
    """
    profile = get_user_clinical_profile(user_id)
    conn = get_connection()
    cursor = conn.cursor()

    # Fetch the most recent past session that actually contains user speech
    cursor.execute("""
        SELECT s.session_id, s.title, s.created_at, s.overall_wellness, s.dominant_emotion, s.summary
        FROM sessions s
        WHERE s.user_id = ?
          AND (? IS NULL OR s.session_id != ?)
          AND EXISTS (SELECT 1 FROM messages m WHERE m.session_id = s.session_id AND m.role = 'user')
        ORDER BY s.last_active DESC, s.created_at DESC
        LIMIT 1
    """, (user_id, exclude_session_id, exclude_session_id))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return {"has_history": False, "profile": profile}

    sess = dict(row)
    # Fetch all user messages from that session to find substantive topics/concerns
    cursor.execute("""
        SELECT text FROM messages
        WHERE session_id = ? AND role = 'user'
        ORDER BY id ASC
    """, (sess["session_id"],))
    raw_msgs = [r["text"].strip() for r in cursor.fetchall() if r["text"] and len(r["text"].strip()) > 0]
    conn.close()

    trivial_set = {
        "hi", "hello", "hey", "yes", "no", "ok", "okay", "thanks", "thank you",
        "bye", "goodbye", "good night", "vanakkam", "seri", "poidu varen"
    }
    # Substantive messages: not trivial greetings/goodbyes
    substantive = [m for m in raw_msgs if m.lower().strip(" .,!?-") not in trivial_set and len(m) > 6]
    if not substantive:
        substantive = raw_msgs

    core_topic = substantive[0] if substantive else (sess.get("title") or "")
    latest_remark = substantive[-1] if substantive else ""
    key_remarks = substantive[:3] if len(substantive) <= 3 else [substantive[0], substantive[-1]]

    clean_summary = sess.get("summary", "")
    if clean_summary == "Initial conversation started.":
        clean_summary = ""

    return {
        "has_history": True,
        "profile": profile,
        "title": sess.get("title"),
        "summary": clean_summary,
        "dominant_emotion": sess.get("dominant_emotion"),
        "core_topic": core_topic,
        "latest_remark": latest_remark,
        "recent_remarks": key_remarks
    }

def get_historical_context(current_session_id: Optional[str] = None, user_id: str = "primary_user", limit: int = 4) -> str:
    """
    Retrieves cross-session memory and clinical trends across past conversations,
    incorporating the persistent clinical profile so Arogya naturally references long-term stressors.
    Strictly isolates data to the requested user_id.
    """
    profile = get_user_clinical_profile(user_id)
    name = profile.get("user_name", "Friend")
    stressors_list = profile.get("recurring_stressors", [])
    stressors_text = ", ".join(stressors_list) if stressors_list else "None recorded yet (First-time user or baseline)"
    coping_list = profile.get("effective_coping", [])
    coping_text = ", ".join(coping_list) if coping_list else "None recorded yet"
    context_text = profile.get("key_context") or "Member seeking conversational companionship and emotional support"

    lines = [
        "--- LONG-TERM CLINICAL PROFILE & RECURRING STRESSOR MEMORY ---",
        f"• User's Name: {name} (Address the user warmly as {name})",
        f"• User Profile & Context: {context_text}",
        f"• Recurring Known Stressors: {stressors_text}",
        f"• Effective Coping Strategies: {coping_text}",
        f"• Baseline Wellness Standard: {profile.get('baseline_wellness', 75)}/100",
        "",
        "--- PAST CONVERSATIONAL MEMORY & RECENT SESSIONS ---"
    ]

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT session_id, title, created_at, overall_wellness, dominant_emotion, summary
        FROM sessions
        WHERE (session_id != ? OR ? IS NULL) 
          AND user_id = ?
          AND EXISTS (SELECT 1 FROM messages m WHERE m.session_id = sessions.session_id AND m.role = 'user')
        ORDER BY last_active DESC
        LIMIT ?
    """, (current_session_id or "", current_session_id or "", user_id, limit))
    past_sessions = cursor.fetchall()

    if not past_sessions:
        conn.close()
        lines.append("No previous sessions recorded. This is the first interaction with this user.")
        return "\n".join(lines)

    trivial_set = {"hi", "hello", "hey", "yes", "no", "ok", "okay", "thanks", "thank you", "bye", "goodbye", "good night"}
    for s in past_sessions:
        s_id = s["session_id"]
        cursor.execute("""
            SELECT text FROM messages
            WHERE session_id = ? AND role = 'user'
            ORDER BY id ASC
        """, (s_id,))
        all_u_msgs = [r["text"].strip() for r in cursor.fetchall() if r["text"]]
        substantive = [m for m in all_u_msgs if m.lower().strip(" .,!?-") not in trivial_set and len(m) > 6]
        highlight_msgs = substantive[:2] if substantive else all_u_msgs[:2]

        s_summary = s["summary"]
        if s_summary == "Initial conversation started.":
            s_summary = "Conversation underway."

        lines.append(
            f"• Session '{s['title']}' ({s['created_at'][:10]}): "
            f"Wellness Score: {s['overall_wellness']}/100, Tone: {s['dominant_emotion']}. "
            f"Summary: {s_summary} "
            f"Key user remarks: {' | '.join(highlight_msgs) if highlight_msgs else 'None recorded'}"
        )

    conn.close()
    return "\n".join(lines)

def get_analytics_summary(user_id: str = "primary_user") -> Dict[str, Any]:
    """
    Computes comprehensive longitudinal clinical analytics across all sessions for a specific user:
    - Multi-session time-series scores & trajectories
    - Symptom distributions with verbatim evidence quotes
    - Pitch stability and prosodic biomarker metrics
    - Long-term clinical profile & recurring stressor clusters
    """
    conn = get_connection()
    cursor = conn.cursor()

    # 1. Fetch all sessions in chronological order for this user (strictly isolated per user_id)
    cursor.execute("""
        SELECT session_id, title, created_at, last_active, overall_wellness, dominant_emotion, summary
        FROM sessions
        WHERE user_id = ?
        ORDER BY created_at ASC
    """, (user_id,))
    session_rows = [dict(r) for r in cursor.fetchall()]

    # 2. Fetch all mental health records for this user's sessions
    cursor.execute("""
        SELECT r.* FROM mental_health_records r
        JOIN sessions s ON r.session_id = s.session_id
        WHERE s.user_id = ?
        ORDER BY r.id ASC
    """, (user_id,))
    all_records = [dict(r) for r in cursor.fetchall()]
    conn.close()

    profile = get_user_clinical_profile(user_id)

    # Map records by session_id
    records_by_session: Dict[str, List[Dict[str, Any]]] = {}
    for r in all_records:
        s_id = r.get("session_id")
        if s_id:
            if s_id not in records_by_session:
                records_by_session[s_id] = []
            records_by_session[s_id].append(r)

    # Symptom tracker accumulators across all time
    dim_accum = {
        "stress_tension": {"label": "Stress & Pressure", "scores": [], "quotes": []},
        "worry_apprehension": {"label": "Worry & Apprehension", "scores": [], "quotes": []},
        "fatigue_exhaustion": {"label": "Fatigue & Low Energy", "scores": [], "quotes": []},
        "emotional_heaviness": {"label": "Emotional Heaviness", "scores": [], "quotes": []},
        "loneliness_isolation": {"label": "Loneliness & Isolation", "scores": [], "quotes": []},
        "sleep_restlessness": {"label": "Sleep & Restlessness", "scores": [], "quotes": []},
        "rumination_overwhelm": {"label": "Overthinking & Overwhelm", "scores": [], "quotes": []}
    }

    timeline_points = []
    semitones_all = []
    observed_strengths = []

    for s in session_rows:
        s_id = s["session_id"]
        recs = records_by_session.get(s_id, [])

        w_scores = [r["overall_wellness"] for r in recs if r.get("overall_wellness") is not None]
        s_semis = [r["voice_semitone_std"] for r in recs if r.get("voice_semitone_std") is not None]
        semitones_all.extend(s_semis)

        session_stress = []
        session_worry = []
        session_fatigue = []
        session_heaviness = []
        session_quotes = []

        for r in recs:
            if r.get("strengths"):
                try:
                    st_list = json.loads(r["strengths"])
                    for item in st_list:
                        if item and item not in observed_strengths:
                            observed_strengths.append(item)
                except Exception:
                    pass

            if r.get("clinical_insights") and r["clinical_insights"] not in observed_strengths:
                observed_strengths.append(r["clinical_insights"])

            try:
                reasons = json.loads(r.get("reasons_json", "[]"))
            except Exception:
                reasons = []

            for r_item in reasons:
                k = r_item.get("key")
                score = r_item.get("score", 0)
                q = (r_item.get("quote") or "").strip()

                if k in dim_accum:
                    dim_accum[k]["scores"].append(score)
                    if q and q.lower() not in ["no explicit mention in statement", "no explicit mention", ""]:
                        if q not in dim_accum[k]["quotes"]:
                            dim_accum[k]["quotes"].append(q)
                        if q not in session_quotes:
                            session_quotes.append(q)

                if k == "stress_tension":
                    session_stress.append(score)
                elif k == "worry_apprehension":
                    session_worry.append(score)
                elif k == "fatigue_exhaustion":
                    session_fatigue.append(score)
                elif k == "emotional_heaviness":
                    session_heaviness.append(score)

        session_wellness = int(round(float(np.mean(w_scores)))) if w_scores else s.get("overall_wellness")
        avg_pitch = round(float(np.mean(s_semis)), 2) if s_semis else None

        timeline_points.append({
            "session_id": s_id,
            "title": s.get("title", "Reflection"),
            "date": s.get("created_at", "")[:10],
            "time": s.get("created_at", "")[11:16] if len(s.get("created_at", "")) >= 16 else "",
            "wellness": session_wellness,
            "dominant_emotion": s.get("dominant_emotion", "Reflective"),
            "reflections_count": len(recs),
            "stress_avg": round(float(np.mean(session_stress)), 1) if session_stress else 0.0,
            "worry_avg": round(float(np.mean(session_worry)), 1) if session_worry else 0.0,
            "fatigue_avg": round(float(np.mean(session_fatigue)), 1) if session_fatigue else 0.0,
            "heaviness_avg": round(float(np.mean(session_heaviness)), 1) if session_heaviness else 0.0,
            "voice_semitone": avg_pitch,
            "summary": s.get("summary", ""),
            "quotes": session_quotes[:4]
        })

    # Overall KPIs (Strictly per user, no hardcoded fake scores)
    total_sessions = len(session_rows)
    total_reflections = len(all_records)
    valid_wellness = [p["wellness"] for p in timeline_points if p.get("wellness") is not None]

    if valid_wellness:
        lifetime_avg = int(round(float(np.mean(valid_wellness))))
        recent_slice = valid_wellness[-3:] if len(valid_wellness) >= 3 else valid_wellness
        recent_avg = int(round(float(np.mean(recent_slice))))
        baseline = profile.get("baseline_wellness", 75.0)
        delta = round(recent_avg - baseline, 1)

        if delta >= 3.0:
            trajectory_status = "Improving"
            trajectory_desc = f"+{delta} pts vs baseline. Emotional regulation and vitality are trending positively."
        elif delta <= -3.0:
            trajectory_status = "Elevated Strain"
            trajectory_desc = f"{delta} pts vs baseline. Recent dialogues indicate notable stressors or fatigue."
        else:
            trajectory_status = "Steady & Balanced"
            trajectory_desc = f"{delta:+} pts vs baseline. Consistent emotional equilibrium maintained."
    else:
        baseline = None
        lifetime_avg = None
        recent_avg = None
        delta = 0.0
        trajectory_status = "New Account"
        trajectory_desc = "No check-ins recorded yet for your account. Complete your first reflection with Arogya to generate your personal score."

    # Compiled symptom distribution metrics
    symptom_distributions = []
    for k, data in dim_accum.items():
        s_list = data["scores"]
        q_list = data["quotes"]
        avg_s = round(float(np.mean(s_list)), 2) if s_list else 0.0
        symptom_distributions.append({
            "key": k,
            "label": data["label"],
            "average_score": avg_s,
            "max_score": 3.0,
            "quote_count": len(q_list),
            "quotes": q_list[:3]
        })

    avg_semitone_lifetime = round(float(np.mean(semitones_all)), 2) if semitones_all else None

    return {
        "kpis": {
            "lifetime_wellness": lifetime_avg,
            "recent_wellness": recent_avg,
            "baseline_wellness": baseline,
            "trajectory_delta": delta,
            "trajectory_status": trajectory_status,
            "trajectory_desc": trajectory_desc,
            "total_sessions": total_sessions,
            "total_reflections": total_reflections,
            "average_voice_semitones": avg_semitone_lifetime
        },
        "profile": profile,
        "timeline": timeline_points,
        "symptoms": symptom_distributions,
        "observed_strengths": observed_strengths[:6]
    }

# Initialize on import
init_db()

