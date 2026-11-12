// ==========================================================================
// AROGYA • EDITORIAL MONOCHROME COMPANION CLIENT
// Black & White Theme • Light & Dark Mode
// Typography Matrix:
// - Arogya Captions: Newsreader (300 Large & Light, Warm Human Voice)
// - Spoken Words: Newsreader Italic (400 Quieter Subline)
// - Controls & Lists: Plus Jakarta Sans
// - Precision Metrics: Space Grotesk Tabular Figures
// ==========================================================================

let currentSessionId = null;
let voiceMode = "fast"; // Default to instant Fast Neural for ChatGPT speed (~0.4s)
let isRecording = false;
let mediaRecorder = null;
let audioChunks = [];
let audioContext = null;
let analyser = null;
let animFrameId = null;
let animTimeoutId = null;
let visualizerRunning = false;
let activeVisualizerSource = null;
let lastFrameTimestamp = 0;
const TARGET_FRAME_MS = 1000 / 30; // 33.33ms strictly hardware-capped 30 FPS

let lastRecordedBlob = null;
let speechRecognizer = null;
let recognizedTranscript = "";

function stopVisualizerLoop() {
    visualizerRunning = false;
    if (animFrameId) {
        cancelAnimationFrame(animFrameId);
        animFrameId = null;
    }
    if (animTimeoutId) {
        clearTimeout(animTimeoutId);
        animTimeoutId = null;
    }
    if (activeVisualizerSource) {
        try { activeVisualizerSource.disconnect(); } catch(e){}
        activeVisualizerSource = null;
    }
}

// DOM Elements
const sessionsList = document.getElementById("sessionsList");
const sessionCountTag = document.getElementById("sessionCountTag");
const newSessionBtn = document.getElementById("newSessionBtn");

const currentSessionTitle = document.getElementById("currentSessionTitle");
const editSessionTitleBtn = document.getElementById("editSessionTitleBtn");
const liveStatusPill = document.getElementById("liveStatusPill");
const liveStatusText = document.getElementById("liveStatusText");
const themeToggleBtn = document.getElementById("themeToggleBtn");
const themeLabel = document.getElementById("themeLabel");

// On-demand Insights Drawer
const toggleInsightsBtn = document.getElementById("toggleInsightsBtn");
const insightsDrawer = document.getElementById("insightsDrawer");
const closeInsightsBtn = document.getElementById("closeInsightsBtn");
const downloadReportBtn = document.getElementById("downloadReportBtn");

const orbCaption = document.getElementById("orbCaption");
const waveformCanvas = document.getElementById("waveformCanvas");
const canvasCtx = waveformCanvas ? waveformCanvas.getContext("2d") : null;

const chatStream = document.getElementById("chatStream");
const micBtn = document.getElementById("micBtn");
const textInput = document.getElementById("textInput");
const sendBtn = document.getElementById("sendBtn");
const audioPlayer = document.getElementById("audioPlayer");
const speakerToggleBtn = document.getElementById("speakerToggleBtn");
const micDeviceSelect = document.getElementById("micDeviceSelect");
const micMeterFill = document.getElementById("micMeterFill");
const micMeterStatus = document.getElementById("micMeterStatus");

// Scorecard & Telemetry in Drawer
const wellnessScoreNum = document.getElementById("wellnessScoreNum");
const wellnessBadge = document.getElementById("wellnessBadge");
const confidenceBadge = document.getElementById("confidenceBadge");
const scoreCircle = document.getElementById("scoreCircle");
const dominantEmotion = document.getElementById("dominantEmotion");
const evidenceReasonsList = document.getElementById("evidenceReasonsList");
const semitoneVal = document.getElementById("semitoneVal");
const prosodyNote = document.getElementById("prosodyNote");

// Crisis Modal Elements
const crisisModal = document.getElementById("crisisModal");
const closeCrisisBtn = document.getElementById("closeCrisisBtn");
const crisisHelplineGrid = document.getElementById("crisisHelplineGrid");

// Phase 2: Hands-Free, VAD Turn-Taking & Grounding State
let isHandsFree = false;
let vadSilenceTimer = null;
let vadHasSpoken = false;
let speechDetectedInCurrentTurn = false;
let vadNoiseFloor = 8.0;
let vadFrameCount = 0;
let vadConsecutiveSpeechFrames = 0;
let bargeInFrameCount = 0;
let isTurnProcessing = false;
let lastSpeechActivityTimestamp = 0;
let lastFinalSpeechTimestamp = 0;
let autoSubmitTriggered = false;
let breathingInterval = null;
let breathingMode = "box";
let breathingCycle = 1;
let isBreathingPaused = false;

// ChatGPT-Style Continuous Voice Dialogue & Spectacular Visualizer State
let isVoiceModalActive = false;
let voiceToneCentroid = 200;
let currentAiReplyText = "";
let currentSpeakingFace = "happy";
let initialSilenceTimer = null;
let isProactiveOpenerPlaying = false;
let currentBufferSource = null;
let isAiAudioPlaying = false;
let currentTurnAbortController = null;
let isMicMuted = false;
let bargeInConsecutiveFrames = 0;
let activeMicStream = null;
let activeVoiceUserBubble = null;

// Persistent hardware mic stream management (Full-Duplex ChatGPT Architecture)
async function getOrCreateMicStream(forceRefresh = false) {
    if (!forceRefresh && activeMicStream && activeMicStream.active && activeMicStream.getAudioTracks().some(t => t.readyState === "live")) {
        return activeMicStream;
    }
    if (activeMicStream) {
        try {
            activeMicStream.getTracks().forEach(t => t.stop());
        } catch(e){}
        activeMicStream = null;
    }

    const selectedMicId = micDeviceSelect ? micDeviceSelect.value : "";
    const audioConstraints = {
        channelCount: 1,
        sampleRate: { ideal: 16000 },
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true
    };
    if (selectedMicId) {
        audioConstraints.deviceId = { ideal: selectedMicId };
    }

    try {
        activeMicStream = await navigator.mediaDevices.getUserMedia({ audio: audioConstraints });
    } catch (err) {
        console.warn("[*] Headset ideal constraint fallback to default audio:", err);
        activeMicStream = await navigator.mediaDevices.getUserMedia({ audio: true });
    }

    // Attach to visualizer to keep audio analysis warm
    startVisualizer(activeMicStream);
    return activeMicStream;
}

function releaseMicStream() {
    if (activeMicStream) {
        try {
            activeMicStream.getTracks().forEach(t => t.stop());
        } catch(e){}
        activeMicStream = null;
    }
    stopVisualizerLoop();
}

// ChatGPT Voice Mode Stream Helpers (Screenshots 2 & 3)
function appendVoiceBubbleUser(text) {
    const stream = document.getElementById("voiceChatStream");
    if (!stream || !text) return null;
    const bubble = document.createElement("div");
    bubble.className = "voice-bubble-user";
    bubble.textContent = text;
    stream.appendChild(bubble);
    stream.scrollTop = stream.scrollHeight;
    return bubble;
}

function appendVoiceBubbleAi(text) {
    const stream = document.getElementById("voiceChatStream");
    if (!stream || !text) return null;
    const bubble = document.createElement("div");
    bubble.className = "voice-bubble-ai";
    bubble.textContent = text;
    stream.appendChild(bubble);
    stream.scrollTop = stream.scrollHeight;
    return bubble;
}

function populateVoiceStreamFromHistory() {
    const stream = document.getElementById("voiceChatStream");
    if (!stream) return;
    stream.innerHTML = "";

    const existingCards = document.querySelectorAll("#chatMessages .message-card");
    if (existingCards && existingCards.length > 0) {
        existingCards.forEach(card => {
            const userTextEl = card.querySelector(".user-speech-bubble, .message-bubble.user, .user-bubble, .message-user-text");
            const aiTextEl = card.querySelector(".ai-reply-text, .message-bubble.ai, .ai-bubble, .message-ai-text");
            if (userTextEl && userTextEl.textContent.trim()) {
                appendVoiceBubbleUser(userTextEl.textContent.trim());
            }
            if (aiTextEl && aiTextEl.textContent.trim()) {
                appendVoiceBubbleAi(aiTextEl.textContent.trim());
            }
        });
    }

    if (stream.children.length === 0) {
        const welcome = document.createElement("div");
        welcome.className = "voice-bubble-ai";
        welcome.style.opacity = "0.75";
        welcome.textContent = "Hey, I'm Arogya. Feel free to talk to me about anything on your mind, I'm here and listening.";
        stream.appendChild(welcome);
    }
    stream.scrollTop = stream.scrollHeight;
}

// Web companion activity state stubs
function notifyEsp32SpeechState(state, face = null) {}
function notifyEsp32Emotion(face) {}

// Auth State Variables & API Helper
let currentUser = null;
let googleClientId = "";
let isGoogleConfigured = false;

function apiFetch(url, options = {}) {
    if (!options.headers) {
        options.headers = {};
    }
    options.credentials = "include";
    const token = localStorage.getItem("arogya_session_token");
    if (token && !options.headers["Authorization"]) {
        if (options.headers instanceof Headers) {
            options.headers.set("Authorization", `Bearer ${token}`);
        } else {
            options.headers["Authorization"] = `Bearer ${token}`;
        }
    }
    return fetch(url, options);
}

// --- INITIALIZATION ---
document.addEventListener("DOMContentLoaded", async () => {
    initTheme();
    initVoiceEngine();
    initControls();
    initPhase2Controls();
    initVoiceModeControls();
    initHeaderDropdownMenu();
    initCanvasVisualizer();
    setupAudioPlayerEvents();
    await initMicDeviceSelector();
    await initAuth();

    // Requirement 1: New user enters -> sign up or login page first!
    if (!currentUser) {
        window.location.replace("/login");
        return;
    }

    updateAuthUI(true, currentUser);
    await initVoiceSelector();

    // Always restore the user's active conversation on page reload (never erase chats!)
    const sessions = await loadSessions();
    if (sessions && sessions.length > 0) {
        const savedSessionId = localStorage.getItem("arogya_active_session_id");
        const sessionToLoad = (savedSessionId && sessions.some(s => s.session_id === savedSessionId))
            ? savedSessionId
            : sessions[0].session_id;
        currentSessionId = sessionToLoad;
        localStorage.setItem("arogya_active_session_id", sessionToLoad);
        await loadSessionData(sessionToLoad);
    } else {
        await startNewSession(true);
    }
});

// ==========================================================================
// PRODUCTION GOOGLE OAUTH 2.0 & MULTI-USER DATA ISOLATION CONTROLLER
// ==========================================================
async function initAuth() {
    try {
        // Fast instant restore from localStorage to eliminate UI flicker / reload logouts
        const cachedUser = localStorage.getItem("arogya_active_user");
        if (cachedUser) {
            try {
                currentUser = JSON.parse(cachedUser);
                updateAuthUI(true, currentUser);
            } catch (e) {}
        }

        // 1. Fetch server auth configuration (live Google Client ID)
        const cfgRes = await apiFetch("/api/auth/config");
        if (cfgRes.ok) {
            const cfg = await cfgRes.json();
            googleClientId = cfg.client_id || "";
            isGoogleConfigured = cfg.is_configured || false;
        }

        // 2. Fetch active session state from backend
        try {
            const meRes = await apiFetch("/api/auth/me");
            if (meRes.ok) {
                const meData = await meRes.json();
                if (meData.authenticated && meData.user) {
                    currentUser = meData.user;
                    localStorage.setItem("arogya_active_user", JSON.stringify(meData.user));
                    updateAuthUI(true, meData.user);
                    if (meData.needs_onboarding) {
                        openOnboardingModal(meData.user);
                    }
                } else if (!currentUser) {
                    updateAuthUI(false, null);
                }
            } else if (!currentUser) {
                updateAuthUI(false, null);
            }
        } catch (authErr) {
            console.warn("Auth initialization notice (keeping local session):", authErr);
        }

        // 3. Setup Google Identity Services (GSI)
        setupGoogleIdentity();

        // 4. Bind auth UI events
        setupAuthEvents();
    } catch (e) {
        console.warn("Auth initialization notice:", e);
    }
}

function updateAuthUI(isAuthenticated, user) {
    const cornerSignInBtn = document.getElementById("authSignInBtn");
    const cornerPillWrap = document.getElementById("userProfileDropdown");
    const cornerUserName = document.getElementById("userNameLabel");
    const cornerAvatarImg = document.getElementById("userAvatarImg");
    const cornerAvatarFallback = document.getElementById("userAvatarFallback");

    const popupUserName = document.getElementById("popupUserName");
    const popupUserEmail = document.getElementById("popupUserEmail");
    const popupUserAvatar = document.getElementById("popupUserAvatar");
    const popupUserAvatarFallback = document.getElementById("popupUserAvatarFallback");

    const sidebarUserName = document.getElementById("sidebarUserName");
    const sidebarUserAvatar = document.getElementById("sidebarUserAvatar");
    const sidebarUserEmail = document.getElementById("sidebarUserEmail");

    if (isAuthenticated && user) {
        document.body.classList.add("user-authenticated");
        const displayName = user.display_name || user.preferred_name || user.given_name || user.name || "User";
        const email = user.email || "";
        const picture = user.picture || "";
        const initial = displayName ? displayName[0].toUpperCase() : "U";

        // Top-left corner pill
        if (cornerSignInBtn) {
            cornerSignInBtn.classList.add("hidden");
            cornerSignInBtn.style.display = "none";
        }
        if (cornerPillWrap) {
            cornerPillWrap.classList.remove("hidden");
            cornerPillWrap.style.display = "inline-flex";
        }
        if (cornerUserName) cornerUserName.textContent = displayName;

        // Avatar handling: strictly ONE avatar (image or fallback, NEVER stacked)
        if (picture) {
            if (cornerAvatarImg) {
                cornerAvatarImg.src = picture;
                cornerAvatarImg.style.display = "block";
                cornerAvatarImg.classList.remove("hidden");
                cornerAvatarImg.onerror = () => {
                    cornerAvatarImg.style.display = "none";
                    if (cornerAvatarFallback) {
                        cornerAvatarFallback.textContent = initial;
                        cornerAvatarFallback.style.display = "inline-flex";
                    }
                };
            }
            if (cornerAvatarFallback) {
                cornerAvatarFallback.style.display = "none";
            }

            if (popupUserAvatar) {
                popupUserAvatar.src = picture;
                popupUserAvatar.style.display = "block";
                popupUserAvatar.classList.remove("hidden");
                popupUserAvatar.onerror = () => {
                    popupUserAvatar.style.display = "none";
                    if (popupUserAvatarFallback) {
                        popupUserAvatarFallback.textContent = initial;
                        popupUserAvatarFallback.style.display = "flex";
                    }
                };
            }
            if (popupUserAvatarFallback) {
                popupUserAvatarFallback.style.display = "none";
            }
        } else {
            if (cornerAvatarImg) {
                cornerAvatarImg.style.display = "none";
            }
            if (cornerAvatarFallback) {
                cornerAvatarFallback.textContent = initial;
                cornerAvatarFallback.style.display = "inline-flex";
            }

            if (popupUserAvatar) {
                popupUserAvatar.style.display = "none";
            }
            if (popupUserAvatarFallback) {
                popupUserAvatarFallback.textContent = initial;
                popupUserAvatarFallback.style.display = "flex";
            }
        }

        // Top-left popup card
        if (popupUserName) popupUserName.textContent = displayName;
        if (popupUserEmail) popupUserEmail.textContent = email;

        // Sidebar card
        if (sidebarUserName) sidebarUserName.textContent = displayName;
        if (sidebarUserAvatar) {
            if (user && user.picture) {
                sidebarUserAvatar.innerHTML = `<img src="${escapeHtml(user.picture)}" alt="${escapeHtml(displayName)}" class="sidebar-avatar-img" referrerpolicy="no-referrer" />`;
            } else {
                sidebarUserAvatar.innerHTML = `<span class="sidebar-avatar-initial">${escapeHtml(initial)}</span>`;
            }
        }
        if (sidebarUserEmail) sidebarUserEmail.textContent = email ? email : "Active Private Space";

        // Welcome Hero Card
        const welcomeGreeting = document.getElementById("welcomeUserGreeting");
        if (welcomeGreeting) {
            welcomeGreeting.textContent = `Welcome back, ${displayName}`;
        }
    } else {
        document.body.classList.remove("user-authenticated");
        if (cornerSignInBtn) {
            cornerSignInBtn.classList.remove("hidden");
            cornerSignInBtn.style.display = "inline-flex";
        }
        if (cornerPillWrap) {
            cornerPillWrap.classList.add("hidden");
            cornerPillWrap.style.display = "none";
        }
        if (sidebarUserName) sidebarUserName.textContent = "Guest Space";
        if (sidebarUserAvatar) sidebarUserAvatar.innerHTML = `<span class="sidebar-avatar-initial">G</span>`;
        if (sidebarUserEmail) sidebarUserEmail.textContent = "Sign in to save chats";
    }
}

function setupGoogleIdentity() {
    const gsiContainer = document.getElementById("gsiButtonContainer");

    if (isGoogleConfigured && googleClientId && window.google && google.accounts) {
        try {
            google.accounts.id.initialize({
                client_id: googleClientId,
                callback: handleGoogleCredentialResponse,
                auto_select: false,
                cancel_on_tap_outside: false
            });

            if (gsiContainer) {
                gsiContainer.innerHTML = "";
                google.accounts.id.renderButton(gsiContainer, {
                    theme: "outline",
                    size: "large",
                    type: "standard",
                    shape: "pill",
                    width: 280,
                    text: "signin_with",
                    logo_alignment: "left"
                });
            }

            // Trigger Google 1-Tap prompt if user is not signed in
            if (!currentUser) {
                google.accounts.id.prompt();
            }
        } catch (err) {
            console.warn("Google Identity initialization notice:", err);
        }
    }
}

async function handleGoogleCredentialResponse(response) {
    if (!response || !response.credential) return;
    try {
        const res = await apiFetch("/api/auth/google", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ credential: response.credential })
        });
        if (!res.ok) {
            const err = await res.json();
            alert("Google Sign-In notice: " + (err.detail || "Authentication error"));
            return;
        }
        const data = await res.json();
        currentUser = data.user;
        if (data.session_token) {
            localStorage.setItem("arogya_session_token", data.session_token);
        }
        if (data.user) {
            localStorage.setItem("arogya_active_user", JSON.stringify(data.user));
        }
        updateAuthUI(true, data.user);
        closeLoginGate();

        if (data.needs_onboarding) {
            // First time user: open 1-time name setup
            openOnboardingModal(data.user);
        } else {
            // Returning user: immediately load previously saved chats
            const sessions = await loadSessions();
            if (sessions && sessions.length > 0) {
                currentSessionId = sessions[0].session_id;
                await loadSessionData(sessions[0].session_id);
            } else {
                await startNewSession(true);
            }
        }
    } catch (e) {
        console.error("Google sign-in error:", e);
    }
}

function openLoginGate(canClose = false) {
    const modal = document.getElementById("loginGateModal");
    const closeBtn = document.getElementById("closeLoginGateBtn");
    if (modal) {
        modal.classList.remove("hidden");
        if (closeBtn) {
            if (canClose) {
                closeBtn.classList.remove("hidden");
            } else {
                closeBtn.classList.add("hidden");
            }
        }
        setupGoogleIdentity();
    }
}

function closeLoginGate() {
    const modal = document.getElementById("loginGateModal");
    if (modal) modal.classList.add("hidden");
}

function openOnboardingModal(user) {
    const modal = document.getElementById("onboardingNameModal");
    const avatarImg = document.getElementById("onboardingUserAvatar");
    const nameInput = document.getElementById("onboardingNameInput");

    if (modal) {
        modal.classList.remove("hidden");
        if (avatarImg && user && user.picture) {
            avatarImg.src = user.picture;
            avatarImg.classList.remove("hidden");
        }
        if (nameInput) {
            nameInput.value = (user && (user.preferred_name || user.given_name || user.name)) || "";
            setTimeout(() => nameInput.focus(), 150);
        }
    }
}

function closeOnboardingModal() {
    const modal = document.getElementById("onboardingNameModal");
    if (modal) modal.classList.add("hidden");
}

async function handleOnboardingSubmit(e) {
    if (e) e.preventDefault();
    const nameInput = document.getElementById("onboardingNameInput");
    if (!nameInput) return;
    const preferredName = nameInput.value.trim();
    if (!preferredName) {
        alert("Please enter a name so Arogya can address you personally.");
        return;
    }

    try {
        const res = await apiFetch("/api/auth/update-name", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ preferred_name: preferredName })
        });
        if (res.ok) {
            const data = await res.json();
            currentUser = data.user;
            localStorage.setItem("arogya_active_user", JSON.stringify(data.user));
            updateAuthUI(true, data.user);
            closeOnboardingModal();
            const sessions = await loadSessions();
            if (sessions && sessions.length > 0) {
                currentSessionId = sessions[0].session_id;
                await loadSessionData(sessions[0].session_id);
            } else {
                await startNewSession(true);
            }
        } else {
            const err = await res.json();
            alert("Update name notice: " + (err.detail || "Could not save name"));
        }
    } catch (err) {
        console.error("Onboarding submission error:", err);
    }
}

function setupAuthEvents() {
    const cornerSignInBtn = document.getElementById("authSignInBtn");
    const userProfileBtn = document.getElementById("userProfileBtn");
    const userProfilePopup = document.getElementById("userProfilePopup");
    const switchAccountBtn = document.getElementById("switchAccountBtn");
    const signOutBtn = document.getElementById("signOutBtn");
    const closeLoginGateBtn = document.getElementById("closeLoginGateBtn");
    const sidebarAuthBtn = document.getElementById("sidebarAuthBtn");
    const onboardingForm = document.getElementById("onboardingNameForm");

    // Top-left sign in button -> open dedicated sliding login page
    if (cornerSignInBtn) {
        cornerSignInBtn.addEventListener("click", () => {
            window.location.href = "/login";
        });
    }

    // Top-left user pill click -> toggle pop-like window
    if (userProfileBtn && userProfilePopup) {
        userProfileBtn.addEventListener("click", (e) => {
            e.stopPropagation();
            userProfilePopup.classList.toggle("hidden");
            userProfileBtn.classList.toggle("active", !userProfilePopup.classList.contains("hidden"));
        });

        // Close pop-like window when clicking outside
        document.addEventListener("click", (e) => {
            if (!userProfilePopup.contains(e.target) && !userProfileBtn.contains(e.target)) {
                userProfilePopup.classList.add("hidden");
                userProfileBtn.classList.remove("active");
            }
        });
    }

    // Switch Account button in pop-like window -> go to /login?action=switch
    if (switchAccountBtn) {
        switchAccountBtn.addEventListener("click", () => {
            if (userProfilePopup) userProfilePopup.classList.add("hidden");
            if (userProfileBtn) userProfileBtn.classList.remove("active");
            window.location.href = "/login?action=switch";
        });
    }

    // Sign Out button in pop-like window
    if (signOutBtn) {
        signOutBtn.addEventListener("click", async () => {
            if (userProfilePopup) userProfilePopup.classList.add("hidden");
            if (userProfileBtn) userProfileBtn.classList.remove("active");

            try {
                await apiFetch("/api/auth/logout", { method: "POST" });
                if (window.google?.accounts?.id?.disableAutoSelect) {
                    window.google.accounts.id.disableAutoSelect();
                }
                currentUser = null;
                localStorage.removeItem("arogya_active_user");
                localStorage.removeItem("arogya_session_token");
                localStorage.removeItem("arogya_active_session_id");
                updateAuthUI(false, null);
                window.location.href = "/login";
            } catch (e) {
                console.warn("Logout notice:", e);
                localStorage.removeItem("arogya_active_user");
                localStorage.removeItem("arogya_session_token");
                localStorage.removeItem("arogya_active_session_id");
                window.location.href = "/login";
            }
        });
    }

    // Sidebar user card & auth button
    const sidebarUserCard = document.getElementById("sidebarUserCard");
    const handleSidebarAuthClick = (e) => {
        e.stopPropagation();
        if (currentUser) {
            if (userProfilePopup) {
                userProfilePopup.classList.toggle("hidden");
                if (userProfileBtn) userProfileBtn.classList.toggle("active", !userProfilePopup.classList.contains("hidden"));
            }
        } else {
            window.location.href = "/login";
        }
    };
    if (sidebarAuthBtn) {
        sidebarAuthBtn.addEventListener("click", handleSidebarAuthClick);
    }
    if (sidebarUserCard) {
        sidebarUserCard.addEventListener("click", (e) => {
            if (e.target.closest("#sidebarAuthBtn")) return; // handled by button
            handleSidebarAuthClick(e);
        });
    }

    // Close button on login gate (only available during Switch Account)
    if (closeLoginGateBtn) {
        closeLoginGateBtn.addEventListener("click", closeLoginGate);
    }

    // 1-Time Onboarding Form Submit
    if (onboardingForm) {
        onboardingForm.addEventListener("submit", handleOnboardingSubmit);
    }
}

// --- THEME ENGINE (BLACK & WHITE: LIGHT / DARK) ---
function initTheme() {
    const savedTheme = localStorage.getItem("arogya_theme") || "dark";
    setTheme(savedTheme);

    if (themeToggleBtn) {
        themeToggleBtn.addEventListener("click", () => {
            const current = document.documentElement.getAttribute("data-theme") || "dark";
            const next = current === "dark" ? "light" : "dark";
            setTheme(next);
        });
    }
}

function setTheme(theme) {
    document.documentElement.setAttribute("data-theme", theme);
    localStorage.setItem("arogya_theme", theme);
    if (themeLabel) {
        themeLabel.textContent = theme === "dark" ? "Dark" : "Light";
    }
    drawIdleWaveform();
}

// --- VOICE ENGINE SWITCHER (SPEED CONTROL) ---
function initVoiceEngine() {
    voiceMode = "fast";
    setVoiceMode("fast");
}

function setVoiceMode(mode) {
    voiceMode = "fast";
    localStorage.setItem("arogya_voice_mode", "fast");

    const badge = document.getElementById("currentEngineBadge");
    if (badge) badge.textContent = "INSTANT (~0.4s)";
}

// ==========================================================================
// CHATGPT-STYLE VOICE SELECTOR CONTROLLER
// ==========================================================================
const DEFAULT_FALLBACK_VOICES = [
    {
        id: "en-IN-NeerjaExpressiveNeural",
        name: "Neerja",
        label: "Neerja (Expressive Indian English)",
        gender: "Female",
        accent: "Expressive Indian English",
        description: "Warm, authentic Indian English companion with emotional empathy & conversational cadence",
        sample_text: "Namaste! Don't worry bro, I am right here with you. Take a gentle breath and speak freely.",
        default: true
    },
    {
        id: "en-US-AvaMultilingualNeural",
        name: "Ava",
        label: "Ava (Human Conversational)",
        gender: "Female",
        accent: "Natural Human Voice",
        description: "Ultra-realistic, warm, human conversational voice with fluid intonation",
        sample_text: "Hello! I am your Arogya companion. I'm right here with you to listen and reflect.",
        default: false
    },
    {
        id: "en-IN-PrabhatNeural",
        name: "Prabhat",
        label: "Prabhat (Indian English Male)",
        gender: "Male",
        accent: "Indian English Male",
        description: "Calm, reassuring human presence with steady Indian conversational cadence",
        sample_text: "Take your time. I am listening to everything you wish to share with me.",
        default: false
    },
    {
        id: "en-US-AndrewMultilingualNeural",
        name: "Andrew",
        label: "Andrew (Conversational Male)",
        gender: "Male",
        accent: "Conversational Male",
        description: "Deep, warm, and comforting human conversational tone",
        sample_text: "Take a gentle breath. I am right here whenever you want to share what is on your mind.",
        default: false
    },
    {
        id: "en-US-EmmaMultilingualNeural",
        name: "Emma",
        label: "Emma (Empathetic Female)",
        gender: "Female",
        accent: "Warm & Gentle",
        description: "Compassionate, gentle, and mindful human presence",
        sample_text: "You can speak freely here without any judgment. How are you feeling right now?",
        default: false
    },
    {
        id: "en-US-BrianMultilingualNeural",
        name: "Brian",
        label: "Brian (Thoughtful Male)",
        gender: "Male",
        accent: "Calm & Grounded",
        description: "Thoughtful, steady, and supportive human male companion",
        sample_text: "I am here with you. Let's take things one step at a time.",
        default: false
    },
    {
        id: "ta-IN-PallaviNeural",
        name: "Pallavi",
        label: "Pallavi (Regional Tamil)",
        gender: "Female",
        accent: "Regional Tamil",
        description: "Authentic regional Tamil voice for pure Tamil conversations",
        sample_text: "வணக்கம், உங்க கூட பேசுறதுல எனக்கு ரொம்ப சந்தோஷம்.",
        default: false
    }
];

let selectedVoice = localStorage.getItem("arogya_selected_voice") || "en-IN-NeerjaExpressiveNeural";
if (selectedVoice === "en-IN-NeerjaNeural") {
    selectedVoice = "en-IN-NeerjaExpressiveNeural";
    localStorage.setItem("arogya_selected_voice", selectedVoice);
}
let availableVoices = [...DEFAULT_FALLBACK_VOICES];
let previewAudio = null;

async function initVoiceSelector() {
    const openBtn = document.getElementById("openVoiceSelectorBtn");
    const closeBtn = document.getElementById("closeVoiceSelectorBtn");
    const backdrop = document.getElementById("voiceSelectorBackdrop");
    const modal = document.getElementById("voiceSelectorModal");
    const confirmBtn = document.getElementById("confirmVoiceBtn");
    const headerLabel = document.getElementById("headerVoiceLabel");
    const listContainer = document.getElementById("voiceSelectorList");

    const sidebarVoiceBtn = document.getElementById("sidebarVoiceSelectorBtn");
    const sidebarVoiceLabel = document.getElementById("sidebarVoiceLabel");

    previewAudio = document.getElementById("previewAudioPlayer") || new Audio();

    function updateVoiceLabels() {
        const currVoiceObj = availableVoices.find(v => v.id === selectedVoice) || availableVoices[0];
        if (headerLabel && currVoiceObj) {
            headerLabel.textContent = `Voice: ${currVoiceObj.name}`;
        }
        const menuVoiceLabel = document.getElementById("menuCurrentVoiceLabel");
        if (menuVoiceLabel && currVoiceObj) {
            menuVoiceLabel.textContent = `Voice: ${currVoiceObj.label || currVoiceObj.name}`;
        }
        if (sidebarVoiceLabel && currVoiceObj) {
            sidebarVoiceLabel.textContent = `Voice: ${currVoiceObj.name}`;
        }
    }

    function renderVoiceList() {
        if (!listContainer) return;
        listContainer.innerHTML = "";

        availableVoices.forEach(v => {
            const isSelected = v.id === selectedVoice;
            const card = document.createElement("div");
            card.className = `voice-option-card ${isSelected ? "selected" : ""}`;
            card.setAttribute("data-voice-id", v.id);

            const initial = v.name.charAt(0).toUpperCase();

            card.innerHTML = `
                <div class="voice-option-info">
                    <div class="voice-avatar-badge">${initial}</div>
                    <div class="voice-option-text">
                        <div class="voice-name-row">
                            <span class="voice-name">${escapeHtml(v.label || v.name)}</span>
                            <span class="voice-tag">${escapeHtml(v.accent)}</span>
                        </div>
                        <span class="voice-desc">${escapeHtml(v.description)}</span>
                    </div>
                </div>
                <div class="voice-option-actions">
                    <button type="button" class="btn-voice-preview" title="Play voice sample" data-voice-id="${v.id}">
                        <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor">
                            <polygon points="5 3 19 12 5 21 5 3"/>
                        </svg>
                    </button>
                    <div class="voice-radio-check"></div>
                </div>
            `;

            // Selection
            card.onclick = (e) => {
                if (e.target.closest(".btn-voice-preview")) return;
                selectVoice(v.id);
            };

            // Preview Play button
            const playBtn = card.querySelector(".btn-voice-preview");
            playBtn.onclick = (e) => {
                e.stopPropagation();
                playVoicePreview(v.id, playBtn);
            };

            listContainer.appendChild(card);
        });
    }

    function selectVoice(voiceId) {
        selectedVoice = voiceId;
        localStorage.setItem("arogya_selected_voice", voiceId);
        updateVoiceLabels();
        renderVoiceList();
        if (typeof sendVoiceConfigToWs === "function") {
            sendVoiceConfigToWs();
        }
    }

    async function playVoicePreview(voiceId, buttonEl) {
        if (!previewAudio) return;

        // If this button is already playing, stop
        if (!previewAudio.paused && buttonEl.classList.contains("playing")) {
            previewAudio.pause();
            previewAudio.currentTime = 0;
            buttonEl.classList.remove("playing");
            buttonEl.innerHTML = `<svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor"><polygon points="5 3 19 12 5 21 5 3"/></svg>`;
            return;
        }

        // Reset any other playing buttons
        document.querySelectorAll(".btn-voice-preview.playing").forEach(btn => {
            btn.classList.remove("playing");
            btn.innerHTML = `<svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor"><polygon points="5 3 19 12 5 21 5 3"/></svg>`;
        });

        buttonEl.innerHTML = `<span style="font-size:10px;">...</span>`;

        try {
            const res = await apiFetch(`/api/voice/preview?voice=${encodeURIComponent(voiceId)}`);
            if (!res.ok) throw new Error("Preview fetch failed");
            const data = await res.json();
            if (data.audio_url) {
                previewAudio.src = data.audio_url;
                await previewAudio.play();
                buttonEl.classList.add("playing");
                buttonEl.innerHTML = `<svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor"><rect x="6" y="4" width="4" height="16"/><rect x="14" y="4" width="4" height="16"/></svg>`;

                previewAudio.onended = () => {
                    buttonEl.classList.remove("playing");
                    buttonEl.innerHTML = `<svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor"><polygon points="5 3 19 12 5 21 5 3"/></svg>`;
                };
            }
        } catch (err) {
            console.warn("Preview error:", err);
            buttonEl.classList.remove("playing");
            buttonEl.innerHTML = `<svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor"><polygon points="5 3 19 12 5 21 5 3"/></svg>`;
        }
    }

    function openModal() {
        if (!modal) return;
        renderVoiceList();
        modal.classList.remove("hidden");
    }

    function closeModal() {
        if (!modal) return;
        modal.classList.add("hidden");
        if (previewAudio && !previewAudio.paused) {
            previewAudio.pause();
            previewAudio.currentTime = 0;
        }
        document.querySelectorAll(".btn-voice-preview.playing").forEach(btn => {
            btn.classList.remove("playing");
            btn.innerHTML = `<svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor"><polygon points="5 3 19 12 5 21 5 3"/></svg>`;
        });
    }

    // Expose globally so dropdown menu and sidebar can both invoke it
    window.openVoiceSelectorModal = openModal;
    window.closeVoiceSelectorModal = closeModal;

    // Pre-render immediately on load
    updateVoiceLabels();
    renderVoiceList();

    // Fetch voice list from backend to merge latest updates
    try {
        const res = await apiFetch("/api/voices");
        if (res.ok) {
            const data = await res.json();
            if (Array.isArray(data.voices) && data.voices.length > 0) {
                availableVoices = data.voices;
            }
            if (!availableVoices.some(v => v.id === selectedVoice)) {
                selectedVoice = data.default_voice || "en-IN-NeerjaExpressiveNeural";
                localStorage.setItem("arogya_selected_voice", selectedVoice);
            }
            updateVoiceLabels();
            renderVoiceList();
        }
    } catch (e) {
        console.warn("Voices fetch notice:", e);
    }

    if (openBtn) openBtn.addEventListener("click", openModal);
    if (sidebarVoiceBtn) sidebarVoiceBtn.addEventListener("click", openModal);
    if (closeBtn) closeBtn.addEventListener("click", closeModal);
    if (backdrop) backdrop.addEventListener("click", closeModal);
    if (confirmBtn) confirmBtn.addEventListener("click", closeModal);
}

// --- CONTROLS SETUP ---
function initControls() {
    if (newSessionBtn) {
        newSessionBtn.addEventListener("click", () => startNewSession(true));
    }

    if (editSessionTitleBtn) {
        editSessionTitleBtn.addEventListener("click", promptRenameCurrentSession);
    }

    if (closeCrisisBtn) {
        closeCrisisBtn.addEventListener("click", () => {
            crisisModal.classList.add("hidden");
        });
    }

    // Insights Drawer Toggle
    if (toggleInsightsBtn) {
        toggleInsightsBtn.addEventListener("click", () => {
            if (insightsDrawer) insightsDrawer.classList.toggle("open");
        });
    }

    if (closeInsightsBtn) {
        closeInsightsBtn.addEventListener("click", () => {
            if (insightsDrawer) insightsDrawer.classList.remove("open");
        });
    }

    // Download Session Report
    if (downloadReportBtn) {
        downloadReportBtn.addEventListener("click", () => {
            if (!currentSessionId) return;
            window.open(`/api/sessions/${currentSessionId}/report/download`, "_blank");
        });
    }

    if (micBtn) {
        micBtn.addEventListener("click", () => {
            if (isRecording) {
                // If user was speaking, clicking mic button stops speaking and immediately sends reply!
                stopRecording();
            } else {
                // Clicking mic button immediately launches the spectacular ChatGPT Voice Mode animation!
                enterVoiceMode();
            }
        });
    }

    if (sendBtn) {
        sendBtn.addEventListener("click", () => handleTextSubmit());
    }

    if (textInput) {
        textInput.addEventListener("keydown", (e) => {
            if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                handleTextSubmit();
            }
        });
    }

    if (speakerToggleBtn) {
        speakerToggleBtn.addEventListener("click", () => {
            audioPlayer.muted = !audioPlayer.muted;
            speakerToggleBtn.style.opacity = audioPlayer.muted ? "0.35" : "1";
        });
    }

    // Mobile Sidebar Drawer Controls
    const mobileMenuBtn = document.getElementById("mobileMenuBtn");
    const closeSidebarBtn = document.getElementById("closeSidebarBtn");
    const sidebarBackdrop = document.getElementById("sidebarBackdrop");
    const sidebar = document.getElementById("sidebar");

    function openMobileSidebar(e) {
        if (e) e.stopPropagation();
        if (sidebar) sidebar.classList.add("mobile-open");
        if (sidebarBackdrop) sidebarBackdrop.classList.remove("hidden");
    }

    function closeMobileSidebar(e) {
        if (e) e.stopPropagation();
        if (sidebar) sidebar.classList.remove("mobile-open");
        if (sidebarBackdrop) sidebarBackdrop.classList.add("hidden");
    }

    if (mobileMenuBtn) {
        mobileMenuBtn.addEventListener("pointerdown", (e) => e.stopPropagation());
        mobileMenuBtn.addEventListener("click", openMobileSidebar);
    }
    if (closeSidebarBtn) closeSidebarBtn.addEventListener("click", closeMobileSidebar);
    if (sidebarBackdrop) sidebarBackdrop.addEventListener("click", closeMobileSidebar);
}

function initPhase2Controls() {
    // Hands-Free VAD Toggle
    const handsFreeBtn = document.getElementById("handsFreeToggleBtn");
    if (handsFreeBtn) {
        handsFreeBtn.addEventListener("click", toggleHandsFree);
    }

    // Grounding Breath Modal Controls
    const openGroundingBtn = document.getElementById("openGroundingBtn");
    if (openGroundingBtn) {
        openGroundingBtn.addEventListener("click", () => openGroundingModal("box"));
    }

    const closeGroundingBtn = document.getElementById("closeGroundingBtn");
    if (closeGroundingBtn) {
        closeGroundingBtn.addEventListener("click", closeGroundingModal);
    }

    const acceptGroundingBtn = document.getElementById("acceptGroundingBtn");
    if (acceptGroundingBtn) {
        acceptGroundingBtn.addEventListener("click", () => {
            const pill = document.getElementById("groundingInvitePill");
            const mode = pill ? (pill.dataset.mode || "box") : "box";
            if (pill) pill.classList.add("hidden");
            openGroundingModal(mode);
        });
    }

    const dismissGroundingBtn = document.getElementById("dismissGroundingBtn");
    if (dismissGroundingBtn) {
        dismissGroundingBtn.addEventListener("click", () => {
            const pill = document.getElementById("groundingInvitePill");
            if (pill) pill.classList.add("hidden");
        });
    }

    const modeBoxBtn = document.getElementById("modeBoxBtn");
    if (modeBoxBtn) {
        modeBoxBtn.addEventListener("click", () => setBreathingMode("box"));
    }

    const mode478Btn = document.getElementById("mode478Btn");
    if (mode478Btn) {
        mode478Btn.addEventListener("click", () => setBreathingMode("478"));
    }

    const toggleBreathingBtn = document.getElementById("toggleBreathingBtn");
    if (toggleBreathingBtn) {
        toggleBreathingBtn.addEventListener("click", toggleBreathingPause);
    }
}

// ==========================================================================
// CHATGPT-STYLE FULL-DUPLEX REAL-TIME VOICE STREAMING ENGINE
// ==========================================================================

class StreamingAudioQueue {
    constructor(audioCtx) {
        this.ctx = audioCtx;
        this.queue = [];
        this.isPlaying = false;
        this.currentSource = null;
        this.nextStartTime = 0;
        this.currentTurnId = null;
        this.onStart = null;
        this.onEnded = null;
    }

    async enqueue(audioArrayBuffer, turnId) {
        if (this.currentTurnId !== null && turnId !== this.currentTurnId) {
            this.stopAndFlush();
        }
        this.currentTurnId = turnId;

        try {
            // decodeAudioData detaches the input buffer, so slice it
            const decodedBuffer = await this.ctx.decodeAudioData(audioArrayBuffer.slice(0));
            this.queue.push({ buffer: decodedBuffer, turnId });
            if (!this.isPlaying) {
                this.playNext();
            }
        } catch (e) {
            console.warn("[*] Audio chunk decode notice:", e);
        }
    }

    playNext() {
        if (this.queue.length === 0) {
            this.isPlaying = false;
            this.currentSource = null;
            if (this.onEnded) this.onEnded();
            return;
        }

        this.isPlaying = true;
        if (this.onStart) this.onStart();

        const item = this.queue.shift();
        const source = this.ctx.createBufferSource();
        source.buffer = item.buffer;
        source.connect(this.ctx.destination);

        const now = this.ctx.currentTime;
        const startTime = Math.max(now, this.nextStartTime);
        source.start(startTime);
        this.nextStartTime = startTime + item.buffer.duration;
        this.currentSource = source;

        source.onended = () => {
            if (this.currentSource === source) {
                this.currentSource = null;
                if (this.queue.length > 0) {
                    this.playNext();
                } else {
                    // Slight buffer grace for next progressive sentence chunk
                    setTimeout(() => {
                        if (this.queue.length > 0) {
                            this.playNext();
                        } else {
                            this.isPlaying = false;
                            this.nextStartTime = 0;
                            if (this.onEnded) this.onEnded();
                        }
                    }, 60);
                }
            }
        };
    }

    stopAndFlush() {
        if (this.currentSource) {
            try {
                this.currentSource.stop(0);
                this.currentSource.disconnect();
            } catch (e) {}
            this.currentSource = null;
        }
        this.queue = [];
        this.isPlaying = false;
        this.nextStartTime = 0;
        if (this.onEnded) this.onEnded();
    }
}

// 16kHz 16-Bit Mono PCM Resampler
function downsampleTo16kPCM(buffer, sampleRate) {
    if (sampleRate === 16000) {
        const pcm = new Int16Array(buffer.length);
        for (let i = 0; i < buffer.length; i++) {
            const s = Math.max(-1, Math.min(1, buffer[i]));
            pcm[i] = s < 0 ? s * 0x8000 : s * 0x7FFF;
        }
        return pcm.buffer;
    }

    const ratio = sampleRate / 16000;
    const newLength = Math.round(buffer.length / ratio);
    const result = new Int16Array(newLength);
    let offsetResult = 0;
    let offsetBuffer = 0;

    while (offsetResult < newLength) {
        const nextOffsetBuffer = Math.round((offsetResult + 1) * ratio);
        let accum = 0;
        let count = 0;
        for (let i = offsetBuffer; i < nextOffsetBuffer && i < buffer.length; i++) {
            accum += buffer[i];
            count++;
        }
        const sample = count > 0 ? (accum / count) : 0;
        const s = Math.max(-1, Math.min(1, sample));
        result[offsetResult] = s < 0 ? s * 0x8000 : s * 0x7FFF;
        offsetResult++;
        offsetBuffer = nextOffsetBuffer;
    }
    return result.buffer;
}

let voiceWebSocket = null;
let isVoiceWebSocketActive = false;
let audioQueue = null;
let pcmProcessorNode = null;
let pcmDummyGain = null;
let pcmSourceNode = null;
let currentStreamingAiBubble = null;
let currentStreamingAiTurnId = null;

function sendVoiceConfigToWs() {
    if (voiceWebSocket && voiceWebSocket.readyState === WebSocket.OPEN) {
        voiceWebSocket.send(JSON.stringify({
            type: "config",
            session_id: currentSessionId || "",
            user_id: currentUserId || "guest_user",
            voice: selectedVoice || "en-IN-NeerjaExpressiveNeural"
        }));
    }
}

function initVoiceWebSocket() {
    if (voiceWebSocket && (voiceWebSocket.readyState === WebSocket.OPEN || voiceWebSocket.readyState === WebSocket.CONNECTING)) {
        return;
    }

    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const wsUrl = `${protocol}//${window.location.host}/api/ws/voice`;
    console.log("[*] Opening Real-Time Voice WebSocket:", wsUrl);

    try {
        voiceWebSocket = new WebSocket(wsUrl);
        voiceWebSocket.binaryType = "arraybuffer";

        voiceWebSocket.onopen = () => {
            console.log("[✓] Voice WebSocket connected!");
            isVoiceWebSocketActive = true;
            sendVoiceConfigToWs();
        };

        voiceWebSocket.onmessage = async (event) => {
            if (typeof event.data === "string") {
                try {
                    const msg = JSON.parse(event.data);
                    handleVoiceWebSocketMessage(msg);
                } catch (e) {
                    console.warn("[!] WS JSON parse notice:", e);
                }
            }
        };

        voiceWebSocket.onerror = (err) => {
            console.warn("[!] Voice WebSocket error:", err);
        };

        voiceWebSocket.onclose = () => {
            console.log("[*] Voice WebSocket closed.");
            isVoiceWebSocketActive = false;
            voiceWebSocket = null;
        };
    } catch (e) {
        console.warn("[!] Failed to instantiate Voice WebSocket:", e);
    }
}

function handleVoiceWebSocketMessage(msg) {
    const modalState = document.getElementById("modalVoiceStateText");
    const orbWrap = document.getElementById("voiceOrbWrapper");
    const telemetryBadge = document.getElementById("modalVocalTelemetry");
    const modalToneBadge = document.getElementById("modalToneBadge");

    if (msg.type === "ready") {
        if (modalState) modalState.textContent = "Listening to you...";
        if (orbWrap) {
            orbWrap.classList.remove("speaking");
            orbWrap.classList.add("listening");
        }
    }
    else if (msg.type === "status") {
        if (msg.state === "processing") {
            if (modalState) modalState.textContent = "Arogya is reflecting...";
        } else if (msg.state === "listening") {
            if (!audioQueue || !audioQueue.isPlaying) {
                if (modalState) modalState.textContent = "Listening to you...";
                if (orbWrap) {
                    orbWrap.classList.remove("speaking");
                    orbWrap.classList.add("listening");
                }
            }
        }
    }
    else if (msg.type === "transcript") {
        if (msg.role === "user") {
            console.log("[+] User transcript:", msg.text);
            appendVoiceBubbleUser(msg.text);
            currentStreamingAiBubble = null;
            currentStreamingAiTurnId = null;
        }
    }
    else if (msg.type === "transcript_chunk") {
        appendVoiceBubbleAiChunk(msg.text, msg.turn_id);
    }
    else if (msg.type === "audio_chunk") {
        if (modalState) modalState.textContent = "Arogya speaking... (speak to interrupt)";
        if (orbWrap) {
            orbWrap.classList.remove("listening");
            orbWrap.classList.add("speaking");
        }

        const binStr = atob(msg.audio_b64);
        const bytes = new Uint8Array(binStr.length);
        for (let i = 0; i < binStr.length; i++) {
            bytes[i] = binStr.charCodeAt(i);
        }
        if (audioQueue) {
            audioQueue.enqueue(bytes.buffer, msg.turn_id);
        }
    }
    else if (msg.type === "telemetry") {
        if (telemetryBadge) {
            const bpm = msg.bpm || 64;
            const label = msg.tone_label || "Calm";
            telemetryBadge.textContent = `${bpm} BPM • ${label}`;
        }
        if (msg.tone_label && modalToneBadge) {
            modalToneBadge.textContent = `Tone: ${msg.tone_label}`;
        }
    }
    else if (msg.type === "interrupted") {
        console.log("[*] Server confirmed barge-in interruption.");
        if (audioQueue) {
            audioQueue.stopAndFlush();
        }
        if (modalState) modalState.textContent = "Listening to you...";
        if (orbWrap) {
            orbWrap.classList.remove("speaking");
            orbWrap.classList.add("listening");
        }
    }
    else if (msg.type === "turn_complete") {
        console.log(`[✓] Turn ${msg.turn_id} completed.`);
    }
}

function appendVoiceBubbleAiChunk(text, turnId) {
    const stream = document.getElementById("voiceChatStream");
    if (!stream || !text) return;

    if (!currentStreamingAiBubble || currentStreamingAiTurnId !== turnId) {
        currentStreamingAiTurnId = turnId;
        currentStreamingAiBubble = document.createElement("div");
        currentStreamingAiBubble.className = "voice-bubble-ai";
        currentStreamingAiBubble.textContent = text;
        stream.appendChild(currentStreamingAiBubble);
    } else {
        currentStreamingAiBubble.textContent += " " + text;
    }

    stream.scrollTop = stream.scrollHeight;
}

function startPcmStreaming(stream) {
    if (!audioContext) {
        audioContext = new (window.AudioContext || window.webkitAudioContext)();
    }
    if (audioContext.state === "suspended") {
        audioContext.resume().catch(() => {});
    }

    stopPcmStreaming();

    try {
        pcmSourceNode = audioContext.createMediaStreamSource(stream);
        pcmProcessorNode = audioContext.createScriptProcessor(4096, 1, 1);

        pcmProcessorNode.onaudioprocess = (e) => {
            if (!isVoiceModalActive || isMicMuted) return;

            const inputData = e.inputBuffer.getChannelData(0);

            // Client-Side Immediate Barge-In Check
            if (audioQueue && audioQueue.isPlaying) {
                let sum = 0;
                for (let i = 0; i < inputData.length; i++) {
                    sum += inputData[i] * inputData[i];
                }
                const rms = Math.sqrt(sum / inputData.length);
                if (rms > 0.05) {
                    console.log("[*] Client-side voice barge-in detected! Stopping audio queue.");
                    audioQueue.stopAndFlush();
                    if (voiceWebSocket && voiceWebSocket.readyState === WebSocket.OPEN) {
                        voiceWebSocket.send(JSON.stringify({ type: "interrupt" }));
                    }
                    const modalState = document.getElementById("modalVoiceStateText");
                    if (modalState) modalState.textContent = "Listening to you...";
                    const orbWrap = document.getElementById("voiceOrbWrapper");
                    if (orbWrap) {
                        orbWrap.classList.remove("speaking");
                        orbWrap.classList.add("listening");
                    }
                }
            }

            // Downsample and stream 16kHz PCM chunks over WebSocket
            if (voiceWebSocket && voiceWebSocket.readyState === WebSocket.OPEN) {
                const pcmBytes = downsampleTo16kPCM(inputData, audioContext.sampleRate);
                voiceWebSocket.send(pcmBytes);
            }
        };

        pcmDummyGain = audioContext.createGain();
        pcmDummyGain.gain.value = 0;
        pcmSourceNode.connect(pcmProcessorNode);
        pcmProcessorNode.connect(pcmDummyGain);
        pcmDummyGain.connect(audioContext.destination);
    } catch (err) {
        console.warn("[!] PCM streaming setup notice:", err);
    }
}

function stopPcmStreaming() {
    if (pcmProcessorNode) {
        try {
            pcmProcessorNode.disconnect();
            if (pcmSourceNode) pcmSourceNode.disconnect();
            if (pcmDummyGain) pcmDummyGain.disconnect();
        } catch(e) {}
        pcmProcessorNode = null;
        pcmSourceNode = null;
        pcmDummyGain = null;
    }
}

// --- CHATGPT-STYLE LIVE VOICE MODE CONTROLS ---
function initVoiceModeControls() {
    const startVoiceModeBtn = document.getElementById("startVoiceModeBtn");
    if (startVoiceModeBtn) {
        startVoiceModeBtn.addEventListener("click", enterVoiceMode);
    }

    const openVoiceModeBtn = document.getElementById("openVoiceModeBtn");
    if (openVoiceModeBtn) {
        openVoiceModeBtn.addEventListener("click", enterVoiceMode);
    }

    const modalMinimizeBtn = document.getElementById("modalMinimizeBtn");
    if (modalMinimizeBtn) {
        modalMinimizeBtn.addEventListener("click", exitVoiceMode);
    }

    // Microphone Mute / Unmute & Voice Interruption Button in Floating Dock
    const modalMicToggleBtn = document.getElementById("modalMicToggleBtn");
    if (modalMicToggleBtn) {
        modalMicToggleBtn.addEventListener("click", () => {
            if (isAiAudioPlaying || (audioQueue && audioQueue.isPlaying)) {
                console.log("[*] Tap on mic button: interrupting AI speech playback.");
                if (audioQueue) audioQueue.stopAndFlush();
                if (voiceWebSocket && voiceWebSocket.readyState === WebSocket.OPEN) {
                    voiceWebSocket.send(JSON.stringify({ type: "interrupt" }));
                }
                isAiAudioPlaying = false;
                const modalState = document.getElementById("modalVoiceStateText");
                if (modalState) modalState.textContent = "Listening to you...";
                const orbWrap = document.getElementById("voiceOrbWrapper");
                if (orbWrap) {
                    orbWrap.classList.remove("speaking");
                    orbWrap.classList.add("listening");
                }
                return;
            }

            // Toggle Mute / Unmute
            isMicMuted = !isMicMuted;
            const modalState = document.getElementById("modalVoiceStateText");
            if (isMicMuted) {
                modalMicToggleBtn.classList.add("muted");
                if (modalState) modalState.textContent = "Microphone muted";
            } else {
                modalMicToggleBtn.classList.remove("muted");
                if (modalState) modalState.textContent = "Listening to you...";
            }
        });
    }

    // Tapping the voice orb interrupts playback instantly
    const voiceOrbWrapper = document.getElementById("voiceOrbWrapper");
    if (voiceOrbWrapper) {
        voiceOrbWrapper.addEventListener("click", () => {
            if (isAiAudioPlaying || (audioQueue && audioQueue.isPlaying)) {
                console.log("[*] Tap on voice orb: interrupting AI playback.");
                if (audioQueue) audioQueue.stopAndFlush();
                if (voiceWebSocket && voiceWebSocket.readyState === WebSocket.OPEN) {
                    voiceWebSocket.send(JSON.stringify({ type: "interrupt" }));
                }
                isAiAudioPlaying = false;
                const modalState = document.getElementById("modalVoiceStateText");
                if (modalState) modalState.textContent = "Listening to you...";
                const orbWrap = document.getElementById("voiceOrbWrapper");
                if (orbWrap) {
                    orbWrap.classList.remove("speaking");
                    orbWrap.classList.add("listening");
                }
            }
        });
    }

    // Quick Inline Text Typing in Voice Mode ('+ Type' button in Floating Dock)
    const voiceDockTypeBtn = document.getElementById("voiceDockTypeBtn");
    const voiceInlineTypeBar = document.getElementById("voiceInlineTypeBar");
    const voiceInlineTextInput = document.getElementById("voiceInlineTextInput");
    const voiceInlineSendBtn = document.getElementById("voiceInlineSendBtn");

    if (voiceDockTypeBtn && voiceInlineTypeBar) {
        voiceDockTypeBtn.addEventListener("click", () => {
            voiceInlineTypeBar.classList.toggle("hidden");
            if (!voiceInlineTypeBar.classList.contains("hidden") && voiceInlineTextInput) {
                voiceInlineTextInput.focus();
            }
        });
    }

    const sendInlineText = () => {
        if (!voiceInlineTextInput) return;
        const text = voiceInlineTextInput.value.trim();
        if (!text) return;
        voiceInlineTextInput.value = "";
        if (voiceInlineTypeBar) voiceInlineTypeBar.classList.add("hidden");
        // Interrupt AI if currently playing and send typed prompt
        if (audioQueue) audioQueue.stopAndFlush();
        stopAllAudioPlayback();
        handleTextSubmit(text);
    };

    if (voiceInlineSendBtn) {
        voiceInlineSendBtn.addEventListener("click", sendInlineText);
    }
    if (voiceInlineTextInput) {
        voiceInlineTextInput.addEventListener("keydown", (e) => {
            if (e.key === "Enter") {
                e.preventDefault();
                sendInlineText();
            }
        });
    }

    // Circular Blue 'X' Button to End Conversation & View Summary
    const endConversationBtn = document.getElementById("endConversationBtn");
    if (endConversationBtn) {
        endConversationBtn.addEventListener("click", endVoiceConversation);
    }

    const inlineFinishBtn = document.getElementById("inlineFinishBtn");
    if (inlineFinishBtn) {
        inlineFinishBtn.addEventListener("click", () => {
            if (isRecording) stopRecording();
        });
    }

    const inlineExpandBtn = document.getElementById("inlineExpandBtn");
    if (inlineExpandBtn) {
        inlineExpandBtn.addEventListener("click", enterVoiceMode);
    }

    const chatgptVoiceModal = document.getElementById("chatgptVoiceModal");
    if (chatgptVoiceModal) {
        chatgptVoiceModal.addEventListener("click", (e) => {
            if (e.target.closest("#endConversationBtn") || e.target.closest("#modalMinimizeBtn") || e.target.closest("#modalMicToggleBtn") || e.target.closest("#voiceDockTypeBtn") || e.target.closest("#voiceInlineTypeBar")) return;
            if (isAiAudioPlaying || (audioQueue && audioQueue.isPlaying)) {
                console.log("[*] Tap on voice modal: interrupting AI speech playback.");
                if (audioQueue) audioQueue.stopAndFlush();
                if (voiceWebSocket && voiceWebSocket.readyState === WebSocket.OPEN) {
                    voiceWebSocket.send(JSON.stringify({ type: "interrupt" }));
                }
                isAiAudioPlaying = false;
                const modalState = document.getElementById("modalVoiceStateText");
                if (modalState) modalState.textContent = "Listening to you...";
                const orbWrap = document.getElementById("voiceOrbWrapper");
                if (orbWrap) {
                    orbWrap.classList.remove("speaking");
                    orbWrap.classList.add("listening");
                }
            }
        });
    }

    // Spacebar tap-to-interrupt in voice mode
    window.addEventListener("keydown", (e) => {
        if (isVoiceModalActive && e.code === "Space" && e.target.tagName !== "INPUT" && e.target.tagName !== "TEXTAREA") {
            e.preventDefault();
            if (isAiAudioPlaying || (audioQueue && audioQueue.isPlaying)) {
                console.log("[*] Spacebar pressed: interrupting AI speech playback.");
                if (audioQueue) audioQueue.stopAndFlush();
                if (voiceWebSocket && voiceWebSocket.readyState === WebSocket.OPEN) {
                    voiceWebSocket.send(JSON.stringify({ type: "interrupt" }));
                }
                isAiAudioPlaying = false;
                const modalState = document.getElementById("modalVoiceStateText");
                if (modalState) modalState.textContent = "Listening to you...";
                const orbWrap = document.getElementById("voiceOrbWrapper");
                if (orbWrap) {
                    orbWrap.classList.remove("speaking");
                    orbWrap.classList.add("listening");
                }
            }
        }
    });
}

async function enterVoiceMode() {
    stopAllAudioPlayback();
    if (currentTurnAbortController) {
        try { currentTurnAbortController.abort(); } catch(e){}
        currentTurnAbortController = null;
    }
    if (!audioContext) {
        audioContext = new (window.AudioContext || window.webkitAudioContext)();
    }
    if (audioContext.state === "suspended") {
        audioContext.resume().catch(() => {});
    }
    if (audioPlayer) {
        audioPlayer.play().then(() => {
            audioPlayer.pause();
            audioPlayer.currentTime = 0;
        }).catch(() => {});
    }
    isVoiceModalActive = true;
    isMicMuted = false;

    const modal = document.getElementById("chatgptVoiceModal");
    if (modal) modal.classList.remove("hidden");

    const inlineStage = document.getElementById("inlineVoiceStage");
    if (inlineStage) inlineStage.classList.add("hidden");

    const modalState = document.getElementById("modalVoiceStateText");
    if (modalState) modalState.textContent = "Listening to you...";

    const orbWrap = document.getElementById("voiceOrbWrapper");
    if (orbWrap) {
        orbWrap.classList.remove("speaking");
        orbWrap.classList.add("listening");
    }

    const modalMic = document.getElementById("modalMicToggleBtn");
    if (modalMic) {
        modalMic.classList.remove("muted");
        modalMic.classList.add("recording");
    }

    // Populate ChatGPT-style conversation stream from history
    populateVoiceStreamFromHistory();

    // 1. Initialize Streaming Audio Queue
    if (!audioQueue) {
        audioQueue = new StreamingAudioQueue(audioContext);
        audioQueue.onStart = () => {
            isAiAudioPlaying = true;
            const ow = document.getElementById("voiceOrbWrapper");
            if (ow) {
                ow.classList.remove("listening");
                ow.classList.add("speaking");
            }
            const ms = document.getElementById("modalVoiceStateText");
            if (ms) ms.textContent = "Arogya speaking... (speak to interrupt)";
        };
        audioQueue.onEnded = () => {
            isAiAudioPlaying = false;
            const ow = document.getElementById("voiceOrbWrapper");
            if (ow) {
                ow.classList.remove("speaking");
                ow.classList.add("listening");
            }
            const ms = document.getElementById("modalVoiceStateText");
            if (ms) ms.textContent = "Listening to you...";
        };
    }

    // 2. Initialize WebSocket to /api/ws/voice
    initVoiceWebSocket();

    // 3. Start microphone capture and 16kHz PCM streaming
    try {
        const stream = await getOrCreateMicStream();
        startPcmStreaming(stream);
        startVisualizerLoop();
    } catch(err) {
        console.warn("[*] Mic stream init notice:", err);
        if (modalState) modalState.textContent = "Please allow microphone access";
    }
}

function exitVoiceMode() {
    if (audioQueue) {
        audioQueue.stopAndFlush();
    }
    stopPcmStreaming();
    if (voiceWebSocket) {
        try { voiceWebSocket.close(); } catch(e){}
        voiceWebSocket = null;
    }

    stopAllAudioPlayback();
    releaseMicStream();
    isVoiceModalActive = false;
    isAiAudioPlaying = false;

    const modal = document.getElementById("chatgptVoiceModal");
    if (modal) modal.classList.add("hidden");
    drawIdleWaveform();
    const inlineStage = document.getElementById("inlineVoiceStage");
    if (inlineStage) inlineStage.classList.add("hidden");

    if (currentSessionId) {
        loadSessionData(currentSessionId);
    }
}

async function endVoiceConversation() {
    console.log("[*] Ending Voice Conversation Session...");
    exitVoiceMode();
    stopAllAudioPlayback();

    // Call finalize endpoint to synthesize entire conversation into a friendly summary
    if (currentSessionId) {
        try {
            setLiveStatus("Summarizing...", "listening");
            if (orbCaption) orbCaption.textContent = "Synthesizing our conversation...";

            const res = await apiFetch(`/api/sessions/${currentSessionId}/finalize`, { method: "POST" });
            if (res.ok) {
                const data = await res.json();
                await loadSessionData(currentSessionId);
                await loadSessions();

                if (data && data.summary) {
                    renderSessionSummaryCard(data.summary);
                }
            } else {
                await loadSessionData(currentSessionId);
                await loadSessions();
            }
        } catch (e) {
            console.warn("Finalize notice:", e);
            await loadSessionData(currentSessionId);
            await loadSessions();
        }
    }

    if (orbCaption) orbCaption.textContent = "Conversation completed. Summary below.";
    setLiveStatus("Completed", "");
}

// Friendly Heart-to-Heart Post-Session Summary Card (STRICTLY Zero Clinical Terms)
function renderSessionSummaryCard(summary) {
    if (!chatStream) return;

    const existing = document.getElementById("sessionSummaryCard");
    if (existing) existing.remove();

    const score = summary.overall_wellness != null ? Math.round(summary.overall_wellness) : 80;
    const scoreClass = score >= 75 ? "score-good" : (score >= 55 ? "score-fair" : "score-low");
    const title = escapeHtml(summary.vibe_title || "Feeling Balanced & Grounded");
    const peace = escapeHtml(summary.peace_of_mind || "Calm Waters");
    const energy = escapeHtml(summary.energy_vibe || "Steady & Recharging");
    const shift = escapeHtml(summary.emotional_shift || "You took time out to pause, reflect, and find your center.");

    const takeaways = summary.companion_takeaways || [];
    const takeawaysHtml = takeaways.map(t => `
        <li class="summary-takeaway-item">
            <span class="takeaway-bullet">🌿</span>
            <span>${escapeHtml(t)}</span>
        </li>
    `).join("");

    const highlights = summary.chat_highlights || [];
    const highlightsHtml = highlights.length > 0 ? `
        <div class="summary-section">
            <div class="summary-section-label">Highlights from our chat</div>
            <ul class="summary-highlights-list">
                ${highlights.map(h => `<li>✨ ${escapeHtml(h)}</li>`).join("")}
            </ul>
        </div>
    ` : "";

    const card = document.createElement("div");
    card.id = "sessionSummaryCard";
    card.className = "session-summary-container";
    card.innerHTML = `
        <div class="summary-card-inner">
            <div class="summary-header">
                <div class="summary-header-badge">
                    <span class="summary-pulse-dot"></span>
                    <span>Conversation Summary &amp; Wellness Insights</span>
                </div>
                <button class="btn-summary-dismiss" onclick="document.getElementById('sessionSummaryCard')?.remove()" title="Close summary">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
                </button>
            </div>

            <div class="summary-hero-row">
                <div class="summary-score-dial">
                    <span class="summary-score-val tabular-num ${scoreClass}">${score}</span>
                    <span class="summary-score-max">/100</span>
                </div>
                <div class="summary-hero-meta">
                    <div class="summary-vibe-pill ${scoreClass}">${title}</div>
                    <div class="summary-shift-text">${shift}</div>
                </div>
            </div>

            <div class="summary-metrics-grid">
                <div class="summary-metric-tile">
                    <div class="summary-tile-label">🌊 Peace of Mind</div>
                    <div class="summary-tile-value">${peace}</div>
                </div>
                <div class="summary-metric-tile">
                    <div class="summary-tile-label">⚡ Energy Level</div>
                    <div class="summary-tile-value">${energy}</div>
                </div>
            </div>

            ${takeaways.length > 0 ? `
            <div class="summary-section">
                <div class="summary-section-label">Friendly Reminders for Today</div>
                <ul class="summary-takeaways-list">
                    ${takeawaysHtml}
                </ul>
            </div>
            ` : ""}

            ${highlightsHtml}

            <div class="summary-footer-actions">
                <button type="button" class="btn-summary-action primary" onclick="startNewSession(true)">
                    <span>Start Fresh Reflection</span>
                </button>
                <button type="button" class="btn-summary-action secondary" onclick="enterVoiceMode()">
                    <span>Resume Live Voice</span>
                </button>
            </div>
        </div>
    `;

    chatStream.appendChild(card);
    chatStream.scrollTop = chatStream.scrollHeight;
}


// --- MICROPHONE DETECTION WITH HARDWARE GUARANTEE ---
async function initMicDeviceSelector() {
    if (!navigator.mediaDevices || !navigator.mediaDevices.enumerateDevices) return;

    try {
        let initialDevices = await navigator.mediaDevices.enumerateDevices();
        const hasLabels = initialDevices.some(d => d.kind === "audioinput" && d.label);

        if (!hasLabels) {
            try {
                const tempStream = await navigator.mediaDevices.getUserMedia({ audio: true });
                tempStream.getTracks().forEach(t => t.stop());
                initialDevices = await navigator.mediaDevices.enumerateDevices();
            } catch(permErr) {
                console.warn("User has not yet granted mic permission:", permErr);
            }
        }

        const audioInputs = initialDevices.filter(d => d.kind === "audioinput");
        if (!micDeviceSelect) return;
        micDeviceSelect.innerHTML = "";

        if (audioInputs.length === 0) {
            const opt = document.createElement("option");
            opt.value = "";
            opt.textContent = "Default Microphone";
            micDeviceSelect.appendChild(opt);
            return;
        }

        let preferredId = localStorage.getItem("preferred_mic_id") || "";
        let autoSelectedId = "";

        audioInputs.forEach((dev, idx) => {
            const label = dev.label || `Microphone ${idx + 1}`;
            const lowerLabel = label.toLowerCase();

            const isHeadset = lowerLabel.includes("headset") || lowerLabel.includes("headphone") || 
                              lowerLabel.includes("bluetooth") || lowerLabel.includes("airpod") || 
                              lowerLabel.includes("earbud") || lowerLabel.includes("hands-free") ||
                              lowerLabel.includes("wireless") || lowerLabel.includes("boat") || lowerLabel.includes("sony");
            const isVirtual = lowerLabel.includes("nahimic") || lowerLabel.includes("virtual") || lowerLabel.includes("stereo mix") || lowerLabel.includes("loopback");
            const isPhysical = isHeadset || lowerLabel.includes("realtek") || lowerLabel.includes("array") || lowerLabel.includes("usb") || lowerLabel.includes("microphone");

            const opt = document.createElement("option");
            opt.value = dev.deviceId;
            opt.textContent = label + (isHeadset ? " 🎧 (Headphones)" : (isVirtual ? " (Virtual)" : ""));

            // Auto-prioritize connected headphones/headsets over laptop mic
            if (isHeadset && !isVirtual) {
                autoSelectedId = dev.deviceId;
            } else if (!autoSelectedId && isPhysical && !isVirtual) {
                autoSelectedId = dev.deviceId;
            }

            micDeviceSelect.appendChild(opt);
        });

        // If headphones were just plugged in, prioritize them automatically
        const targetId = autoSelectedId || preferredId;
        if (targetId && Array.from(micDeviceSelect.options).some(o => o.value === targetId)) {
            micDeviceSelect.value = targetId;
        }

        if (!micDeviceSelect._hasChangeListener) {
            micDeviceSelect.addEventListener("change", () => {
                localStorage.setItem("preferred_mic_id", micDeviceSelect.value);
                console.log("[*] Preferred microphone set to:", micDeviceSelect.options[micDeviceSelect.selectedIndex]?.text);
            });
            micDeviceSelect._hasChangeListener = true;
        }

        if (navigator.mediaDevices && !navigator.mediaDevices._hasDeviceChangeListener) {
            navigator.mediaDevices._hasDeviceChangeListener = true;
            navigator.mediaDevices.addEventListener("devicechange", async () => {
                console.log("[*] Audio hardware change detected (headphone/mic connected or removed). Auto-adapting...");
                await initMicDeviceSelector();
                // If currently in voice mode, seamlessly refresh persistent stream to the new device
                if (isVoiceModalActive) {
                    try {
                        console.log("[*] Refreshing persistent mic stream to newly connected audio device...");
                        await getOrCreateMicStream(true);
                        if (isRecording) {
                            stopRecording();
                            setTimeout(() => {
                                if (isVoiceModalActive && !isRecording) startRecording();
                            }, 250);
                        }
                    } catch(e){}
                }
            });
        }
    } catch (err) {
        console.warn("Could not enumerate audio devices:", err);
        if (micDeviceSelect && micDeviceSelect.options.length === 0) {
            micDeviceSelect.innerHTML = '<option value="">Default Microphone</option>';
        }
    }
}

// --- MINIMALIST WAVEFORM RIBBON ---
function initCanvasVisualizer() {
    drawIdleWaveform();
}

function drawIdleWaveform() {
    if (!canvasCtx || !waveformCanvas) return;
    canvasCtx.clearRect(0, 0, waveformCanvas.width, waveformCanvas.height);
    const isDark = document.documentElement.getAttribute("data-theme") !== "light";
    const centerY = waveformCanvas.height / 2;

    canvasCtx.beginPath();
    canvasCtx.moveTo(0, centerY);
    canvasCtx.lineTo(waveformCanvas.width, centerY);
    canvasCtx.strokeStyle = isDark ? "#282828" : "#D4D4D4";
    canvasCtx.lineWidth = 1.5;
    canvasCtx.stroke();
}

function resetMicMeter() {
    if (micMeterFill) micMeterFill.style.width = "0%";
    if (micMeterStatus) {
        micMeterStatus.textContent = "Standby";
    }
}

// --- EXACT CHATGPT VOICE ORB VISUALIZER & FLUID CONVERSATIONAL PACING (HARDWARE 30 FPS CAP) ---
function startVisualizer(stream) {
    stopVisualizerLoop();

    if (!audioContext) {
        audioContext = new (window.AudioContext || window.webkitAudioContext)();
    }
    if (audioContext.state === "suspended") {
        audioContext.resume().catch(() => {});
    }
    const source = audioContext.createMediaStreamSource(stream);
    activeVisualizerSource = source;
    analyser = audioContext.createAnalyser();
    analyser.fftSize = 256;
    analyser.smoothingTimeConstant = 0.75;
    source.connect(analyser);

    const bufferLength = analyser.frequencyBinCount;
    const freqData = new Uint8Array(bufferLength);
    const timeData = new Uint8Array(bufferLength);

    const inlineCanvas = document.getElementById("inlineWaveCanvas");
    const inlineCtx = inlineCanvas ? inlineCanvas.getContext("2d") : null;

    // Cache DOM references once to avoid layout thrashing across animation frames
    const ribbonTonePill = document.getElementById("voiceTonePill");
    const modalToneBadge = document.getElementById("modalToneBadge");
    const inlineToneBadge = document.getElementById("inlineVoiceToneText");
    const inlineGlow = document.getElementById("inlineOrbGlow");
    const chatgptOrbSphere = document.getElementById("chatgptOrbSphere");
    const inlineVoiceStage = document.getElementById("inlineVoiceStage");
    const modalStateText = document.getElementById("modalVoiceStateText");
    const orbWrap = document.getElementById("voiceOrbWrapper");

    let lastDomUpdateTime = 0;
    visualizerRunning = true;
    lastFrameTimestamp = performance.now();

    function render(now) {
        if (!visualizerRunning || (!isVoiceModalActive && !isRecording && !isAiAudioPlaying && (!audioPlayer || audioPlayer.paused))) {
            stopVisualizerLoop();
            drawIdleWaveform();
            return;
        }

        analyser.getByteFrequencyData(freqData);
        analyser.getByteTimeDomainData(timeData);

        // 1. Calculate Time-Domain RMS Volume + Vocal Band Spectral Energy
        let sum = 0;
        let vocalSum = 0;
        let weightedFreqSum = 0;
        let totalFreqWeight = 0;
        let timeDomainRmsSum = 0;
        const vocalBinsCount = Math.min(24, bufferLength);

        for (let i = 0; i < bufferLength; i++) {
            const val = freqData[i];
            sum += val;
            if (i < vocalBinsCount) {
                vocalSum += val;
            }
            if (val > 10) {
                weightedFreqSum += i * val;
                totalFreqWeight += val;
            }
            const diff = (timeData[i] - 128) / 128.0;
            timeDomainRmsSum += diff * diff;
        }
        const rms = Math.sqrt(timeDomainRmsSum / bufferLength);
        const rmsPercent = Math.min(100, Math.round(rms * 450));
        const avg = sum / bufferLength;
        const vocalAvg = vocalSum / vocalBinsCount;
        const vocalPercent = Math.min(100, Math.round((vocalAvg / 32) * 100));
        // True speech energy accounts for both time-domain acoustic displacement and vocal frequency bands
        const percent = Math.min(100, Math.max(vocalPercent, rmsPercent));

        // 2. Estimate Spectral Centroid & Vocal Tone / Pitch
        if (totalFreqWeight > 0) {
            const centroidBin = weightedFreqSum / totalFreqWeight;
            const nyquist = (audioContext.sampleRate || 16000) / 2;
            voiceToneCentroid = Math.round((centroidBin / bufferLength) * nyquist);
        }

        // Determine Tone & Chromatic Color Palette
        let toneLabel = "Calm & Steady";
        let toneClass = "tone-calm";
        let toneColor = "#38bdf8"; // Cyan
        let glowColor = "rgba(56, 189, 248, 0.45)";
        let secondaryColor = "#2dd4bf"; // Teal

        if (voiceToneCentroid < 160) {
            toneLabel = "Deep & Grounded";
            toneClass = "tone-deep";
            toneColor = "#818cf8"; // Indigo
            glowColor = "rgba(129, 140, 248, 0.5)";
            secondaryColor = "#c084fc"; // Violet
        } else if (voiceToneCentroid > 280) {
            toneLabel = "Expressive & High";
            toneClass = "tone-elevated";
            toneColor = "#fb923c"; // Amber
            glowColor = "rgba(251, 146, 60, 0.55)";
            secondaryColor = "#f43f5e"; // Rose
        }

        // 3. Exact ChatGPT Orb Visualizer: GPU volume-scale during user speech, CSS breathing when idle/speaking
        if (chatgptOrbSphere && isVoiceModalActive) {
            if (isRecording && percent > 5 && !isAiAudioPlaying) {
                const speechScale = 1.0 + Math.min(0.35, (percent / 100) * 0.35);
                chatgptOrbSphere.style.transform = `scale3d(${speechScale.toFixed(3)}, ${speechScale.toFixed(3)}, 1)`;
            } else {
                if (chatgptOrbSphere.style.transform) {
                    chatgptOrbSphere.style.transform = "";
                }
            }
        }

        // 4. Throttled DOM Telemetry (10 FPS / 100ms throttle to prevent layout recalculations)
        if (now - lastDomUpdateTime > 100) {
            lastDomUpdateTime = now;

            if (ribbonTonePill) {
                ribbonTonePill.classList.remove("hidden");
                ribbonTonePill.className = `voice-tone-pill ${toneClass}`;
                ribbonTonePill.textContent = toneLabel;
            }
            if (modalToneBadge) {
                modalToneBadge.className = `voice-modal-tone-badge ${toneClass}`;
                modalToneBadge.textContent = toneLabel;
            }
            if (inlineToneBadge) {
                inlineToneBadge.textContent = toneLabel;
                inlineToneBadge.style.color = toneColor;
                inlineToneBadge.style.borderColor = toneColor + "55";
            }
            if (inlineGlow) {
                inlineGlow.style.background = `radial-gradient(circle, ${glowColor} 0%, transparent 70%)`;
            }

            if (micMeterFill) micMeterFill.style.width = `${percent}%`;
            if (micMeterStatus) micMeterStatus.textContent = percent > 5 ? `${percent}%` : "Quiet";
        }

        // 5. Full-Duplex Voice Barge-In (Interruption while AI is Speaking - Instant Halt)
        if (isVoiceModalActive && (isAiAudioPlaying || (audioPlayer && !audioPlayer.paused))) {
            const bargeInThreshold = Math.max(12, Math.round(vadNoiseFloor + 6.5));
            if (percent >= bargeInThreshold) {
                bargeInConsecutiveFrames = (bargeInConsecutiveFrames || 0) + 1;
                if (bargeInConsecutiveFrames >= 2) {
                    console.log("[*] Full-duplex voice barge-in detected! Instantly halting AI playback.");
                    bargeInConsecutiveFrames = 0;
                    stopAllAudioPlayback();
                    if (currentTurnAbortController) {
                        try { currentTurnAbortController.abort(); } catch(e){}
                        currentTurnAbortController = null;
                    }
                    isAiAudioPlaying = false;
                    const modalState = document.getElementById("modalVoiceStateText");
                    if (modalState) modalState.textContent = "Listening to you...";
                    const orbWrap = document.getElementById("voiceOrbWrapper");
                    if (orbWrap) {
                        orbWrap.classList.remove("speaking");
                        orbWrap.classList.add("listening");
                    }
                    activeVoiceUserBubble = null;
                    if (!isRecording) {
                        startRecording();
                    }
                    vadHasSpoken = true;
                    speechDetectedInCurrentTurn = true;
                    lastSpeechActivityTimestamp = performance.now();
                }
            } else {
                bargeInConsecutiveFrames = Math.max(0, (bargeInConsecutiveFrames || 0) - 1);
            }
        }

        // 6. Conversational VAD & Fluid Auto-Turn Pacing (ChatGPT-Style Natural Auto-Reply)
        // Automatically submits audio on natural silence pause (~1,400ms) without user needing to click anything!
        if (isRecording && !isAiAudioPlaying && (!audioPlayer || audioPlayer.paused) && !isMicMuted) {
            // Adaptive noise floor tracking (adapts to room ambient noise, laptop fans, headphones)
            if (vadFrameCount < 12) {
                vadFrameCount++;
                vadNoiseFloor = 0.8 * vadNoiseFloor + 0.2 * percent;
            } else if (percent < vadNoiseFloor + 3) {
                vadNoiseFloor = 0.95 * vadNoiseFloor + 0.05 * percent;
            }

            // Sensitive speech threshold adapted for headsets, mobile mics, and quiet voices (5% floor)
            const speechThreshold = Math.max(5, Math.round(vadNoiseFloor + 2.5));
            const isVocalEnergyActive = (percent >= speechThreshold);

            if (isVocalEnergyActive) {
                // User is actively vocalizing right now
                if (initialSilenceTimer) {
                    clearTimeout(initialSilenceTimer);
                    initialSilenceTimer = null;
                }
                vadConsecutiveSpeechFrames = (vadConsecutiveSpeechFrames || 0) + 1;
                if (vadConsecutiveSpeechFrames >= 2) {
                    vadHasSpoken = true;
                    speechDetectedInCurrentTurn = true;
                }
                lastSpeechActivityTimestamp = performance.now();
            } else {
                vadConsecutiveSpeechFrames = Math.max(0, (vadConsecutiveSpeechFrames || 0) - 1);
            }

            // Continuous Turn-Taking: Auto-submit only on a true natural conversational pause
            const userSpokeInThisTurn = (vadHasSpoken || speechDetectedInCurrentTurn || (recognizedTranscript && recognizedTranscript.trim().length > 0));
            if (!autoSubmitTriggered && userSpokeInThisTurn && lastSpeechActivityTimestamp > 0) {
                const quietMs = performance.now() - lastSpeechActivityTimestamp;

                // Inspect transcript to see if user is trailing off on an incomplete connector
                const transcriptWords = (recognizedTranscript || "").trim().toLowerCase().split(/\s+/).filter(Boolean);
                const lastWord = transcriptWords[transcriptWords.length - 1] || "";
                const isIncompleteConnector = ["uh", "um", "and", "or", "but", "so", "like", "to", "because", "about", "that", "which"].includes(lastWord);
                const requiredSilenceMs = (isIncompleteConnector || transcriptWords.length < 2) ? 1800 : 1400;

                if (quietMs >= requiredSilenceMs && (isVoiceModalActive || isHandsFree)) {
                    console.log(`[*] Conversational turn complete (${Math.round(quietMs)}ms natural pause). Auto-submitting speech!`);
                    autoSubmitTriggered = true;
                    lastSpeechActivityTimestamp = 0;
                    lastFinalSpeechTimestamp = 0;
                    stopRecording();
                }
            }
        }

        // 7. Render Ribbon Canvas Waveform (Sound & Tone Responsive)
        if (canvasCtx && waveformCanvas && waveformCanvas.offsetParent !== null) {
            canvasCtx.clearRect(0, 0, waveformCanvas.width, waveformCanvas.height);
            const cy = waveformCanvas.height / 2;
            const w = waveformCanvas.width;

            canvasCtx.beginPath();
            canvasCtx.lineWidth = 2.5;
            canvasCtx.strokeStyle = toneColor;

            const sliceWidth = w / bufferLength;
            let x = 0;

            for (let i = 0; i < bufferLength; i++) {
                const v = timeData[i] / 128.0;
                const dynamicY = (v - 1.0) * cy * 1.8 + cy;

                if (i === 0) canvasCtx.moveTo(x, dynamicY);
                else canvasCtx.lineTo(x, dynamicY);

                x += sliceWidth;
            }
            canvasCtx.stroke();
        }

        // 8. Render Inline Audio Canvas (Guarded: only render when modal is NOT active AND visible)
        if (!isVoiceModalActive && inlineCtx && inlineCanvas && inlineVoiceStage && !inlineVoiceStage.classList.contains("hidden")) {
            inlineCtx.clearRect(0, 0, inlineCanvas.width, inlineCanvas.height);
            const w = inlineCanvas.width;
            const h = inlineCanvas.height;

            const numBars = 24;
            const barWidth = w / numBars;
            for (let b = 0; b < numBars; b++) {
                const binIdx = Math.floor(b * (bufferLength / numBars));
                const val = (freqData[binIdx] / 255.0);
                const barHeight = Math.max(3, val * (h * 0.75));
                const bx = b * barWidth;
                const by = h - barHeight;

                inlineCtx.fillStyle = toneColor;
                inlineCtx.globalAlpha = 0.2 + (val * 0.4);
                inlineCtx.fillRect(bx + 1, by, barWidth - 2, barHeight);
            }
            inlineCtx.globalAlpha = 1.0;
        }

        // 9. Hardware-Capped 30 FPS Limiter: Schedule next frame via setTimeout (33ms) + RAF
        if (animTimeoutId) {
            clearTimeout(animTimeoutId);
            animTimeoutId = null;
        }
        animTimeoutId = setTimeout(() => {
            if (visualizerRunning) {
                animFrameId = requestAnimationFrame(render);
            }
        }, 33);
    }

    // Launch first frame of loop
    animFrameId = requestAnimationFrame(render);
}

function handleAudioPlaybackStarted() {
    isAiAudioPlaying = true;
    setLiveStatus("Speaking...", "listening");
    orbCaption.textContent = "Arogya is speaking...";

    // Notify physical ESP32 to show speaking face and start mouth movement
    notifyEsp32SpeechState(1, currentSpeakingFace);

    if (isVoiceModalActive) {
        const aiText = document.getElementById("modalAiLiveText");
        if (aiText && currentAiReplyText) aiText.textContent = currentAiReplyText;

        const modalState = document.getElementById("modalVoiceStateText");
        if (modalState) modalState.textContent = "Arogya speaking... (speak to interrupt)";

        const orbWrap = document.getElementById("voiceOrbWrapper");
        if (orbWrap) {
            orbWrap.classList.add("speaking");
            orbWrap.classList.remove("listening");
        }
    }

    // Pause speech recognizer while Arogya is speaking so it never transcribes speaker output
    if (speechRecognizer) {
        try { speechRecognizer.stop(); } catch(e){}
    }
}

function handleAudioPlaybackEnded() {
    isAiAudioPlaying = false;
    currentBufferSource = null;
    if (!isVoiceModalActive && !isRecording) {
        stopVisualizerLoop();
    }
    setLiveStatus("Ready", "");
    orbCaption.textContent = (isHandsFree || isVoiceModalActive) ? "Listening to your thoughts..." : "Click microphone or type to reflect";
    drawIdleWaveform();

    // Notify physical ESP32 that speech has stopped
    notifyEsp32SpeechState(0);

    if (isVoiceModalActive) {
        const modalState = document.getElementById("modalVoiceStateText");
        if (modalState) modalState.textContent = "Arogya is listening... speak freely";

        const orbWrap = document.getElementById("voiceOrbWrapper");
        if (orbWrap) {
            orbWrap.classList.remove("speaking");
            orbWrap.classList.add("listening");
        }

        // In Voice Mode: automatically resume listening for user's next turn
        setTimeout(() => {
            if (isVoiceModalActive && !isRecording && !isTurnProcessing) {
                startRecording();
            }
        }, 350);
    } else if (isHandsFree && !isRecording) {
        setTimeout(() => {
            if (isHandsFree && !isRecording && !isTurnProcessing) {
                startRecording();
            }
        }, 500);
    }
}

function stopAllAudioPlayback() {
    if (currentBufferSource) {
        try { currentBufferSource.stop(); } catch(e){}
        currentBufferSource = null;
    }
    isAiAudioPlaying = false;
    if (audioPlayer && !audioPlayer.paused) {
        try {
            audioPlayer.pause();
            audioPlayer.currentTime = 0;
        } catch(e){}
    }
}

function setupAudioPlayerEvents() {
    if (!audioPlayer) return;

    audioPlayer.addEventListener("play", () => {
        handleAudioPlaybackStarted();
    });

    audioPlayer.addEventListener("ended", () => {
        handleAudioPlaybackEnded();
    });

    audioPlayer.addEventListener("pause", () => {
        if (!isAiAudioPlaying) {
            notifyEsp32SpeechState(0);
            if (isVoiceModalActive) {
                const orbWrap = document.getElementById("voiceOrbWrapper");
                if (orbWrap) orbWrap.classList.remove("speaking");
            }
        }
    });
}

// --- SESSIONS MANAGEMENT ---
async function loadSessions() {
    try {
        const res = await apiFetch("/api/sessions");
        const sessions = await res.json();
        renderSessionsList(sessions);
        if (sessionCountTag) {
            sessionCountTag.textContent = sessions.length;
        }
        return sessions || [];
    } catch (err) {
        console.error("Failed to load sessions:", err);
        return [];
    }
}

function renderSessionsList(sessions) {
    if (!sessionsList) return;
    sessionsList.innerHTML = "";
    if (sessions.length === 0) {
        sessionsList.innerHTML = `<div style="font-size:11.5px; color:var(--text-muted); padding:10px;">No past sessions yet.</div>`;
        return;
    }

    sessions.forEach(s => {
        const item = document.createElement("div");
        item.className = `session-item ${s.session_id === currentSessionId ? 'active' : ''}`;
        item.onclick = (e) => {
            if (e.target.closest(".session-action-btn")) return;
            selectSession(s.session_id);
        };

        const hasWellness = s.overall_wellness != null;
        const score = hasWellness ? Math.round(s.overall_wellness) : null;
        const scoreClass = hasWellness 
            ? (score >= 75 ? "score-good" : (score >= 55 ? "score-fair" : "score-low"))
            : "score-neutral";
        const scorePillHtml = hasWellness
            ? `<span class="session-score-pill ${scoreClass}">${score}%</span>`
            : `<span class="session-score-pill score-neutral">New</span>`;
        const dateStr = new Date(s.created_at).toLocaleDateString("en-IN", { month: "short", day: "numeric" });

        item.innerHTML = `
            <div class="session-item-content">
                <div class="session-item-title-row">
                    <span class="session-item-title">${escapeHtml(s.title || "Check-in")}</span>
                    ${scorePillHtml}
                </div>
                <span class="session-item-meta tabular-num">${dateStr} • ${escapeHtml(s.dominant_emotion || "Awaiting Reflection")}</span>
            </div>
            <div class="session-actions">
                <button class="session-action-btn" title="Rename" onclick="renameSessionPrompt('${s.session_id}', '${escapeHtml(s.title || '')}')">
                    <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>
                </button>
                <button class="session-action-btn" title="Delete" onclick="deleteSessionConfirm('${s.session_id}')">
                    <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>
                </button>
            </div>
        `;
        sessionsList.appendChild(item);
    });
}

async function selectSession(sessionId) {
    if (currentSessionId === sessionId) return;
    currentSessionId = sessionId;
    localStorage.setItem("arogya_active_session_id", sessionId);
    const sidebar = document.getElementById("sidebar");
    const sidebarBackdrop = document.getElementById("sidebarBackdrop");
    if (sidebar) sidebar.classList.remove("mobile-open");
    if (sidebarBackdrop) sidebarBackdrop.classList.add("hidden");
    await loadSessionData(sessionId);
    await loadSessions();
}

async function startNewSession(triggerGreeting = true) {
    try {
        const sidebar = document.getElementById("sidebar");
        const sidebarBackdrop = document.getElementById("sidebarBackdrop");
        if (sidebar) sidebar.classList.remove("mobile-open");
        if (sidebarBackdrop) sidebarBackdrop.classList.add("hidden");

        const res = await apiFetch("/api/sessions", { method: "POST" });
        const newSess = await res.json();
        currentSessionId = newSess.session_id;
        localStorage.setItem("arogya_active_session_id", newSess.session_id);
        if (currentSessionTitle) currentSessionTitle.textContent = newSess.title;
        renderWelcomeCard();
        resetScorecard();
        await loadSessions();

        if (triggerGreeting) {
            await fetchInitialGreeting();
        }
    } catch (err) {
        console.error("Error creating session:", err);
    }
}

async function renameSessionPrompt(sessionId, currentTitle) {
    const newTitle = prompt("Enter a new title for this conversation:", currentTitle);
    if (!newTitle || !newTitle.trim() || newTitle.trim() === currentTitle) return;

    try {
        const formData = new FormData();
        formData.append("title", newTitle.trim());
        const res = await apiFetch(`/api/sessions/${sessionId}`, {
            method: "PATCH",
            body: formData
        });
        if (res.ok) {
            if (sessionId === currentSessionId && currentSessionTitle) {
                currentSessionTitle.textContent = newTitle.trim();
            }
            await loadSessions();
        }
    } catch (err) {
        console.error("Error renaming session:", err);
    }
}

async function promptRenameCurrentSession() {
    if (!currentSessionId || !currentSessionTitle) return;
    await renameSessionPrompt(currentSessionId, currentSessionTitle.textContent);
}

async function deleteSessionConfirm(sessionId) {
    if (!confirm("Delete this session and its clinical conversation history?")) return;

    try {
        const res = await apiFetch(`/api/sessions/${sessionId}`, { method: "DELETE" });
        if (res.ok) {
            if (sessionId === currentSessionId) {
                currentSessionId = null;
                await loadSessions();
                if (!currentSessionId) {
                    await startNewSession(true);
                } else {
                    await loadSessionData(currentSessionId);
                }
            } else {
                await loadSessions();
            }
        }
    } catch (err) {
        console.error("Error deleting session:", err);
    }
}

async function loadSessionData(sessionId) {
    try {
        const res = await apiFetch(`/api/sessions/${sessionId}`);
        if (!res.ok) {
            console.warn("Session not found or forbidden, switching cleanly:", sessionId);
            localStorage.removeItem("arogya_active_session_id");
            const sessions = await loadSessions();
            if (sessions && sessions.length > 0) {
                currentSessionId = sessions[0].session_id;
                localStorage.setItem("arogya_active_session_id", currentSessionId);
                return await loadSessionData(currentSessionId);
            } else {
                return await startNewSession(true);
            }
        }
        const data = await res.json();
        if (!data || !data.session) {
            localStorage.removeItem("arogya_active_session_id");
            return await startNewSession(true);
        }

        if (currentSessionTitle) currentSessionTitle.textContent = data.session.title || "Emotional Wellness Reflection";
        
        const sessionWellness = (data.session && data.session.overall_wellness != null) 
            ? data.session.overall_wellness 
            : (data.latest_score && data.latest_score.overall_wellness);
        const sessionState = (data.session && data.session.dominant_emotion) 
            || (data.latest_score && data.latest_score.dominant_state);
        updateHeaderScorePill(sessionWellness, sessionState);

        if (data.messages && data.messages.length > 0) {
            chatStream.innerHTML = "";
            renderMessageHistory(data.messages);
        } else {
            renderWelcomeCard();
            await fetchInitialGreeting();
        }

        if (data.latest_score && data.latest_score.overall_wellness != null) {
            updateScorecard(data.latest_score);
        } else {
            resetScorecard();
        }
    } catch (err) {
        console.error("Error loading session data:", err);
    }
}

function renderMessageHistory(messages) {
    let lastUserText = "";
    messages.forEach(msg => {
        if (msg.role === "user") {
            lastUserText = msg.text;
        } else if (msg.role === "assistant") {
            const turnScore = (msg.speech_metrics && msg.speech_metrics.overall_wellness != null) ? msg.speech_metrics.overall_wellness : null;
            const turnState = (msg.speech_metrics && msg.speech_metrics.dominant_state) ? msg.speech_metrics.dominant_state : null;
            appendExchangeToUI(msg.text, lastUserText, msg.audio_path, false, turnScore, turnState);
            lastUserText = "";
        }
    });

    if (lastUserText) {
        appendPendingUserToUI(lastUserText);
    }
}

// Initial Spoken Greeting
async function fetchInitialGreeting() {
    setLiveStatus("Connecting...", "");
    orbCaption.textContent = "Arogya is welcoming you...";
    try {
        const res = await apiFetch(`/api/greeting?session_id=${currentSessionId}&voice_mode=${voiceMode}&voice=${encodeURIComponent(selectedVoice)}`);
        const data = await res.json();

        currentSpeakingFace = data.speaking_face || "happy";
        appendExchangeToUI(data.greeting_text, "", data.audio_url, true);
        setLiveStatus("Ready", "");
    } catch (err) {
        console.error("Error getting greeting:", err);
        setLiveStatus("Ready", "");
    }
}

// --- CONVERSATIONAL RENDERING ENGINE ---
// Strict User Typography:
// Quick Starter Handler for Onboarding Card
window.handleQuickStarter = function(promptText) {
    if (textInput) {
        textInput.value = promptText;
        handleTextSubmit();
    }
};

function renderWelcomeCard() {
    if (!chatStream) return;
    const displayName = (currentUser && (currentUser.display_name || currentUser.preferred_name || currentUser.given_name || currentUser.name)) || "";
    const greetingText = displayName ? `Welcome, ${escapeHtml(displayName)}` : "Welcome to Arogya";
    chatStream.innerHTML = `
        <div class="chat-welcome-card" id="chatWelcomeCard">
            <div class="welcome-symbol-halo">
                <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/></svg>
            </div>
            <div class="welcome-badge">
                <span class="welcome-pulse-dot"></span>
                <span>Arogya • Safe &amp; Confidential Space</span>
            </div>
            <h2 class="welcome-greeting-title" id="welcomeUserGreeting">${greetingText}</h2>
            <p class="welcome-greeting-desc">
                Take a slow, gentle breath. I am your companion, here to listen, support, and reflect with you without judgment.
            </p>
            <div class="welcome-action-suggestions">
                <button type="button" class="btn-quick-starter" onclick="handleQuickStarter('I\\'ve been feeling a bit overwhelmed and stressed today.')">
                    <span>💭 I'm feeling overwhelmed today</span>
                </button>
                <button type="button" class="btn-quick-starter" onclick="handleQuickStarter('Can you guide me through a calming breathing exercise?')">
                    <span>🌿 Can you guide my breathing?</span>
                </button>
                <button type="button" class="btn-quick-starter" onclick="handleQuickStarter('I just have a lot on my mind right now.')">
                    <span>✨ I have a lot on my mind right now</span>
                </button>
            </div>
            <span class="welcome-prompt-tip">Tap the microphone below to speak, or tap <strong>Live Voice</strong> for continuous dialogue</span>
        </div>
    `;
}

// - Arogya Captions: Newsreader (300 Large & Light, Warm Human Voice)
// - Spoken Words: Newsreader Italic (Quieter Subline)
function appendExchangeToUI(captionText, userSpokenWords, audioUrl, autoplay = false, turnScore = null, turnEmotion = null) {
    const pendingCard = document.getElementById("pendingUserCard");
    if (pendingCard) pendingCard.remove();
    const welcomeCard = document.getElementById("chatWelcomeCard");
    if (welcomeCard) welcomeCard.remove();

    const exchange = document.createElement("div");
    exchange.className = "conversation-exchange";

    const escapedCaption = captionText.replace(/\\/g, "\\\\").replace(/'/g, "\\'").replace(/"/g, "&quot;").replace(/\n/g, " ");
    const playBtnHtml = audioUrl ? `
        <button class="btn-caption-play" onclick="playAudio('${audioUrl}')">
            <svg width="10" height="10" viewBox="0 0 24 24" fill="currentColor"><polygon points="5 3 19 12 5 21 5 3"/></svg>
            <span>Play</span>
        </button>
    ` : `
        <button class="btn-caption-play" onclick="synthesizeAndPlay('${escapedCaption}', this)">
            <svg width="10" height="10" viewBox="0 0 24 24" fill="currentColor"><polygon points="5 3 19 12 5 21 5 3"/></svg>
            <span>Play</span>
        </button>
    `;

    let scoreBadgeHtml = "";
    if (turnScore != null) {
        const s = Math.round(turnScore);
        const badgeClass = s >= 75 ? "score-good" : (s >= 55 ? "score-fair" : "score-low");
        const emotionLabel = turnEmotion ? ` • ${escapeHtml(turnEmotion)}` : "";
        scoreBadgeHtml = `<span class="turn-score-badge ${badgeClass}" title="Evaluated mental wellness score for this reflection">${s}%${emotionLabel}</span>`;
    }

    const userSublineHtml = userSpokenWords ? `
        <div class="user-spoken-subline">
            <span class="user-echo-indicator">You:</span>
            <span>"${escapeHtml(userSpokenWords)}"</span>
        </div>
    ` : "";

    exchange.innerHTML = `
        <div class="arogya-caption-card">
            <div class="caption-sender-header">
                <div class="caption-sender-left">
                    <span class="caption-sender-name">Arogya</span>
                    ${scoreBadgeHtml}
                </div>
                ${playBtnHtml}
            </div>
            <div class="arogya-caption-text">${escapeHtml(captionText)}</div>
            ${userSublineHtml}
        </div>
    `;

    chatStream.appendChild(exchange);
    chatStream.scrollTop = chatStream.scrollHeight;

    if (autoplay && audioUrl && !audioPlayer.muted) {
        playAudio(audioUrl);
    }
}

function appendPendingUserToUI(text) {
    let cleanText = text;
    if (typeof cleanText !== "string" || cleanText.includes("[object") || cleanText.trim().length === 0) {
        cleanText = (textInput && textInput.value && textInput.value.trim()) || "Reflecting...";
    }
    const existing = document.getElementById("pendingUserCard");
    if (existing) existing.remove();
    const welcomeCard = document.getElementById("chatWelcomeCard");
    if (welcomeCard) welcomeCard.remove();

    const card = document.createElement("div");
    card.id = "pendingUserCard";
    card.className = "conversation-exchange";
    card.innerHTML = `
        <div class="user-pending-card">
            <div class="user-spoken-subline">
                <span class="user-echo-indicator">You:</span>
                <span>"${escapeHtml(cleanText)}"</span>
            </div>
        </div>
    `;
    chatStream.appendChild(card);
    chatStream.scrollTop = chatStream.scrollHeight;
}

async function playAudio(url) {
    if (!url) return;
    // Mute mic capturing immediately during AI audio output to prevent recording device speaker sound
    if (isRecording) {
        isRecording = false;
        if (mediaRecorder && mediaRecorder.state !== "inactive") {
            try { mediaRecorder.stop(); } catch(e){}
        }
        audioChunks = [];
        lastRecordedBlob = null;
        vadHasSpoken = false;
        speechDetectedInCurrentTurn = false;
        if (speechRecognizer) {
            try { speechRecognizer.stop(); } catch(e){}
        }
    }

    stopAllAudioPlayback();

    // Primary: Web Audio API buffer playback (zero autoplay restrictions, 0ms start latency)
    try {
        if (!audioContext) {
            audioContext = new (window.AudioContext || window.webkitAudioContext)();
        }
        if (audioContext.state === "suspended") {
            await audioContext.resume();
        }

        const resp = await fetch(url);
        const arrayBuf = await resp.arrayBuffer();
        const decodedBuffer = await audioContext.decodeAudioData(arrayBuf);

        const source = audioContext.createBufferSource();
        source.buffer = decodedBuffer;
        source.connect(audioContext.destination);

        currentBufferSource = source;
        handleAudioPlaybackStarted();

        source.onended = () => {
            if (currentBufferSource === source) {
                currentBufferSource = null;
                handleAudioPlaybackEnded();
            }
        };

        source.start(0);
        return;
    } catch (e) {
        console.warn("[!] Web Audio buffer decode notice, falling back to HTML5 Audio element:", e);
    }

    // Secondary fallback: HTML5 Audio element
    if (audioPlayer) {
        audioPlayer.src = url;
        audioPlayer.play().catch(err => {
            console.warn("Autoplay notice or play error:", err);
            // If audio playback couldn't start, ensure hands-free turn transitions aren't blocked
            if (isVoiceModalActive && !isRecording && !isTurnProcessing) {
                setTimeout(() => {
                    if (isVoiceModalActive && !isRecording) startRecording();
                }, 400);
            }
        });
    }
}

async function synthesizeAndPlay(text, btnEl) {
    if (btnEl) {
        btnEl.disabled = true;
        btnEl.innerHTML = `<span style="font-size:10px;">Voicing...</span>`;
    }
    try {
        const formData = new FormData();
        formData.append("text", text);
        formData.append("voice_mode", voiceMode || "fast");
        formData.append("voice", selectedVoice);
        const res = await apiFetch("/api/synthesize", {
            method: "POST",
            body: formData
        });
        if (res.ok) {
            const data = await res.json();
            if (data.audio_url) {
                if (btnEl) {
                    btnEl.disabled = false;
                    btnEl.innerHTML = `<svg width="10" height="10" viewBox="0 0 24 24" fill="currentColor"><polygon points="5 3 19 12 5 21 5 3"/></svg><span>Play</span>`;
                    btnEl.onclick = () => playAudio(data.audio_url);
                }
                playAudio(data.audio_url);
            }
        }
    } catch (e) {
        console.warn("TTS notice:", e);
        if (btnEl) {
            btnEl.disabled = false;
            btnEl.innerHTML = `<svg width="10" height="10" viewBox="0 0 24 24" fill="currentColor"><polygon points="5 3 19 12 5 21 5 3"/></svg><span>Play</span>`;
        }
    }
}

function setLiveStatus(text, modeClass) {
    if (!liveStatusText || !liveStatusPill) return;
    liveStatusText.textContent = text;
    liveStatusPill.className = `live-status-pill ${modeClass || ""}`;
}

// --- RECORDING & SPEECH-TO-SPEECH ---
function initSpeechRecognition() {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) return;

    try {
        if (speechRecognizer) {
            try { speechRecognizer.abort(); } catch(e){}
            speechRecognizer = null;
        }
        speechRecognizer = new SpeechRecognition();
        speechRecognizer.continuous = true;
        speechRecognizer.interimResults = true;
        speechRecognizer.lang = "en-IN";

        speechRecognizer.onresult = (event) => {
            // Voice Barge-In: If Arogya is speaking and user vocalizes words, instantly halt AI playback!
            if (isAiAudioPlaying || (audioPlayer && !audioPlayer.paused)) {
                let spokenWords = "";
                for (let i = event.resultIndex; i < event.results.length; ++i) {
                    spokenWords += event.results[i][0].transcript + " ";
                }
                if (spokenWords.trim().length > 0) {
                    console.log("[*] Interruption detected via browser speech recognition! Instantly halting AI playback.");
                    stopAllAudioPlayback();
                    if (currentTurnAbortController) {
                        try { currentTurnAbortController.abort(); } catch(e){}
                        currentTurnAbortController = null;
                    }
                    isAiAudioPlaying = false;
                    if (isVoiceModalActive) {
                        const modalState = document.getElementById("modalVoiceStateText");
                        if (modalState) modalState.textContent = "Listening to you...";
                        const orbWrap = document.getElementById("voiceOrbWrapper");
                        if (orbWrap) {
                            orbWrap.classList.remove("speaking");
                            orbWrap.classList.add("listening");
                        }
                    }
                    if (!isRecording) {
                        startRecording();
                    }
                    vadHasSpoken = true;
                    speechDetectedInCurrentTurn = true;
                    lastSpeechActivityTimestamp = performance.now();
                }
                return;
            }

            let interim = "";
            for (let i = event.resultIndex; i < event.results.length; ++i) {
                if (event.results[i].isFinal) {
                    recognizedTranscript += event.results[i][0].transcript + " ";
                    lastFinalSpeechTimestamp = performance.now();
                } else {
                    interim += event.results[i][0].transcript;
                }
            }
            const liveText = (recognizedTranscript + interim).trim();
            if (liveText && textInput) {
                textInput.value = liveText;
            }
            if (isVoiceModalActive) {
                const modalUserLive = document.getElementById("modalUserLiveText");
                if (modalUserLive && liveText) {
                    modalUserLive.textContent = `"${liveText}"`;
                }
                if (liveText.length >= 2) {
                    if (!activeVoiceUserBubble) {
                        activeVoiceUserBubble = appendVoiceBubbleUser(liveText);
                    } else {
                        activeVoiceUserBubble.textContent = liveText;
                    }
                }
            }

            if (liveText.length >= 2) {
                if (initialSilenceTimer) {
                    clearTimeout(initialSilenceTimer);
                    initialSilenceTimer = null;
                }
                vadHasSpoken = true;
                speechDetectedInCurrentTurn = true;
                lastSpeechActivityTimestamp = performance.now();
            }
        };

        speechRecognizer.onspeechend = () => {
            console.log("[*] Speech pause detected by browser engine.");
            // Natural pause pacing handled by robust acoustic VAD (no premature cutoff)
        };

        speechRecognizer.onerror = (e) => {
            console.log("[*] Speech recognition notice:", e.error);
        };

        speechRecognizer.onend = () => {
            // If still recording and Arogya is not speaking, keep recognition alive
            if (isRecording && !isAiAudioPlaying && (!audioPlayer || audioPlayer.paused)) {
                try { speechRecognizer.start(); } catch(e){}
            }
        };
    } catch (e) {
        console.warn("Speech recognition setup notice:", e);
    }
}

async function toggleRecording() {
    stopAllAudioPlayback();
    if (isRecording) {
        stopRecording();
    } else {
        await startRecording();
    }
}

async function startRecording() {
    stopAllAudioPlayback();
    notifyEsp32Emotion("thinking");
    try {
        let stream = await getOrCreateMicStream();

        audioChunks = [];
        lastRecordedBlob = null;
        recognizedTranscript = "";
        if (textInput) textInput.value = "";
        autoSubmitTriggered = false;
        vadHasSpoken = false;
        speechDetectedInCurrentTurn = false;
        vadFrameCount = 0;
        vadConsecutiveSpeechFrames = 0;
        bargeInFrameCount = 0;
        lastSpeechActivityTimestamp = 0;
        lastFinalSpeechTimestamp = 0;
        vadNoiseFloor = 8.0;
        if (vadSilenceTimer) {
            clearTimeout(vadSilenceTimer);
            vadSilenceTimer = null;
        }

        const options = MediaRecorder.isTypeSupported('audio/webm;codecs=opus')
            ? { mimeType: 'audio/webm;codecs=opus' }
            : undefined;

        mediaRecorder = new MediaRecorder(stream, options);

        mediaRecorder.ondataavailable = (e) => {
            if (e.data.size > 0) audioChunks.push(e.data);
        };

        mediaRecorder.onstop = async () => {
            resetMicMeter();
            lastRecordedBlob = new Blob(audioChunks, { type: mediaRecorder.mimeType || "audio/webm" });
            
            // Only stop hardware tracks if NOT in Voice Mode and NOT in hands-free
            if (!isVoiceModalActive && !isHandsFree) {
                releaseMicStream();
            }

            const currentText = textInput ? textInput.value.trim() : "";
            const isBrowserHallucination = currentText.toLowerCase().split(/\s+/).every(w => w === "you" || w === "thank");
            const finalClientText = (!isBrowserHallucination && currentText.length >= 2) ? currentText : "";

            const hasRecognizedSpeech = Boolean(finalClientText && finalClientText.length >= 2);
            // Real speech in WebM Opus is >= 2000 bytes; pure silence/noise is tiny
            const hasAudibleAudioBlob = Boolean(lastRecordedBlob && lastRecordedBlob.size > 2000);
            const userActuallySpoke = vadHasSpoken || speechDetectedInCurrentTurn || hasRecognizedSpeech;

            // Reset turn speech detection flags
            vadHasSpoken = false;
            speechDetectedInCurrentTurn = false;
            vadConsecutiveSpeechFrames = 0;

            if (userActuallySpoke && (hasRecognizedSpeech || hasAudibleAudioBlob)) {
                orbCaption.textContent = "Voice captured. Arogya is reflecting...";
                setLiveStatus("Reflecting...", "listening");
                if (isVoiceModalActive) {
                    const modalState = document.getElementById("modalVoiceStateText");
                    if (modalState) modalState.textContent = "Arogya is reflecting...";
                    const userLive = document.getElementById("modalUserLiveText");
                    if (userLive) userLive.textContent = finalClientText ? `"${finalClientText}"` : '"Listening to your thoughts..."';
                }
                await handleTextSubmit(finalClientText);
                return;
            } else {
                orbCaption.textContent = "Listening... speak whenever you're ready.";
                if (isVoiceModalActive) {
                    const modalState = document.getElementById("modalVoiceStateText");
                    if (modalState) modalState.textContent = "Listening to you...";
                    setTimeout(() => {
                        if (isVoiceModalActive && !isRecording && !isAiAudioPlaying && !isTurnProcessing) {
                            startRecording();
                        }
                    }, 200);
                }
                setLiveStatus("Ready", "");
                if (textInput) textInput.focus();
            }
        };

        if (!speechRecognizer) {
            initSpeechRecognition();
        }
        if (speechRecognizer) {
            try {
                speechRecognizer.start();
            } catch(e) {
                initSpeechRecognition();
                try { speechRecognizer.start(); } catch(e2){}
            }
        }

        mediaRecorder.start(250);
        isRecording = true;
        if (micBtn) micBtn.classList.add("recording");
        const modalMic = document.getElementById("modalMicToggleBtn");
        if (modalMic) modalMic.classList.add("recording");

        const inlineStage = document.getElementById("inlineVoiceStage");
        if (inlineStage && !isVoiceModalActive) {
            inlineStage.classList.remove("hidden");
        }

        orbCaption.textContent = "Listening... Speak naturally in English";
        setLiveStatus("Listening...", "listening");

        if (isVoiceModalActive) {
            const modalState = document.getElementById("modalVoiceStateText");
            if (modalState) modalState.textContent = "Listening to you...";
            const orbWrap = document.getElementById("voiceOrbWrapper");
            if (orbWrap) {
                orbWrap.classList.remove("speaking");
                orbWrap.classList.add("listening");
            }
        }

        startVisualizer(stream);
    } catch (err) {
        alert("Please enable microphone permissions in your browser settings.");
        console.error("Mic error:", err);
    }
}

function stopRecording() {
    if (isRecording) {
        isRecording = false;
        autoSubmitTriggered = true;
        // vadHasSpoken and speechDetectedInCurrentTurn are retained for mediaRecorder.onstop inspection
        lastSpeechActivityTimestamp = 0;
        lastFinalSpeechTimestamp = 0;
        if (vadSilenceTimer) {
            clearTimeout(vadSilenceTimer);
            vadSilenceTimer = null;
        }

        if (micBtn) micBtn.classList.remove("recording");
        const modalMic = document.getElementById("modalMicToggleBtn");
        if (modalMic) modalMic.classList.remove("recording");

        const inlineStage = document.getElementById("inlineVoiceStage");
        if (inlineStage) inlineStage.classList.add("hidden");

        setLiveStatus("Processing...", "listening");
        orbCaption.textContent = "Processing speech...";
        
        // In Voice Mode, keep visualizer loop active for continuous full-duplex listening and heartbeat!
        if (!isVoiceModalActive) {
            stopVisualizerLoop();
            drawIdleWaveform();
            resetMicMeter();
        }

        if (isVoiceModalActive) {
            const modalState = document.getElementById("modalVoiceStateText");
            if (modalState) modalState.textContent = "Arogya is reflecting...";
        }

        if (speechRecognizer) {
            try { speechRecognizer.stop(); } catch(e){}
        }

        setTimeout(() => {
            if (mediaRecorder && mediaRecorder.state !== "inactive") {
                mediaRecorder.stop();
            }
        }, 60);
    }
}

// --- SUBMISSION: CHATGPT-SPEED RESPONSE & IMMEDIATE TITLING ---
async function handleTextSubmit(overrideText = null) {
    if (isTurnProcessing) {
        console.log("[*] Turn already processing, ignoring duplicate trigger");
        return;
    }
    isTurnProcessing = true;
    try {
        let text = "";
        if (typeof overrideText === "string" && overrideText.trim().length > 0 && !overrideText.includes("[object")) {
            text = overrideText.trim();
        } else if (textInput && typeof textInput.value === "string" && textInput.value.trim().length > 0) {
            text = textInput.value.trim();
        }

        const audioToSend = lastRecordedBlob;
        lastRecordedBlob = null;

        if (!text && !audioToSend) {
            orbCaption.textContent = "Please speak into the mic or type first.";
            return;
        }

        if (textInput) textInput.value = "";
        appendPendingUserToUI(text || "Voice reflection...");
        setLiveStatus("Reflecting...", "listening");
        orbCaption.textContent = "Arogya is reflecting...";
        notifyEsp32Emotion("thinking");

        if (isVoiceModalActive) {
            const modalState = document.getElementById("modalVoiceStateText");
            if (modalState) modalState.textContent = "Arogya is reflecting...";
            const userLive = document.getElementById("modalUserLiveText");
            if (userLive) userLive.textContent = `"${text || 'Listening to your voice...'}"`;
            if (!activeVoiceUserBubble) {
                activeVoiceUserBubble = appendVoiceBubbleUser(text || "Thinking with you...");
            } else if (text) {
                activeVoiceUserBubble.textContent = text;
            }
        }

        currentTurnAbortController = new AbortController();
        let res, data;
        if (audioToSend) {
            const formData = new FormData();
            formData.append("file", audioToSend, "user_speech.webm");
            formData.append("session_id", currentSessionId);
            formData.append("voice_mode", voiceMode);
            formData.append("voice", selectedVoice);
            formData.append("client_transcript", text === "Voice reflection..." ? "" : text);

            res = await apiFetch("/api/chat/voice", {
                method: "POST",
                body: formData,
                signal: currentTurnAbortController.signal
            });
            data = await res.json();
        } else {
            // Text input: Send voice_mode based on current mode
            const formData = new FormData();
            formData.append("text", text);
            formData.append("session_id", currentSessionId);
            formData.append("voice_mode", (isVoiceModalActive ? (voiceMode || "fast") : "none"));

            res = await apiFetch("/api/chat/text", {
                method: "POST",
                body: formData,
                signal: currentTurnAbortController.signal
            });
            data = await res.json();
        }

        currentAiReplyText = data.reply_text || "";
        currentSpeakingFace = data.speaking_face || "caring";
        const finalUserSpokenText = data.transcript || text || "Voice reflection";

        if (isVoiceModalActive) {
            const aiLive = document.getElementById("modalAiLiveText");
            if (aiLive) aiLive.textContent = data.reply_text;
            const userLive = document.getElementById("modalUserLiveText");
            if (userLive) userLive.textContent = `"${finalUserSpokenText}"`;
            if (activeVoiceUserBubble && finalUserSpokenText) {
                activeVoiceUserBubble.textContent = finalUserSpokenText;
            }
            activeVoiceUserBubble = null; // Fresh bubble for next turn
            const modalState = document.getElementById("modalVoiceStateText");
            if (modalState) modalState.textContent = "Arogya speaking... (speak to interrupt)";
            if (data.reply_text) {
                appendVoiceBubbleAi(data.reply_text);
            }
        }

        const turnScore = (data.evaluation && data.evaluation.overall_wellness !== undefined) ? data.evaluation.overall_wellness : data.overall_wellness;
        const turnState = (data.evaluation && (data.evaluation.dominant_state || data.evaluation.dominant_emotion)) || data.dominant_state;

        // Render response immediately: Arogya Newsreader caption on top, user's words italic underneath
        appendExchangeToUI(data.reply_text, finalUserSpokenText, data.audio_url, Boolean(audioToSend && data.audio_url), turnScore, turnState);
        updateHeaderScorePill(turnScore, turnState);

        // If user typed text but has auto-play active, synthesize in background without blocking text render!
        if (!audioToSend && voiceMode !== "none" && !data.audio_url) {
            synthesizeAndPlay(data.reply_text, null);
        }

        // Immediate Chat Titling
        if (data.new_title) {
            if (currentSessionTitle) currentSessionTitle.textContent = data.new_title;
            const activeTitleEl = document.querySelector(".session-item.active .session-item-title");
            if (activeTitleEl) activeTitleEl.textContent = data.new_title;
        }

        // Update telemetry and grounded evidence in drawer
        if (data.evaluation) {
            updateScorecard(data.evaluation);

            if (data.evaluation.is_crisis) {
                showCrisisAlert(data.evaluation.helplines);
            }
        }

        // Point 3: AUTOMATIC GROUNDING WHEN MENTAL HEALTH SCORE DROPS BELOW THRESHOLD
        const wellness = (data.evaluation && data.evaluation.overall_wellness !== undefined) ? data.evaluation.overall_wellness : data.overall_wellness;
        const shouldAutoGround = (wellness !== null && wellness < 65) || Boolean(data.suggest_grounding);

        if (shouldAutoGround) {
            console.log(`[!] Low mental wellness score / emotional strain detected (${wellness}%). Automatically opening guided grounding breathwork modal.`);
            setTimeout(() => {
                openGroundingModal(data.grounding_mode || "box", true, wellness);
            }, 850);
        }

        await loadSessions();
        setLiveStatus("Ready", "");
        orbCaption.textContent = "Click microphone or type to reflect";
    } catch (err) {
        if (err.name === 'AbortError') {
            console.log("[*] Turn request aborted due to interruption.");
            return;
        }
        console.error("Chat error:", err);
        setLiveStatus("Ready", "");
        orbCaption.textContent = "Could not connect to Arogya. Try again.";
    } finally {
        isTurnProcessing = false;
        currentTurnAbortController = null;
    }
}

// --- CRISIS HELPLINE MODAL ---
function showCrisisAlert(helplines) {
    if (!crisisModal) return;
    crisisModal.classList.remove("hidden");
    if (helplines && helplines.length > 0 && crisisHelplineGrid) {
        crisisHelplineGrid.innerHTML = helplines.map(h => `
            <a href="tel:${h.number.replace(/[^0-9+]/g, '')}" class="helpline-badge">
                <div class="helpline-call-icon">
                    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6 19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72 12.84 12.84 0 0 0 .7 2.81 2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45 12.84 12.84 0 0 0 2.81.7A2 2 0 0 1 22 16.92z"/></svg>
                </div>
                <div class="helpline-details">
                    <span class="helpline-number tabular-num">${escapeHtml(h.number)}</span>
                    <span class="helpline-name">${escapeHtml(h.name)} - ${escapeHtml(h.desc)}</span>
                </div>
            </a>
        `).join("");
    }
}

// --- TELEMETRY GAUGES & EVIDENCE BREAKDOWN IN DRAWER ---
function updateScorecard(evalData) {
    const wellness = evalData.overall_wellness;
    if (wellnessScoreNum) {
        wellnessScoreNum.textContent = wellness !== null && wellness !== undefined ? wellness : "--";
    }

    if (confidenceBadge) {
        const conf = evalData.confidence != null ? Math.round(evalData.confidence * 100) : null;
        confidenceBadge.textContent = conf != null ? `Confidence: ${conf}%` : "Confidence: --";
    }

    if (scoreCircle) {
        if (wellness !== null && wellness !== undefined) {
            const circumference = 251.3;
            const offset = circumference - (wellness / 100) * circumference;
            scoreCircle.style.strokeDashoffset = offset;
        } else {
            scoreCircle.style.strokeDashoffset = 251.3;
        }
    }

    if (wellnessBadge) {
        if (evalData.is_crisis) {
            wellnessBadge.textContent = "Safety Alert Active";
        } else if (wellness === null || wellness === undefined) {
            wellnessBadge.textContent = "Awaiting Reflection";
        } else if (wellness >= 70) {
            wellnessBadge.textContent = "Grounded & Balanced";
        } else if (wellness >= 50) {
            wellnessBadge.textContent = "Mild Emotional Strain";
        } else if (wellness >= 35) {
            wellnessBadge.textContent = "Elevated Pressure";
        } else {
            wellnessBadge.textContent = "High Distress";
        }
    }

    if (dominantEmotion) {
        dominantEmotion.textContent = `Primary State: ${evalData.dominant_state || 'Reflective'}`;
    }

    const aggregateNote = document.getElementById("aggregateNote");
    if (aggregateNote) {
        if (evalData.note) {
            aggregateNote.textContent = evalData.note;
        } else if (evalData.total_reflections) {
            aggregateNote.textContent = `Cumulative Average (${evalData.total_reflections} reflection${evalData.total_reflections > 1 ? 's' : ''})`;
        } else {
            aggregateNote.textContent = `Cumulative Average Across Chats`;
        }
    }

    // Populate Itemized Reasons with Compiled Quotes
    if (evidenceReasonsList) {
        const reasons = evalData.reasons || [];
        if (reasons.length > 0) {
            evidenceReasonsList.innerHTML = reasons.map(r => {
                const quoteText = (r.quote || "No explicit mention across conversations").trim();
                const displayQuote = (quoteText.startsWith('"') || quoteText.startsWith('No explicit')) 
                    ? quoteText 
                    : `"${quoteText}"`;
                return `
                <div class="evidence-item">
                    <div class="evidence-header">
                        <span class="evidence-label">${escapeHtml(r.label || r.dimension || "Indicator")}</span>
                        <span class="evidence-level tabular-num">Level ${r.score}/${r.max_score || 3}</span>
                    </div>
                    <div class="evidence-track">
                        <div class="evidence-bar" style="width: ${(r.score / (r.max_score || 3)) * 100}%;"></div>
                    </div>
                    <p class="evidence-quote">${escapeHtml(displayQuote)}</p>
                </div>
            `;
            }).join("");
        } else {
            evidenceReasonsList.innerHTML = `<div style="font-size:11.5px; color:var(--text-muted); padding:8px 0;">No symptoms recorded yet.</div>`;
        }
    }

    // Voice Semitone Variation
    if (evalData.acoustic_features || evalData.voice_semitone_std !== undefined) {
        const std = evalData.voice_semitone_std !== undefined ? evalData.voice_semitone_std : (evalData.acoustic_features ? evalData.acoustic_features.pitch_semitone_std : null);
        if (semitoneVal) {
            semitoneVal.textContent = std !== null && std !== undefined ? `${std} st` : "N/A";
        }
        if (prosodyNote) {
            prosodyNote.textContent = std !== null && std !== undefined 
                ? `Session mean pitch variance (${std} st) relative to speaker median.`
                : "Text-based input or awaiting voiced speech.";
        }
    }

    if (evalData.overall_wellness !== undefined && evalData.overall_wellness !== null) {
        updateHeaderScorePill(evalData.overall_wellness, evalData.dominant_state || evalData.dominant_emotion);
    }
}

function updateHeaderScorePill(wellness, state) {
    const pill = document.getElementById("headerScorePill");
    if (!pill) return;
    if (wellness == null) {
        pill.textContent = "Awaiting Reflection";
        pill.className = "header-score-pill score-neutral";
        return;
    }
    const score = Math.round(wellness);
    const scoreClass = score >= 75 ? "score-good" : (score >= 55 ? "score-fair" : "score-low");
    const label = state || (score >= 75 ? "Balanced" : (score >= 55 ? "Strain / Fatigue" : "Elevated Distress"));
    pill.textContent = `${score}% • ${label}`;
    pill.className = `header-score-pill ${scoreClass}`;
}

function resetScorecard() {
    if (wellnessScoreNum) wellnessScoreNum.textContent = "--";
    if (confidenceBadge) confidenceBadge.textContent = "Confidence: --";
    if (scoreCircle) scoreCircle.style.strokeDashoffset = "251.3";
    if (wellnessBadge) wellnessBadge.textContent = "Awaiting Reflection";
    if (dominantEmotion) dominantEmotion.textContent = "Primary State: --";
    updateHeaderScorePill(null, null);
    const aggregateNote = document.getElementById("aggregateNote");
    if (aggregateNote) aggregateNote.textContent = "Session Average (Awaiting Input)";

    if (evidenceReasonsList) {
        evidenceReasonsList.innerHTML = `
            <div class="evidence-item">
                <div class="evidence-header">
                    <span class="evidence-label">Awaiting Initial Dialogue</span>
                    <span class="evidence-level tabular-num">Level 0/3</span>
                </div>
                <div class="evidence-track">
                    <div class="evidence-bar" style="width: 0%;"></div>
                </div>
                <p class="evidence-quote">"Speak or type to begin reflection."</p>
            </div>
        `;
    }
    if (semitoneVal) semitoneVal.textContent = "-- st";
    if (prosodyNote) prosodyNote.textContent = "Speaker-relative pitch variance normalized to self-median.";
}

function escapeHtml(text) {
    if (!text) return "";
    return text.toString()
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
}

// ==========================================================================
// PHASE 2: HANDS-FREE & GUIDED BREATHING IMPLEMENTATION
// ==========================================================================

function toggleHandsFree() {
    isHandsFree = !isHandsFree;
    const btn = document.getElementById("handsFreeToggleBtn");
    const lbl = document.getElementById("handsFreeLabel");

    if (btn) btn.classList.toggle("active", isHandsFree);
    if (lbl) lbl.textContent = isHandsFree ? "Hands-Free: ON" : "Hands-Free: OFF";

    if (isHandsFree && !isRecording) {
        orbCaption.textContent = "Hands-Free active. Speak naturally...";
        startRecording();
    } else if (!isHandsFree && isRecording) {
        stopRecording();
    }
}

function showGroundingInvite(mode = "box") {
    const pill = document.getElementById("groundingInvitePill");
    if (pill) {
        pill.classList.remove("hidden");
        pill.dataset.mode = mode;
    }
}

function openGroundingModal(mode = "box", isAutomatic = false, wellnessScore = null) {
    const modal = document.getElementById("groundingModal");
    if (modal) modal.classList.remove("hidden");

    // Pause recording during breathwork so mic doesn't record heavy breathing
    if (isRecording) {
        stopRecording();
    }

    const autoBanner = document.getElementById("automaticGroundingBanner");
    if (autoBanner) {
        if (isAutomatic) {
            autoBanner.classList.remove("hidden");
            const desc = autoBanner.querySelector(".auto-desc");
            if (desc && wellnessScore !== null) {
                desc.textContent = `Arogya noticed your mental health wellness dropped to ${wellnessScore}% (elevated emotional strain). Guiding your breath automatically to restore autonomic calm and equilibrium.`;
            } else if (desc) {
                desc.textContent = "Arogya noticed elevated emotional strain. Guiding your breath automatically to restore calm and equilibrium.";
            }
        } else {
            autoBanner.classList.add("hidden");
        }
    }

    // Play soothing gentle 432Hz entry chime
    playGroundingChime(432);
    setBreathingMode(mode);
}

function closeGroundingModal() {
    const modal = document.getElementById("groundingModal");
    if (modal) modal.classList.add("hidden");
    const autoBanner = document.getElementById("automaticGroundingBanner");
    if (autoBanner) autoBanner.classList.add("hidden");
    stopBreathing();

    // If user was in Live Voice Mode, resume listening comfortably
    if (isVoiceModalActive && !isRecording && (!audioPlayer || audioPlayer.paused)) {
        const modalState = document.getElementById("modalVoiceStateText");
        if (modalState) modalState.textContent = "Arogya is listening... speak freely";
        setTimeout(() => {
            if (isVoiceModalActive && !isRecording) {
                startRecording();
            }
        }, 600);
    }
}

function setBreathingMode(mode) {
    breathingMode = mode;
    const badge = document.getElementById("groundingModeBadge");
    const boxBtn = document.getElementById("modeBoxBtn");
    const v478Btn = document.getElementById("mode478Btn");

    if (boxBtn) boxBtn.classList.toggle("active", mode === "box");
    if (v478Btn) v478Btn.classList.toggle("active", mode === "478");

    if (badge) {
        badge.textContent = mode === "box" 
            ? "BOX 4-4-4-4 • CLINICAL RELAXATION" 
            : "VAGUS 4-7-8 • DEEP TENSION RELEASE";
    }
    startBreathing();
}

function playGroundingChime(freq = 432) {
    try {
        const ctx = new (window.AudioContext || window.webkitAudioContext)();
        const osc = ctx.createOscillator();
        const gain = ctx.createGain();
        osc.type = "sine";
        osc.frequency.setValueAtTime(freq, ctx.currentTime);
        gain.gain.setValueAtTime(0.06, ctx.currentTime);
        gain.gain.exponentialRampToValueAtTime(0.0001, ctx.currentTime + 1.2);
        osc.connect(gain);
        gain.connect(ctx.destination);
        osc.start();
        osc.stop(ctx.currentTime + 1.2);
    } catch (e) {}
}

function startBreathing() {
    stopBreathing();
    isBreathingPaused = false;
    breathingCycle = 1;

    const stage = document.querySelector(".breathing-stage");
    const instruction = document.getElementById("phaseInstruction");
    const countdown = document.getElementById("phaseCountdown");
    const cycleText = document.getElementById("cycleTrackerText");
    const toggleBtn = document.getElementById("toggleBreathingBtn");
    if (toggleBtn) toggleBtn.textContent = "Pause Breath";

    const phases = breathingMode === "box" ? [
        { name: "Inhale", class: "inhale", duration: 4, freq: 432 },
        { name: "Hold", class: "hold", duration: 4, freq: 528 },
        { name: "Exhale", class: "exhale", duration: 4, freq: 396 },
        { name: "Rest", class: "rest", duration: 4, freq: 320 }
    ] : [
        { name: "Inhale", class: "inhale", duration: 4, freq: 432 },
        { name: "Hold", class: "hold", duration: 7, freq: 528 },
        { name: "Exhale", class: "exhale", duration: 8, freq: 396 }
    ];

    let phaseIdx = 0;
    let secondsRemaining = phases[0].duration;

    function stepPhase() {
        if (isBreathingPaused) return;

        const cur = phases[phaseIdx];
        if (stage) {
            stage.className = `breathing-stage ${cur.class}`;
        }
        if (instruction) instruction.textContent = cur.name;
        if (countdown) countdown.textContent = `${secondsRemaining}s`;
        if (cycleText) cycleText.textContent = `Cycle ${breathingCycle} of 4`;

        if (secondsRemaining === cur.duration) {
            playGroundingChime(cur.freq);
        }

        secondsRemaining--;

        if (secondsRemaining < 0) {
            phaseIdx = (phaseIdx + 1) % phases.length;
            if (phaseIdx === 0) {
                breathingCycle++;
                if (breathingCycle > 4) breathingCycle = 1;
            }
            secondsRemaining = phases[phaseIdx].duration;
        }
    }

    stepPhase();
    breathingInterval = setInterval(stepPhase, 1000);
}

function toggleBreathingPause() {
    isBreathingPaused = !isBreathingPaused;
    const toggleBtn = document.getElementById("toggleBreathingBtn");
    if (toggleBtn) {
        toggleBtn.textContent = isBreathingPaused ? "Resume Breath" : "Pause Breath";
    }
}

function stopBreathing() {
    if (breathingInterval) {
        clearInterval(breathingInterval);
        breathingInterval = null;
    }
}

// --- PROGRESSIVE WEB APP (PWA) REGISTRATION & INSTALL LOGIC ---
if ('serviceWorker' in navigator) {
    const isLocalhost = Boolean(
        window.location.hostname === 'localhost' ||
        window.location.hostname === '[::1]' ||
        window.location.hostname.match(/^127(?:\.(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)){3}$/)
    );
    if (isLocalhost) {
        // Unregister service worker and clear stale caches on localhost so updates apply instantly
        navigator.serviceWorker.getRegistrations().then((registrations) => {
            for (let registration of registrations) {
                registration.unregister();
                console.log('[*] Arogya dev: Unregistered service worker on localhost');
            }
        });
        if ('caches' in window) {
            caches.keys().then((names) => {
                for (let name of names) caches.delete(name);
            });
        }
    } else {
        window.addEventListener('load', () => {
            navigator.serviceWorker.register('/sw.js')
                .then((registration) => {
                    console.log('[*] Arogya Service Worker registered with scope:', registration.scope);
                    registration.update();
                })
                .catch((err) => {
                    console.warn('[!] Arogya Service Worker registration error:', err);
                });
        });
    }
}

let deferredPwaPrompt = null;
window.addEventListener('beforeinstallprompt', (e) => {
    e.preventDefault();
    deferredPwaPrompt = e;
    console.log('[*] Arogya PWA: Native install prompt captured');
    const installBtn = document.getElementById('installPwaBtn');
    if (installBtn) {
        installBtn.classList.remove('hidden');
    }
    const menuInstall = document.getElementById('menuInstallAppBtn');
    if (menuInstall) {
        menuInstall.classList.remove('hidden');
    }
});

const installPwaBtn = document.getElementById('installPwaBtn');
if (installPwaBtn) {
    installPwaBtn.addEventListener('click', async () => {
        if (deferredPwaPrompt) {
            deferredPwaPrompt.prompt();
            const { outcome } = await deferredPwaPrompt.userChoice;
            console.log('[*] Arogya PWA install user outcome:', outcome);
            if (outcome === 'accepted') {
                installPwaBtn.classList.add('hidden');
            }
            deferredPwaPrompt = null;
        } else {
            alert("To install Arogya:\n• On Chrome/Edge: Click the install icon in the address bar.\n• On iOS Safari: Tap Share -> 'Add to Home Screen'.\n• On Android: Tap menu -> 'Install App'.");
        }
    });
}

window.addEventListener('appinstalled', () => {
    console.log('[*] Arogya successfully installed as Standalone App');
    const installBtn = document.getElementById('installPwaBtn');
    if (installBtn) installBtn.classList.add('hidden');
});

// ---------------------------------------------------------------------------
// STANDARDIZED CLINICAL SCREENING MODAL (PHQ-9 & GAD-7)
// ---------------------------------------------------------------------------
let activeClinicalTab = "phq9";
let clinicalQuestionsCache = null;

const clinicalModal = document.getElementById("clinicalAssessmentModal");
const openClinicalBtn = document.getElementById("openClinicalModalBtn");
const closeClinicalBtn = document.getElementById("closeClinicalModalBtn");
const clinicalBackdrop = document.getElementById("clinicalModalBackdrop");
const tabPhq9Btn = document.getElementById("tabPhq9Btn");
const tabGad7Btn = document.getElementById("tabGad7Btn");
const questionsContainer = document.getElementById("clinicalQuestionsContainer");
const submitAssessmentBtn = document.getElementById("submitAssessmentBtn");
const clinicalResultBox = document.getElementById("clinicalResultBox");

function openClinicalModal() {
    if (clinicalModal) clinicalModal.classList.remove("hidden");
    if (!clinicalQuestionsCache) {
        loadClinicalQuestions();
    } else {
        renderClinicalQuestions();
    }
}

function closeClinicalModal() {
    if (clinicalModal) clinicalModal.classList.add("hidden");
}

if (openClinicalBtn) openClinicalBtn.addEventListener("click", openClinicalModal);
if (closeClinicalBtn) closeClinicalBtn.addEventListener("click", closeClinicalModal);
if (clinicalBackdrop) clinicalBackdrop.addEventListener("click", closeClinicalModal);

if (tabPhq9Btn) {
    tabPhq9Btn.addEventListener("click", () => {
        activeClinicalTab = "phq9";
        tabPhq9Btn.classList.add("active");
        tabPhq9Btn.style.background = "rgba(56,189,248,0.15)";
        tabPhq9Btn.style.borderColor = "rgba(56,189,248,0.4)";
        tabPhq9Btn.style.color = "#38bdf8";
        if (tabGad7Btn) {
            tabGad7Btn.classList.remove("active");
            tabGad7Btn.style.background = "transparent";
            tabGad7Btn.style.borderColor = "rgba(255,255,255,0.1)";
            tabGad7Btn.style.color = "#94a3b8";
        }
        if (clinicalResultBox) clinicalResultBox.classList.add("hidden");
        renderClinicalQuestions();
    });
}

if (tabGad7Btn) {
    tabGad7Btn.addEventListener("click", () => {
        activeClinicalTab = "gad7";
        tabGad7Btn.classList.add("active");
        tabGad7Btn.style.background = "rgba(56,189,248,0.15)";
        tabGad7Btn.style.borderColor = "rgba(56,189,248,0.4)";
        tabGad7Btn.style.color = "#38bdf8";
        if (tabPhq9Btn) {
            tabPhq9Btn.classList.remove("active");
            tabPhq9Btn.style.background = "transparent";
            tabPhq9Btn.style.borderColor = "rgba(255,255,255,0.1)";
            tabPhq9Btn.style.color = "#94a3b8";
        }
        if (clinicalResultBox) clinicalResultBox.classList.add("hidden");
        renderClinicalQuestions();
    });
}

async function loadClinicalQuestions() {
    try {
        const res = await apiFetch("/api/clinical/questions");
        if (res.ok) {
            clinicalQuestionsCache = await res.json();
            renderClinicalQuestions();
        }
    } catch (e) {
        console.warn("Could not load clinical questions:", e);
    }
}

function renderClinicalQuestions() {
    if (!questionsContainer || !clinicalQuestionsCache) return;
    const data = clinicalQuestionsCache[activeClinicalTab];
    if (!data) return;

    const questions = data.questions || [];
    const scale = data.scale || [
        { score: 0, label: "Not at all" },
        { score: 1, label: "Several days" },
        { score: 2, label: "More than half the days" },
        { score: 3, label: "Nearly every day" }
    ];

    let html = `<p style="font-size: 0.85rem; color: #94a3b8; margin-bottom: 1rem; line-height: 1.4;">${data.description}</p>`;
    
    questions.forEach((q, idx) => {
        html += `
            <div class="clinical-question-item" style="margin-bottom: 1.25rem; padding-bottom: 1.25rem; border-bottom: 1px solid rgba(255,255,255,0.06);">
                <div style="font-size: 0.88rem; font-weight: 600; color: #f1f5f9; margin-bottom: 0.6rem;">
                    ${idx + 1}. ${escapeHtml(q.text)}
                </div>
                <div style="display: grid; grid-template-columns: repeat(4, 1fr); gap: 6px;">
                    ${scale.map(s => `
                        <label style="display: flex; flex-direction: column; align-items: center; justify-content: center; text-align: center; background: rgba(255,255,255,0.03); border: 1px solid rgba(255,255,255,0.08); padding: 8px 4px; border-radius: 6px; cursor: pointer; transition: all 0.15s ease;">
                            <input type="radio" name="q_${q.id}" value="${s.score}" ${s.score === 0 ? "checked" : ""} style="margin-bottom: 4px;">
                            <span style="font-size: 0.72rem; color: #cbd5e1; line-height: 1.2;">${s.label}</span>
                        </label>
                    `).join("")}
                </div>
            </div>
        `;
    });

    questionsContainer.innerHTML = html;
}

if (submitAssessmentBtn) {
    submitAssessmentBtn.addEventListener("click", async () => {
        if (!clinicalQuestionsCache) return;
        const data = clinicalQuestionsCache[activeClinicalTab];
        if (!data) return;

        const answers = {};
        data.questions.forEach(q => {
            const selected = document.querySelector(`input[name="q_${q.id}"]:checked`);
            answers[q.id] = selected ? parseInt(selected.value, 10) : 0;
        });

        submitAssessmentBtn.disabled = true;
        submitAssessmentBtn.textContent = "Calculating...";

        try {
            const res = await apiFetch("/api/clinical/assessment", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    assessment_type: activeClinicalTab,
                    answers: answers,
                    session_id: currentSessionId
                })
            });

            if (res.ok) {
                const result = await res.json();
                if (clinicalResultBox) {
                    clinicalResultBox.classList.remove("hidden");
                    const severityClass = result.total_score >= 15 ? "color: #f87171;" : (result.total_score >= 10 ? "color: #fbbf24;" : "color: #4ade80;");
                    clinicalResultBox.innerHTML = `
                        <div style="display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 0.5rem;">
                            <span style="font-weight: 700; font-size: 0.95rem; color: #f8fafc;">${result.assessment} Score: ${result.total_score} / ${result.max_score}</span>
                            <span style="font-weight: 700; font-size: 0.85rem; text-transform: uppercase; ${severityClass}">${result.severity}</span>
                        </div>
                        <p style="font-size: 0.82rem; color: #cbd5e1; line-height: 1.4; margin-bottom: 0.5rem;">${escapeHtml(result.clinical_action)}</p>
                        ${result.is_crisis ? `
                            <div style="background: rgba(239,68,68,0.15); border: 1px solid #ef4444; padding: 8px; border-radius: 6px; font-size: 0.8rem; color: #fca5a5; margin-top: 6px;">
                                <strong>Safety Notice:</strong> An affirmative response was noted. Please connect with Tele-MANAS (14416) or a healthcare professional.
                            </div>
                        ` : ''}
                    `;
                }
            }
        } catch (err) {
            console.error("Clinical submit error:", err);
        } finally {
            submitAssessmentBtn.disabled = false;
            submitAssessmentBtn.textContent = "Calculate Score";
        }
    });
}

// ==========================================================================
// CONSOLIDATED TOP-RIGHT HEADER DROPDOWN MENU CONTROLLER
// ==========================================================================
function initHeaderDropdownMenu() {
    const menuBtn = document.getElementById("headerMoreMenuBtn");
    const dropdown = document.getElementById("headerDropdownMenu");

    if (menuBtn && dropdown) {
        const toggleDropdown = (e) => {
            if (e) {
                e.preventDefault();
                e.stopPropagation();
            }
            dropdown.classList.toggle("hidden");
        };

        // Instant zero-delay touch and mouse responsiveness
        menuBtn.addEventListener("pointerdown", (e) => {
            e.stopPropagation();
        });

        menuBtn.addEventListener("click", toggleDropdown);

        const handleOutsideDismiss = (e) => {
            if (!dropdown.classList.contains("hidden")) {
                if (!dropdown.contains(e.target) && e.target !== menuBtn && !menuBtn.contains(e.target)) {
                    dropdown.classList.add("hidden");
                }
            }
        };

        document.addEventListener("pointerdown", handleOutsideDismiss);
        document.addEventListener("click", handleOutsideDismiss);
    }

    const menuClinicalBtn = document.getElementById("menuClinicalBtn");
    if (menuClinicalBtn) {
        menuClinicalBtn.addEventListener("click", () => {
            if (dropdown) dropdown.classList.add("hidden");
            openClinicalModal();
        });
    }

    const menuDoctorReportBtn = document.getElementById("menuDoctorReportBtn");
    if (menuDoctorReportBtn) {
        menuDoctorReportBtn.addEventListener("click", () => {
            if (dropdown) dropdown.classList.add("hidden");
        });
    }

    const menuAnalyticsBtn = document.getElementById("menuAnalyticsBtn");
    if (menuAnalyticsBtn) {
        menuAnalyticsBtn.addEventListener("click", () => {
            if (dropdown) dropdown.classList.add("hidden");
        });
    }

    const menuInsightsBtn = document.getElementById("menuInsightsBtn");
    if (menuInsightsBtn) {
        menuInsightsBtn.addEventListener("click", () => {
            if (dropdown) dropdown.classList.add("hidden");
            if (insightsDrawer) {
                insightsDrawer.classList.toggle("open");
                if (insightsDrawer.classList.contains("open")) {
                    loadDrawerInsights();
                }
            }
        });
    }

    const menuVoiceSelectorBtn = document.getElementById("menuVoiceSelectorBtn");
    if (menuVoiceSelectorBtn) {
        menuVoiceSelectorBtn.addEventListener("click", () => {
            if (dropdown) dropdown.classList.add("hidden");
            if (typeof window.openVoiceSelectorModal === "function") {
                window.openVoiceSelectorModal();
            } else {
                const modal = document.getElementById("voiceSelectorModal");
                if (modal) modal.classList.remove("hidden");
            }
        });
    }

    // Companion Name Customization Modal & State
    const menuCompanionNameBtn = document.getElementById("menuCompanionNameBtn");
    const companionNameModal = document.getElementById("companionNameModal");
    const companionModalBackdrop = document.getElementById("companionModalBackdrop");
    const closeCompanionModalBtn = document.getElementById("closeCompanionModalBtn");
    const cancelCompanionModalBtn = document.getElementById("cancelCompanionModalBtn");
    const saveCompanionModalBtn = document.getElementById("saveCompanionModalBtn");
    const companionNameInput = document.getElementById("companionNameInput");
    const menuCompanionNameLabel = document.getElementById("menuCompanionNameLabel");

    async function loadCompanionName() {
        try {
            const res = await fetch("/api/user/companion-name");
            if (res.ok) {
                const data = await res.json();
                const name = data.companion_name || "Arogya";
                if (companionNameInput) companionNameInput.value = name;
                if (menuCompanionNameLabel) menuCompanionNameLabel.textContent = `Companion: ${name}`;
                window.currentCompanionName = name;
            }
        } catch (e) {
            console.warn("Could not load companion name:", e);
        }
    }

    if (menuCompanionNameBtn && companionNameModal) {
        menuCompanionNameBtn.addEventListener("click", () => {
            if (dropdown) dropdown.classList.add("hidden");
            loadCompanionName();
            companionNameModal.classList.remove("hidden");
            if (companionNameInput) setTimeout(() => companionNameInput.focus(), 100);
        });
    }

    const closeCompModal = () => {
        if (companionNameModal) companionNameModal.classList.add("hidden");
    };

    if (closeCompanionModalBtn) closeCompanionModalBtn.addEventListener("click", closeCompModal);
    if (cancelCompanionModalBtn) cancelCompanionModalBtn.addEventListener("click", closeCompModal);
    if (companionModalBackdrop) companionModalBackdrop.addEventListener("click", closeCompModal);

    if (saveCompanionModalBtn && companionNameInput) {
        saveCompanionModalBtn.addEventListener("click", async () => {
            const newName = companionNameInput.value.trim();
            if (!newName) return;
            saveCompanionModalBtn.textContent = "Saving...";
            try {
                const res = await fetch("/api/user/companion-name", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ companion_name: newName })
                });
                if (res.ok) {
                    const data = await res.json();
                    const saved = data.companion_name || newName;
                    if (menuCompanionNameLabel) menuCompanionNameLabel.textContent = `Companion: ${saved}`;
                    window.currentCompanionName = saved;
                    closeCompModal();
                }
            } catch (e) {
                console.error("Failed to save companion name:", e);
            } finally {
                saveCompanionModalBtn.textContent = "Save Name";
            }
        });
    }

    loadCompanionName();

    const menuThemeBtn = document.getElementById("menuThemeBtn");
    if (menuThemeBtn) {
        menuThemeBtn.addEventListener("click", () => {
            if (dropdown) dropdown.classList.add("hidden");
            const current = document.documentElement.getAttribute("data-theme") || "dark";
            const next = current === "dark" ? "light" : "dark";
            setTheme(next);
            const desc = document.getElementById("menuThemeDesc");
            if (desc) desc.textContent = next === "dark" ? "Switch to Light Theme" : "Switch to Dark Theme";
        });
    }

    const menuInstallAppBtn = document.getElementById("menuInstallAppBtn");
    if (menuInstallAppBtn) {
        menuInstallAppBtn.addEventListener("click", () => {
            if (dropdown) dropdown.classList.add("hidden");
            const installBtn = document.getElementById("installPwaBtn");
            if (installBtn) installBtn.click();
        });
    }
}

