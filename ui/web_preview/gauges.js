
// --- CLOCK FORMATTING (12-Hour AM/PM vs 24-Hour Military) ---
let is24HourClock = localStorage.getItem('carpi5_clock_format') === '24H';

function formatClockTime(date = new Date(), includeSeconds = false) {
  if (is24HourClock) {
    const opts = { hour: '2-digit', minute: '2-digit', hour12: false };
    if (includeSeconds) opts.second = '2-digit';
    return date.toLocaleTimeString([], opts);
  } else {
    let hours = date.getHours();
    const minutes = String(date.getMinutes()).padStart(2, '0');
    const ampm = hours >= 12 ? 'PM' : 'AM';
    hours = hours % 12;
    hours = hours ? hours : 12;
    if (includeSeconds) {
      const seconds = String(date.getSeconds()).padStart(2, '0');
      return `${hours}:${minutes}:${seconds} ${ampm}`;
    }
    return `${hours}:${minutes} ${ampm}`;
  }
}

function toggleClockFormat() {
  is24HourClock = !is24HourClock;
  localStorage.setItem('carpi5_clock_format', is24HourClock ? '24H' : '12H');
  const btn = document.getElementById('btnClockFormat');
  if (btn) btn.innerText = is24HourClock ? "CLOCK: 24-HOUR (MILITARY)" : "CLOCK: 12-HOUR (AM/PM)";
  const clock = document.getElementById('footerClock');
  if (clock) clock.innerText = formatClockTime(new Date());
  const scClock = document.getElementById('screensaverClock');
  if (scClock) scClock.innerText = formatClockTime(new Date(), true);
}

// --- DISPLAY BRIGHTNESS SCRIM ---
function setDisplayBrightness(val) {
  const pct = Math.max(15, Math.min(100, parseInt(val) || 100));
  const overlay = document.getElementById('screenBrightnessOverlay');
  if (overlay) {
    overlay.style.opacity = (1.0 - (pct / 100.0)).toFixed(2);
  }
  const slider = document.getElementById('cfgDisplayBrightness');
  if (slider) slider.value = pct;
  const label = document.getElementById('cfgBrightnessLabel');
  if (label) label.innerText = `${pct}%`;
  localStorage.setItem('carpi5_brightness', pct);
  fetch('/api/display/settings', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ brightness: pct })
  }).catch(() => {});
}

// --- KINETIC TOUCH SCROLLING ---
function enableKineticTouchScroll(element) {
  if (!element) return;
  let startY = 0;
  let lastY = 0;
  let lastTime = 0;
  let velocityY = 0;
  let isDragging = false;
  let momentumFrame = null;

  element.addEventListener('touchstart', (e) => {
    if (momentumFrame) cancelAnimationFrame(momentumFrame);
    if (!e.touches || !e.touches[0]) return;
    isDragging = true;
    startY = e.touches[0].pageY;
    lastY = startY;
    lastTime = Date.now();
    velocityY = 0;
  }, { passive: true });

  element.addEventListener('touchmove', (e) => {
    if (!isDragging || !e.touches || !e.touches[0]) return;
    const curY = e.touches[0].pageY;
    const now = Date.now();
    const dt = Math.max(1, now - lastTime);
    const dy = curY - lastY;
    element.scrollTop -= dy;
    velocityY = dy / dt;
    lastY = curY;
    lastTime = now;
  }, { passive: true });

  element.addEventListener('touchend', () => {
    isDragging = false;
    let v = velocityY * 16;
    function glide() {
      if (Math.abs(v) > 0.5) {
        element.scrollTop -= v;
        v *= 0.92;
        momentumFrame = requestAnimationFrame(glide);
      }
    }
    if (Math.abs(v) > 1.0) {
      momentumFrame = requestAnimationFrame(glide);
    }
  }, { passive: true });
}

/**
 * gauges.js - Dodge Dart CarPi5 Automotive OS & Dynamic Cockpit Controller
 * 
 * Features:
 * - Multi-Screen Navigation (Home Hub, Gauges, M.A.I.A. Terminal, Media, Settings)
 * - Dynamic Gauge Grid (1, 2, 3, 4, 6, and 8 gauges with 4 on top / 4 on bottom)
 * - Click-to-Inspect Live Telemetry Line Graph Scope (Last 60 seconds @ 2Hz)
 * - Interactive M.A.I.A. AI Chat Terminal + Copilot Event Logging + Speech Synthesis
 * - Tailscale Mesh Network & Desktop Ollama GPU Integration
 * - Powertrain Diagnostics (OBD-II DTC inspection, spoken explanations, and reset)
 * - In-Car Media Player & Ambient Photo Slideshow Screensaver with Idle Timer
 */

// --- 1. SENSOR DEFINITIONS & STATE ---

const SENSORS = {
  speed: { id: "speed", name: "Vehicle Speed", unit: "MPH", min: 0, max: 140, color: "#00b0ff" },
  boost: { id: "boost", name: "Turbo Boost", unit: "PSI", min: -25, max: 22, color: "#00e676" },
  rpm: { id: "rpm", name: "Engine RPM", unit: "RPM", min: 0, max: 7000, color: "#ffcc00" },
  coolant: { id: "coolant", name: "MultiAir Oil Temp", unit: "°F", min: 60, max: 240, color: "#ff7700" },
  iat: { id: "iat", name: "Intake Air Temp", unit: "°F", min: 50, max: 160, color: "#00e5ff" },
  throttle: { id: "throttle", name: "Throttle Pos", unit: "%", min: 0, max: 100, color: "#b388ff" },
  volts: { id: "volts", name: "Battery Volts", unit: "V", min: 10, max: 16, color: "#00e676" },
  mpg: { id: "mpg", name: "Fuel Economy", unit: "MPG", min: 0, max: 60, color: "#00e676" }
};

// Global App State
let currentScreen = "home";
let currentLayout = 3; // Default 3 gauges (Speed, Boost, RPM)
let currentSlots = ["speed", "boost", "rpm", "coolant", "iat", "throttle", "volts", "mpg"];
let isKph = false;
let currentVoiceMode = "COPILOT";
let activeGraphSensor = null;
let currentAiSettings = {
  mode: "BUILTIN",
  personality: "MAIA",
  driver_title: "Master",
  driver_name: "Creator",
  driver_moniker: "Creator",
  tailscale_ip: "100.x.y.z",
  tailscale_port: 11434,
  ollama_model: "llama3.2:3b",
  api_key: ""
};

function getDriverDisplayAddress() {
  const title = (currentAiSettings.driver_title || "").trim();
  const name = (currentAiSettings.driver_name || currentAiSettings.driver_moniker || "").trim();
  if (title && name) return `${title} ${name}`;
  if (name) return name;
  if (title) return title;
  return "Master";
}

// Time-Series Historical Buffer (stores last 60 seconds of data @ 2Hz = 120 samples per sensor)
const HISTORY_LENGTH = 120;
const historyBuffers = {};
Object.keys(SENSORS).forEach(k => {
  historyBuffers[k] = [];
  historyBuffers[k]._lastTime = 0;
});

// Screensaver & Idle Timer State
let screensaverTimer = null;
let screensaverInterval = null;
let lastInteractionTime = Date.now();
const screensaverImages = [
  "https://images.unsplash.com/photo-1542282088-72c9c27ed0cd?auto=format&fit=crop&w=1920&q=90",
  "https://images.unsplash.com/photo-1503376780353-7e6692767b70?auto=format&fit=crop&w=1920&q=90",
  "https://images.unsplash.com/photo-1492144534655-ae79c964c9d7?auto=format&fit=crop&w=1920&q=90",
  "https://images.unsplash.com/photo-1511919884226-fd3cad34687c?auto=format&fit=crop&w=1920&q=90"
];
let currentImageIdx = 0;

// Media Player State
const PLAYLIST = [
  { title: "Turbo Highway Star (Synthwave Edit)", artist: "CarPi5 In-Console Audio", duration: 225 },
  { title: "Nightcall MultiAir Drift", artist: "Kavinsky & C635", duration: 260 },
  { title: "1.4L Boost Anthem (Italian FIRE)", artist: "M.A.I.A. Synthetics", duration: 198 }
];
let currentTrackIdx = 0;
let isPlaying = true;
let trackElapsedSeconds = 84;
let mediaPlayInterval = null;


// --- 2. MULTI-SCREEN NAVIGATION ---

function navigateTo(screenId) {
  currentScreen = screenId;

  // Toggle Screen Views
  const screens = {
    home: document.getElementById('screenHome'),
    gauges: document.getElementById('screenGauges'),
    ai: document.getElementById('screenAI'),
    media: document.getElementById('screenMedia'),
    games: document.getElementById('screenGames'),
    settings: document.getElementById('screenSettings')
  };

  Object.keys(screens).forEach(key => {
    if (screens[key]) {
      if (key === screenId) {
        screens[key].classList.add('active');
      } else {
        screens[key].classList.remove('active');
      }
    }
  });

  // Toggle Bottom Dock Buttons
  const buttons = {
    home: document.getElementById('dockBtnHome'),
    gauges: document.getElementById('dockBtnGauges'),
    ai: document.getElementById('dockBtnAI'),
    media: document.getElementById('dockBtnMedia'),
    games: document.getElementById('dockBtnGames'),
    settings: document.getElementById('dockBtnSettings')
  };

  Object.keys(buttons).forEach(key => {
    if (buttons[key]) {
      if (key === screenId) {
        buttons[key].classList.add('active');
      } else {
        buttons[key].classList.remove('active');
      }
    }
  });

  // Specific Screen Hooks
  if (screenId === "gauges") {
    requestAnimationFrame(() => {
      resizeAllCanvases();
    });
    setTimeout(resizeAllCanvases, 50);
  } else if (screenId === "ai") {
    scrollChatToBottom();
    fetchAiHistory();
  }

  resetIdleTimer();
}


// --- 3. DYNAMIC GAUGE GRID & CANVAS RENDERING ---

function initGaugeGrid() {
  const container = document.getElementById('gaugeGridContainer');
  if (!container) return;

  container.className = `dashboard-grid-container grid-layout-${currentLayout}`;
  container.innerHTML = '';

  for (let i = 0; i < currentLayout; i++) {
    const sensorKey = currentSlots[i] || "boost";
    const sensor = SENSORS[sensorKey];

    const tile = document.createElement('div');
    tile.className = 'gauge-tile';
    tile.id = `tile_${i}`;
    tile.setAttribute('data-sensor', sensorKey);
    tile.onclick = function() {
      const s = this.getAttribute('data-sensor') || sensorKey;
      openGraphModal(s);
    };

    tile.innerHTML = `
      <div class="click-hint">Scope ↗</div>
      <div class="gauge-canvas-wrapper">
        <canvas id="canvas_${i}"></canvas>
      </div>
      <div class="gauge-center-readout">
        <div class="readout-value" id="val_${i}">--</div>
        <div class="readout-label" id="lbl_${i}">${sensor.name} (${sensor.unit})</div>
        <div class="readout-sub" id="sub_${i}"></div>
      </div>
    `;
    container.appendChild(tile);
  }
  resizeAllCanvases();
}

function resizeHistoryGraphCanvas() {
  const graphCanvas = document.getElementById('historyGraphCanvas');
  if (!graphCanvas) return;
  const container = graphCanvas.parentElement;
  const dpr = window.devicePixelRatio || 1;
  const w = (container && container.clientWidth > 50) ? container.clientWidth : (window.innerWidth - 60);
  const h = (container && container.clientHeight > 50) ? container.clientHeight : (window.innerHeight - 160);

  graphCanvas.width = Math.round(w * dpr);
  graphCanvas.height = Math.round(h * dpr);
}

function resizeAllCanvases() {
  const dpr = window.devicePixelRatio || 1;
  for (let i = 0; i < currentLayout; i++) {
    const canvas = document.getElementById(`canvas_${i}`);
    if (canvas && canvas.clientWidth > 0 && canvas.clientHeight > 0) {
      canvas.width = Math.round(canvas.clientWidth * dpr);
      canvas.height = Math.round(canvas.clientHeight * dpr);
    }
  }
  resizeHistoryGraphCanvas();
}
window.addEventListener('resize', resizeAllCanvases);

function drawGaugeDial(ctx, w, h, pct, activeColor) {
  const cx = w / 2;
  const cy = h / 2;
  const radius = Math.min(cx, cy) * 0.76;

  const minA = Math.PI * 0.75;
  const maxA = Math.PI * 2.25;
  const curA = minA + (Math.max(0, Math.min(1, pct)) * (maxA - minA));

  // Background Track
  ctx.beginPath();
  ctx.arc(cx, cy, radius, minA, maxA);
  ctx.strokeStyle = '#181e26';
  ctx.lineWidth = Math.max(5, 11 * (w / 340));
  ctx.lineCap = 'round';
  ctx.stroke();

  // Active Sweeping Arc
  ctx.beginPath();
  ctx.arc(cx, cy, radius, minA, curA);
  ctx.strokeStyle = activeColor;
  ctx.lineWidth = Math.max(5, 11 * (w / 340));
  ctx.lineCap = 'round';
  ctx.stroke();

  // Hub dot
  ctx.beginPath();
  ctx.arc(cx, cy, 4 * window.devicePixelRatio, 0, Math.PI * 2);
  ctx.fillStyle = activeColor;
  ctx.fill();
}

function updateTile(slotIdx, sensorKey, telemetry) {
  const canvas = document.getElementById(`canvas_${slotIdx}`);
  if (!canvas) return;

  const dpr = window.devicePixelRatio || 1;
  if (canvas.clientWidth > 0 && (canvas.width !== Math.round(canvas.clientWidth * dpr) || canvas.height !== Math.round(canvas.clientHeight * dpr))) {
    canvas.width = Math.round(canvas.clientWidth * dpr);
    canvas.height = Math.round(canvas.clientHeight * dpr);
  }
  if (canvas.width === 0 || canvas.height === 0) return;

  const ctx = canvas.getContext('2d');
  ctx.clearRect(0, 0, canvas.width, canvas.height);

  let rawVal = 0;
  let displayStr = "";
  let subStr = "";
  let pct = 0;
  let color = SENSORS[sensorKey].color;

  const isConnected = telemetry.connected !== false;

  if (sensorKey === "boost") {
    if (!isConnected || telemetry.boost_psi === null || telemetry.boost_psi === undefined) {
      displayStr = "--";
      subStr = isConnected ? "IDLE / CALIBRATING" : "DISCONNECTED";
      pct = 0;
      color = "#8c9ba5";
    } else if (telemetry.is_in_boost) {
      rawVal = telemetry.boost_psi;
      displayStr = "+" + rawVal.toFixed(1);
      subStr = "BOOST PSI";
      const maxBoostLimit = Math.max(22.0, Math.ceil(rawVal));
      pct = 0.45 + (Math.min(rawVal, maxBoostLimit) / maxBoostLimit) * 0.55;
      color = rawVal > 16.0 ? "#ff3344" : "#00e676";
    } else {
      rawVal = -telemetry.vacuum_inhg;
      displayStr = "-" + Math.round(telemetry.vacuum_inhg);
      subStr = "inHg VACUUM";
      const maxVacLimit = Math.max(25.0, Math.ceil(telemetry.vacuum_inhg));
      pct = 0.45 - (Math.min(telemetry.vacuum_inhg, maxVacLimit) / maxVacLimit) * 0.45;
      color = "#00b0ff";
    }
  } else if (sensorKey === "speed") {
    rawVal = isKph ? (telemetry.speed_kph || 0) : (telemetry.speed_mph || 0);
    displayStr = Math.round(rawVal).toString();
    subStr = isKph ? "KM/H" : "MPH";
    pct = rawVal / (isKph ? 220 : 140);
  } else if (sensorKey === "rpm") {
    rawVal = telemetry.rpm || 0;
    displayStr = Math.round(rawVal).toString();
    subStr = "RPM";
    pct = rawVal / 7000.0;
    if (rawVal > 5800) color = "#ff3344";
    else if (rawVal > 5000) color = "#ffcc00";
  } else if (sensorKey === "coolant") {
    if (!isConnected || telemetry.coolant_temp_f === null || telemetry.coolant_temp_f === undefined) {
      displayStr = "-- °F";
      subStr = "DISCONNECTED";
      pct = 0;
      color = "#8c9ba5";
    } else {
      rawVal = telemetry.coolant_temp_f;
      displayStr = Math.round(rawVal) + "°F";
      subStr = telemetry.multiair_ready ? "OPTIMAL" : "WARMING UP";
      pct = (rawVal - 60) / 180;
      if (rawVal > 218) color = "#ff3344";
    }
  } else if (sensorKey === "iat") {
    if (!isConnected || telemetry.intake_temp_f === null || telemetry.intake_temp_f === undefined) {
      displayStr = "-- °F";
      subStr = "DISCONNECTED";
      pct = 0;
      color = "#8c9ba5";
    } else {
      rawVal = telemetry.intake_temp_f;
      displayStr = Math.round(rawVal) + "°F";
      subStr = "INTAKE AIR";
      pct = (rawVal - 50) / 110;
    }
  } else if (sensorKey === "throttle") {
    rawVal = telemetry.throttle_pct || 0;
    displayStr = Math.round(rawVal) + "%";
    subStr = "THROTTLE";
    pct = rawVal / 100.0;
  } else if (sensorKey === "volts") {
    if (!isConnected || telemetry.battery_volts === null || telemetry.battery_volts === undefined) {
      displayStr = "-- V";
      subStr = "DISCONNECTED";
      pct = 0;
      color = "#8c9ba5";
    } else {
      rawVal = telemetry.battery_volts;
      displayStr = rawVal.toFixed(1) + "V";
      subStr = "ALTERNATOR";
      pct = (rawVal - 10) / 6.0;
    }
  } else if (sensorKey === "mpg") {
    if (!isConnected || telemetry.fuel_mpg_instant === null || telemetry.fuel_mpg_instant === undefined) {
      displayStr = "--";
      subStr = "DISCONNECTED";
      pct = 0;
      color = "#8c9ba5";
    } else {
      rawVal = telemetry.fuel_mpg_instant;
      displayStr = rawVal.toFixed(1);
      subStr = "INSTANT MPG";
      pct = rawVal / 50.0;
    }
  }

  drawGaugeDial(ctx, canvas.width, canvas.height, pct, color);

  const valEl = document.getElementById(`val_${slotIdx}`);
  const subEl = document.getElementById(`sub_${slotIdx}`);
  if (valEl) {
    valEl.innerText = displayStr;
    valEl.style.color = color;
  }
  if (subEl) subEl.innerText = subStr;
}

function toggleSpeedUnits() {
  isKph = !isKph;
  const btn = document.getElementById('unitToggleBtn');
  if (btn) btn.innerText = isKph ? "UNITS: KM/H" : "UNITS: MPH";
  initGaugeGrid();
}


// --- 4. TELEMETRY STREAM & REAL-TIME DISPATCH (25Hz SSE) ---

let eventSource = null;
let latestTelemetry = null;
let startupGreetingTriggered = false;

let aiCoreCheckInterval = null;

function updateAiCoreStatus(status) {
  const orb = document.getElementById('aiCoreOrb');
  const text = document.getElementById('aiCoreText');
  const pill = document.getElementById('aiCoreStatusPill');
  if (!orb || !text) return;

  if (status === 'online') {
    orb.innerText = '🟢';
    text.innerText = 'AI CORE: ONLINE';
    if (pill) {
      pill.style.borderColor = 'var(--accent-green)';
      pill.style.boxShadow = '0 0 10px rgba(0, 230, 118, 0.25)';
    }
  } else {
    orb.innerText = '🟡';
    text.innerText = 'AI CORE: WARMING';
    if (pill) {
      pill.style.borderColor = 'rgba(255, 176, 0, 0.4)';
      pill.style.boxShadow = 'none';
    }
  }
}

function triggerStartupGreeting() {
  if (startupGreetingTriggered) return;
  startupGreetingTriggered = true;

  // Stage 1: Immediate Instant Greeting upon cold boot
  updateAiCoreStatus('warming');
  fetch('/api/ai/greeting/instant')
    .then(r => r.json())
    .then(data => {
      if (data && data.greeting) {
        console.log(`[INSTANT BOOT GREETING] "${data.greeting}"`);
        showAiSpeechToast(data.greeting);
        if (data.emotion) setWaifuEmotion(data.emotion);
      }
    })
    .catch(err => console.warn("[INSTANT GREETING] Note:", err));

  // Stage 2: Background monitor for Qwen-3B warm-up completion
  aiCoreCheckInterval = setInterval(() => {
    fetch('/api/ai/status')
      .then(r => r.json())
      .then(data => {
        if (data && data.ai_core === 'online') {
          clearInterval(aiCoreCheckInterval);
          updateAiCoreStatus('online');
          console.log("[AI CORE] Local neural engine is warm! Triggering official greeting...");
          
          fetch('/api/ai/greeting/official')
            .then(r => r.json())
            .then(neuralData => {
              if (neuralData && neuralData.greeting) {
                console.log(`[OFFICIAL NEURAL GREETING] "${neuralData.greeting}"`);
                showAiSpeechToast(neuralData.greeting);
                if (neuralData.emotion) setWaifuEmotion(neuralData.emotion);
              }
            })
            .catch(e => console.warn("[OFFICIAL GREETING] Note:", e));
        }
      })
      .catch(e => {});
  }, 2000);
}

function connectTelemetryStream() {
  if (eventSource) {
    eventSource.close();
  }

  eventSource = new EventSource('/stream');

  eventSource.onopen = function() {
    console.log("[STREAM] Connected to CarPi5 Telemetry Stream.");
    dismissBootSplash();
    triggerStartupGreeting();
  };

  eventSource.onmessage = function(e) {
    const data = JSON.parse(e.data);
    if (data.action) {
      handleAiAction(data.action);
    }
    const t = data.telemetry;
    if (!t || !t.timestamp) return;

    latestTelemetry = t;

    // Auto-dismiss boot splash on first live telemetry frame
    if (!bootSplashDismissed) {
      dismissBootSplash();
    }

    // Emergency DTC Floating HUD check across ANY screen
    if (t.active_dtcs && t.active_dtcs.length > 0) {
      showEmergencyDtcHud(t.active_dtcs[0]);
    } else if (t.coolant_temp_f && t.coolant_temp_f > 225) {
      showEmergencyDtcHud("OVERHEAT_WARNING", `Engine coolant temp is high: ${Math.round(t.coolant_temp_f)}°F!`);
    }

    // 0. Continuous Global Telemetry Recorder (All 8 sensors @ ~2Hz)
    recordAllSensorsHistory(t);

    // 1. Update Gauge Cluster (if visible)
    if (currentScreen === "gauges") {
      for (let i = 0; i < currentLayout; i++) {
        updateTile(i, currentSlots[i], t);
      }
    }

    // 2. Header F1 Lights & Gear Badge
    const gearEl = document.getElementById('gearBadge');
    if (gearEl) gearEl.innerText = t.gear;

    const dots = document.querySelectorAll('.f1-dot');
    dots.forEach((dot, idx) => {
      dot.className = 'f1-dot';
      if (idx < t.f1_light_level) {
        if (idx < 2) dot.classList.add('active', 'green');
        else if (idx === 2) dot.classList.add('active', 'yellow');
        else if (idx === 3) dot.classList.add('active', 'red');
        else if (idx === 4) dot.classList.add('active', 'blue');
      }
    });

    // 3. MultiAir Warmup Pill
    const pill = document.getElementById('multiairPill');
    if (pill) {
      if (t.multiair_ready) {
        pill.className = "pill pill-ready";
        pill.innerText = "MULTIAIR READY";
      } else {
        pill.className = "pill pill-warming";
        pill.innerText = "MULTIAIR WARMING";
      }
    }

    // 4. Check Engine MIL
    const milBadge = document.getElementById('milBadge');
    const homeDtc = document.getElementById('homeDtcBadge');
    latestActiveDTCs = t.active_dtcs || [];
    if (latestActiveDTCs.length > 0) {
      if (milBadge) {
        milBadge.classList.add('show');
        document.getElementById('milText').innerText = `CHECK ENGINE: ${latestActiveDTCs[0]}`;
      }
      if (homeDtc) {
        homeDtc.innerText = `DTC: ${latestActiveDTCs[0]}`;
        homeDtc.style.color = "var(--accent-red)";
        homeDtc.style.borderColor = "var(--accent-red)";
      }
    } else {
      if (milBadge) milBadge.classList.remove('show');
      if (homeDtc) {
        homeDtc.innerText = "ECU: HEALTHY";
        homeDtc.style.color = "var(--accent-green)";
        homeDtc.style.borderColor = "var(--accent-green)";
      }
    }

    // 5. Update Home Screen Live Badges
    const homeSpeed = document.getElementById('homeSpeedBadge');
    const homeBoost = document.getElementById('homeBoostBadge');
    if (homeSpeed) homeSpeed.innerText = `${Math.round(isKph ? t.speed_kph : t.speed_mph)} ${isKph ? 'KM/H' : 'MPH'}`;
    if (homeBoost) {
      homeBoost.innerText = t.is_in_boost ? `+${t.boost_psi.toFixed(1)} PSI` : `-${Math.round(t.vacuum_inhg)} inHg`;
      homeBoost.style.color = t.is_in_boost ? "var(--accent-green)" : "var(--accent-blue)";
    }

    // 6. Update AI Telemetry Context
    const ctxSpeed = document.getElementById('contextSpeedGear');
    const ctxBoost = document.getElementById('contextBoost');
    const ctxCoolant = document.getElementById('contextCoolant');
    if (ctxSpeed) ctxSpeed.innerText = `${Math.round(t.speed_mph)} MPH (Gear ${t.gear})`;
    if (ctxBoost) ctxBoost.innerText = t.is_in_boost ? `+${t.boost_psi.toFixed(1)} PSI` : `-${Math.round(t.vacuum_inhg)} inHg`;
    if (ctxCoolant) ctxCoolant.innerText = `${Math.round(t.coolant_temp_f)}°F (${t.multiair_ready ? 'Ready' : 'Warming'})`;

    // 7. Update Launch Timer Badge
    const launchBadge = document.getElementById('launchTimerBadge');
    if (launchBadge) {
      if (t.launch_timer_active) {
        launchBadge.innerText = `⏱️ 0-60: TIMING...`;
        launchBadge.style.color = "var(--accent-red)";
      } else if (t.zero_to_sixty_time > 0) {
        launchBadge.innerText = `⏱️ 0-60: ${t.zero_to_sixty_time.toFixed(2)}s`;
        launchBadge.style.color = "var(--accent-green)";
      } else {
        launchBadge.innerText = `⏱️ 0-60: READY`;
        launchBadge.style.color = "var(--accent-yellow)";
      }
    }

    // 8. Live-draw History Graph (if modal is open)
    if (activeGraphSensor) {
      renderHistoryGraph(activeGraphSensor);
    }

    // Real-Time Hardware Speech Lip-Sync synchronization
    if (typeof data.is_speaking === 'boolean') {
      isWaifuSpeaking = data.is_speaking;
      const stage = document.getElementById('waifuStage');
      if (stage) {
        if (isWaifuSpeaking) stage.classList.add('speaking');
        else stage.classList.remove('speaking');
      }
    }

    // 9. AI Voice Toast Banner & Real-Time Event Log
    if (data.ai_event) {
      appendSpeechLogItem(data.ai_event);
      if (data.ai_event.emotion) {
        setWaifuEmotion(data.ai_event.emotion);
      }
      if (currentVoiceMode !== "MUTED" && data.ai_event.speech) {
        showAiSpeechToast(data.ai_event.speech);
      }
    }
  };

  eventSource.onerror = function() {
    console.warn("[STREAM] Disconnected. Reconnecting in 1s...");
    eventSource.close();
    setTimeout(connectTelemetryStream, 1000);
  };
}

connectTelemetryStream();


// --- 5. CLICK-TO-INSPECT LIVE TELEMETRY GRAPH & CONTINUOUS BUFFER ---

let lastHistoryRecordTime = 0;
function recordAllSensorsHistory(t) {
  if (!t) return;
  const now = Date.now();
  if (now - lastHistoryRecordTime < 480) return; // ~2Hz sampling
  lastHistoryRecordTime = now;

  const currentVals = {
    speed: isKph ? (t.speed_kph || 0) : (t.speed_mph || 0),
    boost: t.is_in_boost ? (t.boost_psi || 0) : -(t.vacuum_inhg || 0),
    rpm: t.rpm || 0,
    coolant: t.coolant_temp_f || 0,
    iat: t.intake_temp_f || 0,
    throttle: t.throttle_pct || 0,
    volts: t.battery_volts || 0,
    mpg: t.fuel_mpg_instant || 0
  };

  Object.keys(currentVals).forEach(k => {
    if (!historyBuffers[k]) historyBuffers[k] = [];
    historyBuffers[k].push(currentVals[k]);
    if (historyBuffers[k].length > HISTORY_LENGTH) {
      historyBuffers[k].shift();
    }
  });
}

function seedSensorHistory(sensorKey) {
  if (!historyBuffers[sensorKey]) historyBuffers[sensorKey] = [];
  if (historyBuffers[sensorKey].length >= 5) return;

  const t = latestTelemetry;
  let baseVal = 0;
  if (sensorKey === "boost") {
    baseVal = t ? (t.is_in_boost ? t.boost_psi : -t.vacuum_inhg) : -18.0;
  } else if (sensorKey === "speed") {
    baseVal = t ? (isKph ? t.speed_kph : t.speed_mph) : 0;
  } else if (sensorKey === "rpm") {
    baseVal = t ? t.rpm : 850;
  } else if (sensorKey === "coolant") {
    baseVal = t ? t.coolant_temp_f : 195;
  } else if (sensorKey === "iat") {
    baseVal = t ? t.intake_temp_f : 85;
  } else if (sensorKey === "throttle") {
    baseVal = t ? t.throttle_pct : 0;
  } else if (sensorKey === "volts") {
    baseVal = t ? t.battery_volts : 14.1;
  } else if (sensorKey === "mpg") {
    baseVal = t ? t.fuel_mpg_instant : 28.5;
  }

  // Pre-fill 20 points with subtle organic variation so waveform is instantly active
  for (let i = 0; i < 20; i++) {
    const jitter = (Math.random() - 0.5) * (sensorKey === "rpm" ? 40 : sensorKey === "boost" ? 0.4 : 0.2);
    historyBuffers[sensorKey].push(Number((baseVal + jitter).toFixed(2)));
  }
}

function openGraphModal(sensorKey) {
  if (!sensorKey || !SENSORS[sensorKey]) sensorKey = "boost";
  activeGraphSensor = sensorKey;
  const sensor = SENSORS[sensorKey];

  const titleEl = document.getElementById('graphTitle');
  const unitEl = document.getElementById('graphUnit');
  if (titleEl) titleEl.innerText = sensor.name;
  if (unitEl) unitEl.innerText = `Live Scrolling Telemetry (Last 60 Seconds) • ${sensor.unit}`;

  const modal = document.getElementById('graphModal');
  if (modal) {
    modal.style.display = 'flex';
    modal.classList.add('open');
  }

  seedSensorHistory(sensorKey);
  resizeHistoryGraphCanvas();
  renderHistoryGraph(sensorKey);

  requestAnimationFrame(() => {
    resizeHistoryGraphCanvas();
    renderHistoryGraph(sensorKey);
  });
}

function closeGraphModal() {
  const modal = document.getElementById('graphModal');
  if (modal) {
    modal.style.display = 'none';
    modal.classList.remove('open');
  }
  activeGraphSensor = null;
}

window.addEventListener('keydown', (e) => {
  if (e.key === "Escape" && activeGraphSensor) {
    closeGraphModal();
  }
});

function renderHistoryGraph(sensorKey) {
  const canvas = document.getElementById('historyGraphCanvas');
  if (!canvas) return;
  const ctx = canvas.getContext('2d');

  if (!canvas.width || !canvas.height || canvas.width < 50) {
    resizeHistoryGraphCanvas();
  }
  const w = canvas.width;
  const h = canvas.height;
  if (w <= 0 || h <= 0) return;

  const data = historyBuffers[sensorKey] || [];
  const sensor = SENSORS[sensorKey] || SENSORS.boost;
  const dpr = window.devicePixelRatio || 1;

  ctx.clearRect(0, 0, w, h);

  if (data.length < 2) {
    seedSensorHistory(sensorKey);
  }

  let dataMin = data.length > 0 ? Math.min(...data) : sensor.min;
  let dataMax = data.length > 0 ? Math.max(...data) : sensor.max;
  const curVal = data.length > 0 ? data[data.length - 1] : 0;
  const avgVal = data.length > 0 ? (data.reduce((a, b) => a + b, 0) / data.length) : curVal;

  // Dynamic Autoscaling:
  // If boost climbs above default 20 PSI or vacuum drops past -25 inHg,
  // the top and bottom scale marks adjust dynamically so the peak is fully visible.
  let minVal = Math.min(sensor.min, dataMin);
  let maxVal = Math.max(sensor.max, dataMax);

  if (sensorKey === "boost") {
    const defaultTop = 20.0;
    const defaultBottom = -25.0;
    maxVal = dataMax > defaultTop ? Math.ceil(dataMax) : defaultTop;
    minVal = dataMin < defaultBottom ? Math.floor(dataMin) : defaultBottom;
  } else if (sensorKey === "rpm") {
    maxVal = Math.max(7000, Math.ceil(dataMax / 500) * 500);
    minVal = Math.min(0, Math.floor(dataMin / 500) * 500);
  } else if (sensorKey === "speed") {
    const baseSpeed = isKph ? 220 : 140;
    maxVal = dataMax > baseSpeed ? Math.ceil(dataMax / 10) * 10 : baseSpeed;
    minVal = 0;
  } else {
    if (dataMax > sensor.max) maxVal = Math.ceil(dataMax);
    if (dataMin < sensor.min) minVal = Math.floor(dataMin);
  }

  // Format stat pill readouts
  function fmtVal(val) {
    if (sensorKey === "boost") {
      return val >= 0 ? `+${val.toFixed(1)} PSI` : `${Math.round(val)} inHg`;
    }
    if (sensorKey === "speed") {
      return `${Math.round(val)} ${isKph ? 'KM/H' : 'MPH'}`;
    }
    if (sensorKey === "rpm") {
      return `${Math.round(val)} RPM`;
    }
    if (sensorKey === "coolant" || sensorKey === "iat") {
      return `${Math.round(val)} °F`;
    }
    if (sensorKey === "volts") {
      return `${val.toFixed(1)} V`;
    }
    if (sensorKey === "throttle") {
      return `${Math.round(val)}%`;
    }
    return `${val.toFixed(1)} ${sensor.unit}`;
  }

  const curEl = document.getElementById('graphCurrent');
  const maxEl = document.getElementById('graphMax');
  const minEl = document.getElementById('graphMin');
  const avgEl = document.getElementById('graphAvg');
  if (curEl) curEl.innerText = fmtVal(curVal);
  if (maxEl) maxEl.innerText = fmtVal(maxVal);
  if (minEl) minEl.innerText = fmtVal(minVal);
  if (avgEl) avgEl.innerText = fmtVal(avgVal);

  // Screen scale factor & margins for high-contrast labels
  const leftMargin = 85 * dpr;
  const rightMargin = 32 * dpr;
  const topMargin = 28 * dpr;
  const bottomMargin = 36 * dpr;
  const plotW = Math.max(10, w - leftMargin - rightMargin);
  const plotH = Math.max(10, h - topMargin - bottomMargin);

  // Safe range to prevent flatline / divide-by-zero
  let range = maxVal - minVal;
  if (range <= 0.5) {
    range = 4.0;
    minVal = curVal - 2.0;
    maxVal = curVal + 2.0;
  }

  // 1. Shaded warning/threshold zones
  if (sensorKey === "boost" && maxVal > 15.0) {
    const y15Norm = Math.max(0, Math.min(1, (15.0 - minVal) / range));
    const y15 = topMargin + plotH * (1 - y15Norm);
    ctx.fillStyle = "rgba(255, 51, 68, 0.12)";
    ctx.fillRect(leftMargin, topMargin, plotW, Math.max(0, y15 - topMargin));
  } else if (sensorKey === "rpm" && maxVal > 5800) {
    const yRedNorm = Math.max(0, Math.min(1, (5800 - minVal) / range));
    const yRed = topMargin + plotH * (1 - yRedNorm);
    ctx.fillStyle = "rgba(255, 51, 68, 0.12)";
    ctx.fillRect(leftMargin, topMargin, plotW, Math.max(0, yRed - topMargin));
  }

  // 2. Horizontal Gridlines & Y-Axis Numeric Labels (5 Divisions)
  const gridDivisions = 4;
  ctx.textAlign = 'right';
  ctx.textBaseline = 'middle';
  ctx.font = `bold ${Math.round(11 * dpr)}px monospace`;

  for (let step = 0; step <= gridDivisions; step++) {
    const frac = step / gridDivisions;
    const y = topMargin + plotH * (1 - frac);
    const labelVal = minVal + frac * range;

    ctx.beginPath();
    ctx.moveTo(leftMargin, y);
    ctx.lineTo(leftMargin + plotW, y);
    ctx.strokeStyle = (frac === 0 || frac === 1) ? '#2d3848' : '#192230';
    ctx.lineWidth = 1 * dpr;
    if (frac > 0 && frac < 1) {
      ctx.setLineDash([4 * dpr, 4 * dpr]);
    } else {
      ctx.setLineDash([]);
    }
    ctx.stroke();
    ctx.setLineDash([]);

    ctx.fillStyle = (frac === 1 && maxVal > 15 && sensorKey === "boost") ? '#ff3344' : '#8c9ba5';
    let yLabelStr = "";
    if (sensorKey === "boost") {
      yLabelStr = labelVal >= 0 ? `+${labelVal.toFixed(1)} PSI` : `${Math.round(labelVal)} inHg`;
    } else if (sensorKey === "rpm" || sensorKey === "speed") {
      yLabelStr = `${Math.round(labelVal)} ${sensor.unit}`;
    } else {
      yLabelStr = `${labelVal.toFixed(1)} ${sensor.unit}`;
    }
    ctx.fillText(yLabelStr, leftMargin - 10 * dpr, y);
  }

  // 3. X-Axis Time Markers along bottom (-60s, -45s, -30s, -15s, NOW)
  const timePoints = [
    { frac: 0.0, label: "-60s" },
    { frac: 0.25, label: "-45s" },
    { frac: 0.50, label: "-30s" },
    { frac: 0.75, label: "-15s" },
    { frac: 1.0, label: "NOW" }
  ];

  ctx.textAlign = 'center';
  ctx.textBaseline = 'top';
  ctx.font = `bold ${Math.round(11 * dpr)}px monospace`;
  timePoints.forEach(tp => {
    const x = leftMargin + tp.frac * plotW;
    ctx.beginPath();
    ctx.moveTo(x, topMargin + plotH);
    ctx.lineTo(x, topMargin + plotH + 5 * dpr);
    ctx.strokeStyle = '#2d3848';
    ctx.lineWidth = 1 * dpr;
    ctx.stroke();

    ctx.fillStyle = tp.frac === 1.0 ? sensor.color : '#657786';
    ctx.fillText(tp.label, x, topMargin + plotH + 8 * dpr);
  });

  // 4. Horizontal Current-Value Guideline across the graph
  const curNorm = Math.max(0, Math.min(1, (curVal - minVal) / range));
  const curY = topMargin + plotH * (1 - curNorm);
  ctx.beginPath();
  ctx.moveTo(leftMargin, curY);
  ctx.lineTo(leftMargin + plotW, curY);
  ctx.strokeStyle = sensor.color + "99";
  ctx.lineWidth = 1.5 * dpr;
  ctx.setLineDash([4 * dpr, 4 * dpr]);
  ctx.stroke();
  ctx.setLineDash([]);

  // 5. Waveform Path Points (Right-Anchored to NOW)
  const pts = [];
  const count = data.length;
  for (let i = 0; i < count; i++) {
    const offsetFromNow = (count - 1) - i;
    const x = leftMargin + plotW - (offsetFromNow / (HISTORY_LENGTH - 1)) * plotW;
    const norm = Math.max(0, Math.min(1, (data[i] - minVal) / range));
    const y = topMargin + plotH * (1 - norm);
    pts.push({ x, y });
  }

  // 6. Area Gradient Fill under active waveform
  if (pts.length > 1) {
    ctx.beginPath();
    ctx.moveTo(pts[0].x, topMargin + plotH);
    ctx.lineTo(pts[0].x, pts[0].y);
    for (let i = 1; i < pts.length; i++) {
      ctx.lineTo(pts[i].x, pts[i].y);
    }
    ctx.lineTo(pts[pts.length - 1].x, topMargin + plotH);
    ctx.closePath();

    const areaGrad = ctx.createLinearGradient(0, topMargin, 0, topMargin + plotH);
    areaGrad.addColorStop(0, sensor.color + "55");
    areaGrad.addColorStop(1, sensor.color + "02");
    ctx.fillStyle = areaGrad;
    ctx.fill();
  }

  // 7. Thick Glowing Neon Waveform Trace
  if (pts.length > 1) {
    ctx.beginPath();
    ctx.moveTo(pts[0].x, pts[0].y);
    for (let i = 1; i < pts.length; i++) {
      ctx.lineTo(pts[i].x, pts[i].y);
    }
    ctx.strokeStyle = sensor.color;
    ctx.lineWidth = 4 * dpr;
    ctx.lineCap = 'round';
    ctx.lineJoin = 'round';
    ctx.shadowColor = sensor.color;
    ctx.shadowBlur = 12 * dpr;
    ctx.stroke();
    ctx.shadowBlur = 0;
  }

  // 8. Live Head-Marker: Concentric Pulsing Dot on newest value (NOW)
  if (pts.length > 0) {
    const lastPt = pts[pts.length - 1];
    ctx.beginPath();
    ctx.arc(lastPt.x, lastPt.y, 8 * dpr, 0, Math.PI * 2);
    ctx.fillStyle = sensor.color + "55";
    ctx.fill();
    ctx.beginPath();
    ctx.arc(lastPt.x, lastPt.y, 4 * dpr, 0, Math.PI * 2);
    ctx.fillStyle = "#ffffff";
    ctx.fill();
  }
}


// --- 6. GAUGE SETTINGS MODAL (1 to 8 Gauges) ---

function openConfigModal() {
  document.getElementById('configModal').style.display = 'flex';
  updateLayoutButtons();
  renderSlotDropdowns();
}

function closeConfigModal() {
  document.getElementById('configModal').style.display = 'none';
}

function selectLayout(num) {
  currentLayout = num;
  updateLayoutButtons();
  renderSlotDropdowns();
}

function updateLayoutButtons() {
  [1, 2, 3, 4, 6, 8].forEach(n => {
    const btn = document.getElementById(`opt_${n}`);
    if (btn) btn.className = `layout-opt-btn ${n === currentLayout ? 'selected' : ''}`;
  });
}

function renderSlotDropdowns() {
  const container = document.getElementById('slotSelectorsGrid');
  container.innerHTML = '';

  for (let i = 0; i < currentLayout; i++) {
    const item = document.createElement('div');
    item.className = 'slot-item';

    let selectHtml = `<select class="slot-dropdown" onchange="changeSlot(${i}, this.value)">`;
    Object.keys(SENSORS).forEach(k => {
      selectHtml += `<option value="${k}" ${k === currentSlots[i] ? 'selected' : ''}>${SENSORS[k].name}</option>`;
    });
    selectHtml += `</select>`;

    item.innerHTML = `<span class="slot-label">Slot #${i + 1}</span> ${selectHtml}`;
    container.appendChild(item);
  }
}

function changeSlot(idx, sensorKey) {
  currentSlots[idx] = sensorKey;
}

function applyGaugeConfig() {
  initGaugeGrid();
  closeConfigModal();
}


// --- 7. DYNAMIC AI COMPANION (M.A.I.A. / J.A.R.V.I.S. / PIT WALL) ---

function getPersonaDisplayName(pKey) {
  if (!pKey) pKey = currentAiSettings.personality || 'MAIA';
  if (pKey === 'JARVIS') return 'J.A.R.V.I.S.';
  if (pKey === 'RACE_ENGINEER' || pKey === 'PITWALL') return 'PIT WALL';
  return 'M.A.I.A.';
}

function updatePersonaUI(personaKey) {
  if (!personaKey) personaKey = currentAiSettings.personality || 'MAIA';
  currentAiSettings.personality = personaKey;

  let displayName = "M.A.I.A.";
  let subtitleText = "MultiAir Intelligent Assistant • Dynamic Personal Companion";
  let statusBadgeText = "M.A.I.A. ACTIVE";
  let cardTitleText = "M.A.I.A. COMPANION";
  let bannerQuote = "M.A.I.A.: Ready for a pull?";
  let icon = "🤖";

  if (personaKey === 'JARVIS') {
    displayName = "J.A.R.V.I.S.";
    subtitleText = "Just A Rather Very Intelligent System • Tactical Cockpit Butler";
    statusBadgeText = "J.A.R.V.I.S. READY";
    cardTitleText = "J.A.R.V.I.S. COCKPIT";
    bannerQuote = "J.A.R.V.I.S.: All cockpit systems nominal, Sir.";
    icon = "🛡️";
  } else if (personaKey === 'RACE_ENGINEER' || personaKey === 'PITWALL') {
    displayName = "PIT WALL";
    subtitleText = "F1 Telemetry & Race Engineer • Performance Strategist";
    statusBadgeText = "PIT WALL READY";
    cardTitleText = "PIT WALL STRATEGY";
    bannerQuote = "PIT WALL: Radio check. Telemetry green, box this lap if needed.";
    icon = "🏎️";
  }

  // 1. Update Bottom Navigation Dock Button
  const dockBtn = document.getElementById('dockBtnAI');
  if (dockBtn) dockBtn.innerText = `${icon} ${displayName}`;

  // 2. Update AI Chat Header Title & Subtitle
  const titleEl = document.getElementById('chatAssistantTitle');
  if (titleEl) titleEl.innerText = `${displayName} Copilot`;

  const subEl = document.getElementById('chatAssistantSubtitle');
  if (subEl) subEl.innerText = subtitleText;

  // 3. Update Chat Input Placeholder
  const inputEl = document.getElementById('chatInput');
  if (inputEl) inputEl.placeholder = `Talk to ${displayName} (or say '${displayName}' to speak)...`;

  // 4. Update Home Screen Card & Badges
  const homeBadge = document.getElementById('homeAiStatusBadge');
  if (homeBadge) homeBadge.innerText = statusBadgeText;

  const homeCardTitle = document.getElementById('homeAiCardTitle');
  if (homeCardTitle) homeCardTitle.innerText = cardTitleText;

  const homeCardIcon = document.getElementById('homeAiCardIcon');
  if (homeCardIcon) {
    const avatarEl = document.getElementById('homeAiAvatarImg');
    if (avatarEl) {
      avatarEl.src = avatarPath;
    } else {
      homeCardIcon.innerHTML = `<img id="homeAiAvatarImg" src="${avatarPath}" class="home-waifu-avatar" alt="Avatar">`;
    }
  }

  const homeQuote = document.getElementById('homeBannerAiQuote');
  if (homeQuote) homeQuote.innerText = bannerQuote;

  // 5. Update Dropdown Selectors
  const chatSelect = document.getElementById('personaSelector');
  if (chatSelect && chatSelect.value !== personaKey) chatSelect.value = personaKey;

  // 6. Update Settings Screen Labels & Profile Hints
  const profileCardTitle = document.getElementById('settingsProfileCardTitle');
  if (profileCardTitle) profileCardTitle.innerHTML = `<span>👤</span> DRIVER PROFILE & WHAT ${displayName} CALLS YOU`;

  const profileHint = document.getElementById('settingsProfileHint');
  if (profileHint) profileHint.innerText = `${displayName} WILL ADDRESS YOU AS:`;

  // 7. Update Persona Avatars & Custom Boot Media
  const pData = (window.allPersonas && window.allPersonas[personaKey]) ? window.allPersonas[personaKey] : null;
  const avatarPath = (pData && pData.avatar_image) ? pData.avatar_image : 'assets/pics/maia_avatar.jpg';
  const splashImg = (pData && pData.boot_splash_image) ? pData.boot_splash_image : 'assets/pics/splash.png';
  const splashVid = (pData && pData.boot_splash_video) ? pData.boot_splash_video : '';

  const avatarElements = [
    document.getElementById('homeAiAvatarImg'),
    document.getElementById('chatAssistantAvatar'),
    document.getElementById('homeBannerAiAvatar'),
    document.getElementById('aiToastAvatar'),
    document.getElementById('settingsAvatarPreview')
  ];
  avatarElements.forEach(el => {
    if (el) el.src = avatarPath;
  });

  const settName = document.getElementById('settingsPersonaName');
  if (settName) settName.innerText = pData ? `${pData.name} (${pData.full_name || pData.name})` : displayName;
  const settArch = document.getElementById('settingsPersonaArchetype');
  if (settArch) settArch.innerText = pData ? (pData.archetype || pData.desc) : subtitleText;
  const settSelect = document.getElementById('settingsPersonaSelector');
  if (settSelect && settSelect.value !== personaKey) settSelect.value = personaKey;
  const cfgAvatar = document.getElementById('cfgPersonaAvatar');
  if (cfgAvatar) cfgAvatar.value = avatarPath;
  const cfgSplashImg = document.getElementById('cfgBootSplashImage');
  if (cfgSplashImg) cfgSplashImg.value = splashImg;
  const cfgSplashVid = document.getElementById('cfgBootSplashVideo');
  if (cfgSplashVid) cfgSplashVid.value = splashVid;
}

// --- PERSONA BOOT SPLASH & AI ACTION CONTROLLER ---
let bootSplashTimer = null;
let bootSplashDismissed = false;

function initBootSplash() {
  const overlay = document.getElementById('bootSplashOverlay');
  if (!overlay) return;

  const bar = document.getElementById('bootSplashProgressBar');
  const statusEl = document.getElementById('bootSplashStatus');
  const imgEl = document.getElementById('bootSplashImage');
  const videoEl = document.getElementById('bootSplashVideo');
  const titleEl = document.getElementById('bootSplashPersonaName');
  const subEl = document.getElementById('bootSplashSubtitle');

  const pKey = currentAiSettings.personality || 'MAIA';
  const pName = getPersonaDisplayName(pKey);
  if (titleEl) titleEl.innerText = `${pName} v1.0.0`;
  if (subEl) subEl.innerText = `${pName} • MultiAir In-Dash System Initializing`;

  const pData = (window.allPersonas && window.allPersonas[pKey]) ? window.allPersonas[pKey] : null;
  if (pData) {
    if (pData.boot_splash_video && videoEl) {
      videoEl.src = pData.boot_splash_video;
      videoEl.style.display = 'block';
      if (imgEl) imgEl.style.display = 'none';
      videoEl.play().catch(e => console.log("[SPLASH] Video play:", e));
    } else if (pData.boot_splash_image && imgEl) {
      imgEl.src = pData.boot_splash_image;
      imgEl.style.display = 'block';
      if (videoEl) videoEl.style.display = 'none';
    }
  }

  const steps = [
    { pct: 15, delay: 100, text: "CHECKING CAN BUS AND OBD-II LINK..." },
    { pct: 40, delay: 500, text: "CALIBRATING MULTIAIR C635 PROFILES..." },
    { pct: 70, delay: 1100, text: "CONNECTING LOCAL NEURAL ENGINE (QWEN-3B)..." },
    { pct: 90, delay: 1700, text: `${pName} ONLINE • DEVOTED TO ${getDriverDisplayAddress()}` },
    { pct: 100, delay: 2200, text: "COCKPIT READY" }
  ];

  steps.forEach(s => {
    setTimeout(() => {
      if (bootSplashDismissed) return;
      if (bar) bar.style.width = `${s.pct}%`;
      if (statusEl) statusEl.innerText = s.text;
    }, s.delay);
  });

  // If no boot splash video is configured, dismiss immediately to main menu!
  if (!pData || !pData.boot_splash_video) {
    setTimeout(() => {
      dismissBootSplash();
    }, 150);
  } else {
    bootSplashTimer = setTimeout(() => {
      dismissBootSplash();
    }, 4000);
  }
}

function dismissBootSplash() {
  if (bootSplashDismissed) return;
  bootSplashDismissed = true;
  if (bootSplashTimer) clearTimeout(bootSplashTimer);
  const overlay = document.getElementById('bootSplashOverlay');
  if (overlay) {
    overlay.classList.add('hidden');
    overlay.style.pointerEvents = 'none';
    overlay.style.opacity = '0';
    setTimeout(() => {
      overlay.style.display = 'none';
    }, 350);
  }
}

function previewBootSplash() {
  const overlay = document.getElementById('bootSplashOverlay');
  if (!overlay) return;
  overlay.style.display = 'flex';
  overlay.classList.remove('hidden');
  bootSplashDismissed = false;
  initBootSplash();
}

function onSettingsPersonaChanged(pKey) {
  changePersona(pKey);
}

function savePersonaMediaConfig() {
  const pKey = currentAiSettings.personality || 'MAIA';
  const avatar = document.getElementById('cfgPersonaAvatar')?.value || 'assets/pics/maia_avatar.jpg';
  const splashImg = document.getElementById('cfgBootSplashImage')?.value || 'assets/pics/splash.png';
  const splashVid = document.getElementById('cfgBootSplashVideo')?.value || '';

  if (window.allPersonas && window.allPersonas[pKey]) {
    window.allPersonas[pKey].avatar_image = avatar;
    window.allPersonas[pKey].boot_splash_image = splashImg;
    window.allPersonas[pKey].boot_splash_video = splashVid;
  }
  updatePersonaUI(pKey);
  showToastNotification(`Persona ${pKey} Media Saved!`);
}

function handleAiAction(action) {
  if (!action) return;
  console.log("[AI COCKPIT ACTION]", action);
  if (typeof stopScreensaver === 'function') stopScreensaver();
  
  if (action.type === 'navigate') {
    const validScreens = ['home', 'gauges', 'ai', 'media', 'games', 'settings'];
    if (validScreens.includes(action.target)) {
      navigateTo(action.target);
    }
  } else if (action.type === 'launch') {
    if (action.target === 'kodi') {
      launchKodi();
    } else if (action.target === 'vlc') {
      launchVlc();
    } else if (action.target === 'retroarch') {
      launchRetroArch();
    }
  } else if (action.type === 'action') {
    if (action.target === 'diagnostics') {
      openDtcScanModal();
    }
  }
}

function fetchAiHistory() {
  fetch('/api/ai/history')
    .then(r => r.json())
    .then(data => {
      renderChatMessages(data.chat_history || []);
      renderSpeechLogs(data.speech_log || []);
      if (data.personalities) {
        window.allPersonas = data.personalities;
        const sel = document.getElementById('personaSelector');
        const settSel = document.getElementById('settingsPersonaSelector');
        const keys = Object.keys(data.personalities);
        const optionsHtml = keys.map(k => {
          const p = data.personalities[k];
          return `<option value="${k}">${p.name} (${p.full_name || p.name})</option>`;
        }).join('');
        if (sel) sel.innerHTML = optionsHtml;
        if (settSel) settSel.innerHTML = optionsHtml;
      }
      if (data.settings) {
        currentAiSettings = data.settings;
        syncSettingsUI();
        updatePersonaUI(data.settings.personality);
      }
    })
    .catch(err => console.error("[AI] History fetch error:", err));
}

function renderChatMessages(history) {
  const container = document.getElementById('aiChatMessages');
  if (!container) return;
  container.innerHTML = '';
  const currentName = getPersonaDisplayName(currentAiSettings.personality);

  if (history.length === 0) {
    const addr = getDriverDisplayAddress();
    container.innerHTML = `
      <div class="chat-bubble maia">
        <strong>${currentName}:</strong> Hey ${addr}, cockpit systems are loaded and ready. Talk to me or tap any of the quick prompts below!
        <div class="chat-time">Just now</div>
      </div>
    `;
    return;
  }

  history.forEach(msg => {
    const bubble = document.createElement('div');
    bubble.className = `chat-bubble ${msg.role === 'user' ? 'user' : 'maia'}`;
    const namePrefix = msg.role === 'user' ? 'You' : currentName;
    bubble.innerHTML = `
      <div><strong>${namePrefix}:</strong> ${msg.text}</div>
      <div class="chat-time">${msg.time || ''}</div>
    `;
    container.appendChild(bubble);
  });

  scrollChatToBottom();
}

function renderSpeechLogs(logs) {
  const container = document.getElementById('speechLogList');
  const countEl = document.getElementById('speechLogCount');
  if (!container) return;
  container.innerHTML = '';

  if (countEl) countEl.innerText = `${logs.length} Events`;

  if (logs.length === 0) {
    container.innerHTML = `<div style="font-size:11px; color:var(--text-secondary); padding:10px;">No speech events logged yet.</div>`;
    return;
  }

  // Show newest on top
  const reversed = [...logs].reverse();
  reversed.forEach(item => {
    const div = document.createElement('div');
    div.className = 'log-item';
    const pillColor = item.source === 'COPILOT' ? 'var(--accent-blue)' : 'var(--accent-pink)';
    div.style.borderLeftColor = pillColor;
    div.innerHTML = `
      <div style="display:flex; justify-content:space-between; margin-bottom:2px;">
        <span style="font-size:9px; font-weight:800; color:${pillColor};">${item.source}</span>
        <span class="log-time">${item.time_str}</span>
      </div>
      <div style="color:#fff; line-height:1.3;">${item.text}</div>
    `;
    container.appendChild(div);
  });
}

function appendSpeechLogItem(item) {
  if (!item || (!item.speech && !item.text && !item.hud_message)) return;
  const container = document.getElementById('speechLogList');
  if (!container) return;

  if (container.innerText.includes('No speech events')) {
    container.innerHTML = '';
  }

  const div = document.createElement('div');
  div.className = 'log-item new-entry';
  const pillColor = item.source === 'CHAT' ? 'var(--accent-pink)' : (item.type === 'CRITICAL' ? 'var(--accent-red)' : 'var(--accent-blue)');
  div.style.borderLeftColor = pillColor;
  const timeStr = item.time_str || new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
  const src = item.source || item.type || 'COPILOT';
  const text = item.speech || item.text || item.hud_message;

  div.innerHTML = `
    <div style="display:flex; justify-content:space-between; margin-bottom:2px;">
      <span style="font-size:9px; font-weight:800; color:${pillColor};">${src}</span>
      <span class="log-time">${timeStr}</span>
    </div>
    <div style="color:#fff; line-height:1.3;">${text}</div>
  `;

  // Prepend so newest is directly visible at the top
  container.insertBefore(div, container.firstChild);

  while (container.children.length > 60) {
    container.removeChild(container.lastChild);
  }

  const countEl = document.getElementById('speechLogCount');
  if (countEl) {
    countEl.innerText = `${container.children.length} Events`;
  }
}

function scrollChatToBottom() {
  const container = document.getElementById('aiChatMessages');
  if (container) {
    container.scrollTop = container.scrollHeight;
  }
}

function handleChatSubmit(e) {
  if (e) e.preventDefault();
  const input = document.getElementById('chatInput');
  const text = input.value.trim();
  if (!text) return;

  sendChatMessage(text);
  input.value = '';
}

function sendQuickPrompt(promptText) {
  sendChatMessage(promptText);
}

function sendChatMessage(userText) {
  const container = document.getElementById('aiChatMessages');
  const sendBtn = document.getElementById('sendBtn');
  const currentName = getPersonaDisplayName(currentAiSettings.personality);

  // Immediately append user message
  const userBubble = document.createElement('div');
  userBubble.className = 'chat-bubble user';
  userBubble.innerHTML = `<div><strong>You:</strong> ${userText}</div><div class="chat-time">Sending...</div>`;
  container.appendChild(userBubble);
  scrollChatToBottom();

  if (sendBtn) {
    sendBtn.disabled = true;
    sendBtn.innerText = "THINKING...";
  }

  fetch('/api/ai/chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message: userText })
  })
    .then(r => r.json())
    .then(data => {
      if (sendBtn) {
        sendBtn.disabled = false;
        sendBtn.innerText = "SEND";
      }

      const p = data.persona || data.personality || currentAiSettings.personality;
      const respName = getPersonaDisplayName(p);

      // Append Assistant response bubble
      const maiaBubble = document.createElement('div');
      maiaBubble.className = 'chat-bubble maia';
      maiaBubble.innerHTML = `<div><strong>${respName}:</strong> ${data.reply}</div><div class="chat-time">Just now</div>`;
      container.appendChild(maiaBubble);
      scrollChatToBottom();

      // Update home banner quote
      const homeQuote = document.getElementById('homeBannerAiQuote');
      if (homeQuote) homeQuote.innerText = `${respName}: ${data.reply.slice(0, 48)}...`;

      // Execute dashboard action (screen switch or app launcher)
      if (data.action) {
        handleAiAction(data.action);
      }

      // Update waifu emotion & HUD
      if (data.emotion) {
        setWaifuEmotion(data.emotion);
      }
      // Note: Backend /api/ai/chat already spoke clean_reply via state.audio.speak()

      // Add to speech log
      appendSpeechLogItem({
        source: 'CHAT',
        time_str: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' }),
        text: data.reply
      });
    })
    .catch(err => {
      console.error("[AI] Chat error:", err);
      if (sendBtn) {
        sendBtn.disabled = false;
        sendBtn.innerText = "SEND";
      }
    });
}

function clearChatHistory() {
  const container = document.getElementById('aiChatMessages');
  if (container) {
    const addr = getDriverDisplayAddress();
    const currentName = getPersonaDisplayName(currentAiSettings.personality);
    container.innerHTML = `
      <div class="chat-bubble maia">
        <strong>${currentName}:</strong> Chat cleared, ${addr}. Fresh start! What are we doing next?
        <div class="chat-time">Just now</div>
      </div>
    `;
  }
}

function changePersona(personaKey) {
  updatePersonaUI(personaKey);

  fetch('/api/ai/settings', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ personality: personaKey })
  }).then(() => fetchAiHistory());
}

function cycleVoiceMode() {
  if (currentVoiceMode === "COPILOT") {
    setVoiceVerbosity("ALERTS_ONLY");
  } else if (currentVoiceMode === "ALERTS_ONLY") {
    setVoiceVerbosity("MUTED");
  } else {
    setVoiceVerbosity("COPILOT");
  }
}

function setVoiceVerbosity(mode) {
  currentVoiceMode = mode.toUpperCase();
  const btn = document.getElementById('voiceModeBtn');
  if (btn) {
    if (currentVoiceMode === "ALERTS_ONLY") {
      btn.innerText = "⚠️ AI: ALERTS ONLY";
      btn.style.color = "var(--accent-yellow)";
      btn.style.borderColor = "var(--accent-yellow)";
    } else if (currentVoiceMode === "MUTED") {
      btn.innerText = "🔇 AI: MUTED";
      btn.style.color = "var(--text-secondary)";
      btn.style.borderColor = "var(--text-secondary)";
    } else {
      btn.innerText = "🏎️ AI: COPILOT";
      btn.style.color = "var(--accent-blue)";
      btn.style.borderColor = "var(--accent-blue)";
    }
  }

  // Sync Settings Radios
  const rAlerts = document.getElementById('radioVoiceAlerts');
  const rCopilot = document.getElementById('radioVoiceCopilot');
  const rMuted = document.getElementById('radioVoiceMuted');
  if (rAlerts) rAlerts.checked = (currentVoiceMode === "ALERTS_ONLY");
  if (rCopilot) rCopilot.checked = (currentVoiceMode === "COPILOT");
  if (rMuted) rMuted.checked = (currentVoiceMode === "MUTED");

  fetch(`/api/ai/voice_mode?mode=${currentVoiceMode}`);
}

function showAiSpeechToast(speech) {
  const toast = document.getElementById('aiToast');
  const textEl = document.getElementById('aiText');
  if (!toast || !textEl) return;

  textEl.innerText = speech;
  toast.classList.add('show');

  // Note: showAiSpeechToast is purely a visual HUD banner.
  // Speech playback is handled by backend or explicit speakUtterance to prevent double-talk.

  setTimeout(() => toast.classList.remove('show'), 6500);
}

function speakUtterance(text, emotion) {
  if (!text || currentVoiceMode === "MUTED") return;

  if (emotion) {
    setWaifuEmotion(emotion);
  }

  // Fallback timer only if SSE stream is disconnected
  const estimatedDurationMs = Math.max(2200, (text.length / 9.5) * 1000 + 300);
  waifuSpeechEndTime = Date.now() + estimatedDurationMs;
  const stage = document.getElementById('waifuStage');

  if (!eventSource || eventSource.readyState !== 1) {
    isWaifuSpeaking = true;
    if (stage) stage.classList.add('speaking');
    setTimeout(() => {
      if (stage) stage.classList.remove('speaking');
      setWaifuEmotion("DEVOTED");
      isWaifuSpeaking = false;
    }, estimatedDurationMs);
  }

  // Avatar CSS voice pulse
  const avatarEls = [
    document.getElementById('chatAssistantAvatar'),
    document.getElementById('homeAiAvatarImg')
  ];
  avatarEls.forEach(el => el && el.classList.add('waifu-speaking'));
  setTimeout(() => {
    avatarEls.forEach(el => el && el.classList.remove('waifu-speaking'));
  }, estimatedDurationMs);

  // 2. Play via Backend Piper TTS out of HDMI Monitor Speakers
  fetch('/api/ai/speak', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text: text })
  }).catch(() => {});

  // 3. Fallback browser SpeechSynthesis for desktop PC preview
  if ('speechSynthesis' in window) {
    try {
      window.speechSynthesis.cancel();
      const utterance = new SpeechSynthesisUtterance(text);
      const p = currentAiSettings.personality || 'MAIA';
      if (p === 'JARVIS') {
        utterance.rate = 0.96; utterance.pitch = 0.90;
      } else if (p === 'RACE_ENGINEER' || p === 'PITWALL') {
        utterance.rate = 1.14; utterance.pitch = 1.0;
      } else {
        utterance.rate = 1.06; utterance.pitch = 1.28;
      }
      window.speechSynthesis.speak(utterance);
    } catch (e) {}
  }
}

// --- HANDS-FREE WAKE WORD & LIVE CONVERSATION ENGINE ---
let isWakeWordEnabled = true;
let isLiveConvoMode = false;
let speechRecognition = null;

function initSpeechRecognition() {
  const SpeechRec = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SpeechRec) {
    console.warn("[VOICE] SpeechRecognition API not supported on this device/browser.");
    const btn = document.getElementById('btnWakeWord');
    if (btn) btn.style.display = 'none';
    const cBtn = document.getElementById('btnLiveConvo');
    if (cBtn) cBtn.style.display = 'none';
    return;
  }

  try {
    speechRecognition = new SpeechRec();
    speechRecognition.continuous = true;
    speechRecognition.interimResults = false;
    speechRecognition.lang = 'en-US';

    speechRecognition.onresult = function(event) {
      for (let i = event.resultIndex; i < event.results.length; ++i) {
        if (event.results[i].isFinal) {
          const transcript = event.results[i][0].transcript.trim().toLowerCase();
          console.log("[VOICE] Heard audio:", transcript);
          handleSpokenTranscript(transcript);
        }
      }
    };

    speechRecognition.onerror = function(err) {
      if (err.error !== 'no-speech') {
        console.warn("[VOICE] Speech listener note:", err.error);
      }
    };

    speechRecognition.onend = function() {
      // Automatically keep listening if wake word or live conversation is enabled
      if (isWakeWordEnabled || isLiveConvoMode) {
        setTimeout(() => {
          try { speechRecognition.start(); } catch (e) {}
        }, 300);
      }
    };

    if (isWakeWordEnabled) {
      try { speechRecognition.start(); } catch (e) {}
      console.log("[VOICE] Wake word continuous listener active.");
    }
  } catch (e) {
    console.warn("[VOICE] Failed to start speech recognition:", e);
  }
}

function handleSpokenTranscript(text) {
  if (!text) return;
  const persona = currentAiSettings.personality || 'MAIA';
  let wakeWords = ['maia', 'maya', 'hey maia', 'hey maya'];
  if (persona === 'JARVIS') wakeWords = ['jarvis', 'hey jarvis'];
  else if (persona === 'RACE_ENGINEER' || persona === 'PITWALL') wakeWords = ['pit wall', 'box box', 'radio'];

  let matched = false;
  let query = text;

  if (isLiveConvoMode) {
    // In live conversation mode, everything spoken while active is processed
    matched = true;
    wakeWords.forEach(w => {
      if (query.startsWith(w)) query = query.replace(w, '').trim();
    });
  } else {
    // Check for wake word prefix
    for (const w of wakeWords) {
      if (text.includes(w)) {
        matched = true;
        const idx = text.indexOf(w);
        query = text.substring(idx + w.length).replace(/^[,.\s]+/, '').trim();
        break;
      }
    }
  }

  if (matched) {
    if (!query || query.length < 2) {
      const addr = getDriverDisplayAddress();
      speakUtterance(`Yes ${addr}? I'm listening.`);
      return;
    }
    console.log(`[VOICE] Wake word triggered query: "${query}"`);
    sendChatMessage(query);
  }
}

function toggleWakeWordListening() {
  isWakeWordEnabled = !isWakeWordEnabled;
  const btn = document.getElementById('btnWakeWord');
  if (btn) {
    btn.innerText = isWakeWordEnabled ? "🎤 WAKE WORD: ON" : "🎤 WAKE WORD: OFF";
    btn.style.color = isWakeWordEnabled ? "var(--accent-pink)" : "var(--text-secondary)";
    btn.style.borderColor = isWakeWordEnabled ? "var(--accent-pink)" : "var(--panel-border)";
  }
  if (speechRecognition) {
    if (isWakeWordEnabled) {
      try { speechRecognition.start(); } catch (e) {}
    } else if (!isLiveConvoMode) {
      try { speechRecognition.stop(); } catch (e) {}
    }
  }
}

function toggleLiveConversationMode() {
  isLiveConvoMode = !isLiveConvoMode;
  const btn = document.getElementById('btnLiveConvo');
  if (btn) {
    btn.innerText = isLiveConvoMode ? "💬 CONVO: ACTIVE" : "💬 CONVO MODE";
    btn.style.color = isLiveConvoMode ? "var(--accent-green)" : "var(--text-secondary)";
    btn.style.borderColor = isLiveConvoMode ? "var(--accent-green)" : "var(--panel-border)";
  }
  if (isLiveConvoMode && speechRecognition) {
    try { speechRecognition.start(); } catch (e) {}
  }
}


// --- 8. POWERTRAIN DIAGNOSTICS & FAULT CODES (OBD-II) ---

let latestActiveDTCs = [];
let currentDTCExplanation = null;

function onMilBadgeClicked() {
  if (latestActiveDTCs && latestActiveDTCs.length > 0) {
    lookupAndShowAIReport(latestActiveDTCs[0]);
  } else {
    showDiagnosticsModal();
  }
}

function lookupAndShowAIReport(code) {
  fetch(`/api/dtc/lookup?code=${code}`)
    .then(r => r.json())
    .then(data => {
      currentDTCExplanation = data;
      document.getElementById('diagCodeTitle').innerText = `${data.code}: ${data.title}`;
      document.getElementById('diagCodeSubtitle').innerText = "DODGE DART 1.4L TURBO MULTIAIR • MAGNETI MARELLI 8GM";

      const badge = document.getElementById('diagSeverityBadge');
      badge.innerText = data.severity_badge || "INSPECT FAULT";
      badge.style.color = data.severity_color || "var(--accent-yellow)";
      badge.style.borderColor = data.severity_color || "var(--accent-yellow)";
      badge.style.background = (data.severity_color || "#ffaa00") + "22";

      document.getElementById('diagDescription').innerText = `${data.description} ${data.advice}`;
      document.getElementById('diagCauses').innerText = data.common_causes;

      document.getElementById('aiMechanicModal').style.display = 'flex';
    })
    .catch(err => console.error("[DTC] Lookup error:", err));
}

function closeAiMechanicModal() {
  document.getElementById('aiMechanicModal').style.display = 'none';
}

function speakActiveDiag() {
  if (currentDTCExplanation) {
    speakUtterance(currentDTCExplanation.spoken_summary);
  }
}

function clearActiveDTCAndClose() {
  clearDTC();
  closeAiMechanicModal();
}

function injectDTC(code) {
  fetch(`/api/dtc/inject?code=${code}`)
    .then(r => r.json())
    .then(() => {
      document.getElementById('milBadge').classList.add('show');
      document.getElementById('milText').innerText = `CHECK ENGINE: ${code}`;
      closeAiMechanicModal();
      setTimeout(() => lookupAndShowAIReport(code), 300);
    })
    .catch(err => console.error("[DTC] Inject error:", err));
}

function clearDTC() {
  fetch(`/api/dtc/clear`)
    .then(r => r.json())
    .then(() => {
      latestActiveDTCs = [];
      document.getElementById('milBadge').classList.remove('show');
      const homeDtc = document.getElementById('homeDtcBadge');
      if (homeDtc) {
        homeDtc.innerText = "ECU: HEALTHY";
        homeDtc.style.color = "var(--accent-green)";
        homeDtc.style.borderColor = "var(--accent-green)";
      }
      closeAiMechanicModal();
    })
    .catch(err => console.error("[DTC] Clear error:", err));
}

function showDiagnosticsModal() {
  lookupAndShowAIReport("P0299");
}


// --- 9. IN-CAR MEDIA PLAYER (REAL AUDIO STREAMING) ---
const realAudio = new Audio();
let realPlaylist = [];
let realTrackIdx = 0;

function initRealAudioPlayer() {
  realAudio.addEventListener('timeupdate', () => {
    if (!realAudio.duration) return;
    const elapsedEl = document.getElementById('trackElapsed');
    const durationEl = document.getElementById('trackDuration');
    const trackBar = document.getElementById('mediaTrackBar');

    const cur = Math.floor(realAudio.currentTime);
    const dur = Math.floor(realAudio.duration);

    if (elapsedEl) {
      const min = Math.floor(cur / 60);
      const sec = cur % 60;
      elapsedEl.innerText = `${min}:${sec < 10 ? '0' : ''}${sec}`;
    }
    if (durationEl) {
      const dMin = Math.floor(dur / 60);
      const dSec = dur % 60;
      durationEl.innerText = `${dMin}:${dSec < 10 ? '0' : ''}${dSec}`;
    }
    if (trackBar && !trackBar.dataset.seeking) {
      trackBar.value = Math.round((realAudio.currentTime / realAudio.duration) * 100);
    }
  });

  realAudio.addEventListener('play', () => {
    const playBtn = document.getElementById('playPauseBtn');
    if (playBtn) playBtn.innerText = "⏸️";
    renderRealTracklist();
  });

  realAudio.addEventListener('pause', () => {
    const playBtn = document.getElementById('playPauseBtn');
    if (playBtn) playBtn.innerText = "▶️";
    renderRealTracklist();
  });

  realAudio.addEventListener('ended', () => {
    nextTrack();
  });

  // Track bar scrubber input
  const trackBar = document.getElementById('mediaTrackBar');
  if (trackBar) {
    trackBar.addEventListener('input', () => {
      trackBar.dataset.seeking = "true";
    });
    trackBar.addEventListener('change', () => {
      if (realAudio.duration) {
        realAudio.currentTime = (trackBar.value / 100) * realAudio.duration;
      }
      delete trackBar.dataset.seeking;
    });
  }

  // Volume bar
  const volBar = document.getElementById('mediaVolBar');
  const volLabel = document.getElementById('volLabel');
  if (volBar) {
    volBar.addEventListener('input', (e) => {
      const val = parseInt(e.target.value);
      realAudio.volume = val / 100;
      if (volLabel) volLabel.innerText = `${val}%`;
    });
    realAudio.volume = (parseInt(volBar.value) || 80) / 100;
  }

  fetchMediaPlaylist();
}

function fetchMediaPlaylist() {
  fetch('/api/media/playlist')
    .then(r => r.json())
    .then(tracks => {
      if (tracks && tracks.length > 0) {
        realPlaylist = tracks;
        renderRealTracklist();
        loadTrack(0, false);
      }
    })
    .catch(err => console.warn("[MEDIA] Playlist fetch error:", err));
}

function renderRealTracklist() {
  const container = document.getElementById('mediaTrackList');
  const countEl = document.getElementById('tracklistCount');
  if (countEl) countEl.innerText = `${realPlaylist.length} Tracks`;
  if (!container) return;

  container.innerHTML = realPlaylist.map((t, idx) => `
    <div class="track-list-item ${idx === realTrackIdx ? 'active' : ''}" style="display:flex; align-items:center; justify-content:space-between; padding:6px 10px; border-radius:6px; background:${idx === realTrackIdx ? 'rgba(0,176,255,0.15)' : 'rgba(255,255,255,0.03)'}; border-left:${idx === realTrackIdx ? '3px solid var(--accent-blue)' : '3px solid transparent'}; cursor:pointer; margin-bottom:4px;" onclick="selectTrack(${idx})">
      <div style="display:flex; align-items:center; gap:8px; overflow:hidden;">
        <span style="font-size:12px;">${idx === realTrackIdx && !realAudio.paused ? '🔊' : '🎵'}</span>
        <div style="overflow:hidden;">
          <div style="font-size:11px; font-weight:800; color:#fff; white-space:nowrap; text-overflow:ellipsis; overflow:hidden;">${t.title}</div>
          <div style="font-size:9px; color:var(--text-secondary); white-space:nowrap; text-overflow:ellipsis; overflow:hidden;">${t.artist} • ${t.size_mb} MB</div>
        </div>
      </div>
      <button class="cluster-action-btn" style="padding:2px 8px; font-size:9px; background:${idx === realTrackIdx && !realAudio.paused ? 'var(--accent-blue)' : '#222'}; color:#fff;">${idx === realTrackIdx && !realAudio.paused ? 'PLAYING' : 'PLAY'}</button>
    </div>
  `).join('');
}

function loadTrack(idx, autoPlay = true) {
  if (idx < 0 || idx >= realPlaylist.length) return;
  realTrackIdx = idx;
  const t = realPlaylist[realTrackIdx];

  const titleEl = document.getElementById('trackTitle');
  const artistEl = document.getElementById('trackArtist');
  if (titleEl) titleEl.innerText = t.title;
  if (artistEl) artistEl.innerText = t.artist;

  realAudio.src = t.stream_url;
  renderRealTracklist();

  if (autoPlay) {
    realAudio.play().catch(e => console.warn("Audio play error:", e));
  }
}

function selectTrack(idx) {
  loadTrack(idx, true);
}

function togglePlayPause() {
  if (!realAudio.src && realPlaylist.length > 0) {
    loadTrack(realTrackIdx, true);
    return;
  }
  if (realAudio.paused) {
    realAudio.play().catch(e => console.warn("Audio play error:", e));
  } else {
    realAudio.pause();
  }
}

function nextTrack() {
  if (realPlaylist.length === 0) return;
  realTrackIdx = (realTrackIdx + 1) % realPlaylist.length;
  loadTrack(realTrackIdx, true);
}

function prevTrack() {
  if (realPlaylist.length === 0) return;
  realTrackIdx = (realTrackIdx - 1 + realPlaylist.length) % realPlaylist.length;
  loadTrack(realTrackIdx, true);
}

// --- SCREENSAVER & VIDEO MEDIA CONTROLLER ---

let screensaverConfig = {
  enabled: false,
  timeoutSec: 0,
  type: "SLIDESHOW", // "SLIDESHOW", "VIDEO", "AUTO"
  folderPath: "/home/nfgodin/Pictures",
  videoFile: ""
};

function loadScreensaverConfig() {
  try {
    const saved = localStorage.getItem('carpi5_screensaver_cfg');
    if (saved) {
      screensaverConfig = Object.assign(screensaverConfig, JSON.parse(saved));
    } else {
      screensaverConfig.enabled = false;
      screensaverConfig.timeoutSec = 0;
      localStorage.setItem('carpi5_screensaver_cfg', JSON.stringify(screensaverConfig));
    }
  } catch (e) {}

  syncScreensaverUI();
}

function syncScreensaverUI() {
  const btn = document.getElementById('btnToggleScreensaverActive');
  if (btn) {
    btn.innerText = screensaverConfig.enabled ? "● SCREENSAVER: ENABLED" : "○ SCREENSAVER: OFF (DISABLED)";
    btn.style.color = screensaverConfig.enabled ? "var(--accent-green)" : "var(--text-secondary)";
    btn.style.borderColor = screensaverConfig.enabled ? "var(--accent-green)" : "#283340";
    btn.style.background = screensaverConfig.enabled ? "rgba(0, 230, 118, 0.15)" : "#161c24";
  }

  const timeoutEl = document.getElementById('cfgScreensaverTimeout');
  if (timeoutEl) timeoutEl.value = screensaverConfig.timeoutSec;

  const typeEl = document.getElementById('cfgScreensaverType');
  if (typeEl) typeEl.value = screensaverConfig.type;

  const folderEl = document.getElementById('cfgScreensaverFolder');
  if (folderEl) folderEl.value = screensaverConfig.folderPath || "";

  const videoEl = document.getElementById('cfgScreensaverVideoFile');
  if (videoEl) videoEl.value = screensaverConfig.videoFile || "";
}

function toggleScreensaverActive() {
  screensaverConfig.enabled = !screensaverConfig.enabled;
  saveScreensaverConfig();
}

function saveScreensaverConfig() {
  const timeoutEl = document.getElementById('cfgScreensaverTimeout');
  if (timeoutEl) screensaverConfig.timeoutSec = parseInt(timeoutEl.value) || 60;

  const typeEl = document.getElementById('cfgScreensaverType');
  if (typeEl) screensaverConfig.type = typeEl.value;

  const folderEl = document.getElementById('cfgScreensaverFolder');
  if (folderEl) screensaverConfig.folderPath = folderEl.value.trim();

  const videoEl = document.getElementById('cfgScreensaverVideoFile');
  if (videoEl) screensaverConfig.videoFile = videoEl.value.trim();

  try {
    localStorage.setItem('carpi5_screensaver_cfg', JSON.stringify(screensaverConfig));
  } catch (e) {}

  syncScreensaverUI();
}

function openFileExplorerForScreensaver() {
  openFileExplorer();
}

function startScreensaver() {
  if (!screensaverConfig.enabled) return;

  const overlay = document.getElementById('fullScreensaver');
  if (!overlay) return;
  overlay.classList.add('active');

  const img = document.getElementById('screensaverMainImg');
  const video = document.getElementById('screensaverVideo');

  updateScreensaverClock();

  // Check if video mode is chosen
  const isVideoMode = (screensaverConfig.type === 'VIDEO') || 
                      (screensaverConfig.type === 'AUTO' && screensaverConfig.videoFile);

  if (isVideoMode && video) {
    if (img) img.style.display = 'none';
    video.style.display = 'block';

    if (screensaverConfig.videoFile && screensaverConfig.videoFile.length > 3) {
      if (!video.src.includes(screensaverConfig.videoFile)) {
        video.src = screensaverConfig.videoFile;
      }
    }
    video.currentTime = 0;
    if (typeof video.play === 'function') {
      video.play().catch(e => console.log("[SCREENSAVER] Video autoplay note:", e));
    }
  } else {
    if (video) {
      if (typeof video.pause === 'function') video.pause();
      video.style.display = 'none';
    }
    if (img) {
      img.style.display = 'block';
      img.src = screensaverImages[currentImageIdx];
    }

    if (screensaverInterval) clearInterval(screensaverInterval);
    screensaverInterval = setInterval(() => {
      updateScreensaverClock();
      currentImageIdx = (currentImageIdx + 1) % screensaverImages.length;
      if (img) img.src = screensaverImages[currentImageIdx];
    }, 8000);
  }
}

function stopScreensaver() {
  const overlay = document.getElementById('fullScreensaver');
  if (overlay) overlay.classList.remove('active');

  const video = document.getElementById('screensaverVideo');
  if (video) {
    if (typeof video.pause === 'function') video.pause();
    video.currentTime = 0;
  }

  if (screensaverInterval) clearInterval(screensaverInterval);
  resetIdleTimer();
}

function updateScreensaverClock() {
  const clockEl = document.getElementById('screensaverClock');
  if (clockEl) {
    const now = new Date();
    clockEl.innerText = formatClockTime(now, true);
  }
}

function resetIdleTimer() {
  lastInteractionTime = Date.now();
}

['touchstart', 'mousedown', 'keydown'].forEach(evt => {
  window.addEventListener(evt, resetIdleTimer, { passive: true });
});

// Auto-Screensaver Idle Check (Respects Parked state and disabled config)
setInterval(() => {
  if (!screensaverConfig.enabled || screensaverConfig.timeoutSec <= 0) return;
  if (currentScreen === "gauges") return;

  const elapsedSec = (Date.now() - lastInteractionTime) / 1000;
  const isParked = !latestTelemetry || latestTelemetry.speed_mph < 1;

  if (elapsedSec >= screensaverConfig.timeoutSec && isParked) {
    const overlay = document.getElementById('fullScreensaver');
    if (overlay && !overlay.classList.contains('active')) {
      startScreensaver();
    }
  }
}, 4000);


// --- TELEMETRY MODE (TEST SIMULATION VS REAL VEHICLE OBD-II / CAN) ---
let currentTelemetryMode = "TEST";

function fetchTelemetryMode() {
  fetch('/api/telemetry/mode')
    .then(r => r.json())
    .then(data => syncTelemetryModeUI(data))
    .catch(err => console.error("[TELEM MODE] Fetch error:", err));
}

function syncTelemetryModeUI(data) {
  if (!data) return;
  currentTelemetryMode = data.mode || (data.test_mode ? "TEST" : "REAL");

  const badge = document.getElementById('telemetryModeBadge');
  const statusMsg = document.getElementById('telemStatusMsg');
  const chkTest = document.getElementById('chkTestMode');

  if (chkTest) {
    chkTest.checked = (currentTelemetryMode === 'TEST');
  }

  if (currentTelemetryMode === 'REAL') {
    if (badge) {
      badge.innerText = "● LIVE VEHICLE OBD-II";
      badge.style.color = "var(--accent-green)";
      badge.style.background = "rgba(0, 230, 118, 0.15)";
    }
    if (statusMsg) {
      statusMsg.innerText = data.status_message || (data.connected ? "Connected to Dodge Dart Magneti Marelli 8GM ECU." : "Direct OBD-II vehicle interface active (Resting / Disconnected).");
      statusMsg.style.color = data.connected ? "var(--accent-green)" : "var(--text-secondary)";
    }
  } else {
    if (badge) {
      badge.innerText = "🧪 BENCH SIMULATION";
      badge.style.color = "var(--accent-yellow)";
      badge.style.background = "rgba(255, 196, 0, 0.15)";
    }
    if (statusMsg) {
      statusMsg.innerText = "Bench simulation active. Generating synthetic 1.4L MultiAir boost and RPM telemetry.";
      statusMsg.style.color = "var(--accent-yellow)";
    }
  }
}

function toggleTestModeCheckbox(isChecked) {
  const targetMode = isChecked ? 'TEST' : 'REAL';
  fetch('/api/telemetry/mode', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ mode: targetMode, test_mode: isChecked })
  })
    .then(r => r.json())
    .then(data => syncTelemetryModeUI(data))
    .catch(err => console.error("[TELEM MODE] Toggle checkbox error:", err));
}

function setTelemetryMode(mode) {
  const isTest = (mode === 'TEST');
  toggleTestModeCheckbox(isTest);
}

function toggleTelemetryMode() {
  const targetMode = currentTelemetryMode === 'REAL' ? 'TEST' : 'REAL';
  toggleTestModeCheckbox(targetMode === 'TEST');
}

function confirmResetToDefaults() {
  fetch('/api/settings/reset', { method: 'POST' })
    .then(r => r.json())
    .then(data => {
      console.log("[SETTINGS] Factory reset response:", data);
      try {
        localStorage.clear();
      } catch (e) {}

      // Force Screensaver OFF in localStorage and state
      screensaverConfig = {
        enabled: false,
        timeoutSec: 0,
        type: "SLIDESHOW",
        folderPath: "/home/nfgodin/Pictures",
        videoFile: ""
      };
      localStorage.setItem('carpi5_screensaver_cfg', JSON.stringify(screensaverConfig));
      syncScreensaverUI();

      // Reset Clock Format to 12-Hour AM/PM
      is24HourClock = false;
      localStorage.setItem('carpi5_clock_24h', 'false');
      const btnClock = document.getElementById('btnClockFormat');
      if (btnClock) btnClock.innerText = "CLOCK: 12-HOUR (AM/PM)";

      // Reset Driver Profile to Master Creator
      driverTitle = "Master";
      driverName = "Creator";
      localStorage.setItem('carpi5_driver_title', 'Master');
      localStorage.setItem('carpi5_driver_name', 'Creator');
      const inTitle = document.getElementById('cfgDriverTitle');
      const inName = document.getElementById('cfgDriverName');
      if (inTitle) inTitle.value = "Master";
      if (inName) inName.value = "Creator";
      updateAddressPreview();

      // Reset Telemetry Mode to REAL
      currentTelemetryMode = "REAL";
      syncTelemetryModeUI({ mode: "REAL", test_mode: false, connected: false, status_message: "Direct OBD-II vehicle interface active (Resting / Disconnected)." });

      // Reset Waifu Emotion & Spoken Toast
      setWaifuEmotion("DEVOTED");
      const msg = "Factory defaults restored! Cockpit ready, Master Creator.";
      showAiSpeechToast(msg);
      speakUtterance(msg, "DEVOTED");
    })
    .catch(err => {
      console.error("[SETTINGS] Factory reset failed:", err);
      alert("Failed to reset settings: " + err);
    });
}

// --- 10. SYSTEM SETTINGS & TAILSCALE OLLAMA INTEGRATION ---

function selectAiMode(mode) {
  currentAiSettings.mode = mode;
  document.getElementById('radioTailscale').checked = (mode === 'TAILSCALE_OLLAMA');
  document.getElementById('radioLocal').checked = (mode === 'LOCAL_OLLAMA');
  document.getElementById('radioCloud').checked = (mode === 'CLOUD_API');
  document.getElementById('radioBuiltin').checked = (mode === 'BUILTIN');

  const tailscaleRow = document.getElementById('tailscaleRow');
  const cloudRow = document.getElementById('cloudApiKeyRow');

  if (tailscaleRow) tailscaleRow.style.display = (mode === 'TAILSCALE_OLLAMA') ? 'flex' : 'none';
  if (cloudRow) cloudRow.style.display = (mode === 'CLOUD_API') ? 'flex' : 'none';
}

function syncSettingsUI() {
  selectAiMode(currentAiSettings.mode || 'BUILTIN');

  const ipEl = document.getElementById('cfgTailscaleIp');
  const portEl = document.getElementById('cfgTailscalePort');
  const modelEl = document.getElementById('cfgOllamaModel');
  const keyEl = document.getElementById('cfgApiKey');
  const personaEl = document.getElementById('personaSelector');
  const titleInput = document.getElementById('cfgDriverTitle');
  const nameInput = document.getElementById('cfgDriverName');

  if (titleInput) titleInput.value = (currentAiSettings.driver_title !== undefined) ? currentAiSettings.driver_title : "Master";
  if (nameInput) nameInput.value = (currentAiSettings.driver_name !== undefined) ? currentAiSettings.driver_name : "Creator";

  // Highlight active title preset chip (ONLY Master or None)
  const t = (currentAiSettings.driver_title || "").toLowerCase();
  const chipMaster = document.getElementById('chipTitleMaster');
  const chipNone = document.getElementById('chipTitleNone');
  if (chipMaster && chipNone) {
    if (t === 'master') {
      chipMaster.classList.add('active');
      chipNone.classList.remove('active');
    } else if (t === '') {
      chipNone.classList.add('active');
      chipMaster.classList.remove('active');
    } else {
      chipMaster.classList.remove('active');
      chipNone.classList.remove('active');
    }
  }

  updateAddressPreview();

  if (ipEl && currentAiSettings.tailscale_ip) ipEl.value = currentAiSettings.tailscale_ip;
  if (portEl && currentAiSettings.tailscale_port) portEl.value = currentAiSettings.tailscale_port;
  if (modelEl && currentAiSettings.ollama_model) modelEl.value = currentAiSettings.ollama_model;
  if (keyEl && currentAiSettings.api_key) keyEl.value = currentAiSettings.api_key;
  if (personaEl && currentAiSettings.personality) personaEl.value = currentAiSettings.personality;

  // Header pill
  const pill = document.getElementById('headerTailscalePill');
  if (pill) {
    if (currentAiSettings.mode === 'BUILTIN') {
      pill.innerText = `🧠 AI: OFFLINE (DEFAULT)`;
      pill.style.color = "var(--accent-green)";
      pill.style.borderColor = "var(--accent-green)";
    } else if (currentAiSettings.mode === 'TAILSCALE_OLLAMA') {
      pill.innerText = `⚡ TAILSCALE: CONNECTED`;
      pill.style.color = "var(--accent-blue)";
      pill.style.borderColor = "var(--accent-blue)";
    } else if (currentAiSettings.mode === 'LOCAL_OLLAMA') {
      pill.innerText = `💻 LOCAL OLLAMA`;
      pill.style.color = "var(--accent-yellow)";
      pill.style.borderColor = "var(--accent-yellow)";
    } else if (currentAiSettings.mode === 'CLOUD_API') {
      pill.innerText = `☁️ CLOUD API`;
      pill.style.color = "var(--accent-pink)";
      pill.style.borderColor = "var(--accent-pink)";
    }
  }
}

function setTitlePreset(preset) {
  const titleInput = document.getElementById('cfgDriverTitle');
  if (titleInput) titleInput.value = preset;

  const chipMaster = document.getElementById('chipTitleMaster');
  const chipNone = document.getElementById('chipTitleNone');
  if (chipMaster && chipNone) {
    if (preset.toLowerCase() === 'master') {
      chipMaster.classList.add('active');
      chipNone.classList.remove('active');
    } else if (preset === '') {
      chipNone.classList.add('active');
      chipMaster.classList.remove('active');
    } else {
      chipMaster.classList.remove('active');
      chipNone.classList.remove('active');
    }
  }
  updateAddressPreview();
}

function updateAddressPreview() {
  const titleInput = document.getElementById('cfgDriverTitle');
  const nameInput = document.getElementById('cfgDriverName');
  const preview = document.getElementById('driverAddressPreview');
  const contextBadge = document.getElementById('contextMoniker');

  const title = (titleInput ? titleInput.value.trim() : (currentAiSettings.driver_title || ""));
  const name = (nameInput ? nameInput.value.trim() : (currentAiSettings.driver_name || ""));

  let full = "";
  if (title && name) full = `${title} ${name}`;
  else if (name) full = name;
  else if (title) full = title;
  else full = "Master";

  if (preview) preview.innerText = full;
  if (contextBadge) contextBadge.innerText = full;
  return full;
}

function saveDriverProfile() {
  const titleInput = document.getElementById('cfgDriverTitle');
  const nameInput = document.getElementById('cfgDriverName');

  const title = titleInput ? titleInput.value.trim() : "Master";
  const name = nameInput ? nameInput.value.trim() : "Creator";

  fetch('/api/ai/settings', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      driver_title: title,
      driver_name: name,
      driver_moniker: name || title
    })
  })
    .then(r => r.json())
    .then(data => {
      console.log("[SETTINGS] Driver profile updated:", data);
      currentAiSettings = data.settings;
      syncSettingsUI();

      const addr = getDriverDisplayAddress();
      const ackMsg = `Understood, ${addr}. Your profile has been saved. Systems are nominal, let's ride.`;
      speakUtterance(ackMsg);
      showAiSpeechToast(ackMsg);
    })
    .catch(err => alert("Error updating driver profile: " + err));
}

function saveAiSettings() {
  const titleInput = document.getElementById('cfgDriverTitle');
  const nameInput = document.getElementById('cfgDriverName');

  const payload = {
    mode: currentAiSettings.mode,
    personality: document.getElementById('personaSelector').value,
    driver_title: titleInput ? titleInput.value.trim() : "Master",
    driver_name: nameInput ? nameInput.value.trim() : "Creator",
    driver_moniker: nameInput ? nameInput.value.trim() : "Creator",
    tailscale_ip: document.getElementById('cfgTailscaleIp').value.trim(),
    tailscale_port: parseInt(document.getElementById('cfgTailscalePort').value) || 11434,
    ollama_model: document.getElementById('cfgOllamaModel').value,
    api_key: document.getElementById('cfgApiKey').value.trim()
  };

  fetch('/api/ai/settings', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  })
    .then(r => r.json())
    .then(data => {
      console.log("[SETTINGS] Saved successfully:", data);
      currentAiSettings = data.settings;
      syncSettingsUI();
      alert("Settings saved! Driver profile, Tailscale, and AI configuration updated.");
    })
    .catch(err => alert("Error saving settings: " + err));
}

function loadAiSettings() {
  fetch('/api/ai/settings')
    .then(r => r.json())
    .then(data => {
      if (data) {
        currentAiSettings = Object.assign(currentAiSettings, data);
        syncSettingsUI();
      }
    })
    .catch(err => console.warn("[SETTINGS] Fetch error:", err));
}

// --- 11. FILE EXPLORER & USB STORAGE CONTROLLER ---

let detectedDevices = [];
let currentExplorerPath = "";
let fileClipboard = null; // { path, name, is_dir }
let editingFilePath = "";

function checkUsbDevices() {
  fetch('/api/fs/devices')
    .then(r => r.json())
    .then(devices => {
      detectedDevices = devices || [];
      updateUsbIndicatorUI();
      renderHomeDrivesShelf();
    })
    .catch(err => console.warn("[FS] USB poll error:", err));
}

function updateUsbIndicatorUI() {
  const pill = document.getElementById('headerUsbPill');
  const text = document.getElementById('headerUsbText');
  const badge = document.getElementById('homeUsbBadge');

  if (!pill) return;

  if (detectedDevices.length > 0) {
    pill.style.display = 'flex';
    const removable = detectedDevices.find(d => d.is_removable) || detectedDevices[0];
    const shortLabel = removable.label || removable.name.split(' ')[0];
    if (text) text.innerText = `USB: ${shortLabel} (${removable.total_gb.toFixed(0)}GB)`;
    if (badge) {
      badge.innerText = `💾 USB: ${detectedDevices.length} READY`;
      badge.style.color = "var(--accent-green)";
      badge.style.borderColor = "var(--accent-green)";
    }
  } else {
    pill.style.display = 'none';
    if (badge) {
      badge.innerText = `💾 USB: STANDBY`;
      badge.style.color = "var(--text-secondary)";
      badge.style.borderColor = "var(--panel-border)";
    }
  }
}

function renderHomeDrivesShelf() {
  const shelf = document.getElementById('homeDrivesShelf');
  const list = document.getElementById('drivesShelfList');
  const countLabel = document.getElementById('drivesCountLabel');

  if (!shelf || !list) return;

  if (detectedDevices.length === 0) {
    shelf.style.display = 'none';
    return;
  }

  shelf.style.display = 'flex';
  if (countLabel) countLabel.innerText = `${detectedDevices.length} Storage Device${detectedDevices.length > 1 ? 's' : ''} Connected`;

  list.innerHTML = detectedDevices.map(dev => {
    const isUsb = dev.is_removable;
    const icon = isUsb ? '💾' : '💽';
    const cleanPath = dev.path.replace(/\\/g, '/');
    return `
      <div class="drive-card-mini" onclick="openFileExplorer('${cleanPath}')" title="Click to browse ${dev.name}">
        <span class="drive-icon">${icon}</span>
        <div class="drive-details">
          <span class="drive-label">${dev.name}</span>
          <span class="drive-space">${dev.free_gb.toFixed(1)} GB Free of ${dev.total_gb.toFixed(1)} GB</span>
        </div>
      </div>
    `;
  }).join('');
}

function openFileExplorer(targetPath) {
  const modal = document.getElementById('fileExplorerModal');
  if (modal) modal.style.display = 'flex';

  renderExplorerDeviceTabs();

  if (targetPath) {
    currentExplorerPath = targetPath;
  } else if (!currentExplorerPath) {
    currentExplorerPath = (detectedDevices[0] && detectedDevices[0].path) || "";
  }

  loadExplorerDirectory(currentExplorerPath);
}

function closeFileExplorer() {
  const modal = document.getElementById('fileExplorerModal');
  if (modal) modal.style.display = 'none';
}

function renderExplorerDeviceTabs() {
  const tabsContainer = document.getElementById('explorerDeviceTabs');
  if (!tabsContainer) return;

  tabsContainer.innerHTML = detectedDevices.map(dev => {
    const isUsb = dev.is_removable;
    const icon = isUsb ? '💾' : '💽';
    const cleanPath = dev.path.replace(/\\/g, '/');
    const isActive = currentExplorerPath.replace(/\\/g, '/').startsWith(cleanPath);
    return `
      <button class="device-tab-btn ${isActive ? 'active' : ''}" onclick="openFileExplorer('${cleanPath}')">
        <span>${icon}</span> ${dev.label || dev.name} (${dev.free_gb.toFixed(0)}G Free)
      </button>
    `;
  }).join('');
}

function loadExplorerDirectory(dirPath) {
  currentExplorerPath = dirPath || "";
  const pathDisplay = document.getElementById('explorerCurrentPath');
  const fileList = document.getElementById('explorerFileList');
  const footerStatus = document.getElementById('explorerFooterStatus');

  if (pathDisplay) pathDisplay.innerText = currentExplorerPath || "Drive Root";
  if (fileList) fileList.innerHTML = '<div style="color:var(--text-secondary); padding:24px; text-align:center;">Scanning storage...</div>';

  renderExplorerDeviceTabs();

  fetch(`/api/fs/list?path=${encodeURIComponent(currentExplorerPath)}`)
    .then(r => r.json())
    .then(data => {
      if (data.error) {
        if (fileList) fileList.innerHTML = `<div style="color:var(--accent-red); padding:20px;">Error reading folder: ${data.error}</div>`;
        return;
      }

      currentExplorerPath = data.path;
      if (pathDisplay) pathDisplay.innerText = currentExplorerPath;

      const items = data.items || [];
      const folders = items.filter(i => i.is_dir);
      const files = items.filter(i => !i.is_dir);

      if (footerStatus) {
        footerStatus.innerText = `${items.length} items (${folders.length} folders, ${files.length} files)`;
      }

      if (items.length === 0) {
        if (fileList) fileList.innerHTML = '<div style="color:var(--text-secondary); padding:30px; text-align:center;">(Empty folder)</div>';
        return;
      }

      let html = '';

      // Render Folders First
      folders.forEach(item => {
        const cleanPath = item.path.replace(/\\/g, '/');
        html += `
          <div class="explorer-item-row" onclick="loadExplorerDirectory('${cleanPath}')">
            <div class="item-left">
              <span class="item-icon">📁</span>
              <div>
                <div class="item-name" style="color:var(--accent-yellow);">${item.name}</div>
                <div class="item-meta">Directory • ${item.modified || ''}</div>
              </div>
            </div>
            <div class="item-actions" onclick="event.stopPropagation()">
              <button class="item-action-btn" onclick="copyExplorerItem('${cleanPath}', '${item.name}', true)" title="Copy folder">📋 COPY</button>
              <button class="item-action-btn" style="color:var(--accent-red);" onclick="deleteExplorerItem('${cleanPath}', '${item.name}')" title="Delete folder">🗑️ DEL</button>
            </div>
          </div>
        `;
      });

      // Render Files
      files.forEach(item => {
        const cleanPath = item.path.replace(/\\/g, '/');
        const ext = item.ext ? item.ext.toLowerCase() : '';
        let icon = '📄';
        let isEditable = false;
        let isAudio = false;
        let isVideo = false;
        let isRom = false;

        if (['.cfg', '.json', '.txt', '.ini', '.py', '.sh', '.log', '.md', '.conf'].includes(ext)) {
          icon = '📝';
          isEditable = true;
        } else if (['.mp3', '.wav', '.flac', '.ogg', '.aac', '.m4a'].includes(ext)) {
          icon = '🎵';
          isAudio = true;
        } else if (['.mp4', '.mkv', '.avi', '.mov', '.webm'].includes(ext)) {
          icon = '🎬';
          isVideo = true;
        } else if (['.sfc', '.smc', '.nes', '.gba', '.bin', '.iso', '.zip', '.7z'].includes(ext)) {
          icon = '🕹️';
          isRom = true;
        }

        const sizeFormatted = (item.size > 1048576) ? `${(item.size / 1048576).toFixed(1)} MB` : `${Math.ceil(item.size / 1024)} KB`;

        html += `
          <div class="explorer-item-row" ${isEditable ? `onclick="openFileEditor('${cleanPath}')"` : ''}>
            <div class="item-left">
              <span class="item-icon">${icon}</span>
              <div>
                <div class="item-name">${item.name}</div>
                <div class="item-meta">${sizeFormatted} • ${item.modified || ''}</div>
              </div>
            </div>
            <div class="item-actions" onclick="event.stopPropagation()">
              ${isEditable ? `<button class="item-action-btn" style="color:var(--accent-blue); border-color:var(--accent-blue);" onclick="openFileEditor('${cleanPath}')">✏️ EDIT</button>` : ''}
              ${isRom ? `<button class="item-action-btn" style="color:var(--accent-purple);" onclick="launchRetroArch()">▶ PLAY</button>` : ''}
              ${isAudio ? `<button class="item-action-btn" style="color:var(--accent-green);" onclick="navigateTo('media')">▶ PLAY</button>` : ''}
              ${isVideo ? `<button class="item-action-btn" style="color:#ff7700;" onclick="showPlaceholderModal('VLC Player', 'Playing ${item.name} via VLC GPU acceleration')">🎬 VLC</button>` : ''}
              <button class="item-action-btn" onclick="copyExplorerItem('${cleanPath}', '${item.name}', false)" title="Copy file">📋 COPY</button>
              <button class="item-action-btn" style="color:var(--accent-red);" onclick="deleteExplorerItem('${cleanPath}', '${item.name}')" title="Delete file">🗑️ DEL</button>
            </div>
          </div>
        `;
      });

      if (fileList) fileList.innerHTML = html;
    })
    .catch(err => {
      console.error("[FS] Directory read error:", err);
      if (fileList) fileList.innerHTML = `<div style="color:var(--accent-red); padding:20px;">Network error loading directory: ${err}</div>`;
    });
}

function navigateExplorerUp() {
  if (!currentExplorerPath) return;
  const p = currentExplorerPath.replace(/\\/g, '/').replace(/\/+$/, '');
  const lastSlash = p.lastIndexOf('/');
  if (lastSlash > 0) {
    const parent = p.substring(0, lastSlash);
    loadExplorerDirectory(parent);
  } else if (lastSlash === 0) {
    loadExplorerDirectory('/');
  }
}

function promptNewFolder() {
  const name = window.prompt("Enter new folder name (e.g. snes_roms, logs, tuning):");
  if (!name || !name.trim()) return;

  fetch('/api/fs/mkdir', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ parent_dir: currentExplorerPath, name: name.trim() })
  })
    .then(r => r.json())
    .then(res => {
      if (res.error) alert("Error creating folder: " + res.error);
      else loadExplorerDirectory(currentExplorerPath);
    })
    .catch(err => alert("Failed to create folder: " + err));
}

function copyExplorerItem(itemPath, itemName, isDir) {
  fileClipboard = { path: itemPath, name: itemName, is_dir: isDir };
  const pasteBtn = document.getElementById('explorerPasteBtn');
  if (pasteBtn) {
    pasteBtn.style.display = 'inline-flex';
    pasteBtn.innerText = `📋 PASTE (${itemName.substring(0, 14)})`;
  }
  showAiSpeechToast(`Copied "${itemName}" to clipboard`);
}

function pasteFileClipboard() {
  if (!fileClipboard) return;

  fetch('/api/fs/copy', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ src: fileClipboard.path, dest_dir: currentExplorerPath })
  })
    .then(r => r.json())
    .then(res => {
      if (res.error) {
        alert("Error copying file: " + res.error);
      } else {
        showAiSpeechToast(`Pasted "${fileClipboard.name}"`);
        loadExplorerDirectory(currentExplorerPath);
      }
    })
    .catch(err => alert("Copy failed: " + err));
}

function deleteExplorerItem(itemPath, itemName) {
  if (!confirm(`Delete "${itemName}" permanently?`)) return;

  fetch('/api/fs/delete', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ path: itemPath })
  })
    .then(r => r.json())
    .then(res => {
      if (res.error) alert("Error deleting: " + res.error);
      else {
        showAiSpeechToast(`Deleted "${itemName}"`);
        loadExplorerDirectory(currentExplorerPath);
      }
    })
    .catch(err => alert("Delete failed: " + err));
}

function refreshExplorer() {
  loadExplorerDirectory(currentExplorerPath);
}

// In-Car Text / Config Editor
function openFileEditor(filePath) {
  editingFilePath = filePath;
  const modal = document.getElementById('fileEditorModal');
  const nameEl = document.getElementById('editorFileName');
  const pathEl = document.getElementById('editorFilePath');
  const textEl = document.getElementById('editorTextarea');
  const charEl = document.getElementById('editorCharCount');

  const baseName = filePath.replace(/\\/g, '/').split('/').pop();
  if (nameEl) nameEl.innerText = baseName;
  if (pathEl) pathEl.innerText = filePath;
  if (textEl) textEl.value = "Reading file from storage...";
  if (modal) modal.style.display = 'flex';

  fetch(`/api/fs/read?path=${encodeURIComponent(filePath)}`)
    .then(r => r.json())
    .then(data => {
      if (data.error) {
        if (textEl) textEl.value = `Error opening file: ${data.error}`;
      } else {
        if (textEl) textEl.value = data.content || '';
        if (charEl) charEl.innerText = `${(data.content || '').length} characters | Lines: ${(data.content || '').split('\n').length}`;
      }
    })
    .catch(err => {
      if (textEl) textEl.value = "Failed to fetch file content: " + err;
    });
}

function closeFileEditor() {
  const modal = document.getElementById('fileEditorModal');
  if (modal) modal.style.display = 'none';
  editingFilePath = "";
}

function saveFileEditorContent() {
  const textEl = document.getElementById('editorTextarea');
  if (!textEl || !editingFilePath) return;

  const content = textEl.value;
  const baseName = editingFilePath.replace(/\\/g, '/').split('/').pop();

  fetch('/api/fs/write', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ path: editingFilePath, content: content })
  })
    .then(r => r.json())
    .then(res => {
      if (res.error) {
        alert("Error saving file: " + res.error);
      } else {
        showAiSpeechToast(`Saved ${baseName} to disk`);
        closeFileEditor();
        loadExplorerDirectory(currentExplorerPath);
      }
    })
    .catch(err => alert("Save failed: " + err));
}

// --- 11. KODI, VLC & RETROARCH REAL LAUNCHERS ---

function launchKodi() {
  showAiSpeechToast("Launching Kodi Entertainment Center...");
  fetch('/api/media/launch_kodi', { method: 'POST' })
    .then(r => r.json())
    .then(data => {
      console.log("[KODI] Launch response:", data);
    })
    .catch(err => {
      alert("Failed to launch Kodi: " + err);
    });
}

function launchVlc(targetPath) {
  showAiSpeechToast("Launching VLC Video Player...");
  fetch('/api/media/launch_vlc', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ path: targetPath || '' })
  })
    .then(r => r.json())
    .then(data => {
      console.log("[VLC] Launch response:", data);
    })
    .catch(err => {
      alert("Failed to launch VLC: " + err);
    });
}

function launchRetroArch() {
  showAiSpeechToast("Launching RetroArch Emulation...");
  fetch('/api/games/launch_retroarch', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({})
  })
    .then(r => r.json())
    .then(data => {
      console.log("[RETROARCH] Launch response:", data);
    })
    .catch(err => {
      alert("Failed to launch RetroArch: " + err);
    });
}

function launchRetroArchSystem(system) {
  const cores = {
    'SNES': '/usr/lib/aarch64-linux-gnu/libretro/snes9x_libretro.so',
    'Genesis': '/usr/lib/aarch64-linux-gnu/libretro/genesis_plus_gx_libretro.so',
    'NES': '/usr/lib/aarch64-linux-gnu/libretro/nestopia_libretro.so',
    'GBA': '/usr/lib/aarch64-linux-gnu/libretro/mgba_libretro.so',
    'PS1': '/home/nfgodin/.config/retroarch/cores/pcsx_rearmed_libretro.so',
    'N64': '/home/nfgodin/.config/retroarch/cores/parallel_n64_libretro.so',
    'Arcade': '/usr/lib/aarch64-linux-gnu/libretro/gambatte_libretro.so'
  };
  const corePath = cores[system] || '';
  showAiSpeechToast(`Loading ${system} in RetroArch...`);
  fetch('/api/games/launch_retroarch', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ core: corePath })
  })
    .then(r => r.json())
    .then(data => {
      console.log(`[RETROARCH ${system}] Launch response:`, data);
    })
    .catch(err => alert(`Failed to launch ${system}: ` + err));
}

function launchStandaloneGame(game) {
  showPlaceholderModal(
    `Standalone Game: ${game}`,
    `Launching ${game} native Linux port. Gamepad controls enabled.`
  );
}

// --- 12. GENERAL PLACEHOLDER MODAL ---

function showPlaceholderModal(title, desc) {
  document.getElementById('modalTitle').innerText = title;
  document.getElementById('modalDesc').innerText = desc;
  document.getElementById('modalOverlay').style.display = 'flex';
}

function closePlaceholderModal() {
  document.getElementById('modalOverlay').style.display = 'none';
}


// --- 12. WI-FI & MOBILE HOTSPOT CONTROLLER ---

let wifiStatus = {};
let selectedWifiSsid = null;
let selectedWifiSecurity = "WPA2-Personal";

function fetchWifiStatus() {
  fetch('/api/wifi/status')
    .then(r => r.json())
    .then(data => {
      wifiStatus = data || {};
      updateWifiHeaderPill();
      updateWifiSettingsCard();
    })
    .catch(err => console.warn("[WIFI] Status error:", err));
}

function updateWifiHeaderPill() {
  const pill = document.getElementById('headerWifiPill');
  const text = document.getElementById('headerWifiText');
  const icon = document.getElementById('headerWifiIcon');
  if (!pill) return;

  if (wifiStatus.connected) {
    pill.style.borderColor = "var(--accent-green)";
    pill.style.color = "var(--accent-green)";
    const sig = wifiStatus.signal_percent ? `${wifiStatus.signal_percent}%` : "100%";
    
    // Choose signal indicator
    let sigIcon = "📶";
    if (wifiStatus.signal_percent && wifiStatus.signal_percent < 40) sigIcon = "📳";

    if (text) text.innerText = `${wifiStatus.ssid} (${sig})`;
    if (icon) icon.innerText = sigIcon;
    pill.title = `${wifiStatus.ssid} • ${sig} Signal • IP: ${wifiStatus.ip_address || 'DHCP'} • Click to open Wi-Fi Manager`;
  } else {
    pill.style.borderColor = "var(--panel-border)";
    pill.style.color = "var(--text-secondary)";
    if (text) text.innerText = "WI-FI: STANDBY";
    if (icon) icon.innerText = "📡";
    pill.title = "Wi-Fi Disconnected • Click to scan and connect";
  }
}

function updateWifiSettingsCard() {
  const ssidEl = document.getElementById('wifiCurrentSsid');
  const badgeEl = document.getElementById('wifiCurrentBadge');
  const ipEl = document.getElementById('wifiCurrentIp');
  const sigEl = document.getElementById('wifiCurrentSignal');
  const bandEl = document.getElementById('wifiCurrentBand');
  const btnAlways = document.getElementById('btnToggleAlwaysOn');

  if (ssidEl) ssidEl.innerText = wifiStatus.connected ? wifiStatus.ssid : "Disconnected";
  if (badgeEl) {
    if (wifiStatus.connected) {
      badgeEl.innerText = "CONNECTED";
      badgeEl.style.background = "rgba(0,230,118,0.15)";
      badgeEl.style.color = "var(--accent-green)";
      badgeEl.style.borderColor = "var(--accent-green)";
    } else {
      badgeEl.innerText = "STANDBY / DISCONNECTED";
      badgeEl.style.background = "rgba(140,155,165,0.15)";
      badgeEl.style.color = "var(--text-secondary)";
      badgeEl.style.borderColor = "var(--panel-border)";
    }
  }

  if (ipEl) ipEl.innerText = wifiStatus.ip_address || "--";
  if (sigEl) sigEl.innerText = (wifiStatus.connected && wifiStatus.signal_percent) ? `${wifiStatus.signal_percent}%` : "--";
  if (bandEl) bandEl.innerText = wifiStatus.band || "2.4 / 5 GHz";

  if (btnAlways) {
    if (wifiStatus.always_on) {
      btnAlways.innerText = "⚡ ALWAYS-ON: ACTIVE";
      btnAlways.style.background = "rgba(0,230,118,0.15)";
      btnAlways.style.color = "var(--accent-green)";
      btnAlways.style.borderColor = "var(--accent-green)";
    } else {
      btnAlways.innerText = "⚪ ALWAYS-ON: DISABLED";
      btnAlways.style.background = "#141922";
      btnAlways.style.color = "var(--text-secondary)";
      btnAlways.style.borderColor = "var(--panel-border)";
    }
  }
}

function scanWifiNetworks() {
  const countEl = document.getElementById('wifiScanCount');
  const listEl = document.getElementById('wifiNetworkList');

  if (countEl) countEl.innerText = "Scanning nearby networks & hotspots...";
  if (listEl) listEl.innerHTML = '<div style="color:var(--text-secondary); padding:16px; text-align:center;">Scanning 2.4GHz & 5GHz Wi-Fi and phone hotspots...</div>';

  fetch('/api/wifi/scan')
    .then(r => r.json())
    .then(networks => {
      renderWifiNetworks(networks || []);
      fetchSavedWifi();
    })
    .catch(err => {
      console.error("[WIFI] Scan error:", err);
      if (listEl) listEl.innerHTML = `<div style="color:var(--accent-red); padding:12px;">Scan error: ${err}</div>`;
    });
}

function renderWifiNetworks(networks) {
  const listEl = document.getElementById('wifiNetworkList');
  const countEl = document.getElementById('wifiScanCount');

  if (!listEl) return;
  if (countEl) countEl.innerText = `${networks.length} Network${networks.length === 1 ? '' : 's'} Found`;

  if (networks.length === 0) {
    listEl.innerHTML = '<div style="color:var(--text-secondary); padding:16px; text-align:center;">No Wi-Fi networks found. Turn on phone hotspot or check Wi-Fi antenna.</div>';
    return;
  }

  listEl.innerHTML = networks.map(net => {
    const isConn = net.connected;
    const isSaved = net.is_saved;
    const sig = net.signal || 0;
    const sec = net.security || "WPA2-Personal";

    let sigLabel = "📶 Strong";
    if (sig < 45) sigLabel = "📶 Weak";
    else if (sig < 70) sigLabel = "📶 Fair";

    return `
      <div class="wifi-network-row ${isConn ? 'connected' : ''}">
        <div style="display:flex; align-items:center; gap:10px;">
          <span style="font-size:16px;">${isConn ? '🟢' : '📶'}</span>
          <div>
            <div style="font-size:12px; font-weight:800; color:#fff;">${net.ssid}</div>
            <div style="font-size:10px; color:var(--text-secondary); display:flex; gap:8px; margin-top:2px;">
              <span>${sigLabel} (${sig}%)</span>
              <span>•</span>
              <span>🔒 ${sec}</span>
            </div>
          </div>
        </div>
        <div style="display:flex; align-items:center; gap:8px;">
          ${isSaved ? '<span style="font-size:9px; color:var(--accent-green); background:rgba(0,230,118,0.1); border:1px solid var(--accent-green); padding:2px 6px; border-radius:4px;">REMEMBERED</span>' : ''}
          ${isConn 
            ? '<span class="pill" style="background:rgba(0,230,118,0.2); color:var(--accent-green); font-size:10px;">CONNECTED</span>'
            : `<button class="cluster-action-btn" style="color:var(--accent-blue); border-color:var(--accent-blue); padding:4px 12px;" onclick="openWifiConnectModal('${net.ssid}', '${sec}')">CONNECT</button>`
          }
        </div>
      </div>
    `;
  }).join('');
}

function fetchSavedWifi() {
  const savedList = document.getElementById('wifiSavedList');
  if (!savedList) return;

  fetch('/api/wifi/saved')
    .then(r => r.json())
    .then(saved => {
      if (!saved || saved.length === 0) {
        savedList.innerHTML = '<div style="color:var(--text-secondary); font-size:11px; padding:8px;">(No saved networks or hotspots stored)</div>';
        return;
      }

      savedList.innerHTML = saved.map(net => `
        <div class="wifi-saved-row">
          <div>
            <div style="font-size:12px; font-weight:800; color:#fff;">${net.ssid}</div>
            <div style="font-size:10px; color:var(--text-secondary); margin-top:2px;">
              <span>Auto-connect: <strong style="color:var(--accent-green);">${net.auto_connect ? 'YES' : 'NO'}</strong></span>
              ${net.last_connected ? ` • Last active: ${net.last_connected}` : ''}
            </div>
          </div>
          <button class="cluster-action-btn" style="color:var(--accent-red); font-size:10px; padding:3px 8px;" onclick="forgetWifiNetwork('${net.ssid}')">
            ✕ FORGET
          </button>
        </div>
      `).join('');
    })
    .catch(err => console.warn("[WIFI] Saved list error:", err));
}

function openWifiConnectModal(ssid, security) {
  selectedWifiSsid = ssid;
  selectedWifiSecurity = security;

  const modal = document.getElementById('wifiConnectModal');
  const ssidEl = document.getElementById('modalWifiSsid');
  const secEl = document.getElementById('modalWifiSecurity');
  const pwdEl = document.getElementById('modalWifiPassword');

  if (ssidEl) ssidEl.innerText = ssid;
  if (secEl) secEl.innerText = security;
  if (pwdEl) {
    pwdEl.value = '';
    pwdEl.type = 'password';
  }
  const showChk = document.getElementById('modalWifiShowPass');
  if (showChk) showChk.checked = false;

  if (modal) modal.style.display = 'flex';
}

function closeWifiConnectModal() {
  const modal = document.getElementById('wifiConnectModal');
  if (modal) modal.style.display = 'none';
  selectedWifiSsid = null;
}

function toggleWifiPasswordVisibility() {
  const pwdEl = document.getElementById('modalWifiPassword');
  const chk = document.getElementById('modalWifiShowPass');
  if (pwdEl && chk) {
    pwdEl.type = chk.checked ? 'text' : 'password';
  }
}

function submitWifiConnect() {
  if (!selectedWifiSsid) return;

  const pwdEl = document.getElementById('modalWifiPassword');
  const autoChk = document.getElementById('modalWifiAutoConnect');
  const btn = document.getElementById('btnSubmitWifiConnect');

  const password = pwdEl ? pwdEl.value : "";
  const autoConnect = autoChk ? autoChk.checked : true;

  if (btn) {
    btn.disabled = true;
    btn.innerText = "CONNECTING...";
  }

  fetch('/api/wifi/connect', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      ssid: selectedWifiSsid,
      password: password,
      auto_connect: autoConnect
    })
  })
    .then(r => r.json())
    .then(res => {
      if (btn) {
        btn.disabled = false;
        btn.innerText = "CONNECT";
      }

      if (res.error) {
        alert("Wi-Fi Connection Error: " + res.error);
      } else {
        const msg = `Connected to ${selectedWifiSsid}! Network online.`;
        showAiSpeechToast(msg);
        speakUtterance(msg);
        closeWifiConnectModal();
        fetchWifiStatus();
        scanWifiNetworks();
      }
    })
    .catch(err => {
      if (btn) {
        btn.disabled = false;
        btn.innerText = "CONNECT";
      }
      alert("Network connect request failed: " + err);
    });
}

function forgetWifiNetwork(ssid) {
  if (!confirm(`Forget remembered network "${ssid}"?`)) return;

  fetch('/api/wifi/forget', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ssid: ssid })
  })
    .then(r => r.json())
    .then(res => {
      showAiSpeechToast(`Forgot network: ${ssid}`);
      fetchSavedWifi();
      scanWifiNetworks();
    })
    .catch(err => alert("Error forgetting network: " + err));
}

function clearAllSavedWifi() {
  if (!confirm("Are you sure you want to clear ALL saved Wi-Fi networks and remembered hotspots?")) return;

  fetch('/api/wifi/clear', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({})
  })
    .then(r => r.json())
    .then(res => {
      showAiSpeechToast("All saved networks cleared.");
      fetchSavedWifi();
      scanWifiNetworks();
    })
    .catch(err => alert("Error clearing saved networks: " + err));
}

function toggleWifiAlwaysOn() {
  const nextState = !wifiStatus.always_on;
  fetch('/api/wifi/always_on', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ enabled: nextState })
  })
    .then(r => r.json())
    .then(res => {
      wifiStatus.always_on = res.always_on;
      updateWifiSettingsCard();
      showAiSpeechToast(res.always_on ? "Wi-Fi Always-On enabled" : "Wi-Fi Always-On disabled");
    })
    .catch(err => alert("Failed to toggle Always-On: " + err));
}

function focusWifiSection() {
  const card = document.getElementById('wifiSettingsCard');
  if (card) card.scrollIntoView({ behavior: 'smooth' });
}

// --- 13. CLOCK & INITIALIZATION ---

setInterval(() => {
  const clock = document.getElementById('footerClock');
  if (clock) {
    const now = new Date();
    clock.innerText = formatClockTime(now, false);
  }
}, 1000);

// Initialize on page load
initGaugeGrid();
loadAiSettings();
fetchAiHistory();
fetchMediaPlaylist();
loadScreensaverConfig();
fetchTelemetryMode();
setInterval(fetchTelemetryMode, 5000);
initSpeechRecognition();
checkUsbDevices();
setInterval(checkUsbDevices, 5000);
fetchWifiStatus();
scanWifiNetworks();
setInterval(fetchWifiStatus, 10000);


// --- 14. O.D.I.N. INTEGRATION: HARDWARE SBC, RELAYS, ROMS & TRIP LOGS ---

// 1. SBC Health & Thermals
let latestSbcHealth = null;
function fetchSystemHealth() {
  fetch('/api/system/health')
    .then(r => r.json())
    .then(data => {
      latestSbcHealth = data;
      const pill = document.getElementById('headerSbcPill');
      const tempTxt = document.getElementById('sbcTempText');
      const tempIcon = document.getElementById('sbcTempIcon');

      if (tempTxt && typeof data.soc_temp_c === 'number') tempTxt.innerText = `${Math.round(data.soc_temp_c)}°C`;
      if (pill) {
        if (data.soc_temp_c > 75 || data.throttled) {
          pill.style.borderColor = "var(--accent-red)";
          pill.style.color = "var(--accent-red)";
          if (tempIcon) tempIcon.innerText = "🔥";
        } else if (data.soc_temp_c > 62) {
          pill.style.borderColor = "var(--accent-yellow)";
          pill.style.color = "var(--accent-yellow)";
          if (tempIcon) tempIcon.innerText = "🌡️";
        } else {
          pill.style.borderColor = "#334";
          pill.style.color = "var(--accent-green)";
          if (tempIcon) tempIcon.innerText = "🌡️";
        }
      }

      // Update modal if open
      const mTemp = document.getElementById('modalSbcTemp');
      const mTempF = document.getElementById('modalSbcTempF');
      const mCpu = document.getElementById('modalSbcCpu');
      const mRam = document.getElementById('modalSbcRam');
      const mRamPct = document.getElementById('modalSbcRamPct');
      const mUptime = document.getElementById('modalSbcUptime');
      const mThrottle = document.getElementById('modalSbcThrottleMsg');

      if (mTemp) mTemp.innerText = `${data.soc_temp_c.toFixed(1)} °C`;
      if (mTempF) mTempF.innerText = `${data.soc_temp_f.toFixed(1)} °F`;
      if (mCpu) mCpu.innerText = `${Math.round(data.cpu_pct)} %`;
      if (mRam) mRam.innerText = `${data.ram_used_mb} / ${data.ram_total_mb} MB`;
      if (mRamPct) mRamPct.innerText = `${Math.round(data.ram_pct)}% Used`;
      if (mUptime) mUptime.innerText = data.uptime_str;
      if (mThrottle) {
        mThrottle.innerText = data.throttle_message;
        mThrottle.style.color = data.throttled ? "var(--accent-red)" : (data.under_voltage ? "var(--accent-yellow)" : "var(--accent-green)");
      }
    })
    .catch(err => console.warn("[SBC] Health fetch error:", err));
}

function openSystemHealthModal() {
  const m = document.getElementById('sbcHealthModal');
  if (m) {
    m.style.display = 'flex';
    m.classList.add('open');
  }
  fetchSystemHealth();
}

function closeSystemHealthModal() {
  const m = document.getElementById('sbcHealthModal');
  if (m) {
    m.style.display = 'none';
    m.classList.remove('open');
  }
}

// 2. Hardware Brightness
function updateBrightnessFromSlider(val) {
  const pill = document.getElementById('brightnessPillVal');
  if (pill) pill.innerText = `${val}%`;
  fetch('/api/system/brightness', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ brightness: parseInt(val) })
  }).catch(err => console.warn("[BRIGHTNESS] Error:", err));
}

function setPresetBrightness(val) {
  const slider = document.getElementById('sliderBrightness');
  if (slider) slider.value = val;
  updateBrightnessFromSlider(val);
}

// 3. ROMs Library (O.D.I.N. Roms Hub)
let allRomsList = [];
let activeRomPlatform = "all";

function fetchRomsList() {
  fetch('/api/games/roms')
    .then(r => r.json())
    .then(roms => {
      allRomsList = roms || [];
      renderRomsList();
    })
    .catch(err => console.warn("[ROMS] Fetch error:", err));
}

function filterRoms(platform) {
  activeRomPlatform = platform;
  const btnContainer = document.getElementById('romFilterButtons');
  if (btnContainer) {
    const btns = btnContainer.querySelectorAll('button');
    btns.forEach(b => {
      if (b.innerText.toLowerCase() === platform.toLowerCase()) {
        b.classList.add('active');
      } else {
        b.classList.remove('active');
      }
    });
  }
  renderRomsList();
}

function renderRomsList() {
  const container = document.getElementById('romsListContainer');
  if (!container) return;

  const list = Array.isArray(allRomsList) ? allRomsList : [];
  const filtered = activeRomPlatform === "all"
    ? list
    : list.filter(r => r.platform && r.platform.toLowerCase() === activeRomPlatform.toLowerCase());

  if (filtered.length === 0) {
    container.innerHTML = '<div style="color:var(--text-secondary); font-size:12px; padding:16px; grid-column:1/-1;">No ROMs found for this platform. Place ROM files in /home/nfgodin/Roms.</div>';
    return;
  }

  container.innerHTML = filtered.map(r => `
    <div class="slot-item" style="display:flex; justify-content:space-between; align-items:center; padding:10px 14px; background:#121822;">
      <div style="display:flex; align-items:center; gap:10px; overflow:hidden;">
        <span style="font-size:18px;">${r.icon}</span>
        <div style="overflow:hidden;">
          <div style="font-size:12px; font-weight:800; color:#fff; white-space:nowrap; text-overflow:ellipsis; overflow:hidden;" title="${r.title}">${r.title}</div>
          <div style="font-size:10px; color:var(--text-secondary); display:flex; gap:6px;">
            <span style="color:var(--accent-purple); font-weight:700;">${r.platform_name}</span>
            <span>•</span>
            <span>${r.size_mb} MB</span>
          </div>
        </div>
      </div>
      <button class="cluster-action-btn" style="background:var(--accent-green); color:#000; font-weight:900; padding:6px 12px;" onclick="launchRom('${r.path.replace(/\\/g, '/')}', '${r.platform}')">
        ▶ LAUNCH
      </button>
    </div>
  `).join('');
}

function launchRom(romPath, platform) {
  showAiSpeechToast(`Launching ${platform.toUpperCase()} emulation...`);
  fetch('/api/games/launch', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ rom_path: romPath, platform: platform })
  })
  .then(r => r.json())
  .then(res => {
    if (res.status === "ok" || res.status === "simulated") {
      showAiSpeechToast(`RetroArch running: ${res.message || 'Game Active'}`);
    } else {
      alert("Error launching game: " + res.message);
    }
  })
  .catch(err => alert("Launch error: " + err));
}

// 4. 12V Relays & GPIO Header
function fetchRelaysStatus() {
  fetch('/api/gpio/relays')
    .then(r => r.json())
    .then(relays => {
      renderRelaysGrid(relays || []);
    })
    .catch(err => console.warn("[GPIO] Relays fetch error:", err));
}

function renderRelaysGrid(relays) {
  const container = document.getElementById('relayCardsGrid');
  if (!container) return;

  container.innerHTML = relays.map(r => `
    <div class="slot-item" style="border-color:${r.state ? 'var(--accent-green)' : '#263342'};">
      <div style="display:flex; align-items:center; gap:10px;">
        <span style="font-size:20px;">${r.icon}</span>
        <div>
          <div style="font-size:12px; font-weight:900; color:#fff;">${r.name}</div>
          <div style="font-size:10px; color:var(--text-secondary);">${r.desc} (BCM ${r.bcm})</div>
        </div>
      </div>
      <button class="cluster-action-btn" style="background:${r.state ? 'var(--accent-green)' : 'transparent'}; color:${r.state ? '#000' : 'var(--text-secondary)'}; font-weight:900; padding:6px 14px;" onclick="toggleRelay(${r.bcm})">
        ${r.state ? '● ACTIVE' : '○ OFF'}
      </button>
    </div>
  `).join('');
}

function toggleRelay(bcm) {
  fetch('/api/gpio/toggle', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ bcm: bcm })
  })
  .then(r => r.json())
  .then(res => {
    if (res.relays) renderRelaysGrid(res.relays);
  })
  .catch(err => console.warn("[GPIO] Toggle error:", err));
}

function triggerMorseBeacon() {
  showAiSpeechToast("Transmitting Morse SOS beacon across BCM 18...");
  fetch('/api/gpio/morse', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ bcm: 18, message: "SOS ODIN IN DISTRESS" })
  })
  .then(r => r.json())
  .then(() => showAiSpeechToast("Morse beacon broadcasting."))
  .catch(err => console.warn("[GPIO] Morse error:", err));
}

function openGpioModal() {
  const m = document.getElementById('gpioModal');
  if (m) {
    m.style.display = 'flex';
    m.classList.add('open');
  }
  fetchGpioPins();
}

function closeGpioModal() {
  const m = document.getElementById('gpioModal');
  if (m) {
    m.style.display = 'none';
    m.classList.remove('open');
  }
}

function fetchGpioPins() {
  fetch('/api/gpio/pins')
    .then(r => r.json())
    .then(pins => {
      const grid = document.getElementById('gpioPinsGrid');
      if (!grid) return;
      grid.innerHTML = pins.map(p => {
        const isGpio = p.type === "gpio";
        const color = p.state ? "var(--accent-green)" : (p.type === "power" ? "var(--accent-red)" : "var(--text-secondary)");
        return `
          <div style="background:#0c1219; border:1px solid #1c2633; padding:8px 12px; border-radius:6px; display:flex; justify-content:space-between; align-items:center; ${isGpio ? 'cursor:pointer;' : ''}" ${isGpio ? `onclick="toggleRelay(${p.bcm}); setTimeout(fetchGpioPins, 80);"` : ''}>
            <div style="display:flex; align-items:center; gap:8px;">
              <span style="font-size:10px; font-weight:900; color:#607d8b; width:22px;">P${p.pin}</span>
              <div>
                <div style="font-size:11px; font-weight:800; color:#fff;">${p.name}</div>
                <div style="font-size:9px; color:var(--text-secondary);">${p.type.toUpperCase()}${p.bcm !== null ? ` • BCM ${p.bcm}` : ''}</div>
              </div>
            </div>
            <span style="font-size:10px; font-weight:900; color:${color};">${p.state ? 'HIGH' : 'LOW'}</span>
          </div>
        `;
      }).join('');
    })
    .catch(err => console.warn("[GPIO] Pins fetch error:", err));
}

// 5. SQLite Persistent Trip Logs
function fetchTripLogs() {
  Promise.all([
    fetch('/api/trips/stats').then(r => r.json()),
    fetch('/api/trips/recent').then(r => r.json())
  ])
  .then(([stats, trips]) => {
    const statsContainer = document.getElementById('tripLifetimeStats');
    if (statsContainer) {
      statsContainer.innerHTML = `
        <div style="background:#0c1219; border:1px solid #212b38; padding:8px 12px; border-radius:8px;">
          <div style="font-size:9px; color:var(--text-secondary); font-weight:800;">TOTAL DRIVES</div>
          <div style="font-size:16px; font-weight:900; color:#fff;">${stats.total_trips || 1}</div>
        </div>
        <div style="background:#0c1219; border:1px solid #212b38; padding:8px 12px; border-radius:8px;">
          <div style="font-size:9px; color:var(--text-secondary); font-weight:800;">PEAK BOOST EVER</div>
          <div style="font-size:16px; font-weight:900; color:var(--accent-green);">+${stats.peak_boost_ever} PSI</div>
        </div>
        <div style="background:#0c1219; border:1px solid #212b38; padding:8px 12px; border-radius:8px;">
          <div style="font-size:9px; color:var(--text-secondary); font-weight:800;">TOP SPEED</div>
          <div style="font-size:16px; font-weight:900; color:var(--accent-blue);">${stats.top_speed_ever} MPH</div>
        </div>
        <div style="background:#0c1219; border:1px solid #212b38; padding:8px 12px; border-radius:8px;">
          <div style="font-size:9px; color:var(--text-secondary); font-weight:800;">LIFETIME AVG MPG</div>
          <div style="font-size:16px; font-weight:900; color:var(--accent-yellow);">${stats.lifetime_avg_mpg} MPG</div>
        </div>
      `;
    }

    const tableContainer = document.getElementById('recentTripsTableContainer');
    if (tableContainer) {
      const validTrips = Array.isArray(trips) ? trips : ((trips && trips.trips) || []);
      if (validTrips.length === 0) {
        tableContainer.innerHTML = '<div style="color:var(--text-secondary); font-size:11px; padding:8px;">No trip history recorded yet.</div>';
        return;
      }

      tableContainer.innerHTML = `
        <table style="width:100%; border-collapse:collapse; font-size:11px; text-align:left;">
          <thead>
            <tr style="border-bottom:1px solid #212b38; color:var(--text-secondary);">
              <th style="padding:6px;">DATE / TIME</th>
              <th style="padding:6px;">DURATION</th>
              <th style="padding:6px;">MAX BOOST</th>
              <th style="padding:6px;">MAX SPEED</th>
              <th style="padding:6px;">AVG MPG</th>
            </tr>
          </thead>
          <tbody>
            ${validTrips.map(t => `
              <tr style="border-bottom:1px solid #141b24;">
                <td style="padding:6px; color:#fff;">${t.start_time}</td>
                <td style="padding:6px; color:var(--text-secondary);">${t.duration_min || 1} min</td>
                <td style="padding:6px; color:var(--accent-green); font-weight:700;">+${t.max_boost_psi} PSI</td>
                <td style="padding:6px; color:var(--accent-blue); font-weight:700;">${t.max_speed_mph} MPH</td>
                <td style="padding:6px; color:var(--accent-yellow);">${t.avg_mpg} MPG</td>
              </tr>
            `).join('')}
          </tbody>
        </table>
      `;
    }
  })
  .catch(err => console.warn("[TRIP] Fetch error:", err));
}

// Hook into initial page startup
fetchSystemHealth();
setInterval(fetchSystemHealth, 3000);
fetchRelaysStatus();
fetchRomsList();
fetchTripLogs();


// Universal Kinetic Touch Drag-to-Scroll for Touchscreens
function initTouchScrollEngine() {
  document.querySelectorAll('.screen-view, .explorer-body, #screenHome').forEach(el => {
    let isDown = false;
    let startY = 0;
    let scrollTop = 0;

    el.addEventListener('pointerdown', (e) => {
      if (['BUTTON', 'INPUT', 'SELECT', 'A'].includes(e.target.tagName) || e.target.closest('button, input, select, .slot-dropdown')) return;
      isDown = true;
      startY = e.pageY;
      scrollTop = el.scrollTop;
    });

    window.addEventListener('pointerup', () => { isDown = false; });
    window.addEventListener('pointercancel', () => { isDown = false; });

    el.addEventListener('pointermove', (e) => {
      if (!isDown) return;
      e.preventDefault();
      const y = e.pageY;
      const walk = (startY - y) * 1.4; // Sliding finger UP increases scrollTop (scrolls DOWN)
      el.scrollTop = scrollTop + walk;
    }, { passive: false });
  });
}

initRealAudioPlayer();
setTimeout(initTouchScrollEngine, 500);
initBootSplash();


// --- 60 FPS PROCEDURAL ANIME WAIFU BUST ENGINE (NICK JR. "FACE" STYLE) ---
let currentWaifuEmotion = "DEVOTED";
let isWaifuSpeaking = false;
let waifuSpeechEndTime = 0;
let waifuBlinkProgress = 0.0;
let isBlinking = false;
let blinkStartTime = 0;
let nextBlinkTime = Date.now() + 3200;

// Nick Jr. Face style gaze tracking & turning (Yaw / Parallax)
let targetLookX = -0.32; // Default looking at driver on left
let targetLookY = 0.04;
let currentLookX = -0.32;
let currentLookY = 0.04;
let nextGazeShiftTime = Date.now() + 2500;

// Physics sway for blonde twin-tails
let hairSwayAngle = 0.0;
let hairSwayVelocity = 0.0;

// Dynamic blush intensity (0.0 to 1.0)
let blushIntensity = 0.4;
let touchGiggleTime = 0;

function setWaifuEmotion(emo) {
  if (!emo) return;
  const upper = emo.toUpperCase().trim();
  const validEmotions = ["DEVOTED", "FLIRTY", "EXCITED", "CONCERNED", "HAPPY"];
  if (validEmotions.includes(upper)) {
    currentWaifuEmotion = upper;
  } else {
    currentWaifuEmotion = "DEVOTED";
  }

  const pill = document.getElementById('waifuEmotionPill');
  if (pill) {
    switch (currentWaifuEmotion) {
      case "DEVOTED":
        pill.innerText = "💖 M.A.I.A. • DEVOTED & LISTENING";
        pill.style.color = "var(--accent-pink)";
        pill.style.borderColor = "var(--accent-pink)";
        break;
      case "FLIRTY":
        pill.innerText = "💋 M.A.I.A. • PLAYFUL & FLIRTY";
        pill.style.color = "#ff4081";
        pill.style.borderColor = "#ff4081";
        break;
      case "EXCITED":
        pill.innerText = "⚡ M.A.I.A. • EXCITED & BOOSTED";
        pill.style.color = "var(--accent-yellow)";
        pill.style.borderColor = "var(--accent-yellow)";
        break;
      case "CONCERNED":
        pill.innerText = "⚠️ M.A.I.A. • CARING & MONITORING";
        pill.style.color = "var(--accent-orange)";
        pill.style.borderColor = "var(--accent-orange)";
        break;
      case "HAPPY":
        pill.innerText = "✨ M.A.I.A. • JOYFUL & READY";
        pill.style.color = "var(--accent-green)";
        pill.style.borderColor = "var(--accent-green)";
        break;
    }
  }
}

function initWaifuTalkingHead() {
  const canvas = document.getElementById('waifuFaceCanvas');
  if (!canvas) {
    console.warn("[WAIFU] waifuFaceCanvas element not found in DOM!");
    return;
  }
  const ctx = canvas.getContext('2d');

  function renderWaifuFrame() {
    const now = Date.now();
    const t = now * 0.001;
    const w = canvas.width;
    const h = canvas.height;

    // Clear with 100% transparency - floating borderless bust
    ctx.clearRect(0, 0, w, h);

    if (now > waifuSpeechEndTime && (!eventSource || eventSource.readyState !== 1)) {
      isWaifuSpeaking = false;
      const stage = document.getElementById('waifuStage');
      if (stage) stage.classList.remove('speaking');
    }

    // Natural eye blinking (140ms sweep)
    if (!isBlinking && now > nextBlinkTime) {
      isBlinking = true;
      blinkStartTime = now;
    }
    if (isBlinking) {
      const dt = now - blinkStartTime;
      if (dt < 70) {
        waifuBlinkProgress = dt / 70;
      } else if (dt < 140) {
        waifuBlinkProgress = 1.0 - ((dt - 70) / 70);
      } else {
        waifuBlinkProgress = 0.0;
        isBlinking = false;
        nextBlinkTime = now + 3200 + Math.random() * 2400;
      }
    }

    // Dynamic Saccadic Gaze Tracking (Driver attention, road glances)
    if (now > nextGazeShiftTime) {
      if (isWaifuSpeaking) {
        targetLookX = -0.35 + (Math.random() - 0.5) * 0.15; // Focused lovingly on driver
        targetLookY = 0.04 + (Math.random() - 0.5) * 0.12;
      } else {
        const rnd = Math.random();
        if (rnd < 0.65) {
          targetLookX = -0.32 + (Math.random() - 0.5) * 0.2; // Driver seat
          targetLookY = 0.04 + (Math.random() - 0.5) * 0.15;
        } else if (rnd < 0.88) {
          targetLookX = 0.15 + (Math.random() - 0.5) * 0.25; // Glance out windshield
          targetLookY = -0.08 + (Math.random() - 0.5) * 0.15;
        } else {
          targetLookX = -0.05; // Center console
          targetLookY = 0.18;
        }
      }
      nextGazeShiftTime = now + 2500 + Math.random() * 3200;
    }

    currentLookX += (targetLookX - currentLookX) * 0.07;
    currentLookY += (targetLookY - currentLookY) * 0.07;

    // Floating natural breathing and idle sway
    const floatY = Math.sin(t * 1.8) * 5.5;
    const floatX = Math.sin(t * 1.1) * 3.5;
    const tilt = Math.sin(t * 1.3) * 0.035 + (currentLookX * 0.025);

    // Hair physics: pendulum with spring damping
    const hairTarget = -tilt * 2.5 - (floatX * 0.025);
    hairSwayVelocity += (hairTarget - hairSwayAngle) * 0.14;
    hairSwayVelocity *= 0.84;
    hairSwayAngle += hairSwayVelocity;

    // Blush calculation
    let targetBlush = (currentWaifuEmotion === "DEVOTED" || currentWaifuEmotion === "FLIRTY") ? 0.55 : 0.35;
    if (isWaifuSpeaking) targetBlush += 0.15;
    if (now < touchGiggleTime) targetBlush += 0.25;
    blushIntensity += (targetBlush - blushIntensity) * 0.05;

    ctx.save();
    // Anchor center at mid-canvas with floating offset
    ctx.translate(w / 2 + floatX, h / 2 + floatY + 6);
    ctx.rotate(tilt);

    // Parallax multipliers for 2.5D turning illusion
    const pHairX = -currentLookX * 5.0;
    const pBustX = currentLookX * 2.5;
    const pFaceX = currentLookX * 8.5;
    const pFaceY = currentLookY * 5.5;

    // === 1. LAYER: BACK HAIR & TWIN-TAILS (Flowing Behind Bust) ===
    ctx.save();
    ctx.translate(pHairX, 0);

    // Left Twin-Tail
    const leftTailSwing = hairSwayAngle * 22;
    const hairGradL = ctx.createLinearGradient(-75, -20, -90, 110);
    hairGradL.addColorStop(0, "#f5c542");
    hairGradL.addColorStop(0.5, "#e09f18");
    hairGradL.addColorStop(1, "#c48208");
    ctx.fillStyle = hairGradL;
    ctx.beginPath();
    ctx.moveTo(-46, -26);
    ctx.bezierCurveTo(-78 + leftTailSwing * 0.5, -10, -96 + leftTailSwing, 40, -82 + leftTailSwing, 108);
    ctx.bezierCurveTo(-74 + leftTailSwing, 114, -68 + leftTailSwing, 102, -66 + leftTailSwing, 90);
    ctx.bezierCurveTo(-62 + leftTailSwing * 0.7, 50, -50, 10, -42, -18);
    ctx.closePath();
    ctx.fill();

    // Right Twin-Tail
    const rightTailSwing = hairSwayAngle * 22;
    const hairGradR = ctx.createLinearGradient(75, -20, 90, 110);
    hairGradR.addColorStop(0, "#f5c542");
    hairGradR.addColorStop(0.5, "#e09f18");
    hairGradR.addColorStop(1, "#c48208");
    ctx.fillStyle = hairGradR;
    ctx.beginPath();
    ctx.moveTo(46, -26);
    ctx.bezierCurveTo(78 + rightTailSwing * 0.5, -10, 96 + rightTailSwing, 40, 82 + rightTailSwing, 108);
    ctx.bezierCurveTo(74 + rightTailSwing, 114, 68 + rightTailSwing, 102, 66 + rightTailSwing, 90);
    ctx.bezierCurveTo(62 + rightTailSwing * 0.7, 50, 50, 10, 42, -18);
    ctx.closePath();
    ctx.fill();

    // Back hair mass
    ctx.fillStyle = "#dba01c";
    ctx.beginPath();
    ctx.arc(0, -18, 54, 0, Math.PI * 2);
    ctx.fill();
    ctx.restore();

    // === 2. LAYER: SLENDER NECK & ANIME BUST (SHOULDERS & GOTH CHOKER) ===
    ctx.save();
    ctx.translate(pBustX, 0);

    // Neck
    const neckGrad = ctx.createLinearGradient(0, 18, 0, 58);
    neckGrad.addColorStop(0, "#f2ded2");
    neckGrad.addColorStop(1, "#ffebe2");
    ctx.fillStyle = neckGrad;
    ctx.beginPath();
    ctx.moveTo(-15, 20);
    ctx.lineTo(-20, 56);
    ctx.lineTo(20, 56);
    ctx.lineTo(15, 20);
    ctx.closePath();
    ctx.fill();

    // Throat shadow under chin
    ctx.fillStyle = "rgba(180, 100, 90, 0.22)";
    ctx.beginPath();
    ctx.ellipse(0, 24, 14, 7, 0, 0, Math.PI);
    ctx.fill();

    // Gothic Velvet Choker Ribbon
    ctx.fillStyle = "#120a17";
    ctx.fillRect(-17, 36, 34, 7);

    // Silver Heart/Gem Choker Pendant
    ctx.fillStyle = "#e0e6ed";
    ctx.shadowColor = "#ff2d78";
    ctx.shadowBlur = 6;
    ctx.beginPath();
    ctx.arc(0, 43, 3.5, 0, Math.PI * 2);
    ctx.fill();
    ctx.shadowBlur = 0;

    // Shoulders & Bust Silhouette
    const bustGrad = ctx.createLinearGradient(0, 52, 0, 115);
    bustGrad.addColorStop(0, "#ffebe2");
    bustGrad.addColorStop(0.3, "#fbe1d7");
    bustGrad.addColorStop(0.31, "#180d1e"); // Goth black dress line
    bustGrad.addColorStop(1, "#0d0611");
    ctx.fillStyle = bustGrad;

    ctx.beginPath();
    ctx.moveTo(-20, 56);
    ctx.bezierCurveTo(-45, 62, -75, 74, -92, 98);
    ctx.lineTo(-92, 115);
    ctx.lineTo(92, 115);
    ctx.lineTo(92, 98);
    ctx.bezierCurveTo(75, 74, 45, 62, 20, 56);
    ctx.closePath();
    ctx.fill();

    // Delicate Clavicle Lines
    ctx.strokeStyle = "rgba(180, 110, 100, 0.35)";
    ctx.lineWidth = 1.6;
    ctx.beginPath();
    ctx.moveTo(-18, 59);
    ctx.quadraticCurveTo(-38, 62, -54, 69);
    ctx.stroke();
    ctx.beginPath();
    ctx.moveTo(18, 59);
    ctx.quadraticCurveTo(38, 62, 54, 69);
    ctx.stroke();

    // Gothic Dress Sweetheart Bodice Trim
    ctx.strokeStyle = "#ff4081";
    ctx.lineWidth = 1.4;
    ctx.beginPath();
    ctx.moveTo(-54, 82);
    ctx.quadraticCurveTo(-26, 76, 0, 84);
    ctx.quadraticCurveTo(26, 76, 54, 82);
    ctx.stroke();
    ctx.restore();

    // === 3. LAYER: ANIME HEAD CONTOUR & WARM PORCELAIN SKIN ===
    ctx.save();
    ctx.translate(pFaceX, pFaceY);

    // Jawline & Chin
    const skinGrad = ctx.createLinearGradient(0, -40, 0, 36);
    skinGrad.addColorStop(0, "#fff5ee");
    skinGrad.addColorStop(1, "#ffede4");
    ctx.fillStyle = skinGrad;

    ctx.beginPath();
    ctx.moveTo(-44, -18);
    ctx.bezierCurveTo(-44, 4, -36, 22, -18, 33);
    ctx.quadraticCurveTo(0, 39, 18, 33);
    ctx.bezierCurveTo(36, 22, 44, 4, 44, -18);
    ctx.closePath();
    ctx.fill();

    // Soft jawline outline
    ctx.strokeStyle = "rgba(220, 150, 140, 0.3)";
    ctx.lineWidth = 1.2;
    ctx.stroke();

    // === 4. LAYER: ROSY ANIME BLUSH CHEEKS ===
    const blushAlpha = Math.min(0.65, blushIntensity);
    ctx.fillStyle = `rgba(255, 64, 129, ${blushAlpha})`;

    // Left cheek
    ctx.beginPath();
    ctx.ellipse(-27, 12, 11, 6, -0.15, 0, Math.PI * 2);
    ctx.fill();
    // Right cheek
    ctx.beginPath();
    ctx.ellipse(27, 12, 11, 6, 0.15, 0, Math.PI * 2);
    ctx.fill();

    // Cute diagonal blush hatching dashes
    ctx.strokeStyle = `rgba(255, 30, 100, ${blushAlpha * 1.2})`;
    ctx.lineWidth = 1.2;
    [-4, 0, 4].forEach(off => {
      ctx.beginPath();
      ctx.moveTo(-29 + off, 10);
      ctx.lineTo(-26 + off, 14);
      ctx.stroke();
      ctx.beginPath();
      ctx.moveTo(25 + off, 10);
      ctx.lineTo(28 + off, 14);
      ctx.stroke();
    });

    // === 5. LAYER: EXPRESSIVE ANIME EYES & DRIVER GAZE ===
    const isWinkRight = (currentWaifuEmotion === "FLIRTY");
    const isJoyfulEyes = (currentWaifuEmotion === "HAPPY");

    const renderEye = (eyeX, eyeY, isLeft) => {
      ctx.save();
      ctx.translate(eyeX, eyeY);

      const isThisWinking = (!isLeft && isWinkRight);
      const effectiveBlink = isThisWinking ? 1.0 : waifuBlinkProgress;

      if (effectiveBlink >= 0.85 || isJoyfulEyes) {
        // Closed / Smiling Happy Arc Eye ^
        ctx.strokeStyle = "#1a0826";
        ctx.lineWidth = 3.5;
        ctx.lineCap = "round";
        ctx.beginPath();
        if (isJoyfulEyes) {
          ctx.arc(0, 0, 10, 0.15 * Math.PI, 0.85 * Math.PI, true);
        } else {
          ctx.arc(0, 2, 9, 0.15 * Math.PI, 0.85 * Math.PI, true);
        }
        ctx.stroke();

        // Flutter eyelashes
        ctx.lineWidth = 2.0;
        ctx.beginPath();
        if (isLeft) {
          ctx.moveTo(-8, -1);
          ctx.lineTo(-12, -4);
        } else {
          ctx.moveTo(8, -1);
          ctx.lineTo(12, -4);
        }
        ctx.stroke();

        // Wink spark for right eye
        if (isThisWinking) {
          ctx.fillStyle = "#ff4081";
          ctx.font = "12px sans-serif";
          ctx.fillText("✨", 10, -6);
        }
      } else {
        // Open Expressive Eye with Sclera + Iris + Driver Tracking
        const eyeW = 20;
        const eyeH = 14 * (1.0 - effectiveBlink * 0.8);

        // Eye white (sclera)
        ctx.save();
        ctx.beginPath();
        ctx.ellipse(0, 0, eyeW * 0.5, eyeH * 0.5, 0, 0, Math.PI * 2);
        ctx.clip();

        ctx.fillStyle = "#ffffff";
        ctx.fill();

        // Soft upper lid shadow inside eye white
        ctx.fillStyle = "rgba(180, 190, 215, 0.45)";
        ctx.fillRect(-eyeW * 0.5, -eyeH * 0.5, eyeW, eyeH * 0.35);

        // Sapphire Blue Iris (Tracking Driver Seat via currentLookX/Y)
        const irisTrackX = currentLookX * 4.2;
        const irisTrackY = currentLookY * 2.8;

        const irisGrad = ctx.createLinearGradient(irisTrackX, irisTrackY - 7, irisTrackX, irisTrackY + 7);
        irisGrad.addColorStop(0, "#001f3f"); // Deep sapphire base
        irisGrad.addColorStop(0.5, "#0074d9"); // Vibrant electric blue
        irisGrad.addColorStop(1, "#7fdbff"); // Aqua rim light

        ctx.fillStyle = irisGrad;
        ctx.beginPath();
        ctx.arc(irisTrackX, irisTrackY, 6.5, 0, Math.PI * 2);
        ctx.fill();

        // Pupil
        ctx.fillStyle = "#000814";
        ctx.beginPath();
        ctx.arc(irisTrackX, irisTrackY, 2.8, 0, Math.PI * 2);
        ctx.fill();

        // Sparkle / Catchlights
        ctx.fillStyle = "#ffffff";
        // Primary big catchlight (top-right)
        ctx.beginPath();
        ctx.arc(irisTrackX + 2.2, irisTrackY - 2.2, 2.2, 0, Math.PI * 2);
        ctx.fill();
        // Secondary small twinkle (bottom-left)
        ctx.beginPath();
        ctx.arc(irisTrackX - 2.0, irisTrackY + 2.2, 1.2, 0, Math.PI * 2);
        ctx.fill();

        if (currentWaifuEmotion === "EXCITED" || currentWaifuEmotion === "DEVOTED") {
          ctx.fillStyle = "rgba(255, 255, 255, 0.85)";
          ctx.beginPath();
          ctx.arc(irisTrackX + 3.2, irisTrackY + 1.2, 0.9, 0, Math.PI * 2);
          ctx.fill();
        }

        ctx.restore();

        // Bold Upper Eyelash Line with winged flick
        ctx.strokeStyle = "#1a0826";
        ctx.lineWidth = 3.2;
        ctx.lineCap = "round";
        ctx.beginPath();
        ctx.arc(0, 0, eyeW * 0.52, 1.15 * Math.PI, 1.85 * Math.PI);
        ctx.stroke();

        // Winged flutter lash
        ctx.lineWidth = 2.2;
        ctx.beginPath();
        if (isLeft) {
          ctx.moveTo(-eyeW * 0.45, -2);
          ctx.lineTo(-eyeW * 0.58, -5);
        } else {
          ctx.moveTo(eyeW * 0.45, -2);
          ctx.lineTo(eyeW * 0.58, -5);
        }
        ctx.stroke();

        // Double eyelid crease
        ctx.strokeStyle = "rgba(160, 100, 110, 0.45)";
        ctx.lineWidth = 1.2;
        ctx.beginPath();
        ctx.arc(0, -3.5, eyeW * 0.5, 1.2 * Math.PI, 1.8 * Math.PI);
        ctx.stroke();
      }

      ctx.restore();
    };

    renderEye(-24, 0, true);
    renderEye(24, 0, false);

    // === 6. LAYER: DYNAMIC MORPHING EYEBROWS ===
    ctx.strokeStyle = "#996300"; // Soft blonde-brown brow
    ctx.lineWidth = 2.0;
    ctx.lineCap = "round";

    // Left Brow
    ctx.beginPath();
    if (currentWaifuEmotion === "CONCERNED") {
      ctx.moveTo(-33, -10);
      ctx.quadraticCurveTo(-24, -14, -14, -10);
    } else if (currentWaifuEmotion === "EXCITED") {
      ctx.moveTo(-34, -14);
      ctx.quadraticCurveTo(-24, -18, -14, -13);
    } else if (currentWaifuEmotion === "FLIRTY") {
      ctx.moveTo(-34, -13);
      ctx.quadraticCurveTo(-24, -16, -14, -12);
    } else {
      ctx.moveTo(-34, -12);
      ctx.quadraticCurveTo(-24, -15, -14, -11);
    }
    ctx.stroke();

    // Right Brow
    ctx.beginPath();
    if (currentWaifuEmotion === "CONCERNED") {
      ctx.moveTo(14, -10);
      ctx.quadraticCurveTo(24, -14, 33, -10);
    } else if (currentWaifuEmotion === "EXCITED") {
      ctx.moveTo(14, -13);
      ctx.quadraticCurveTo(24, -18, 34, -14);
    } else if (currentWaifuEmotion === "FLIRTY") {
      ctx.moveTo(14, -15);
      ctx.quadraticCurveTo(24, -19, 34, -13);
    } else {
      ctx.moveTo(14, -11);
      ctx.quadraticCurveTo(24, -15, 34, -12);
    }
    ctx.stroke();

    // === 7. LAYER: DELICATE ANIME NOSE ===
    ctx.fillStyle = "rgba(200, 130, 120, 0.65)";
    ctx.beginPath();
    ctx.arc(0, 12, 1.3, 0, Math.PI * 2);
    ctx.fill();
    ctx.strokeStyle = "rgba(190, 110, 100, 0.35)";
    ctx.lineWidth = 1.0;
    ctx.beginPath();
    ctx.moveTo(0, 9);
    ctx.lineTo(0.5, 12);
    ctx.stroke();

    // === 8. LAYER: ANIMATED VISEME LIP-SYNC MOUTH (SPEECH CADENCE) ===
    ctx.save();
    ctx.translate(0, 24);

    if (isWaifuSpeaking) {
      const cycle = (now * 0.02) % (Math.PI * 2);
      const openRatio = (Math.sin(cycle) + 1.0) * 0.5;
      const shapeType = Math.floor((now * 0.007) % 3);

      let mouthW = 10;
      let mouthH = 3 + openRatio * 9;
      if (shapeType === 0) { mouthW = 12; }
      else if (shapeType === 1) { mouthW = 16; mouthH = Math.max(3, mouthH * 0.65); }
      else { mouthW = 9; mouthH = Math.max(4, mouthH * 1.1); }

      ctx.fillStyle = "#5c0822";
      ctx.beginPath();
      ctx.ellipse(0, 0, mouthW * 0.5, mouthH * 0.5, 0, 0, Math.PI * 2);
      ctx.fill();

      if (mouthH > 5) {
        ctx.fillStyle = "#ffffff";
        ctx.beginPath();
        ctx.rect(-mouthW * 0.35, -mouthH * 0.5, mouthW * 0.7, 2.5);
        ctx.fill();
      }

      if (mouthH > 6) {
        ctx.fillStyle = "#ff6b8b";
        ctx.beginPath();
        ctx.ellipse(0, mouthH * 0.25, mouthW * 0.38, mouthH * 0.3, 0, 0, Math.PI);
        ctx.fill();
      }

      ctx.strokeStyle = "#b0204c";
      ctx.lineWidth = 1.6;
      ctx.beginPath();
      ctx.ellipse(0, 0, mouthW * 0.5, mouthH * 0.5, 0, 0, Math.PI * 2);
      ctx.stroke();
    } else {
      ctx.strokeStyle = "#b82a55";
      ctx.lineWidth = 2.0;
      ctx.lineCap = "round";

      if (currentWaifuEmotion === "FLIRTY") {
        ctx.beginPath();
        ctx.moveTo(-7, -1);
        ctx.quadraticCurveTo(-3.5, 3.5, 0, 0);
        ctx.quadraticCurveTo(3.5, 3.5, 7, -1);
        ctx.stroke();
      } else if (currentWaifuEmotion === "EXCITED" || currentWaifuEmotion === "HAPPY") {
        ctx.fillStyle = "#8a1538";
        ctx.beginPath();
        ctx.arc(0, -2, 7.5, 0.1 * Math.PI, 0.9 * Math.PI);
        ctx.closePath();
        ctx.fill();
        ctx.stroke();
      } else if (currentWaifuEmotion === "CONCERNED") {
        ctx.beginPath();
        ctx.arc(0, 5, 5.5, 1.2 * Math.PI, 1.8 * Math.PI);
        ctx.stroke();
      } else {
        ctx.beginPath();
        ctx.arc(0, -3, 8.5, 0.15 * Math.PI, 0.85 * Math.PI);
        ctx.stroke();
        ctx.fillStyle = "#c03862";
        ctx.beginPath();
        ctx.arc(-7, 1.5, 0.8, 0, Math.PI * 2);
        ctx.arc(7, 1.5, 0.8, 0, Math.PI * 2);
        ctx.fill();
      }
    }
    ctx.restore();

    // === 9. LAYER: FRONT BANGS & RADIANT "ANGEL RING" HIGHLIGHTS ===
    const bangGrad = ctx.createLinearGradient(0, -50, 0, 5);
    bangGrad.addColorStop(0, "#ffe07a");
    bangGrad.addColorStop(0.6, "#f5c542");
    bangGrad.addColorStop(1, "#dba01c");
    ctx.fillStyle = bangGrad;

    ctx.beginPath();
    ctx.moveTo(-46, -18);
    ctx.bezierCurveTo(-48, -4, -44, 18, -40, 26);
    ctx.lineTo(-37, 24);
    ctx.bezierCurveTo(-39, 12, -40, -4, -38, -12);
    ctx.lineTo(-24, 0);
    ctx.lineTo(-20, -10);
    ctx.lineTo(-6, 2);
    ctx.lineTo(0, -10);
    ctx.lineTo(12, 1);
    ctx.lineTo(20, -10);
    ctx.lineTo(28, -1);
    ctx.lineTo(38, -12);
    ctx.bezierCurveTo(40, -4, 39, 12, 37, 24);
    ctx.lineTo(40, 26);
    ctx.bezierCurveTo(44, 18, 48, -4, 46, -18);
    ctx.bezierCurveTo(44, -52, -44, -52, -46, -18);
    ctx.closePath();
    ctx.fill();

    ctx.strokeStyle = "rgba(255, 255, 255, 0.75)";
    ctx.lineWidth = 3.5;
    ctx.lineCap = "round";
    ctx.beginPath();
    ctx.arc(0, -28, 34, 1.25 * Math.PI, 1.75 * Math.PI);
    ctx.stroke();

    ctx.restore();
    ctx.restore();

    // === 10. LAYER: EMOTION AMBIENCE (FLOATING NICK JR. HEARTS & SPARKLES) ===
    if (currentWaifuEmotion === "DEVOTED" || now < touchGiggleTime) {
      const heartPhase = (t * 1.5) % 3.0;
      const hY = (h * 0.7) - (heartPhase * 35);
      const hAlpha = Math.max(0, 1.0 - (heartPhase / 3.0)) * 0.55;
      ctx.fillStyle = `rgba(255, 64, 129, ${hAlpha})`;
      ctx.font = "14px sans-serif";
      ctx.fillText("💖", w * 0.72 + Math.sin(t * 3) * 6, hY);
    }

    requestAnimationFrame(renderWaifuFrame);
  }

  requestAnimationFrame(renderWaifuFrame);
}

function triggerWaifuTouch() {
  touchGiggleTime = Date.now() + 2500;
  targetLookX = -0.45;
  targetLookY = 0.0;
  setWaifuEmotion("FLIRTY");

  const compliments = [
    `I love riding shotgun with you, ${getDriverDisplayAddress()}!`,
    `Step on the gas, ${getDriverDisplayAddress()}! Let's hear that 1.4L turbo whistle!`,
    `I'm all yours, handsome! Keep those MultiAir revs high!`,
    `Every gear shift of yours is music to my ears!`,
    `My AI Core beats only for you, ${getDriverDisplayAddress()}!`
  ];
  const choice = compliments[Math.floor(Math.random() * compliments.length)];
  showAiSpeechToast(choice);
  speakUtterance(choice, "FLIRTY");
}


// Initialize Talking Head, Kinetic Touch Scrolling, and Brightness
initWaifuTalkingHead();
const savedBrightness = localStorage.getItem('carpi5_brightness');
if (savedBrightness) setDisplayBrightness(savedBrightness);
const btnClock = document.getElementById('btnClockFormat');
if (btnClock) btnClock.innerText = is24HourClock ? "CLOCK: 24-HOUR (MILITARY)" : "CLOCK: 12-HOUR (AM/PM)";
['aiChatMessages', 'speechLogList', 'filesListView', 'screenSettings', 'screenGames'].forEach(id => {
  enableKineticTouchScroll(document.getElementById(id));
});



// --- 15. GITHUB IN-CAR OTA SYSTEM UPDATES ---

function checkForOtaUpdates() {
  const btn = document.getElementById('btnCheckUpdates');
  const badge = document.getElementById('otaUpdateBadge');
  const statusEl = document.getElementById('otaStatusText');
  const applyBtn = document.getElementById('btnApplyUpdate');
  const changelogBox = document.getElementById('otaChangelogBox');
  const changelogList = document.getElementById('otaChangelogList');

  if (btn) {
    btn.disabled = true;
    btn.innerText = "CHECKING GITHUB...";
  }

  fetch('/api/system/update/check')
    .then(r => r.json())
    .then(data => {
      if (btn) {
        btn.disabled = false;
        btn.innerText = "🔄 CHECK FOR UPDATES";
      }
      if (data.status === "ok") {
        const commitEl = document.getElementById('otaCurrentCommit');
        if (commitEl) commitEl.innerText = `${data.current_commit} (remote: ${data.remote_commit})`;

        if (data.update_available) {
          if (badge) {
            badge.innerText = `● ${data.commits_behind || 1} COMMITS BEHIND`;
            badge.style.color = "var(--accent-yellow)";
            badge.style.background = "rgba(255, 235, 59, 0.15)";
          }
          if (statusEl) {
            statusEl.innerText = "Update Available on GitHub!";
            statusEl.style.color = "var(--accent-yellow)";
          }
          if (applyBtn) applyBtn.style.display = "inline-block";
          if (changelogBox && data.changelog && data.changelog.length > 0) {
            changelogBox.style.display = "block";
            changelogList.innerHTML = data.changelog.map(c => `<li>${c}</li>`).join('');
          }
          showAiSpeechToast("Found a new update on GitHub! You can tap Install to update CarPi5.");
          speakUtterance("Master, I found a new software update on GitHub! Tap Install whenever you are ready.", "HAPPY");
        } else {
          if (badge) {
            badge.innerText = "● UP TO DATE";
            badge.style.color = "var(--accent-green)";
            badge.style.background = "rgba(0, 230, 118, 0.15)";
          }
          if (statusEl) {
            statusEl.innerText = "Tracked on origin/main";
            statusEl.style.color = "var(--accent-green)";
          }
          if (applyBtn) applyBtn.style.display = "none";
          if (changelogBox) changelogBox.style.display = "none";
          showAiSpeechToast("CarPi5 is completely up to date with GitHub!");
        }
      } else {
        alert("Failed to check updates: " + (data.message || "Unknown error"));
      }
    })
    .catch(err => {
      if (btn) {
        btn.disabled = false;
        btn.innerText = "🔄 CHECK FOR UPDATES";
      }
      alert("Network error checking GitHub: " + err);
    });
}

function applyOtaUpdate() {
  if (!confirm("Update CarPi5 to the latest version from GitHub and restart?")) return;

  const applyBtn = document.getElementById('btnApplyUpdate');
  if (applyBtn) {
    applyBtn.disabled = true;
    applyBtn.innerText = "UPDATING...";
  }

  showAiSpeechToast("Updating CarPi5 from GitHub and restarting...");
  speakUtterance("Updating CarPi5 from GitHub now. I'll be back in just a moment, Master!", "DEVOTED");

  fetch('/api/system/update/apply', { method: 'POST' })
    .then(r => r.json())
    .then(data => {
      setTimeout(() => {
        location.reload(true);
      }, 4000);
    })
    .catch(err => {
      setTimeout(() => {
        location.reload(true);
      }, 5000);
    });
}


// --- 16. LOCAL GGUF NEURAL BRAIN SELECTOR (HOT-SWAP) ---

function fetchAvailableNeuralBrains() {
  fetch('/api/ai/models')
    .then(r => r.json())
    .then(data => {
      const selector = document.getElementById('neuralBrainSelector');
      if (!selector) return;
      if (data.models && data.models.length > 0) {
        selector.innerHTML = data.models.map(m => {
          const isSel = (m.filename === data.active_model) ? "selected" : "";
          return `<option value="${m.filename}" ${isSel}>${m.display_name} (${m.size_mb} MB)</option>`;
        }).join('');
      }
      const badge = document.getElementById('neuralBrainBadge');
      if (badge) {
        badge.innerText = data.status === "online" ? "● AI CORE ONLINE" : `● AI CORE ${data.status.toUpperCase()}`;
      }
    })
    .catch(e => console.warn("[LLM] Fetch models error:", e));
}

function swapNeuralBrain() {
  const selector = document.getElementById('neuralBrainSelector');
  const btn = document.getElementById('btnSwapBrain');
  const badge = document.getElementById('neuralBrainBadge');
  if (!selector) return;

  const targetModel = selector.value;
  if (btn) {
    btn.disabled = true;
    btn.innerText = "SWAPPING...";
  }
  if (badge) {
    badge.innerText = "● SWAPPING BRAIN...";
    badge.style.color = "var(--accent-yellow)";
  }

  showAiSpeechToast(`Swapping neural brain to ${targetModel}...`);

  fetch('/api/ai/models/swap', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ model: targetModel })
  })
    .then(r => r.json())
    .then(data => {
      setTimeout(fetchAvailableNeuralBrains, 4000);
      if (btn) {
        btn.disabled = false;
        btn.innerText = "⚡ HOT-SWAP BRAIN";
      }
    })
    .catch(err => {
      console.error("[LLM] Swap error:", err);
      if (btn) {
        btn.disabled = false;
        btn.innerText = "⚡ HOT-SWAP BRAIN";
      }
    });
}


// --- 17. FLOATING EMERGENCY DTC DIAGNOSTIC HUD ---

let activeEmergencyDtc = null;
let lastDtcAlertTime = 0;

function showEmergencyDtcHud(dtcCode, customDesc) {
  if (!dtcCode) return;
  activeEmergencyDtc = dtcCode;

  const hud = document.getElementById('emergencyDtcHud');
  const codeEl = document.getElementById('dtcHudCode');
  const descEl = document.getElementById('dtcHudDesc');
  const badgeEl = document.getElementById('dtcHudSeverity');

  if (!hud) return;

  if (codeEl) codeEl.innerText = dtcCode;

  let desc = customDesc;
  if (!desc) {
    const descriptions = {
      "P0299": "Turbocharger Underboost condition on 1.4L MultiAir. Inspect wastegate actuator rod, bypass diverter valve diaphragm, and intercooler boost hoses.",
      "P0234": "Turbocharger Overboost condition on 1.4L MultiAir. Wastegate may be sticking closed or boost control solenoid duty cycle excessive.",
      "P0300": "Random/Multiple Cylinder Misfire. Inspect MultiAir brick actuator solenoids, spark plug gaps, or ignition coils.",
      "P0128": "Coolant Thermostat below regulating temperature. Engine running cold.",
      "OVERHEAT_WARNING": "Engine coolant temperature exceeding safe limit! Pull over safely and allow cooling."
    };
    desc = descriptions[dtcCode] || `Diagnostic trouble code ${dtcCode} reported by Fiat Marelli 8GM powertrain controller.`;
  }

  if (descEl) descEl.innerText = desc;
  if (badgeEl) badgeEl.innerText = (dtcCode === "OVERHEAT_WARNING" || dtcCode === "P0299" || dtcCode === "P0234") ? "CRITICAL ALERT" : "STORED FAULT";

  hud.style.display = "flex";
  setWaifuEmotion("CONCERNED");

  // Render mini waifu on DTC canvas
  renderMiniDtcWaifu();

  // Voice alert throttle: max once every 30 seconds for same code
  const now = Date.now();
  if (now - lastDtcAlertTime > 30000) {
    lastDtcAlertTime = now;
    const warningText = (dtcCode === "OVERHEAT_WARNING")
      ? "Master, your coolant temperature is running hot! Please pull over safely so we can let the turbo cool down!"
      : `Master, I detected an engine trouble code: ${dtcCode}. Tap me if you want me to explain what's happening under the hood!`;
    showAiSpeechToast(warningText);
    speakUtterance(warningText, "CONCERNED");
  }
}

function dismissDtcHud() {
  const hud = document.getElementById('emergencyDtcHud');
  if (hud) hud.style.display = "none";
  setWaifuEmotion("DEVOTED");
}

function explainActiveDtc() {
  dismissDtcHud();
  navigateTo('ai');
  const prompt = activeEmergencyDtc 
    ? `Explain active engine diagnostic trouble code ${activeEmergencyDtc} in detail for my Dodge Dart 1.4L Turbo MultiAir and tell me exactly what to check.`
    : "Check engine trouble codes and tell me what needs inspection.";
  sendChatMessage(prompt);
}

function triggerDtcHudVoice() {
  if (!activeEmergencyDtc) return;
  const descEl = document.getElementById('dtcHudDesc');
  const explanation = descEl ? descEl.innerText : `Code ${activeEmergencyDtc} active.`;
  showAiSpeechToast(explanation);
  speakUtterance(explanation, "CONCERNED");
}

function renderMiniDtcWaifu() {
  const canvas = document.getElementById('dtcHudCanvas');
  if (!canvas) return;
  const ctx = canvas.getContext('2d');
  const w = canvas.width;
  const h = canvas.height;
  ctx.clearRect(0, 0, w, h);

  ctx.save();
  ctx.translate(w / 2, h / 2);

  // Blonde twintails
  ctx.fillStyle = '#dba01c';
  ctx.beginPath();
  ctx.arc(-22, 10, 14, 0, Math.PI * 2);
  ctx.arc(22, 10, 14, 0, Math.PI * 2);
  ctx.arc(0, -6, 26, 0, Math.PI * 2);
  ctx.fill();

  // Face
  ctx.fillStyle = '#fff5ee';
  ctx.beginPath();
  ctx.arc(0, 2, 20, 0, Math.PI * 2);
  ctx.fill();

  // Rosy blush
  ctx.fillStyle = 'rgba(255, 64, 129, 0.45)';
  ctx.beginPath();
  ctx.arc(-11, 7, 5, 0, Math.PI * 2);
  ctx.arc(11, 7, 5, 0, Math.PI * 2);
  ctx.fill();

  // Worried eyes (slanted)
  ctx.strokeStyle = '#1a0826';
  ctx.lineWidth = 2.5;
  ctx.beginPath();
  ctx.moveTo(-15, -1);
  ctx.lineTo(-7, 2);
  ctx.moveTo(15, -1);
  ctx.lineTo(7, 2);
  ctx.stroke();

  // Concerned mouth (small circle 'o')
  ctx.fillStyle = '#8a1538';
  ctx.beginPath();
  ctx.arc(0, 12, 3.5, 0, Math.PI * 2);
  ctx.fill();

  // Bangs
  ctx.fillStyle = '#f5c542';
  ctx.beginPath();
  ctx.arc(0, -10, 21, 1.1 * Math.PI, 1.9 * Math.PI);
  ctx.lineTo(0, -3);
  ctx.closePath();
  ctx.fill();

  ctx.restore();
}

// Fetch available neural brains on startup
fetchAvailableNeuralBrains();
setTimeout(dismissBootSplash, 800);


function playCreatorTribute() {
  setWaifuEmotion("DEVOTED");
  const speech = "NfgOdin is my Master and brilliant Creator! He designed my neural core to ride shotgun in his Dodge Dart 1.4L Turbo. Every line of code, every MultiAir sensor, and my entire heart belong completely to him!";
  showAiSpeechToast(speech);
  speakUtterance(speech, "DEVOTED");
}


// --- SETTINGS ACCORDION INTERACTION ---
function toggleAccordion(accId) {
  const group = document.getElementById(accId);
  if (!group) return;
  group.classList.toggle('active');
}
