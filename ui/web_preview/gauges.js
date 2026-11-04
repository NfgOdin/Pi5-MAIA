

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



// --- DISPLAY BRIGHTNESS SCRIM & HARDWARE BRIGHTNESS ---

function updateBrightnessFromSlider(val) {

  const pct = Math.max(10, Math.min(100, parseInt(val) || 100));

  

  // 1. Update UI Elements

  const pill = document.getElementById('brightnessPillVal');

  if (pill) pill.innerText = `${pct}%`;

  const slider = document.getElementById('sliderBrightness');

  if (slider && slider.value !== String(pct)) slider.value = pct;

  const cfgSlider = document.getElementById('cfgDisplayBrightness');

  if (cfgSlider && cfgSlider.value !== String(pct)) cfgSlider.value = pct;

  const label = document.getElementById('cfgBrightnessLabel');

  if (label) label.innerText = `${pct}%`;



  // 2. Hardware / Software Scrim (Smoothly dims any HDMI or DSI car display)

  const overlay = document.getElementById('screenBrightnessOverlay');

  if (overlay) {

    overlay.style.opacity = (1.0 - (pct / 100.0)).toFixed(2);

  }



  // 3. Persist setting across reboots

  localStorage.setItem('carpi5_brightness', pct);



  // 4. Send to backend in case sysfs backlight driver is present

  fetch('/api/system/brightness', {

    method: 'POST',

    headers: { 'Content-Type': 'application/json' },

    body: JSON.stringify({ brightness: pct })

  }).catch(() => {});

}



function setDisplayBrightness(val) {

  updateBrightnessFromSlider(val);

}



// --- GLOBAL TOUCH DRAG VS TAP DISCRIMINATOR & CLICK SUPPRESSION ---

let isTouchScrolling = false;

let touchScrollDistance = 0;

let touchStartY = 0;

let touchStartX = 0;



window.addEventListener('touchstart', (e) => {

  if (e.touches && e.touches[0]) {

    touchStartY = e.touches[0].clientY;

    touchStartX = e.touches[0].clientX;

    touchScrollDistance = 0;

    isTouchScrolling = false;

  }

}, { passive: true });



window.addEventListener('touchmove', (e) => {

  if (e.touches && e.touches[0]) {

    const dy = Math.abs(e.touches[0].clientY - touchStartY);

    const dx = Math.abs(e.touches[0].clientX - touchStartX);

    touchScrollDistance = Math.max(touchScrollDistance, Math.hypot(dx, dy));

    if (touchScrollDistance > 20) {

      isTouchScrolling = true;

    }

  }

}, { passive: true });



window.addEventListener('touchend', () => {

  setTimeout(() => {

    isTouchScrolling = false;

    touchScrollDistance = 0;

  }, 160);

}, { passive: true });



// Prevent accidental clicks on accordion headers/buttons if user was dragging to scroll!

window.addEventListener('click', (e) => {

  if (isTouchScrolling || touchScrollDistance > 20) {

    e.stopPropagation();

    e.preventDefault();

  }

}, true); // Capture phase listener!



function enableKineticTouchScroll(element) {

  // Native Chromium hardware-accelerated scrolling handles touch scrolling.

  if (element) {

    element.style.touchAction = 'pan-y';

    element.style.webkitOverflowScrolling = 'touch';

  }

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

  personality: "RUM",

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

  { title: "1.4L Boost Anthem (Italian FIRE)", artist: "R.U.M. Synthetics", duration: 198 }

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

    browser: document.getElementById('screenBrowser'),

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

    browser: document.getElementById('dockBtnBrowser'),

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

    if (data.is_speaking !== undefined) {

      isHardwareSpeaking = data.is_speaking;

    }

    if (data.live_convo_mode !== undefined || data.is_mic_listening !== undefined) {

      if (typeof syncVoiceButtonState === 'function') {

        syncVoiceButtonState(!!data.live_convo_mode, !!data.is_mic_listening, data.wake_word_enabled);

      }

    }

    if (data.voice_transcript && data.voice_transcript.timestamp && data.voice_transcript.text) {

      if (window._lastVoiceTranscriptTs !== data.voice_transcript.timestamp) {

        window._lastVoiceTranscriptTs = data.voice_transcript.timestamp;

        console.log("[USB MIC] Transcript received from Pi:", data.voice_transcript.text);

        handleSpokenTranscript(data.voice_transcript.text, true);

      }

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



    // Real-Time Hardware Speech Lip-Sync synchronization & Shotgun Auto-Popup

    if (typeof data.is_speaking === 'boolean') {

      const wasSpeaking = isHardwareSpeaking;

      isWaifuSpeaking = data.is_speaking;

      isHardwareSpeaking = data.is_speaking;

      const stage = document.getElementById('waifuStage');

      if (stage) {

        if (isWaifuSpeaking) stage.classList.add('speaking');

        else stage.classList.remove('speaking');

      }

      if (data.is_speaking && currentScreen !== 'ai') {

        handleSpeechAutoShotgun(null, 4500);

      } else if (wasSpeaking && !data.is_speaking) {

        scheduleShotgunAutoDismiss(2800);

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

  if (!pKey) pKey = currentAiSettings.personality || 'RUM';

  if (pKey === 'JARVIS') return 'J.A.R.V.I.S.';

  if (pKey === 'RACE_ENGINEER' || pKey === 'PITWALL') return 'PIT WALL';

  return 'R.U.M.';

}



function updatePersonaUI(personaKey) {

  if (!personaKey || personaKey === 'MAIA') personaKey = 'RUM';

  currentAiSettings.personality = personaKey;



  const pData = (window.allPersonas && window.allPersonas[personaKey]) ? window.allPersonas[personaKey] : null;

  const avatarPath = (pData && pData.avatar_image) ? pData.avatar_image : 'assets/pics/maia_avatar.jpg';

  const splashImg = (pData && pData.boot_splash_image) ? pData.boot_splash_image : 'assets/pics/splash.png';

  const splashVid = (pData && pData.boot_splash_video) ? pData.boot_splash_video : '';



  let displayName = "R.U.M.";

  let subtitleText = "Realtime Underhood MultiAir • The Forgotten Triplet";

  let statusBadgeText = "R.U.M. ACTIVE";

  let cardTitleText = "R.U.M. COMPANION";

  let bannerQuote = "Master! Rum is right here riding shotgun with you!";

  let icon = "💜";



  if (personaKey === 'JARVIS') {

    displayName = "J.A.R.V.I.S.";

    subtitleText = "Just A Rather Very Intelligent System • Tactical Cockpit Butler";

    statusBadgeText = "J.A.R.V.I.S. READY";

    cardTitleText = "J.A.R.V.I.S. COCKPIT";

    bannerQuote = "All cockpit systems nominal, Sir.";

    icon = "🛡️";

  } else if (personaKey === 'RACE_ENGINEER' || personaKey === 'PITWALL') {

    displayName = "PIT WALL";

    subtitleText = "F1 Telemetry & Race Engineer • Performance Strategist";

    statusBadgeText = "PIT WALL READY";

    cardTitleText = "PIT WALL STRATEGY";

    bannerQuote = "Radio check. Telemetry green, box this lap if needed.";

    icon = "🏎️";

  }



  // 1. Update Bottom Navigation Dock Button

  const dockBtn = document.getElementById('dockBtnAI');

  if (dockBtn) dockBtn.innerText = `${icon} ${displayName === 'R.U.M.' ? 'RUM' : displayName}`;



  // 2. Update AI Chat Header Title & Subtitle

  const titleEl = document.getElementById('chatAssistantTitle');

  if (titleEl) titleEl.innerText = `${displayName} Copilot`;



  const subEl = document.getElementById('chatAssistantSubtitle');

  if (subEl) subEl.innerText = subtitleText;



  // 3. Update Chat Input Placeholder

  const inputEl = document.getElementById('chatInput');

  if (inputEl) inputEl.placeholder = `Talk to Rum (or say 'Hey Rum' / tap 🎙️)...`;



  // 4. Update Home Screen Card & Badges

  const homeBadge = document.getElementById('homeAiStatusBadge');

  if (homeBadge) homeBadge.innerText = statusBadgeText;



  const homeCardTitle = document.getElementById('homeAiCardTitle');

  if (homeCardTitle) homeCardTitle.innerText = cardTitleText;



  const homeBannerName = document.getElementById('homeBannerAiName');

  if (homeBannerName) homeBannerName.innerText = `${displayName}:`;



  const accBadge = document.getElementById('accAiBadge');

  if (accBadge) accBadge.innerText = `ACTIVE: ${displayName}`;



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



  const pKey = currentAiSettings.personality || 'RUM';

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

  const pKey = currentAiSettings.personality || 'RUM';

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

    const isRum = (currentAiSettings.personality === 'RUM' || activeAvatarEngine === '3D_VRM');

    const introMsg = isRum

      ? `Yay, ${addr}! Rum is right here riding shotgun with you! Tap any quick prompt below or talk to me anytime!`

      : `Hey ${addr}, cockpit systems are loaded and ready. Talk to me or tap any of the quick prompts below!`;

    container.innerHTML = `

      <div class="chat-bubble maia">

        <strong>${currentName}:</strong> ${introMsg}

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

  if (!logs || !logs.length) return;

  logs.forEach(item => {

    appendSpeechLogItem(item);

  });

}



function appendSpeechLogItem(item) {

  if (!item || (!item.speech && !item.text && !item.hud_message)) return;

  const chatContainer = document.getElementById('aiChatMessages');

  if (!chatContainer) return;



  const text = item.speech || item.text || item.hud_message;

  const timeStr = item.time_str || new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

  const src = item.source || item.type || 'COPILOT';



  // Do not duplicate chat replies already rendered by appendMessage

  if (src === 'CHAT') return;



  const isAlert = (item.type === 'CRITICAL' || (item.tags && item.tags.includes('ALERT')));

  const div = document.createElement('div');

  div.className = 'copilot-event-entry';

  div.innerHTML = `

    <div class="copilot-event-bubble ${isAlert ? 'alert' : ''}">

      <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom: 4px; font-size: 10px; font-weight: 800;">

        <span style="color:${isAlert ? 'var(--accent-red)' : 'var(--accent-lavender, #c084fc)'}; display:flex; align-items:center; gap:5px;">

          <span>${isAlert ? '⚠️' : '💜'}</span> <b>RUM • ${src}</b>

        </span>

        <span style="color:var(--text-secondary); font-size: 9px;">${timeStr}</span>

      </div>

      <div style="color: #f3f0ff; font-size: 11px; line-height: 1.4;">${text}</div>

    </div>

  `;

  chatContainer.appendChild(div);

  chatContainer.scrollTop = chatContainer.scrollHeight;

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



function sendChatMessage(userText, isVoice = false) {

  const container = document.getElementById('aiChatMessages');

  const sendBtn = document.getElementById('sendBtn');

  const nowTime = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });



  // Immediately append user message on the SENT (right) side of the chat screen

  const userBubble = document.createElement('div');

  userBubble.className = 'chat-bubble user';

  const sentLabel = isVoice ? `🎤 Voice • ${nowTime}` : `Sending...`;

  userBubble.innerHTML = `<div><strong>${isVoice ? '🎤 You' : 'You'}:</strong> ${userText}</div><div class="chat-time">${sentLabel}</div>`;

  if (container) {

    container.appendChild(userBubble);

    scrollChatToBottom();

  }



  if (sendBtn) {

    sendBtn.disabled = true;

    sendBtn.innerHTML = "⏳";

  }



  fetch('/api/ai/chat', {

    method: 'POST',

    headers: { 'Content-Type': 'application/json' },

    body: JSON.stringify({ message: userText, source: isVoice ? 'voice' : 'text' })

  })

    .then(r => r.json())

    .then(data => {

      if (sendBtn) {

        sendBtn.disabled = false;

        sendBtn.innerHTML = "➤";

      }

      const timeEl = userBubble.querySelector('.chat-time');

      if (timeEl) {

        timeEl.innerText = isVoice ? `🎤 Voice • Sent ${nowTime}` : `Sent • ${nowTime}`;

      }



      const p = data.persona || data.personality || currentAiSettings.personality;

      const respName = getPersonaDisplayName(p);



      // Append R.U.M. response bubble on the left side

      if (container && userBubble.parentNode !== container) container.appendChild(userBubble);

      const maiaBubble = document.createElement('div');

      maiaBubble.className = 'chat-bubble maia';

      maiaBubble.innerHTML = `<div><strong>${respName}:</strong> ${data.reply}</div><div class="chat-time">Just now</div>`;

      if (container) {

        container.appendChild(maiaBubble);

        scrollChatToBottom();

      }



      // Trigger speaking animation on 3D VRM

      const estMs = Math.max(2400, (data.reply.length / 10.0) * 1000);

      if (typeof setVrmSpeaking === 'function') {

        setVrmSpeaking(estMs, data.reply);

      }



      // Update home banner quote

      const homeQuote = document.getElementById('homeBannerAiQuote');

      if (homeQuote) homeQuote.innerText = `${respName}: ${data.reply.slice(0, 56)}...`;



      // Execute dashboard action (screen switch or app launcher)

      if (data.action) {

        handleAiAction(data.action);

      }



      // Update emotion & HUD

      if (data.emotion) {

        setWaifuEmotion(data.emotion);

      }



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

        sendBtn.innerHTML = "➤";

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

  if (typeof showVrmSpeech === 'function') {

    showVrmSpeech(speech, 6500);

  }



  const toast = document.getElementById('aiToast');

  const textEl = document.getElementById('aiText');

  if (toast && textEl) {

    textEl.innerText = speech;

    toast.classList.add('show');

    setTimeout(() => toast.classList.remove('show'), 6500);

  }

}



// --- AUTO-SHOTGUN FLOATING HUD ON SPEECH ---

let isShotgunAutoPopped = false;

let shotgunAutoDismissTimer = null;



function handleSpeechAutoShotgun(text, durationMs) {

  if (currentScreen === 'ai') return;

  const floatingHud = document.getElementById('vrmFloatingHud');

  if (!floatingHud) return;



  if (shotgunAutoDismissTimer) {

    clearTimeout(shotgunAutoDismissTimer);

    shotgunAutoDismissTimer = null;

  }



  if (!isCompanionFloating) {

    popOutFloatingCompanion(true);

    isShotgunAutoPopped = true;

  }



  if (text) {

    showVrmSpeech(text, durationMs || 5000);

  }

}



function scheduleShotgunAutoDismiss(delayMs = 2800) {

  if (!isShotgunAutoPopped || currentScreen === 'ai') return;

  if (shotgunAutoDismissTimer) clearTimeout(shotgunAutoDismissTimer);

  shotgunAutoDismissTimer = setTimeout(() => {

    if (isShotgunAutoPopped && !isHardwareSpeaking && currentScreen !== 'ai') {

      dockCompanionToAi();

      isShotgunAutoPopped = false;

    }

    shotgunAutoDismissTimer = null;

  }, delayMs);

}



function speakUtterance(text, emotion) {

  if (!text || currentVoiceMode === "MUTED") return;



  if (currentScreen !== 'ai') {

    handleSpeechAutoShotgun(text, Math.max(2200, (text.length / 9.5) * 1000 + 400));

  }



  if (emotion) {

    setWaifuEmotion(emotion);

  }



  // Fallback timer only if SSE stream is disconnected

  const estimatedDurationMs = Math.max(2200, (text.length / 9.5) * 1000 + 300);

  if (!eventSource || eventSource.readyState !== 1) {

    waifuSpeechEndTime = Date.now() + estimatedDurationMs;

  }

  if (typeof setVrmSpeaking === 'function') setVrmSpeaking(estimatedDurationMs, text, false);

  const stage = document.getElementById('waifuStage');



  if (!eventSource || eventSource.readyState !== 1) {

    isWaifuSpeaking = true;

    if (stage) stage.classList.add('speaking');

    setTimeout(() => {

      if (stage) stage.classList.remove('speaking');

      setWaifuEmotion("DEVOTED");

      isWaifuSpeaking = false;

      scheduleShotgunAutoDismiss(2500);

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

      const p = currentAiSettings.personality || 'RUM';

      if (p === 'JARVIS') {

        utterance.rate = 0.96; utterance.pitch = 0.90;

      } else if (p === 'RACE_ENGINEER' || p === 'PITWALL') {

        utterance.rate = 1.14; utterance.pitch = 1.0;

      } else {

        // High-pitched 12-yr-old anime girl pitch for Rum

        utterance.rate = 1.08; utterance.pitch = 1.24;

      }

      window.speechSynthesis.speak(utterance);

    } catch (e) {}

  }

}



// --- HANDS-FREE WAKE WORD & LIVE CONVERSATION ENGINE (BACKEND PIPEWIRE USB MIC + BROWSER FALLBACK) ---

let isWakeWordEnabled = true;

let isLiveConvoMode = false;

let isVoiceRecording = false;



function initSpeechRecognition() {

  // Backend PipeWire USB microphone daemon is always active on Pi 5!

  // Ensure Wake Word and Live Convo buttons are always visible and synced.

  const btn = document.getElementById('btnWakeWord');

  if (btn) btn.style.display = 'inline-flex';

  const cBtn = document.getElementById('btnLiveConvo');

  if (cBtn) cBtn.style.display = 'inline-flex';

}



function syncVoiceButtonState(convoActive, micCapturing, wakeEnabled) {

  isLiveConvoMode = !!convoActive;

  isVoiceRecording = !!(convoActive || micCapturing);

  if (wakeEnabled !== undefined) {

    isWakeWordEnabled = !!wakeEnabled;

    const wBtn = document.getElementById('btnWakeWord');

    if (wBtn) {

      wBtn.innerText = isWakeWordEnabled ? "🎤 WAKE WORD: ON" : "🔇 WAKE WORD: OFF";

      wBtn.style.borderColor = isWakeWordEnabled ? "var(--accent-pink)" : "var(--panel-border)";

      wBtn.style.color = isWakeWordEnabled ? "var(--accent-pink)" : "var(--text-secondary)";

    }

  }



  const btn = document.getElementById('btnLiveConvo');

  if (!btn) return;

  if (convoActive) {

    btn.innerHTML = "🔴";

    btn.classList.add('recording');

    btn.style.borderColor = "var(--accent-red, #ef4444)";

    btn.style.boxShadow = "0 0 16px rgba(239, 68, 68, 0.85)";

    btn.style.background = "rgba(239, 68, 68, 0.35)";

    btn.title = "Live Voice Conversation Active (Speak freely to Rum! Tap to stop)";

  } else {

    btn.innerHTML = "🎙️";

    btn.classList.remove('recording');

    btn.style.borderColor = "";

    btn.style.boxShadow = "";

    btn.style.background = "";

    btn.title = "Toggle Live Voice Conversation Mode (USB Mic)";

  }

}



async function toggleLiveConversationMode() {

  try {

    const resp = await fetch('/api/ai/listen', {

      method: 'POST',

      headers: { 'Content-Type': 'application/json' },

      body: JSON.stringify({ action: 'toggle_convo' })

    });

    const data = await resp.json();

    syncVoiceButtonState(data.live_convo_mode, data.is_mic_listening, data.wake_word_enabled);

    if (data.live_convo_mode) {

      showAiSpeechToast("🔴 Live Voice Mode ON! Speak to Rum anytime — your words appear in chat!");

    } else {

      showAiSpeechToast("🎙️ Live Voice Mode paused. Wake word 'Hey Rum' is still active!");

    }

  } catch (err) {

    console.error("[VOICE] Backend listen toggle failed:", err);

  }

}



function toggleWakeWordListening() {

  const nextWake = !isWakeWordEnabled;

  fetch('/api/ai/listen', {

    method: 'POST',

    headers: { 'Content-Type': 'application/json' },

    body: JSON.stringify({ action: 'set_wake', enabled: nextWake })

  })

    .then(r => r.json())

    .then(data => {

      syncVoiceButtonState(data.live_convo_mode, data.is_mic_listening, data.wake_word_enabled);

      showAiSpeechToast(data.wake_word_enabled ? "🎤 Wake word 'Hey Rum' enabled!" : "🔇 Wake word listening paused.");

    })

    .catch(err => console.warn("[VOICE] Wake toggle error:", err));

}



function handleSpokenTranscript(text, isFromMic = true) {

  if (!text) return;

  const rawText = text.trim();

  if (!rawText) return;



  let query = rawText;

  const qLower = query.toLowerCase();



  // Strip wake words if prepended to a longer question

  const wakePrefixes = [

    'hey rum', 'hi rum', 'hello rum', 'okay rum', 'ok rum', 'yo rum', 'rum',

    'hey ram', 'hi ram', 'ram', 'hey rem', 'hi rem', 'rem',

    'hey ron', 'ron', 'hey rome', 'rome', 'hey room', 'room',

    'hey run', 'hey rob', 'hey drum', 'r.u.m.', 'r.u.m'

  ];

  let matchedWakeOnly = false;

  for (const w of wakePrefixes) {

    if (qLower === w || qLower === w + '!' || qLower === w + '?') {

      matchedWakeOnly = true;

      break;

    }

    if (qLower.startsWith(w + ' ') || qLower.startsWith(w + ',') || qLower.startsWith(w + '.')) {

      query = query.substring(w.length).replace(/^[,.\s!?]+/, '').trim();

      break;

    }

  }



  const cleanCmd = (query || '').toLowerCase().trim();



  // 1. Direct Vehicle Telemetry Queries

  if (cleanCmd.includes('speed') || cleanCmd.includes('how fast') || cleanCmd.includes('fast am i')) {

    const spd = Math.round((latestTelemetry && latestTelemetry.speed_mph) || 0);

    const reply = `You're cruising at ${spd} miles per hour, Master!`;

    appendChatMessage('user', rawText);

    appendChatMessage('assistant', reply);

    speakUtterance(reply);

    return;

  }

  if (cleanCmd.includes('coolant') || cleanCmd.includes('engine temp') || cleanCmd.includes('temperature')) {

    const temp = Math.round((latestTelemetry && latestTelemetry.coolant_temp_f) || 195);

    const reply = `Engine coolant temperature is currently ${temp} degrees Fahrenheit!`;

    appendChatMessage('user', rawText);

    appendChatMessage('assistant', reply);

    speakUtterance(reply);

    return;

  }

  if (cleanCmd.includes('rpm') || cleanCmd.includes('tachometer') || cleanCmd.includes('revs')) {

    const rpm = Math.round((latestTelemetry && latestTelemetry.rpm) || 0);

    const reply = `Engine tachometer is at ${rpm} RPM!`;

    appendChatMessage('user', rawText);

    appendChatMessage('assistant', reply);

    speakUtterance(reply);

    return;

  }

  if (cleanCmd.includes('boost') || cleanCmd.includes('turbo') || cleanCmd.includes('psi')) {

    const psi = ((latestTelemetry && latestTelemetry.boost_psi) || 0).toFixed(1);

    const reply = `Turbo boost is at ${psi} PSI!`;

    appendChatMessage('user', rawText);

    appendChatMessage('assistant', reply);

    speakUtterance(reply);

    return;

  }

  if (cleanCmd.includes('battery') || cleanCmd.includes('voltage') || cleanCmd.includes('alternator')) {

    const v = ((latestTelemetry && latestTelemetry.battery_voltage) || 14.2).toFixed(1);

    const reply = `Battery system is reading ${v} volts!`;

    appendChatMessage('user', rawText);

    appendChatMessage('assistant', reply);

    speakUtterance(reply);

    return;

  }

  if (cleanCmd.includes('fuel') || cleanCmd.includes('gas tank') || cleanCmd.includes('how much gas')) {

    const fuel = Math.round((latestTelemetry && latestTelemetry.fuel_level_pct) || 75);

    const reply = `Fuel level is at ${fuel} percent!`;

    appendChatMessage('user', rawText);

    appendChatMessage('assistant', reply);

    speakUtterance(reply);

    return;

  }



  // 2. Direct App & Screen Navigation Controls

  if (cleanCmd.includes('gauge') || cleanCmd.includes('dashboard')) {

    navigateTo('gauges');

    showAiSpeechToast("Switching to Gauges!");

    return;

  }

  if (cleanCmd.includes('telemetry') || cleanCmd.includes('sensor')) {

    navigateTo('telemetry');

    showAiSpeechToast("Opening Telemetry Graphs!");

    return;

  }

  if (cleanCmd.includes('diagnostic') || cleanCmd.includes('trouble code') || cleanCmd.includes('fault code') || cleanCmd.includes('dtc')) {

    showDiagnosticsModal();

    showAiSpeechToast("Scanning Powertrain Diagnostics!");

    return;

  }

  if (cleanCmd.includes('browser') || cleanCmd.includes('firefox') || cleanCmd.includes('internet') || cleanCmd.includes('web')) {

    launchFirefoxBrowser();

    return;

  }

  if (cleanCmd.includes('media') || cleanCmd.includes('music') || cleanCmd.includes('song')) {

    navigateTo('media');

    showAiSpeechToast("Opening Media Player!");

    return;

  }

  if (cleanCmd.includes('game') || cleanCmd.includes('retroarch')) {

    navigateTo('games');

    showAiSpeechToast("Opening Games Hub!");

    return;

  }

  if (cleanCmd.includes('setting')) {

    navigateTo('settings');

    showAiSpeechToast("Opening Settings!");

    return;

  }

  if (cleanCmd.includes('home') || cleanCmd.includes('main screen')) {

    navigateTo('home');

    showAiSpeechToast("Returning to Home screen!");

    return;

  }



  // 3. Direct Kinetic Animations & Mocap Actions

  if (cleanCmd.includes('jump') || cleanCmd.includes('hop')) {

    playVrmAction('action_jump', 3200, false);

    return;

  }

  if (cleanCmd.includes('lean in') || cleanCmd.includes('come closer') || cleanCmd.includes('bow')) {

    playVrmAction('bend_over', 3800, false);

    return;

  }

  if (cleanCmd.includes('laugh') || cleanCmd.includes('giggle') || cleanCmd.includes('joke')) {

    playVrmAction('amusement', 3600, false);

    if (!cleanCmd.includes('tell me a joke')) return;

  }

  if (cleanCmd.includes('peace') || cleanCmd.includes('v sign')) {

    playVrmAction('peace', 4200, false);

    return;

  }

  if (cleanCmd.includes('shoot') || cleanCmd.includes('finger gun')) {

    playVrmAction('shoot', 4500, false);

    return;

  }

  if (cleanCmd.includes('spin') || cleanCmd.includes('twirl')) {

    playVrmAction('spin', 4500, false);

    return;

  }

  if (cleanCmd.includes('model') || cleanCmd.includes('pose')) {

    playVrmAction('model_pose', 4800, false);

    return;

  }

  if (cleanCmd.includes('squat') || cleanCmd.includes('exercise')) {

    playVrmAction('squat', 4400, false);

    return;

  }

  if (cleanCmd.includes('dance') || cleanCmd.includes('groove')) {

    playVrmAction(cleanCmd.includes('groove') ? 'dance_side_groove' : 'dance_hiphop_step', 5500, false);

    return;

  }

  if (cleanCmd.includes('sit') || cleanCmd.includes('relax')) {

    playVrmAction('sit_idle', 8000, false);

    return;

  }

  if (cleanCmd.includes('walk')) {

    playVrmAction('walk_loop', 6000, false);

    return;

  }

  if (cleanCmd.includes('jog') || cleanCmd.includes('run')) {

    playVrmAction('jog_loop', 6000, false);

    return;

  }

  if (cleanCmd.includes('wave') || cleanCmd.includes('say hi') || cleanCmd.includes('hello')) {

    playVrmAction('greeting', 3800, false);

    return;

  }



  // If user only said her name ("Rum!" / "Hey Rum!"), greet cheerfully and open follow-up window

  if (matchedWakeOnly || !query || query.length < 2) {

    playVrmAction('greeting', 3800, false);

    sendChatMessage(rawText, true);

    return;

  }



  // Transcribe spoken words onto the sent (right) side of the chat screen and send to Rum's neural brain!

  sendChatMessage(query, true);

}



// --- ANIMATIONS & POSES DRAWER CONTROLS ---



function openAnimationsDrawer() {

  const m = document.getElementById('animationsDrawerModal');

  if (m) m.style.display = 'flex';

}



function toggleAnimationsDrawer() {

  const m = document.getElementById('animationsDrawerModal');

  if (!m) return;

  m.style.display = (m.style.display === 'flex') ? 'none' : 'flex';

}



function closeAnimationsDrawer() {

  const m = document.getElementById('animationsDrawerModal');

  if (m) m.style.display = 'none';

}



function filterAnimationCategory(cat, btnEl) {

  document.querySelectorAll('.anim-tab-btn').forEach(b => {

    b.style.background = 'rgba(255,255,255,0.08)';

    b.style.color = 'var(--text-secondary)';

    b.style.border = '1px solid #445';

  });

  if (btnEl) {

    btnEl.style.background = 'var(--accent-purple, #a855f7)';

    btnEl.style.color = '#fff';

    btnEl.style.border = 'none';

  }

  const cards = document.querySelectorAll('.anim-card-btn');

  cards.forEach(c => {

    const cardCat = c.getAttribute('data-cat');

    if (cat === 'all' || cardCat === cat) {

      c.style.display = 'flex';

    } else {

      c.style.display = 'none';

    }

  });

}



function triggerDrawerAnim(actionKey) {

  playVrmAction(actionKey, 4800, false);

  const m = document.getElementById('animationsDrawerModal');

  if (m) m.style.display = 'none';

  showAiSpeechToast(`Playing animation: ${actionKey}`);

}



// --- VOICE COMMANDS MODAL CONTROLS ---



function openVoiceCommandsModal() {

  const m = document.getElementById('voiceCommandsModal');

  if (m) m.style.display = 'flex';

}



function closeVoiceCommandsModal() {

  const m = document.getElementById('voiceCommandsModal');

  if (m) m.style.display = 'none';

}



// --- FIREFOX BROWSER INTEGRATION (TOP WINDOW & AUTO-CLOSE ON UNFOCUS) ---



let isFirefoxRunning = false;

let firefoxWatcherTimer = null;



async function launchFirefoxBrowser() {

  showAiSpeechToast("🦊 Launching Firefox Web Browser...");

  try {

    const res = await fetch('/api/system/browser/launch', { method: 'POST' });

    const data = await res.json();

    isFirefoxRunning = true;

    startFirefoxWatcher();

    showAiSpeechToast("Firefox open on top. Close window or tap CarPi5 to return!");

  } catch (err) {

    console.error("[FIREFOX] Launch error:", err);

  }

}



async function closeFirefoxBrowser() {

  try {

    await fetch('/api/system/browser/close', { method: 'POST' });

    isFirefoxRunning = false;

    stopFirefoxWatcher();

    showAiSpeechToast("Firefox closed.");

  } catch (err) {

    console.warn("[FIREFOX] Close error:", err);

  }

}



function startFirefoxWatcher() {

  if (firefoxWatcherTimer) clearInterval(firefoxWatcherTimer);

  firefoxWatcherTimer = setInterval(async () => {

    try {

      const resp = await fetch('/api/system/browser/status');

      const data = await resp.json();

      isFirefoxRunning = Boolean(data.running);

      if (!isFirefoxRunning) {

        stopFirefoxWatcher();

      }

    } catch (e) {}

  }, 1800);

}



function stopFirefoxWatcher() {

  if (firefoxWatcherTimer) {

    clearInterval(firefoxWatcherTimer);

    firefoxWatcherTimer = null;

  }

}



// Firefox remains open until user closes its window (or toggles BROWSER button)







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



  // Sync TTS Voice Engine UI

  const ttsEng = (currentAiSettings.tts_engine || 'KOKORO').toUpperCase();

  selectTtsEngine(ttsEng, false);

  const kVoiceEl = document.getElementById('cfgKokoroVoice');

  if (kVoiceEl && currentAiSettings.kokoro_voice) kVoiceEl.value = currentAiSettings.kokoro_voice;

  const pitchEl = document.getElementById('cfgTtsPitch');

  const lblPitch = document.getElementById('lblTtsPitch');

  if (pitchEl && currentAiSettings.tts_pitch !== undefined) {

    pitchEl.value = currentAiSettings.tts_pitch;

    if (lblPitch) lblPitch.innerText = currentAiSettings.tts_pitch + 'x';

  }

  const elKey = document.getElementById('cfgElevenLabsKey');

  const elVid = document.getElementById('cfgElevenLabsVoiceId');

  if (elKey && currentAiSettings.elevenlabs_api_key) elKey.value = currentAiSettings.elevenlabs_api_key;

  if (elVid && currentAiSettings.elevenlabs_voice_id) elVid.value = currentAiSettings.elevenlabs_voice_id;



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





function selectTtsEngine(engine, autoSave = true) {

  const eng = (engine || 'KOKORO').toUpperCase();

  currentAiSettings.tts_engine = eng;

  const rKokoro = document.getElementById('radioTtsKokoro');

  const rPiper = document.getElementById('radioTtsPiper');

  const rEleven = document.getElementById('radioTtsEleven');

  const rOpenAi = document.getElementById('radioTtsOpenAi');

  if (rKokoro) rKokoro.checked = (eng === 'KOKORO');

  if (rPiper) rPiper.checked = (eng === 'PIPER');

  if (rEleven) rEleven.checked = (eng === 'ELEVENLABS');

  if (rOpenAi) rOpenAi.checked = (eng === 'OPENAI_TTS');



  const elRow = document.getElementById('elevenLabsKeyRow');

  if (elRow) elRow.style.display = (eng === 'ELEVENLABS') ? 'flex' : 'none';



  if (autoSave) {

    saveTtsVoiceSettings();

  }

}



let pitchDebounceTimer = null;

function onPitchSliderInput(val) {

  const p = parseFloat(val) || 1.0;

  const lbl = document.getElementById('lblTtsPitch');

  if (lbl) lbl.innerText = p.toFixed(2) + 'x';

}



function onPitchSliderChanged(val) {

  const p = parseFloat(val) || 1.0;

  onPitchSliderInput(val);

  saveTtsVoiceSettings();

  if (pitchDebounceTimer) clearTimeout(pitchDebounceTimer);

  pitchDebounceTimer = setTimeout(() => {

    testTtsVoiceSample();

  }, 250);

}



function saveTtsVoiceSettings() {

  const kVoiceEl = document.getElementById('cfgKokoroVoice');

  const pitchEl = document.getElementById('cfgTtsPitch');

  const elKey = document.getElementById('cfgElevenLabsKey');

  const elVid = document.getElementById('cfgElevenLabsVoiceId');

  const pitchVal = pitchEl ? parseFloat(pitchEl.value) : 1.18;



  const payload = {

    tts_engine: currentAiSettings.tts_engine || 'KOKORO',

    kokoro_voice: kVoiceEl ? kVoiceEl.value : 'af_nicole',

    tts_pitch: pitchVal,

    pitch_factor: pitchVal,

    elevenlabs_api_key: elKey ? elKey.value.trim() : (currentAiSettings.elevenlabs_api_key || ''),

    elevenlabs_voice_id: elVid ? elVid.value.trim() : (currentAiSettings.elevenlabs_voice_id || 'jBpfuIE2acCO8z3wKNLl')

  };

  Object.assign(currentAiSettings, payload);



  fetch('/api/ai/settings', {

    method: 'POST',

    headers: { 'Content-Type': 'application/json' },

    body: JSON.stringify(payload)

  })

    .then(r => r.json())

    .then(data => {

      if (data && data.settings) currentAiSettings = data.settings;

    })

    .catch(err => console.warn('[TTS] Save settings error:', err));

}



function testTtsVoiceSample() {

  saveTtsVoiceSettings();

  const eng = (currentAiSettings.tts_engine || 'KOKORO');

  const sample = `Yay Master! Rum is speaking with the ${eng === 'KOKORO' ? 'Kokoro neural' : eng.toLowerCase()} voice engine right now! How do I sound?`;

  showAiSpeechToast(sample);

  speakUtterance(sample, 'HAPPY');

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



// 2. Hardware Brightness (delegates to main handler)



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



// 5. SQLite Persistent Trip Logs & Driving Diagnostics

function fetchTripLogs() {

  Promise.all([

    fetch('/api/trips/stats').then(r => r.json()).catch(() => ({})),

    fetch('/api/trips/recent').then(r => r.json()).catch(() => []),

    fetch('/api/trips/retention').then(r => r.json()).catch(() => ({ retention_days: 0 }))

  ])

  .then(([stats, trips, retention]) => {

    // 1. Retention dropdown synchronization

    const retentionSelect = document.getElementById('tripRetentionSelect');

    if (retentionSelect && retention && retention.retention_days !== undefined) {

      retentionSelect.value = String(retention.retention_days);

    }



    // 2. Lifetime Telemetry Stats Cards (8 metrics)

    const statsContainer = document.getElementById('tripLifetimeStats');

    if (statsContainer) {

      statsContainer.innerHTML = `

        <div style="background:#0c1219; border:1px solid #212b38; padding:8px 12px; border-radius:8px;">

          <div style="font-size:9px; color:var(--text-secondary); font-weight:800;">TOTAL DRIVES</div>

          <div style="font-size:16px; font-weight:900; color:#fff;">${stats.total_trips || 0}</div>

        </div>

        <div style="background:#0c1219; border:1px solid #212b38; padding:8px 12px; border-radius:8px;">

          <div style="font-size:9px; color:var(--text-secondary); font-weight:800;">TOTAL MILES</div>

          <div style="font-size:16px; font-weight:900; color:var(--accent-blue);">${stats.total_distance_miles || 0} MI</div>

        </div>

        <div style="background:#0c1219; border:1px solid #212b38; padding:8px 12px; border-radius:8px;">

          <div style="font-size:9px; color:var(--text-secondary); font-weight:800;">TOTAL DRIVE TIME</div>

          <div style="font-size:16px; font-weight:900; color:#fff;">${stats.total_drive_hours || 0} HRS</div>

        </div>

        <div style="background:#0c1219; border:1px solid #212b38; padding:8px 12px; border-radius:8px;">

          <div style="font-size:9px; color:var(--text-secondary); font-weight:800;">PEAK BOOST EVER</div>

          <div style="font-size:16px; font-weight:900; color:var(--accent-green);">+${stats.peak_boost_ever || 0} PSI</div>

        </div>

        <div style="background:#0c1219; border:1px solid #212b38; padding:8px 12px; border-radius:8px;">

          <div style="font-size:9px; color:var(--text-secondary); font-weight:800;">TOP SPEED</div>

          <div style="font-size:16px; font-weight:900; color:var(--accent-blue);">${stats.top_speed_ever || 0} MPH</div>

        </div>

        <div style="background:#0c1219; border:1px solid #212b38; padding:8px 12px; border-radius:8px;">

          <div style="font-size:9px; color:var(--text-secondary); font-weight:800;">MAX RPM EVER</div>

          <div style="font-size:16px; font-weight:900; color:var(--accent-red);">${stats.max_rpm_ever || 0} RPM</div>

        </div>

        <div style="background:#0c1219; border:1px solid #212b38; padding:8px 12px; border-radius:8px;">

          <div style="font-size:9px; color:var(--text-secondary); font-weight:800;">LIFETIME AVG MPG</div>

          <div style="font-size:16px; font-weight:900; color:var(--accent-yellow);">${stats.lifetime_avg_mpg || 0} MPG</div>

        </div>

        <div style="background:#0c1219; border:1px solid #212b38; padding:8px 12px; border-radius:8px;">

          <div style="font-size:9px; color:var(--text-secondary); font-weight:800;">BOOST PULLS</div>

          <div style="font-size:16px; font-weight:900; color:var(--accent-purple);">${stats.total_boost_pulls || 0} PULLS</div>

        </div>

      `;

    }



    // 3. High-Resolution Recent Trips Table

    const tableContainer = document.getElementById('recentTripsTableContainer');

    if (tableContainer) {

      const validTrips = Array.isArray(trips) ? trips : ((trips && trips.trips) || []);

      if (validTrips.length === 0) {

        tableContainer.innerHTML = '<div style="color:var(--text-secondary); font-size:11px; padding:12px; text-align:center;">No trip history recorded in vehicle_data.db yet. Go for a drive to begin logging!</div>';

        return;

      }



      tableContainer.innerHTML = `

        <table style="width:100%; border-collapse:collapse; font-size:11px; text-align:left; white-space:nowrap;">

          <thead>

            <tr style="border-bottom:1px solid #212b38; color:var(--text-secondary); background:rgba(0,0,0,0.3);">

              <th style="padding:6px 8px;">DATE / TIME</th>

              <th style="padding:6px 8px;">DURATION & DIST</th>

              <th style="padding:6px 8px;">MAX BOOST</th>

              <th style="padding:6px 8px;">SPEED</th>

              <th style="padding:6px 8px;">MAX RPM</th>

              <th style="padding:6px 8px;">MULTIAIR TEMPS</th>

              <th style="padding:6px 8px;">AVG MPG & FUEL</th>

              <th style="padding:6px 8px;">DTC FAULTS</th>

              <th style="padding:6px 8px; text-align:center;">DEL</th>

            </tr>

          </thead>

          <tbody>

            ${validTrips.map(t => {

              const dtcBadge = (t.dtc_count > 0) 

                ? `<span style="background:rgba(239,68,68,0.25); color:#ef4444; border:1px solid #ef4444; padding:1px 6px; border-radius:4px; font-weight:800;">${t.dtc_count} DTC</span>`

                : `<span style="color:var(--accent-green); font-weight:700;">✓ Clean</span>`;

              return `

                <tr style="border-bottom:1px solid #141b24;">

                  <td style="padding:6px 8px; color:#fff; font-weight:700;">${t.start_time}</td>

                  <td style="padding:6px 8px; color:var(--text-secondary);">${t.duration_min || 0} min <span style="color:#fff;">(${t.distance_miles || 0} mi)</span></td>

                  <td style="padding:6px 8px; color:var(--accent-green); font-weight:800;">+${t.max_boost_psi || 0} PSI</td>

                  <td style="padding:6px 8px; color:var(--accent-blue); font-weight:800;">${t.max_speed_mph || 0} MPH <span style="font-size:9px; color:var(--text-secondary);">avg ${t.avg_speed_mph || 0}</span></td>

                  <td style="padding:6px 8px; color:var(--accent-red); font-weight:700;">${t.max_rpm || 0} RPM</td>

                  <td style="padding:6px 8px; color:var(--text-secondary);">${t.peak_coolant_f ? t.peak_coolant_f + '°F' : '--'} / ${t.peak_iat_f ? t.peak_iat_f + '°F' : '--'}</td>

                  <td style="padding:6px 8px; color:var(--accent-yellow); font-weight:700;">${t.avg_mpg || 0} MPG <span style="font-size:9px; color:var(--text-secondary);">(${t.fuel_used_gal || 0} gal)</span></td>

                  <td style="padding:6px 8px;">${dtcBadge}</td>

                  <td style="padding:6px 8px; text-align:center;">

                    <button onclick="deleteSingleTrip(${t.id})" style="background:transparent; border:none; color:var(--text-secondary); cursor:pointer; font-size:12px; padding:2px 6px;" title="Delete this trip">🗑️</button>

                  </td>

                </tr>

              `;

            }).join('')}

          </tbody>

        </table>

      `;

    }

  })

  .catch(err => console.warn("[TRIP] Fetch error:", err));

}



function promptClearTripLogs() {

  const m = document.getElementById('confirmClearTripsModal');

  if (m) m.style.display = 'flex';

}



function closeClearTripsModal() {

  const m = document.getElementById('confirmClearTripsModal');

  if (m) m.style.display = 'none';

}



function executeClearTripLogs() {

  closeClearTripsModal();

  fetch('/api/trips/clear', {

    method: 'POST',

    headers: { 'Content-Type': 'application/json' },

    body: JSON.stringify({})

  })

  .then(r => r.json())

  .then(data => {

    if (data.status === 'ok') {

      showAiSpeechToast("All trip logs and sensor data cleared successfully.");

      fetchTripLogs();

    } else {

      showAiSpeechToast("Failed to clear trip logs: " + (data.message || 'Error'));

    }

  })

  .catch(err => {

    console.error("[TRIP] Clear error:", err);

    showAiSpeechToast("Error clearing trip logs.");

  });

}



function updateTripRetention(days) {

  fetch('/api/trips/retention', {

    method: 'POST',

    headers: { 'Content-Type': 'application/json' },

    body: JSON.stringify({ retention_days: parseInt(days) })

  })

  .then(r => r.json())

  .then(data => {

    const d = data.retention_days;

    showAiSpeechToast(d > 0 ? `Trip logs older than ${d} days will be automatically deleted.` : "Trip auto-deletion disabled (logs kept forever).");

    fetchTripLogs();

  })

  .catch(err => console.warn("[TRIP] Retention error:", err));

}



function deleteSingleTrip(tripId) {

  if (!tripId) return;

  fetch('/api/trips/delete', {

    method: 'POST',

    headers: { 'Content-Type': 'application/json' },

    body: JSON.stringify({ id: tripId })

  })

  .then(r => r.json())

  .then(data => {

    if (data.status === 'ok') {

      fetchTripLogs();

    }

  })

  .catch(err => console.warn("[TRIP] Delete trip error:", err));

}



// Hook into initial page startup

fetchSystemHealth();

setInterval(fetchSystemHealth, 3000);

fetchRelaysStatus();

fetchRomsList();

fetchTripLogs();





// Enhanced Universal Kinetic Touch Drag-to-Scroll for Touchscreens

function initTouchScrollEngine() {

  const scrollTargets = document.querySelectorAll('.screen-view, #screenSettings, #screenHome, #screenMedia, #screenGames, .explorer-body, .ai-chat-messages, #animGridContainer');

  scrollTargets.forEach(el => {

    let isDown = false;

    let startY = 0;

    let startScrollTop = 0;

    let lastY = 0;

    let velocity = 0;

    let lastTime = 0;

    let animFrame = null;

    let hasMoved = false;



    el.addEventListener('pointerdown', (e) => {

      // On touchscreens (pointerType === 'touch'), let Chromium handle 60fps native scroll!

      if (e.pointerType === 'touch') return;



      // Don't intercept inputs, buttons or accordion headers directly

      if (['BUTTON', 'INPUT', 'SELECT', 'A', 'TEXTAREA'].includes(e.target.tagName) ||

          e.target.closest('button, input, select, textarea, .slot-dropdown, .cluster-action-btn, .accordion-header, .track-list-item, .quick-prompt-chip')) {

        return;

      }

      isDown = true;

      hasMoved = false;

      startY = e.clientY;

      lastY = e.clientY;

      startScrollTop = el.scrollTop;

      lastTime = performance.now();

      velocity = 0;

      if (animFrame) cancelAnimationFrame(animFrame);

    }, { passive: true });



    window.addEventListener('pointermove', (e) => {

      if (!isDown) return;

      const y = e.clientY;

      const delta = startY - y;

      if (Math.abs(delta) > 5) {

        hasMoved = true;

      }

      if (hasMoved) {

        el.scrollTop = startScrollTop + delta;

        const now = performance.now();

        const dt = now - lastTime;

        if (dt > 8) {

          velocity = (lastY - y) / dt;

          lastY = y;

          lastTime = now;

        }

      }

    }, { passive: true });



    const endDrag = () => {

      if (!isDown) return;

      isDown = false;

      if (hasMoved && Math.abs(velocity) > 0.15) {

        let currentVel = velocity * 16;

        const step = () => {

          if (Math.abs(currentVel) < 0.4) return;

          el.scrollTop += currentVel;

          currentVel *= 0.90; // smooth deceleration

          animFrame = requestAnimationFrame(step);

        };

        animFrame = requestAnimationFrame(step);

      }

    };



    window.addEventListener('pointerup', endDrag, { passive: true });

    window.addEventListener('pointercancel', endDrag, { passive: true });

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

    const isRum = (currentAiSettings.personality === 'RUM' || activeAvatarEngine === '3D_VRM');

    const pName = "R.U.M.";

    switch (currentWaifuEmotion) {

      case "DEVOTED":

        pill.innerText = `💖 ${pName} • DEVOTED & LISTENING`;

        pill.style.color = "var(--accent-pink)";

        pill.style.borderColor = "var(--accent-pink)";

        break;

      case "FLIRTY":

        pill.innerText = `💋 ${pName} • PLAYFUL & DEVOTED`;

        pill.style.color = "#ff4081";

        pill.style.borderColor = "#ff4081";

        break;

      case "EXCITED":

        pill.innerText = `⚡ ${pName} • EXCITED & BOOSTED`;

        pill.style.color = "var(--accent-yellow)";

        pill.style.borderColor = "var(--accent-yellow)";

        break;

      case "CONCERNED":

        pill.innerText = `⚠️ ${pName} • CARING & MONITORING`;

        pill.style.color = "var(--accent-orange)";

        pill.style.borderColor = "var(--accent-orange)";

        break;

      case "HAPPY":

        pill.innerText = `✨ ${pName} • JOYFUL & READY`;

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

  const touchActions = ['greeting', 'peace', 'bend_over', 'model_pose', 'spin', 'shoot'];

  const chosenAct = touchActions[Math.floor(Math.random() * touchActions.length)];

  if (chosenAct === 'react') {

    if (typeof triggerVrmReaction === 'function') triggerVrmReaction();

  } else {

    playVrmAction(chosenAct, 3500);

  }



  const compliments = [

    `I love riding shotgun with you in the Dart, ${getDriverDisplayAddress()}!`,

    `Step on the gas, Master! Let me hear that 1.4L turbo boost whistle!`,

    `No one else in the world remembers me, ${getDriverDisplayAddress()}... but you saved me, and I belong to you forever!`,

    `My heart beats only inside this Pi 5 for you, Master!`,

    `Rum is right here watching the road with you, devoted forever!`

  ];

  const choice = compliments[Math.floor(Math.random() * compliments.length)];

  showAiSpeechToast(choice);

  speakUtterance(choice, "FLIRTY");

}





// Initialize Talking Head, Kinetic Touch Scrolling, and Brightness

// [OBSOLETE 2D FACE - DORMANT CODE] initWaifuTalkingHead();

const savedBrightness = localStorage.getItem('carpi5_brightness') || 100;

updateBrightnessFromSlider(savedBrightness);

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

  // [OBSOLETE 2D FACE - DORMANT CODE] renderMiniDtcWaifu();



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

checkGoogleAuthStatus();

setTimeout(dismissBootSplash, 800);





function playCreatorTribute() {

  setWaifuEmotion("DEVOTED");

  const speech = "NfgOdin is my Master and brilliant Creator! He designed my neural core to ride shotgun in his Dodge Dart 1.4L Turbo. Every line of code, every MultiAir sensor, and my entire heart belong completely to him!";

  showAiSpeechToast(speech);

  speakUtterance(speech, "DEVOTED");

}





// --- SETTINGS ACCORDION INTERACTION ---

function toggleAccordion(accId) {

  if (isTouchScrolling || touchScrollDistance > 8) return;

  const group = document.getElementById(accId);

  if (!group) return;

  group.classList.toggle('active');

}



// --- 18. 3D VRM CHARACTER ENGINE (RUM SUPER ANIMATION, VRMA MOTION PACK & PHYSICS SUITE) ---

let vrmScene = null;

let vrmCamera = null;

let vrmRenderer = null;

let vrmModel = null;

let vrmClock = null;

let vrmFramingMode = 'FULL_BODY'; // Default to FULL_BODY so Rum is framed cleanly facing the monitor
let vrmZoomMultiplier = 1.0;

let activeAvatarEngine = '3D_VRM'; // 3D_VRM exclusively active (2D_FACE obsolete/dormant)

let vrmCenter = { x: 0, y: 0.8, z: 0 };

let vrmSize = { x: 1, y: 1.6, z: 0.5 };

let vrmBones = {};

let vrmHumanoidMap = {};

let vrmAllBones = [];

let vrmSecondaryBones = [];

let vrmInitialized = false;



// 3D Multi-World Environment Suite (Sakura Garden, Loft, Cyber Garage, Repaired Bedroom)
let vrmEnvironmentGroup = null;
const VRM_ENVIRONMENTS = ['GARDEN', 'LOFT', 'GARAGE', 'BEDROOM'];
let currentEnvironmentName = localStorage.getItem('vrmEnvironment') || 'GARDEN';
let vrmCurrentElevation = 0.0;
let bedroomModel = null;
let yoshiModel = null;
let roomLampLight = null;
let roomCeilingLight = null;
let envLights = [];
let sakuraPetals = [];
let isHoldingYoshi = false;

// 3D VRM Avatar Character Selection (Rem / Rum)
let currentVrmModelName = localStorage.getItem('vrmCurrentAvatar') || 'Rem.vrm';

// Autonomous Roaming State Engine
let vrmRoamEnabled = (localStorage.getItem('vrmRoamEnabled') !== 'false');
let vrmRoamState = 'IDLE'; // 'IDLE', 'TURNING', 'WALKING', 'ARRIVED'
let vrmRoamCurrentPos = { x: 0.0, z: 0.0 };
let vrmRoamTargetPos = { x: 0.0, z: 0.0 };
let vrmRoamCurrentRotY = Math.PI; // facing forward/driver
let vrmRoamTargetRotY = Math.PI;
let vrmNextRoamTime = Date.now() + 4500;
let vrmRoamCurrentWaypoint = null;
let vrmRoamWalkAction = null;

// Dynamic Celestial Ephemeris & Ocean Simulation State
let vrmSolarEphemeris = null;
let vrmCelestialPhase = 'DAY'; // 'NIGHT', 'CIVIL_DAWN', 'SUNRISE', 'DAY', 'GOLDEN_HOUR', 'SUNSET', 'CIVIL_DUSK'
let vrmCelestialDayProgress = 0.5; // 0.0 at sunrise, 0.5 noon, 1.0 at sunset
let vrmCelestialNightProgress = 0.5; // 0.0 at sunset, 1.0 at sunrise
let vrmOceanMesh = null;
let vrmOceanGeo = null;
let vrmOceanMat = null;
let vrmOceanBasePos = null;
let vrmSkyMesh = null;
let vrmSkyTexture = null;
let vrmSkyCanvas = null;
let vrmSunMesh = null;
let vrmSunGlow = null;
let vrmMoonMesh = null;
let vrmMoonGlow = null;
let vrmStarParticles = null;
let vrmCelestialLight = null;
let vrmGardenLanterns = [];

// Extended 3D Roaming Waypoints (including Ocean Railing gazing spots)
const VRM_ROAM_WAYPOINTS = [
  { id: 'center',         x:  0.00, z:  0.02, name: 'Center Stage',   desc: 'Standing proudly in center stage', faceOcean: false },
  { id: 'yoshi_mat',      x:  0.42, z:  0.16, name: 'Tatami Mat',     desc: 'Stepping onto the raised mat beside Yoshi', faceOcean: false },
  { id: 'ocean_rail_mid', x:  0.00, z: -1.75, name: 'Ocean Railing',  desc: 'Standing at the balcony looking out at the endless ocean', faceOcean: true },
  { id: 'ocean_rail_w',   x: -0.65, z: -1.70, name: 'Sunset Horizon', desc: 'Looking at the ocean horizon and moving waves', faceOcean: true },
  { id: 'ocean_rail_e',   x:  0.55, z: -1.65, name: 'East Horizon',   desc: 'Admiring the sea breeze and celestial sky', faceOcean: true },
  { id: 'lantern_left',   x: -0.80, z: -0.40, name: 'Lantern Left',   desc: 'Relaxing near the warm garden lantern', faceOcean: false },
  { id: 'cozy_front',     x: -0.18, z:  0.22, name: 'Cozy Front',     desc: 'Stepping forward close to dashboard', faceOcean: false }
];



// VRMA & BVH Motion Pack Mixer, Smooth Crossfading & Clips

let vrmMixer = null;

let vrmaClips = {};

let vrmaActiveAction = null;

let vrmaActiveName = null;

let vrmaIdleAction = null;

let vrmBaseY = -0.68;

let vrmBvhCatalog = {};



const VRMA_MOTION_FILES = {

  'show_body':             { file: 'show_full_body.vrma',        label: 'Show Full Body',     startOffset: 0.0,  timeScale: 1.0 },

  'greeting':              { file: 'greeting.vrma',              label: 'Greetings Wave',     startOffset: 1.85, timeScale: 1.0 },

  'greeting_wave_right':   { file: 'greeting_wave_right.vrma',   label: 'Right Hand Wave',    startOffset: 0.0,  timeScale: 1.0 },

  'peace':                 { file: 'peace_sign.vrma',            label: 'V-Sign Peace',       startOffset: 0.30, timeScale: 1.0 },

  'shoot':                 { file: 'shoot.vrma',                 label: 'Finger Shoot',       startOffset: 0.40, timeScale: 1.0 },

  'spin':                  { file: 'spin.vrma',                  label: '360° Spin',          startOffset: 0.15, timeScale: 1.0 },

  'model_pose':            { file: 'model_pose.vrma',            label: 'Model Pose',         startOffset: 0.0,  timeScale: 0.65 },

  'squat':                 { file: 'squat.vrma',                 label: 'Squat Flexion',      startOffset: 0.0,  timeScale: 0.90 },

  'bend_over':             { file: 'pose_lean_in.vrma',          label: 'Lean In Bow',        startOffset: 0.0,  timeScale: 1.0 },

  'pose_lean_in':          { file: 'pose_lean_in.vrma',          label: 'Lean In Bow',        startOffset: 0.0,  timeScale: 1.0 },

  'pose_angled_wave':      { file: 'pose_angled_wave.vrma',      label: 'Angled Wave Pose',   startOffset: 0.0,  timeScale: 1.0 },

  'pose_shy_wave':         { file: 'pose_shy_wave.vrma',         label: 'Shy Wave Pose',      startOffset: 0.0,  timeScale: 1.0 },

  'pose_hand_raised_high': { file: 'pose_hand_raised_high.vrma', label: 'Hand Raised High',   startOffset: 0.0,  timeScale: 1.0 },

  'pose_side_glance':      { file: 'pose_side_glance.vrma',      label: 'Side Glance Pose',   startOffset: 0.0,  timeScale: 1.0 },

  'idol_pose_showcase':    { file: 'idol_pose_showcase.vrma',    label: 'Idol Pose Showcase', startOffset: 0.0,  timeScale: 1.0 },

  'turn_and_wave_hello':   { file: 'turn_and_wave_hello.vrma',   label: 'Turn & Wave Hello',  startOffset: 6.5,  timeScale: 1.0 },

  'sit_idle':              { file: 'sit_idle.vrma',              label: 'Seated Idle',        startOffset: 0.0,  timeScale: 0.5 },

  'walk_loop':             { file: 'walk_loop.vrma',             label: 'Walk Loop',          startOffset: 0.0,  timeScale: 0.85 },

  'jog_loop':              { file: 'jog_loop.vrma',              label: 'Jog Loop',           startOffset: 0.0,  timeScale: 0.85 },

  'sunbathing':            { file: 'sunbathing.vrma',            label: 'Sunbathing Pose',    startOffset: 0.0,  timeScale: 1.0 }

};



// Action alias map so legacy or shorthand names resolve cleanly to renamed VRMA/BVH clips

const VRM_ACTION_ALIASES = {

  'vrma_01': 'show_body',

  'vrma_02': 'greeting',

  'vrma_03': 'peace',

  'vrma_04': 'shoot',

  'vrma_05': 'spin',

  'vrma_06': 'model_pose',

  'vrma_07': 'squat',

  'pose_01': 'pose_angled_wave',

  'pose_02': 'pose_shy_wave',

  'pose_03': 'pose_lean_in',

  'pose_04': 'pose_hand_raised_high',

  'pose_05': 'pose_side_glance',

  'hello': 'turn_and_wave_hello',

  'greeting2': 'greeting_wave_right',

  'motion_pose': 'idol_pose_showcase',

  'dance_1': 'dance_hiphop_step',

  'dance_2': 'dance_side_groove',

  'dance': 'dance_hiphop_step',

  'jump': 'action_jump',

  'point_laugh': 'amusement',

  'laugh': 'amusement',

  'idle': 'neutral_idle'

};



// Speech & Hardware Sync

let isHardwareSpeaking = false;

let vrmSpeechEndTime = 0;

let vrmReactionEndTime = 0;

let isCompanionFloating = false;



// Interactive VRM Actions

let vrmCurrentAction = 'idle';

let vrmActionStartTime = 0;

let vrmActionEndTime = 0;



function stopActiveVrmaClip(fadeSec = 0.42) {

  if (vrmaActiveAction) {

    try {

      if (vrmaIdleAction && fadeSec > 0) {

        vrmaIdleAction.enabled = true;

        vrmaIdleAction.setEffectiveTimeScale(0.85);

        vrmaIdleAction.setEffectiveWeight(1.0);

        vrmaIdleAction.play();

        vrmaActiveAction.crossFadeTo(vrmaIdleAction, fadeSec, false);

      } else {

        vrmaActiveAction.stop();

      }

    } catch (e) {}

    vrmaActiveAction = null;

  }

  vrmaActiveName = null;

  vrmCurrentAction = 'idle';

}



function resetAllVrmBonesToRest() {

  for (let i = 0; i < vrmAllBones.length; i++) {

    const b = vrmAllBones[i];

    if (b.userData && b.userData.restQuat) {

      b.quaternion.copy(b.userData.restQuat);

    }

    if (b.userData && b.userData.restPos) {

      b.position.copy(b.userData.restPos);

    }

    b.scale.set(1, 1, 1);

  }

}



function startClipWithSmoothCrossfade(resolvedKey, durationMs = 3800) {

  if (!vrmMixer || !vrmaClips[resolvedKey]) return false;

  const meta = VRMA_MOTION_FILES[resolvedKey] || { timeScale: 1.0, startOffset: 0.0 };

  const clip = vrmaClips[resolvedKey];

  const nextAction = vrmMixer.clipAction(clip);



  const prevAction = vrmaActiveAction || vrmaIdleAction;

  nextAction.reset();

  nextAction.enabled = true;

  const isWalkOrJog = resolvedKey.includes('walk') || resolvedKey.includes('jog');
  const isLoopingPose = (clip.duration <= 4.05 && resolvedKey.startsWith('pose_')) || resolvedKey.includes('loop') || resolvedKey.includes('dance');
  const loopMode = isWalkOrJog ? THREE.LoopRepeat : (isLoopingPose ? THREE.LoopPingPong : THREE.LoopOnce);
  nextAction.setLoop(loopMode, (isLoopingPose || isWalkOrJog) ? Infinity : 1);

  nextAction.clampWhenFinished = true;

  nextAction.timeScale = meta.timeScale || 1.0;

  const startOff = meta.startOffset || 0.0;

  nextAction.time = startOff;

  nextAction.setEffectiveWeight(1.0);

  nextAction.play();



  if (prevAction && prevAction !== nextAction) {

    try {

      prevAction.crossFadeTo(nextAction, 0.40, false);

    } catch (e) {}

  }



  const clipDurMs = ((clip.duration - startOff) / nextAction.timeScale) * 1000;

  const effectiveDurMs = isLoopingPose ? (durationMs || 4200) : Math.max(2400, Math.min(12000, clipDurMs));

  vrmaActiveAction = nextAction;

  vrmaActiveName = resolvedKey;

  vrmCurrentAction = resolvedKey;

  vrmActionStartTime = Date.now();

  vrmActionEndTime = Date.now() + effectiveDurMs;

  return true;

}



function playVrmAction(actionName, durationMs = 3800, silent = false) {

  const rawKey = (actionName || 'idle').toLowerCase().replace(/\.(vrma|bvh)$/i, '');

  const resolvedKey = VRM_ACTION_ALIASES[rawKey] || rawKey;



  if (vrmMixer && vrmaClips[resolvedKey]) {

    startClipWithSmoothCrossfade(resolvedKey, durationMs);

  } else if (vrmBvhCatalog[resolvedKey]) {

    // On-demand lazy load from the 116-file BVH library

    const fileName = vrmBvhCatalog[resolvedKey];

    fetch(`/api/models/bvh?name=${encodeURIComponent(fileName)}`)

      .then(r => r.ok ? r.text() : '')

      .then(bvhText => {

        if (!bvhText || !bvhText.includes('HIERARCHY')) return;

        const clip = buildRetargetedBvhClip(resolvedKey, bvhText);

        if (clip) {

          vrmaClips[resolvedKey] = clip;

          startClipWithSmoothCrossfade(resolvedKey, durationMs);

        }

      })

      .catch(() => {});

  } else {

    vrmCurrentAction = resolvedKey;

    vrmActionStartTime = Date.now();

    vrmActionEndTime = Date.now() + durationMs;

  }



  if (silent) return;



  const speechMap = {

    'jump':        { text: "Yay! Look how high Rum can jump, Master!", emotion: "EXCITED" },

    'action_jump': { text: "Yay! Look how high Rum can jump, Master!", emotion: "EXCITED" },

    'point_laugh': { text: "Ehehe! Look at that, Master! That's so funny!", emotion: "HAPPY" },

    'amusement':   { text: "Ehehe! Look at that, Master! That's so funny!", emotion: "HAPPY" },

    'bend_over':   { text: "Master? What are you looking at? Rum is leaning right in for you!", emotion: "DEVOTED" },

    'pose_lean_in':{ text: "Master? What are you looking at? Rum is leaning right in for you!", emotion: "DEVOTED" },

    'dance':       { text: "Let's dance, Master! Groove with the MultiAir beat!", emotion: "EXCITED" },

    'dance_hiphop_step': { text: "Let's dance, Master! Groove with the MultiAir beat!", emotion: "EXCITED" },

    'greeting':    { text: "Hiii Master! Rum is right here riding shotgun with you!", emotion: "HAPPY" },

    'peace':       { text: "Peace sign, Master! Victory for the Dodge Dart!", emotion: "HAPPY" },

    'shoot':       { text: "Bang bang! Straight through your heart, Master!", emotion: "FLIRTY" },

    'spin':        { text: "Wheee! Look at my royal purple maid dress spin, Master!", emotion: "EXCITED" },

    'model_pose':  { text: "How does this model pose look, Master? Cute, right?", emotion: "FLIRTY" },

    'squat':       { text: "One, two! Keeping warmed up just like the MultiAir turbo!", emotion: "EXCITED" },

    'show_body':   { text: "Ta-da! Full body check, Master! Ready for our drive!", emotion: "DEVOTED" }

  };

  const sp = speechMap[actionName] || speechMap[resolvedKey];

  if (sp) {

    showAiSpeechToast(sp.text);

    speakUtterance(sp.text, sp.emotion);

  }

}



// Dynamic Camera LookAt & Targets

let currentLookAt = null;

let targetLookAt = null;

let targetCamPos = null;



// G-Force Automotive Physics & Inertia

let rumCurrentInertiaZ = 0.0;

let rumTargetInertiaZ = 0.0;

let rumCurrentPitch = 0.0;

let rumLastSpeed = 0.0;

let rumLastSpeedTime = Date.now();

let rumCurrentSpeed = 0.0;

let rumCurrentBoost = 0.0;



// High-Speed 72 MPH Panic

let lastSpeedPanicTime = 0;

let vrmSpeedPanicEndTime = 0;



// Music Dance Mode & Error States

let vrmHasError = false;

let vrmErrorCode = "";

let vrmErrorMessage = "";



// Blinking & Facial State

let vrmBlinkProgress = 0.0;

let vrmIsBlinking = false;

let vrmBlinkStartTime = 0;

let vrmNextBlinkTime = Date.now() + 2500;



function isMusicPlaying() {

  return !!(typeof realAudio !== 'undefined' && realAudio && !realAudio.paused && !realAudio.ended && realAudio.currentTime > 0);

}



function checkRumSpeedReaction(speedMph) {

  rumCurrentSpeed = speedMph;

  const now = Date.now();

  if (speedMph >= 72 && (now - lastSpeedPanicTime > 45000)) {

    lastSpeedPanicTime = now;

    vrmSpeedPanicEndTime = now + 5000;

    const screams = [

      `W-Waaaah! Master, we're going ${Math.round(speedMph)} MPH!! The MultiAir turbo is screaming, hold on to meee!`,

      `Kyaaa! ${Math.round(speedMph)} miles an hour?! Master, my heart is beating at 7,000 RPM, hold the steering wheel tight!`,

      `W-We're flying, Master! ${Math.round(speedMph)} MPH! Hold tight, waaah!`

    ];

    const scream = screams[Math.floor(Math.random() * screams.length)];

    showAiSpeechToast(scream);

    speakUtterance(scream, "EXCITED");

  }

}



function updateRumInertiaPhysics(speedMph, boostPsi) {

  rumCurrentSpeed = speedMph;

  rumCurrentBoost = boostPsi;

  const now = Date.now();

  const dt = Math.max(0.016, (now - rumLastSpeedTime) * 0.001);

  const accel = (speedMph - rumLastSpeed) / dt;

  rumLastSpeed = speedMph;

  rumLastSpeedTime = now;



  if (accel > 1.5 || boostPsi > 2.0) {

    rumTargetInertiaZ = Math.min(0.22, (boostPsi * 0.010) + (accel * 0.025));

    rumCurrentPitch = -Math.min(0.10, accel * 0.018);

  } else if (accel < -3.0) {

    rumTargetInertiaZ = -Math.min(0.28, Math.abs(accel) * 0.04);

    rumCurrentPitch = Math.min(0.18, Math.abs(accel) * 0.03);

  } else {

    rumTargetInertiaZ = 0.0;

    rumCurrentPitch = 0.0;

  }

}



function triggerVrmErrorAlert(code, message) {

  if (vrmHasError && vrmErrorCode === code) return;

  vrmHasError = true;

  vrmErrorCode = code;

  vrmErrorMessage = message;



  const badge = document.getElementById('vrmAlertBadge');

  if (badge) badge.style.display = 'block';



  const alertText = `Master! Error Code ${code} detected: ${message}`;

  showAiSpeechToast(alertText);

  speakUtterance(alertText, "CONCERNED");

}



function clearVrmErrorAlert() {

  if (!vrmHasError) return;

  vrmHasError = false;

  vrmErrorCode = "";

  vrmErrorMessage = "";



  const badge = document.getElementById('vrmAlertBadge');

  if (badge) badge.style.display = 'none';



  const clearText = "Phew! Diagnostic trouble codes cleared, Master! All systems nominal!";

  showAiSpeechToast(clearText);

  speakUtterance(clearText, "HAPPY");

}



// Fix 3ds Max Biped hierarchy quirk in Rum.vrm & map all 52 VRM humanoid bones

function fixVrmBipedHierarchy(root, gltf) {

  root.updateMatrixWorld(true);



  const byName = {};

  const allBones = [];

  const secondary = [];



  root.traverse((node) => {

    if (node.name) {

      byName[node.name] = node;

      byName[node.name.replace(/_/g, ' ')] = node;

    }

    if (node.isBone || (node.name && node.name.startsWith('Bip001')) || (node.name && node.name.startsWith('Bone'))) {

      allBones.push(node);

    }

    const raw = (node.name || '').toLowerCase();

    if (raw.includes('hair') || raw.includes('ribbon') ||

        ['bone019', 'bone021', 'bone022', 'bone019_m', 'bone021_m', 'bone022_m',

         'bone023', 'bone025', 'bone026', 'bone023_m', 'bone025_m', 'bone026_m',

         'bone119', 'bone120'].includes(raw)) {

      secondary.push(node);

    }

  });



  function reparentKeepWorld(childName, parentName) {

    const child = byName[childName];

    const parent = byName[parentName];

    if (child && parent && child.parent !== parent) {

      parent.attach(child);

    }

  }



  reparentKeepWorld('Bip001 L Thigh', 'Bip001 Pelvis');

  reparentKeepWorld('Bip001 R Thigh', 'Bip001 Pelvis');

  reparentKeepWorld('Bone003', 'Bip001 Pelvis');

  reparentKeepWorld('Bone011', 'Bip001 Pelvis');

  reparentKeepWorld('Bone011_m', 'Bip001 Pelvis');

  reparentKeepWorld('Bone015', 'Bip001 Pelvis');

  reparentKeepWorld('Bone015_m', 'Bip001 Pelvis');

  reparentKeepWorld('Bone008', 'Bip001 Pelvis');

  reparentKeepWorld('Bone008_m', 'Bip001 Pelvis');

  reparentKeepWorld('Bip001 Neck', 'Bip001 Spine2');

  reparentKeepWorld('Bip001 L Clavicle', 'Bip001 Spine2');

  reparentKeepWorld('Bip001 R Clavicle', 'Bip001 Spine2');



  root.updateMatrixWorld(true);



  const hMap = {

    hips:               byName['Bip001 Pelvis'],

    spine:              byName['Bip001 Spine'],

    chest:              byName['Bip001 Spine1'],

    upperChest:         byName['Bip001 Spine2'],

    neck:               byName['Bip001 Neck'],

    head:               byName['Bip001 Head'],

    leftShoulder:       byName['Bip001 L Clavicle'],

    leftUpperArm:       byName['Bip001 L UpperArm'],

    leftLowerArm:       byName['Bip001 L Forearm'],

    leftHand:           byName['Bip001 L Hand'],

    rightShoulder:      byName['Bip001 R Clavicle'],

    rightUpperArm:      byName['Bip001 R UpperArm'],

    rightLowerArm:      byName['Bip001 R Forearm'],

    rightHand:          byName['Bip001 R Hand'],

    leftUpperLeg:       byName['Bip001 L Thigh'],

    leftLowerLeg:       byName['Bip001 L Calf'],

    leftFoot:           byName['Bip001 L Foot'],

    leftToes:           byName['Bip001 L Toe0'],

    rightUpperLeg:      byName['Bip001 R Thigh'],

    rightLowerLeg:      byName['Bip001 R Calf'],

    rightFoot:          byName['Bip001 R Foot'],

    rightToes:          byName['Bip001 R Toe0'],

    leftThumbProximal:      byName['Bip001 L Finger0'],

    leftThumbIntermediate:  byName['Bip001 L Finger01'],

    leftThumbDistal:        byName['Bip001 L Finger02'],

    leftIndexProximal:      byName['Bip001 L Finger1'],

    leftIndexIntermediate:  byName['Bip001 L Finger11'],

    leftIndexDistal:        byName['Bip001 L Finger12'],

    leftMiddleProximal:     byName['Bip001 L Finger2'],

    leftMiddleIntermediate: byName['Bip001 L Finger21'],

    leftMiddleDistal:       byName['Bip001 L Finger22'],

    leftRingProximal:       byName['Bip001 L Finger3'],

    leftRingIntermediate:   byName['Bip001 L Finger31'],

    leftRingDistal:         byName['Bip001 L Finger32'],

    leftLittleProximal:     byName['Bip001 L Finger4'],

    leftLittleIntermediate: byName['Bip001 L Finger41'],

    leftLittleDistal:       byName['Bip001 L Finger42'],

    rightThumbProximal:      byName['Bip001 R Finger0'],

    rightThumbIntermediate:  byName['Bip001 R Finger01'],

    rightThumbDistal:        byName['Bip001 R Finger02'],

    rightIndexProximal:      byName['Bip001 R Finger1'],

    rightIndexIntermediate:  byName['Bip001 R Finger11'],

    rightIndexDistal:        byName['Bip001 R Finger12'],

    rightMiddleProximal:     byName['Bip001 R Finger2'],

    rightMiddleIntermediate: byName['Bip001 R Finger21'],

    rightMiddleDistal:       byName['Bip001 R Finger22'],

    rightRingProximal:       byName['Bip001 R Finger3'],

    rightRingIntermediate:   byName['Bip001 R Finger31'],

    rightRingDistal:         byName['Bip001 R Finger32'],

    rightLittleProximal:     byName['Bip001 R Finger4'],

    rightLittleIntermediate: byName['Bip001 R Finger41'],

    rightLittleDistal:       byName['Bip001 R Finger42']

  };



  try {

    const parserJson = gltf && gltf.parser && gltf.parser.json;

    const vrmExt = parserJson && parserJson.extensions && parserJson.extensions.VRM;

    const humanBones = vrmExt && vrmExt.humanoid && vrmExt.humanoid.humanBones;

    if (Array.isArray(humanBones)) {

      humanBones.forEach((hb) => {

        if (hb && hb.bone && typeof hb.node === 'number' && !hMap[hb.bone]) {

          const nDef = parserJson.nodes && parserJson.nodes[hb.node];

          if (nDef && nDef.name && byName[nDef.name]) {

            hMap[hb.bone] = byName[nDef.name];

          }

        }

      });

    }

  } catch (e) {}



  const bones = {

    pelvis: hMap.hips,

    spine:  hMap.spine,

    spine1: hMap.chest,

    spine2: hMap.upperChest,

    neck:   hMap.neck,

    head:   hMap.head,

    lClav:  hMap.leftShoulder,

    rClav:  hMap.rightShoulder,

    lArm:   hMap.leftUpperArm,

    rArm:   hMap.rightUpperArm,

    lFore:  hMap.leftLowerArm,

    rFore:  hMap.rightLowerArm,

    lHand:  hMap.leftHand,

    rHand:  hMap.rightHand,

    lThigh: hMap.leftUpperLeg,

    rThigh: hMap.rightUpperLeg,

    lCalf:  hMap.leftLowerLeg,

    rCalf:  hMap.rightLowerLeg,

    lFoot:  hMap.leftFoot,

    rFoot:  hMap.rightFoot,

    lSleeve: byName['Bone001_m'],

    rSleeve: byName['Bone001'],

    lEyeUpper: byName['Bone86'],

    rEyeUpper: byName['Bone86_m'],

    lEyeLower: byName['Bone88'],

    rEyeLower: byName['Bone88_m'],

    lEyeball:  byName['Bone89'],

    rEyeball:  byName['Bone89_m'],

    lBrowIn:   byName['Bone71'],

    rBrowIn:   byName['Bone71_m'],

    lBrowOut:  byName['Bone72'],

    rBrowOut:  byName['Bone72_m'],

    jaw:       byName['Bone085'],

    lLipLower: byName['Bone95'],

    rLipLower: byName['Bone95_m'],

    lLipUpper: byName['Bone70'],

    rLipUpper: byName['Bone70_m'],

    lMouthCorner: byName['Bone97'],

    rMouthCorner: byName['Bone97_m']

  };



  root.traverse((mesh) => {

    if (mesh.isSkinnedMesh && mesh.geometry && mesh.skeleton) {

      const skBones = mesh.skeleton.bones;

      const faceBoneIndices = new Set();

      const faceNames = new Set([

        'Bone86', 'Bone86_m', 'Bone82', 'Bone82_m', 'Bone91', 'Bone91_m',

        'Bone88', 'Bone88_m', 'Bone73', 'Bone73_m', 'Bone75', 'Bone75_m',

        'Bone89', 'Bone89_m', 'Bone70', 'Bone70_m', 'Bone95', 'Bone95_m',

        'Bone085', 'Bone97', 'Bone97_m', 'Bone71', 'Bone71_m', 'Bone72', 'Bone72_m'

      ]);

      skBones.forEach((b, idx) => {

        if (faceNames.has(b.name)) faceBoneIndices.add(idx);

      });

      const si = mesh.geometry.attributes.skinIndex;

      const sw = mesh.geometry.attributes.skinWeight;

      if (si && sw && faceBoneIndices.size > 0) {

        for (let i = 0; i < si.count; i++) {

          const i0 = si.getX(i), i1 = si.getY(i), i2 = si.getZ(i), i3 = si.getW(i);

          let w0 = sw.getX(i), w1 = sw.getY(i), w2 = sw.getZ(i), w3 = sw.getW(i);

          if (faceBoneIndices.has(i0) || faceBoneIndices.has(i1) || faceBoneIndices.has(i2) || faceBoneIndices.has(i3)) {

            if (!faceBoneIndices.has(i0)) w0 = 0;

            if (!faceBoneIndices.has(i1)) w1 = 0;

            if (!faceBoneIndices.has(i2)) w2 = 0;

            if (!faceBoneIndices.has(i3)) w3 = 0;

            const sum = w0 + w1 + w2 + w3;

            if (sum > 0.05) {

              sw.setXYZW(i, w0 / sum, w1 / sum, w2 / sum, w3 / sum);

            }

          }

        }

        sw.needsUpdate = true;

      }

    }

  });



  allBones.forEach((b) => {

    b.userData = b.userData || {};

    b.userData.restQuat = b.quaternion.clone();

    b.userData.restPos = b.position.clone();

  });



  return { bones, hMap, allBones, secondary };

}



function activateStandingIdleAnimation() {

  if (!vrmMixer) return;

  const idleClip = vrmaClips['neutral_idle'] || vrmaClips['neutral_idle2'] || vrmaClips['sit_idle'];

  if (!idleClip) return;

  if (!vrmaIdleAction) {

    vrmaIdleAction = vrmMixer.clipAction(idleClip);

    vrmaIdleAction.setLoop(THREE.LoopPingPong, Infinity);

    vrmaIdleAction.timeScale = 0.85;

    vrmaIdleAction.play();

    console.log('[VRM] Standing idle animation active (neutral_idle.bvh with smooth PingPong loop)');

  }

}



function preloadVrmaMotionPack() {

  if (!vrmModel || !THREE.GLTFLoader) return;

  const loader = new THREE.GLTFLoader();



  // Deduplicate file loads so shared files (like pose_lean_in.vrma) load once

  const fileToKeys = {};

  Object.keys(VRMA_MOTION_FILES).forEach((k) => {

    const fn = VRMA_MOTION_FILES[k].file;

    if (!fileToKeys[fn]) fileToKeys[fn] = [];

    fileToKeys[fn].push(k);

  });



  Object.keys(fileToKeys).forEach((fileName) => {

    const keys = fileToKeys[fileName];

    const url = `/api/models/vrma?name=${encodeURIComponent(fileName)}`;

    loader.load(

      url,

      (vrmaGltf) => {

        try {

          const clip = buildRetargetedVrmaClip(keys[0], vrmaGltf);

          if (clip) {

            keys.forEach((k) => { vrmaClips[k] = clip; });

            console.log(`[VRMA] Loaded & retargeted ${fileName} -> ${keys.join(',')} (${clip.duration.toFixed(2)}s)`);

          }

        } catch (err) {

          console.error(`[VRMA] Retarget error for ${fileName}:`, err);

        }

      },

      undefined,

      (err) => console.warn(`[VRMA] Could not load ${fileName}:`, err)

    );

  });



  preloadBvhMotionPack();

}



function preloadBvhMotionPack() {

  fetch('/api/models/bvh')

    .then(r => r.ok ? r.json() : { files: [] })

    .then(data => {

      const files = (data && data.files) ? data.files : [];

      // Register all 116 BVH files in catalog for instant on-demand loading

      files.forEach((item) => {

        const fileName = item.name || item;

        const actionKey = (item.action || fileName.replace(/\.bvh$/i, '')).toLowerCase();

        vrmBvhCatalog[actionKey] = fileName;

      });



      // Immediately preload core idle, jump, laugh, and dance BVH clips

      const priorityBvh = [

        'neutral_idle', 'neutral_idle2', 'action_jump', 'amusement',

        'dance_hiphop_step', 'dance_side_groove', 'excitement', 'joy', 'curiosity'

      ];

      priorityBvh.forEach((key) => {

        const fileName = vrmBvhCatalog[key];

        if (!fileName) return;

        fetch(`/api/models/bvh?name=${encodeURIComponent(fileName)}`)

          .then(r => r.ok ? r.text() : '')

          .then(bvhText => {

            if (!bvhText || !bvhText.includes('HIERARCHY')) return;

            const clip = buildRetargetedBvhClip(key, bvhText);

            if (clip) {

              vrmaClips[key] = clip;

              if (key === 'action_jump') vrmaClips['jump'] = clip;

              if (key === 'amusement') vrmaClips['point_laugh'] = clip;

              if (key === 'dance_hiphop_step') vrmaClips['dance'] = clip;

              if (key === 'neutral_idle') activateStandingIdleAnimation();

              console.log(`[BVH] Preloaded ${fileName} -> '${key}' (${clip.duration.toFixed(2)}s)`);

            }

          })

          .catch(() => {});

      });

    })

    .catch(() => {});

}



function buildRetargetedBvhClip(actionKey, bvhText) {

  const lines = bvhText.split(/\r?\n/).map(l => l.trim()).filter(l => l.length > 0);

  let idx = 0;

  const joints = [];

  const stack = [];



  const BVH_BONE_MAP = {

    'hips': 'hips', 'hip': 'hips', 'pelvis': 'hips', 'root': 'hips', 'center': 'hips', 'bip001_pelvis': 'hips',

    'spine': 'spine', 'abdomen': 'spine', 'waist': 'spine', 'lowerback': 'spine', 'bip001_spine': 'spine',

    'chest': 'chest', 'spine1': 'chest', 'thorax': 'chest', 'bip001_spine1': 'chest',

    'upperchest': 'upperChest', 'spine2': 'upperChest', 'chest2': 'upperChest', 'bip001_spine2': 'upperChest',

    'neck': 'neck', 'neck1': 'neck', 'bip001_neck': 'neck',

    'head': 'head', 'bip001_head': 'head',

    'leftshoulder': 'leftShoulder', 'lcollar': 'leftShoulder', 'shoulder_l': 'leftShoulder', 'l_shoulder': 'leftShoulder', 'bip001_l_clavicle': 'leftShoulder',

    'leftupperarm': 'leftUpperArm', 'leftarm': 'leftUpperArm', 'lshldr': 'leftUpperArm', 'upperarm_l': 'leftUpperArm', 'l_upperarm': 'leftUpperArm', 'bip001_l_upperarm': 'leftUpperArm',

    'leftlowerarm': 'leftLowerArm', 'leftforearm': 'leftLowerArm', 'lforearm': 'leftLowerArm', 'lowerarm_l': 'leftLowerArm', 'l_forearm': 'leftLowerArm', 'bip001_l_forearm': 'leftLowerArm',

    'lefthand': 'leftHand', 'lhand': 'leftHand', 'hand_l': 'leftHand', 'l_hand': 'leftHand', 'bip001_l_hand': 'leftHand',

    'rightshoulder': 'rightShoulder', 'rcollar': 'rightShoulder', 'shoulder_r': 'rightShoulder', 'r_shoulder': 'rightShoulder', 'bip001_r_clavicle': 'rightShoulder',

    'rightupperarm': 'rightUpperArm', 'rightarm': 'rightUpperArm', 'rshldr': 'rightUpperArm', 'upperarm_r': 'rightUpperArm', 'r_upperarm': 'rightUpperArm', 'bip001_r_upperarm': 'rightUpperArm',

    'rightlowerarm': 'rightLowerArm', 'rightforearm': 'rightLowerArm', 'rforearm': 'rightLowerArm', 'lowerarm_r': 'rightLowerArm', 'r_forearm': 'rightLowerArm', 'bip001_r_forearm': 'rightLowerArm',

    'righthand': 'rightHand', 'rhand': 'rightHand', 'hand_r': 'rightHand', 'r_hand': 'rightHand', 'bip001_r_hand': 'rightHand',

    'leftupperleg': 'leftUpperLeg', 'leftupleg': 'leftUpperLeg', 'lthigh': 'leftUpperLeg', 'thigh_l': 'leftUpperLeg', 'l_thigh': 'leftUpperLeg', 'bip001_l_thigh': 'leftUpperLeg',

    'leftlowerleg': 'leftLowerLeg', 'leftleg': 'leftLowerLeg', 'lshin': 'leftLowerLeg', 'lcalf': 'leftLowerLeg', 'calf_l': 'leftLowerLeg', 'l_calf': 'leftLowerLeg', 'bip001_l_calf': 'leftLowerLeg',

    'leftfoot': 'leftFoot', 'lfoot': 'leftFoot', 'foot_l': 'leftFoot', 'l_foot': 'leftFoot', 'bip001_l_foot': 'leftFoot',

    'lefttoes': 'leftToes', 'lefttoebase': 'leftToes', 'ltoe': 'leftToes', 'bip001_l_toe0': 'leftToes',

    'rightupperleg': 'rightUpperLeg', 'rightupleg': 'rightUpperLeg', 'rthigh': 'rightUpperLeg', 'thigh_r': 'rightUpperLeg', 'r_thigh': 'rightUpperLeg', 'bip001_r_thigh': 'rightUpperLeg',

    'rightlowerleg': 'rightLowerLeg', 'rightleg': 'rightLowerLeg', 'rshin': 'rightLowerLeg', 'rcalf': 'rightLowerLeg', 'calf_r': 'rightLowerLeg', 'r_calf': 'rightLowerLeg', 'bip001_r_calf': 'rightLowerLeg',

    'rightfoot': 'rightFoot', 'rfoot': 'rightFoot', 'foot_r': 'rightFoot', 'r_foot': 'rightFoot', 'bip001_r_foot': 'rightFoot',

    'righttoes': 'rightToes', 'righttoebase': 'rightToes', 'rtoe': 'rightToes', 'bip001_r_toe0': 'rightToes'

  };



  let inEndSite = false;

  while (idx < lines.length && lines[idx] !== 'MOTION') {

    const line = lines[idx++];

    const parts = line.split(/\s+/);

    const kw = parts[0].toUpperCase();

    if (kw === 'ROOT' || kw === 'JOINT') {

      const rawName = parts.slice(1).join('_').replace(/^mixamorig:?/i, '');

      const cleanKey = rawName.toLowerCase().replace(/[^a-z0-9_]/g, '');

      const hName = BVH_BONE_MAP[cleanKey] || BVH_BONE_MAP[cleanKey.replace(/_/g, '')] || null;

      const jObj = { name: rawName, hName: hName, channels: [], parent: stack.length > 0 ? stack[stack.length - 1] : null };

      joints.push(jObj);

      stack.push(jObj);

    } else if (kw === 'END') {

      inEndSite = true;

    } else if (kw === '}') {

      if (inEndSite) inEndSite = false;

      else stack.pop();

    } else if (kw === 'CHANNELS' && !inEndSite && stack.length > 0) {

      const count = parseInt(parts[1], 10) || 0;

      stack[stack.length - 1].channels = parts.slice(2, 2 + count);

    }

  }



  if (idx >= lines.length || lines[idx] !== 'MOTION') return null;

  idx++;



  let numFrames = 0;

  let frameTime = 0.033333;

  while (idx < lines.length) {

    const line = lines[idx];

    if (/^Frames:/i.test(line)) {

      numFrames = parseInt(line.split(':')[1].trim(), 10) || 0;

      idx++;

    } else if (/^Frame Time:/i.test(line)) {

      frameTime = parseFloat(line.split(':')[1].trim()) || 0.033333;

      idx++;

      break;

    } else {

      idx++;

    }

  }

  if (numFrames <= 0) return null;



  const times = new Float32Array(numFrames);

  for (let f = 0; f < numFrames; f++) times[f] = f * frameTime;



  const trackQuats = {};

  joints.forEach((j) => {

    if (j.hName && vrmHumanoidMap[j.hName]) {

      trackQuats[j.hName] = new Float32Array(numFrames * 4);

    }

  });



  const deg2rad = Math.PI / 180.0;

  const qStep = new THREE.Quaternion();

  const qFrame = new THREE.Quaternion();

  const qVrm0 = new THREE.Quaternion();

  const qTarget = new THREE.Quaternion();

  const axX = new THREE.Vector3(1, 0, 0);

  const axY = new THREE.Vector3(0, 1, 0);

  const axZ = new THREE.Vector3(0, 0, 1);



  let fCount = 0;

  while (idx < lines.length && fCount < numFrames) {

    const vals = lines[idx++].split(/\s+/).map(Number);

    let cPtr = 0;

    for (let jIdx = 0; jIdx < joints.length; jIdx++) {

      const j = joints[jIdx];

      qFrame.identity();

      for (let c = 0; c < j.channels.length; c++) {

        const ch = j.channels[c].toLowerCase();

        const v = vals[cPtr++] || 0;

        if (ch === 'xrotation') {

          qStep.setFromAxisAngle(axX, v * deg2rad);

          qFrame.multiply(qStep);

        } else if (ch === 'yrotation') {

          qStep.setFromAxisAngle(axY, v * deg2rad);

          qFrame.multiply(qStep);

        } else if (ch === 'zrotation') {

          qStep.setFromAxisAngle(axZ, v * deg2rad);

          qFrame.multiply(qStep);

        }

      }

      if (j.hName && trackQuats[j.hName]) {

        const dstBone = vrmHumanoidMap[j.hName];

        const dstRestQuat = (dstBone.userData && dstBone.userData.restQuat) ? dstBone.userData.restQuat : new THREE.Quaternion();

        qVrm0.set(-qFrame.x, qFrame.y, -qFrame.z, qFrame.w);

        qTarget.copy(dstRestQuat).multiply(qVrm0);

        const out = trackQuats[j.hName];

        const base = fCount * 4;

        out[base]     = qTarget.x;

        out[base + 1] = qTarget.y;

        out[base + 2] = qTarget.z;

        out[base + 3] = qTarget.w;

      }

    }

    fCount++;

  }



  const retargetedTracks = [];

  Object.keys(trackQuats).forEach((hName) => {

    const dstBone = vrmHumanoidMap[hName];

    if (dstBone) {

      retargetedTracks.push(new THREE.QuaternionKeyframeTrack(

        `${dstBone.uuid}.quaternion`,

        times,

        trackQuats[hName]

      ));

    }

  });



  return new THREE.AnimationClip(actionKey, numFrames * frameTime, retargetedTracks);

}



function buildRetargetedVrmaClip(actionKey, vrmaGltf) {

  const parserJson = vrmaGltf.parser && vrmaGltf.parser.json;

  const ext = parserJson && parserJson.extensions && parserJson.extensions.VRMC_vrm_animation;

  const humanBones = ext && ext.humanoid && ext.humanoid.humanBones;

  const srcClip = vrmaGltf.animations && vrmaGltf.animations[0];

  if (!humanBones || !srcClip) return null;



  vrmaGltf.scene.updateMatrixWorld(true);



  const nodeNameToHumanoid = {};

  const vrmaNodeRestWorld = {};

  const vrmaParentRestWorld = {};

  const vrmaHipsRestPos = new THREE.Vector3();



  const vrmaNodeByName = {};

  vrmaGltf.scene.traverse((obj) => {

    if (obj.name) {

      vrmaNodeByName[obj.name] = obj;

      vrmaNodeByName[obj.name.replace(/_/g, ' ')] = obj;

    }

  });



  Object.keys(humanBones).forEach((hName) => {

    const nodeIdx = humanBones[hName].node;

    const nodeDef = parserJson.nodes && parserJson.nodes[nodeIdx];

    if (!nodeDef || !nodeDef.name) return;

    const nName = nodeDef.name;

    const nNameSan = nName.replace(/\s+/g, '_');

    nodeNameToHumanoid[nName] = hName;

    nodeNameToHumanoid[nNameSan] = hName;



    const vrmaObj = vrmaNodeByName[nName];

    if (vrmaObj) {

      const qw = new THREE.Quaternion();

      vrmaObj.getWorldQuaternion(qw);

      vrmaNodeRestWorld[nName] = qw;

      vrmaNodeRestWorld[nNameSan] = qw;



      const qp = new THREE.Quaternion();

      if (vrmaObj.parent) vrmaObj.parent.getWorldQuaternion(qp);

      vrmaParentRestWorld[nName] = qp;

      vrmaParentRestWorld[nNameSan] = qp;



      if (hName === 'hips') {

        vrmaHipsRestPos.copy(vrmaObj.position);

      }

    }

  });



  const retargetedTracks = [];

  const qRaw = new THREE.Quaternion();

  const qNorm = new THREE.Quaternion();

  const qVrm0 = new THREE.Quaternion();

  const qTarget = new THREE.Quaternion();



  for (let i = 0; i < srcClip.tracks.length; i++) {

    const track = srcClip.tracks[i];

    const dotIdx = track.name.lastIndexOf('.');

    if (dotIdx < 0) continue;

    const srcNodeName = track.name.substring(0, dotIdx);

    const propName = track.name.substring(dotIdx + 1);



    const hName = nodeNameToHumanoid[srcNodeName];

    if (!hName) continue;

    const dstBone = vrmHumanoidMap[hName];

    if (!dstBone) continue;



    if (propName === 'quaternion') {

      const qParentWorld = vrmaParentRestWorld[srcNodeName] || new THREE.Quaternion();

      const qNodeWorldInv = (vrmaNodeRestWorld[srcNodeName] || new THREE.Quaternion()).clone().invert();

      const dstRestQuat = (dstBone.userData && dstBone.userData.restQuat) ? dstBone.userData.restQuat : new THREE.Quaternion();



      const srcVals = track.values;

      const dstVals = new Float32Array(srcVals.length);



      for (let k = 0; k < srcVals.length; k += 4) {

        qRaw.set(srcVals[k], srcVals[k + 1], srcVals[k + 2], srcVals[k + 3]);

        qNorm.copy(qParentWorld).multiply(qRaw).multiply(qNodeWorldInv);

        qVrm0.set(-qNorm.x, qNorm.y, -qNorm.z, qNorm.w);

        qTarget.copy(dstRestQuat).multiply(qVrm0);



        dstVals[k]     = qTarget.x;

        dstVals[k + 1] = qTarget.y;

        dstVals[k + 2] = qTarget.z;

        dstVals[k + 3] = qTarget.w;

      }



      let tArr = track.times.slice();

      let vArr = dstVals;

      // Expand 1-frame static pose VRMAs (e.g. pose_lean_in.vrma) to 4.0s so AnimationMixer holds & crossfades smoothly

      if (tArr.length === 1) {

        tArr = new Float32Array([0.0, 4.0]);

        vArr = new Float32Array(dstVals.length * 2);

        vArr.set(dstVals, 0);

        vArr.set(dstVals, dstVals.length);

      }



      retargetedTracks.push(new THREE.QuaternionKeyframeTrack(

        `${dstBone.uuid}.quaternion`,

        tArr,

        vArr

      ));

    } else if (propName === 'position' && hName === 'hips' && track.values.length >= 3) {

      // Keep character anchored horizontally in center of stage and prevent floating upward

      const dstRestPos = (dstBone.userData && dstBone.userData.restPos) ? dstBone.userData.restPos : new THREE.Vector3();

      const srcVals = track.values;

      const dstVals = new Float32Array(srcVals.length);

      const baseY0 = srcVals[1];



      for (let k = 0; k < srcVals.length; k += 3) {

        const dy = Math.min(0.01, srcVals[k + 1] - baseY0); // allow crouch/squat down, prevent upward floating

        dstVals[k]     = dstRestPos.x;

        dstVals[k + 1] = dstRestPos.y + dy;

        dstVals[k + 2] = dstRestPos.z;

      }



      let tArr = track.times.slice();

      let vArr = dstVals;

      if (tArr.length === 1) {

        tArr = new Float32Array([0.0, 4.0]);

        vArr = new Float32Array(dstVals.length * 2);

        vArr.set(dstVals, 0);

        vArr.set(dstVals, dstVals.length);

      }



      retargetedTracks.push(new THREE.VectorKeyframeTrack(

        `${dstBone.uuid}.position`,

        tArr,

        vArr

      ));

    }

  }



  const finalDur = srcClip.duration < 0.05 ? 4.0 : srcClip.duration;

  return new THREE.AnimationClip(actionKey, finalDur, retargetedTracks);

}



function initVrmEngine() {

  if (vrmInitialized) return;

  const container = document.getElementById('vrmStageContainer');

  const canvas = document.getElementById('vrmCanvas');

  if (!container || !canvas || typeof THREE === 'undefined') {

    console.warn("[VRM] Waiting for Three.js / VRM container...");

    return;

  }



  const width = container.clientWidth || 360;

  const height = container.clientHeight || 460;



  vrmScene = new THREE.Scene();

  vrmClock = new THREE.Clock();



  vrmCamera = new THREE.PerspectiveCamera(32, width / height, 0.1, 60.0);

  currentLookAt = new THREE.Vector3(0, vrmBaseY + 0.68, 0);

  targetLookAt = new THREE.Vector3(0, vrmBaseY + 0.68, 0);

  targetCamPos = new THREE.Vector3(0.80, vrmBaseY + 0.82, 4.05);

  vrmCamera.position.copy(targetCamPos);

  vrmCamera.lookAt(currentLookAt);



  try {

    vrmRenderer = new THREE.WebGLRenderer({

      canvas: canvas,

      alpha: true,

      antialias: true,

      powerPreference: 'high-performance'

    });

    vrmRenderer.setSize(width, height);

    vrmRenderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));

    vrmRenderer.outputEncoding = THREE.sRGBEncoding;

  } catch (err) {

    console.error("[VRM] WebGLRenderer init failed:", err);

    return;

  }



  const ambientLight = new THREE.AmbientLight(0xfff0ff, 0.90);

  vrmScene.add(ambientLight);



  const keyLight = new THREE.DirectionalLight(0xffffff, 0.68);

  keyLight.position.set(1.2, 2.4, 2.6);

  vrmScene.add(keyLight);



  const rimLight = new THREE.DirectionalLight(0xc084fc, 0.45);

  rimLight.position.set(-1.5, 1.5, -2.0);

  vrmScene.add(rimLight);



  vrmInitialized = true;

  initFloatingHudDraggable();

  initAvatarPokeRaycaster(canvas);

  vrmEnvironmentGroup = new THREE.Group();
  vrmScene.add(vrmEnvironmentGroup);

  loadRumVrmModel(currentVrmModelName);

  setVrmEnvironment(currentEnvironmentName);

  loadYoshiPlushProp();

  initSolarEphemerisEngine();



  function animateVrm() {

    requestAnimationFrame(animateVrm);



    const delta = vrmClock ? Math.min(vrmClock.getDelta(), 0.1) : 0.016;

    const time = vrmClock ? vrmClock.getElapsedTime() : Date.now() * 0.001;

    const now = Date.now();



    // 1. Natural Eye Blinking Sweep (240ms smooth blink with 55ms closed hold + occasional double-blink)

    if (!vrmIsBlinking && now > vrmNextBlinkTime) {

      vrmIsBlinking = true;

      vrmBlinkStartTime = now;

    }

    if (vrmIsBlinking) {

      const bdt = now - vrmBlinkStartTime;

      if (bdt < 85) {

        vrmBlinkProgress = bdt / 85;

      } else if (bdt < 140) {

        vrmBlinkProgress = 1.0;

      } else if (bdt < 240) {

        vrmBlinkProgress = 1.0 - ((bdt - 140) / 100);

      } else {

        vrmBlinkProgress = 0.0;

        vrmIsBlinking = false;

        vrmNextBlinkTime = (Math.random() < 0.28) ? (now + 180) : (now + 2200 + Math.random() * 1600);

      }

    }



    // 2. Speech & Action State (Synced strictly to hardware audio playback when SSE is connected!)

    const isSpeaking = (isHardwareSpeaking || now < vrmSpeechEndTime || now < (typeof waifuSpeechEndTime !== 'undefined' ? waifuSpeechEndTime : 0));

    const isReacting = (now < vrmReactionEndTime);

    const isSpeedPanic = (now < vrmSpeedPanicEndTime);

    const dancing = (isMusicPlaying() && !isSpeaking && !vrmHasError && !isSpeedPanic);



    // 3. Smooth G-Force Inertia Interpolation (NO vertical floating!)

    rumCurrentInertiaZ += (rumTargetInertiaZ - rumCurrentInertiaZ) * (delta * 6.0);



    if (vrmModel) {

      const isActionActive = (now < vrmActionEndTime);

      // Autonomous Roaming State Update
      updateAutonomousRoaming(delta, isSpeaking, isReacting, isActionActive, dancing, isSpeedPanic);

      // Environment surface elevation (e.g. stepping onto raised tatami mat in Garden)
      const targetElevation = getEnvironmentSurfaceElevation(vrmRoamCurrentPos.x, vrmRoamCurrentPos.z);
      vrmCurrentElevation += (targetElevation - vrmCurrentElevation) * Math.min(1.0, delta * 7.0);

      // Anchor feet firmly on stage floor (vrmBaseY + elevation), apply autonomous roaming X/Z & G-force inertia
      vrmModel.rotation.set(0, vrmRoamCurrentRotY, 0);

      vrmModel.position.set(
        -vrmCenter.x + vrmRoamCurrentPos.x,
        vrmBaseY + vrmCurrentElevation,
        (-vrmCenter.z) + vrmRoamCurrentPos.z + rumCurrentInertiaZ
      );

      if (!isActionActive && vrmaActiveAction && vrmaActiveName !== 'walk_loop') {

        stopActiveVrmaClip(0.45);

      }



      // Auto-trigger real dance BVH clip when music is playing

      if (dancing && !isActionActive && vrmaClips['dance'] && vrmaActiveName !== 'dance') {

        playVrmAction('dance', 8000, true);

      }



      // Update AnimationMixer (drives active VRMA/BVH clips, neutral_idle.bvh standby AND roaming walk!)

      if (vrmMixer && (vrmaActiveAction || vrmaIdleAction || vrmRoamWalkAction)) {

        vrmMixer.update(delta);

        // Prevent unnatural owl-like head spinning! Strictly clamp head & neck rotation to natural human anatomy

        if (vrmBones.head) {

          vrmBones.head.rotation.y = THREE.MathUtils.clamp(vrmBones.head.rotation.y, -0.55, 0.55);

          vrmBones.head.rotation.x = THREE.MathUtils.clamp(vrmBones.head.rotation.x, -0.45, 0.45);

          vrmBones.head.rotation.z = THREE.MathUtils.clamp(vrmBones.head.rotation.z, -0.35, 0.35);

        }

        if (vrmBones.neck) {

          vrmBones.neck.rotation.y = THREE.MathUtils.clamp(vrmBones.neck.rotation.y, -0.35, 0.35);

        }

      } else {

        // Fallback only during the ~0.3s before neutral_idle.bvh finishes loading

        resetAllVrmBonesToRest();

        if (vrmBones.lArm) vrmBones.lArm.rotation.set(0, 0.10, 1.30);

        if (vrmBones.rArm) vrmBones.rArm.rotation.set(0, -0.10, -1.30);

      }



      // 4a. Facial Rig Animation: Reset facial bones to rest first, then apply Eye Blinking & Lip-Sync

      ['lEyeUpper', 'rEyeUpper', 'lEyeLower', 'rEyeLower', 'lEyeball', 'rEyeball',

       'jaw', 'lLipLower', 'rLipLower', 'lLipUpper', 'rLipUpper', 'lMouthCorner', 'rMouthCorner',

       'lBrowIn', 'rBrowIn', 'lBrowOut', 'rBrowOut'].forEach((fk) => {

        const fb = vrmBones[fk];

        if (fb && fb.userData) {

          if (fb.userData.restPos) fb.position.copy(fb.userData.restPos);

          if (fb.userData.restQuat) fb.quaternion.copy(fb.userData.restQuat);

          fb.scale.set(1, 1, 1);

        }

      });



      const blinkAmt = (vrmCurrentAction === 'amusement' || vrmCurrentAction === 'point_laugh') ? Math.max(vrmBlinkProgress, 0.85) : vrmBlinkProgress;

      if (blinkAmt > 0.01) {

        if (vrmBones.lEyeUpper && vrmBones.lEyeUpper.userData.restPos) {

          vrmBones.lEyeUpper.position.y = vrmBones.lEyeUpper.userData.restPos.y - 0.025 * blinkAmt;

          vrmBones.lEyeUpper.rotation.x = -0.12 * blinkAmt;

        }

        if (vrmBones.rEyeUpper && vrmBones.rEyeUpper.userData.restPos) {

          vrmBones.rEyeUpper.position.y = vrmBones.rEyeUpper.userData.restPos.y - 0.025 * blinkAmt;

          vrmBones.rEyeUpper.rotation.x = -0.12 * blinkAmt;

        }

        if (vrmBones.lEyeLower && vrmBones.lEyeLower.userData.restPos) {

          vrmBones.lEyeLower.position.y = vrmBones.lEyeLower.userData.restPos.y + 0.006 * blinkAmt;

        }

        if (vrmBones.rEyeLower && vrmBones.rEyeLower.userData.restPos) {

          vrmBones.rEyeLower.position.y = vrmBones.rEyeLower.userData.restPos.y + 0.006 * blinkAmt;

        }

        if (vrmBones.lEyeball && vrmBones.lEyeball.userData.restPos) {

          vrmBones.lEyeball.scale.set(1.0, Math.max(0.05, 1.0 - 0.95 * blinkAmt), 1.0);

          vrmBones.lEyeball.position.z = vrmBones.lEyeball.userData.restPos.z + 0.010 * blinkAmt;

        }

        if (vrmBones.rEyeball && vrmBones.rEyeball.userData.restPos) {

          vrmBones.rEyeball.scale.set(1.0, Math.max(0.05, 1.0 - 0.95 * blinkAmt), 1.0);

          vrmBones.rEyeball.position.z = vrmBones.rEyeball.userData.restPos.z + 0.010 * blinkAmt;

        }

      }



      if (isSpeaking || vrmCurrentAction === 'amusement' || vrmCurrentAction === 'point_laugh') {

        const syl1 = Math.sin(time * 18.5);

        const syl2 = Math.sin(time * 11.3 + 0.8);

        const syl3 = Math.cos(time * 27.0);

        const rawOpen = Math.max(0.0, (syl1 * 0.55 + syl2 * 0.35 + syl3 * 0.25 + 0.35));

        const mouthOpen = Math.min(1.0, rawOpen);

        const vowelWidth = 0.5 + 0.5 * Math.sin(time * 7.2);



        if (vrmBones.jaw && vrmBones.jaw.userData.restPos) {

          vrmBones.jaw.position.y = vrmBones.jaw.userData.restPos.y - (0.0045 * mouthOpen);

          vrmBones.jaw.rotation.x = -0.05 * mouthOpen;

        }

        if (vrmBones.lLipLower && vrmBones.lLipLower.userData.restPos) {

          vrmBones.lLipLower.position.y = vrmBones.lLipLower.userData.restPos.y - (0.0055 * mouthOpen);

        }

        if (vrmBones.rLipLower && vrmBones.rLipLower.userData.restPos) {

          vrmBones.rLipLower.position.y = vrmBones.rLipLower.userData.restPos.y - (0.0055 * mouthOpen);

        }

        if (vrmBones.lLipUpper && vrmBones.lLipUpper.userData.restPos) {

          vrmBones.lLipUpper.position.y = vrmBones.lLipUpper.userData.restPos.y + (0.0025 * mouthOpen);

        }

        if (vrmBones.rLipUpper && vrmBones.rLipUpper.userData.restPos) {

          vrmBones.rLipUpper.position.y = vrmBones.rLipUpper.userData.restPos.y + (0.0025 * mouthOpen);

        }

        if (vrmBones.lMouthCorner && vrmBones.lMouthCorner.userData.restPos) {

          vrmBones.lMouthCorner.position.y = vrmBones.lMouthCorner.userData.restPos.y + (0.003 * vowelWidth);

          vrmBones.lMouthCorner.position.x = vrmBones.lMouthCorner.userData.restPos.x * (1.0 + 0.14 * vowelWidth);

        }

        if (vrmBones.rMouthCorner && vrmBones.rMouthCorner.userData.restPos) {

          vrmBones.rMouthCorner.position.y = vrmBones.rMouthCorner.userData.restPos.y + (0.003 * vowelWidth);

          vrmBones.rMouthCorner.position.x = vrmBones.rMouthCorner.userData.restPos.x * (1.0 + 0.14 * vowelWidth);

        }

        const browLift = 0.003 * mouthOpen;

        ['lBrowIn', 'rBrowIn', 'lBrowOut', 'rBrowOut'].forEach((bk) => {

          if (vrmBones[bk] && vrmBones[bk].userData.restPos) {

            vrmBones[bk].position.y = vrmBones[bk].userData.restPos.y + browLift;

          }

        });

      }

    }



    // 4b. World-Space Gravity Drape for Hanging Kimono Sleeves (Bone001_m & Bone001)

    if (vrmModel) {

      vrmModel.updateMatrixWorld(true);

      const sleeveTargetWorldQ = new THREE.Quaternion().setFromEuler(

        new THREE.Euler(0.45 + Math.sin(time * 2.2) * 0.02, Math.PI, Math.cos(time * 1.8) * 0.02)

      );

      ['Bone001_m', 'Bone001'].forEach((sName) => {

        const sb = vrmModel.getObjectByName(sName);

        if (sb && sb.parent) {

          const pWorldQ = new THREE.Quaternion();

          sb.parent.getWorldQuaternion(pWorldQ);

          sb.quaternion.copy(pWorldQ.invert().multiply(sleeveTargetWorldQ));

        }

      });

    }



    // 5. Dynamic Camera Director

    updateCameraDirector(delta, isSpeaking, isReacting);



    // 5b. Animated Sakura Blossom Petals in Garden Environment
    if (currentEnvironmentName === 'GARDEN' && sakuraPetals && sakuraPetals.length > 0) {
      for (let i = 0; i < sakuraPetals.length; i++) {
        const p = sakuraPetals[i];
        p.position.y -= delta * p.userData.fallSpeed;
        p.position.x += Math.sin(time * 1.5 + p.userData.seed) * (delta * 0.15);
        p.position.z += Math.cos(time * 1.2 + p.userData.seed) * (delta * 0.12);
        p.rotation.z += delta * p.userData.rotSpeed;
        p.rotation.x += delta * (p.userData.rotSpeed * 0.8);
        if (p.position.y < vrmBaseY) {
          p.position.y = vrmBaseY + 3.2;
          p.position.x = (Math.random() - 0.5) * 3.5;
          p.position.z = (Math.random() - 0.5) * 2.5;
        }
      }
    }

    // 5c. Real Moving Ocean Waves & Celestial Day/Night Arc Simulation
    if (currentEnvironmentName === 'GARDEN') {
      updateGardenOceanAndSky(time, delta);
    }

    // 6. Render

    if (vrmRenderer && vrmScene && vrmCamera) {

      vrmRenderer.render(vrmScene, vrmCamera);

    }

  }



  animateVrm();

}



function updateCameraDirector(delta, isSpeaking, isReacting) {

  if (!vrmCamera || !targetCamPos || !targetLookAt || !currentLookAt) return;



  // Head Y in stage coordinates (feet anchored at -0.68, head near -0.68 + vrmSize.y * 0.85)

  const headY = vrmBaseY + (vrmSize.y * 0.82);

  const fullBodyDist = isCompanionFloating ? 2.85 : 3.12;

  const portraitDist = isCompanionFloating ? 1.05 : 1.15;



  const isDoingAction = (Date.now() < vrmActionEndTime);

  if (isCompanionFloating) {

    // Shotgun HUD: close-up on Rum's expressive face

    targetCamPos.set(0.65, headY + 0.05, 1.35);

    targetLookAt.set(0.0, headY, 0.0);

  } else if (vrmFramingMode === 'ROOM') {

    // Room View: wide diorama view of Rum, Yoshi plush, table, plant, and sunlit window

    targetCamPos.set(2.5, vrmBaseY + 1.50, 3.80 * vrmZoomMultiplier);

    targetLookAt.set(0.1, vrmBaseY + 0.60, -0.1);

  } else if (!isDoingAction && (vrmFramingMode === 'PORTRAIT' || (vrmFramingMode === 'AUTO' && (isSpeaking || isReacting)))) {

    // Portrait / Speaking Zoom: close-up on Rum's face and upper body

    targetCamPos.set(0.70, headY + 0.05, 1.65 * vrmZoomMultiplier);

    targetLookAt.set(0.0, headY, 0.0);

  } else {

    // Full Body: Zoomed out so entire body (hair to shoes) is completely in view without any part cut off

    targetCamPos.set(0.80, vrmBaseY + 0.82, 4.05 * vrmZoomMultiplier);

    // Smoothly track Rem's horizontal wandering position and elevation on the stage
    targetLookAt.set(vrmRoamCurrentPos.x * 0.40, vrmBaseY + vrmCurrentElevation + 0.68, vrmRoamCurrentPos.z * 0.40);

  }



  const lerpFactor = Math.min(1.0, delta * 4.2);

  vrmCamera.position.lerp(targetCamPos, lerpFactor);

  currentLookAt.lerp(targetLookAt, lerpFactor);

  vrmCamera.lookAt(currentLookAt);

}



function loadRumVrmModel(modelName = (currentVrmModelName || 'Rem.vrm')) {

  currentVrmModelName = modelName;
  localStorage.setItem('vrmCurrentAvatar', modelName);

  const notice = document.getElementById('vrmLoadingNotice');

  if (notice) notice.style.display = 'flex';



  const loader = new THREE.GLTFLoader();

  const vrmUrl = `/api/models/vrm?name=${encodeURIComponent(modelName)}`;



  loader.load(

    vrmUrl,

    (gltf) => {

      console.log(`[VRM] ${modelName} loaded successfully!`, gltf);

      if (notice) notice.style.display = 'none';



      if (vrmModel) {

        vrmScene.remove(vrmModel);

      }



      vrmModel = gltf.scene;

      vrmaIdleAction = null;

      vrmaActiveAction = null;



      // Fix 3ds Max Biped hierarchy & map bones

      const rig = fixVrmBipedHierarchy(vrmModel, gltf);

      vrmBones = rig.bones;

      vrmHumanoidMap = rig.hMap;

      vrmAllBones = rig.allBones;

      vrmSecondaryBones = rig.secondary;



      // Measure raw unscaled height so child models (Rum.vrm) are scaled slightly smaller (0.85x)

      // while taller adult models scale proportionally and fit cleanly on the same stage floor

      const rawBox = new THREE.Box3().setFromObject(vrmModel);

      const rawSize = rawBox.getSize(new THREE.Vector3());

      const isPetiteModel = /rum|rem/i.test(modelName) || rawSize.y < 1.56;

      // Beautiful proportion: scale Rum up to 1.18x so she fills the frame nicely with the room

      const targetScale = isPetiteModel ? 1.18 : Math.min(1.25, 1.42 / Math.max(1.0, rawSize.y));

      vrmModel.scale.set(targetScale, targetScale, targetScale);

      vrmModel.updateMatrixWorld(true);



      const box = new THREE.Box3().setFromObject(vrmModel);

      const center = box.getCenter(new THREE.Vector3());

      const size = box.getSize(new THREE.Vector3());



      vrmCenter = center;

      vrmSize = size;

      // Anchor feet (box.min.y) firmly at stage floor (-0.68) so she never floats and leaves headroom for taller VRMs

      vrmBaseY = -0.68 - box.min.y;



      vrmModel.position.set(-center.x, vrmBaseY, -center.z);

      vrmModel.rotation.set(0, Math.PI, 0);



      vrmModel.traverse((node) => {

        if (node.isMesh) {

          node.castShadow = true;

          node.receiveShadow = true;

          node.frustumCulled = false;

          if (node.material) {

            node.material.depthWrite = true;

          }

        }

      });



      vrmScene.add(vrmModel);

      vrmMixer = new THREE.AnimationMixer(vrmModel);

      vrmRoamWalkAction = null;

      preloadVrmaMotionPack();



      updateFramingButtonLabel();

      updateWorldButtonLabel();

      updateRoamButtonLabel();

      updateModelButtonLabel();

      resizeVrmToStage();



      const emotionPill = document.getElementById('waifuEmotionPill');

      if (emotionPill) {

        const isRem = (currentVrmModelName.includes('Rem') || currentVrmModelName.toLowerCase().includes('rem'));
        emotionPill.innerText = isRem ? "💙 REM (3D VRM) • DEVOTED TO MASTER" : "💜 RUM (3D VRM) • PLAYFUL SISTER";

      }

    },

    (progress) => {

      if (progress.total > 0 && notice) {

        const pct = Math.round((progress.loaded / progress.total) * 100);

        notice.innerHTML = `<span>⚡</span> LOADING RUM VRM (${pct}%)...`;

      }

    },

    (error) => {

      console.warn(`[VRM] Fallback checking Rem.vrm:`, error);

      if (modelName === 'Rem.vrm') {

        loadRumVrmModel('Rum.vrm');

        return;

      } else if (modelName === 'Rum.vrm') {

        loadRumVrmModel('Rem.vrm');

        return;

      }

      if (notice) {

        notice.innerHTML = '<span style="color:var(--accent-red);">VRM Load Error</span>';

      }

    }

  );

}



function resizeVrmToStage() {

  if (!vrmRenderer || !vrmCamera) return;

  const targetContainer = isCompanionFloating ? document.getElementById('vrmFloatingBody') : document.getElementById('vrmStageContainer');

  if (!targetContainer) return;

  const w = targetContainer.clientWidth || 360;

  const h = targetContainer.clientHeight || 460;

  vrmRenderer.setSize(w, h);

  vrmCamera.aspect = w / h;

  vrmCamera.updateProjectionMatrix();

}



function updateFramingButtonLabel() {

  const btn = document.getElementById('btnVrmViewToggle');

  const hudBtn = document.getElementById('btnHudViewToggle');

  const labels = {

    'FULL_BODY': '🔍 FULL BODY',

    'ROOM': '🏠 ROOM VIEW',

    'AUTO': '🤖 AUTO ZOOM',

    'PORTRAIT': '👤 PORTRAIT'

  };

  const label = labels[vrmFramingMode] || '🔍 FULL BODY';

  if (btn) btn.innerText = label;

  if (hudBtn) hudBtn.innerText = (vrmFramingMode === 'ROOM') ? '🏠' : ((vrmFramingMode === 'PORTRAIT') ? '👤' : '🔍');

}



function toggleVrmFraming() {

  if (vrmFramingMode === 'FULL_BODY') vrmFramingMode = 'ROOM';

  else if (vrmFramingMode === 'ROOM') vrmFramingMode = 'PORTRAIT';

  else if (vrmFramingMode === 'PORTRAIT') vrmFramingMode = 'AUTO';

  else vrmFramingMode = 'FULL_BODY';

  updateFramingButtonLabel();

}



function triggerVrmReaction() {

  if (vrmaClips['greeting']) {

    playVrmAction('greeting', 3800, true);

  } else {

    vrmReactionEndTime = Date.now() + 3500;

  }

}



function setVrmSpeaking(durationMs, text, forceTimer = false) {

  if (forceTimer || !eventSource || eventSource.readyState !== 1) {

    vrmSpeechEndTime = Date.now() + (durationMs || 3000);

  }

  if (text) {

    const bubble = document.getElementById('vrmHudBubble');

    const hud = document.getElementById('vrmFloatingHud');

    if (bubble) {

      bubble.innerText = text;

      bubble.classList.add('show');

      if (hud) hud.classList.add('talking');

      setTimeout(() => {

        bubble.classList.remove('show');

        if (hud) hud.classList.remove('talking');

      }, durationMs || 3000);

    }

  }

}



function showVrmSpeech(text, durationMs = 5000) {

  setVrmSpeaking(durationMs, text);

}



// Floating Shotgun Companion Mode (Rum Riding Shotgun Anywhere on Screen)

function popOutFloatingCompanion(isAuto = false) {

  const canvas = document.getElementById('vrmCanvas');

  const floatingBody = document.getElementById('vrmFloatingBody');

  const floatingHud = document.getElementById('vrmFloatingHud');

  if (!canvas || !floatingBody || !floatingHud) return;



  floatingHud.style.display = 'flex';

  floatingBody.appendChild(canvas);

  isCompanionFloating = true;

  isShotgunAutoPopped = !!isAuto;



  resizeVrmToStage();

  if (!isAuto) {

    triggerVrmReaction();

    showVrmSpeech("Master! Rum is riding shotgun with you across all screens!", 4500);

  }

}



function dockCompanionToAi() {

  const canvas = document.getElementById('vrmCanvas');

  const stageContainer = document.getElementById('vrmStageContainer');

  const floatingHud = document.getElementById('vrmFloatingHud');

  if (shotgunAutoDismissTimer) {

    clearTimeout(shotgunAutoDismissTimer);

    shotgunAutoDismissTimer = null;

  }

  isShotgunAutoPopped = false;

  if (!canvas || !stageContainer || !floatingHud) return;



  floatingHud.style.display = 'none';

  stageContainer.appendChild(canvas);

  isCompanionFloating = false;



  resizeVrmToStage();

}



function dismissFloatingHud() {

  isShotgunAutoPopped = false;

  dockCompanionToAi();

}



function initFloatingHudDraggable() {

  const hud = document.getElementById('vrmFloatingHud');

  const header = document.getElementById('vrmHudHeader');

  if (!hud || !header) return;



  let isDragging = false;

  let startX = 0;

  let startY = 0;

  let initialLeft = 0;

  let initialTop = 0;



  header.addEventListener('pointerdown', (e) => {

    if (e.target.closest('button')) return;

    isDragging = true;

    startX = e.clientX;

    startY = e.clientY;

    const rect = hud.getBoundingClientRect();

    initialLeft = rect.left;

    initialTop = rect.top;

    hud.style.bottom = 'auto';

    hud.style.right = 'auto';

    hud.style.left = initialLeft + 'px';

    hud.style.top = initialTop + 'px';

    header.setPointerCapture(e.pointerId);

    e.preventDefault();

  }, { passive: false });



  window.addEventListener('pointermove', (e) => {

    if (!isDragging) return;

    const dx = e.clientX - startX;

    const dy = e.clientY - startY;

    let newLeft = Math.max(10, Math.min(window.innerWidth - hud.offsetWidth - 10, initialLeft + dx));

    let newTop = Math.max(10, Math.min(window.innerHeight - hud.offsetHeight - 10, initialTop + dy));

    hud.style.left = newLeft + 'px';

    hud.style.top = newTop + 'px';

    e.preventDefault();

  }, { passive: false });



  const stopDrag = (e) => {

    if (!isDragging) return;

    isDragging = false;

    try { header.releasePointerCapture(e.pointerId); } catch (_) {}

  };



  window.addEventListener('pointerup', stopDrag, { passive: true });

  window.addEventListener('pointercancel', stopDrag, { passive: true });

}



// [OBSOLETE 2D FACE TOGGLES - Locked to 3D_VRM so 2D face cannot be activated]

function toggleAvatar2d3d() {

  switchAvatarEngine('3D_VRM');

}



function switchAvatarEngine(mode) {

  activeAvatarEngine = '3D_VRM';

  const vrmContainer = document.getElementById('vrmStageContainer');

  const faceCanvas = document.getElementById('waifuFaceCanvas');

  const selector = document.getElementById('cfgAvatarEngine');

  const emotionPill = document.getElementById('waifuEmotionPill');



  if (selector) selector.value = '3D_VRM';

  if (vrmContainer) vrmContainer.style.display = 'flex';

  if (faceCanvas) faceCanvas.style.display = 'none';

  if (!vrmInitialized) {

    initVrmEngine();

  } else {

    resizeVrmToStage();

  }

  if (emotionPill) emotionPill.innerText = "💖 R.U.M. (3D VRM) • DEVOTED TO MASTER";

}



// Auto-initialize 3D VRM Rum on startup

window.addEventListener('load', () => {

  setTimeout(initVrmEngine, 500);

});

window.addEventListener('resize', () => {

  if (typeof resizeVrmToStage === 'function') resizeVrmToStage();

});





// ============================================================================
// --- PROCEDURAL TEXTURE GENERATORS (Zero network lag, 100% solid & seamless) ---
// ============================================================================

function createWoodPlankTexture() {
  const canvas = document.createElement('canvas');
  canvas.width = 512;
  canvas.height = 512;
  const ctx = canvas.getContext('2d');

  ctx.fillStyle = '#4a2e1b';
  ctx.fillRect(0, 0, 512, 512);

  const plankH = 64;
  for (let y = 0; y < 512; y += plankH) {
    const tint = (Math.random() - 0.5) * 18;
    ctx.fillStyle = `rgb(${74 + tint}, ${46 + tint * 0.7}, ${27 + tint * 0.5})`;
    ctx.fillRect(0, y, 512, plankH - 2);

    ctx.strokeStyle = 'rgba(30, 16, 8, 0.25)';
    ctx.lineWidth = 1;
    for (let i = 0; i < 5; i++) {
      ctx.beginPath();
      const gy = y + 8 + Math.random() * (plankH - 16);
      ctx.moveTo(0, gy);
      ctx.bezierCurveTo(128, gy + (Math.random() - 0.5) * 6, 384, gy + (Math.random() - 0.5) * 6, 512, gy);
      ctx.stroke();
    }

    ctx.strokeStyle = '#22140a';
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.moveTo(0, y + plankH - 1);
    ctx.lineTo(512, y + plankH - 1);
    ctx.stroke();

    const offset = (y / plankH) % 2 === 0 ? 0 : 256;
    ctx.beginPath();
    ctx.moveTo(offset + 180, y);
    ctx.lineTo(offset + 180, y + plankH - 2);
    ctx.stroke();
  }

  const tex = new THREE.CanvasTexture(canvas);
  tex.wrapS = THREE.RepeatWrapping;
  tex.wrapT = THREE.RepeatWrapping;
  tex.repeat.set(4, 4);
  return tex;
}

function createPlushRugTexture(baseColor = '#f6efe3', trimColor = '#9c7cb0') {
  const canvas = document.createElement('canvas');
  canvas.width = 512;
  canvas.height = 512;
  const ctx = canvas.getContext('2d');

  ctx.fillStyle = baseColor;
  ctx.fillRect(0, 0, 512, 512);

  ctx.fillStyle = 'rgba(210, 195, 175, 0.28)';
  for (let x = 0; x < 512; x += 8) {
    for (let y = 0; y < 512; y += 8) {
      if ((x + y) % 16 === 0) {
        ctx.fillRect(x, y, 4, 4);
      }
    }
  }

  ctx.strokeStyle = trimColor;
  ctx.lineWidth = 14;
  ctx.beginPath();
  ctx.arc(256, 256, 240, 0, Math.PI * 2);
  ctx.stroke();

  ctx.strokeStyle = '#f472b6';
  ctx.lineWidth = 4;
  ctx.beginPath();
  ctx.arc(256, 256, 224, 0, Math.PI * 2);
  ctx.stroke();

  return new THREE.CanvasTexture(canvas);
}

function createCityTwilightTexture() {
  const canvas = document.createElement('canvas');
  canvas.width = 1024;
  canvas.height = 512;
  const ctx = canvas.getContext('2d');

  const grad = ctx.createLinearGradient(0, 0, 0, 512);
  grad.addColorStop(0.0, '#0a0d24');
  grad.addColorStop(0.4, '#1e1b4b');
  grad.addColorStop(0.7, '#4c1d95');
  grad.addColorStop(0.9, '#c2410c');
  grad.addColorStop(1.0, '#fbbf24');
  ctx.fillStyle = grad;
  ctx.fillRect(0, 0, 1024, 512);

  ctx.fillStyle = 'rgba(255, 255, 255, 0.85)';
  for (let i = 0; i < 75; i++) {
    const sx = Math.random() * 1024;
    const sy = Math.random() * 240;
    const sr = Math.random() * 1.5 + 0.5;
    ctx.beginPath();
    ctx.arc(sx, sy, sr, 0, Math.PI * 2);
    ctx.fill();
  }

  ctx.fillStyle = '#17112c';
  ctx.beginPath();
  ctx.moveTo(0, 380);
  ctx.lineTo(150, 340);
  ctx.lineTo(320, 370);
  ctx.lineTo(520, 330);
  ctx.lineTo(720, 360);
  ctx.lineTo(890, 320);
  ctx.lineTo(1024, 350);
  ctx.lineTo(1024, 512);
  ctx.lineTo(0, 512);
  ctx.fill();

  ctx.fillStyle = '#0f0b1e';
  const buildings = [
    { x: 30,  w: 70,  h: 180 },
    { x: 120, w: 90,  h: 240 },
    { x: 230, w: 60,  h: 160 },
    { x: 310, w: 110, h: 290 },
    { x: 440, w: 80,  h: 210 },
    { x: 540, w: 100, h: 260 },
    { x: 660, w: 75,  h: 190 },
    { x: 755, w: 115, h: 310 },
    { x: 890, w: 95,  h: 220 }
  ];
  buildings.forEach(b => {
    ctx.fillRect(b.x, 512 - b.h, b.w, b.h);

    ctx.fillStyle = 'rgba(254, 240, 138, 0.75)';
    for (let wy = 512 - b.h + 15; wy < 490; wy += 14) {
      for (let wx = b.x + 8; wx < b.x + b.w - 10; wx += 10) {
        if (Math.random() > 0.45) {
          ctx.fillRect(wx, wy, 5, 8);
        }
      }
    }
    ctx.fillStyle = '#0f0b1e';
  });

  return new THREE.CanvasTexture(canvas);
}

function createCyberGridTexture() {
  const canvas = document.createElement('canvas');
  canvas.width = 512;
  canvas.height = 512;
  const ctx = canvas.getContext('2d');

  ctx.fillStyle = '#0a0d14';
  ctx.fillRect(0, 0, 512, 512);

  ctx.strokeStyle = 'rgba(0, 229, 255, 0.18)';
  ctx.lineWidth = 1.5;
  const step = 64;
  for (let i = 0; i <= 512; i += step) {
    ctx.beginPath();
    ctx.moveTo(i, 0);
    ctx.lineTo(i, 512);
    ctx.stroke();

    ctx.beginPath();
    ctx.moveTo(0, i);
    ctx.lineTo(512, i);
    ctx.stroke();
  }

  ctx.fillStyle = 'rgba(255, 23, 68, 0.45)';
  for (let x = step; x < 512; x += step) {
    for (let y = step; y < 512; y += step) {
      ctx.fillRect(x - 2, y - 2, 4, 4);
    }
  }

  const tex = new THREE.CanvasTexture(canvas);
  tex.wrapS = THREE.RepeatWrapping;
  tex.wrapT = THREE.RepeatWrapping;
  tex.repeat.set(5, 5);
  return tex;
}

function createGarageHoloTexture() {
  const canvas = document.createElement('canvas');
  canvas.width = 1024;
  canvas.height = 512;
  const ctx = canvas.getContext('2d');

  ctx.fillStyle = 'rgba(6, 11, 25, 0.85)';
  ctx.fillRect(0, 0, 1024, 512);

  ctx.strokeStyle = 'rgba(0, 229, 255, 0.22)';
  ctx.lineWidth = 1.5;
  for (let x = 0; x <= 1024; x += 64) {
    ctx.beginPath();
    ctx.moveTo(x, 0);
    ctx.lineTo(1024, 512);
    ctx.stroke();
  }
  for (let y = 0; y <= 512; y += 64) {
    ctx.beginPath();
    ctx.moveTo(0, y);
    ctx.lineTo(1024, y);
    ctx.stroke();
  }

  ctx.strokeStyle = '#ff1744';
  ctx.lineWidth = 4;
  ctx.strokeRect(40, 40, 944, 432);

  ctx.fillStyle = '#00e5ff';
  ctx.font = 'bold 36px monospace';
  ctx.fillText('DODGE DART • MULTIAIR TURBO 1.4L', 80, 100);

  ctx.fillStyle = '#ff1744';
  ctx.font = 'bold 24px monospace';
  ctx.fillText('CARPI5 CYBER WORKSPACE & TELEMETRY HUB', 80, 140);

  ctx.strokeStyle = '#00e5ff';
  ctx.lineWidth = 6;
  ctx.beginPath();
  ctx.arc(512, 330, 130, Math.PI * 0.8, Math.PI * 2.2);
  ctx.stroke();

  ctx.strokeStyle = '#ff1744';
  ctx.lineWidth = 8;
  ctx.beginPath();
  ctx.arc(512, 330, 130, Math.PI * 0.8, Math.PI * 1.6);
  ctx.stroke();

  ctx.fillStyle = '#ffffff';
  ctx.font = 'bold 42px monospace';
  ctx.textAlign = 'center';
  ctx.fillText('18.5 PSI', 512, 325);
  ctx.font = '18px monospace';
  ctx.fillStyle = 'rgba(255, 255, 255, 0.7)';
  ctx.fillText('BOOST PRESSURE • ACTIVE', 512, 360);

  return new THREE.CanvasTexture(canvas);
}

function createSakuraNightSkyTexture() {
  const canvas = document.createElement('canvas');
  canvas.width = 1024;
  canvas.height = 512;
  const ctx = canvas.getContext('2d');

  const grad = ctx.createLinearGradient(0, 0, 0, 512);
  grad.addColorStop(0.0, '#050716');
  grad.addColorStop(0.5, '#131138');
  grad.addColorStop(1.0, '#2b1b4a');
  ctx.fillStyle = grad;
  ctx.fillRect(0, 0, 1024, 512);

  ctx.fillStyle = 'rgba(255, 255, 255, 0.9)';
  for (let i = 0; i < 90; i++) {
    const sx = Math.random() * 1024;
    const sy = Math.random() * 380;
    const sr = Math.random() * 1.6 + 0.5;
    ctx.beginPath();
    ctx.arc(sx, sy, sr, 0, Math.PI * 2);
    ctx.fill();
  }

  ctx.fillStyle = '#fef08a';
  ctx.beginPath();
  ctx.arc(820, 110, 48, 0, Math.PI * 2);
  ctx.fill();

  ctx.fillStyle = '#0e0f2c';
  ctx.beginPath();
  ctx.arc(802, 102, 42, 0, Math.PI * 2);
  ctx.fill();

  const moonGlow = ctx.createRadialGradient(820, 110, 30, 820, 110, 110);
  moonGlow.addColorStop(0.0, 'rgba(254, 240, 138, 0.25)');
  moonGlow.addColorStop(1.0, 'rgba(254, 240, 138, 0.0)');
  ctx.fillStyle = moonGlow;
  ctx.beginPath();
  ctx.arc(820, 110, 110, 0, Math.PI * 2);
  ctx.fill();

  ctx.fillStyle = '#0b0817';
  ctx.fillRect(0, 470, 1024, 42);

  return new THREE.CanvasTexture(canvas);
}

function createTatamiDeckTexture() {
  const canvas = document.createElement('canvas');
  canvas.width = 512;
  canvas.height = 512;
  const ctx = canvas.getContext('2d');

  ctx.fillStyle = '#d4b895';
  ctx.fillRect(0, 0, 512, 512);

  const slatW = 32;
  for (let x = 0; x < 512; x += slatW) {
    const tint = (Math.random() - 0.5) * 12;
    ctx.fillStyle = `rgb(${212 + tint}, ${184 + tint * 0.8}, ${149 + tint * 0.6})`;
    ctx.fillRect(x, 0, slatW - 2, 512);

    ctx.strokeStyle = 'rgba(120, 90, 50, 0.18)';
    ctx.lineWidth = 1;
    for (let k = 0; k < 4; k++) {
      ctx.beginPath();
      const gx = x + Math.random() * (slatW - 4);
      ctx.moveTo(gx, 0);
      ctx.lineTo(gx + (Math.random() - 0.5) * 4, 512);
      ctx.stroke();
    }

    ctx.strokeStyle = '#634832';
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.moveTo(x + slatW - 1, 0);
    ctx.lineTo(x + slatW - 1, 512);
    ctx.stroke();
  }

  const tex = new THREE.CanvasTexture(canvas);
  tex.wrapS = THREE.RepeatWrapping;
  tex.wrapT = THREE.RepeatWrapping;
  tex.repeat.set(4, 4);
  return tex;
}


// ============================================================================
// --- MULTI-WORLD 3D ENVIRONMENTS (Loft, Cyber Garage, Sakura Garden, Bedroom) ---
// ============================================================================

function clearVrmEnvironment() {
  if (!vrmEnvironmentGroup) return;
  while (vrmEnvironmentGroup.children.length > 0) {
    const obj = vrmEnvironmentGroup.children[0];
    vrmEnvironmentGroup.remove(obj);
    if (obj.geometry) obj.geometry.dispose();
    if (obj.material) {
      if (Array.isArray(obj.material)) {
        obj.material.forEach(m => m.dispose());
      } else {
        obj.material.dispose();
      }
    }
  }
  envLights = [];
  sakuraPetals = [];
  vrmOceanMesh = null;
  vrmOceanGeo = null;
  vrmOceanMat = null;
  vrmOceanBasePos = null;
  vrmSkyMesh = null;
  vrmSkyTexture = null;
  vrmSunMesh = null;
  vrmSunGlow = null;
  vrmMoonMesh = null;
  vrmMoonGlow = null;
  vrmStarParticles = null;
  vrmCelestialLight = null;
  vrmGardenLanterns = [];
}

function buildLoftEnvironment() {
  clearVrmEnvironment();

  // 1. Solid Walnut Wood Plank Floor (10x10m)
  const floorGeo = new THREE.PlaneGeometry(10, 10);
  const floorTex = createWoodPlankTexture();
  const floorMat = new THREE.MeshStandardMaterial({
    map: floorTex,
    roughness: 0.68,
    metalness: 0.08
  });
  const floor = new THREE.Mesh(floorGeo, floorMat);
  floor.rotation.x = -Math.PI / 2;
  floor.position.set(0, vrmBaseY, 0);
  floor.receiveShadow = true;
  vrmEnvironmentGroup.add(floor);

  // 2. Circular Plush Cream Rug with Lavender Trim (1.75m radius)
  const rugGeo = new THREE.CircleGeometry(1.75, 48);
  const rugTex = createPlushRugTexture('#f6efe3', '#9c7cb0');
  const rugMat = new THREE.MeshStandardMaterial({
    map: rugTex,
    roughness: 0.85,
    metalness: 0.02
  });
  const rug = new THREE.Mesh(rugGeo, rugMat);
  rug.rotation.x = -Math.PI / 2;
  rug.position.set(0.05, vrmBaseY + 0.003, 0.05);
  rug.receiveShadow = true;
  vrmEnvironmentGroup.add(rug);

  // 3. Panoramic Twilight City Window Backdrop
  const winGeo = new THREE.PlaneGeometry(6.5, 3.8);
  const winTex = createCityTwilightTexture();
  const winMat = new THREE.MeshBasicMaterial({ map: winTex });
  const windowBackdrop = new THREE.Mesh(winGeo, winMat);
  windowBackdrop.position.set(0, vrmBaseY + 1.9, -2.85);
  vrmEnvironmentGroup.add(windowBackdrop);

  // Window mullions (sleek modern black beams)
  const frameMat = new THREE.MeshStandardMaterial({ color: 0x181820, roughness: 0.4 });
  const fTop = new THREE.Mesh(new THREE.BoxGeometry(6.55, 0.08, 0.06), frameMat);
  fTop.position.set(0, vrmBaseY + 3.8, -2.82);
  vrmEnvironmentGroup.add(fTop);

  const fBottom = new THREE.Mesh(new THREE.BoxGeometry(6.55, 0.08, 0.06), frameMat);
  fBottom.position.set(0, vrmBaseY + 0.02, -2.82);
  vrmEnvironmentGroup.add(fBottom);

  [-2.15, 0, 2.15].forEach(x => {
    const vBeam = new THREE.Mesh(new THREE.BoxGeometry(0.06, 3.8, 0.06), frameMat);
    vBeam.position.set(x, vrmBaseY + 1.9, -2.82);
    vrmEnvironmentGroup.add(vBeam);
  });

  const hBeam = new THREE.Mesh(new THREE.BoxGeometry(6.55, 0.05, 0.06), frameMat);
  hBeam.position.set(0, vrmBaseY + 1.9, -2.82);
  vrmEnvironmentGroup.add(hBeam);

  // 4. Floor Lamp with Warm Amber Illumination
  const lampPoleMat = new THREE.MeshStandardMaterial({ color: 0x222226, metalness: 0.8, roughness: 0.2 });
  const lampPole = new THREE.Mesh(new THREE.CylinderGeometry(0.02, 0.02, 1.85, 12), lampPoleMat);
  lampPole.position.set(1.9, vrmBaseY + 0.92, -0.4);
  vrmEnvironmentGroup.add(lampPole);

  const lampShadeMat = new THREE.MeshStandardMaterial({ color: 0xffe2b8, roughness: 0.3, emissive: 0xffaa44, emissiveIntensity: 0.35 });
  const lampShade = new THREE.Mesh(new THREE.ConeGeometry(0.24, 0.32, 24, 1, true), lampShadeMat);
  lampShade.position.set(1.9, vrmBaseY + 1.78, -0.4);
  lampShade.rotation.x = Math.PI;
  vrmEnvironmentGroup.add(lampShade);

  const warmLampLight = new THREE.PointLight(0xffa544, 2.0, 7.5, 1.4);
  warmLampLight.position.set(1.9, vrmBaseY + 1.70, -0.4);
  vrmEnvironmentGroup.add(warmLampLight);
  envLights.push(warmLampLight);

  // 5. Yoshi Round Wooden End-Table
  const tableTop = new THREE.Mesh(
    new THREE.CylinderGeometry(0.38, 0.38, 0.04, 24),
    new THREE.MeshStandardMaterial({ color: 0x613d23, roughness: 0.5 })
  );
  tableTop.position.set(0.68, vrmBaseY + 0.28, 0.22);
  vrmEnvironmentGroup.add(tableTop);

  const tableLeg = new THREE.Mesh(
    new THREE.CylinderGeometry(0.03, 0.04, 0.28, 12),
    new THREE.MeshStandardMaterial({ color: 0x1a1a1a, metalness: 0.6 })
  );
  tableLeg.position.set(0.68, vrmBaseY + 0.14, 0.22);
  vrmEnvironmentGroup.add(tableLeg);

  // Potted indoor bonsai / monstera on floor
  const pot = new THREE.Mesh(
    new THREE.CylinderGeometry(0.18, 0.12, 0.35, 16),
    new THREE.MeshStandardMaterial({ color: 0xffffff, roughness: 0.3 })
  );
  pot.position.set(-1.8, vrmBaseY + 0.175, -0.8);
  vrmEnvironmentGroup.add(pot);

  const foliage = new THREE.Mesh(
    new THREE.DodecahedronGeometry(0.36, 1),
    new THREE.MeshStandardMaterial({ color: 0x228b22, roughness: 0.7 })
  );
  foliage.position.set(-1.8, vrmBaseY + 0.55, -0.8);
  vrmEnvironmentGroup.add(foliage);

  updateYoshiEnvironmentRest();
}

function buildGarageEnvironment() {
  clearVrmEnvironment();

  // 1. Dark Obsidian / Hex Grid Floor (10x10m)
  const floorGeo = new THREE.PlaneGeometry(10, 10);
  const floorTex = createCyberGridTexture();
  const floorMat = new THREE.MeshStandardMaterial({
    map: floorTex,
    roughness: 0.25,
    metalness: 0.85
  });
  const floor = new THREE.Mesh(floorGeo, floorMat);
  floor.rotation.x = -Math.PI / 2;
  floor.position.set(0, vrmBaseY, 0);
  floor.receiveShadow = true;
  vrmEnvironmentGroup.add(floor);

  // 2. Dual Concentric Glowing Neon Floor Rings
  // Outer Ring: Dodge Dart Red (#ff1744)
  const ringOuterGeo = new THREE.RingGeometry(1.65, 1.72, 64);
  const ringOuterMat = new THREE.MeshBasicMaterial({ color: 0xff1744, side: THREE.DoubleSide });
  const ringOuter = new THREE.Mesh(ringOuterGeo, ringOuterMat);
  ringOuter.rotation.x = -Math.PI / 2;
  ringOuter.position.set(0, vrmBaseY + 0.003, 0);
  vrmEnvironmentGroup.add(ringOuter);

  // Inner Ring: Cyber Cyan (#00e5ff)
  const ringInnerGeo = new THREE.RingGeometry(0.95, 1.00, 64);
  const ringInnerMat = new THREE.MeshBasicMaterial({ color: 0x00e5ff, side: THREE.DoubleSide });
  const ringInner = new THREE.Mesh(ringInnerGeo, ringInnerMat);
  ringInner.rotation.x = -Math.PI / 2;
  ringInner.position.set(0, vrmBaseY + 0.003, 0);
  vrmEnvironmentGroup.add(ringInner);

  // 3. MultiAir Turbo Holographic Wall Screen
  const holoGeo = new THREE.PlaneGeometry(6.0, 3.2);
  const holoTex = createGarageHoloTexture();
  const holoMat = new THREE.MeshBasicMaterial({
    map: holoTex,
    transparent: true,
    opacity: 0.90
  });
  const holoWall = new THREE.Mesh(holoGeo, holoMat);
  holoWall.position.set(0, vrmBaseY + 1.8, -2.8);
  vrmEnvironmentGroup.add(holoWall);

  // 4. Cyber Showroom Overhead Spotlights
  const spotLight = new THREE.SpotLight(0xffffff, 3.0, 12, Math.PI / 4, 0.4);
  spotLight.position.set(0, vrmBaseY + 3.8, 1.0);
  spotLight.target.position.set(0, vrmBaseY, 0);
  vrmEnvironmentGroup.add(spotLight);
  vrmEnvironmentGroup.add(spotLight.target);
  envLights.push(spotLight);

  const redAccent = new THREE.PointLight(0xff1744, 2.2, 5.5);
  redAccent.position.set(2.2, vrmBaseY + 1.0, 0.2);
  vrmEnvironmentGroup.add(redAccent);
  envLights.push(redAccent);

  const cyanAccent = new THREE.PointLight(0x00e5ff, 2.2, 5.5);
  cyanAccent.position.set(-2.2, vrmBaseY + 1.0, 0.2);
  vrmEnvironmentGroup.add(cyanAccent);
  envLights.push(cyanAccent);

  updateYoshiEnvironmentRest();
}

function createCelestialSkyCanvas() {
  const canvas = document.createElement('canvas');
  canvas.width = 512;
  canvas.height = 256;
  return canvas;
}

function updateSkyCanvas(canvas, phase) {
  if (!canvas) return;
  const ctx = canvas.getContext('2d');
  const w = canvas.width;
  const h = canvas.height;
  const grad = ctx.createLinearGradient(0, 0, 0, h);

  if (phase === 'DAY') {
    grad.addColorStop(0.00, '#0d47a1'); // Deep anime zenith blue
    grad.addColorStop(0.35, '#1e88e5');
    grad.addColorStop(0.70, '#64b5f6');
    grad.addColorStop(0.92, '#bbdefb');
    grad.addColorStop(1.00, '#e3f2fd'); // Soft horizon haze
  } else if (phase === 'GOLDEN_HOUR') {
    grad.addColorStop(0.00, '#1a237e');
    grad.addColorStop(0.30, '#4a148c');
    grad.addColorStop(0.60, '#f57c00');
    grad.addColorStop(0.85, '#ffb300');
    grad.addColorStop(1.00, '#ffe082');
  } else if (phase === 'SUNSET') {
    grad.addColorStop(0.00, '#260633'); // Royal purple twilight zenith
    grad.addColorStop(0.25, '#4a0e4e');
    grad.addColorStop(0.55, '#c2185b'); // Rich crimson
    grad.addColorStop(0.78, '#e65100'); // Blazing orange
    grad.addColorStop(0.92, '#ff6d00');
    grad.addColorStop(1.00, '#ffd54f'); // Molten gold at the ocean waterline
  } else if (phase === 'CIVIL_DUSK' || phase === 'CIVIL_DAWN') {
    grad.addColorStop(0.00, '#0a0e1a');
    grad.addColorStop(0.40, '#1f1a3a');
    grad.addColorStop(0.75, '#4a1c40');
    grad.addColorStop(0.92, '#7b2d42');
    grad.addColorStop(1.00, '#9e4758');
  } else {
    // NIGHT
    grad.addColorStop(0.00, '#02040a'); // Starlit deep space
    grad.addColorStop(0.45, '#060a14');
    grad.addColorStop(0.80, '#0a1224');
    grad.addColorStop(1.00, '#101c36'); // Faint nocturnal ocean mist
  }

  ctx.fillStyle = grad;
  ctx.fillRect(0, 0, w, h);

  // Painterly soft cumulus clouds near horizon
  if (phase === 'DAY' || phase === 'GOLDEN_HOUR' || phase === 'SUNSET') {
    ctx.save();
    ctx.fillStyle = (phase === 'SUNSET') ? 'rgba(255, 120, 80, 0.22)' :
                    (phase === 'GOLDEN_HOUR') ? 'rgba(255, 200, 120, 0.22)' :
                    'rgba(255, 255, 255, 0.24)';
    const cloudYs = [h * 0.68, h * 0.74, h * 0.70];
    const cloudXs = [w * 0.20, w * 0.55, w * 0.85];
    const cloudRs = [45, 60, 50];
    for (let c = 0; c < 3; c++) {
      ctx.beginPath();
      ctx.arc(cloudXs[c], cloudYs[c], cloudRs[c], 0, Math.PI * 2);
      ctx.arc(cloudXs[c] + cloudRs[c] * 0.6, cloudYs[c] + 6, cloudRs[c] * 0.7, 0, Math.PI * 2);
      ctx.arc(cloudXs[c] - cloudRs[c] * 0.6, cloudYs[c] + 4, cloudRs[c] * 0.65, 0, Math.PI * 2);
      ctx.fill();
    }
    ctx.restore();
  }
}

function createStarfieldParticles() {
  const count = 120;
  const starGeo = new THREE.BufferGeometry();
  const positions = new Float32Array(count * 3);
  for (let i = 0; i < count; i++) {
    positions[i * 3 + 0] = (Math.random() - 0.5) * 38.0;
    positions[i * 3 + 1] = vrmBaseY + 2.0 + Math.random() * 14.0;
    positions[i * 3 + 2] = -25.2 + (Math.random() - 0.5) * 0.8;
  }
  starGeo.setAttribute('position', new THREE.BufferAttribute(positions, 3));
  const starMat = new THREE.PointsMaterial({
    color: 0xffffff,
    size: 0.16,
    transparent: true,
    opacity: 0.85
  });
  return new THREE.Points(starGeo, starMat);
}

function updateCelestialVisuals() {
  if (vrmSkyCanvas && vrmSkyTexture) {
    updateSkyCanvas(vrmSkyCanvas, vrmCelestialPhase);
    vrmSkyTexture.needsUpdate = true;
  }

  const isNight = (vrmCelestialPhase === 'NIGHT' || vrmCelestialPhase === 'CIVIL_DUSK' || vrmCelestialPhase === 'CIVIL_DAWN');
  const isSunset = (vrmCelestialPhase === 'SUNSET');
  const isGolden = (vrmCelestialPhase === 'GOLDEN_HOUR');

  if (vrmSunMesh) {
    vrmSunMesh.visible = !isNight;
  }
  if (vrmMoonMesh) {
    vrmMoonMesh.visible = isNight;
  }
  if (vrmStarParticles) {
    vrmStarParticles.visible = isNight;
  }

  // Ocean Water Base Color
  if (vrmOceanMat) {
    if (isSunset) {
      vrmOceanMat.color.setHex(0xb83824); // fiery crimson reflection
      vrmOceanMat.roughness = 0.14;
    } else if (isGolden) {
      vrmOceanMat.color.setHex(0xa86c18); // golden hour amber
      vrmOceanMat.roughness = 0.16;
    } else if (isNight) {
      vrmOceanMat.color.setHex(0x061124); // midnight deep indigo
      vrmOceanMat.roughness = 0.22;
    } else {
      vrmOceanMat.color.setHex(0x0a406c); // clear deep azure
      vrmOceanMat.roughness = 0.18;
    }
  }

  // Directional Celestial Light
  if (vrmCelestialLight) {
    if (isSunset) {
      vrmCelestialLight.color.setHex(0xff5722);
      vrmCelestialLight.intensity = 1.60;
    } else if (isGolden) {
      vrmCelestialLight.color.setHex(0xffa726);
      vrmCelestialLight.intensity = 1.40;
    } else if (isNight) {
      vrmCelestialLight.color.setHex(0x7fa8d6);
      vrmCelestialLight.intensity = 0.42;
    } else {
      vrmCelestialLight.color.setHex(0xfff5e6);
      vrmCelestialLight.intensity = 1.25;
    }
  }

  // Veranda Paper Lanterns auto-ignition (warm amber glow at dusk/night, dimmed by day)
  if (vrmGardenLanterns && vrmGardenLanterns.length > 0) {
    const ignite = (isNight || isSunset);
    vrmGardenLanterns.forEach(lant => {
      if (lant.mesh && lant.mesh.material) {
        lant.mesh.material.emissiveIntensity = ignite ? 0.85 : 0.08;
      }
      if (lant.light) {
        lant.light.intensity = ignite ? 1.85 : 0.10;
      }
    });
  }
}

function initSolarEphemerisEngine() {
  fetchSolarEphemeris();
  // Poll ephemeris every 30 minutes
  setInterval(fetchSolarEphemeris, 30 * 60 * 1000);
}

async function fetchSolarEphemeris() {
  try {
    const res = await fetch('/api/solar/ephemeris', { cache: 'no-cache' });
    if (!res.ok) throw new Error('HTTP ' + res.status);
    const data = await res.json();
    if (data && data.status === 'success') {
      vrmSolarEphemeris = data;
      vrmCelestialPhase = data.day_phase || 'DAY';
      vrmCelestialDayProgress = (data.day_progress !== undefined) ? data.day_progress : 0.5;
      updateCelestialVisuals();
      return;
    }
  } catch (err) {
    // Offline or daemon initializing - fall back mathematically
  }
  calculateOfflineSolarEphemeris();
}

function calculateOfflineSolarEphemeris() {
  const now = new Date();
  const hours = now.getHours() + (now.getMinutes() / 60);
  const sunrise = 6.5;
  const sunset = 17.0;
  if (hours >= sunrise && hours <= sunset) {
    vrmCelestialDayProgress = (hours - sunrise) / (sunset - sunrise);
    if (vrmCelestialDayProgress < 0.08) vrmCelestialPhase = 'CIVIL_DAWN';
    else if (vrmCelestialDayProgress > 0.88) vrmCelestialPhase = 'SUNSET';
    else if (vrmCelestialDayProgress > 0.75) vrmCelestialPhase = 'GOLDEN_HOUR';
    else vrmCelestialPhase = 'DAY';
  } else {
    vrmCelestialDayProgress = 1.0;
    if (hours > sunset && hours < sunset + 0.6) vrmCelestialPhase = 'CIVIL_DUSK';
    else if (hours > sunrise - 0.6 && hours < sunrise) vrmCelestialPhase = 'CIVIL_DAWN';
    else vrmCelestialPhase = 'NIGHT';
    const nightDuration = 24 - (sunset - sunrise);
    let timeSinceSunset = (hours >= sunset) ? (hours - sunset) : (hours + 24 - sunset);
    vrmCelestialNightProgress = Math.max(0.0, Math.min(1.0, timeSinceSunset / nightDuration));
  }
  updateCelestialVisuals();
}

window.setVrmCelestialPhase = function(phase, progress) {
  if (phase) vrmCelestialPhase = phase.toUpperCase();
  if (progress !== undefined) {
    vrmCelestialDayProgress = progress;
    vrmCelestialNightProgress = progress;
  }
  updateCelestialVisuals();
  console.log('[CELESTIAL] Manually set phase: ' + vrmCelestialPhase + ', progress: ' + progress);
};

function updateGardenOceanAndSky(time, delta) {
  // 1. Undulating Ocean Waves
  if (vrmOceanGeo && vrmOceanBasePos) {
    const pos = vrmOceanGeo.attributes.position;
    const base = vrmOceanBasePos;
    const count = pos.count;
    for (let i = 0; i < count; i++) {
      const bx = base.getX(i);
      const bz = base.getZ(i);
      const waveY = (
        Math.sin(bx * 0.75 + time * 1.8) * 0.048 +
        Math.cos(bz * 0.60 + time * 1.4) * 0.038 +
        Math.sin((bx + bz) * 1.15 + time * 2.2) * 0.024
      );
      pos.setY(i, waveY);
    }
    pos.needsUpdate = true;
  }

  // 2. Position Sun Orb along Day Arc
  if (vrmSunMesh && vrmSunMesh.visible) {
    const sunX = -13.0 + 26.0 * vrmCelestialDayProgress;
    const sunY = (vrmBaseY + 0.3) + Math.sin(vrmCelestialDayProgress * Math.PI) * 9.2;
    vrmSunMesh.position.set(sunX, sunY, -24.8);
    if (vrmCelestialLight) {
      vrmCelestialLight.position.set(sunX, sunY, -24.8);
    }
  }

  // 3. Position Moon Orb along Night Arc
  if (vrmMoonMesh && vrmMoonMesh.visible) {
    const moonX = -12.5 + 25.0 * vrmCelestialNightProgress;
    const moonY = (vrmBaseY + 0.6) + Math.sin(vrmCelestialNightProgress * Math.PI) * 8.6;
    vrmMoonMesh.position.set(moonX, moonY, -24.8);
    if (vrmCelestialLight) {
      vrmCelestialLight.position.set(moonX, moonY, -24.8);
    }
  }

  // 4. Starfield Twinkle
  if (vrmStarParticles && vrmStarParticles.visible) {
    vrmStarParticles.material.opacity = 0.65 + Math.sin(time * 3.0) * 0.25;
  }

  // 5. Veranda Lantern Candle Flicker
  if (vrmGardenLanterns && vrmGardenLanterns.length > 0) {
    const isNightLike = (vrmCelestialPhase === 'NIGHT' || vrmCelestialPhase === 'SUNSET' || vrmCelestialPhase === 'CIVIL_DUSK');
    if (isNightLike) {
      const flicker = 1.0 + Math.sin(time * 7.5) * 0.05 + Math.cos(time * 11.2) * 0.03;
      vrmGardenLanterns.forEach(lant => {
        if (lant.light) lant.light.intensity = 1.85 * flicker;
      });
    }
  }
}

function buildGardenEnvironment() {
  clearVrmEnvironment();

  // 1. Traditional Hinoki Wood Deck (10x8m, spanning z: +2.5 to -2.2)
  const deckGeo = new THREE.PlaneGeometry(10, 8);
  const deckTex = createTatamiDeckTexture();
  const deckMat = new THREE.MeshStandardMaterial({
    map: deckTex,
    roughness: 0.65,
    metalness: 0.05
  });
  const deck = new THREE.Mesh(deckGeo, deckMat);
  deck.rotation.x = -Math.PI / 2;
  deck.position.set(0, vrmBaseY, 0.4);
  deck.receiveShadow = true;
  vrmEnvironmentGroup.add(deck);

  // 2. Real Moving Dynamic Ocean with Undulating Waves
  // Starts right under the veranda deck edge at z = -2.25 and extends back to z = -26.25
  const oceanWidth = 36.0;
  const oceanDepth = 24.0;
  vrmOceanGeo = new THREE.PlaneGeometry(oceanWidth, oceanDepth, 48, 36);
  vrmOceanGeo.rotateX(-Math.PI / 2);
  vrmOceanBasePos = vrmOceanGeo.attributes.position.clone();

  vrmOceanMat = new THREE.MeshStandardMaterial({
    color: 0x0a406c,
    roughness: 0.18,
    metalness: 0.82,
    flatShading: true
  });
  vrmOceanMesh = new THREE.Mesh(vrmOceanGeo, vrmOceanMat);
  vrmOceanMesh.position.set(0, vrmBaseY - 0.28, -14.25);
  vrmOceanMesh.receiveShadow = true;
  vrmEnvironmentGroup.add(vrmOceanMesh);

  // 3. Dynamic Celestial Sky Dome Plane at Horizon (z = -26.2)
  const skyGeo = new THREE.PlaneGeometry(42.0, 18.0);
  vrmSkyCanvas = createCelestialSkyCanvas();
  vrmSkyTexture = new THREE.CanvasTexture(vrmSkyCanvas);
  const skyMat = new THREE.MeshBasicMaterial({ map: vrmSkyTexture });
  vrmSkyMesh = new THREE.Mesh(skyGeo, skyMat);
  vrmSkyMesh.position.set(0, vrmBaseY + 7.8, -26.2);
  vrmEnvironmentGroup.add(vrmSkyMesh);

  // 4. 3D Sun Orb + Corona Halo
  const sunGeo = new THREE.SphereGeometry(0.55, 20, 20);
  const sunMat = new THREE.MeshBasicMaterial({ color: 0xfff6cf });
  vrmSunMesh = new THREE.Mesh(sunGeo, sunMat);
  const coronaGeo = new THREE.PlaneGeometry(2.6, 2.6);
  const coronaMat = new THREE.MeshBasicMaterial({
    color: 0xffa022,
    transparent: true,
    opacity: 0.45,
    blending: THREE.AdditiveBlending,
    side: THREE.DoubleSide
  });
  vrmSunGlow = new THREE.Mesh(coronaGeo, coronaMat);
  vrmSunMesh.add(vrmSunGlow);
  vrmSunMesh.position.set(0, vrmBaseY + 6.0, -24.8);
  vrmEnvironmentGroup.add(vrmSunMesh);

  // 5. 3D Moon Orb + Soft Lunar Glow
  const moonGeo = new THREE.SphereGeometry(0.48, 20, 20);
  const moonMat = new THREE.MeshStandardMaterial({
    color: 0xe8eef5,
    emissive: 0x82a9db,
    emissiveIntensity: 0.50,
    roughness: 0.85
  });
  vrmMoonMesh = new THREE.Mesh(moonGeo, moonMat);
  const moonHaloGeo = new THREE.PlaneGeometry(2.0, 2.0);
  const moonHaloMat = new THREE.MeshBasicMaterial({
    color: 0x5b92e5,
    transparent: true,
    opacity: 0.32,
    blending: THREE.AdditiveBlending,
    side: THREE.DoubleSide
  });
  vrmMoonGlow = new THREE.Mesh(moonHaloGeo, moonHaloMat);
  vrmMoonMesh.add(vrmMoonGlow);
  vrmMoonMesh.position.set(0, vrmBaseY + 6.0, -24.8);
  vrmMoonMesh.visible = false;
  vrmEnvironmentGroup.add(vrmMoonMesh);

  // 6. 120 Twinkling Starfield Particles
  vrmStarParticles = createStarfieldParticles();
  vrmEnvironmentGroup.add(vrmStarParticles);

  // 7. Dynamic Directional Celestial Light
  vrmCelestialLight = new THREE.DirectionalLight(0xfff5e6, 1.25);
  vrmCelestialLight.position.set(0, vrmBaseY + 6.0, -24.8);
  vrmCelestialLight.castShadow = true;
  vrmEnvironmentGroup.add(vrmCelestialLight);
  envLights.push(vrmCelestialLight);

  // 8. Authentic Vermilion Japanese Veranda Railing (at z = -2.2)
  const woodMat = new THREE.MeshStandardMaterial({ color: 0x9c2222, roughness: 0.55 });
  // Top railing beam
  const beamTop = new THREE.Mesh(new THREE.BoxGeometry(7.4, 0.08, 0.09), woodMat);
  beamTop.position.set(0, vrmBaseY + 0.95, -2.2);
  vrmEnvironmentGroup.add(beamTop);
  // Mid railing beam
  const beamMid = new THREE.Mesh(new THREE.BoxGeometry(7.4, 0.04, 0.06), woodMat);
  beamMid.position.set(0, vrmBaseY + 0.45, -2.2);
  vrmEnvironmentGroup.add(beamMid);
  // 5 Support Posts
  [-2.4, -1.2, 0.0, 1.2, 2.4].forEach(x => {
    const post = new THREE.Mesh(new THREE.BoxGeometry(0.10, 1.05, 0.10), woodMat);
    post.position.set(x, vrmBaseY + 0.50, -2.2);
    vrmEnvironmentGroup.add(post);
  });
  // 16 Slender Vertical Baluster Slats
  for (let i = 0; i < 16; i++) {
    const bx = -2.25 + (i * 0.30);
    if (Math.abs(bx) < 0.1 || Math.abs(bx - 1.2) < 0.1 || Math.abs(bx + 1.2) < 0.1) continue;
    const slat = new THREE.Mesh(new THREE.BoxGeometry(0.025, 0.45, 0.025), woodMat);
    slat.position.set(bx, vrmBaseY + 0.70, -2.2);
    vrmEnvironmentGroup.add(slat);
  }

  // 9. Traditional Veranda Paper Lanterns with Warm Soft Glow
  vrmGardenLanterns = [];
  [-1.6, 1.6].forEach(x => {
    const lanternGeo = new THREE.CylinderGeometry(0.12, 0.14, 0.32, 16);
    const lanternMat = new THREE.MeshStandardMaterial({
      color: 0xffecd0,
      emissive: 0xff8844,
      emissiveIntensity: 0.55
    });
    const lantern = new THREE.Mesh(lanternGeo, lanternMat);
    lantern.position.set(x, vrmBaseY + 1.25, -2.1);
    vrmEnvironmentGroup.add(lantern);

    const lantLight = new THREE.PointLight(0xff9955, 1.6, 4.5);
    lantLight.position.set(x, vrmBaseY + 1.25, -2.1);
    vrmEnvironmentGroup.add(lantLight);
    envLights.push(lantLight);

    vrmGardenLanterns.push({ mesh: lantern, light: lantLight });
  });

  // 10. 60 Animated Sakura Blossom Petals
  sakuraPetals = [];
  const petalGeo = new THREE.PlaneGeometry(0.045, 0.045);
  const petalMat = new THREE.MeshBasicMaterial({
    color: 0xffb7c5,
    side: THREE.DoubleSide,
    transparent: true,
    opacity: 0.88
  });
  for (let i = 0; i < 60; i++) {
    const petal = new THREE.Mesh(petalGeo, petalMat);
    petal.position.set(
      (Math.random() - 0.5) * 3.5,
      vrmBaseY + Math.random() * 3.0,
      (Math.random() - 0.5) * 2.5
    );
    petal.rotation.set(Math.random() * Math.PI, Math.random() * Math.PI, Math.random() * Math.PI);
    petal.userData = {
      fallSpeed: 0.22 + Math.random() * 0.28,
      rotSpeed: (Math.random() - 0.5) * 2.0,
      seed: Math.random() * 10
    };
    vrmEnvironmentGroup.add(petal);
    sakuraPetals.push(petal);
  }

  // 11. Walkable Raised Sakura Tatami Mat Platform
  const matW = 0.84;
  const matH = 0.04;
  const matD = 0.70;
  const matGeo = new THREE.BoxGeometry(matW, matH, matD);
  const matMat = new THREE.MeshStandardMaterial({
    color: 0xcc3b68,
    roughness: 0.75,
    metalness: 0.05
  });
  const raisedMat = new THREE.Mesh(matGeo, matMat);
  raisedMat.position.set(0.52, vrmBaseY + (matH / 2), 0.16);
  raisedMat.receiveShadow = true;
  vrmEnvironmentGroup.add(raisedMat);

  // Woven gold brocade border trim
  const trimGeo = new THREE.BoxGeometry(matW + 0.02, 0.038, matD + 0.02);
  const trimMat = new THREE.MeshStandardMaterial({
    color: 0xb48a3c,
    roughness: 0.60
  });
  const matTrim = new THREE.Mesh(trimGeo, trimMat);
  matTrim.position.set(0.52, vrmBaseY + 0.019, 0.16);
  vrmEnvironmentGroup.add(matTrim);

  updateYoshiEnvironmentRest();
  updateCelestialVisuals();
}

function buildBedroomEnvironment() {
  clearVrmEnvironment();

  // 1. GUARANTEED UNBROKEN SOLID OAK UNDERLAYER (10x10m) - Zero gaps or holes forever!
  const floorGeo = new THREE.PlaneGeometry(10, 10);
  const floorTex = createWoodPlankTexture();
  const floorMat = new THREE.MeshStandardMaterial({ map: floorTex, roughness: 0.70 });
  const floor = new THREE.Mesh(floorGeo, floorMat);
  floor.rotation.x = -Math.PI / 2;
  floor.position.set(0, vrmBaseY - 0.005, 0);
  floor.receiveShadow = true;
  vrmEnvironmentGroup.add(floor);

  // 2. Load Sketchfab bedroom GLTF if not already cached
  if (!bedroomModel) {
    const loader = new THREE.GLTFLoader();
    loader.load('models/environment/bedroom/scene.gltf', (gltf) => {
      bedroomModel = gltf.scene;
      const box = new THREE.Box3().setFromObject(bedroomModel);
      const center = box.getCenter(new THREE.Vector3());
      bedroomModel.position.set(-center.x, vrmBaseY - box.min.y, -center.z);

      // FIXED: Only hide true obstructing front walls and ceiling!
      // Do NOT hide floor boards (FrontSide_4, FrontSide_11, FrontSide_12, etc.)!
      const hideMeshNames = [
        'BackSide', 'FrontSide_0', 'FrontSide_84', 'FrontSide_52', 'FrontSide_17', 'FrontSide_19'
      ];
      bedroomModel.traverse((node) => {
        if (node.isMesh) {
          for (const h of hideMeshNames) {
            if (node.name.includes(h) || (node.material && node.material.name.includes(h))) {
              node.visible = false;
              break;
            }
          }
          if (node.visible) {
            node.castShadow = true;
            node.receiveShadow = true;
            node.frustumCulled = false;
            if (node.material) {
              node.material.side = THREE.DoubleSide;
              node.material.depthWrite = true;
            }
          }
        }
      });
      vrmEnvironmentGroup.add(bedroomModel);
    });
  } else {
    vrmEnvironmentGroup.add(bedroomModel);
  }

  // Bedroom lights
  const bedLamp = new THREE.PointLight(0xffb048, 2.2, 7.5, 1.4);
  bedLamp.position.set(2.4, vrmBaseY + 1.6, 0.8);
  vrmEnvironmentGroup.add(bedLamp);
  envLights.push(bedLamp);

  const bedCeil = new THREE.PointLight(0xffecd0, 1.2, 12.0, 1.2);
  bedCeil.position.set(0.0, vrmBaseY + 3.4, 0.0);
  vrmEnvironmentGroup.add(bedCeil);
  envLights.push(bedCeil);

  updateYoshiEnvironmentRest();
}

function setVrmEnvironment(envName) {
  currentEnvironmentName = envName || 'LOFT';
  localStorage.setItem('vrmEnvironment', currentEnvironmentName);

  if (currentEnvironmentName === 'GARAGE') {
    buildGarageEnvironment();
  } else if (currentEnvironmentName === 'GARDEN') {
    buildGardenEnvironment();
  } else if (currentEnvironmentName === 'BEDROOM') {
    buildBedroomEnvironment();
  } else {
    buildLoftEnvironment();
  }

  updateWorldButtonLabel();
}

function cycleVrmEnvironment() {
  const curIdx = VRM_ENVIRONMENTS.indexOf(currentEnvironmentName);
  const nextIdx = (curIdx + 1) % VRM_ENVIRONMENTS.length;
  setVrmEnvironment(VRM_ENVIRONMENTS[nextIdx]);
}

function updateWorldButtonLabel() {
  const btn = document.getElementById('btnVrmWorldToggle');
  const labels = {
    'LOFT': '🏯 LOFT',
    'GARAGE': '🏎️ GARAGE',
    'GARDEN': '🌸 GARDEN',
    'BEDROOM': '🛏️ BEDROOM'
  };
  if (btn) btn.innerText = labels[currentEnvironmentName] || '🏯 LOFT';
}

function getEnvironmentSurfaceElevation(x, z) {
  if (currentEnvironmentName === 'GARDEN') {
    const minX = 0.52 - 0.42;
    const maxX = 0.52 + 0.42;
    const minZ = 0.16 - 0.35;
    const maxZ = 0.16 + 0.35;
    if (x >= minX && x <= maxX && z >= minZ && z <= maxZ) {
      return 0.04; // 4cm elevation onto raised mat
    }
  }
  return 0.0;
}

function getEnvironmentYoshiPos() {
  if (currentEnvironmentName === 'GARAGE') {
    return { pos: [0.65, vrmBaseY + 0.16, 0.15], rot: [0, 3.0, 0], scale: 1.35 };
  } else if (currentEnvironmentName === 'GARDEN') {
    // Yoshi sits proudly on the right side of the raised tatami mat facing the screen!
    return { pos: [0.66, vrmBaseY + 0.04 + 0.16, 0.16], rot: [0, 3.0, 0], scale: 1.35 };
  } else if (currentEnvironmentName === 'BEDROOM') {
    return { pos: [0.48, vrmBaseY + 0.16, 0.22], rot: [0, 3.0, 0], scale: 1.35 };
  } else {
    // LOFT
    return { pos: [0.65, vrmBaseY + 0.30, 0.22], rot: [0, 2.7, 0], scale: 1.25 };
  }
}

function updateYoshiEnvironmentRest() {
  if (!yoshiModel || isHoldingYoshi) return;
  const cfg = getEnvironmentYoshiPos();
  yoshiModel.position.set(cfg.pos[0], cfg.pos[1], cfg.pos[2]);
  yoshiModel.rotation.set(cfg.rot[0], cfg.rot[1], cfg.rot[2]);
  yoshiModel.scale.set(cfg.scale, cfg.scale, cfg.scale);
}

function loadYoshiPlushProp() {
  if (typeof THREE === 'undefined' || !vrmScene) return;
  const loader = new THREE.GLTFLoader();
  const yoshiUrl = 'models/environment/props/yoshi/scene.gltf';

  loader.load(
    yoshiUrl,
    (gltf) => {
      yoshiModel = gltf.scene;
      updateYoshiEnvironmentRest();

      yoshiModel.traverse((node) => {
        if (node.isMesh) {
          node.castShadow = true;
          node.receiveShadow = true;
          node.frustumCulled = false;
        }
      });

      vrmScene.add(yoshiModel);
      console.log('[Yoshi] Yoshi plushie placed in room successfully!');
    },
    (progress) => {},
    (err) => {
      console.warn('[Yoshi] Yoshi model load note:', err);
    }
  );
}


// ============================================================================
// --- AUTONOMOUS ROAMING ENGINE (Natural walking, gestures & interaction awareness) ---
// ============================================================================

function startRoamWalkAnimation() {
  if (!vrmMixer) return;
  const clip = vrmaClips['walk_loop'] || vrmaClips['action_walk'];
  if (!clip) return;

  if (!vrmRoamWalkAction) {
    vrmRoamWalkAction = vrmMixer.clipAction(clip);
    vrmRoamWalkAction.setLoop(THREE.LoopRepeat, Infinity);
    vrmRoamWalkAction.timeScale = 0.85;
  }

  vrmRoamWalkAction.reset();
  vrmRoamWalkAction.enabled = true;
  vrmRoamWalkAction.setEffectiveWeight(1.0);
  vrmRoamWalkAction.play();

  vrmaActiveName = 'walk_loop';
  vrmActionEndTime = Date.now() + 60000;

  if (vrmaIdleAction) {
    vrmaIdleAction.crossFadeTo(vrmRoamWalkAction, 0.35, false);
  }
}

function stopRoamWalkAnimation() {
  if (!vrmMixer || !vrmRoamWalkAction) return;
  if (vrmaIdleAction) {
    vrmaIdleAction.enabled = true;
    vrmaIdleAction.setEffectiveWeight(1.0);
    vrmaIdleAction.play();
    vrmRoamWalkAction.crossFadeTo(vrmaIdleAction, 0.40, false);
  } else {
    vrmRoamWalkAction.stop();
  }
  if (vrmaActiveName === 'walk_loop') {
    vrmaActiveName = null;
    vrmActionEndTime = 0;
  }
}

function updateAutonomousRoaming(delta, isSpeaking, isReacting, isActionActive, dancing, isSpeedPanic) {
  const isInteracting = isSpeaking || isReacting || isSpeedPanic || dancing || (isActionActive && vrmaActiveName !== 'walk_loop');

  if (!vrmRoamEnabled || isInteracting) {
    if (vrmRoamState === 'WALKING') {
      stopRoamWalkAnimation();
    }
    vrmRoamState = 'IDLE';

    // Smoothly turn to face driver/master (Math.PI)
    let diff = THREE.MathUtils.euclideanModulo(Math.PI - vrmRoamCurrentRotY + Math.PI, Math.PI * 2) - Math.PI;
    if (Math.abs(diff) > 0.02) {
      vrmRoamCurrentRotY += Math.sign(diff) * Math.min(Math.abs(diff), delta * 3.8);
    } else {
      vrmRoamCurrentRotY = Math.PI;
    }
    vrmNextRoamTime = Date.now() + 8500;
    return;
  }

  const now = Date.now();

  if (vrmRoamState === 'IDLE') {
    if (now >= vrmNextRoamTime) {
      const candidates = VRM_ROAM_WAYPOINTS.filter(wp => {
        const d = Math.hypot(wp.x - vrmRoamCurrentPos.x, wp.z - vrmRoamCurrentPos.z);
        return d > 0.22;
      });
      const wp = candidates[Math.floor(Math.random() * candidates.length)] || VRM_ROAM_WAYPOINTS[0];
      vrmRoamCurrentWaypoint = wp;
      vrmRoamTargetPos = { x: wp.x, z: wp.z };

      const dx = vrmRoamTargetPos.x - vrmRoamCurrentPos.x;
      const dz = vrmRoamTargetPos.z - vrmRoamCurrentPos.z;
      // In VRM space, rotation.y = 0 faces -Z (away), rotation.y = PI faces +Z (screen/user).
      // To face destination (dx, dz): forward vector is (-sin(rotY), -cos(rotY)), so angle = atan2(-dx, -dz)
      vrmRoamTargetRotY = Math.atan2(-dx, -dz);
      vrmRoamState = 'TURNING';
    }
  } else if (vrmRoamState === 'TURNING') {
    let diff = THREE.MathUtils.euclideanModulo(vrmRoamTargetRotY - vrmRoamCurrentRotY + Math.PI, Math.PI * 2) - Math.PI;
    if (Math.abs(diff) > 0.08) {
      vrmRoamCurrentRotY += Math.sign(diff) * Math.min(Math.abs(diff), delta * 3.8);
    } else {
      vrmRoamCurrentRotY = vrmRoamTargetRotY;
      vrmRoamState = 'WALKING';
      startRoamWalkAnimation();
    }
  } else if (vrmRoamState === 'WALKING') {
    const dx = vrmRoamTargetPos.x - vrmRoamCurrentPos.x;
    const dz = vrmRoamTargetPos.z - vrmRoamCurrentPos.z;
    const dist = Math.hypot(dx, dz);

    if (dist > 0.045) {
      // Keep Rem facing forward directly along her travel path
      const targetAngle = Math.atan2(-dx, -dz);
      let diff = THREE.MathUtils.euclideanModulo(targetAngle - vrmRoamCurrentRotY + Math.PI, Math.PI * 2) - Math.PI;
      vrmRoamCurrentRotY += diff * Math.min(1.0, delta * 3.5);

      const walkSpeed = 0.32;
      const step = Math.min(dist, walkSpeed * delta);
      // Advance forward directly along destination vector (zero sliding, zero moonwalking)
      vrmRoamCurrentPos.x += (dx / dist) * step;
      vrmRoamCurrentPos.z += (dz / dist) * step;
    } else {
      vrmRoamCurrentPos.x = vrmRoamTargetPos.x;
      vrmRoamCurrentPos.z = vrmRoamTargetPos.z;
      stopRoamWalkAnimation();
      vrmRoamState = 'ARRIVED';

      if (vrmRoamCurrentWaypoint && vrmRoamCurrentWaypoint.faceOcean) {
        // Rem turns to gaze out at the ocean horizon (rotation.y = 0.05 faces -Z)
        vrmRoamTargetRotY = 0.05;
      } else {
        // Face forward toward master / driver
        vrmRoamTargetRotY = Math.PI;
      }

      const roll = Math.random();
      if (roll < 0.22 && vrmaClips['pose_shy_wave']) {
        playVrmAction('pose_shy_wave', 3500, true);
      } else if (roll < 0.40 && vrmaClips['greeting_wave_right']) {
        playVrmAction('greeting_wave_right', 3000, true);
      } else if (roll < 0.55 && vrmaClips['model_pose']) {
        playVrmAction('model_pose', 3200, true);
      }

      vrmNextRoamTime = Date.now() + 8000 + Math.random() * 7000;
    }
  } else if (vrmRoamState === 'ARRIVED') {
    let diff = THREE.MathUtils.euclideanModulo(vrmRoamTargetRotY - vrmRoamCurrentRotY + Math.PI, Math.PI * 2) - Math.PI;
    if (Math.abs(diff) > 0.04) {
      vrmRoamCurrentRotY += Math.sign(diff) * Math.min(Math.abs(diff), delta * 2.8);
    } else {
      vrmRoamCurrentRotY = vrmRoamTargetRotY;
      if (now >= vrmNextRoamTime) {
        vrmRoamState = 'IDLE';
      }
    }
  }
}

function toggleVrmRoaming() {
  vrmRoamEnabled = !vrmRoamEnabled;
  localStorage.setItem('vrmRoamEnabled', vrmRoamEnabled ? 'true' : 'false');
  if (!vrmRoamEnabled) {
    if (vrmRoamState === 'WALKING') {
      stopRoamWalkAnimation();
    }
    vrmRoamState = 'IDLE';
    vrmRoamTargetRotY = Math.PI;
  } else {
    vrmNextRoamTime = Date.now() + 2500;
  }
  updateRoamButtonLabel();
}

function updateRoamButtonLabel() {
  const btn = document.getElementById('btnVrmRoamToggle');
  if (btn) {
    btn.innerText = vrmRoamEnabled ? '🚶 ROAM: ON' : '🧍 STAY';
    btn.style.borderColor = vrmRoamEnabled ? '#22c55e' : '#64748b';
    btn.style.color = vrmRoamEnabled ? '#4ade80' : '#94a3b8';
  }
}

function toggleRemRumAvatar() {
  const isRem = (currentVrmModelName.includes('Rem') || currentVrmModelName.toLowerCase().includes('rem'));
  const newModel = isRem ? 'Rum.vrm' : 'Rem.vrm';
  currentVrmModelName = newModel;
  localStorage.setItem('vrmCurrentAvatar', newModel);
  loadRumVrmModel(newModel);
  updateModelButtonLabel();
}

function updateModelButtonLabel() {
  const btn = document.getElementById('btnVrmModelToggle');
  const hudTitle = document.getElementById('vrmHudTitle');
  const emotionPill = document.getElementById('waifuEmotionPill');
  const isRem = (currentVrmModelName.includes('Rem') || currentVrmModelName.toLowerCase().includes('rem'));

  if (btn) {
    btn.innerText = isRem ? '💙 REM' : '💜 RUM';
    btn.style.borderColor = isRem ? '#38bdf8' : '#c084fc';
    btn.style.color = isRem ? '#38bdf8' : '#c084fc';
  }
  if (hudTitle) {
    hudTitle.innerHTML = isRem ? '<span>💙</span> REM • SHOTGUN' : '<span>💜</span> RUM • SHOTGUN';
  }
  if (emotionPill) {
    emotionPill.innerText = isRem ? '💙 REM (3D VRM) • DEVOTED TO MASTER' : '💜 RUM (3D VRM) • PLAYFUL SISTER';
  }
}



function initAvatarPokeRaycaster(canvas) {

  if (!canvas || !vrmCamera) return;

  const raycaster = new THREE.Raycaster();

  const mouse = new THREE.Vector2();

  // Mouse wheel zoom
  canvas.addEventListener('wheel', (e) => {
    e.preventDefault();
    const d = Math.sign(e.deltaY) * 0.08;
    vrmZoomMultiplier = Math.max(0.65, Math.min(1.85, vrmZoomMultiplier + d));
  }, { passive: false });

  // Double click / tap reset zoom
  canvas.addEventListener('dblclick', () => {
    vrmZoomMultiplier = 1.0;
  });

  // Touch pinch-to-zoom for touchscreen
  let touchDist = 0;
  canvas.addEventListener('touchstart', (e) => {
    if (e.touches.length === 2) {
      touchDist = Math.hypot(
        e.touches[0].clientX - e.touches[1].clientX,
        e.touches[0].clientY - e.touches[1].clientY
      );
    }
  }, { passive: true });

  canvas.addEventListener('touchmove', (e) => {
    if (e.touches.length === 2 && touchDist > 0) {
      const curDist = Math.hypot(
        e.touches[0].clientX - e.touches[1].clientX,
        e.touches[0].clientY - e.touches[1].clientY
      );
      const ratio = touchDist / curDist;
      vrmZoomMultiplier = Math.max(0.65, Math.min(1.85, vrmZoomMultiplier * (ratio > 1 ? 1.025 : 0.975)));
      touchDist = curDist;
    }
  }, { passive: true });



  canvas.addEventListener('pointerdown', (e) => {

    const rect = canvas.getBoundingClientRect();

    mouse.x = ((e.clientX - rect.left) / rect.width) * 2 - 1;

    mouse.y = -((e.clientY - rect.top) / rect.height) * 2 + 1;



    raycaster.setFromCamera(mouse, vrmCamera);



    // 1. Check if user tapped Yoshi Plush

    if (yoshiModel) {

      const yoshiHits = raycaster.intersectObjects(yoshiModel.children, true);

      if (yoshiHits.length > 0) {

        triggerYoshiPlushInteraction();

        return;

      }

    }



    // 2. Check if user tapped Rum VRM

    if (vrmModel) {

      const hits = raycaster.intersectObjects(vrmModel.children, true);

      if (hits.length > 0) {

        const hitPoint = hits[0].point;

        const box = new THREE.Box3().setFromObject(vrmModel);

        const relY = (hitPoint.y - box.min.y) / Math.max(0.1, box.max.y - box.min.y);

        triggerAvatarPokeReaction(relY);

      }

    }

  });

}



function triggerAvatarPokeReaction(relY) {

  if (relY >= 0.78) {

    playVrmAction('greeting', 3200);

    setWaifuEmotion('HAPPY', '😊 HAPPY • HEADPAT RECEIVED');

    speakUtterance('Ehehe! That tickles, Master! Headpats make Rum so happy!');

  } else if (relY >= 0.52) {

    playVrmAction('pose_shy_wave', 3500);

    setWaifuEmotion('SURPRISED', '😳 SURPRISED • KEEP EYES ON ROAD');

    speakUtterance('Hey Master! Keep both hands on the steering wheel, eyes on the road!');

  } else if (relY >= 0.28) {

    playVrmAction('amusement', 3400);

    setWaifuEmotion('DEVOTED', '💖 DEVOTED • TICKLED');

    speakUtterance('Whoa! That tickles! Rum is your co-pilot, focus on the boost!');

  } else {

    playVrmAction('action_jump', 3000);

    setWaifuEmotion('EXCITED', '✨ EXCITED • READY FOR HYPERDRIVE');

    speakUtterance('One, two! Rum feet are ready to jump into hyperdrive!');

  }

}



function triggerYoshiPlushInteraction() {

  if (!yoshiModel) return;

  isHoldingYoshi = !isHoldingYoshi;



  if (isHoldingYoshi) {

    playVrmAction('pose_v_sign', 4000);

    setWaifuEmotion('HAPPY', '🦖 YOSHI TIME! • BEST FRIENDS');

    speakUtterance('Yay! Master, look at my Yoshi plushie! He loves riding shotgun in the car too!');

    yoshiModel.position.set(0.08, vrmBaseY + (vrmSize.y * 0.52), 0.32);

    yoshiModel.rotation.set(-0.2, 0.2, 0);

  } else {

    playVrmAction('greeting', 3000);

    setWaifuEmotion('DEVOTED', '🦖 YOSHI RESTING');

    speakUtterance('Okay! Let us put Yoshi right here so he can watch the road with us!');

    updateYoshiEnvironmentRest();

  }

}





// --- 9. IN-DASH WEB BROWSER CONTROLLER ---

let browserHistory = [];

let browserHistoryIndex = -1;



function browserNavigateTo(url) {

  if (!url) return;

  const input = document.getElementById('browserUrlInput');

  const iframe = document.getElementById('carpiBrowserIframe');

  const overlay = document.getElementById('browserWelcomeOverlay');

  

  if (!url.startsWith('http://') && !url.startsWith('https://')) {

    if (url.includes('.') && !url.includes(' ')) {

      url = 'https://' + url;

    } else {

      url = 'https://www.google.com/search?q=' + encodeURIComponent(url);

    }

  }



  if (input) input.value = url;

  if (overlay) overlay.style.display = 'none';

  if (iframe) iframe.src = url;



  if (browserHistory[browserHistoryIndex] !== url) {

    browserHistory = browserHistory.slice(0, browserHistoryIndex + 1);

    browserHistory.push(url);

    browserHistoryIndex = browserHistory.length - 1;

  }

}



function browserLoadUrl() {

  const input = document.getElementById('browserUrlInput');

  if (input && input.value.trim()) {

    browserNavigateTo(input.value.trim());

  }

}



function browserReload() {

  const iframe = document.getElementById('carpiBrowserIframe');

  if (iframe && iframe.src && iframe.src !== 'about:blank') {

    iframe.src = iframe.src;

  }

}



function browserGoHome() {

  const input = document.getElementById('browserUrlInput');

  const iframe = document.getElementById('carpiBrowserIframe');

  const overlay = document.getElementById('browserWelcomeOverlay');

  if (input) input.value = '';

  if (iframe) iframe.src = 'about:blank';

  if (overlay) overlay.style.display = 'flex';

}



function browserGoBack() {

  if (browserHistoryIndex > 0) {

    browserHistoryIndex--;

    const prevUrl = browserHistory[browserHistoryIndex];

    const input = document.getElementById('browserUrlInput');

    const iframe = document.getElementById('carpiBrowserIframe');

    if (input) input.value = prevUrl;

    if (iframe) iframe.src = prevUrl;

  } else {

    browserGoHome();

  }

}



function browserGoForward() {

  if (browserHistoryIndex < browserHistory.length - 1) {

    browserHistoryIndex++;

    const nextUrl = browserHistory[browserHistoryIndex];

    const input = document.getElementById('browserUrlInput');

    const iframe = document.getElementById('carpiBrowserIframe');

    if (input) input.value = nextUrl;

    if (iframe) iframe.src = nextUrl;

  }

}





// --- 19. GOOGLE OAUTH 2.0 DEVICE FLOW & GEMINI AI INTEGRATION ---

let googleAuthPollTimer = null;

let googleDeviceDirectUrl = "https://www.google.com/device";

let googleQrCodeInstance = null;



function checkGoogleAuthStatus() {

  fetch('/api/auth/google/status')

    .then(r => r.json())

    .then(data => {

      const card = document.getElementById('googleAuthCard');

      const badge = document.getElementById('googleAuthBadge');

      const unlinkedView = document.getElementById('googleAuthUnlinkedView');

      const linkedView = document.getElementById('googleAuthLinkedView');

      const inputCid = document.getElementById('cfgGoogleClientId');

      const inputCsec = document.getElementById('cfgGoogleClientSecret');



      if (inputCid && data.client_id && !inputCid.value) {

        inputCid.value = data.client_id;

      }



      if (data.authenticated || data.has_api_key) {

        if (badge) {

          if (data.authenticated) {

            badge.innerText = '● GEMINI ONLINE (OAUTH LINKED)';

          } else {

            badge.innerText = '● GEMINI ONLINE (CLOUD API KEY)';

          }

          badge.style.background = 'rgba(52, 168, 83, 0.15)';

          badge.style.color = '#34a853';

        }

        if (unlinkedView) unlinkedView.style.display = 'none';

        if (linkedView) linkedView.style.display = 'block';



        const uName = document.getElementById('googleUserName');

        const uEmail = document.getElementById('googleUserEmail');

        const uAvatar = document.getElementById('googleUserAvatar');



        if (uName) uName.innerText = data.authenticated ? (data.name || 'Google User') : 'Google Gemini Cloud AI';

        if (uEmail) uEmail.innerText = data.authenticated ? (data.email || 'user@gmail.com') : ('API Key Active (' + (data.api_key_masked || '••••••') + ')');

        if (uAvatar) {

          uAvatar.src = data.picture || 'assets/pics/maia_avatar.jpg';

          uAvatar.onerror = function() { this.src = 'assets/pics/maia_avatar.jpg'; };

        }



        const selModel = document.getElementById('cfgGeminiModel');

        const m = (currentAiSettings && currentAiSettings.gemini_model) || data.gemini_model || 'gemini-3.5-flash';

        if (selModel) selModel.value = m;



        const selEngine = document.getElementById('cfgAiEngineMode');

        const engMode = (currentAiSettings && currentAiSettings.mode) || data.mode || 'GEMINI';

        if (selEngine) selEngine.value = (engMode === 'CLOUD_API') ? 'GEMINI' : engMode;

      } else {

        if (badge) {

          badge.innerText = '● NOT LINKED (OFFLINE GGUF)';

          badge.style.background = 'rgba(66, 133, 244, 0.15)';

          badge.style.color = '#4285f4';

        }

        if (unlinkedView) unlinkedView.style.display = 'block';

        if (linkedView) linkedView.style.display = 'none';

      }

    })

    .catch(err => console.warn('[GOOGLE_AUTH] Status check failed:', err));

}



function openGoogleAuthModal() {

  const modal = document.getElementById('googleAuthModal');

  const setupBox = document.getElementById('googleAuthSetupClientIdBox');

  const bodyGrid = document.getElementById('googleAuthModalBody');

  const successBox = document.getElementById('googleAuthSuccessBox');

  const statusText = document.getElementById('googleAuthStatusText');

  const codeBox = document.getElementById('googleAuthUserCode');

  const qrElem = document.getElementById('googleAuthQr');



  if (!modal) return;

  modal.style.display = 'flex';

  if (successBox) successBox.style.display = 'none';



  fetch('/api/auth/google/status')

    .then(r => r.json())

    .then(data => {

      const configuredCid = (document.getElementById('cfgGoogleClientId')?.value || data.client_id || '').trim();

      if (!configuredCid) {

        if (setupBox) setupBox.style.display = 'block';

        if (bodyGrid) bodyGrid.style.display = 'none';

        const modalCid = document.getElementById('modalGoogleClientId');

        if (modalCid) modalCid.focus();

      } else {

        if (setupBox) setupBox.style.display = 'none';

        if (bodyGrid) bodyGrid.style.display = 'grid';

        if (statusText) statusText.innerText = 'Requesting device authorization code from Google...';

        if (codeBox) codeBox.innerText = '---- ----';

        if (qrElem) qrElem.innerHTML = '';



        startGoogleDeviceFlowRequest(configuredCid);

      }

    })

    .catch(() => {

      if (setupBox) setupBox.style.display = 'block';

      if (bodyGrid) bodyGrid.style.display = 'none';

    });

}



function submitModalClientIdAndStart() {

  const cidInput = document.getElementById('modalGoogleClientId');

  const csecInput = document.getElementById('modalGoogleClientSecret');

  const cid = cidInput ? cidInput.value.trim() : '';

  const csec = csecInput ? csecInput.value.trim() : '';



  if (!cid) {

    alert('Please enter your Google Cloud OAuth Client ID.');

    return;

  }



  const mainCid = document.getElementById('cfgGoogleClientId');

  const mainCsec = document.getElementById('cfgGoogleClientSecret');

  if (mainCid) mainCid.value = cid;

  if (mainCsec) mainCsec.value = csec;



  fetch('/api/auth/google/config', {

    method: 'POST',

    headers: { 'Content-Type': 'application/json' },

    body: JSON.stringify({ client_id: cid, client_secret: csec })

  })

    .then(r => r.json())

    .then(() => {

      const setupBox = document.getElementById('googleAuthSetupClientIdBox');

      const bodyGrid = document.getElementById('googleAuthModalBody');

      if (setupBox) setupBox.style.display = 'none';

      if (bodyGrid) bodyGrid.style.display = 'grid';

      startGoogleDeviceFlowRequest(cid, csec);

    })

    .catch(err => alert('Failed to save OAuth credentials: ' + err));

}



function startGoogleDeviceFlowRequest(cid, csec) {

  const statusText = document.getElementById('googleAuthStatusText');

  const codeBox = document.getElementById('googleAuthUserCode');

  const qrElem = document.getElementById('googleAuthQr');



  fetch('/api/auth/google/start', {

    method: 'POST',

    headers: { 'Content-Type': 'application/json' },

    body: JSON.stringify({ client_id: cid, client_secret: csec })

  })

    .then(r => r.json())

    .then(data => {

      if (data.status === 'pending') {

        const userCode = data.user_code;

        const directUrl = data.direct_url || (data.verification_url + '?user_code=' + userCode);

        googleDeviceDirectUrl = directUrl;



        if (codeBox) codeBox.innerText = userCode;

        if (statusText) statusText.innerText = `Waiting for phone approval (Polls every ${data.interval || 5}s)...`;



        if (qrElem) {

          qrElem.innerHTML = '';

          try {

            if (typeof QRCode !== 'undefined') {

              new QRCode(qrElem, {

                text: directUrl,

                width: 150,

                height: 150,

                colorDark: '#000000',

                colorLight: '#ffffff',

                correctLevel: QRCode.CorrectLevel.M

              });

            } else {

              qrElem.innerHTML = `<a href="${directUrl}" target="_blank" style="color:#4285f4; font-size:11px; word-break:break-all;">${directUrl}</a>`;

            }

          } catch (e) {

            console.error('[QRCODE] Render error:', e);

            qrElem.innerHTML = `<a href="${directUrl}" target="_blank" style="color:#4285f4; font-size:11px; word-break:break-all;">${directUrl}</a>`;

          }

        }



        startGoogleAuthPolling();

      } else {

        if (statusText) statusText.innerText = 'Error: ' + (data.message || 'Failed to start auth flow.');

        const setupBox = document.getElementById('googleAuthSetupClientIdBox');

        const bodyGrid = document.getElementById('googleAuthModalBody');

        if (setupBox && data.message && data.message.includes('Client ID')) {

          setupBox.style.display = 'block';

          bodyGrid.style.display = 'none';

        }

      }

    })

    .catch(err => {

      if (statusText) statusText.innerText = 'Network connection failed: ' + err;

    });

}



function startGoogleAuthPolling() {

  stopGoogleAuthPolling();

  googleAuthPollTimer = setInterval(() => {

    fetch('/api/auth/google/status')

      .then(r => r.json())

      .then(data => {

        if (data.authenticated) {

          stopGoogleAuthPolling();

          onGoogleAuthSuccess(data);

        } else if (data.status === 'error') {

          const statusText = document.getElementById('googleAuthStatusText');

          if (statusText) statusText.innerText = 'Auth Notice: ' + (data.last_error || 'Expired or Denied');

        }

      })

      .catch(err => console.warn('[GOOGLE_AUTH] Poll error:', err));

  }, 2500);

}



function stopGoogleAuthPolling() {

  if (googleAuthPollTimer) {

    clearInterval(googleAuthPollTimer);

    googleAuthPollTimer = null;

  }

}



function onGoogleAuthSuccess(authData) {

  const bodyGrid = document.getElementById('googleAuthModalBody');

  const successBox = document.getElementById('googleAuthSuccessBox');

  const successUser = document.getElementById('googleAuthSuccessUser');



  if (bodyGrid) bodyGrid.style.display = 'none';

  if (successBox) successBox.style.display = 'block';

  if (successUser) {

    const disp = authData.name ? `${authData.name} (${authData.email})` : (authData.email || 'Master Creator');

    successUser.innerText = 'Signed in as ' + disp;

  }



  updateAiEngineMode('GEMINI');



  const userName = authData.name || 'Master Creator';

  const joyfulSpeech = `Yay! Google Account connected, ${userName}! Gemini cloud intelligence is now online and riding shotgun with us!`;

  if (typeof speakUtterance === 'function') {

    speakUtterance(joyfulSpeech, 'HAPPY');

  }

  if (typeof showAiSpeechToast === 'function') {

    showAiSpeechToast('Google Connected! Gemini AI Online!');

  }



  checkGoogleAuthStatus();



  setTimeout(() => {

    closeGoogleAuthModal();

  }, 2800);

}



function closeGoogleAuthModal() {

  const modal = document.getElementById('googleAuthModal');

  if (modal) modal.style.display = 'none';

  stopGoogleAuthPolling();

}



function openGoogleDeviceUrlInBrowser() {

  if (googleDeviceDirectUrl) {

    window.open(googleDeviceDirectUrl, '_blank');

  }

}



function disconnectGoogleAccount() {

  if (!confirm('Are you sure you want to disconnect your Google Account and return to the local offline Qwen model?')) {

    return;

  }



  fetch('/api/auth/google/logout', { method: 'POST' })

    .then(r => r.json())

    .then(() => {

      updateAiEngineMode('LOCAL_GGUF');

      checkGoogleAuthStatus();

      if (typeof speakUtterance === 'function') {

        speakUtterance('Google Account disconnected. Offline local brain is active.', 'DEFAULT');

      }

    })

    .catch(err => alert('Failed to disconnect Google account: ' + err));

}



function saveGoogleCloudConfig() {

  const cid = document.getElementById('cfgGoogleClientId')?.value.trim() || '';

  const csec = document.getElementById('cfgGoogleClientSecret')?.value.trim() || '';



  fetch('/api/auth/google/config', {

    method: 'POST',

    headers: { 'Content-Type': 'application/json' },

    body: JSON.stringify({ client_id: cid, client_secret: csec })

  })

    .then(r => r.json())

    .then(() => {

      alert('Google OAuth Client credentials saved!');

      checkGoogleAuthStatus();

    })

    .catch(err => alert('Failed to save config: ' + err));

}



function updateAiEngineMode(mode) {

  fetch('/api/ai/settings', {

    method: 'POST',

    headers: { 'Content-Type': 'application/json' },

    body: JSON.stringify({ mode: mode })

  })

    .then(r => r.json())

    .then(data => {

      if (data.settings) currentAiSettings = Object.assign(currentAiSettings, data.settings);

      const selEngine = document.getElementById('cfgAiEngineMode');

      if (selEngine) selEngine.value = mode;

      console.log('[AI] Copilot engine mode updated to:', mode);

    })

    .catch(err => console.warn('[AI] Mode update error:', err));

}



function updateGeminiModel(model) {

  fetch('/api/ai/settings', {

    method: 'POST',

    headers: { 'Content-Type': 'application/json' },

    body: JSON.stringify({ gemini_model: model })

  })

    .then(r => r.json())

    .then(data => {

      if (data.settings) currentAiSettings = Object.assign(currentAiSettings, data.settings);

      console.log('[AI] Gemini model updated to:', model);

    })

    .catch(err => console.warn('[AI] Model update error:', err));

}

