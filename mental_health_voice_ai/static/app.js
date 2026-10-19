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

// --- INITIALIZATION ---
document.addEventListener("DOMContentLoaded", async () => {
    initTheme();
    initVoiceEngine();
    initControls();
    initPhase2Controls();
    initCanvasVisualizer();
    setupAudioPlayerEvents();
    await initMicDeviceSelector();

    await loadSessions();
    // Always start a fresh new chat session on entry
    await startNewSession(true);
});

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
    const savedMode = localStorage.getItem("arogya_voice_mode") || "fast";
    setVoiceMode(savedMode);

    const fastBtn = document.getElementById("engineFastBtn");
    const clonedBtn = document.getElementById("engineClonedBtn");

    if (fastBtn) {
        fastBtn.addEventListener("click", () => setVoiceMode("fast"));
    }
    if (clonedBtn) {
        clonedBtn.addEventListener("click", () => setVoiceMode("cloned"));
    }
}

function setVoiceMode(mode) {
    voiceMode = mode;
    localStorage.setItem("arogya_voice_mode", mode);

    const fastBtn = document.getElementById("engineFastBtn");
    const clonedBtn = document.getElementById("engineClonedBtn");
    const badge = document.getElementById("currentEngineBadge");

    if (fastBtn) fastBtn.classList.toggle("active", mode === "fast");
    if (clonedBtn) clonedBtn.classList.toggle("active", mode === "cloned");
    if (badge) badge.textContent = mode === "fast" ? "INSTANT" : "CLONED";
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
        micBtn.addEventListener("click", toggleRecording);
    }

    if (sendBtn) {
        sendBtn.addEventListener("click", handleTextSubmit);
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

function startVisualizer(stream) {
    if (!audioContext) {
        audioContext = new (window.AudioContext || window.webkitAudioContext)();
    }
    if (audioContext.state === "suspended") {
        audioContext.resume();
    }
    const source = audioContext.createMediaStreamSource(stream);
    analyser = audioContext.createAnalyser();
    analyser.fftSize = 64;
    source.connect(analyser);

    const bufferLength = analyser.frequencyBinCount;
    const dataArray = new Uint8Array(bufferLength);

    function render() {
        if (!isRecording) return;
        animFrameId = requestAnimationFrame(render);
        analyser.getByteFrequencyData(dataArray);

        let sum = 0;
        for (let i = 0; i < bufferLength; i++) {
            sum += dataArray[i];
        }
        const avg = sum / bufferLength;
        const percent = Math.min(100, Math.round((avg / 100) * 100));

        if (micMeterFill) {
            micMeterFill.style.width = `${percent}%`;
        }
        if (micMeterStatus) {
            micMeterStatus.textContent = percent > 5 ? `${percent}%` : "Quiet";
        }

        // Hands-Free Conversational Voice Activity Detection (VAD)
        if (isHandsFree && isRecording) {
            if (percent > 12) {
                vadHasSpoken = true;
                if (vadSilenceTimer) {
                    clearTimeout(vadSilenceTimer);
                    vadSilenceTimer = null;
                }
            } else if (vadHasSpoken && percent <= 10) {
                if (!vadSilenceTimer) {
                    vadSilenceTimer = setTimeout(() => {
                        if (isHandsFree && isRecording && vadHasSpoken) {
                            vadHasSpoken = false;
                            stopRecording();
                        }
                    }, 1400); // 1.4s natural pause detection
                }
            }
        }

        if (canvasCtx && waveformCanvas) {
            canvasCtx.clearRect(0, 0, waveformCanvas.width, waveformCanvas.height);
            const isDark = document.documentElement.getAttribute("data-theme") !== "light";
            const barWidth = (waveformCanvas.width / bufferLength) * 1.5;
            let x = 0;

            for (let i = 0; i < bufferLength; i++) {
                const barHeight = (dataArray[i] / 255.0) * (waveformCanvas.height - 4);
                canvasCtx.fillStyle = isDark ? "#FFFFFF" : "#000000";
                canvasCtx.fillRect(x, (waveformCanvas.height - barHeight) / 2, barWidth - 1, barHeight);
                x += barWidth + 1;
            }
        }
    }
    render();
}

function setupAudioPlayerEvents() {
    if (!audioPlayer) return;

    audioPlayer.addEventListener("play", () => {
        setLiveStatus("Speaking...", "listening");
        orbCaption.textContent = "Arogya is speaking...";
    });

    audioPlayer.addEventListener("ended", () => {
        setLiveStatus("Ready", "");
        orbCaption.textContent = isHandsFree ? "Hands-Free active. Listening..." : "Click microphone or type to reflect";
        drawIdleWaveform();

        // Hands-Free Loop: automatically resume listening after Arogya finishes speaking
        if (isHandsFree && !isRecording) {
            setTimeout(() => {
                if (isHandsFree && !isRecording) {
                    startRecording();
                }
            }, 600);
        }
    });

    audioPlayer.addEventListener("pause", () => {
        setLiveStatus("Ready", "");
    });
}

// --- SESSIONS MANAGEMENT ---
async function loadSessions() {
    try {
        const res = await fetch("/api/sessions");
        const sessions = await res.json();
        renderSessionsList(sessions);
        if (sessionCountTag) {
            sessionCountTag.textContent = sessions.length;
        }
    } catch (err) {
        console.error("Failed to load sessions:", err);
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
    await loadSessionData(sessionId);
    await loadSessions();
}

async function startNewSession(triggerGreeting = true) {
    try {
        const res = await fetch("/api/sessions", { method: "POST" });
        const newSess = await res.json();
        currentSessionId = newSess.session_id;
        if (currentSessionTitle) currentSessionTitle.textContent = newSess.title;
        chatStream.innerHTML = "";
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
        const res = await fetch(`/api/sessions/${sessionId}`, {
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
        const res = await fetch(`/api/sessions/${sessionId}`, { method: "DELETE" });
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
        const res = await fetch(`/api/sessions/${sessionId}`);
        const data = await res.json();

        if (currentSessionTitle) currentSessionTitle.textContent = data.session.title || "Emotional Wellness Reflection";
        chatStream.innerHTML = "";

        if (data.messages && data.messages.length > 0) {
            renderMessageHistory(data.messages);
        } else {
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
        const res = await fetch(`/api/greeting?session_id=${currentSessionId}&voice_mode=${voiceMode}`);
        const data = await res.json();

        appendExchangeToUI(data.greeting_text, "", data.audio_url, true);
        setLiveStatus("Ready", "");
    } catch (err) {
        console.error("Error getting greeting:", err);
        setLiveStatus("Ready", "");
    }
}

// --- CONVERSATIONAL RENDERING ENGINE ---
// Strict User Typography:
// - Arogya Captions: Newsreader (300 Large & Light, Warm Human Voice)
// - Spoken Words: Newsreader Italic (Quieter Subline)
function appendExchangeToUI(captionText, userSpokenWords, audioUrl, autoplay = false) {
    const pendingCard = document.getElementById("pendingUserCard");
    if (pendingCard) pendingCard.remove();

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
    const existing = document.getElementById("pendingUserCard");
    if (existing) existing.remove();

    const card = document.createElement("div");
    card.id = "pendingUserCard";
    card.className = "conversation-exchange";
    card.innerHTML = `
        <div class="user-pending-card">
            <div class="user-spoken-subline">
                <span class="user-echo-indicator">You:</span>
                <span>"${escapeHtml(text)}"</span>
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
    try {
        const selectedMicId = micDeviceSelect ? micDeviceSelect.value : "";
        const audioConstraints = selectedMicId
            ? {
                deviceId: { exact: selectedMicId },
                channelCount: 1,
                sampleRate: 16000,
                echoCancellation: false,
                noiseSuppression: false,
                autoGainControl: true
              }
            : {
                channelCount: 1,
                sampleRate: 16000,
                echoCancellation: false,
                noiseSuppression: false,
                autoGainControl: true
              };

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

            if (!currentText || currentText.length < 2 || isBrowserHallucination) {
                if (textInput) textInput.value = "";
                orbCaption.textContent = "Transcribing speech with neural Whisper...";
                setLiveStatus("Transcribing...", "listening");

                try {
                    const formTr = new FormData();
                    formTr.append("file", lastRecordedBlob, "speech.webm");
                    const trRes = await fetch("/api/transcribe", { method: "POST", body: formTr });
                    const trData = await trRes.json();
                    const trText = (trData.transcript || "").trim();

                    if (trText.length > 1) {
                        if (textInput) textInput.value = trText;
                        orbCaption.textContent = "Speech transcribed. Click Send or press Enter.";
                        await handleTextSubmit();
                        return;
                    } else {
                        orbCaption.textContent = "Microphone captured silence. Please select physical mic or type.";
                    }
                } catch(e) {
                    console.error("Transcribe error:", e);
                    orbCaption.textContent = "Could not catch words clearly. Try speaking again.";
                }
            } else {
                orbCaption.textContent = "Speech converted. Click Send or press Enter.";
                await handleTextSubmit();
                return;
            }
            setLiveStatus("Ready", "");
            if (textInput) textInput.focus();
        };

        if (!speechRecognizer) initSpeechRecognition();
        if (speechRecognizer) {
            try { speechRecognizer.start(); } catch(e){}
        }

        mediaRecorder.start(250);
        isRecording = true;
        if (micBtn) micBtn.classList.add("recording");
        orbCaption.textContent = "Listening... Speak naturally in English or Tanglish";
        setLiveStatus("Listening...", "listening");

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
        setLiveStatus("Processing...", "listening");
        orbCaption.textContent = "Processing speech...";
        drawIdleWaveform();
        resetMicMeter();

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
async function handleTextSubmit() {
    const text = textInput ? textInput.value.trim() : "";
    if (!text) {
        orbCaption.textContent = "Please speak into the mic or type first.";
        return;
    }

    if (textInput) textInput.value = "";
    appendPendingUserToUI(text);
    setLiveStatus("Reflecting...", "listening");
    orbCaption.textContent = "Arogya is reflecting...";

    const audioToSend = lastRecordedBlob;
    lastRecordedBlob = null;

    try {
        let res, data;
        if (audioToSend) {
            const formData = new FormData();
            formData.append("file", audioToSend, "user_speech.webm");
            formData.append("session_id", currentSessionId);
            formData.append("voice_mode", voiceMode);
            formData.append("client_transcript", text);

            res = await fetch("/api/chat/voice", {
                method: "POST",
                body: formData
            });
            data = await res.json();
        } else {
            const formData = new FormData();
            formData.append("text", text);
            formData.append("session_id", currentSessionId);
            formData.append("voice_mode", voiceMode);

            res = await fetch("/api/chat/text", {
                method: "POST",
                body: formData
            });
            data = await res.json();
        }

        // Render response: Arogya Newsreader caption on top, user's words italic underneath
        appendExchangeToUI(data.reply_text, text, data.audio_url, true);

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

        // Auto-invite gentle breathing if anxiety/tension is detected
        if (data.suggest_grounding) {
            showGroundingInvite(data.grounding_mode || "box");
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

function openGroundingModal(mode = "box") {
    const modal = document.getElementById("groundingModal");
    if (modal) modal.classList.remove("hidden");
    setBreathingMode(mode);
}

function closeGroundingModal() {
    const modal = document.getElementById("groundingModal");
    if (modal) modal.classList.add("hidden");
    stopBreathing();
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

