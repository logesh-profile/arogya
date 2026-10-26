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

from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Request, Response
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from google.oauth2 import id_token as google_id_token
from google.auth.transport import requests as google_requests
from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

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
    update_user_clinical_profile,
    upsert_google_user,
    update_user_preferred_name,
    create_auth_session,
    get_user_by_session_token,
    revoke_auth_session,
    get_user_by_id,
    switch_or_create_local_user,
    get_all_profiles
)
from mental_health_engine import (
    extract_acoustic_features,
    analyze_and_respond,
    generate_quick_session_title,
    generate_memory_greeting,
    classify_user_emotion_from_voice_tone
)
from voice_engine import transcribe_audio, synthesize_speech
from serial_bridge import get_esp32_bridge

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, ".env"))

GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "").strip()

app = FastAPI(title="Arogya - Mental Health Voice Companion")

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

STATIC_DIR = os.path.join(BASE_DIR, "static")
CACHE_DIR = os.path.join(BASE_DIR, "audio_cache")
DATA_DIR = os.path.join(BASE_DIR, "data")
os.makedirs(STATIC_DIR, exist_ok=True)
os.makedirs(CACHE_DIR, exist_ok=True)

def get_ffmpeg_executable() -> Optional[str]:
    """Cross-platform FFmpeg resolver: checks system PATH, imageio-ffmpeg package, or local Windows root."""
    # 1. System PATH (Render/Linux, Ubuntu, Mac, or Windows PATH)
    sys_ffmpeg = shutil.which("ffmpeg")
    if sys_ffmpeg:
        return sys_ffmpeg
    # 2. imageio-ffmpeg auto-downloaded wheel binary
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        pass
    # 3. Local bundled Windows executable
    local_ffmpeg = os.path.join(os.path.dirname(BASE_DIR), "ffmpeg.exe")
    if os.path.exists(local_ffmpeg):
        return local_ffmpeg
    return None

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
app.mount("/audio", StaticFiles(directory=CACHE_DIR), name="audio")

# ---------------------------------------------------------------------------
# AUTHENTICATION DEPENDENCIES & HELPERS
# ---------------------------------------------------------------------------
def get_current_user(request: Request) -> Optional[dict]:
    token = request.cookies.get("arogya_session")
    if not token:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header.split(" ", 1)[1].strip()
    if token:
        return get_user_by_session_token(token)
    return None

def get_effective_user(request: Request) -> dict:
    user = get_current_user(request)
    if user:
        return user
    primary = get_user_by_id("primary_user")
    if primary:
        return primary
    return {"id": "primary_user", "name": "User", "display_name": "Friend", "email": ""}

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
    print(f"[*] Arogya Mental Health Server started at http://localhost:8000 (Google OAuth configured: {bool(GOOGLE_CLIENT_ID and not GOOGLE_CLIENT_ID.startswith('your_'))})")


@app.get("/")
def index():
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))

@app.get("/login")
def login_page():
    return FileResponse(os.path.join(STATIC_DIR, "login.html"))

@app.get("/manifest.json")
def pwa_manifest():
    return FileResponse(os.path.join(STATIC_DIR, "manifest.json"), media_type="application/manifest+json")

@app.get("/sw.js")
def service_worker():
    return FileResponse(
        os.path.join(STATIC_DIR, "sw.js"),
        media_type="application/javascript",
        headers={"Service-Worker-Allowed": "/"}
    )

@app.get("/analytics")
def analytics_page():
    return FileResponse(os.path.join(STATIC_DIR, "analytics.html"))

@app.get("/api/analytics/summary")
def get_analytics(request: Request):
    user = get_effective_user(request)
    if not user:
        return {
            "total_sessions": 0,
            "overall_wellness": 75,
            "dominant_emotion": "Calm",
            "trend_points": [],
            "symptom_averages": {},
            "clinical_profile": {}
        }
    return get_analytics_summary(user_id=user["id"])

# ---------------------------------------------------------------------------
# AUTHENTICATION ROUTES (PRODUCTION GOOGLE OAUTH 2.0 & SESSION PERSISTENCE)
# ---------------------------------------------------------------------------
@app.get("/api/auth/config")
def get_auth_config():
    is_conf = bool(GOOGLE_CLIENT_ID and not GOOGLE_CLIENT_ID.startswith("your_"))
    return {
        "client_id": GOOGLE_CLIENT_ID if is_conf else "",
        "is_configured": is_conf
    }

@app.get("/api/auth/me")
def get_auth_me(request: Request):
    user = get_current_user(request)
    if not user:
        return {
            "authenticated": False,
            "user": None,
            "needs_onboarding": False
        }
    return {
        "authenticated": True,
        "user": user,
        "needs_onboarding": not bool(user.get("onboarding_completed"))
    }

@app.post("/api/auth/google")
async def auth_google(request: Request, response: Response):
    """
    Verifies Google Identity Services (GSI) credential token on backend,
    creates/updates user, and establishes an HTTP-only session cookie.
    """
    try:
        data = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid request payload")

    credential = data.get("credential")
    if not credential:
        raise HTTPException(status_code=400, detail="Missing Google credential token")

    try:
        aud = GOOGLE_CLIENT_ID if (GOOGLE_CLIENT_ID and not GOOGLE_CLIENT_ID.startswith("your_")) else None
        id_info = google_id_token.verify_oauth2_token(credential, google_requests.Request(), audience=aud)
        google_id = id_info.get("sub")
        email = id_info.get("email", "")
        name = id_info.get("name", "User")
        given_name = id_info.get("given_name", name.split()[0] if name else "User")
        picture = id_info.get("picture", "")

        user = upsert_google_user(google_id, email, name, given_name, picture)
        preferred_name = data.get("preferred_name", "").strip()
        if preferred_name:
            user = update_user_preferred_name(user["id"], preferred_name)

        session_token = create_auth_session(user["id"])
        response.set_cookie(
            key="arogya_session",
            value=session_token,
            max_age=30 * 86400,
            httponly=True,
            samesite="lax",
            secure=False
        )
        return {
            "status": "success",
            "user": user,
            "session_token": session_token,
            "needs_onboarding": not bool(user.get("onboarding_completed"))
        }
    except Exception as e:
        print(f"[!] Google token verification failed: {e}")
        raise HTTPException(status_code=401, detail=f"Authentication verification error: {str(e)}")

@app.post("/api/auth/update-name")
async def auth_update_name(request: Request):
    """One-time display name setup after initial Google login."""
    user = get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")
    try:
        data = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid request payload")
    
    preferred_name = data.get("preferred_name", "").strip()
    if not preferred_name:
        raise HTTPException(status_code=400, detail="Preferred name cannot be empty")
    
    updated_user = update_user_preferred_name(user["id"], preferred_name)
    return {"status": "success", "user": updated_user}

@app.post("/api/auth/logout")
def auth_logout(request: Request, response: Response):
    token = request.cookies.get("arogya_session")
    if token:
        revoke_auth_session(token)
    response.delete_cookie(key="arogya_session")
    return {"status": "logged_out"}

@app.post("/api/auth/switch-local")
async def auth_switch_local(request: Request, response: Response):
    """
    Switches to or creates a local user profile for multi-account testing and isolated memory.
    Establishes an HTTP-only session cookie so subsequent requests are strictly isolated to this user.
    """
    try:
        data = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid request payload")

    username = (data.get("username") or data.get("name") or "").strip()
    if not username:
        raise HTTPException(status_code=400, detail="Username cannot be empty")

    res = switch_or_create_local_user(username)
    response.set_cookie(
        key="arogya_session",
        value=res["session_token"],
        max_age=30 * 86400,
        httponly=True,
        samesite="lax",
        secure=False
    )
    return {
        "status": "success",
        "user": res["user"],
        "session_token": res["session_token"]
    }

@app.get("/api/auth/profiles")
def get_user_profiles():
    """Returns all available user profiles for quick account switching."""
    return {"profiles": get_all_profiles()}


# ---------------------------------------------------------------------------
# SESSIONS & CLINICAL CONVERSATIONS (USER ISOLATED)
# ---------------------------------------------------------------------------
@app.get("/api/sessions")
def list_sessions(request: Request):
    user = get_effective_user(request)
    if not user:
        return []
    return get_all_sessions(user_id=user["id"])

@app.post("/api/sessions")
def new_session(request: Request):
    user = get_effective_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Please sign in with Google to create a session")
    session_id = f"sess_{uuid.uuid4().hex[:10]}"
    title = "New Reflection"
    sess = create_session(session_id, title, user_id=user["id"])
    return sess

@app.get("/api/sessions/{session_id}")
def load_session(session_id: str, request: Request):
    user = get_effective_user(request)
    sess = get_session(session_id, user_id=user["id"])
    if not sess:
        sess = get_session(session_id)
        if not sess:
            raise HTTPException(status_code=404, detail="Session not found")
    messages = get_session_messages(session_id)
    aggregated = get_aggregated_mental_health_insights(session_id, user_id=user["id"])
    return {
        "session": sess,
        "messages": messages,
        "latest_score": aggregated
    }

@app.patch("/api/sessions/{session_id}")
def update_session_title(session_id: str, request: Request, title: str = Form(...)):
    user = get_effective_user(request)
    if not rename_session(session_id, title, user_id=user["id"]):
        raise HTTPException(status_code=404, detail="Session not found")
    return {"status": "success", "session_id": session_id, "title": title}

@app.delete("/api/sessions/{session_id}")
def remove_session(session_id: str, request: Request):
    user = get_effective_user(request)
    delete_session(session_id, user_id=user["id"])
    return {"status": "deleted", "session_id": session_id}

@app.get("/api/greeting")
async def get_initial_greeting(request: Request, session_id: Optional[str] = None, voice_mode: str = "fast"):
    """
    Dynamic memory-anchored greeting: Proactively connects with authenticated user's name and past clinical journey.
    """
    user = get_effective_user(request)
    greeting_info = generate_memory_greeting(session_id, user_id=user["id"])
    if isinstance(greeting_info, dict):
        greeting_text = greeting_info.get("reply_text", "")
        spoken_text = greeting_info.get("spoken_text", greeting_text)
        lang_mode = greeting_info.get("language_mode", "tanglish")
    else:
        greeting_text = str(greeting_info)
        spoken_text = greeting_text
        lang_mode = "tanglish"

    audio_url = await synthesize_speech(
        text=greeting_text,
        mode=voice_mode,
        language_mode=lang_mode,
        spoken_text=spoken_text
    )

    # Save to session if session_id provided
    if session_id:
        save_message(session_id, "assistant", greeting_text, audio_path=audio_url)

    return {
        "greeting_text": greeting_text,
        "audio_url": audio_url,
        "speaking_face": "happy"
    }

# ---------------------------------------------------------------------------
# ESP32 ROBOT DISPLAY & AFFECTIVE ATTUNEMENT SERIAL ENDPOINTS
# ---------------------------------------------------------------------------
@app.post("/api/esp32/speech_state")
async def esp32_speech_state(request: Request):
    """
    Called by client audio player when speech begins (state=1) or finishes (state=0).
    Synchronizes external ESP32 OLED face expressions and mouth movement opcodes.
    """
    try:
        data = await request.json()
    except Exception:
        data = {}
    state = int(data.get("state", 0))
    face = data.get("face")

    bridge = get_esp32_bridge()
    bridge.last_activity_time = time.time()
    if state == 1:
        if face:
            clean_face = str(face).strip().lower()
            bridge.current_emotion = clean_face
            bridge.send(f"EMO:{clean_face}")
        bridge.current_activity = "speaking"
        bridge.send("SPK:1")
    else:
        bridge.current_activity = "idle"
        bridge.send("SPK:0")

    return {
        "status": "ok",
        "state": state,
        "face": bridge.current_emotion,
        "activity": bridge.current_activity,
        "esp32_connected": bridge.is_connected()
    }

@app.post("/api/esp32/emotion")
async def esp32_emotion(request: Request):
    """
    Direct emotion opcode dispatch to ESP32 display (e.g. EMO:caring, EMO:thinking).
    """
    try:
        data = await request.json()
    except Exception:
        data = {}
    face = str(data.get("face", "calm")).strip().lower()
    bridge = get_esp32_bridge()
    bridge.current_emotion = face
    bridge.last_activity_time = time.time()
    bridge.send(f"EMO:{face}")
    return {
        "status": "ok",
        "face": face,
        "esp32_connected": bridge.is_connected()
    }

@app.get("/api/esp32/status")
def esp32_status():
    """
    Diagnostic status endpoint for physical ESP32 connection (graceful fallback on cloud/Render).
    """
    bridge = get_esp32_bridge()
    return bridge.get_status()

@app.get("/api/debug_gemini")
def debug_gemini():
    from mental_health_voice_ai.mental_health_engine import client, API_KEY
    if not API_KEY:
        return {"status": "error", "error": "API_KEY is empty"}
    try:
        models = [m.name for m in client.models.list()]
        return {"status": "ok", "models": models}
    except Exception as e:
        return {"status": "error", "error": str(e)}
def debug_gemini(model: str = "gemini-2.0-flash"):
    from mental_health_voice_ai.mental_health_engine import client, API_KEY
    from google.genai import types
    if not API_KEY:
        return {"status": "error", "error": "API_KEY is empty or missing in environment"}
    try:
        cfg = types.GenerateContentConfig(response_mime_type="application/json")
        resp = client.models.generate_content(model=model, contents='output JSON: {"greeting": "hi"}', config=cfg)
        return {"model": model, "status": "ok", "reply": resp.text.strip()}
    except Exception as e:
        return {"model": model, "status": "error", "msg": str(e)}

@app.get("/api/expression")
@app.get("/expression")
def get_esp32_expression():
    """
    ESP32 Wi-Fi Polling Endpoint: Returns the active FACS emotion and activity state.
    """
    bridge = get_esp32_bridge()
    now = time.time()
    emo = getattr(bridge, "current_emotion", "calm")
    act = getattr(bridge, "current_activity", "idle")
    last_act = getattr(bridge, "last_activity_time", 0.0)

    # Safe auto-timeout: if speaking for more than 4.5 seconds without refresh, return to idle
    if act == "speaking" and (now - last_act > 4.5):
        act = "idle"
        bridge.current_activity = "idle"

    return {
        "emotion": emo,
        "activity": act,
        "keyword": emo.upper(),
        "last_update": now
    }

@app.post("/api/expression")
@app.post("/expression")
async def set_esp32_expression(request: Request):
    """
    Sets the active FACS emotion and activity state for ESP32.
    """
    try:
        data = await request.json()
    except Exception:
        data = {}
    emo = data.get("emotion") or data.get("face") or "calm"
    act = data.get("activity") or "idle"
    bridge = get_esp32_bridge()
    bridge.current_emotion = str(emo).strip().lower()
    bridge.current_activity = str(act).strip().lower()
    bridge.last_activity_time = time.time()
    bridge.send(f"EMO:{bridge.current_emotion}")
    if bridge.current_activity == "speaking":
        bridge.send("SPK:1")
    elif bridge.current_activity == "idle":
        bridge.send("SPK:0")
    return {
        "status": "ok",
        "emotion": bridge.current_emotion,
        "activity": bridge.current_activity
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
    ffmpeg_exe = get_ffmpeg_executable()

    active_audio_path = raw_path
    if ffmpeg_exe and os.path.exists(ffmpeg_exe):
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
    request: Request,
    file: UploadFile = File(...),
    session_id: str = Form(...),
    voice_mode: str = Form("fast"),
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
    user = get_effective_user(request)
    if not session_id or session_id in ["null", "undefined", "None"]:
        all_sess = get_all_sessions(user_id=user["id"])
        if all_sess and len(all_sess) > 0:
            session_id = all_sess[0]["session_id"]
        else:
            session_id = f"sess_{uuid.uuid4().hex[:10]}"
            create_session(session_id, "Check-in", user_id=user["id"])
    bridge = get_esp32_bridge()
    bridge.send("EMO:thinking")

    # 1. Save uploaded raw audio
    raw_filename = f"user_raw_{uuid.uuid4().hex[:8]}.webm"
    raw_path = os.path.join(CACHE_DIR, raw_filename)
    with open(raw_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    # 2. Normalize to 16kHz Mono PCM WAV via FFmpeg
    clean_filename = f"user_speech_{uuid.uuid4().hex[:8]}.wav"
    clean_path = os.path.join(CACHE_DIR, clean_filename)
    ffmpeg_exe = get_ffmpeg_executable()
    
    if ffmpeg_exe and os.path.exists(ffmpeg_exe):
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

    # 3. Determine Transcript & Acoustic Features Concurrently
    # STT runs on RTX 3050 GPU (CUDA FP16), DSP runs on CPU in thread pool
    transcript = ""
    if client_transcript and len(client_transcript.strip()) > 1:
        c_text = client_transcript.strip()
        words = c_text.lower().strip(" .,!?-").split()
        if not (all(w == "you" for w in words) or c_text.lower() in ["you", "thank you", "[gentle sigh]"]):
            transcript = c_text

    loop = asyncio.get_event_loop()
    if transcript:
        # Client transcript provided; extract acoustics in background thread
        acoustic_features = await loop.run_in_executor(None, extract_acoustic_features, active_audio_path)
    else:
        # Run Whisper GPU STT and Librosa CPU DSP concurrently
        whisper_task = loop.run_in_executor(None, transcribe_audio, active_audio_path)
        dsp_task = loop.run_in_executor(None, extract_acoustic_features, active_audio_path)
        whisper_text, acoustic_features = await asyncio.gather(whisper_task, dsp_task)
        if whisper_text:
            transcript = whisper_text

    if not transcript:
        transcript = "I wanted to take a moment to reflect on my feelings."

    # Immediate Affective Attunement: mirror user's vocal tone on ESP32 display
    tone_emotion = classify_user_emotion_from_voice_tone(acoustic_features, transcript)
    bridge.send(f"EMO:{tone_emotion['listening_face']}")

    # 4. Session History & Baseline Statistical Context
    session_messages = get_session_messages(session_id)
    historical_context = get_historical_context(session_id, user_id=user["id"])
    n_sessions = get_session_count(user_id=user["id"])
    baseline = get_user_baseline_stats(user_id=user["id"])

    semitone_std = acoustic_features.get("pitch_semitone_std")
    voice_z = None
    if semitone_std is not None and baseline.get("voice_mean") is not None and baseline.get("voice_std"):
        voice_z = (semitone_std - baseline["voice_mean"]) / baseline["voice_std"]

    latest_rec = get_latest_mental_health_record(session_id)
    trend_z = None
    if latest_rec and latest_rec.get("overall_wellness") is not None and baseline.get("wellness_std"):
        trend_z = (latest_rec["overall_wellness"] - baseline["wellness_mean"]) / baseline["wellness_std"]

    # 5. Save User Message
    save_message(
        session_id=session_id,
        role="user",
        text=transcript,
        audio_path=f"/audio/{clean_filename}",
        speech_metrics=acoustic_features
    )

    # 6. Evidence-Grounded Evaluation & Empathetic Response (temp=0.0)
    eval_result = analyze_and_respond(
        current_transcript=transcript,
        acoustic_features=acoustic_features,
        session_history=session_messages,
        historical_context=historical_context,
        voice_z=voice_z,
        trend_z=trend_z,
        n_sessions=n_sessions,
        user_id=user["id"]
    )

    reply_text = eval_result.get("reply_text", "I'm listening and I'm right here with you.")
    spoken_text = eval_result.get("spoken_text")
    language_mode = eval_result.get("language_mode", "tanglish")

    speaking_face = eval_result.get("speaking_face", tone_emotion["speaking_face"])
    bridge.current_emotion = speaking_face
    bridge.last_activity_time = time.time()
    bridge.send(f"EMO:{speaking_face}")

    # 7. Synthesize Spoken Response (Emotion-Adaptive Cadence & Native Voice Routing)
    user_wellness = eval_result.get("overall_wellness", 75)
    user_state = eval_result.get("dominant_state", "Calm")
    ai_audio_url = await synthesize_speech(
        text=reply_text, 
        mode=voice_mode, 
        wellness_score=user_wellness if user_wellness is not None else 75, 
        dominant_state=user_state,
        language_mode=language_mode,
        spoken_text=spoken_text
    )

    # 8. Save Assistant Message (Stores canonical colloquial text for chat history)
    save_message(
        session_id=session_id,
        role="assistant",
        text=reply_text,
        audio_path=ai_audio_url
    )

    # 9. Update Database Record with Grounded Evidence
    eval_result["session_id"] = session_id
    eval_result["voice_semitone_std"] = semitone_std
    save_mental_health_record(eval_result)

    # 10. Compute Cumulative Session Average & Compiled Insights
    aggregated = get_aggregated_mental_health_insights(session_id, user_id=user["id"])

    # 11. Instant Auto-titling based on First Message
    current_sess = get_session(session_id, user_id=user["id"]) or get_session(session_id)
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
        "user_emotion": eval_result.get("user_emotion", tone_emotion["user_emotion"]),
        "listening_face": eval_result.get("listening_face", tone_emotion["listening_face"]),
        "speaking_face": eval_result.get("speaking_face", tone_emotion["speaking_face"]),
        "overall_wellness": aggregated.get("overall_wellness", 75),
        "evaluation": aggregated,
        "suggest_grounding": eval_result.get("suggest_grounding", False),
        "grounding_mode": eval_result.get("grounding_mode", "box"),
        "language_mode": language_mode,
        "speech_register": eval_result.get("speech_register", "warm_tanglish"),
        "new_title": new_title
    }

@app.post("/api/chat/text")
async def process_text_chat(
    request: Request,
    text: str = Form(...),
    session_id: str = Form(...),
    voice_mode: str = Form("fast")
):
    """
    Instant text chat with grounded evidence scoring and immediate titling.
    """
    user = get_effective_user(request)
    if not session_id or session_id in ["null", "undefined", "None"]:
        all_sess = get_all_sessions(user_id=user["id"])
        if all_sess and len(all_sess) > 0:
            session_id = all_sess[0]["session_id"]
        else:
            session_id = f"sess_{uuid.uuid4().hex[:10]}"
            create_session(session_id, "Check-in", user_id=user["id"])
    bridge = get_esp32_bridge()
    bridge.send("EMO:thinking")

    dummy_acoustics = {
        "duration": 0.0,
        "pitch_semitone_std": None,
        "pause_ratio": 0.0,
        "is_valid_speech": False,
        "note": "Text-based input"
    }

    session_messages = get_session_messages(session_id)
    historical_context = get_historical_context(session_id, user_id=user["id"])
    n_sessions = get_session_count(user_id=user["id"])
    baseline = get_user_baseline_stats(user_id=user["id"])

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
        n_sessions=n_sessions,
        user_id=user["id"]
    )

    speaking_face = eval_result.get("speaking_face", "caring")
    bridge.current_emotion = speaking_face
    bridge.last_activity_time = time.time()
    bridge.send(f"EMO:{speaking_face}")

    reply_text = eval_result.get("reply_text", "I hear you, and thank you for sharing that with me.")
    spoken_text = eval_result.get("spoken_text")
    language_mode = eval_result.get("language_mode", "tanglish")
    speech_register = eval_result.get("speech_register", "warm_tanglish")
    
    ai_audio_url = None
    if voice_mode and voice_mode != "none":
        try:
            user_wellness = eval_result.get("overall_wellness", 75)
            user_state = eval_result.get("dominant_state", "Calm")
            ai_audio_url = await synthesize_speech(
                text=reply_text, 
                mode=voice_mode, 
                wellness_score=user_wellness if user_wellness is not None else 75, 
                dominant_state=user_state,
                language_mode=language_mode,
                spoken_text=spoken_text
            )
        except Exception as e:
            print(f"[!] Speech synthesis notice: {e}")

    save_message(session_id=session_id, role="assistant", text=reply_text, audio_path=ai_audio_url)
    eval_result["session_id"] = session_id
    eval_result["voice_semitone_std"] = None
    save_mental_health_record(eval_result)

    # Compute Cumulative Session Average & Compiled Insights
    aggregated = get_aggregated_mental_health_insights(session_id, user_id=user["id"])

    current_sess = get_session(session_id, user_id=user["id"]) or get_session(session_id)
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
        "user_emotion": eval_result.get("user_emotion", "calm"),
        "listening_face": eval_result.get("listening_face", "calm"),
        "speaking_face": eval_result.get("speaking_face", "caring"),
        "overall_wellness": aggregated.get("overall_wellness", 75),
        "evaluation": aggregated,
        "suggest_grounding": eval_result.get("suggest_grounding", False),
        "grounding_mode": eval_result.get("grounding_mode", "box"),
        "language_mode": language_mode,
        "speech_register": speech_register,
        "new_title": new_title
    }

@app.get("/api/sessions/{session_id}/report")
def get_session_report_data(session_id: str, request: Request):
    """
    Returns full structured report data for this conversation.
    """
    user = get_effective_user(request)
    report = get_session_report(session_id, user_id=user["id"])
    if not report:
        raise HTTPException(status_code=404, detail="Session report not found")
    return report

@app.get("/api/sessions/{session_id}/report/download")
def download_session_report(session_id: str, request: Request):
    """
    Generates a clean, transparent Markdown clinical reflection report for download.
    """
    user = get_effective_user(request)
    report = get_session_report(session_id, user_id=user["id"])
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
def download_analytics_report(request: Request):
    """
    Generates a full multi-session longitudinal clinical report in Markdown format.
    """
    user = get_effective_user(request)
    summary = get_analytics_summary(user_id=user["id"])
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
    port = int(os.environ.get("PORT", 8000))
    host = os.environ.get("HOST", "0.0.0.0")
    uvicorn.run("app:app", host=host, port=port, reload=False)

