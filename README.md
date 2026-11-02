<div align="center">

  <img src="mental_health_voice_ai/static/assets/icon-192.png" alt="Arogya Emblem" width="100" style="border-radius: 24px; box-shadow: 0 8px 24px rgba(0,0,0,0.3); margin-bottom: 16px;" />

  # 🌿 Arogya (ஆரோக்கியா)
  ### Real-Time Embodied Voice Companion & Acoustic Biomarker Mental Health AI

  <p align="center">
    <strong>Sub-second voice AI companion powered by Groq LPU™, Neon Serverless PostgreSQL, Edge-TTS, and DSP Acoustic Biomarkers — engineered for loneliness, elderly care, and emotional de-escalation.</strong>
  </p>

  <p align="center">
    <a href="https://fastapi.tiangolo.com/"><img src="https://img.shields.io/badge/FastAPI-0.115+-009688?style=for-the-badge&logo=fastapi&logoColor=white" alt="FastAPI" /></a>
    <a href="https://groq.com/"><img src="https://img.shields.io/badge/Groq%20LPU-Ultra--Fast-F55036?style=for-the-badge&logo=groq&logoColor=white" alt="Groq LPU" /></a>
    <a href="https://neon.tech/"><img src="https://img.shields.io/badge/Neon-PostgreSQL%20Serverless-00E599?style=for-the-badge&logo=postgresql&logoColor=black" alt="Neon PostgreSQL" /></a>
    <a href="https://render.com/"><img src="https://img.shields.io/badge/Render-Free%20Tier%20Optimized-46E3B7?style=for-the-badge&logo=render&logoColor=white" alt="Render" /></a>
    <a href="https://github.com/logesh-profile/arogya/blob/main/LICENSE"><img src="https://img.shields.io/badge/License-MIT-blue.svg?style=for-the-badge" alt="License" /></a>
  </p>
</div>

---

## 📸 Real System Showcase & Hardware Embodiment

Arogya is designed not just as a software app, but as a **physical, room-scale companion presence** that elderly individuals, isolated students, and anyone experiencing loneliness can talk to hands-free without staring at screens or typing text.

<div align="center">
  <table>
    <tr>
      <td width="50%" align="center">
        <img src="mental_health_voice_ai/static/assets/companion_robot_chatting.jpg" alt="Arogya Conversational Companion Setup" style="border-radius: 12px; width: 100%; object-fit: cover;" />
        <br />
        <strong>Interactive Companion Robot in Conversational Dialogue</strong>
        <p><em>Real-time voice exchange, dynamic facial expression attunement, and hands-free full-duplex VAD.</em></p>
      </td>
      <td width="50%" align="center">
        <img src="mental_health_voice_ai/static/assets/companion_robot_elderly.jpg" alt="Arogya Companion for Elderly Care" style="border-radius: 12px; width: 100%; object-fit: cover;" />
        <br />
        <strong>Ambient Presence & Elderly Companionship</strong>
        <p><em>De-escalating loneliness and chronic isolation through natural spoken Tamil & Tanglish dialogue.</em></p>
      </td>
    </tr>
    <tr>
      <td width="50%" align="center">
        <img src="mental_health_voice_ai/static/assets/companion_talking_elder.jpg" alt="Companion Talking to Elder" style="border-radius: 12px; width: 100%; object-fit: cover;" />
        <br />
        <strong>Voice-First Empathetic Grounding</strong>
        <p><em>Zero keyboard friction: users speak freely and Arogya listens, reflects, and co-regulates stress.</em></p>
      </td>
      <td width="50%" align="center">
        <img src="mental_health_voice_ai/static/assets/companion_robot_elder.jpg" alt="Desktop Companion Hardware" style="border-radius: 12px; width: 100%; object-fit: cover;" />
        <br />
        <strong>Embodied Desktop Form Factor</strong>
        <p><em>ESP32 microcontrollers synchronize speech states, WiFi CSI room presence, and somatic cues.</em></p>
      </td>
    </tr>
  </table>
</div>

---

## 🌟 The Core Challenge: Why Arogya Exists

Traditional mental health apps and chatbots suffer from five critical flaws:

| Problem in Legacy AI Chatbots | Why It Fails In Real Life | How Arogya Solves It |
| :--- | :--- | :--- |
| **Typing Friction & Stigma** | Overwhelmed, depressed, or elderly users lack the cognitive energy to type lengthy paragraphs into a screen. | **Hands-Free Ambient VAD**: Operates like a companion sitting on the table. Speak naturally; it listens, pauses, and replies with zero clicks. |
| **Diglossia & Vernacular Barrier** | Chatbots reply in formal, textbook Tamil (*"நீங்கள் ஓய்வு எடுக்க வேண்டும்"*) or stiff English that alienates Indian youth and seniors. | **Dual-Channel Tanglish Naturalizer**: Displays clean Latin-script Tanglish in UI while synthesizing authentic colloquial spoken Tamil (*"கொஞ்சம் rest எடுங்க, namma pesalaam"*). |
| **High Latency (4–8s Delays)** | Waiting 6 seconds for a cloud LLM + TTS pipeline breaks the natural emotional rhythm of human conversation. | **Groq LPU Sub-Second Pipeline**: Whisper Turbo (~0.5s) + Groq LLM (~0.3s) + Edge-TTS (~0.35s) = Instant sub-second response. |
| **Hallucinated Clinical Claims** | Chatbots offer ungrounded psychobabble or false diagnoses without accountability. | **Zero-Hallucination Evidence Scoring**: Verbatim quote-backed scoring (4 DSM-5/PHQ-9 dimensions). *No exact quote = No points.* |
| **High Resource & Battery Drain** | Uncapped browser visualizers spike CPU/GPU to 100% and drain batteries rapidly. | **Strict 30 FPS Hardware Throttler**: Visualizer loop capped at 30 FPS, idling at 0 FPS / 0% CPU when silent. |

---

## 🛠️ Complete System Architecture

```mermaid
flowchart TD
    %% Audio Ingestion & Frontend
    subgraph ClientLayer ["1. Client Interface & Audio Ingestion"]
        A["User Spoken Voice\n(Tanglish / Tamil / Indian English)"] --> B["Web Audio API Input\n(boAt Headset / Laptop Mic Array)"]
        B --> C["Hardware Full-Duplex VAD\n(1.4s Natural Pause Auto-Submit)"]
        C --> D["30 FPS Dynamic Visualizer\n(setTimeout 33ms Capped, 0% CPU on Idle)"]
        C --> E["WAV Audio Payload\n(16kHz Mono PCM)"]
    end

    %% Edge Safety & High-Speed STT
    subgraph FastAPILayer ["2. FastAPI Async Application Router"]
        E --> F["POST /api/chat/voice"]
        F --> G["Groq Whisper LPU\n(whisper-large-v3-turbo ~0.5s)"]
        G --> H["Transcribed Conversational Text"]
        H --> I{"Pre-Execution Safety Triage\n(openai/gpt-oss-safeguard-20b)"}
        
        %% Crisis Branch
        I -- "Self-Harm / Crisis Detected" --> CR["Immediate Crisis Circuit Breaker\n(Tele-MANAS 14416 + KIRAN 1800-599-0019)"]
        
        %% Safe Reasoning Branch
        I -- "Safe Dialogue" --> J["Session & Context Assembly\n(Request-Scoped DB Connection)"]
    end

    %% Database & State Isolation
    subgraph StorageLayer ["3. Cloud Persistence & Data Isolation"]
        DB[(Neon Serverless PostgreSQL\nRowWrapper + SSL Connection Pool)]
        DB -->|"Fetch Past 10 Turns &\nLong-Term Clinical Profile"| J
    end

    %% Groq LPU Reasoning & Evidence Scoring
    subgraph GroqLPULayer ["4. Groq Ultra-Fast LPU Engine"]
        J --> K["Groq LPU Conversational LLM\n(qwen/qwen3.8-27b ~0.3s)"]
        K --> L["Dual-Channel Generation\n• Channel 1: UI Tanglish\n• Channel 2: Spoken Tamil Prosody"]
        K --> M["Quote-Grounded Evidence Evaluator\n(DSM-5 / PHQ-9 Symptom Dimensions)"]
    end

    %% Voice Synthesis & Async Background Tasks
    subgraph SpeechOutputLayer ["5. Audio Synthesis & Async Storage"]
        L --> N["Microsoft Edge-TTS Neural\n(ta-IN-PallaviNeural / en-IN-NeerjaNeural ~0.35s)"]
        N --> O["Synthesized Audio Base64 + Audio URL"]
        
        %% FastAPI BackgroundTasks
        M --> P["FastAPI BackgroundTasks\n(_persist_turn Non-Blocking Execution)"]
        P -.->|"Asynchronous Turn Logging &\nLongitudinal Profile Update"| DB
    end

    %% Response Delivery & Embodiment
    subgraph EmbodiedOutput ["6. Delivery, Somatic Grounding & Robotics"]
        O --> Q["Instant Browser Audio Playback\n(Sub-Second Total Turnaround)"]
        O --> R["ESP32 Microcontroller Bridge\n(Wi-Fi / Serial Facial Animation Sync)"]
        Q --> S["Somatic Grounding System\n(Box Breathing 4-4-4-4 + 432Hz Harmonic Chimes)"]
    end

    CR --> Q
```

---

## ⚡ Architectural Highlights & Technical Pillars

### 1. 🚀 Ultra-Low Latency Groq LPU Pipeline
- **Groq Whisper Large v3 Turbo (`whisper-large-v3-turbo`)**: Transcribes raw speech payloads to text in **~450ms–600ms**, replacing bulky local models and avoiding GPU memory bottlenecks on cloud servers.
- **Groq LPU Reasoning (`qwen/qwen3.8-27b`)**: Generates empathetic, clinically grounded turns in **~250ms–350ms** with zero cold starts.
- **Microsoft Edge-TTS (`ta-IN-PallaviNeural`, `en-IN-NeerjaNeural`)**: Generates crystal-clear spoken Tamil and Indian English speech in **~350ms–400ms**.
- **End-to-End Latency**: The complete loop from user voice end-of-speech to robotic voice output completes in **~1.0 to 1.3 seconds**.

### 2. 🛡️ Multi-User Data Isolation & Neon PostgreSQL Serverless
- **Zero Global Memory Leaks**: All user sessions, turns, and profiles are persisted in PostgreSQL tables (`users`, `sessions`, `turns`, `clinical_evaluations`, `user_clinical_profile`). No shared in-memory dictionaries or cross-user contamination.
- **Cross-Compatible RowWrapper Architecture**: Custom lightweight wrapper bridging PostgreSQL `psycopg2.extras.RealDictCursor` dictionary outputs with legacy tuple indexing (`[0]`), ensuring zero crash regressions.
- **Request-Scoped Connections**: Database connections are created per request using connection pooling with SSL encryption and safe closing.

### 3. 🎯 Non-Blocking FastAPI BackgroundTasks
- **Immediate User Response**: The HTTP endpoint returns speech audio and response text immediately to the user without waiting for database operations to finish.
- **Asynchronous Persistence (`_persist_turn`)**: Database insertion of chat history, session title generation, and long-term clinical profile updating occur asynchronously in the background via FastAPI's native `BackgroundTasks`.

### 4. 🎛️ Client-Side 30 FPS Hardware Timer (Zero GPU Burn)
- **Eliminating 144Hz Runaway CPU Usage**: High-refresh gaming monitors and laptop screens previously drove `requestAnimationFrame` loops at 144–240 FPS, causing excessive battery drain.
- **Hardware Throttling**: The visualizer is governed by a strict 30 FPS hardware timer (`setTimeout(..., 33)`), decoupling animation speed from screen refresh rate.
- **Complete Idle Sleep**: When the user is silent and audio is not playing, the canvas animation loop halts completely (0 FPS, 0% CPU).

### 5. 🗣️ Dual-Channel Spoken Tamil & Tanglish Naturalizer
- **Channel 1 (UI Presentation)**: Conversational, friendly Tanglish in Latin script:
  > *"Romba tired-ah irukka bro? Konjam rest edunga, namma aprama pesalaam."*
- **Channel 2 (TTS Synthesis)**: Authentic spoken colloquial Tamil (*பேச்சுத் தமிழ்*) without diglossia artifacts:
  > *"ரொம்ப tired-ஆ இருக்கா ப்ரோ? கொஞ்சம் rest எடுங்க... நம்ம அப்றமா பேசலாம்."*
- **Eliminates Stiff Robot Syndrome**: Replaces formal textbook phrases (*"நீங்கள் ஓய்வு எடுக்க வேண்டும்"*) with genuine warmth (*"கொஞ்சம் rest எடுங்க"*, *"என்ன ஆச்சு"*, *"நான் help பண்றேன்"*).

### 6. 📊 Zero-Hallucination Evidence Scoring (DSM-5 / PHQ-9 Aligned)
- Assesses 4 core emotional symptom dimensions:
  1. **Stress & Pressure**
  2. **Worry & Apprehension**
  3. **Fatigue & Low Energy**
  4. **Emotional Heaviness**
- **Strict Empirical Standard**: Every awarded point strictly requires an exact verbatim quote from the user's transcript. **No verbatim quote = 0 points**.
- **Longitudinal Tracking**: Multi-session wellness scores (0–100) are compiled into the `/analytics` portal for self-reflection and therapeutic review.

### 7. 🚨 Immediate Crisis Triage & Safety Protocol
- Independent safety filter powered by Groq's `openai/gpt-oss-safeguard-20b` (with fallback to `meta-llama/llama-prompt-guard-2-86m`).
- Instantly detects acute distress, self-harm, or suicidal ideation before any generative turn.
- Automatically launches the **Confidential Support Resources** modal, surfacing toll-free national helplines:
  - **Tele-MANAS (Govt. of India)**: `14416` (24/7 National Toll-Free)
  - **KIRAN Mental Health Service**: `1800-599-0019`
  - **Vandrevala Foundation**: `9999 666 555`

---

## 🔄 Architectural Evolution: Before vs. After

| Architecture Component | Old Setup | Current Arogya Setup | Direct Benefit |
| :--- | :--- | :--- | :--- |
| **Speech-to-Text (STT)** | Local Faster-Whisper (CUDA FP16, 1.8GB RAM) | **Groq Whisper Large v3 Turbo** (`whisper-large-v3-turbo`) | 0.5s transcript speed; RAM drops from 1.8GB to **< 120MB** |
| **Reasoning Engine** | Gemini 3.5 Flash Lite (API quota rate limits) | **Groq LPU** (`qwen/qwen3.8-27b`) | 250ms token generation; zero rate-limiting hiccups |
| **Safety Guard** | Static regex or slow external filter | **Groq Safeguard** (`openai/gpt-oss-safeguard-20b`) | Pre-execution safety check in ~150ms |
| **Database Architecture** | Local SQLite3 only (unsuitable for cloud servers) | **Neon Serverless PostgreSQL** + SQLite3 fallback | Multi-tenant user isolation, cloud persistence across restarts |
| **Execution Flow** | Synchronous endpoint blocking on DB saves | **FastAPI `BackgroundTasks`** | Immediate audio delivery; DB writes happen in background |
| **UI Canvas Visualizer** | Uncapped `requestAnimationFrame` (144+ FPS, high CPU) | **Strict 30 FPS Timer** (`setTimeout 33ms`, 0% idle) | 0% CPU on idle; prevents laptop/phone battery overheating |
| **Deployment Target** | Requires 6GB NVIDIA GPU locally | **100% Render Free Tier Ready** | Can be hosted completely free 24/7 on the cloud |

---

## 🗄️ Database Schema & Isolation Model

```mermaid
erDiagram
    users ||--o{ sessions : "owns"
    users ||--o{ clinical_evaluations : "has"
    users ||--o| user_clinical_profile : "maintains"
    sessions ||--o{ turns : "contains"

    users {
        string id PK
        string email UK
        string name
        string avatar_url
        string auth_provider
        timestamp created_at
    }

    sessions {
        string id PK
        string user_id FK
        string title
        timestamp created_at
    }

    turns {
        string id PK
        string session_id FK
        string user_id FK
        string role
        text content
        timestamp created_at
    }

    clinical_evaluations {
        string id PK
        string session_id FK
        string user_id FK
        int stress_score
        int worry_score
        int fatigue_score
        int heaviness_score
        int overall_wellness
        json quote_evidence
        timestamp created_at
    }

    user_clinical_profile {
        string user_id PK, FK
        string preferred_name
        json stressors
        json coping_mechanisms
        int baseline_wellness
        timestamp updated_at
    }
```

---

## 📡 Core API Specification

| Endpoint | Method | Scope | Description |
| :--- | :---: | :--- | :--- |
| `/` | `GET` | Public | Main conversational companion interface |
| `/analytics` | `GET` | Authenticated | Longitudinal multi-session analytics and clinical reflections |
| `/manifest.json` | `GET` | Public | Progressive Web App (PWA) manifest |
| `/api/health` | `GET` | Public | Healthcheck ping endpoint (keeps Render container awake) |
| `/api/auth/me` | `GET` | Session | Retrieve current logged-in user and onboarding state |
| `/api/auth/google` | `POST` | Public | Authenticate via Google Identity Services OAuth 2.0 credential |
| `/api/auth/update-name` | `POST` | Authenticated | Update user's preferred conversational display name |
| `/api/auth/logout` | `POST` | Authenticated | Terminate session and clear HTTP-only auth cookies |
| `/api/chat/voice` | `POST` | Authenticated | Full-duplex speech-to-speech loop with Groq Whisper & Edge-TTS |
| `/api/chat/text` | `POST` | Authenticated | Text conversation with quote-backed clinical evaluation |
| `/api/analytics/summary`| `GET` | Authenticated | Longitudinal wellness trends, radar metrics, and profile anchors |
| `/api/analytics/export/download` | `GET` | Authenticated | Download complete clinical summary report in Markdown |
| `/api/esp32/speech_state` | `GET` | Hardware | Synchronize speaking/listening states with ESP32 OLED face |

---

## 🚀 Deployment & Setup Guide

### 1. Prerequisites
- **Python 3.10 or 3.11** installed
- **FFmpeg** installed and accessible in system `PATH`
- A free **Groq API Key** from [console.groq.com](https://console.groq.com/)
- (Optional for Cloud) A free **Neon Serverless PostgreSQL** database URL from [neon.tech](https://neon.tech/)

### 2. Local Installation
```bash
# Clone the repository
git clone https://github.com/logesh-profile/arogya.git
cd arogya

# Create and activate virtual environment
python -m venv venv

# Windows:
venv\Scripts\activate
# Linux/macOS:
source venv/bin/activate

# Install lightweight dependencies (< 150MB total)
pip install -r requirements.txt
```

### 3. Environment Configuration
Create a `.env` file in `mental_health_voice_ai/`:
```env
# Groq Ultra-Fast LPU API Key
GROQ_API_KEY=gsk_your_groq_api_key_here

# PostgreSQL Database (Leave blank to automatically use local SQLite3)
DATABASE_URL=postgresql://user:password@ep-cool-cloud.neon.tech/neondb?sslmode=require

# Google OAuth 2.0 Client ID (Free Google Sign-In)
GOOGLE_CLIENT_ID=your_google_client_id.apps.googleusercontent.com

# Session Secret Key
SESSION_SECRET_KEY=arogya_secure_session_secret_2026
```

### 4. Running the Application
```bash
# Launch FastAPI backend with live reloading
python mental_health_voice_ai/run_arogya.py
```
Open **`http://localhost:8000`** in Google Chrome or Microsoft Edge.

---

## ☁️ Deploying to Render (Free Tier Optimized)

Arogya is specifically optimized to run within Render's free tier (512MB RAM, shared vCPU) with zero out-of-memory crashes:

1. **Push your code to GitHub**:
   ```bash
   git push origin main
   ```
2. **Create a New Web Service on Render**:
   - Connect your GitHub repository `arogya`.
   - **Environment**: `Python 3`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `uvicorn mental_health_voice_ai.app:app --host 0.0.0.0 --port $PORT`
3. **Add Environment Variables in Render Dashboard**:
   - `GROQ_API_KEY`: `gsk_...`
   - `DATABASE_URL`: `postgresql://...` (from Neon)
   - `GOOGLE_CLIENT_ID`: `...apps.googleusercontent.com`
   - `SESSION_SECRET_KEY`: `arogya_secret_key`
4. **Prevent Free Tier Cold Starts**:
   - Setup a free ping monitor (e.g., [Cron-Job.org](https://cron-job.org/) or [UptimeRobot](https://uptimerobot.com/)) to send a `GET` request to your `https://your-app.onrender.com/api/health` endpoint every **10 minutes**.
   - This keeps your Render container active 24/7 with zero cold starts.

---

## 🔒 Ethical AI & Clinical Safety Disclaimer

> [!IMPORTANT]
> **Arogya is an emotional wellness companion, loneliness de-escalation tool, and somatic grounding guide. It is NOT a diagnostic medical device and does NOT provide psychiatric prescriptions or replace professional clinical therapy.**
>
> In any circumstance involving acute psychological distress, self-harm ideation, or domestic emergency, Arogya immediately halts automated AI processing and directs users to India's national 24/7 crisis helplines:
> - **Tele-MANAS**: Call **14416** (National Mental Health Toll-Free)
> - **KIRAN**: Call **1800-599-0019** (Social Justice & Empowerment Toll-Free)
> - **National Emergency**: Call **112**

---

## 📄 License & Attribution

This project is licensed under the **MIT License** — see the [LICENSE](LICENSE) file for details.  
*Engineered with empathy for voice-first companion robotics and accessible mental health intelligence.*
