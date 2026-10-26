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
let activeVisualizerSource = null;
let lastRecordedBlob = null;
let speechRecognizer = null;
let recognizedTranscript = "";

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

// Phase 2: Hands-Free & Grounding Breathing State
let isHandsFree = false;
let vadSilenceTimer = null;
let vadHasSpoken = false;
let breathingInterval = null;
let breathingMode = "box";
let breathingCycle = 1;
let isBreathingPaused = false;

// ChatGPT-Style Continuous Voice Dialogue & Spectacular Visualizer State
let isVoiceModalActive = false;
let voiceToneCentroid = 200;
let currentAiReplyText = "";
let currentSpeakingFace = "happy";

// ESP32 Microcontroller Synchronizer (Non-blocking, cloud-safe)
function notifyEsp32SpeechState(state, face = null) {
    fetch("/api/esp32/speech_state", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ state: state, face: face })
    }).catch(() => {});
}

function notifyEsp32Emotion(face) {
    fetch("/api/esp32/emotion", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ face: face })
    }).catch(() => {});
}

// Auth State Variables
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
    initCanvasVisualizer();
    setupAudioPlayerEvents();
    await initMicDeviceSelector();
    await initAuth();

    if (currentUser) {
        updateAuthUI(true, currentUser);
    } else {
        updateAuthUI(false, null);
    }

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
            } else {
                currentUser = null;
                localStorage.removeItem("arogya_active_user");
                localStorage.removeItem("arogya_session_token");
                updateAuthUI(false, null);
            }
        } else if (meRes.status === 401) {
            currentUser = null;
            localStorage.removeItem("arogya_active_user");
            localStorage.removeItem("arogya_session_token");
            updateAuthUI(false, null);
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
        if (sidebarUserAvatar) sidebarUserAvatar.textContent = initial;
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
        if (sidebarUserName) sidebarUserName.textContent = "Guest";
        if (sidebarUserAvatar) sidebarUserAvatar.textContent = "G";
        if (sidebarUserEmail) sidebarUserEmail.textContent = "Sign in to persist chats";
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
                updateAuthUI(false, null);
                window.location.href = "/login";
            } catch (e) {
                console.warn("Logout notice:", e);
                localStorage.removeItem("arogya_active_user");
                localStorage.removeItem("arogya_session_token");
                window.location.href = "/login";
            }
        });
    }

    // Sidebar auth button
    if (sidebarAuthBtn) {
        sidebarAuthBtn.addEventListener("click", () => {
            if (currentUser) {
                if (userProfilePopup) userProfilePopup.classList.toggle("hidden");
            } else {
                window.location.href = "/login";
            }
        });
    }

    // Sidebar auth button
    if (sidebarAuthBtn) {
        sidebarAuthBtn.addEventListener("click", () => {
            if (currentUser) {
                if (userProfilePopup) userProfilePopup.classList.toggle("hidden");
            } else {
                openLoginGate(false);
            }
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

    function openMobileSidebar() {
        if (sidebar) sidebar.classList.add("mobile-open");
        if (sidebarBackdrop) sidebarBackdrop.classList.remove("hidden");
    }

    function closeMobileSidebar() {
        if (sidebar) sidebar.classList.remove("mobile-open");
        if (sidebarBackdrop) sidebarBackdrop.classList.add("hidden");
    }

    if (mobileMenuBtn) mobileMenuBtn.addEventListener("click", openMobileSidebar);
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

// --- CHATGPT-STYLE LIVE VOICE MODE CONTROLS ---
function initVoiceModeControls() {
    const openVoiceModeBtn = document.getElementById("openVoiceModeBtn");
    if (openVoiceModeBtn) {
        openVoiceModeBtn.addEventListener("click", enterVoiceMode);
    }

    const modalMinimizeBtn = document.getElementById("modalMinimizeBtn");
    if (modalMinimizeBtn) {
        modalMinimizeBtn.addEventListener("click", exitVoiceMode);
    }

    const modalMicToggleBtn = document.getElementById("modalMicToggleBtn");
    if (modalMicToggleBtn) {
        modalMicToggleBtn.addEventListener("click", () => {
            if (isRecording) {
                stopRecording();
            } else {
                startRecording();
            }
        });
    }

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
}

function enterVoiceMode() {
    isVoiceModalActive = true;
    const modal = document.getElementById("chatgptVoiceModal");
    if (modal) modal.classList.remove("hidden");

    const inlineStage = document.getElementById("inlineVoiceStage");
    if (inlineStage) inlineStage.classList.add("hidden");

    const modalState = document.getElementById("modalVoiceStateText");
    if (modalState) modalState.textContent = "Arogya is listening... speak freely";

    const userText = document.getElementById("modalUserLiveText");
    if (userText) userText.textContent = "Listening to your voice...";

    const aiText = document.getElementById("modalAiLiveText");
    if (aiText) aiText.textContent = "";

    const orbWrap = document.getElementById("voiceOrbWrapper");
    if (orbWrap) {
        orbWrap.classList.remove("speaking");
        orbWrap.classList.add("listening");
    }

    const modalMic = document.getElementById("modalMicToggleBtn");
    if (modalMic) modalMic.classList.add("recording");

    if (!isRecording) {
        startRecording();
    }
}

function exitVoiceMode() {
    if (animFrameId) {
        cancelAnimationFrame(animFrameId);
        animFrameId = null;
    }
    if (activeVisualizerSource) {
        try { activeVisualizerSource.disconnect(); } catch(e){}
        activeVisualizerSource = null;
    }
    isVoiceModalActive = false;
    const modal = document.getElementById("chatgptVoiceModal");
    if (modal) modal.classList.add("hidden");
    drawIdleWaveform();
    const inlineStage = document.getElementById("inlineVoiceStage");
    if (inlineStage) {
        if (isRecording) inlineStage.classList.remove("hidden");
        else inlineStage.classList.add("hidden");
    }
    // Always sync complete conversation history into main chat stream
    if (currentSessionId) {
        loadSessionData(currentSessionId);
    }
}

async function endVoiceConversation() {
    console.log("[*] Ending Voice Conversation Session...");
    exitVoiceMode();

    if (isRecording) {
        stopRecording();
    }
    if (audioPlayer) {
        audioPlayer.pause();
        audioPlayer.currentTime = 0;
    }

    // Refresh and list out the complete conversation in the main view
    if (currentSessionId) {
        await loadSessionData(currentSessionId);
        await loadSessions();
    }

    if (orbCaption) orbCaption.textContent = "Conversation completed. All exchanges listed below.";
    setLiveStatus("Completed", "");
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

        let preferredId = localStorage.getItem("preferred_mic_id") || "";
        let autoSelectedId = "";

        audioInputs.forEach((dev, idx) => {
            const label = dev.label || `Microphone ${idx + 1}`;
            const lowerLabel = label.toLowerCase();

            const isVirtual = lowerLabel.includes("nahimic") || lowerLabel.includes("virtual") || lowerLabel.includes("stereo mix") || lowerLabel.includes("loopback");
            const isPhysical = lowerLabel.includes("realtek") || lowerLabel.includes("array") || lowerLabel.includes("headset") || lowerLabel.includes("usb") || lowerLabel.includes("microphone");

            const opt = document.createElement("option");
            opt.value = dev.deviceId;
            opt.textContent = label + (isVirtual ? " (Virtual)" : "");

            if (!autoSelectedId && isPhysical && !isVirtual) {
                autoSelectedId = dev.deviceId;
            }

            micDeviceSelect.appendChild(opt);
        });

        const targetId = preferredId || autoSelectedId;
        if (targetId && Array.from(micDeviceSelect.options).some(o => o.value === targetId)) {
            micDeviceSelect.value = targetId;
        }

        micDeviceSelect.addEventListener("change", () => {
            localStorage.setItem("preferred_mic_id", micDeviceSelect.value);
            console.log("[*] Preferred microphone set to:", micDeviceSelect.options[micDeviceSelect.selectedIndex]?.text);
        });
    } catch (err) {
        console.warn("Could not enumerate audio devices:", err);
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

// --- SPECTACULAR SOUND & TONE AUDIO VISUALIZER (OPTIMIZED 60 FPS CAP) ---
function startVisualizer(stream) {
    if (animFrameId) {
        cancelAnimationFrame(animFrameId);
        animFrameId = null;
    }
    if (activeVisualizerSource) {
        try { activeVisualizerSource.disconnect(); } catch(e){}
        activeVisualizerSource = null;
    }
    if (!audioContext) {
        audioContext = new (window.AudioContext || window.webkitAudioContext)();
    }
    if (audioContext.state === "suspended") {
        audioContext.resume();
    }
    const source = audioContext.createMediaStreamSource(stream);
    activeVisualizerSource = source;
    analyser = audioContext.createAnalyser();
    analyser.fftSize = 256;
    analyser.smoothingTimeConstant = 0.8;
    source.connect(analyser);

    const bufferLength = analyser.frequencyBinCount;
    const freqData = new Uint8Array(bufferLength);
    const timeData = new Uint8Array(bufferLength);

    const orbCanvas = document.getElementById("voiceOrbCanvas");
    const orbCtx = orbCanvas ? orbCanvas.getContext("2d") : null;

    const inlineCanvas = document.getElementById("inlineWaveCanvas");
    const inlineCtx = inlineCanvas ? inlineCanvas.getContext("2d") : null;

    // Cache DOM references once to avoid layout thrashing across animation frames
    const ribbonTonePill = document.getElementById("voiceTonePill");
    const modalToneBadge = document.getElementById("modalToneBadge");
    const inlineToneBadge = document.getElementById("inlineVoiceToneText");
    const inlineGlow = document.getElementById("inlineOrbGlow");
    const centerBadge = document.getElementById("voiceOrbCenterBadge");
    const inlineVoiceStage = document.getElementById("inlineVoiceStage");
    const modalStateText = document.getElementById("modalVoiceStateText");
    const orbWrap = document.getElementById("voiceOrbWrapper");

    let rotationAngle = 0;
    let lastRenderTime = 0;
    let lastDomUpdateTime = 0;

    function render(timestamp) {
        if (!isRecording && (!audioPlayer || audioPlayer.paused)) {
            if (animFrameId) {
                clearTimeout(animFrameId);
                cancelAnimationFrame(animFrameId);
                animFrameId = null;
            }
            drawIdleWaveform();
            return;
        }

        // Strict 30 FPS Hardware Limiter decoupled from 144Hz monitors to prevent GPU overheating
        const TARGET_FPS = 30;
        const MIN_FRAME_INTERVAL = 1000 / TARGET_FPS; // 33.3ms
        if (timestamp) {
            if (!lastRenderTime) lastRenderTime = timestamp;
            const elapsed = timestamp - lastRenderTime;
            if (elapsed < MIN_FRAME_INTERVAL) {
                animFrameId = setTimeout(() => {
                    requestAnimationFrame(render);
                }, MIN_FRAME_INTERVAL - elapsed);
                return;
            }
            lastRenderTime = timestamp;
        }
        animFrameId = setTimeout(() => {
            requestAnimationFrame(render);
        }, MIN_FRAME_INTERVAL);

        analyser.getByteFrequencyData(freqData);
        analyser.getByteTimeDomainData(timeData);

        // 1. Calculate RMS Volume (Energy) & Focused Vocal Band Energy
        let sum = 0;
        let vocalSum = 0;
        let weightedFreqSum = 0;
        let totalFreqWeight = 0;
        const vocalBinsCount = Math.min(22, bufferLength); // Primary human vocal frequency band (< 3.2 kHz)

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
        }
        const avg = sum / bufferLength;
        const vocalAvg = vocalSum / vocalBinsCount;
        // Vocal percent accurately tracks speech on boAt headsets and laptop mic arrays
        const vocalPercent = Math.min(100, Math.round((vocalAvg / 40) * 100));
        const percent = Math.min(100, Math.max(vocalPercent, Math.round((avg / 60) * 100)));

        // 2. Estimate Spectral Centroid & Vocal Tone / Pitch
        if (totalFreqWeight > 0) {
            const centroidBin = weightedFreqSum / totalFreqWeight;
            const nyquist = (audioContext.sampleRate || 16000) / 2;
            voiceToneCentroid = Math.round((centroidBin / bufferLength) * nyquist);
        }

        // Determine Tone & Chromatic Color Palette (Descriptive labels without confusing Hz numbers)
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
        } else {
            toneLabel = "Calm & Steady";
            toneClass = "tone-calm";
            toneColor = "#38bdf8"; // Cyan
            glowColor = "rgba(56, 189, 248, 0.45)";
            secondaryColor = "#2dd4bf"; // Teal
        }

        // Throttled DOM Telemetry Updates (10 FPS / 100ms throttle to prevent layout recalculations)
        const now = performance.now();
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

            if (centerBadge && isVoiceModalActive) {
                const scaleVal = 1 + (percent / 200);
                centerBadge.style.transform = `scale(${scaleVal})`;
                centerBadge.style.boxShadow = `0 0 ${16 + percent * 0.7}px ${toneColor}88`;
            }
        }

        // 3. ChatGPT-Style Barge-In / Interruption Detection
        if (audioPlayer && !audioPlayer.paused && audioPlayer.currentTime > 0) {
            if (vocalPercent > 16) {
                console.log("[*] Barge-in detected: User interrupted Arogya!");
                audioPlayer.pause();
                audioPlayer.currentTime = 0;
                setLiveStatus("Listening...", "listening");
                orbCaption.textContent = "You spoke — Arogya paused to listen to you";
                if (modalStateText) modalStateText.textContent = "Arogya paused • Listening to you...";
                if (orbWrap) {
                    orbWrap.classList.remove("speaking");
                    orbWrap.classList.add("listening");
                }
            }
        }

        // 4. Conversational Voice Activity Detection (VAD) & Natural Pause Pacing
        if (isRecording) {
            const hasRecognizedWords = Boolean(recognizedTranscript.trim().length > 0 || (textInput && textInput.value.trim().length > 0));
            
            // Speech active: vocalPercent >= 8 for 3 frames OR recognized words
            if (vocalPercent >= 8 || hasRecognizedWords) {
                vadVoicedFrameCount = (typeof vadVoicedFrameCount !== "undefined" ? vadVoicedFrameCount : 0) + 1;
                if (vadVoicedFrameCount >= 3 || hasRecognizedWords) {
                    vadHasSpoken = true;
                }
                if (vadSilenceTimer) {
                    clearTimeout(vadSilenceTimer);
                    vadSilenceTimer = null;
                }
            } else if (vocalPercent < 6) {
                if (typeof vadVoicedFrameCount !== "undefined") {
                    vadVoicedFrameCount = Math.max(0, vadVoicedFrameCount - 1);
                }
                if (vadHasSpoken) {
                    if (!vadSilenceTimer) {
                        // Natural 2.0s conversational pause window allows thoughtful, slow-cadence speech without premature cutoffs
                        vadSilenceTimer = setTimeout(() => {
                            if (isRecording && vadHasSpoken) {
                                vadHasSpoken = false;
                                vadVoicedFrameCount = 0;
                                stopRecording();
                            }
                        }, 2000);
                    }
                }
            }
        }

        // 5. Render Ribbon Canvas Waveform (Sound & Tone Responsive)
        // Guarded: only render if waveformCanvas is attached and visible
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

        // 6. Render Full-Screen ChatGPT Voice Orb (Spectacular Liquid Aura + Breathing Harmonic Rings)
        // Guarded: only render when Voice Modal is ACTIVE to save 90% GPU rasterization
        if (isVoiceModalActive && orbCtx && orbCanvas) {
            orbCtx.clearRect(0, 0, orbCanvas.width, orbCanvas.height);
            const cx = orbCanvas.width / 2;
            const cy = orbCanvas.height / 2;

            // Ambient organic breathing oscillation so it feels alive even during silence
            const breath = Math.sin(Date.now() / 360) * 5;
            const baseRadius = 60 + breath + (avg * 0.75);

            rotationAngle += 0.02 + (avg * 0.001);

            // Radiant Bloom Glow
            const radialGrad = orbCtx.createRadialGradient(cx, cy, baseRadius * 0.25, cx, cy, baseRadius * 1.85);
            radialGrad.addColorStop(0, glowColor);
            radialGrad.addColorStop(0.5, glowColor.replace("0.5", "0.2").replace("0.55", "0.2"));
            radialGrad.addColorStop(1, "transparent");

            orbCtx.fillStyle = radialGrad;
            orbCtx.beginPath();
            orbCtx.arc(cx, cy, baseRadius * 1.85, 0, Math.PI * 2);
            orbCtx.fill();

            // Concentric Sine-Warped Harmonic Rings (Driven by Volume & Frequency)
            for (let ring = 1; ring <= 4; ring++) {
                const ringRadius = baseRadius + (ring * 16 * (avg / 35 + 0.35));
                orbCtx.beginPath();
                orbCtx.lineWidth = ring === 1 ? 2.5 : 1.8;
                orbCtx.strokeStyle = ring % 2 === 0 ? secondaryColor : toneColor;
                orbCtx.globalAlpha = Math.max(0.2, 0.9 / ring);

                const points = 48;
                for (let p = 0; p <= points; p++) {
                    const theta = (p / points) * Math.PI * 2 + (ring * 0.4 * (ring % 2 === 0 ? 1 : -1) * rotationAngle);
                    const harmonicIndex = Math.floor((p / points) * (bufferLength / 2));
                    const freqWarp = (freqData[harmonicIndex] / 255.0) * 22 * (1 / ring);
                    const r = ringRadius + Math.sin(theta * (ring + 2) + rotationAngle * 3.2) * (5 + freqWarp);
                    const px = cx + Math.cos(theta) * r;
                    const py = cy + Math.sin(theta) * r;

                    if (p === 0) orbCtx.moveTo(px, py);
                    else orbCtx.lineTo(px, py);
                }
                orbCtx.closePath();
                orbCtx.stroke();
            }

            // Orbiting Acoustic Spark Particles
            const particleCount = 8;
            for (let pt = 0; pt < particleCount; pt++) {
                const ptAngle = rotationAngle * (1.2 + pt * 0.1) + (pt * (Math.PI * 2 / particleCount));
                const ptDist = baseRadius * 1.35 + Math.sin(ptAngle * 3) * (8 + avg * 0.25);
                const ptx = cx + Math.cos(ptAngle) * ptDist;
                const pty = cy + Math.sin(ptAngle) * ptDist;
                const ptRadius = 2.2 + (avg / 25);

                orbCtx.beginPath();
                orbCtx.fillStyle = toneColor;
                orbCtx.globalAlpha = 0.75;
                orbCtx.arc(ptx, pty, ptRadius, 0, Math.PI * 2);
                orbCtx.fill();
            }

            orbCtx.globalAlpha = 1.0;
        }

        // 7. Render Inline Audio Canvas (Active in Chat Stream)
        // Guarded: only render when modal is NOT active AND inline voice stage is visible
        if (!isVoiceModalActive && inlineCtx && inlineCanvas && inlineVoiceStage && !inlineVoiceStage.classList.contains("hidden")) {
            inlineCtx.clearRect(0, 0, inlineCanvas.width, inlineCanvas.height);
            const w = inlineCanvas.width;
            const h = inlineCanvas.height;
            const cy = h / 2;

            // Background Spectrum Histogram Bars
            const numBars = 32;
            const barWidth = w / numBars;
            for (let b = 0; b < numBars; b++) {
                const binIdx = Math.floor(b * (bufferLength / numBars));
                const val = (freqData[binIdx] / 255.0);
                const barHeight = Math.max(3, val * (h * 0.75));
                const bx = b * barWidth;
                const by = h - barHeight;

                inlineCtx.fillStyle = toneColor;
                inlineCtx.globalAlpha = 0.15 + (val * 0.35);
                inlineCtx.fillRect(bx + 1, by, barWidth - 2, barHeight);
            }

            // Layered Flowing Fluid Sine Ribbons
            for (let layer = 1; layer <= 2; layer++) {
                inlineCtx.beginPath();
                inlineCtx.lineWidth = layer === 1 ? 2.5 : 1.5;
                inlineCtx.strokeStyle = layer === 1 ? toneColor : secondaryColor;
                inlineCtx.globalAlpha = layer === 1 ? 0.9 : 0.6;

                const step = w / 40;
                for (let x = 0; x <= w; x += step) {
                    const normX = x / w;
                    const freqIdx = Math.floor(normX * (bufferLength / 2));
                    const waveEnergy = (freqData[freqIdx] / 255.0) * (h * 0.35);
                    const breath = Math.sin((x * 0.03) + (rotationAngle * (layer * 2))) * (4 + waveEnergy);
                    const y = cy + breath;

                    if (x === 0) inlineCtx.moveTo(x, y);
                    else inlineCtx.lineTo(x, y);
                }
                inlineCtx.stroke();
            }
            inlineCtx.globalAlpha = 1.0;
        }
    }
    animFrameId = requestAnimationFrame(render);
}

function setupAudioPlayerEvents() {
    if (!audioPlayer) return;

    audioPlayer.addEventListener("play", () => {
        setLiveStatus("Speaking...", "listening");
        orbCaption.textContent = "Arogya is speaking...";

        // Notify physical ESP32 to show speaking face and start mouth movement
        notifyEsp32SpeechState(1, currentSpeakingFace);

        if (isVoiceModalActive) {
            const aiText = document.getElementById("modalAiLiveText");
            if (aiText && currentAiReplyText) aiText.textContent = currentAiReplyText;

            const modalState = document.getElementById("modalVoiceStateText");
            if (modalState) modalState.textContent = "Arogya is speaking... (tap or speak to interrupt)";

            const orbWrap = document.getElementById("voiceOrbWrapper");
            if (orbWrap) {
                orbWrap.classList.add("speaking");
                orbWrap.classList.remove("listening");
            }
        }
    });

    audioPlayer.addEventListener("ended", () => {
        if (!isRecording && animFrameId) {
            cancelAnimationFrame(animFrameId);
            animFrameId = null;
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
                if (isVoiceModalActive && !isRecording) {
                    startRecording();
                }
            }, 500);
        } else if (isHandsFree && !isRecording) {
            setTimeout(() => {
                if (isHandsFree && !isRecording) {
                    startRecording();
                }
            }, 600);
        }
    });

    audioPlayer.addEventListener("pause", () => {
        if (!isRecording && animFrameId) {
            cancelAnimationFrame(animFrameId);
            animFrameId = null;
        }
        setLiveStatus("Ready", "");
        notifyEsp32SpeechState(0);
        if (isVoiceModalActive) {
            const orbWrap = document.getElementById("voiceOrbWrapper");
            if (orbWrap) orbWrap.classList.remove("speaking");
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

        const score = s.overall_wellness || 75;
        const dateStr = new Date(s.created_at).toLocaleDateString("en-IN", { month: "short", day: "numeric" });

        item.innerHTML = `
            <div class="session-item-content">
                <span class="session-item-title">${escapeHtml(s.title || "Check-in")}</span>
                <span class="session-item-meta tabular-num">${dateStr} • ${escapeHtml(s.dominant_emotion || "Reflective")}</span>
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
        const data = await res.json();

        if (currentSessionTitle) currentSessionTitle.textContent = data.session.title || "Emotional Wellness Reflection";
        if (data.messages && data.messages.length > 0) {
            chatStream.innerHTML = "";
            renderMessageHistory(data.messages);
        } else {
            renderWelcomeCard();
            await fetchInitialGreeting();
        }

        if (data.latest_score) {
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
            appendExchangeToUI(msg.text, lastUserText, msg.audio_path, false);
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
        const res = await apiFetch(`/api/greeting?session_id=${currentSessionId}&voice_mode=${voiceMode}`);
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
function appendExchangeToUI(captionText, userSpokenWords, audioUrl, autoplay = false) {
    const pendingCard = document.getElementById("pendingUserCard");
    if (pendingCard) pendingCard.remove();
    const welcomeCard = document.getElementById("chatWelcomeCard");
    if (welcomeCard) welcomeCard.remove();

    const exchange = document.createElement("div");
    exchange.className = "conversation-exchange";

    const playBtnHtml = audioUrl ? `
        <button class="btn-caption-play" onclick="playAudio('${audioUrl}')">
            <svg width="10" height="10" viewBox="0 0 24 24" fill="currentColor"><polygon points="5 3 19 12 5 21 5 3"/></svg>
            <span>Play</span>
        </button>
    ` : "";

    const userSublineHtml = userSpokenWords ? `
        <div class="user-spoken-subline">
            <span class="user-echo-indicator">You:</span>
            <span>"${escapeHtml(userSpokenWords)}"</span>
        </div>
    ` : "";

    exchange.innerHTML = `
        <div class="arogya-caption-card">
            <div class="caption-sender-header">
                <span class="caption-sender-name">Arogya</span>
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

function playAudio(url) {
    if (!audioPlayer) return;
    audioPlayer.src = url;
    audioPlayer.play().catch(err => {
        console.warn("Autoplay notice:", err);
    });
}

function setLiveStatus(text, modeClass) {
    if (!liveStatusText || !liveStatusPill) return;
    liveStatusText.textContent = text;
    liveStatusPill.className = `live-status-pill ${modeClass || ""}`;
}

// --- RECORDING & SPEECH-TO-SPEECH ---
function initSpeechRecognition() {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (SpeechRecognition) {
        speechRecognizer = new SpeechRecognition();
        speechRecognizer.continuous = true;
        speechRecognizer.interimResults = true;
        speechRecognizer.lang = "en-IN";

        speechRecognizer.onresult = (event) => {
            let interim = "";
            for (let i = event.resultIndex; i < event.results.length; ++i) {
                if (event.results[i].isFinal) {
                    recognizedTranscript += event.results[i][0].transcript + " ";
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
            }
        };

        speechRecognizer.onerror = (e) => {
            console.warn("Speech recognition notice:", e.error);
        };
    }
}

async function toggleRecording() {
    if (isRecording) {
        stopRecording();
    } else {
        await startRecording();
    }
}

async function startRecording() {
    notifyEsp32Emotion("thinking");
    try {
        const selectedMicId = micDeviceSelect ? micDeviceSelect.value : "";
        const audioConstraints = {
            channelCount: 1,
            sampleRate: { ideal: 16000 },
            echoCancellation: true,
            noiseSuppression: true,
            autoGainControl: true
        };
        if (selectedMicId) {
            audioConstraints.deviceId = { exact: selectedMicId };
        }

        let stream;
        try {
            stream = await navigator.mediaDevices.getUserMedia({ audio: audioConstraints });
        } catch (devErr) {
            stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        }

        audioChunks = [];
        lastRecordedBlob = null;
        recognizedTranscript = "";
        if (textInput) textInput.value = "";

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
            stream.getTracks().forEach(track => track.stop());

            const currentText = textInput ? textInput.value.trim() : "";
            const isBrowserHallucination = currentText.toLowerCase().split(/\s+/).every(w => w === "you" || w === "thank");
            const finalClientText = (!isBrowserHallucination && currentText.length >= 2) ? currentText : "";

            if (lastRecordedBlob && lastRecordedBlob.size > 1500) {
                orbCaption.textContent = "Voice captured. Arogya is reflecting...";
                setLiveStatus("Reflecting...", "listening");
                if (isVoiceModalActive) {
                    const modalState = document.getElementById("modalVoiceStateText");
                    if (modalState) modalState.textContent = "Arogya is reflecting...";
                    const userLive = document.getElementById("modalUserLiveText");
                    if (userLive && finalClientText) userLive.textContent = `"${finalClientText}"`;
                }
                await handleTextSubmit(finalClientText);
                return;
            } else {
                orbCaption.textContent = "Microphone captured silence. Speak into the mic or type.";
                if (isVoiceModalActive) {
                    const modalState = document.getElementById("modalVoiceStateText");
                    if (modalState) modalState.textContent = "Silence captured. Speak again when ready.";
                }
                setLiveStatus("Ready", "");
                if (textInput) textInput.focus();
            }
        };

        if (!speechRecognizer) initSpeechRecognition();
        if (speechRecognizer) {
            try { speechRecognizer.start(); } catch(e){}
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

        orbCaption.textContent = "Listening... Speak naturally in English or Tanglish";
        setLiveStatus("Listening...", "listening");

        if (isVoiceModalActive) {
            const modalState = document.getElementById("modalVoiceStateText");
            if (modalState) modalState.textContent = "Arogya is listening... speak freely";
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
        if (micBtn) micBtn.classList.remove("recording");
        const modalMic = document.getElementById("modalMicToggleBtn");
        if (modalMic) modalMic.classList.remove("recording");

        const inlineStage = document.getElementById("inlineVoiceStage");
        if (inlineStage) inlineStage.classList.add("hidden");

        setLiveStatus("Processing...", "listening");
        orbCaption.textContent = "Processing speech...";
        if (animFrameId) {
            cancelAnimationFrame(animFrameId);
            animFrameId = null;
        }
        drawIdleWaveform();
        resetMicMeter();

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
        }, 200);
    }
}

// --- SUBMISSION: CHATGPT-SPEED RESPONSE & IMMEDIATE TITLING ---
async function handleTextSubmit(overrideText = null) {
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
    }

    try {
        let res, data;
        if (audioToSend) {
            const formData = new FormData();
            formData.append("file", audioToSend, "user_speech.webm");
            formData.append("session_id", currentSessionId);
            formData.append("voice_mode", voiceMode);
            formData.append("client_transcript", text === "Voice reflection..." ? "" : text);

            res = await apiFetch("/api/chat/voice", {
                method: "POST",
                body: formData
            });
            data = await res.json();
        } else {
            const formData = new FormData();
            formData.append("text", text);
            formData.append("session_id", currentSessionId);
            formData.append("voice_mode", voiceMode);

            res = await apiFetch("/api/chat/text", {
                method: "POST",
                body: formData
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
            const modalState = document.getElementById("modalVoiceStateText");
            if (modalState) modalState.textContent = "Arogya is speaking... (tap or speak to interrupt)";
        }

        // Render response: Arogya Newsreader caption on top, user's words italic underneath
        appendExchangeToUI(data.reply_text, finalUserSpokenText, data.audio_url, true);

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
        console.error("Chat error:", err);
        setLiveStatus("Ready", "");
        orbCaption.textContent = "Could not connect to Arogya. Try again.";
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
        const conf = Math.round((evalData.confidence || 0.5) * 100);
        confidenceBadge.textContent = `Confidence: ${conf}%`;
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
        if (wellness === null || wellness === undefined) {
            wellnessBadge.textContent = "Safety Alert Active";
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
}

function resetScorecard() {
    if (wellnessScoreNum) wellnessScoreNum.textContent = "75";
    if (confidenceBadge) confidenceBadge.textContent = "Confidence: 50%";
    if (scoreCircle) scoreCircle.style.strokeDashoffset = "62.8";
    if (wellnessBadge) wellnessBadge.textContent = "Grounded & Balanced";
    if (dominantEmotion) dominantEmotion.textContent = "Primary State: Calm";
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
    window.addEventListener('load', () => {
        navigator.serviceWorker.register('/sw.js')
            .then((registration) => {
                console.log('[*] Arogya Service Worker registered with scope:', registration.scope);
            })
            .catch((err) => {
                console.warn('[!] Arogya Service Worker registration error:', err);
            });
    });
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

