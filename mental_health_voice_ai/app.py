import os
import sys
import uuid
import shutil
import asyncio
import time
import io
from typing import Optional

# Ensure UTF-8 on Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Request, Response, Query, BackgroundTasks
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
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
    get_all_profiles,
    save_clinical_assessment,
    get_user_clinical_assessments,
    get_doctor_clinical_summary
)
from mental_health_engine import (
    extract_acoustic_features,
    analyze_and_respond,
    generate_quick_session_title,
    generate_memory_greeting,
    classify_user_emotion_from_voice_tone,
    PHQ9_QUESTIONS,
    GAD7_QUESTIONS,
    RESPONSE_SCALE,
    score_phq9,
    score_gad7
)
from voice_engine import (
    transcribe_audio,
    synthesize_speech,
    stream_edge_tts_chunks,
    AVAILABLE_VOICES,
    DEFAULT_VOICE,
    generate_voice_preview
)

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

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
app.mount("/audio", StaticFiles(directory=CACHE_DIR), name="audio")

# ---------------------------------------------------------------------------
# AUTHENTICATION DEPENDENCIES & HELPERS
# ---------------------------------------------------------------------------
def get_current_user(request: Request) -> Optional[dict]:
    # 1. Bearer Header (highest priority from localStorage in client requests)
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        bearer_token = auth_header.split(" ", 1)[1].strip()
        user = get_user_by_session_token(bearer_token)
        if user:
            return user

    # 2. HTTP-only Session Cookie
    cookie_token = request.cookies.get("arogya_session")
    if cookie_token:
        user = get_user_by_session_token(cookie_token)
        if user:
            return user

    # 3. Query Param Token (for report downloads / media links)
    query_token = request.query_params.get("token")
    if query_token:
        user = get_user_by_session_token(query_token)
        if user:
            return user

    return None

def get_effective_user(request: Request) -> dict:
    user = get_current_user(request)
    if user:
        return user
    return {"id": "guest_user", "name": "", "display_name": "Friend", "email": ""}

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


@app.get("/health")
@app.get("/api/health")
def health_check():
    return {
        "status": "healthy",
        "service": "Arogya Mental Health Voice AI",
        "timestamp": time.time(),
        "groq_active": bool(os.getenv("GROQ_API_KEY")),
        "database": "active"
    }

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
            "overall_wellness": None,
            "dominant_emotion": "Awaiting Reflection",
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
@app.get("/api/voices")
def get_available_voices():
    """Returns curated natural ChatGPT-style voice models for user selection."""
    return {
        "voices": AVAILABLE_VOICES,
        "default_voice": DEFAULT_VOICE
    }

@app.get("/api/voice/preview")
async def get_voice_preview_endpoint(voice: Optional[str] = None):
    """Returns or generates a cached preview audio clip for a given voice persona."""
    target_voice = voice or DEFAULT_VOICE
    audio_url = await generate_voice_preview(target_voice)
    if not audio_url:
        raise HTTPException(status_code=500, detail="Voice preview generation failed")
    return {"voice": target_voice, "audio_url": audio_url}

@app.get("/api/tts/stream")
async def stream_tts_endpoint(text: str = Query(...), voice: Optional[str] = Query(None)):
    """
    In-memory Edge-TTS audio streaming endpoint.
    Yields raw MP3 chunks directly with media_type='audio/mpeg' and zero disk I/O.
    """
    return StreamingResponse(
        stream_edge_tts_chunks(text=text, voice=voice),
        media_type="audio/mpeg"
    )

@app.post("/api/synthesize")
async def standalone_synthesize(
    request: Request,
    text: str = Form(...),
    voice_mode: str = Form("fast"),
    voice: Optional[str] = Form(None)
):
    """
    Synthesizes speech in-memory without creating physical disk files.
    Returns StreamingResponse if requested by client, or instant Data URI.
    """
    if "audio/mpeg" in request.headers.get("accept", ""):
        return StreamingResponse(
            stream_edge_tts_chunks(text=text, voice=voice),
            media_type="audio/mpeg"
        )

    audio_url = await synthesize_speech(
        text=text,
        mode=voice_mode,
        language_mode="indian_english",
        voice=voice
    )
    if not audio_url:
        raise HTTPException(status_code=500, detail="Speech synthesis failed")
    return {"audio_url": audio_url}

@app.get("/api/sessions")
def list_sessions(request: Request):
    user = get_effective_user(request)
    if not user or user["id"] in ["guest_user", "usr_guest"]:
        return []
    return get_all_sessions(user_id=user["id"])

@app.post("/api/sessions")
def new_session(request: Request):
    user = get_effective_user(request)
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
        # Restrict cross-user access if session belongs to a different registered user
        if sess.get("user_id") and sess.get("user_id") not in ["guest_user", "usr_guest", user["id"]]:
            raise HTTPException(status_code=403, detail="Access denied")
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
async def get_initial_greeting(
    request: Request,
    session_id: Optional[str] = None,
    voice_mode: str = "fast",
    voice: Optional[str] = Query(None)
):
    """
    Dynamic memory-anchored greeting: Proactively connects with authenticated user's name and past clinical journey.
    """
    user = get_effective_user(request)
    greeting_info = generate_memory_greeting(session_id, user_id=user["id"])
    if isinstance(greeting_info, dict):
        greeting_text = greeting_info.get("reply_text", "")
        spoken_text = greeting_info.get("spoken_text", greeting_text)
        lang_mode = greeting_info.get("language_mode", "indian_english")
    else:
        greeting_text = str(greeting_info)
        spoken_text = greeting_text
        lang_mode = "indian_english"

    audio_url = await synthesize_speech(
        text=greeting_text,
        mode=voice_mode,
        language_mode=lang_mode,
        spoken_text=spoken_text,
        voice=voice
    )

    # Save to session if session_id provided with actual user_id
    if session_id:
        save_message(session_id, "assistant", greeting_text, audio_path=audio_url, user_id=user["id"])

    return {
        "greeting_text": greeting_text,
        "audio_url": audio_url,
        "speaking_face": "happy"
    }

# ---------------------------------------------------------------------------
# ESP32 ROBOT DISPLAY & AFFECTIVE ATTUNEMENT SERIAL ENDPOINTS
# ---------------------------------------------------------------------------
class DummyBridge:
    current_emotion = "neutral"
    last_activity_time = 0.0
    def send(self, *args, **kwargs):
        pass

_dummy_bridge = DummyBridge()
def get_esp32_bridge():
    return _dummy_bridge

# Lightweight Web Companion State Endpoints (Hardware independent)
@app.post("/api/esp32/speech_state")
async def esp32_speech_state(request: Request):
    return {"status": "ok", "state": 0}

@app.post("/api/esp32/emotion")
async def esp32_emotion(request: Request):
    return {"status": "ok", "face": "calm"}

@app.get("/api/esp32/status")
def esp32_status():
    return {"connected": False, "port": None, "mode": "web_standalone"}

@app.get("/api/expression")
@app.get("/expression")
def get_esp32_expression():
    return {"emotion": "calm", "activity": "idle", "keyword": "CALM", "last_update": time.time()}

@app.post("/api/expression")
@app.post("/expression")
async def set_esp32_expression(request: Request):
    return {"status": "ok", "emotion": "calm", "activity": "idle"}


@app.post("/api/transcribe")
async def transcribe_only(file: UploadFile = File(...)):
    """
    Fast audio transcription endpoint directly in memory.
    Completely eliminates local file saving and FFmpeg OS subprocess spikes.
    """
    audio_bytes = await file.read()
    bio = io.BytesIO(audio_bytes)
    bio.name = file.filename or "audio.webm"

    transcript = ""
    try:
        t = transcribe_audio(bio)
        if t and t.lower() not in ["you", "thank you", "[gentle sigh]"]:
            transcript = t.strip()
    except Exception as e:
        print(f"[!] Transcribe error: {e}")

    return {"transcript": transcript}

def _persist_turn(
    session_id: str,
    user_id: str,
    transcript: str,
    user_audio_url: Optional[str],
    speech_metrics: dict,
    reply_text: str,
    ai_audio_url: Optional[str],
    user_wellness: int,
    user_state: str,
    eval_result: dict,
    semitone_std: Optional[float] = None,
    new_title: Optional[str] = None
):
    try:
        save_message(
            session_id=session_id,
            role="user",
            text=transcript,
            audio_path=user_audio_url,
            speech_metrics=speech_metrics,
            user_id=user_id
        )
        save_message(
            session_id=session_id,
            role="assistant",
            text=reply_text,
            audio_path=ai_audio_url,
            speech_metrics={"overall_wellness": user_wellness, "dominant_state": user_state},
            user_id=user_id
        )
        eval_result["session_id"] = session_id
        eval_result["voice_semitone_std"] = semitone_std
        save_mental_health_record(eval_result)
        aggregated = get_aggregated_mental_health_insights(session_id, user_id=user_id)
        update_session_meta(
            session_id=session_id,
            title=new_title,
            wellness=aggregated.get("overall_wellness") or user_wellness,
            emotion=aggregated.get("dominant_state", user_state),
            summary=eval_result.get("summary_snippet", "")
        )
        stressor_candidate = eval_result.get("core_topic") or eval_result.get("conversation_title")
        coping_candidate = eval_result.get("observed_resilience")
        update_user_clinical_profile(
            user_id=user_id,
            new_stressor=stressor_candidate if (stressor_candidate and stressor_candidate not in ["Daily Reflection", "Check-in", "Personal Check-in"]) else None,
            new_coping=coping_candidate,
            baseline_wellness=float(user_wellness) if user_wellness else None
        )
    except Exception as e:
        print(f"[!] Background turn save notice: {e}")

@app.post("/api/chat/voice")
async def process_voice_chat(
    request: Request,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    session_id: str = Form(...),
    voice_mode: str = Form("fast"),
    client_transcript: Optional[str] = Form(None),
    voice: Optional[str] = Form(None)
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

    # 1. Read uploaded raw audio directly into memory (zero disk I/O, zero FFmpeg subprocess)
    audio_bytes = await file.read()
    bio = io.BytesIO(audio_bytes)
    bio.name = file.filename or "audio.webm"

    # 2. Determine Transcript & Acoustic Features Concurrently in Memory
    transcript = ""
    if client_transcript and len(client_transcript.strip()) > 1:
        c_text = client_transcript.strip()
        words = c_text.lower().strip(" .,!?-").split()
        if not (all(w == "you" for w in words) or c_text.lower() in ["you", "thank you", "[gentle sigh]"]):
            transcript = c_text

    # 3. Session History & Baseline Statistical Context
    session_messages = get_session_messages(session_id)
    historical_context = get_historical_context(session_id, user_id=user["id"])
    n_sessions = get_session_count(user_id=user["id"])
    baseline = get_user_baseline_stats(user_id=user["id"])

    latest_rec = get_latest_mental_health_record(session_id)
    trend_z = None
    if latest_rec and latest_rec.get("overall_wellness") is not None and baseline.get("wellness_std"):
        trend_z = (latest_rec["overall_wellness"] - baseline["wellness_mean"]) / baseline["wellness_std"]

    loop = asyncio.get_event_loop()
    if transcript:
        # High-Speed Parallel Pipeline: Run in-memory DSP and LLM concurrently
        dsp_task = loop.run_in_executor(None, extract_acoustic_features, audio_bytes)
        llm_task = loop.run_in_executor(
            None,
            analyze_and_respond,
            transcript,
            {},
            session_messages,
            historical_context,
            None,
            trend_z,
            n_sessions,
            user["id"]
        )
        acoustic_features, eval_result = await asyncio.gather(dsp_task, llm_task)
    else:
        # Run in-memory Groq Whisper STT and DSP concurrently
        whisper_task = loop.run_in_executor(None, transcribe_audio, bio)
        dsp_task = loop.run_in_executor(None, extract_acoustic_features, audio_bytes)
        whisper_text, acoustic_features = await asyncio.gather(whisper_task, dsp_task)
        transcript = whisper_text or "I wanted to take a moment to reflect on my feelings."
        eval_result = analyze_and_respond(
            current_transcript=transcript,
            acoustic_features=acoustic_features,
            session_history=session_messages,
            historical_context=historical_context,
            voice_z=None,
            trend_z=trend_z,
            n_sessions=n_sessions,
            user_id=user["id"]
        )

    # Attach acoustic telemetry
    eval_result["acoustic_features"] = acoustic_features
    raw_semitone = acoustic_features.get("pitch_semitone_std")
    semitone_std = float(raw_semitone) if isinstance(raw_semitone, (int, float)) else None
    voice_z = None
    if semitone_std is not None and baseline.get("voice_mean") is not None and baseline.get("voice_std"):
        voice_z = (semitone_std - baseline["voice_mean"]) / baseline["voice_std"]
    eval_result["voice_z"] = voice_z

    # Immediate Affective Attunement: mirror user's vocal tone on ESP32 display
    tone_emotion = classify_user_emotion_from_voice_tone(acoustic_features, transcript)
    bridge.send(f"EMO:{tone_emotion['listening_face']}")

    reply_text = eval_result.get("reply_text", "I'm listening and I'm right here with you.")
    spoken_text = eval_result.get("spoken_text")
    language_mode = eval_result.get("language_mode", "indian_english")

    speaking_face = eval_result.get("speaking_face", tone_emotion["speaking_face"])
    bridge.current_emotion = speaking_face
    bridge.last_activity_time = time.time()
    bridge.send(f"EMO:{speaking_face}")

    # 5. Synthesize Spoken Response (Emotion-Adaptive Cadence & Native Voice Routing)
    user_wellness = eval_result.get("overall_wellness", 75)
    user_state = eval_result.get("dominant_state", "Calm")
    ai_audio_url = await synthesize_speech(
        text=reply_text, 
        mode=voice_mode, 
        wellness_score=user_wellness if user_wellness is not None else 75, 
        dominant_state=user_state,
        language_mode=language_mode,
        spoken_text=spoken_text,
        voice=voice
    )

    # 6. Instant Auto-titling calculation
    current_sess = get_session(session_id, user_id=user["id"]) or get_session(session_id)
    new_title = None
    default_prefixes = ["Check-in", "New Reflection", "Emotional Wellness Reflection", "New Assessment", "Daily Reflection"]
    curr_t = current_sess.get("title", "") if current_sess else ""
    if current_sess and (any(curr_t.startswith(p) for p in default_prefixes)):
        new_title = eval_result.get("conversation_title") or generate_quick_session_title(transcript)

    # 7. Asynchronous Database Persistence via FastAPI BackgroundTasks (0ms delay to client)
    background_tasks.add_task(
        _persist_turn,
        session_id=session_id,
        user_id=user["id"],
        transcript=transcript,
        user_audio_url=None, # In-memory processing (zero disk files)
        speech_metrics=acoustic_features,
        reply_text=reply_text,
        ai_audio_url=ai_audio_url,
        user_wellness=user_wellness,
        user_state=user_state,
        eval_result=eval_result,
        semitone_std=semitone_std,
        new_title=new_title
    )

    return {
        "transcript": transcript,
        "reply_text": reply_text,
        "audio_url": ai_audio_url,
        "acoustic_features": acoustic_features,
        "user_emotion": eval_result.get("user_emotion", tone_emotion["user_emotion"]),
        "listening_face": eval_result.get("listening_face", tone_emotion["listening_face"]),
        "speaking_face": eval_result.get("speaking_face", tone_emotion["speaking_face"]),
        "overall_wellness": user_wellness,
        "evaluation": eval_result,
        "suggest_grounding": eval_result.get("suggest_grounding", False),
        "grounding_mode": eval_result.get("grounding_mode", "box"),
        "language_mode": language_mode,
        "speech_register": eval_result.get("speech_register", "warm_conversational"),
        "new_title": new_title
    }

@app.post("/api/chat/text")
async def process_text_chat(
    request: Request,
    background_tasks: BackgroundTasks,
    text: str = Form(...),
    session_id: str = Form(...),
    voice_mode: str = Form("fast"),
    voice: Optional[str] = Form(None)
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
    language_mode = eval_result.get("language_mode", "indian_english")
    speech_register = eval_result.get("speech_register", "warm_conversational")
    
    user_wellness = eval_result.get("overall_wellness", 75)
    user_state = eval_result.get("dominant_state", "Calm")
    ai_audio_url = None
    if voice_mode and voice_mode != "none":
        try:
            ai_audio_url = await synthesize_speech(
                text=reply_text, 
                mode=voice_mode, 
                wellness_score=user_wellness if user_wellness is not None else 75, 
                dominant_state=user_state,
                language_mode=language_mode,
                spoken_text=spoken_text,
                voice=voice
            )
        except Exception as e:
            print(f"[!] Speech synthesis notice: {e}")

    current_sess = get_session(session_id, user_id=user["id"]) or get_session(session_id)
    new_title = None
    default_prefixes = ["Check-in", "New Reflection", "Emotional Wellness Reflection", "New Assessment", "Daily Reflection"]
    curr_t = current_sess.get("title", "") if current_sess else ""
    if current_sess and (any(curr_t.startswith(p) for p in default_prefixes)):
        new_title = eval_result.get("conversation_title") or generate_quick_session_title(text)

    # Asynchronous Database Persistence via FastAPI BackgroundTasks (0ms delay to client)
    background_tasks.add_task(
        _persist_turn,
        session_id=session_id,
        user_id=user["id"],
        transcript=text,
        user_audio_url=None,
        speech_metrics=dummy_acoustics,
        reply_text=reply_text,
        ai_audio_url=ai_audio_url,
        user_wellness=user_wellness,
        user_state=user_state,
        eval_result=eval_result,
        semitone_std=None,
        new_title=new_title
    )

    return {
        "transcript": text,
        "reply_text": reply_text,
        "audio_url": ai_audio_url,
        "user_emotion": eval_result.get("user_emotion", "calm"),
        "listening_face": eval_result.get("listening_face", "calm"),
        "speaking_face": eval_result.get("speaking_face", "caring"),
        "overall_wellness": user_wellness,
        "evaluation": eval_result,
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
    created = str(report.get("created_at") or "N/A")[:10]
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
        f"- **Lifetime Wellness Baseline:** {kpis.get('lifetime_wellness') if kpis.get('lifetime_wellness') is not None else 'Awaiting Data'}/100",
        f"- **Recent Wellness Average:** {kpis.get('recent_wellness') if kpis.get('recent_wellness') is not None else 'Awaiting Data'}/100",
        f"- **Trajectory Delta:** {kpis.get('trajectory_delta', 0.0):+} pts ({kpis.get('trajectory_status', 'Stable')})",
        f"- **Trajectory Assessment:** {kpis.get('trajectory_desc', '')}",
        f"- **Total Monitored Sessions:** {kpis.get('total_sessions', 0)}",
        f"- **Total Reflection Turns:** {kpis.get('total_reflections', 0)}",
        f"- **Average Pitch Variation:** {kpis.get('average_voice_semitones', '--')} semitones",
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
        w_val = item.get('wellness')
        lines.append(f"- **Wellness:** {w_val if w_val is not None else 'N/A'}/100 | **Dominant State:** {item.get('dominant_emotion', 'Reflective')}")
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


# ---------------------------------------------------------------------------
# CLINICAL INTELLIGENCE: STANDARDIZED ASSESSMENTS & DOCTOR / THERAPIST EXPORT
# ---------------------------------------------------------------------------
@app.get("/api/clinical/questions")
def get_clinical_questions():
    """Returns standardized PHQ-9 and GAD-7 screening questionnaires."""
    return {
        "phq9": {
            "title": "PHQ-9 (Patient Health Questionnaire - Depression)",
            "description": "Over the last 2 weeks, how often have you been bothered by any of the following problems?",
            "scale": RESPONSE_SCALE,
            "questions": PHQ9_QUESTIONS
        },
        "gad7": {
            "title": "GAD-7 (Generalized Anxiety Disorder Screener)",
            "description": "Over the last 2 weeks, how often have you been bothered by the following problems?",
            "scale": RESPONSE_SCALE,
            "questions": GAD7_QUESTIONS
        }
    }

@app.post("/api/clinical/assessment")
async def submit_clinical_assessment(request: Request):
    """Evaluates and persists standardized PHQ-9 or GAD-7 assessments."""
    user = get_effective_user(request)
    try:
        data = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid payload")

    assessment_type = (data.get("assessment_type") or "phq9").lower().strip()
    answers = data.get("answers", {})
    session_id = data.get("session_id")

    if assessment_type == "phq9":
        result = score_phq9(answers)
    elif assessment_type == "gad7":
        result = score_gad7(answers)
    else:
        raise HTTPException(status_code=400, detail="Unsupported assessment type. Use 'phq9' or 'gad7'.")

    saved = save_clinical_assessment(
        user_id=user["id"],
        session_id=session_id,
        assessment_type=assessment_type,
        total_score=result["total_score"],
        severity=result["severity"],
        answers=result["answers"],
        clinical_notes=result.get("clinical_action", "")
    )
    result["saved_at"] = saved["created_at"]
    return result

@app.get("/api/clinical/assessments")
def list_clinical_assessments(request: Request):
    """Lists past standardized clinical assessments for the authenticated user."""
    user = get_effective_user(request)
    return {
        "assessments": get_user_clinical_assessments(user["id"], limit=10)
    }

@app.get("/api/clinical/report/doctor-summary")
def get_doctor_summary_html(request: Request, session_id: Optional[str] = None):
    """
    Returns a high-design, print-ready Clinical Summary Report HTML view
    designed for psychiatrists, therapists, and medical healthcare providers.
    """
    from fastapi.responses import HTMLResponse
    user = get_effective_user(request)
    summary = get_doctor_clinical_summary(user_id=user["id"], session_id=session_id)
    pat = summary.get("patient", {})
    bw = summary.get("baseline_wellness", {})
    std_ass = summary.get("standardized_assessments", {})
    phq = std_ass.get("phq9")
    gad = std_ass.get("gad7")
    ac = summary.get("acoustic_biomarkers", {})
    evidence = summary.get("evidence_symptoms", [])

    phq_html = f"""
        <div class="clinical-score-card">
            <div class="card-tag">DEPRESSION SCREENER (PHQ-9)</div>
            <div class="score-display">
                <span class="score-big">{phq.get('total_score', '--')}</span>
                <span class="score-scale">/27</span>
            </div>
            <div class="severity-pill {'severity-high' if phq.get('total_score', 0) >= 15 else ('severity-med' if phq.get('total_score', 0) >= 10 else 'severity-low')}">
                {phq.get('severity', 'Not Taken Yet')}
            </div>
            <p class="action-note"><strong>Clinical Guidance:</strong> {phq.get('clinical_notes', 'Psychoeducation and supportive monitoring.')}</p>
            {f'<div class="alert-suicide-flag"><strong>Safety Trigger:</strong> Affirmative response on Item 9 (Self-harm/Suicidal ideation). Urgent clinical assessment advised.</div>' if phq.get('answers', {}).get('9', 0) > 0 else ''}
        </div>
    """ if phq else """
        <div class="clinical-score-card not-taken">
            <div class="card-tag">DEPRESSION SCREENER (PHQ-9)</div>
            <div class="score-display"><span class="score-big">--</span><span class="score-scale">/27</span></div>
            <p class="action-note">Patient has not yet completed a formal PHQ-9 assessment.</p>
        </div>
    """

    gad_html = f"""
        <div class="clinical-score-card">
            <div class="card-tag">ANXIETY SCREENER (GAD-7)</div>
            <div class="score-display">
                <span class="score-big">{gad.get('total_score', '--')}</span>
                <span class="score-scale">/21</span>
            </div>
            <div class="severity-pill {'severity-high' if gad.get('total_score', 0) >= 15 else ('severity-med' if gad.get('total_score', 0) >= 10 else 'severity-low')}">
                {gad.get('severity', 'Not Taken Yet')}
            </div>
            <p class="action-note"><strong>Clinical Guidance:</strong> {gad.get('clinical_notes', 'Grounding breathing, cognitive restructuring.')}</p>
        </div>
    """ if gad else """
        <div class="clinical-score-card not-taken">
            <div class="card-tag">ANXIETY SCREENER (GAD-7)</div>
            <div class="score-display"><span class="score-big">--</span><span class="score-scale">/21</span></div>
            <p class="action-note">Patient has not yet completed a formal GAD-7 assessment.</p>
        </div>
    """

    evidence_rows = ""
    for ev in evidence:
        quotes = ev.get("quote", "")
        evidence_rows += f"""
            <tr>
                <td style="font-weight: 600; width: 25%;">{ev.get('label', 'Indicator')}</td>
                <td style="width: 15%; text-align: center;"><span class="badge-evidence-score">Level {ev.get('score', 0)}/3</span></td>
                <td style="font-style: italic; color: #475569;">"{quotes}"</td>
            </tr>
        """
    if not evidence_rows:
        evidence_rows = "<tr><td colspan='3' style='text-align:center; color:#94a3b8; padding: 1.5rem;'>No explicit symptom indicators noted across recent dialogue.</td></tr>"

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Arogya • Clinical Summary & Triage Report</title>
    <style>
        :root {{
            --primary: #0f172a;
            --accent: #2563eb;
            --border: #e2e8f0;
            --bg-card: #f8fafc;
            --text-dark: #0f172a;
            --text-muted: #64748b;
        }}
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
            background: #f1f5f9;
            color: var(--text-dark);
            line-height: 1.5;
            padding: 2rem 1rem;
        }}
        .report-page {{
            max-width: 900px;
            margin: 0 auto;
            background: #ffffff;
            border-radius: 12px;
            box-shadow: 0 4px 20px rgba(0,0,0,0.06);
            padding: 2.5rem 3rem;
            border: 1px solid var(--border);
        }}
        .report-header {{
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
            border-bottom: 2px solid var(--border);
            padding-bottom: 1.5rem;
            margin-bottom: 2rem;
        }}
        .brand-title {{ font-size: 1.35rem; font-weight: 800; letter-spacing: -0.02em; color: var(--primary); }}
        .brand-sub {{ font-size: 0.85rem; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.05em; margin-top: 0.2rem; }}
        .header-actions {{ display: flex; gap: 0.75rem; }}
        .btn-print {{
            background: var(--accent);
            color: #ffffff;
            border: none;
            padding: 0.5rem 1rem;
            font-size: 0.85rem;
            font-weight: 600;
            border-radius: 6px;
            cursor: pointer;
            box-shadow: 0 2px 4px rgba(37,99,235,0.2);
        }}
        .btn-print:hover {{ background: #1d4ed8; }}
        .patient-grid {{
            display: grid;
            grid-template-columns: repeat(4, 1fr);
            gap: 1rem;
            background: var(--bg-card);
            padding: 1.25rem;
            border-radius: 8px;
            border: 1px solid var(--border);
            margin-bottom: 2rem;
        }}
        .meta-item .meta-label {{ font-size: 0.75rem; color: var(--text-muted); text-transform: uppercase; font-weight: 600; }}
        .meta-item .meta-value {{ font-size: 0.95rem; font-weight: 700; color: var(--primary); margin-top: 0.2rem; }}
        
        .section-heading {{
            font-size: 1.05rem;
            font-weight: 700;
            color: var(--primary);
            border-bottom: 1px solid var(--border);
            padding-bottom: 0.4rem;
            margin-bottom: 1rem;
            margin-top: 2rem;
        }}
        .scores-grid {{
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 1.25rem;
            margin-bottom: 2rem;
        }}
        .clinical-score-card {{
            background: var(--bg-card);
            border: 1px solid var(--border);
            border-radius: 8px;
            padding: 1.25rem;
            position: relative;
        }}
        .clinical-score-card.not-taken {{ opacity: 0.65; }}
        .card-tag {{ font-size: 0.75rem; font-weight: 700; color: var(--text-muted); letter-spacing: 0.03em; }}
        .score-display {{ display: flex; align-items: baseline; margin: 0.5rem 0; }}
        .score-big {{ font-size: 2.2rem; font-weight: 800; color: var(--primary); }}
        .score-scale {{ font-size: 1rem; color: var(--text-muted); margin-left: 0.25rem; }}
        .severity-pill {{
            display: inline-block;
            padding: 0.2rem 0.65rem;
            font-size: 0.75rem;
            font-weight: 700;
            border-radius: 9999px;
            text-transform: uppercase;
        }}
        .severity-low {{ background: #dcfce7; color: #166534; }}
        .severity-med {{ background: #fef9c3; color: #854d0e; }}
        .severity-high {{ background: #fee2e2; color: #991b1b; }}
        .action-note {{ font-size: 0.85rem; color: #334155; margin-top: 0.75rem; }}
        .alert-suicide-flag {{
            background: #fef2f2;
            border: 1px solid #f87171;
            color: #991b1b;
            padding: 0.6rem;
            border-radius: 6px;
            font-size: 0.8rem;
            margin-top: 0.75rem;
        }}
        
        .evidence-table {{
            width: 100%;
            border-collapse: collapse;
            font-size: 0.85rem;
            margin-top: 0.5rem;
        }}
        .evidence-table th {{
            background: #f8fafc;
            text-align: left;
            padding: 0.6rem 0.75rem;
            border-bottom: 2px solid var(--border);
            color: var(--text-muted);
            font-size: 0.75rem;
            text-transform: uppercase;
        }}
        .evidence-table td {{
            padding: 0.75rem;
            border-bottom: 1px solid var(--border);
            vertical-align: top;
        }}
        .badge-evidence-score {{
            display: inline-block;
            background: #e2e8f0;
            color: #334155;
            padding: 0.15rem 0.5rem;
            border-radius: 4px;
            font-weight: 600;
            font-size: 0.75rem;
        }}
        
        .biomarkers-row {{
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 1rem;
            margin-top: 0.75rem;
            background: var(--bg-card);
            padding: 1rem;
            border-radius: 8px;
            border: 1px solid var(--border);
        }}
        
        .helplines-box {{
            background: #f0fdf4;
            border: 1px solid #bbf7d0;
            border-radius: 8px;
            padding: 1rem;
            margin-top: 2rem;
            font-size: 0.85rem;
            color: #166534;
        }}
        .helplines-box strong {{ color: #14532d; }}
        .disclaimer-box {{
            margin-top: 2rem;
            padding-top: 1.25rem;
            border-top: 1px solid var(--border);
            font-size: 0.75rem;
            color: var(--text-muted);
            text-align: justify;
        }}
        @media print {{
            body {{ background: #ffffff; padding: 0; }}
            .report-page {{ border: none; box-shadow: none; padding: 0; }}
            .btn-print {{ display: none; }}
        }}
    </style>
</head>
<body>
    <div class="report-page">
        <header class="report-header">
            <div>
                <div class="brand-title">Arogya • Clinical Intelligence Suite</div>
                <div class="brand-sub">Comprehensive Affective & Psychiatric Triage Summary</div>
            </div>
            <div class="header-actions">
                <button class="btn-print" onclick="window.print()">Print / Export PDF</button>
            </div>
        </header>

        <section class="patient-grid">
            <div class="meta-item">
                <div class="meta-label">Patient Name</div>
                <div class="meta-value">{pat.get('display_name', 'Patient')}</div>
            </div>
            <div class="meta-item">
                <div class="meta-label">Patient ID / Reference</div>
                <div class="meta-value">{pat.get('id', 'guest_user')[:14]}</div>
            </div>
            <div class="meta-item">
                <div class="meta-label">Assessment Date</div>
                <div class="meta-value">{summary.get('generated_at', '')}</div>
            </div>
            <div class="meta-item">
                <div class="meta-label">Longitudinal Sessions</div>
                <div class="meta-value">{pat.get('total_sessions', 1)} Completed</div>
            </div>
        </section>

        <h3 class="section-heading">1. Validated Standardized Screening Instruments</h3>
        <div class="scores-grid">
            {phq_html}
            {gad_html}
        </div>

        <h3 class="section-heading">2. Longitudinal Trajectory & Baseline Stability</h3>
        <div class="patient-grid" style="grid-template-columns: repeat(3, 1fr); margin-bottom: 1.5rem;">
            <div class="meta-item">
                <div class="meta-label">Running Mean Wellness</div>
                <div class="meta-value">{round(bw.get('mean', 75.0), 1)} / 100</div>
            </div>
            <div class="meta-item">
                <div class="meta-label">Variance (Std Dev)</div>
                <div class="meta-value">&plusmn;{round(bw.get('std', 10.0), 1)} pts</div>
            </div>
            <div class="meta-item">
                <div class="meta-label">Dominant Affective State</div>
                <div class="meta-value">{bw.get('dominant_state', 'Reflective')}</div>
            </div>
        </div>

        <h3 class="section-heading">3. Objective Acoustic Biomarkers (Digital Signal Processing)</h3>
        <div class="biomarkers-row">
            <div class="meta-item">
                <div class="meta-label">Pitch Variation (Semitones)</div>
                <div class="meta-value">{f"{ac.get('semitone_std')} st" if ac.get('semitone_std') is not None else "Text Dialogue"}</div>
            </div>
            <div class="meta-item">
                <div class="meta-label">Vocal Vitality Score</div>
                <div class="meta-value">{ac.get('vitality_index', 80)}%</div>
            </div>
            <div class="meta-item">
                <div class="meta-label">Prosodic Attunement</div>
                <div class="meta-value">Continuous / In-Memory</div>
            </div>
        </div>

        <h3 class="section-heading">4. Verbatim Quote-Backed Symptom Evidence</h3>
        <table class="evidence-table">
            <thead>
                <tr>
                    <th>Domain</th>
                    <th style="text-align: center;">Evaluated Level</th>
                    <th>Exact Patient Dialogue Evidence</th>
                </tr>
            </thead>
            <tbody>
                {evidence_rows}
            </tbody>
        </table>

        <div class="helplines-box">
            <strong>National Mental Health Emergency Contacts (India 24/7):</strong><br>
            &bull; <strong>Tele-MANAS (Govt. of India):</strong> 14416 (Toll-free)<br>
            &bull; <strong>KIRAN Mental Health Support:</strong> 1800-599-0019<br>
            &bull; <strong>Vandrevala Foundation:</strong> +91 9999 666 555
        </div>

        <div class="disclaimer-box">
            <strong>Clinical Disclaimer:</strong> {summary.get('disclaimer')}
        </div>
    </div>
</body>
</html>"""
    return HTMLResponse(content=html)

@app.get("/api/clinical/report/doctor-summary/download")
def download_doctor_summary_markdown(request: Request, session_id: Optional[str] = None):
    """Downloads doctor summary as formatted clinical Markdown."""
    user = get_effective_user(request)
    summary = get_doctor_clinical_summary(user_id=user["id"], session_id=session_id)
    pat = summary.get("patient", {})
    bw = summary.get("baseline_wellness", {})
    std_ass = summary.get("standardized_assessments", {})
    phq = std_ass.get("phq9")
    gad = std_ass.get("gad7")
    ac = summary.get("acoustic_biomarkers", {})
    evidence = summary.get("evidence_symptoms", [])

    lines = [
        "# Arogya • Clinical Summary & Triage Report",
        f"**Generated:** {summary.get('generated_at')}",
        f"**Patient Name:** {pat.get('display_name', 'Patient')}",
        f"**Patient ID:** {pat.get('id', 'guest_user')}",
        f"**Total Sessions Monitored:** {pat.get('total_sessions', 1)}",
        "",
        "## 1. Validated Standardized Screening Scores",
        f"- **PHQ-9 Depression Screener:** {phq.get('total_score', 'N/A') if phq else 'Not Taken'}/27 ({phq.get('severity', '') if phq else ''})",
        f"  *Clinical Action:* {phq.get('clinical_notes', 'N/A') if phq else 'N/A'}",
        f"- **GAD-7 Anxiety Screener:** {gad.get('total_score', 'N/A') if gad else 'Not Taken'}/21 ({gad.get('severity', '') if gad else ''})",
        f"  *Clinical Action:* {gad.get('clinical_notes', 'N/A') if gad else 'N/A'}",
        "",
        "## 2. Longitudinal Trajectory & Baseline",
        f"- **Running Baseline Mean:** {round(bw.get('mean', 75.0), 1)}/100",
        f"- **Variance (Std Dev):** ±{round(bw.get('std', 10.0), 1)} pts",
        f"- **Dominant Emotional State:** {bw.get('dominant_state', 'Reflective')}",
        "",
        "## 3. Objective Acoustic Biomarkers",
        f"- **Pitch Variation:** {ac.get('semitone_std', 'N/A')} semitones",
        f"- **Vocal Vitality Index:** {ac.get('vitality_index', 80)}%",
        "",
        "## 4. Grounded Quote-Backed Evidence",
    ]
    for ev in evidence:
        lines.append(f"- **{ev.get('label')}:** Level {ev.get('score')}/3 | *Quote:* \"{ev.get('quote')}\"")

    lines.append("")
    lines.append("## 5. Emergency Support Resources")
    lines.append("- **Tele-MANAS:** 14416 (Toll-free)")
    lines.append("- **KIRAN:** 1800-599-0019")
    lines.append("")
    lines.append(f"*{summary.get('disclaimer')}*")

    content = "\n".join(lines)
    from fastapi.responses import Response
    return Response(
        content=content,
        media_type="text/markdown",
        headers={"Content-Disposition": "attachment; filename=Arogya_Doctor_Clinical_Summary.md"}
    )



if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    host = os.environ.get("HOST", "0.0.0.0")
    uvicorn.run("app:app", host=host, port=port, reload=False)

