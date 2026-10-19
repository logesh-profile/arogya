/**
 * Arogya • Longitudinal Clinical Analytics & Trajectory Controller
 */

document.addEventListener("DOMContentLoaded", () => {
    initTheme();
    loadCurrentUser();
    loadAnalyticsData();
});

// Load authenticated user profile
async function loadCurrentUser() {
    try {
        const res = await fetch("/api/auth/me");
        if (res.ok) {
            const data = await res.json();
            if (data.user) {
                const nameLabel = document.getElementById("userNameLabel");
                const avatarFallback = document.getElementById("userAvatarFallback");
                const avatarImg = document.getElementById("userAvatarImg");
                const disp = data.user.given_name || data.user.name || "Logeshwaran";
                if (nameLabel) nameLabel.textContent = disp;
                if (avatarFallback) avatarFallback.textContent = (data.user.name || disp)[0].toUpperCase();
                if (data.user.picture && avatarImg) {
                    avatarImg.src = data.user.picture;
                    avatarImg.classList.remove("hidden");
                    if (avatarFallback) avatarFallback.classList.add("hidden");
                }
            }
        }
    } catch (e) {
        console.warn("Analytics auth check notice:", e);
    }
}

// Theme Management (Synced with Main Companion)
function initTheme() {
    const savedTheme = localStorage.getItem("arogya_theme") || "dark";
    document.documentElement.setAttribute("data-theme", savedTheme);
    updateThemeUI(savedTheme);

    const toggleBtn = document.getElementById("themeToggleBtn");
    if (toggleBtn) {
        toggleBtn.addEventListener("click", () => {
            const current = document.documentElement.getAttribute("data-theme") || "dark";
            const next = current === "dark" ? "light" : "dark";
            document.documentElement.setAttribute("data-theme", next);
            localStorage.setItem("arogya_theme", next);
            updateThemeUI(next);
            if (window.lastAnalyticsData) {
                renderTrendChart(window.lastAnalyticsData.timeline, window.lastAnalyticsData.kpis);
            }
        });
    }
}

function updateThemeUI(theme) {
    const label = document.getElementById("themeLabel");
    if (label) {
        label.textContent = theme === "dark" ? "Dark" : "Light";
    }
}

// Fetch & Populate Analytics Summary
async function loadAnalyticsData() {
    try {
        const res = await fetch("/api/analytics/summary");
        if (!res.ok) throw new Error("Failed to load analytics summary");
        const data = await res.json();
        window.lastAnalyticsData = data;

        populateKPIs(data.kpis, data.profile);
        renderTrendChart(data.timeline, data.kpis);
        populateSymptoms(data.symptoms);
        populateProfile(data.profile, data.observed_strengths);
        populateTimeline(data.timeline);
    } catch (err) {
        console.error("Analytics load error:", err);
    }
}

// KPIs
function populateKPIs(kpis, profile) {
    if (!kpis) return;

    const lifetimeEl = document.getElementById("kpiLifetime");
    if (lifetimeEl) lifetimeEl.textContent = kpis.lifetime_wellness || 75;

    const deltaEl = document.getElementById("kpiDelta");
    if (deltaEl) {
        const d = kpis.trajectory_delta || 0.0;
        deltaEl.textContent = (d > 0 ? `+${d}` : `${d}`);
    }

    const badgeEl = document.getElementById("kpiTrajectoryBadge");
    if (badgeEl) {
        badgeEl.textContent = kpis.trajectory_status || "Steady";
        badgeEl.className = "trajectory-badge";
        if (kpis.trajectory_delta >= 3) {
            badgeEl.classList.add("positive");
        } else if (kpis.trajectory_delta <= -3) {
            badgeEl.classList.add("strain");
        }
    }

    const descEl = document.getElementById("kpiTrajectoryDesc");
    if (descEl) descEl.textContent = kpis.trajectory_desc || "";

    const reflectionsEl = document.getElementById("kpiReflections");
    if (reflectionsEl) reflectionsEl.textContent = kpis.total_reflections || 0;

    const sessionsEl = document.getElementById("kpiSessionsCount");
    if (sessionsEl) sessionsEl.textContent = `across ${kpis.total_sessions || 0} session${kpis.total_sessions === 1 ? '' : 's'}`;

    const semiEl = document.getElementById("kpiSemitones");
    if (semiEl) semiEl.textContent = kpis.average_voice_semitones || "1.85";
}

// HTML5 Canvas Trend Chart
function renderTrendChart(timeline, kpis) {
    const canvas = document.getElementById("trendCanvas");
    if (!canvas) return;

    const ctx = canvas.getContext("2d");
    const dpr = window.devicePixelRatio || 1;
    const rect = canvas.getBoundingClientRect();
    const w = rect.width;
    const h = rect.height;

    canvas.width = w * dpr;
    canvas.height = h * dpr;
    ctx.scale(dpr, dpr);

    const isDark = document.documentElement.getAttribute("data-theme") !== "light";
    const textColor = isDark ? "#a1a1aa" : "#71717a";
    const gridColor = isDark ? "rgba(255, 255, 255, 0.06)" : "rgba(0, 0, 0, 0.06)";
    const lineColor = isDark ? "#ffffff" : "#09090b";
    const baselineColor = isDark ? "rgba(255, 255, 255, 0.35)" : "rgba(0, 0, 0, 0.35)";

    ctx.clearRect(0, 0, w, h);

    const padLeft = 45;
    const padRight = 30;
    const padTop = 30;
    const padBottom = 40;
    const plotW = w - padLeft - padRight;
    const plotH = h - padTop - padBottom;

    // Y Axis: 0 to 100
    const minY = 30;
    const maxY = 100;

    // Horizontal Gridlines & Y-labels
    ctx.font = "10px 'Space Grotesk', monospace";
    ctx.fillStyle = textColor;
    ctx.textAlign = "right";

    const ySteps = [40, 60, 80, 100];
    ySteps.forEach(val => {
        const y = padTop + plotH - ((val - minY) / (maxY - minY)) * plotH;
        ctx.strokeStyle = gridColor;
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.moveTo(padLeft, y);
        ctx.lineTo(w - padRight, y);
        ctx.stroke();

        ctx.fillText(`${val}`, padLeft - 8, y + 3);
    });

    // Draw Baseline Guide Line
    const baseline = kpis ? kpis.baseline_wellness || 75 : 75;
    const baseY = padTop + plotH - ((baseline - minY) / (maxY - minY)) * plotH;
    ctx.save();
    ctx.setLineDash([4, 4]);
    ctx.strokeStyle = baselineColor;
    ctx.lineWidth = 1.2;
    ctx.beginPath();
    ctx.moveTo(padLeft, baseY);
    ctx.lineTo(w - padRight, baseY);
    ctx.stroke();
    ctx.restore();

    if (!timeline || timeline.length === 0) {
        ctx.font = "13px 'Plus Jakarta Sans', sans-serif";
        ctx.fillStyle = textColor;
        ctx.textAlign = "center";
        ctx.fillText("No multi-session points recorded yet. Complete check-ins to view trajectory.", w / 2, h / 2);
        return;
    }

    const n = timeline.length;
    const points = timeline.map((pt, i) => {
        const x = n === 1 ? padLeft + plotW / 2 : padLeft + (i / (n - 1)) * plotW;
        const val = Math.max(minY, Math.min(maxY, pt.wellness || 75));
        const y = padTop + plotH - ((val - minY) / (maxY - minY)) * plotH;
        return { x, y, pt };
    });

    // Connect with smooth line
    if (points.length > 1) {
        ctx.save();
        ctx.strokeStyle = lineColor;
        ctx.lineWidth = 2.4;
        ctx.lineJoin = "round";
        ctx.lineCap = "round";
        ctx.beginPath();
        ctx.moveTo(points[0].x, points[0].y);

        for (let i = 1; i < points.length; i++) {
            ctx.lineTo(points[i].x, points[i].y);
        }
        ctx.stroke();
        ctx.restore();
    }

    // Draw Points & Labels
    points.forEach((p, idx) => {
        // Point shadow/glow
        ctx.beginPath();
        ctx.arc(p.x, p.y, 4.5, 0, Math.PI * 2);
        ctx.fillStyle = lineColor;
        ctx.fill();

        // White border dot
        ctx.beginPath();
        ctx.arc(p.x, p.y, 2.5, 0, Math.PI * 2);
        ctx.fillStyle = isDark ? "#09090b" : "#ffffff";
        ctx.fill();

        // X Label (Date or Session Title)
        ctx.font = "10px 'Space Grotesk', monospace";
        ctx.fillStyle = textColor;
        ctx.textAlign = "center";
        const label = p.pt.date ? p.pt.date.slice(5) : `S${idx + 1}`;
        ctx.fillText(label, p.x, h - 14);

        // Score above point
        ctx.font = "bold 10px 'Space Grotesk', monospace";
        ctx.fillStyle = lineColor;
        ctx.fillText(`${p.pt.wellness}`, p.x, p.y - 10);
    });
}

// Symptom Distribution List
function populateSymptoms(symptoms) {
    const list = document.getElementById("symptomsList");
    if (!list) return;
    list.innerHTML = "";

    if (!symptoms || symptoms.length === 0) {
        list.innerHTML = `<p class="profile-field-text">No symptom indicators recorded yet.</p>`;
        return;
    }

    symptoms.forEach(item => {
        const score = item.average_score || 0.0;
        const pct = Math.min(100, Math.round((score / 3.0) * 100));
        const quotesText = item.quotes && item.quotes.length > 0 
            ? item.quotes.map(q => `"${q}"`).join(" • ")
            : "No explicit symptom mentions recorded";

        const div = document.createElement("div");
        div.className = "symptom-stat-item";
        div.innerHTML = `
            <div class="symptom-stat-header">
                <span class="symptom-stat-name">${escapeHtml(item.label)}</span>
                <span class="symptom-stat-score tabular-num">${score.toFixed(1)} / 3.0</span>
            </div>
            <div class="symptom-bar-track">
                <div class="symptom-bar-fill" style="width: ${pct}%;"></div>
            </div>
            <div class="symptom-stat-quotes">${escapeHtml(quotesText)}</div>
        `;
        list.appendChild(div);
    });
}

// Clinical Profile Cards
function populateProfile(profile, strengths) {
    if (!profile) return;

    const ctxEl = document.getElementById("profileContext");
    if (ctxEl) {
        ctxEl.textContent = profile.key_context || "Student navigating academic deadlines, career placements, and daily personal routines.";
    }

    const stressCloud = document.getElementById("stressorsTagCloud");
    if (stressCloud) {
        stressCloud.innerHTML = "";
        const stressors = profile.recurring_stressors || [];
        if (stressors.length === 0) {
            stressCloud.innerHTML = `<span class="profile-field-text">No recurring stressors identified.</span>`;
        } else {
            stressors.forEach(s => {
                const tag = document.createElement("span");
                tag.className = "theme-tag";
                tag.textContent = s;
                stressCloud.appendChild(tag);
            });
        }
    }

    const copingCloud = document.getElementById("copingTagCloud");
    if (copingCloud) {
        copingCloud.innerHTML = "";
        const coping = profile.effective_coping || [];
        if (coping.length === 0) {
            copingCloud.innerHTML = `<span class="profile-field-text">No coping strategies recorded.</span>`;
        } else {
            coping.forEach(c => {
                const tag = document.createElement("span");
                tag.className = "theme-tag";
                tag.textContent = c;
                copingCloud.appendChild(tag);
            });
        }
    }

    const strList = document.getElementById("strengthsList");
    if (strList) {
        strList.innerHTML = "";
        const allStrengths = strengths && strengths.length > 0 
            ? strengths 
            : ["Open emotional expression", "Proactive self-awareness", "Engaging in reflective pauses"];
        allStrengths.forEach(st => {
            const li = document.createElement("li");
            li.textContent = st;
            strList.appendChild(li);
        });
    }
}

// Chronological Timeline Log
function populateTimeline(timeline) {
    const list = document.getElementById("timelineList");
    if (!list) return;
    list.innerHTML = "";

    if (!timeline || timeline.length === 0) {
        list.innerHTML = `<p class="profile-field-text">No session history found. Start a check-in on the companion page to record reflections.</p>`;
        return;
    }

    // Show reverse chronological (newest first)
    const reversed = [...timeline].reverse();

    reversed.forEach(item => {
        const card = document.createElement("div");
        card.className = "session-timeline-card";

        const quotesHtml = item.quotes && item.quotes.length > 0 
            ? `<div class="session-log-quotes">Evidence: ${item.quotes.map(q => `"${escapeHtml(q)}"`).join(" • ")}</div>` 
            : "";

        card.innerHTML = `
            <div class="session-log-left">
                <div class="session-log-title-row">
                    <h3 class="session-log-title">${escapeHtml(item.title || "Daily Reflection")}</h3>
                    <span class="session-log-date tabular-num">${item.date || ""} ${item.time || ""}</span>
                </div>
                <p class="session-log-summary">${escapeHtml(item.summary || "Reflective check-in session completed.")}</p>
                ${quotesHtml}
            </div>
            <div class="session-log-right">
                <span class="session-log-score tabular-num">${item.wellness}/100</span>
                <span class="session-log-emotion">${escapeHtml(item.dominant_emotion || "Calm")}</span>
            </div>
        `;
        list.appendChild(card);
    });
}

function escapeHtml(str) {
    if (!str) return "";
    return String(str)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
}
