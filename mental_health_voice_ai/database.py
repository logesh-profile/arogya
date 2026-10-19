import os
import sqlite3
import json
from datetime import datetime
from typing import List, Dict, Any, Optional
import numpy as np

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

    # Sessions table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            session_id TEXT PRIMARY KEY,
            title TEXT,
            created_at TIMESTAMP,
            last_active TIMESTAMP,
            overall_wellness INTEGER DEFAULT 75,
            dominant_emotion TEXT DEFAULT 'Calm',
            summary TEXT DEFAULT ''
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

    # User clinical profile table (Phase 2 Persistent Cross-Session Memory)
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

    # Seed or upgrade default primary profile
    cursor.execute("SELECT user_id, user_name FROM user_clinical_profile WHERE user_id = 'primary_user'")
    row = cursor.fetchone()
    now = datetime.now().isoformat()
    if not row:
        cursor.execute("""
            INSERT INTO user_clinical_profile (user_id, user_name, key_context, recurring_stressors, effective_coping, baseline_wellness, last_updated)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            "primary_user",
            "Logeshwaran",
            "College student preparing for semester exams, software projects, and campus placement interviews",
            json.dumps(["Semester exams and academic pressure", "Office workload and project deadlines", "Sleep deprivation and fatigue", "Campus placement anxiety"]),
            json.dumps(["Guided box breathing (4-4-4-4)", "Taking short walks", "Reflective spoken pauses", "Listening to calming music"]),
            75.0,
            now
        ))
    elif row["user_name"] == "Friend" or not row["user_name"]:
        cursor.execute("""
            UPDATE user_clinical_profile 
            SET user_name = 'Logeshwaran',
                key_context = 'College student preparing for semester exams, software projects, and campus placement interviews',
                recurring_stressors = ?,
                effective_coping = ?
            WHERE user_id = 'primary_user'
        """, (
            json.dumps(["Semester exams and academic pressure", "Office workload and project deadlines", "Sleep deprivation and fatigue", "Campus placement anxiety"]),
            json.dumps(["Guided box breathing (4-4-4-4)", "Taking short walks", "Reflective spoken pauses", "Listening to calming music"])
        ))

    conn.commit()
    conn.close()

def create_session(session_id: str, title: str = "New Assessment") -> Dict[str, Any]:
    conn = get_connection()
    cursor = conn.cursor()
    now = datetime.now().isoformat()
    cursor.execute("""
        INSERT INTO sessions (session_id, title, created_at, last_active, overall_wellness, dominant_emotion, summary)
        VALUES (?, ?, ?, ?, 75, 'Calm', 'Initial conversation started.')
    """, (session_id, title, now, now))
    conn.commit()
    conn.close()
    return {
        "session_id": session_id,
        "title": title,
        "created_at": now,
        "overall_wellness": 75,
        "dominant_emotion": "Calm"
    }

def get_all_sessions() -> List[Dict[str, Any]]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT session_id, title, created_at, last_active, overall_wellness, dominant_emotion, summary
        FROM sessions
        ORDER BY last_active DESC
    """)
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def get_session(session_id: str) -> Optional[Dict[str, Any]]:
    conn = get_connection()
    cursor = conn.cursor()
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

def rename_session(session_id: str, new_title: str) -> bool:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE sessions SET title = ? WHERE session_id = ?", (new_title.strip(), session_id))
    conn.commit()
    conn.close()
    return True

def delete_session(session_id: str) -> bool:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
    cursor.execute("DELETE FROM mental_health_records WHERE session_id = ?", (session_id,))
    cursor.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))
    conn.commit()
    conn.close()
    return True

def save_message(session_id: str, role: str, text: str, audio_path: Optional[str] = None, speech_metrics: Optional[Dict[str, Any]] = None):

    conn = get_connection()
    cursor = conn.cursor()
    now = datetime.now().isoformat()
    metrics_str = json.dumps(speech_metrics) if speech_metrics else None

    cursor.execute("""
        INSERT INTO messages (session_id, role, text, timestamp, audio_path, speech_metrics_json)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (session_id, role, text, now, audio_path, metrics_str))

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

def get_session_count() -> int:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM sessions")
    count = cursor.fetchone()[0]
    conn.close()
    return count

def get_user_baseline_stats() -> Dict[str, Any]:
    """
    Computes running baseline statistics (mean and standard deviation)
    from historical records to calculate z-scores in code.
    """
    conn = get_connection()
    cursor = conn.cursor()
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

def get_aggregated_mental_health_insights(session_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Computes cumulative average mental health score and compiles verbatim reasons
    across all exchanges within the session and across all conversations.
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

    # 2. Fetch historical records across all sessions
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
        session_avg = 75

    # Calculate All-Time Global Average Wellness
    all_wellness_vals = [r["overall_wellness"] for r in all_time_rows if r.get("overall_wellness") is not None]
    all_time_avg = int(round(float(np.mean(all_wellness_vals)))) if all_wellness_vals else session_avg

    # Calculate Confidence based on exchanges and sessions
    n_exchanges = len(active_records)
    n_all_time = len(all_wellness_vals)
    confidence = round(min(1.0, max(0.35, (n_exchanges * 0.15) + (n_all_time * 0.04))), 2)

    # Compile Reasons & Quotes Across All Exchanges
    dim_map = {
        "stress_tension": {"label": "Stress & Pressure", "scores": [], "quotes": []},
        "worry_apprehension": {"label": "Worry & Apprehension", "scores": [], "quotes": []},
        "fatigue_exhaustion": {"label": "Fatigue & Low Energy", "scores": [], "quotes": []},
        "emotional_heaviness": {"label": "Emotional Heaviness", "scores": [], "quotes": []}
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
    if session_avg >= 70:
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

def get_session_report(session_id: str) -> Optional[Dict[str, Any]]:
    sess = get_session(session_id)
    if not sess:
        return None
    messages = get_session_messages(session_id)
    aggregated = get_aggregated_mental_health_insights(session_id)

    return {
        "session_id": session_id,
        "title": sess.get("title", "Check-in"),
        "created_at": sess.get("created_at"),
        "overall_wellness": aggregated.get("overall_wellness", sess.get("overall_wellness", 75)),
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
    and effective coping mechanisms across all sessions.
    """
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT user_id, user_name, key_context, recurring_stressors, effective_coping, baseline_wellness, last_updated
        FROM user_clinical_profile
        WHERE user_id = ?
    """, (user_id,))
    row = cursor.fetchone()
    conn.close()

    if not row:
        return {
            "user_id": user_id,
            "user_name": "Friend",
            "key_context": "Student navigating academic deadlines, career placements, and daily personal routines",
            "recurring_stressors": ["Academic deadlines and performance pressure", "Sleep and energy regulation", "Balancing technical projects"],
            "effective_coping": ["Guided box breathing (4-4-4-4)", "Taking short screen-free walks", "Reflective spoken dialogue"],
            "baseline_wellness": 75.0,
            "last_updated": datetime.now().isoformat()
        }

    d = dict(row)
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

    name = user_name.strip() if (user_name and isinstance(user_name, str) and len(user_name.strip()) > 1) else curr.get("user_name", "Logeshwaran")
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

def get_recent_session_memory_anchor() -> Dict[str, Any]:
    """
    Retrieves the most recent meaningful session topic, user quotes, and recurring stressors
    for memory-anchored greeting recall across days.
    """
    profile = get_user_clinical_profile("primary_user")
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT session_id, title, created_at, overall_wellness, dominant_emotion, summary
        FROM sessions
        WHERE summary IS NOT NULL AND summary != '' AND summary != 'Initial conversation started.'
        ORDER BY created_at DESC
        LIMIT 1
    """)
    row = cursor.fetchone()
    if not row:
        conn.close()
        return {"has_history": False, "profile": profile}

    sess = dict(row)
    cursor.execute("""
        SELECT role, text FROM messages
        WHERE session_id = ? AND role = 'user'
        ORDER BY id DESC LIMIT 2
    """, (sess["session_id"],))
    msgs = [r["text"] for r in cursor.fetchall()]
    conn.close()

    return {
        "has_history": True,
        "profile": profile,
        "title": sess.get("title"),
        "summary": sess.get("summary"),
        "dominant_emotion": sess.get("dominant_emotion"),
        "recent_remarks": msgs
    }

def get_historical_context(current_session_id: Optional[str] = None, limit: int = 4) -> str:
    """
    Retrieves cross-session memory and clinical trends across past and present conversations,
    incorporating the persistent clinical profile so Arogya naturally references long-term stressors.
    """
    profile = get_user_clinical_profile("primary_user")
    name = profile.get("user_name", "Logeshwaran")
    stressors_text = ", ".join(profile.get("recurring_stressors", [])) or "Semester exams, Project deadlines, Sleep fatigue"
    coping_text = ", ".join(profile.get("effective_coping", [])) or "Guided breathing, Short walks, Calming pauses"

    lines = [
        "--- LONG-TERM CLINICAL PROFILE & RECURRING STRESSOR MEMORY ---",
        f"• User's Name: {name} (Always address and know the user as {name})",
        f"• User Profile & Context: {profile.get('key_context', 'College student facing semester exams and placement preparation')}",
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
        WHERE session_id != ? OR ? IS NULL
        ORDER BY last_active DESC
        LIMIT ?
    """, (current_session_id or "", current_session_id or "", limit))
    past_sessions = cursor.fetchall()

    if not past_sessions:
        conn.close()
        lines.append("No previous sessions recorded. This is the first interaction with the user.")
        return "\n".join(lines)

    for s in past_sessions:
        s_id = s["session_id"]
        cursor.execute("""
            SELECT role, text FROM messages
            WHERE session_id = ? AND role = 'user'
            ORDER BY id DESC LIMIT 2
        """, (s_id,))
        recent_user_msgs = [r["text"] for r in cursor.fetchall()]
        recent_user_msgs.reverse()

        lines.append(
            f"• Session '{s['title']}' ({s['created_at'][:10]}): "
            f"Wellness Score: {s['overall_wellness']}/100, Tone: {s['dominant_emotion']}. "
            f"Summary: {s['summary']} "
            f"Key user remarks: {' | '.join(recent_user_msgs) if recent_user_msgs else 'None recorded'}"
        )

    conn.close()
    return "\n".join(lines)

def get_analytics_summary() -> Dict[str, Any]:
    """
    Computes comprehensive longitudinal clinical analytics across all sessions:
    - Multi-session time-series scores & trajectories
    - Symptom distributions with verbatim evidence quotes
    - Pitch stability and prosodic biomarker metrics
    - Long-term clinical profile & recurring stressor clusters
    """
    conn = get_connection()
    cursor = conn.cursor()

    # 1. Fetch all sessions in chronological order
    cursor.execute("""
        SELECT session_id, title, created_at, last_active, overall_wellness, dominant_emotion, summary
        FROM sessions
        ORDER BY created_at ASC
    """)
    session_rows = [dict(r) for r in cursor.fetchall()]

    # 2. Fetch all mental health records
    cursor.execute("""
        SELECT * FROM mental_health_records
        ORDER BY id ASC
    """)
    all_records = [dict(r) for r in cursor.fetchall()]
    conn.close()

    profile = get_user_clinical_profile("primary_user")

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
        "emotional_heaviness": {"label": "Emotional Heaviness", "scores": [], "quotes": []}
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

        session_wellness = int(round(float(np.mean(w_scores)))) if w_scores else s.get("overall_wellness", 75)
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

    # Overall KPIs
    total_sessions = len(session_rows)
    total_reflections = len(all_records)
    all_wellness = [p["wellness"] for p in timeline_points]
    lifetime_avg = int(round(float(np.mean(all_wellness)))) if all_wellness else 75

    recent_slice = all_wellness[-3:] if len(all_wellness) >= 3 else all_wellness
    recent_avg = int(round(float(np.mean(recent_slice)))) if recent_slice else lifetime_avg

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

    avg_semitone_lifetime = round(float(np.mean(semitones_all)), 2) if semitones_all else 1.85

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

