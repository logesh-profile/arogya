import os
import sys
import uuid
import shutil
import asyncio
import time
from typing import Optional

# Ensure UTF-8 on Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware

# Local imports
from database import (
    init_db,
    create_session,
    get_all_sessions,
    get_session,
    get_session_messages,
    save_message,
    save_mental_health_record,
    get_latest_mental_health_record,
    update_session_meta,
    get_historical_context,
    delete_session,
    rename_session,
    get_session_count,
    get_user_baseline_stats,
    get_session_report,
    get_aggregated_mental_health_insights,
    get_analytics_summary,
    get_user_clinical_profile,
    update_user_clinical_profile
)
from mental_health_engine import extract_acoustic_features, analyze_and_respond, generate_quick_session_title
from voice_engine import transcribe_audio, synthesize_speech

app = FastAPI(title="Arogya - Mental Health Voice Companion")

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")
CACHE_DIR = os.path.join(BASE_DIR, "audio_cache")
DATA_DIR = os.path.join(BASE_DIR, "data")
os.makedirs(STATIC_DIR, exist_ok=True)
os.makedirs(CACHE_DIR, exist_ok=True)

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
app.mount("/audio", StaticFiles(directory=CACHE_DIR), name="audio")

def prune_audio_cache(max_age_hours: int = 84):
    """Deletes temporary audio cache files older than max_age_hours (default 84 hours)."""
    now = time.time()
    cutoff = now - (max_age_hours * 3600)
    count = 0
    try:
        for fname in os.listdir(CACHE_DIR):
            if fname.startswith("temp_") or fname.startswith("clean_tr_") or fname.startswith("user_raw_"):
                fpath = os.path.join(CACHE_DIR, fname)
                if os.path.isfile(fpath) and os.path.getmtime(fpath) < cutoff:
                    try:
                        os.remove(fpath)
                        count += 1
                    except Exception:
                        pass
        if count > 0:
            print(f"[*] Pruned {count} expired temporary audio cache files (>84h).")
    except Exception as e:
        print(f"[!] Audio cache pruning notice: {e}")

@app.on_event("startup")
def on_startup():
    init_db()
    prune_audio_cache(max_age_hours=84)
    print("[*] Arogya Mental Health Server started at http://localhost:8000")


@app.get("/")
def index():
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))

@app.get("/analytics")
def analytics_page():
    return FileResponse(os.path.join(STATIC_DIR, "analytics.html"))

@app.get("/api/analytics/summary")
def get_analytics():
    return get_analytics_summary()

@app.get("/api/sessions")
def list_sessions():
    return get_all_sessions()

@app.post("/api/sessions")
def new_session():
    session_id = f"sess_{uuid.uuid4().hex[:10]}"
    title = "New Reflection"
    sess = create_session(session_id, title)
    return sess

@app.get("/api/sessions/{session_id}")
def load_session(session_id: str):
    sess = get_session(session_id)
    if not sess:
        raise HTTPException(status_code=404, detail="Session not found")
    messages = get_session_messages(session_id)
    aggregated = get_aggregated_mental_health_insights(session_id)
    return {
        "session": sess,
        "messages": messages,
        "latest_score": aggregated
    }

@app.patch("/api/sessions/{session_id}")
def update_session_title(session_id: str, title: str = Form(...)):
    if not rename_session(session_id, title):
        raise HTTPException(status_code=404, detail="Session not found")
    return {"status": "success", "session_id": session_id, "title": title}

@app.delete("/api/sessions/{session_id}")
def remove_session(session_id: str):
    delete_session(session_id)
    return {"status": "deleted", "session_id": session_id}


@app.get("/api/greeting")
async def get_initial_greeting(session_id: Optional[str] = None, voice_mode: str = "fast"):
    """
    Instant initial greeting: returns pre-cached studio audio for sub-millisecond page startup.
    """
    history_context = get_historical_context(session_id, limit=2)
    has_history = "--- PAST CONVERSATIONAL MEMORY" in history_context

    static_dir = os.path.join(BASE_DIR, "static", "audio")
    if has_history:
        greeting_text = "Hello again. It is wonderful to hear from you. Take a soft, gentle breath... how are you truly feeling right now?"
        cached_rel = "/static/audio/greeting_welcome_back.mp3"
        cached_path = os.path.join(static_dir, "greeting_welcome_back.mp3")
    else:
        greeting_text = "Hello there, and welcome. I am Arogya, your personal wellbeing companion. I am right here with you. Take a comfortable breath... how has your day been treating you?"
        cached_rel = "/static/audio/greeting_welcome.mp3"
        cached_path = os.path.join(static_dir, "greeting_welcome.mp3")

    if os.path.exists(cached_path):
        audio_url = cached_rel
    else:
        audio_url = await synthesize_speech(greeting_text, mode=voice_mode)

    # Save to session if session_id provided
    if session_id:
        save_message(session_id, "assistant", greeting_text, audio_path=audio_url)

    return {
        "greeting_text": greeting_text,
        "audio_url": audio_url
    }

@app.post("/api/transcribe")
async def transcribe_only(file: UploadFile = File(...)):
    """
    Fast audio transcription endpoint for instant client-side preview.
    """
    raw_filename = f"temp_tr_{uuid.uuid4().hex[:8]}.webm"
    raw_path = os.path.join(CACHE_DIR, raw_filename)
    with open(raw_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    clean_filename = f"clean_tr_{uuid.uuid4().hex[:8]}.wav"
    clean_path = os.path.join(CACHE_DIR, clean_filename)
    ffmpeg_exe = os.path.join(os.path.dirname(BASE_DIR), "ffmpeg.exe")

    active_audio_path = raw_path
    if os.path.exists(ffmpeg_exe):
        import subprocess
        try:
            cmd = [ffmpeg_exe, "-y", "-i", raw_path, "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le", clean_path]
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
            active_audio_path = clean_path
        except Exception:
            pass

    transcript = ""
    try:
        t = transcribe_audio(active_audio_path)
        if t and t.lower() not in ["you", "thank you", "[gentle sigh]"]:
            transcript = t.strip()
    except Exception as e:
        print(f"[!] Transcribe error: {e}")

    # Cleanup temporary transcribe audio
    for p in [raw_path, clean_path]:
        if os.path.exists(p):
            try: os.remove(p)
            except Exception: pass

    return {"transcript": transcript}

@app.post("/api/chat/voice")
async def process_voice_chat(
    file: UploadFile = File(...),
    session_id: str = Form(...),
    voice_mode: str = Form("cloned"),
    client_transcript: Optional[str] = Form(None)
):
    """
    Core speech-to-speech loop:
    1. Normalizes audio using FFmpeg to 16kHz Mono PCM WAV
    2. Transcribes voice (Dual: Browser Speech Recognition + Whisper GPU)
    3. Extracts acoustic biomarkers (prosody, tone, energy)
    4. Retrieves past session history for long-term clinical memory
    5. Evaluates mental health score & generates empathetic reply (Gemini 3.8 Flash)
    6. Synthesizes voice in Indian accent (F5-TTS cloned / fast Indian neural)
    """
    # 1. Save uploaded raw audio
    raw_filename = f"user_raw_{uuid.uuid4().hex[:8]}.webm"
    raw_path = os.path.join(CACHE_DIR, raw_filename)
    with open(raw_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    # 2. Normalize to 16kHz Mono PCM WAV via FFmpeg
    clean_filename = f"user_speech_{uuid.uuid4().hex[:8]}.wav"
    clean_path = os.path.join(CACHE_DIR, clean_filename)
    ffmpeg_exe = os.path.join(os.path.dirname(BASE_DIR), "ffmpeg.exe")
    
    if os.path.exists(ffmpeg_exe):
        import subprocess
        try:
            cmd = [ffmpeg_exe, "-y", "-i", raw_path, "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le", clean_path]
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
            active_audio_path = clean_path
        except Exception as e:
            print(f"[!] FFmpeg conversion failed: {e}, using raw path")
            active_audio_path = raw_path
    else:
        active_audio_path = raw_path

    # 3. Determine Transcript (Prioritize user's reviewed/client transcript, fallback to Whisper)
    transcript = ""
    if client_transcript and len(client_transcript.strip()) > 1:
        c_text = client_transcript.strip()
        words = c_text.lower().strip(" .,!?-").split()
        if not (all(w == "you" for w in words) or c_text.lower() in ["you", "thank you", "[gentle sigh]"]):
            transcript = c_text

    # If client transcript was empty, use Whisper on clean audio
    if not transcript:
        try:
            whisper_text = transcribe_audio(active_audio_path)
            if whisper_text:
                transcript = whisper_text
        except Exception as e:
            print(f"[!] Whisper error: {e}")

    if not transcript:
        transcript = "I wanted to take a moment to reflect on my feelings."


    # 4. Acoustic biomarker extraction (Code-only DSP via librosa.pyin)
    acoustic_features = extract_acoustic_features(active_audio_path)

    # 5. Session History & Baseline Statistical Context
    session_messages = get_session_messages(session_id)
    historical_context = get_historical_context(session_id)
    n_sessions = get_session_count()
    baseline = get_user_baseline_stats()

    semitone_std = acoustic_features.get("pitch_semitone_std")
    voice_z = None
    if semitone_std is not None and baseline.get("voice_mean") is not None and baseline.get("voice_std"):
        voice_z = (semitone_std - baseline["voice_mean"]) / baseline["voice_std"]

    latest_rec = get_latest_mental_health_record(session_id)
    trend_z = None
    if latest_rec and latest_rec.get("overall_wellness") is not None and baseline.get("wellness_std"):
        trend_z = (latest_rec["overall_wellness"] - baseline["wellness_mean"]) / baseline["wellness_std"]

    # 6. Save User Message
    save_message(
        session_id=session_id,
        role="user",
        text=transcript,
        audio_path=f"/audio/{clean_filename}",
        speech_metrics=acoustic_features
    )

    # 7. Evidence-Grounded Evaluation & Empathetic Response (temp=0.0)
    eval_result = analyze_and_respond(
        current_transcript=transcript,
        acoustic_features=acoustic_features,
        session_history=session_messages,
        historical_context=historical_context,
        voice_z=voice_z,
        trend_z=trend_z,
        n_sessions=n_sessions
    )

    reply_text = eval_result.get("reply_text", "I'm listening and I'm right here with you.")

    # 8. Synthesize Spoken Response
    ai_audio_url = await synthesize_speech(reply_text, mode=voice_mode)

    # 9. Save Assistant Message
    save_message(
        session_id=session_id,
        role="assistant",
        text=reply_text,
        audio_path=ai_audio_url
    )

    # 10. Update Database Record with Grounded Evidence
    eval_result["session_id"] = session_id
    eval_result["voice_semitone_std"] = semitone_std
    save_mental_health_record(eval_result)

    # 11. Compute Cumulative Session Average & Compiled Insights
    aggregated = get_aggregated_mental_health_insights(session_id)

    # 12. Instant Auto-titling based on First Message
    current_sess = get_session(session_id)
    new_title = None
    default_prefixes = ["Check-in", "New Reflection", "Emotional Wellness Reflection", "New Assessment", "Daily Reflection"]
    curr_t = current_sess.get("title", "") if current_sess else ""
    if current_sess and (any(curr_t.startswith(p) for p in default_prefixes)):
        new_title = eval_result.get("conversation_title") or generate_quick_session_title(transcript)

    update_session_meta(
        session_id=session_id,
        title=new_title,
        wellness=aggregated.get("overall_wellness", 75),
        emotion=aggregated.get("dominant_state", "Reflective"),
        summary=eval_result.get("summary_snippet", "")
    )

    return {
        "transcript": transcript,
        "reply_text": reply_text,
        "audio_url": ai_audio_url,
        "acoustic_features": acoustic_features,
        "evaluation": aggregated,
        "suggest_grounding": eval_result.get("suggest_grounding", False),
        "grounding_mode": eval_result.get("grounding_mode", "box"),
        "new_title": new_title
    }

@app.post("/api/chat/text")
async def process_text_chat(
    text: str = Form(...),
    session_id: str = Form(...),
    voice_mode: str = Form("fast")
):
    """
    Instant text chat with grounded evidence scoring and immediate titling.
    """
    dummy_acoustics = {
        "duration": 0.0,
        "pitch_semitone_std": None,
        "pause_ratio": 0.0,
        "is_valid_speech": False,
        "note": "Text-based input"
    }

    session_messages = get_session_messages(session_id)
    historical_context = get_historical_context(session_id)
    n_sessions = get_session_count()
    baseline = get_user_baseline_stats()

    latest_rec = get_latest_mental_health_record(session_id)
    trend_z = None
    if latest_rec and latest_rec.get("overall_wellness") is not None and baseline.get("wellness_std"):
        trend_z = (latest_rec["overall_wellness"] - baseline["wellness_mean"]) / baseline["wellness_std"]

    save_message(session_id=session_id, role="user", text=text, speech_metrics=dummy_acoustics)

    eval_result = analyze_and_respond(
        current_transcript=text,
        acoustic_features=dummy_acoustics,
        session_history=session_messages,
        historical_context=historical_context,
        voice_z=None,
        trend_z=trend_z,
        n_sessions=n_sessions
    )

    reply_text = eval_result.get("reply_text", "I hear you, and thank you for sharing that with me.")
    
    ai_audio_url = None
    if voice_mode and voice_mode != "none":
        try:
            ai_audio_url = await synthesize_speech(reply_text, mode=voice_mode)
        except Exception as e:
            print(f"[!] Speech synthesis notice: {e}")

    save_message(session_id=session_id, role="assistant", text=reply_text, audio_path=ai_audio_url)
    eval_result["session_id"] = session_id
    eval_result["voice_semitone_std"] = None
    save_mental_health_record(eval_result)

    # Compute Cumulative Session Average & Compiled Insights
    aggregated = get_aggregated_mental_health_insights(session_id)

    current_sess = get_session(session_id)
    new_title = None
    default_prefixes = ["Check-in", "New Reflection", "Emotional Wellness Reflection", "New Assessment", "Daily Reflection"]
    curr_t = current_sess.get("title", "") if current_sess else ""
    if current_sess and (any(curr_t.startswith(p) for p in default_prefixes)):
        new_title = eval_result.get("conversation_title") or generate_quick_session_title(text)

    update_session_meta(
        session_id=session_id,
        title=new_title,
        wellness=aggregated.get("overall_wellness", 75),
        emotion=aggregated.get("dominant_state", "Reflective"),
        summary=eval_result.get("summary_snippet", "")
    )

    return {
        "transcript": text,
        "reply_text": reply_text,
        "audio_url": ai_audio_url,
        "evaluation": aggregated,
        "suggest_grounding": eval_result.get("suggest_grounding", False),
        "grounding_mode": eval_result.get("grounding_mode", "box"),
        "new_title": new_title
    }

@app.get("/api/sessions/{session_id}/report")
def get_session_report_data(session_id: str):
    """
    Returns full structured report data for this conversation.
    """
    report = get_session_report(session_id)
    if not report:
        raise HTTPException(status_code=404, detail="Session report not found")
    return report

@app.get("/api/sessions/{session_id}/report/download")
def download_session_report(session_id: str):
    """
    Generates a clean, transparent Markdown clinical reflection report for download.
    """
    report = get_session_report(session_id)
    if not report:
        raise HTTPException(status_code=404, detail="Session not found")

    title = report.get("title", "Check-in")
    created = report.get("created_at", "N/A")[:10]
    wellness = report.get("overall_wellness")
    conf = int(report.get("confidence", 0.5) * 100)
    dom_state = report.get("dominant_state", "Reflective")
    semi_std = report.get("voice_semitone_std")

    lines = [
        f"# Arogya • Emotional Wellness Reflection Report",
        f"**Session:** {title} | **Date:** {created}",
        f"**Estimated Wellness Score:** {wellness if wellness is not None else 'N/A'}/100 (Confidence: {conf}%)",
        f"**Primary Emotional State:** {dom_state}",
        f"*(Note: These are estimated self-reported signals and not a clinical diagnosis.)*",
        "",
        "## 1. Grounded Symptom Evidence Breakdown",
    ]

    reasons = report.get("reasons", [])
    if reasons:
        for r in reasons:
            label = r.get("label", "Indicator")
            score = r.get("score", 0)
            quote = r.get("quote", "No explicit mention")
            lines.append(f"- **{label}:** Level {score}/3")
            lines.append(f"  *Verbatim Evidence:* \"{quote}\"")
    else:
        lines.append("- No explicit symptom indicators recorded.")

    lines.append("")
    lines.append("## 2. Voice Prosodic Biomarkers")
    if semi_std is not None:
        lines.append(f"- **Pitch Variation:** {semi_std} semitones (gender-neutral relative to speaker median)")
    else:
        lines.append("- Speech sample too brief or typed via text.")

    lines.append("")
    lines.append("## 3. Conversation Transcript")
    for msg in report.get("transcript", []):
        sender = "You" if msg["role"] == "user" else "Arogya"
        lines.append(f"**{sender}:** {msg['text']}")

    lines.append("")
    lines.append("## 4. Emergency Support Resources")
    lines.append("- **Tele-MANAS (Govt. of India 24/7 Toll-Free):** 14416")
    lines.append("- **KIRAN Mental Health Support:** 1800-599-0019")
    lines.append("- **Vandrevala Foundation:** +91 9999 666 555")

    content = "\n".join(lines)
    from fastapi.responses import Response
    return Response(
        content=content,
        media_type="text/markdown",
        headers={"Content-Disposition": f"attachment; filename=Arogya_Report_{session_id}.md"}
    )

@app.get("/api/analytics/export/download")
def download_analytics_report():
    """
    Generates a full multi-session longitudinal clinical report in Markdown format.
    """
    summary = get_analytics_summary()
    kpis = summary.get("kpis", {})
    profile = summary.get("profile", {})
    timeline = summary.get("timeline", [])
    symptoms = summary.get("symptoms", [])

    lines = [
        "# Arogya • Longitudinal Clinical Reflection & Wellness Analytics Report",
        f"**Generated:** {time.strftime('%Y-%m-%d %H:%M:%S')}",
        f"**Patient/User Profile:** {profile.get('user_name', 'Friend')}",
        f"**Context:** {profile.get('key_context', 'General wellbeing')}",
        "",
        "## 1. Executive Telemetry & Longitudinal KPIs",
        f"- **Lifetime Wellness Baseline:** {kpis.get('lifetime_wellness', 75)}/100",
        f"- **Recent Wellness Average:** {kpis.get('recent_wellness', 75)}/100",
        f"- **Trajectory Delta:** {kpis.get('trajectory_delta', 0.0):+} pts ({kpis.get('trajectory_status', 'Stable')})",
        f"- **Trajectory Assessment:** {kpis.get('trajectory_desc', '')}",
        f"- **Total Monitored Sessions:** {kpis.get('total_sessions', 0)}",
        f"- **Total Reflection Turns:** {kpis.get('total_reflections', 0)}",
        f"- **Average Pitch Variation:** {kpis.get('average_voice_semitones', 1.85)} semitones (pYIN normal)",
        "",
        "## 2. Long-Term Clinical Profile & Stressor Memory",
        f"**Recurring Stressor Themes:**",
    ]

    for s in profile.get("recurring_stressors", []):
        lines.append(f"  - {s}")

    lines.append("")
    lines.append("**Effective Coping Mechanisms:**")
    for c in profile.get("effective_coping", []):
        lines.append(f"  - {c}")

    lines.append("")
    lines.append("## 3. Symptom Distribution Breakdown (All Time)")
    for sym in symptoms:
        lines.append(f"- **{sym.get('label', 'Symptom')}:** Average Severity {sym.get('average_score', 0.0)}/3.0 (Occurred in {sym.get('quote_count', 0)} reflections)")
        for q in sym.get("quotes", [])[:2]:
            lines.append(f"  *Verbatim quote:* \"{q}\"")

    lines.append("")
    lines.append("## 4. Multi-Session Chronological Timeline")
    for item in timeline:
        lines.append(f"### Session: {item.get('title', 'Reflection')} ({item.get('date', '')})")
        lines.append(f"- **Wellness:** {item.get('wellness', 75)}/100 | **Dominant State:** {item.get('dominant_emotion', 'Reflective')}")
        lines.append(f"- **Stress:** {item.get('stress_avg', 0)}/3 | **Worry:** {item.get('worry_avg', 0)}/3 | **Fatigue:** {item.get('fatigue_avg', 0)}/3")
        if item.get("quotes"):
            quoted_strs = ['"' + str(q) + '"' for q in item.get('quotes', [])]
            lines.append(f"- **Recorded Quotes:** {', '.join(quoted_strs)}")
        lines.append("")

    lines.append("## 5. Emergency Support Resources")
    lines.append("- **Tele-MANAS (Govt. of India 24/7 Toll-Free):** 14416")
    lines.append("- **KIRAN Mental Health Support:** 1800-599-0019")
    lines.append("- **Vandrevala Foundation:** +91 9999 666 555")

    content = "\n".join(lines)
    from fastapi.responses import Response
    return Response(
        content=content,
        media_type="text/markdown",
        headers={"Content-Disposition": "attachment; filename=Arogya_Longitudinal_Report.md"}
    )


@app.post("/api/synthesize")
async def standalone_synthesize(
    text: str = Form(...),
    voice_mode: str = Form("cloned")
):
    """
    On-demand speech synthesis for any text message.
    """
    audio_url = await synthesize_speech(text, mode=voice_mode)
    return {"audio_url": audio_url}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)

