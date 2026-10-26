# 🌿 Arogya • Embodied Voice Companion & Acoustic Biomarker Mental Health AI

> **A real-time bilingual voice companion robot and longitudinal mental health intelligence platform featuring authentic Tanglish & English voice cloning, hands-free conversational VAD, non-contact mmWave vital radar sensing, and deterministic quote-grounded evidence scoring.**

---

## 🌟 Executive Overview

**Arogya** is designed to live in the user’s room as a physical, real-world presence that understands both emotional and physiological states — even before the user speaks. 

Existing solutions suffer from three fatal flaws:
1. **Linguistic Stigma:** Indian youth express their deepest emotions in colloquial vernaculars (**Tanglish** — Tamil naturally blended with English). Conventional chatbots reply in stiff, unnatural English.
2. **Neglect of Acoustic & Physical Biomarkers:** Depression, anxiety, and burnout manifest in pitch flattening ($f_0$ semitone variance), pause ratios, and rapid shallow breathing. Text chatbots cannot detect any of this.
3. **The "Silent Suffering" Barrier:** When individuals are severely overwhelmed, they lack the energy to type into a phone. Arogya's ambient companion robot senses presence and vital signs via **60GHz mmWave radar** and speaks with a human voice to de-escalate stress proactively.

---

## 🚀 Key Features

### 1. Dual-Channel Conversational Tamil & Tanglish Speech Naturalizer
- **Dual-Channel Generation Pipeline:** Decouples chat UI presentation from speech synthesis:
  - **Channel 1 (UI Display):** Clean, warm conversational Tanglish in Latin script (e.g. *"Romba tired-ah irukka bro? Konjam rest edunga, namma pesalaam."*).
  - **Channel 2 (TTS Speech):** Authentic spoken colloquial Tamil (*பேச்சுத் தமிழ்*) in Tamil script with preserved English loanwords (e.g. *"ரொம்ப tired-ஆ இருக்கா ப்ரோ? கொஞ்சம் rest எடுங்க... நம்ம பேசலாம்."*).
- **Zero Diglossia Artifacts:** Eliminates awkward textbook/Google-translated Tamil (*"நீங்கள் ஓய்வு எடுக்க வேண்டும்"*) in favor of natural conversational spoken phrases (*"கொஞ்சம் rest எடுங்க"*, *"என்ன ஆச்சு"*, *"நான் help பண்றேன்"*, *"சொல்லுங்க கேக்குறேன்"*).
- **Native High-Fidelity Tamil Voice (`ta-IN-PallaviNeural`):** Authentic human Indian Tamil intonation, prosody, and retroflex consonant articulation (`ழ`, `ற`, `ள`, `ண`) with sub-second latency (~0.35s - 0.45s) and 0 MB VRAM footprint.
- **Indian English Neural Voice (`en-IN-NeerjaNeural`):** Natural cadence for English dialogue with emotion-adaptive pacing and pitch inflection.
- **Cloned Studio Mode (F5-TTS Flow-Matching Diffusion):** Local GPU-accelerated zero-shot voice cloning running on NVIDIA RTX 3050 with phonetic Tanglish staging.

### 2. Hands-Free Ambient Conversational Mode (Full-Duplex VAD)
- Operates naturally like a friend in the room.
- Web Audio API energy detection senses when the user speaks and automatically submits upon a **1.4-second natural pause**.
- Plays Arogya's response and automatically resumes listening without requiring manual clicks.

### 3. Interactive Guided Calming Breathing (High-End Concentric Animation)
- Real-time somatic grounding engine with smooth, cubic-bezier pulsating concentric rings and **432Hz harmonic acoustic chimes**.
- Supports **Box Breathing (4-4-4-4)** and **Calming Vagus Stimulation (4-7-8)** with live phase countdowns.
- **Automatic Tension Trigger:** Gentle invitation pill automatically appears whenever speech evaluation detects stress or anxiety $\ge 2/3$.

### 4. Zero-Hallucination Evidence Scoring
- Evaluates 4 core symptom dimensions: *Stress & Pressure*, *Worry & Apprehension*, *Fatigue & Low Energy*, and *Emotional Heaviness*.
- **Strict Empirical Criteria:** Requires verbatim transcript quotes for every awarded point. **"No quote = No points"**.
- Overall wellness score (0–100) and statistical confidence are deterministically calculated in Python code.

### 5. Scientific DSP Acoustic Biomarkers
- Probabilistic YIN (`librosa.pyin`) fundamental frequency ($f_0$) tracking.
- Speaker-normalized, pitch-invariant semitone deviation:
  $$\text{semitones} = 12 \cdot \log_2\left(\frac{f_0}{\text{median}(f_0)}\right)$$
- Extraction is decoupled from the LLM prompt to prevent subjective hallucination.

### 6. Dedicated Separate Analytics & Trajectory Portal (`/analytics`)
- Standalone analytics dashboard displaying multi-session longitudinal wellness curves, trajectory delta ($\Delta = \text{recent} - \text{baseline}$), symptom distributions, and voice biomarker history.
- One-click export of structured clinical reflection reports in Markdown format.

### 7. Long-Term Clinical Profile & Stressor Memory
- Persistent SQLite memory (`user_clinical_profile`) tracking key user context (academics, placement interviews, sleep habits), recurring stressor clusters, and proven coping mechanisms.
- Arogya naturally references previous discussions across different days.

### 8. Embodied Hardware & Non-Contact mmWave Sensing Architecture
- Connects with **60GHz FMCW mmWave radar** (e.g., HLK-LD2410 / Seeed Studio mmWave) over ESP32 UART.
- Measures presence, respiratory rate (breaths/min), and heart-rate variability non-invasively through chest-wall micromotions without intrusive cameras or wearables.

### 9. Immediate Crisis Safety Triage
- Independent safety filter detecting acute crisis or self-harm ideation without corrupting numerical scores.
- Immediate direct integration with **Tele-MANAS (14416)**, **KIRAN (1800-599-0019)**, and **Vandrevala Foundation**.

### 10. Real Google OAuth 2.0 Authentication & User Isolation
- **100% Free Google Sign-In:** Leverages Google Identity Services (GSI) web SDK with zero third-party subscription fees or quotas.
- **Top-Left Corner Profile Flyout:** Clicking the authenticated user pill in the top-left corner opens a pop-like flyout card showing Google-verified badge, avatar, preferred name, and email.
- **Google Account Switcher:** Built-in "Switch Account" action triggers Google's native account chooser (`disableAutoSelect` + One Tap / Button prompt) to select from any Google accounts logged into the browser.
- **One-Time Preferred Name Onboarding:** New users are prompted once upon initial Google sign-in to enter their desired display name, which is personalized into Arogya's long-term conversational memory.
- **Strict User Privacy Isolation:** User reflections, sessions, voice prosody recordings, mental health metrics, and clinical memory profiles are securely partitioned by user ID in SQLite.

---

## 🛠️ System Architecture

```mermaid
graph TD
    A["User Spoken Speech (Tanglish / English)"] --> B["Microphone Input / Web Audio VAD"]
    B --> C["FFmpeg Normalization (16kHz Mono PCM WAV)"]
    C --> D["Speech-to-Text (Whisper GPU + Web Speech)"]
    C --> E["DSP Acoustic Extraction (pYIN Semitones, Pause Ratio)"]
    
    D --> F["Language & Register Detection (tanglish_engine.py)"]
    F --> G["Gemini 3.5 Flash Lite (temp=0.0)"]
    G --> H["Verbatim Quote Evidence Scoring (7 Dimensions)"]
    E --> I["Deterministic Python Wellness Fusion (0-100)"]
    H --> I
    
    I --> J["Conversational Tamil/Tanglish Naturalizer"]
    J --> K["Prosody & Phonetic Preparation"]
    K --> L["Intelligent TTS Router"]
    L --> M["Fast Native Tamil (ta-IN-PallaviNeural ~0.35s)"]
    L --> N["Fast Indian English (en-IN-NeerjaNeural ~0.4s)"]
    L --> O["Cloned GPU Studio (F5-TTS on RTX 3050 ~1.9s)"]
    M --> P["Browser Audio Playback & 60 FPS Visualizer"]
    N --> P
    O --> P
```

---

## 📦 Tech Stack

- **Backend:** Python 3.11, FastAPI, Uvicorn, SQLite3 (WAL mode)
- **AI Models & Pipeline:**
  - Google Gemini API (`gemini-3.5-flash-lite`, `google-genai` SDK)
  - Faster-Whisper (CTranslate2, CUDA FP16 on RTX 3050 GPU)
  - Conversational Tamil/Tanglish Naturalizer (`tanglish_engine.py`)
  - Edge-TTS (`ta-IN-PallaviNeural`, `en-IN-NeerjaNeural`)
  - F5-TTS (Flow-matching diffusion zero-shot voice cloning on RTX 3050 GPU)
- **Audio DSP:** Librosa (pYIN $f_0$), SoundFile, NumPy, FFmpeg
- **Frontend:** HTML5 Canvas, Vanilla CSS3 (Editorial Monochrome system), JavaScript (ES6+), Web Audio API (Strict $\le 60\text{ FPS}$ Cap), Service Worker PWA
- **Hardware Interface:** NVIDIA GeForce RTX 3050 6GB Laptop GPU (CUDA 13.0 / PyTorch cu121)

---

## ⚡ Quick Start Guide

### 1. Prerequisites
- Python 3.10 or 3.11
- NVIDIA GPU with CUDA 12.1+ (Recommended for F5-TTS; CPU works for Fast Neural mode)
- [FFmpeg](https://ffmpeg.org/download.html) installed and accessible in PATH or root directory

### 2. Clone and Setup
```bash
git clone https://github.com/logesh-profile/arogya.git
cd arogya

# Create and activate virtual environment
python -m venv venv
# Windows:
venv\Scripts\activate
# Linux/macOS:
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 3. Environment Variables
Create a `.env` file inside `mental_health_voice_ai/`:
```bash
GEMINI_API_KEY=your_gemini_api_key_here
GOOGLE_CLIENT_ID=69205169774-un0j1m41flrjvjm3ha6gvsg07f99nqu3.apps.googleusercontent.com
```

### 4. Launch Arogya
```bash
python mental_health_voice_ai/run_arogya.py
```
Open **`http://localhost:8000`** in Chrome or Edge.

---

## 📊 Key API Endpoints

| Endpoint | Method | Description |
| :--- | :--- | :--- |
| `/` | `GET` | Main companion conversational interface |
| `/analytics` | `GET` | Dedicated separate longitudinal analytics portal |
| `/api/auth/me` | `GET` | Active authenticated user profile and onboarding status |
| `/api/auth/google` | `POST` | Authenticate via Google OAuth 2.0 credential token |
| `/api/auth/update-name` | `POST` | 1-time display name onboarding for new accounts |
| `/api/auth/logout` | `POST` | Terminate session and clear authentication cookie |
| `/api/chat/voice` | `POST` | Core speech-to-speech loop with evidence scoring & prosody |
| `/api/chat/text` | `POST` | Rapid text chat with grounded evidence & titling |
| `/api/analytics/summary` | `GET` | Longitudinal multi-session metrics, trend points & profile |
| `/api/analytics/export/download` | `GET` | Download full clinical reflection report (Markdown) |
| `/api/greeting` | `GET` | Instant studio greeting personalized by memory |

---

## 🔒 Ethical AI & Clinical Scope Disclaimer
*Arogya is designed as an everyday emotional decompression companion, somatic grounding guide, and early-warning wellness triage aid. It is not a licensed medical device and does not diagnose psychiatric conditions or replace a human clinical psychologist. In cases of acute crisis, immediate referral to national toll-free helplines (Tele-MANAS: 14416) is automatically presented.*

---

## 📄 License
MIT License. Developed for mental health accessibility and voice-first companion robotics.
