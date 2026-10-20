/**
 * Arogya CompanionAI • Sliding Authentication Controller
 * Black & White Monochrome Sliding Interface with Real Google OAuth 2.0
 */

let googleClientId = "";
let isGoogleConfigured = false;

document.addEventListener("DOMContentLoaded", async () => {
    initSlidingControls();
    await initGoogleAuth();
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
