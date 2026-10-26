/**
 * Arogya CompanionAI • Sliding Authentication Controller
 * Black & White Monochrome Sliding Interface with Real Google OAuth 2.0
 */

let googleClientId = "";
let isGoogleConfigured = false;

document.addEventListener("DOMContentLoaded", async () => {
    initSlidingControls();
    initLocalAuthControls();
    await initGoogleAuth();
    await loadExistingProfiles();
});

// --- 1. SLIDING WINDOW CONTROLS ---
function initSlidingControls() {
    const slidingCard = document.getElementById("slidingCard");
    const btnSwitchToSignUp = document.getElementById("btnSwitchToSignUp");
    const btnSwitchToLogin = document.getElementById("btnSwitchToLogin");

    // URL parameter check (e.g. /login?mode=signup or /login?action=switch)
    const urlParams = new URLSearchParams(window.location.search);
    if (urlParams.get("mode") === "signup") {
        slidingCard.classList.add("signup-active");
    }

    if (btnSwitchToSignUp) {
        btnSwitchToSignUp.addEventListener("click", () => {
            slidingCard.classList.add("signup-active");
            // Auto focus preferred name input
            setTimeout(() => {
                const nameInput = document.getElementById("signupPreferredNameInput");
                if (nameInput) nameInput.focus();
            }, 400);
        });
    }

    if (btnSwitchToLogin) {
        btnSwitchToLogin.addEventListener("click", () => {
            slidingCard.classList.remove("signup-active");
        });
    }
}

// --- 2. GOOGLE IDENTITY SERVICES INITIALIZATION ---
async function initGoogleAuth() {
    try {
        const res = await fetch("/api/auth/config");
        if (res.ok) {
            const data = await res.json();
            googleClientId = data.client_id || "";
            isGoogleConfigured = data.is_configured || false;
        }

        if (!googleClientId) {
            console.warn("[!] Google Client ID is not yet configured in .env");
            return;
        }

        const urlParams = new URLSearchParams(window.location.search);
        const isSwitchAction = urlParams.get("action") === "switch";

        // Wait for Google SDK to load
        let attempts = 0;
        const checkGsi = setInterval(() => {
            attempts++;
            if (window.google && window.google.accounts && window.google.accounts.id) {
                clearInterval(checkGsi);
                setupGoogleButtons(isSwitchAction);
            } else if (attempts > 30) {
                clearInterval(checkGsi);
                console.warn("[!] Google Identity SDK timed out.");
            }
        }, 150);
    } catch (e) {
        console.warn("[!] Error fetching auth config:", e);
    }
}

function setupGoogleButtons(isSwitchAction) {
    try {
        if (isSwitchAction && window.google?.accounts?.id?.disableAutoSelect) {
            window.google.accounts.id.disableAutoSelect();
        }

        window.google.accounts.id.initialize({
            client_id: googleClientId,
            callback: handleGoogleCredentialResponse,
            auto_select: false,
            cancel_on_tap_outside: true,
            context: "signin"
        });

        // 1. Render Google button for LOGIN panel
        const loginContainer = document.getElementById("gsiLoginButtonContainer");
        if (loginContainer) {
            loginContainer.innerHTML = "";
            window.google.accounts.id.renderButton(loginContainer, {
                type: "standard",
                shape: "pill",
                theme: "outline",
                text: "continue_with",
                size: "large",
                logo_alignment: "left",
                width: 320
            });
        }

        // 2. Render Google button for SIGN UP panel
        const signupContainer = document.getElementById("gsiSignupButtonContainer");
        if (signupContainer) {
            signupContainer.innerHTML = "";
            window.google.accounts.id.renderButton(signupContainer, {
                type: "standard",
                shape: "pill",
                theme: "outline",
                text: "signup_with",
                size: "large",
                logo_alignment: "left",
                width: 320
            });
        }
    } catch (err) {
        console.error("[!] Error setting up Google buttons:", err);
    }
}

// --- 3. HANDLE GOOGLE CREDENTIAL RETURN ---
async function handleGoogleCredentialResponse(response) {
    if (!response || !response.credential) {
        showToast("Google sign-in was not completed. Please try again.");
        return;
    }

    const slidingCard = document.getElementById("slidingCard");
    const isSignupMode = slidingCard && slidingCard.classList.contains("signup-active");
    
    let preferredName = "";
    if (isSignupMode) {
        const nameInput = document.getElementById("signupPreferredNameInput");
        if (nameInput && nameInput.value.trim()) {
            preferredName = nameInput.value.trim();
        }
    }

    try {
        showToast("Verifying with Google...", false);
        const res = await fetch("/api/auth/google", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                credential: response.credential,
                preferred_name: preferredName
            })
        });

        if (!res.ok) {
            const err = await res.json().catch(() => ({ detail: "Authentication failed" }));
            showToast(err.detail || "Authentication failed. Please try again.");
            return;
        }

        const data = await res.json();
        const user = data.user;
        if (data.session_token) {
            localStorage.setItem("arogya_session_token", data.session_token);
        }
        if (user) {
            localStorage.setItem("arogya_active_user", JSON.stringify(user));
        }
        const displayName = user.preferred_name || user.given_name || user.name || "Friend";

        showToast(`Welcome, ${displayName}! Entering Arogya...`, false);

        // Smooth redirect to main companion chat
        setTimeout(() => {
            window.location.href = "/";
        }, 650);

    } catch (err) {
        console.error("[!] Auth submission error:", err);
        showToast("Network error during sign in. Please try again.");
    }
}

// --- 3B. LOCAL PROFILE AUTH CONTROLS ---
function initLocalAuthControls() {
    const btnLocalLogin = document.getElementById("btnLocalLogin");
    const localInput = document.getElementById("localUsernameInput");
    const btnLocalSignup = document.getElementById("btnLocalSignup");
    const signupInput = document.getElementById("signupPreferredNameInput");

    if (btnLocalLogin && localInput) {
        btnLocalLogin.addEventListener("click", () => {
            loginWithLocalUsername(localInput.value);
        });
        localInput.addEventListener("keydown", (e) => {
            if (e.key === "Enter") {
                e.preventDefault();
                loginWithLocalUsername(localInput.value);
            }
        });
    }

    if (btnLocalSignup && signupInput) {
        btnLocalSignup.addEventListener("click", () => {
            loginWithLocalUsername(signupInput.value);
        });
    }
}

async function loadExistingProfiles() {
    try {
        const res = await fetch("/api/auth/profiles", { credentials: "include" });
        if (!res.ok) return;
        const data = await res.json();
        const profiles = data.profiles || [];
        const container = document.getElementById("existingProfilesList");
        if (!container) return;
        container.innerHTML = "";
        if (profiles.length > 0) {
            const label = document.createElement("div");
            label.style.fontSize = "11px";
            label.style.color = "rgba(255,255,255,0.6)";
            label.style.marginBottom = "6px";
            label.textContent = "Switch to recent user:";
            container.appendChild(label);

            const pillsWrap = document.createElement("div");
            pillsWrap.style.display = "flex";
            pillsWrap.style.flexWrap = "wrap";
            pillsWrap.style.gap = "6px";
            pillsWrap.style.marginBottom = "8px";

            profiles.slice(0, 5).forEach(p => {
                const btn = document.createElement("button");
                btn.type = "button";
                btn.className = "profile-chip-btn";
                btn.style.padding = "4px 10px";
                btn.style.fontSize = "11.5px";
                btn.style.borderRadius = "999px";
                btn.style.border = "1px solid rgba(255,255,255,0.2)";
                btn.style.background = "rgba(255,255,255,0.06)";
                btn.style.color = "#fff";
                btn.style.cursor = "pointer";
                const dName = p.preferred_name || p.given_name || p.name || "User";
                btn.textContent = dName;
                btn.onclick = () => loginWithLocalUsername(dName);
                pillsWrap.appendChild(btn);
            });
            container.appendChild(pillsWrap);
        }
    } catch (e) {
        console.warn("Could not load profiles:", e);
    }
}

async function loginWithLocalUsername(username) {
    if (!username || !username.trim()) {
        showToast("Please enter a username.");
        return;
    }
    showToast(`Entering as ${username.trim()}...`, false);
    try {
        const res = await fetch("/api/auth/switch-local", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ username: username.trim() }),
            credentials: "include"
        });
        if (!res.ok) {
            showToast("Failed to switch profile.");
            return;
        }
        const data = await res.json();
        if (data.session_token) {
            localStorage.setItem("arogya_session_token", data.session_token);
        }
        if (data.user) {
            localStorage.setItem("arogya_active_user", JSON.stringify(data.user));
        }
        showToast(`Welcome, ${username.trim()}! Entering Arogya...`, false);
        setTimeout(() => {
            window.location.href = "/";
        }, 500);
    } catch (e) {
        console.error("Local login error:", e);
        showToast("Network error during local login.");
    }
}

// --- 4. TOAST NOTIFICATION UTILITY ---
let toastTimer = null;
function showToast(message, autoHide = true) {
    const toast = document.getElementById("loginToast");
    const msgEl = document.getElementById("toastMessage");
    if (!toast || !msgEl) return;

    msgEl.textContent = message;
    toast.classList.remove("hidden");

    if (toastTimer) clearTimeout(toastTimer);
    if (autoHide) {
        toastTimer = setTimeout(() => {
            toast.classList.add("hidden");
        }, 4000);
    }
}

// Register PWA Service Worker
if ('serviceWorker' in navigator) {
    window.addEventListener('load', () => {
        navigator.serviceWorker.register('/sw.js').catch(() => {});
    });
}

