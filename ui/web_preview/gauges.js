// CarPi5 UI Core: Cluster Gauges, 25Hz SSE Telemetry Stream, Navigation & Startup Orchestration

// --- FULLSCREEN 12-GAUGE CLUSTER CONTROLS ---
let isGaugeFullscreen = false;
let previousLayoutBeforeFullscreen = 3;

function toggleFullscreenGauges() {
  if (isGaugeFullscreen) {
    exitFullscreenGauges();
  } else {
    enterFullscreenGauges();
  }
}

function enterFullscreenGauges() {
  isGaugeFullscreen = true;
  document.body.classList.add('gauge-fullscreen-active');
  previousLayoutBeforeFullscreen = currentLayout;
  currentLayout = 12;
  initGaugeGrid();
  try {
    if (document.documentElement.requestFullscreen && !document.fullscreenElement) {
      document.documentElement.requestFullscreen().catch(() => {});
    }
  } catch (e) {}
}

function exitFullscreenGauges() {
  isGaugeFullscreen = false;
  document.body.classList.remove('gauge-fullscreen-active');
  if (previousLayoutBeforeFullscreen) {
    currentLayout = previousLayoutBeforeFullscreen;
  }
  initGaugeGrid();
  try {
    if (document.exitFullscreen && document.fullscreenElement) {
      document.exitFullscreen().catch(() => {});
    }
  } catch (e) {}
}

window.addEventListener('keydown', (e) => {
  if (e.key === 'Escape' && isGaugeFullscreen) {
    exitFullscreenGauges();
  }
});

// --- CLOCK FORMATTING (12-Hour AM/PM vs 24-Hour Military) ---
let is24HourClock = localStorage.getItem('carpi5_clock_format') === '24H';

function toggleClockFormat() {
  is24HourClock = !is24HourClock;
  localStorage.setItem('carpi5_clock_format', is24HourClock ? '24H' : '12H');
  const btn = document.getElementById('btnClockFormat');
  if (btn) btn.innerText = is24HourClock ? "CLOCK: 24-HOUR (MILITARY)" : "CLOCK: 12-HOUR (AM/PM)";
  const clock = document.getElementById('footerClock');
  if (typeof updateSystemClock === 'function') updateSystemClock(); else if (clock) clock.innerText = formatClockTime(new Date());
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

// --- 2. MULTI-SCREEN NAVIGATION ---

function navigateTo(screenId) {
  if (screenId === 'files') screenId = 'explorer';
  if (screenId === 'trips') screenId = 'trip';
  if (screenId === 'drag_launch') screenId = 'dragy';
  if (screenId !== "gauges" && isGaugeFullscreen) {
    exitFullscreenGauges();
  }
  currentScreen = screenId;

  // Toggle Screen Views
  const screens = {
    home: document.getElementById('screenHome'),
    vehicle: document.getElementById('screenVehicle'),
    gauges: document.getElementById('screenGauges'),
    ai: document.getElementById('screenAI'),
    media: document.getElementById('screenMedia'),
    music: document.getElementById('screenMusic'),
    audiosuite: document.getElementById('screenAudioSuite'),
    explorer: document.getElementById('screenExplorer'),
    games: document.getElementById('screenGames'),
    browser: document.getElementById('screenBrowser'),
    maps: document.getElementById('screenMaps'),
    dashcam: document.getElementById('screenDashcam'),
    diagnostics: document.getElementById('screenDiagnostics'),
    trip: document.getElementById('screenTripLogger'),
    hardware: document.getElementById('screenHardware'),
    settings: document.getElementById('screenSettings'),
    library: document.getElementById('screenLibrary'),
    maintenance: document.getElementById('screenMaintenance'),
    dragy: document.getElementById('screenDragy'),
    phone: document.getElementById('screenPhone'),
    canyon: document.getElementById('screenCanyon')
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
  // Phase 2: Diagnostic & Utility Prop Attachment Lifecycle
  if (screenId === 'diagnostics') {
    if (typeof attachMultimeterToVrm === 'function') attachMultimeterToVrm();
  } else {
    if (typeof detachMultimeterFromVrm === 'function') detachMultimeterFromVrm();
  }
  // Phase 8: MultiAir Maintenance & Vector Memory Refresh Lifecycle
  if (screenId === 'maintenance') {
    refreshMaintenanceData();
  }
  // Phase 9: Drag Launch Control & G-G Friction Circle Init Lifecycle
  if (screenId === 'dragy' || screenId === 'drag_launch') {
    if (typeof initDragyStudio === 'function') initDragyStudio();
  }
  // Phase 15: Cockpit Telephony, Kinship & SMS Studio Lifecycle
  if (screenId === 'phone') {
    if (typeof initPhoneStudio === 'function') initPhoneStudio();
  }
  // Toggle Bottom Dock Buttons
  const buttons = {
    home: document.getElementById('dockBtnHome'),
    gauges: document.getElementById('dockBtnGauges'),
    ai: document.getElementById('dockBtnAI'),
    media: document.getElementById('dockBtnMedia'),
    phone: document.getElementById('dockBtnPhone'),
    games: document.getElementById('dockBtnGames'),
    browser: document.getElementById('dockBtnBrowser'),
    maps: document.getElementById('dockBtnMaps'),
    dashcam: document.getElementById('dockBtnDashcam'),
    settings: document.getElementById('dockBtnSettings')
  };

  Object.keys(buttons).forEach(key => {
    if (buttons[key]) {
      if (key === screenId || (screenId === 'music' && key === 'media')) {
        buttons[key].classList.add('active');
      } else {
        buttons[key].classList.remove('active');
      }
    }
  });

  // Specific Screen Hooks
  // Cockpit top HOME button active state
  const headerHome = document.getElementById('headerHomeBtn');
  if (headerHome) {
    if (screenId === 'home') {
      headerHome.classList.add('on-home');
    } else {
      headerHome.classList.remove('on-home');
    }
  }
  if (screenId === "explorer" || screenId === "files") {
    if (typeof openFileExplorer === "function") openFileExplorer();
  }
  if (screenId === "hardware" || screenId === "sbc") {
    if (typeof startHardwareStudioLoop === "function") startHardwareStudioLoop();
  } else {
    if (typeof stopHardwareStudioLoop === "function") stopHardwareStudioLoop();
  }
  if (screenId === "hardware" || screenId === "sbc") {
    if (typeof startHardwareStudioLoop === "function") startHardwareStudioLoop();
  } else {
    if (typeof stopHardwareStudioLoop === "function") stopHardwareStudioLoop();
  }
  if (screenId === "audiosuite") {
    if (typeof renderFullAudioSuiteEqGrid === "function") renderFullAudioSuiteEqGrid();
  }
  if (typeof initTouchScrollEngine === 'function') setTimeout(initTouchScrollEngine, 60);
  if (screenId === 'media' && typeof checkExternalAppStatus === 'function') checkExternalAppStatus();
  if (screenId === "diagnostics") {
    if (typeof refreshDiagnostics === "function") refreshDiagnostics();
    if (typeof initTouchScrollEngine === "function") setTimeout(initTouchScrollEngine, 100);
  } else if (screenId === "trip") {
    if (typeof refreshTripsList === "function") refreshTripsList();
    if (typeof initTouchScrollEngine === "function") setTimeout(initTouchScrollEngine, 100);
  } else if (screenId === "gauges") {
    requestAnimationFrame(() => {
      resizeAllCanvases();
    });
    setTimeout(resizeAllCanvases, 50);
  } else if (screenId === "ai") {
    if (!vrmInitialized && typeof initVrmEngine === "function") {
      initVrmEngine();
    }
    if (typeof dockCompanionToAi === "function") dockCompanionToAi(false);
    scrollChatToBottom();
    fetchAiHistory();
  } else if (screenId === "maps") {
    initOrUpdateMap();
  } else if (screenId === "dashcam") {
    refreshDashcamClips();
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
    if (!isConnected || (telemetry.fuel_mpg_instant === null && telemetry.fuel_gph === null)) {
      displayStr = "--";
      subStr = "DISCONNECTED";
      pct = 0;
      color = "#8c9ba5";
    } else if ((telemetry.speed_mph || 0) < 2.0) {
      const gph = (telemetry.fuel_gph !== null && telemetry.fuel_gph !== undefined) ? telemetry.fuel_gph : 0.25;
      rawVal = gph;
      displayStr = rawVal.toFixed(2);
      subStr = "GPH (IDLE BURN)";
      pct = Math.min(1.0, rawVal / 2.0);
      color = "#00e676";
    } else if (telemetry.fuel_mpg_instant !== null && telemetry.fuel_mpg_instant !== undefined) {
      rawVal = telemetry.fuel_mpg_instant;
      displayStr = rawVal.toFixed(1);
      subStr = "INSTANT MPG";
      pct = Math.min(1.0, rawVal / 50.0);
      color = "#00e676";
    } else {
      displayStr = "--";
      subStr = "CALCULATING";
      pct = 0;
      color = "#00e676";
    }
  } else if (sensorKey === "load") {
    rawVal = (telemetry.engine_load_pct !== undefined && telemetry.engine_load_pct !== null) ? telemetry.engine_load_pct : 0;
    displayStr = Math.round(rawVal) + "%";
    subStr = rawVal > 85 ? "HIGH LOAD" : "ENGINE LOAD";
    pct = rawVal / 100.0;
    color = rawVal > 85 ? "#ff3344" : "#ff5252";
  } else if (sensorKey === "timing") {
    rawVal = (telemetry.timing_advance_deg !== undefined && telemetry.timing_advance_deg !== null) ? telemetry.timing_advance_deg : 0;
    displayStr = (rawVal >= 0 ? "+" : "") + rawVal.toFixed(1) + "°";
    subStr = "TIMING ADV";
    pct = Math.max(0, Math.min(1, (rawVal + 10) / 50.0));
    color = "#e040fb";
  } else if (sensorKey === "afr") {
    rawVal = (telemetry.afr !== undefined && telemetry.afr !== null) ? telemetry.afr : 14.7;
    displayStr = rawVal.toFixed(2);
    subStr = rawVal < 14.2 ? "RICH (POWER)" : (rawVal > 15.2 ? "LEAN (ECO)" : "STOICH (14.7)");
    pct = Math.max(0, Math.min(1, (rawVal - 10) / 10.0));
    color = "#69f0ae";
  } else if (sensorKey === "fuel_level") {
    rawVal = (telemetry.fuel_level_pct !== undefined && telemetry.fuel_level_pct !== null) ? telemetry.fuel_level_pct : 50;
    displayStr = Math.round(rawVal) + "%";
    subStr = rawVal < 15 ? "LOW FUEL" : "TANK LEVEL";
    pct = rawVal / 100.0;
    color = rawVal < 15 ? "#ff3344" : "#40c4ff";
  } else if (sensorKey === "ambient") {
    rawVal = (telemetry.ambient_temp_f !== undefined && telemetry.ambient_temp_f !== null) ? telemetry.ambient_temp_f : 72;
    displayStr = Math.round(rawVal) + "°F";
    subStr = "OUTSIDE AIR";
    pct = Math.max(0, Math.min(1, (rawVal - 20) / 100.0));
    color = "#ffd740";
  } else if (sensorKey === "pedal") {
    rawVal = (telemetry.pedal_pos_pct !== undefined && telemetry.pedal_pos_pct !== null) ? telemetry.pedal_pos_pct : 0;
    displayStr = Math.round(rawVal) + "%";
    subStr = "ACCEL PEDAL";
    pct = rawVal / 100.0;
    color = "#7c4dff";
  } else if (sensorKey === "runtime") {
    rawVal = (telemetry.engine_runtime_sec || 0) / 60.0;
    displayStr = rawVal < 60 ? Math.round(rawVal) + "m" : (rawVal / 60.0).toFixed(1) + "h";
    subStr = "RUN TIME";
    pct = Math.min(1.0, rawVal / 120.0);
    color = "#64ffda";
  } else if (sensorKey === "baro") {
    rawVal = (telemetry.baro_kpa !== undefined && telemetry.baro_kpa !== null) ? telemetry.baro_kpa : 101.3;
    displayStr = Math.round(rawVal) + " kPa";
    subStr = "BAROMETRIC";
    pct = Math.max(0, Math.min(1, (rawVal - 60) / 50.0));
    color = "#ffab40";
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

  // Single-Greeting Boot Lifecycle: Check if neural AI engine is already warm
  fetch('/api/ai/status')
    .then(r => r.json())
    .then(data => {
      if (data && data.ai_core === 'online') {
        // AI Core is already warm in memory: deliver single rich neural greeting
        updateAiCoreStatus('online');
        fetch('/api/ai/greeting/official')
          .then(r => r.json())
          .then(neuralData => {
            if (neuralData && neuralData.greeting) {
              console.log(`[OFFICIAL NEURAL GREETING] "${neuralData.greeting}"`);
              if (typeof appendSpeechLogItem === 'function') {
                appendSpeechLogItem({
                  speech: neuralData.greeting,
                  source: 'NEURAL_BOOT',
                  persona: neuralData.persona,
                  emotion: neuralData.emotion || 'DEVOTED'
                });
              }
              showAiSpeechToast(neuralData.greeting);
              if (neuralData.emotion) setWaifuEmotion(neuralData.emotion);
            }
          })
          .catch(e => console.warn("[OFFICIAL GREETING] Note:", e));
      } else {
        // Cold boot: deliver fast instant greeting while neural engine warms up
        updateAiCoreStatus('warming');
        fetch('/api/ai/greeting/instant')
          .then(r => r.json())
          .then(instData => {
            if (instData && instData.greeting) {
              console.log(`[INSTANT BOOT GREETING] "${instData.greeting}"`);
              if (typeof appendSpeechLogItem === 'function') {
                appendSpeechLogItem({
                  speech: instData.greeting,
                  source: 'INSTANT_BOOT',
                  persona: instData.persona,
                  emotion: instData.emotion || 'HAPPY'
                });
              }
              showAiSpeechToast(instData.greeting);
              if (instData.emotion) setWaifuEmotion(instData.emotion);
            }
          })
          .catch(err => console.warn("[INSTANT GREETING] Note:", err));

        // When neural engine finishes warming, smoothly transition status without chattering a 2nd greeting!
        aiCoreCheckInterval = setInterval(() => {
          fetch('/api/ai/status')
            .then(r => r.json())
            .then(statusData => {
              if (statusData && statusData.ai_core === 'online') {
                clearInterval(aiCoreCheckInterval);
                updateAiCoreStatus('online');
                console.log("[AI CORE] Local neural engine is warm and ready for conversation.");
              }
            })
            .catch(e => {});
        }, 2000);
      }
    })
    .catch(() => {
      fetch('/api/ai/greeting/instant')
        .then(r => r.json())
        .then(data => {
          if (data && data.greeting) showAiSpeechToast(data.greeting);
        })
        .catch(e => {});
    });
}

function connectTelemetryStream() {
  if (eventSource) {
    eventSource.close();
  }

  eventSource = new EventSource('/stream');

  eventSource.onopen = function() {
    console.log("[STREAM] Connected to CarPi5 Telemetry Stream.");
    if (typeof resetPcSpeechStreamBaseline === 'function') resetPcSpeechStreamBaseline();
    dismissBootSplash();
    triggerStartupGreeting();
  };

  eventSource.onmessage = function(e) {
    const data = JSON.parse(e.data);
    if (data.circadian) {
      latestCircadian = data.circadian;
    }
    if (data.mood) {
      latestMood = data.mood;
      if (data.mood && data.mood.emotion && data.mood.emotion !== window._lastStreamMoodEmotion) {
        window._lastStreamMoodEmotion = data.mood.emotion;
        if (!isWaifuSpeaking && typeof setWaifuEmotion === 'function') {
          setWaifuEmotion(data.mood.emotion);
        }
      }
    if (data.pip) {
      handlePipConnectomeStream(data.pip);
    }
    }
    if (data.action) {
      handleAiAction(data.action);
    }
    if (data.is_speaking !== undefined) {
      isHardwareSpeaking = data.is_speaking;
    }
    if (data.speech_viseme && typeof vrmVisemeCtrl !== 'undefined' && vrmVisemeCtrl) {
      vrmVisemeCtrl.setSseTimeline(data.speech_viseme);
    }
    if (data.speech_seq !== undefined && typeof handleRemoteSpeechSeq === 'function') {
      handleRemoteSpeechSeq(data.speech_seq);
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
    if (data.gps) {
      updateGpsAndDragyUI(data.gps);
      if (typeof updateDragyStudioUI === 'function') {
        updateDragyStudioUI(data.gps, data.telemetry);
      }
    } else if (data.telemetry && typeof updateDragyStudioUI === 'function') {
      updateDragyStudioUI(null, data.telemetry);
    }
    if (typeof updateCanyonAndThermalUI === 'function') {
      updateCanyonAndThermalUI(data.thermal, data.lap_timer);
    }
    const t = data.telemetry;
    if (!t || !t.timestamp) return;

    latestTelemetry = t;
    // Phase 4: Live Virtual Dyno, MultiAir & Shift Quality Updates
    updateDynoBadgeUI(t);
    const maBadge = document.getElementById('multiairBadge');
    if (maBadge && t.multiair_status) {
      if (t.multiair_status === 'COLD_PROTECT') {
        maBadge.innerText = '❄️ MULTIAIR: COLD PROTECT';
        maBadge.style.color = '#38bdf8';
        maBadge.style.borderColor = 'rgba(56,189,248,0.5)';
      } else if (t.multiair_status === 'WARM_OPTIMAL') {
        maBadge.innerText = '🛡️ MULTIAIR: PRIMED';
        maBadge.style.color = 'var(--accent-green)';
        maBadge.style.borderColor = 'rgba(0,230,118,0.4)';
      } else if (t.multiair_status === 'THERMAL_ALERT') {
        maBadge.innerText = '🔥 MULTIAIR: OIL HOT';
        maBadge.style.color = '#ef4444';
        maBadge.style.borderColor = 'rgba(239,68,68,0.5)';
      }
    }
    const shiftBadge = document.getElementById('shiftScoreBadge');
    if (shiftBadge && t.last_shift_score !== null && t.last_shift_score !== undefined) {
      if (t.last_shift_score !== lastObservedShiftScore) {
        lastObservedShiftScore = t.last_shift_score;
        const typeLabel = (t.last_shift_type || 'SHIFT').replace(/_/g, ' ');
        shiftBadge.innerText = `🎯 ${typeLabel}: ${t.last_shift_score} PTS`;
        shiftBadge.style.display = 'inline-block';
        if (t.last_shift_score >= 90) {
          shiftBadge.style.color = 'var(--accent-green)';
          shiftBadge.style.borderColor = 'var(--accent-green)';
        } else if (t.last_shift_score >= 70) {
          shiftBadge.style.color = 'var(--accent-yellow)';
          shiftBadge.style.borderColor = 'var(--accent-yellow)';
        } else {
          shiftBadge.style.color = '#ef4444';
          shiftBadge.style.borderColor = '#ef4444';
        }
        if (shiftScoreFadeTimer) clearTimeout(shiftScoreFadeTimer);
        shiftScoreFadeTimer = setTimeout(() => {
          if (shiftBadge) shiftBadge.style.display = 'none';
        }, 5000);
      }
    }
    // Phase 2: Update Physical G-Force Coupling & Gauge Gaze Triggers
    const curSpeed = (t.speed !== undefined) ? t.speed : (t.speed_mph || 0);
    const curBoost = (t.boost_psi !== undefined) ? t.boost_psi : 0;
    const curSteer = (t.steering_angle !== undefined) ? t.steering_angle : 0;
    const curLatG = (t.lateral_accel !== undefined) ? t.lateral_accel : 0;
    if (typeof updateVrmInertiaPhysics === 'function') {
      updateVrmInertiaPhysics(curSpeed, curBoost, curSteer, curLatG);
    }

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

// --- AUDIBLE SHIFT CHIME & REDLINE HUD FLASH CONTROLLER ---
let lastShiftBeepTime = 0;
let audioCtxShift = null;

function triggerShiftTone(rpm) {
  const now = Date.now();
  if (now - lastShiftBeepTime < 550) return; // Debounce
  lastShiftBeepTime = now;
  try {
    if (!audioCtxShift) {
      const AudioCtx = window.AudioContext || window.webkitAudioContext;
      if (AudioCtx) audioCtxShift = new AudioCtx();
    }
    if (audioCtxShift && audioCtxShift.state === 'suspended') {
      audioCtxShift.resume();
    }
    if (audioCtxShift) {
      const osc = audioCtxShift.createOscillator();
      const gain = audioCtxShift.createGain();
      // High-pitched F1/Rally prompt tone: 2200Hz -> 2600Hz sweep
      osc.type = 'sine';
      osc.frequency.setValueAtTime(2200, audioCtxShift.currentTime);
      osc.frequency.exponentialRampToValueAtTime(2700, audioCtxShift.currentTime + 0.08);
      gain.gain.setValueAtTime(0.4, audioCtxShift.currentTime);
      gain.gain.exponentialRampToValueAtTime(0.001, audioCtxShift.currentTime + 0.12);
      osc.connect(gain);
      gain.connect(audioCtxShift.destination);
      osc.start();
      osc.stop(audioCtxShift.currentTime + 0.12);
    }
  } catch (e) {
    console.warn("[AUDIO] Shift chime error:", e);
  }
  // Visual Redline Flash on header and cluster
  const header = document.querySelector('.cluster-header');
  if (header) {
    header.classList.add('shift-redline-flash');
    setTimeout(() => header.classList.remove('shift-redline-flash'), 180);
  }
}
        // 2a. Audible Shift Chime & Redline Tach Warning (5,800+ RPM under load)
    if (t.rpm && t.rpm >= 5800 && t.gear !== 'N' && t.gear !== '〜') {
      triggerShiftTone(t.rpm);
    }
    // 2. Header F1 Lights & Gear Badge
    const gearEl = document.getElementById('gearBadge');
    if (gearEl) {
      if (t.gear === '⇄') {
        gearEl.innerHTML = '<span class="gear-shifting-anim">⇄</span>';
        gearEl.title = 'Shifting Gears';
        gearEl.style.borderColor = 'var(--accent-cyan, #00e5ff)';
      } else if (t.gear === '〜') {
        gearEl.innerHTML = '<span class="gear-coasting-anim">〜</span>';
        gearEl.title = 'Coasting in Neutral';
        gearEl.style.borderColor = 'var(--accent-yellow, #eab308)';
      } else {
        gearEl.innerText = t.gear;
        gearEl.title = `C635 Gear: ${t.gear}`;
        gearEl.style.borderColor = (t.gear === 'N') ? '#4a5568' : 'var(--accent-red, #ff3344)';
      }
    }

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
    const vehHubSpeed = document.getElementById('vehHubSpeedBadge');
    const vehHubBoost = document.getElementById('vehHubBoostBadge');
    if (vehHubSpeed) vehHubSpeed.innerText = `${Math.round(isKph ? t.speed_kph : t.speed_mph)} ${isKph ? 'KM/H' : 'MPH'}`;
    if (vehHubBoost) {
      vehHubBoost.innerText = t.is_in_boost ? `+${t.boost_psi.toFixed(1)} PSI` : `-${Math.round(t.vacuum_inhg)} inHg`;
      vehHubBoost.style.color = t.is_in_boost ? 'var(--accent-green)' : 'var(--accent-blue)';
    }
    }

    // 6. Update AI Telemetry Context
    const ctxSpeed = document.getElementById('contextSpeedGear');
    const ctxBoost = document.getElementById('contextBoost');
    const ctxCoolant = document.getElementById('contextCoolant');
    if (ctxSpeed) ctxSpeed.innerText = `${Math.round(t.speed_mph)} MPH (Gear ${t.gear})`;
    if (ctxBoost) ctxBoost.innerText = t.is_in_boost ? `+${t.boost_psi.toFixed(1)} PSI` : `-${Math.round(t.vacuum_inhg)} inHg`;
    if (ctxCoolant) ctxCoolant.innerText = `${Math.round(t.coolant_temp_f)}°F (${t.multiair_ready ? 'Ready' : 'Warming'})`;

    // 8. Auto-Dimming Headlight Obsidian Midnight Mode
    if (t.headlights_on !== undefined) {
      const mode = localStorage.getItem('carpi5_theme_mode') || 'AUTO';
      if (mode === 'AUTO') {
        if (t.headlights_on) {
          document.body.classList.add('cockpit-night-mode');
          document.body.classList.add('obsidian-midnight');
          const badge = document.getElementById('themeModeBadge');
          if (badge) {
            badge.innerText = 'AUTO (HEADLIGHTS • OBSIDIAN)';
            badge.style.borderColor = 'var(--accent-blue)';
            badge.style.color = 'var(--accent-blue)';
          }
        } else {
          const isNight = (vrmCelestialPhase === 'NIGHT' || vrmCelestialPhase === 'CIVIL_DUSK' || vrmCelestialPhase === 'CIVIL_DAWN');
          if (!isNight) {
            document.body.classList.remove('cockpit-night-mode');
            document.body.classList.remove('obsidian-midnight');
            const badge = document.getElementById('themeModeBadge');
            if (badge) {
              badge.innerText = 'AUTO (SOLAR)';
              badge.style.borderColor = 'var(--accent-yellow)';
              badge.style.color = 'var(--accent-yellow)';
            }
          }
        }
      }
    }
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
      const shouldDuck = (data.audio_duck !== undefined) ? data.audio_duck : data.is_speaking;
      setMediaDuckState(shouldDuck);
      isHardwareSpeaking = data.is_speaking;
      const stage = document.getElementById('waifuStage');
      if (stage) {
        if (isWaifuSpeaking) stage.classList.add('speaking');
        else stage.classList.remove('speaking');
      }
      const vrmPill = document.getElementById('vrmMinHudPill');
      if (vrmPill) {
        if (isWaifuSpeaking) vrmPill.classList.add('speaking');
        else vrmPill.classList.remove('speaking');
      }
      const mini = document.getElementById('vrmMiniBubble');
      if (mini) {
        if (isWaifuSpeaking) mini.classList.add('talking');
        else mini.classList.remove('talking');
      }
      if (data.is_speaking && currentScreen !== 'ai' && !window.isCompanionMinimizedByUser) {
        handleSpeechAutoShotgun(null, 4500);
      } else if (wasSpeaking && !data.is_speaking) {
        scheduleShotgunAutoDismiss(2800);
      }
    }

    // 9. AI Voice Toast Banner, Real-Time Event Log & Choreographed Emote Sync
    if (data.ai_event) {
      appendSpeechLogItem(data.ai_event);
      if (data.ai_event.emotion) {
        setWaifuEmotion(data.ai_event.emotion);
      }
      if (typeof triggerChoreographedEmote === 'function' && (data.ai_event.beats || data.ai_event.emote_clip || data.ai_event.facial_preset)) {
        const spLen = (data.ai_event.speech || '').length;
        const estDurMs = Math.max(2400, (spLen / 10.0) * 1000);
        triggerChoreographedEmote(data.ai_event, estDurMs);
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
    mpg: (t.speed_mph || 0) < 2.0 ? (t.fuel_gph || 0.25) : (t.fuel_mpg_instant || 0),
    load: t.engine_load_pct || 0,
    timing: t.timing_advance_deg || 0,
    afr: t.afr || 0,
    fuel_level: t.fuel_level_pct || 0,
    ambient: t.ambient_temp_f || 0,
    pedal: t.pedal_pos_pct || 0,
    runtime: (t.engine_runtime_sec || 0) / 60.0,
    baro: t.baro_kpa || 0
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
    baseVal = t ? ((t.speed_mph || 0) < 2.0 ? (t.fuel_gph || 0.25) : (t.fuel_mpg_instant || 28.5)) : 28.5;
  } else if (sensorKey === "load") {
    baseVal = t ? (t.engine_load_pct || 25) : 25;
  } else if (sensorKey === "timing") {
    baseVal = t ? (t.timing_advance_deg || 5) : 5;
  } else if (sensorKey === "afr") {
    baseVal = t ? (t.afr || 14.7) : 14.7;
  } else if (sensorKey === "fuel_level") {
    baseVal = t ? (t.fuel_level_pct || 65) : 65;
  } else if (sensorKey === "ambient") {
    baseVal = t ? (t.ambient_temp_f || 75) : 75;
  } else if (sensorKey === "pedal") {
    baseVal = t ? (t.pedal_pos_pct || 0) : 0;
  } else if (sensorKey === "runtime") {
    baseVal = t ? ((t.engine_runtime_sec || 0) / 60.0) : 15;
  } else if (sensorKey === "baro") {
    baseVal = t ? (t.baro_kpa || 101.3) : 101.3;
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
  [1, 2, 3, 4, 6, 8, 12].forEach(n => {
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
  try {
    localStorage.setItem('carpi5_layout', currentLayout);
    localStorage.setItem('carpi5_slots', JSON.stringify(currentSlots));
  } catch (e) {}
  initGaugeGrid();
  closeConfigModal();
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
        folderPath: "~/Pictures",
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

// --- 12. GENERAL PLACEHOLDER MODAL ---

function showPlaceholderModal(title, desc) {
  document.getElementById('modalTitle').innerText = title;
  document.getElementById('modalDesc').innerText = desc;
  document.getElementById('modalOverlay').style.display = 'flex';
}

function closePlaceholderModal() {
  document.getElementById('modalOverlay').style.display = 'none';
}

// --- 13. CLOCK & INITIALIZATION ---

function updateSystemClock() {
  const now = new Date();
  const timeStr = formatClockTime(now, false);
  const timeSecStr = formatClockTime(now, true);
  const headerClock = document.getElementById('headerClock');
  if (headerClock) headerClock.innerText = timeStr;
  const footerClock = document.getElementById('footerClock');
  if (footerClock) footerClock.innerText = timeStr;
  const scClock = document.getElementById('screensaverClock');
  if (scClock) scClock.innerText = timeSecStr;
}

// Enhanced Universal Kinetic Touch Drag-to-Scroll for Touchscreens

function initTouchScrollEngine() {
  const scrollTargets = document.querySelectorAll(
    '.screen-view, #screenSettings, #screenHome, #screenMedia, #screenGames, #screenLibrary, #screenVehicle, #screenHardware, #screenMaintenance, .maint-items-list, .maint-results-list, ' +
    '.hw-studio-container, .win11-drive-container, .win11-viewport-content, #explorerFileList, .win11-sidebar, #libraryMarkdownContainer, #libraryReaderView, #libraryShelfView, ' +
    '#gpioBoardPinsContainer, #romsGrid, #romsListContainer, #fileListGrid, .explorer-body, .explorer-tree, .ai-chat-messages, #aiChatMessages, ' +
    '#animGridContainer, #tripsListContainer, .trip-detail-panel, #recentTripsTableContainer, #diagCodesList, .diag-detail-panel, #trackListContainer, ' +
    '#fullAudioSuiteEqGrid, #mediaTrackList, .music-playlist-panel, #dashcamClipsList, #wifiNetworkList, #btDeviceList, .device-tabs-row, #animCategoriesBar, .media-container, .settings-container, ' +
    '.speech-log-list, .diag-memory-box, .app-drawer-grid'
  );
  scrollTargets.forEach(el => {
    if (!el || el.dataset.touchScrollInit) return;
    el.dataset.touchScrollInit = 'true';
    let isDown = false;
    let isDragging = false;
    let startY = 0;
    let startX = 0;
    let startScrollTop = 0;
    let startScrollLeft = 0;
    let lastY = 0;
    let velocityY = 0;
    let lastTime = 0;
    let animFrame = null;
    el.addEventListener('pointerdown', (e) => {
      // Don't intercept text inputs, sliders, or select dropdowns
      if (['INPUT', 'SELECT', 'TEXTAREA'].includes(e.target.tagName)) return;
      isDown = true;
      isDragging = false;
      startY = e.clientY;
      startX = e.clientX;
      lastY = e.clientY;
      startScrollTop = el.scrollTop;
      startScrollLeft = el.scrollLeft;
      lastTime = performance.now();
      velocityY = 0;
      if (animFrame) cancelAnimationFrame(animFrame);
    }, { passive: true });

    window.addEventListener('pointermove', (e) => {
      if (!isDown) return;
      const dy = startY - e.clientY;
      const dx = startX - e.clientX;
      // Threshold: if finger moved more than 6px, engage dragging!
      if (!isDragging && (Math.abs(dy) > 6 || Math.abs(dx) > 6)) {
        isDragging = true;
      }
      if (isDragging) {
        if (el.scrollHeight > el.clientHeight) {
          el.scrollTop = startScrollTop + dy;
        }
        if (el.scrollWidth > el.clientWidth) {
          el.scrollLeft = startScrollLeft + dx;
        }
        const now = performance.now();
        const dt = now - lastTime;
        if (dt > 8) {
          velocityY = (lastY - e.clientY) / dt;
          lastY = e.clientY;
          lastTime = now;
        }
      }
    }, { passive: true });
    const endDrag = (e) => {
      if (!isDown) return;
      isDown = false;
      if (isDragging) {
        // Intercept and prevent the upcoming click event on child buttons/cards!
        const blockClick = (ev) => {
          ev.stopImmediatePropagation();
          ev.preventDefault();
          window.removeEventListener('click', blockClick, true);
        };
        window.addEventListener('click', blockClick, true);
        // Kinetic momentum fling deceleration
        if (Math.abs(velocityY) > 0.08) {
          let currentVel = velocityY * 16;
          const step = () => {
            if (Math.abs(currentVel) < 0.25) return;
            el.scrollTop += currentVel;
            currentVel *= 0.92; // Natural momentum friction
            animFrame = requestAnimationFrame(step);
          };
          animFrame = requestAnimationFrame(step);
        }
      }
    };

    window.addEventListener('pointerup', endDrag, { passive: true });
    window.addEventListener('pointercancel', endDrag, { passive: true });
  });
}
// Re-attach touch swipe scroller periodically so dynamically loaded DOM is always swipeable
setTimeout(initTouchScrollEngine, 300);
setInterval(initTouchScrollEngine, 1500);
initBootSplash();

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

function playCreatorTribute() {
  setWaifuEmotion("DEVOTED");
  const p = (typeof getActivePersonaData === 'function') ? getActivePersonaData() : {};
  const sysEv = p.system_events || {};
  const fallbackSpeech = "This cockpit was crafted with love to ride shotgun in the Dodge Dart 1.4L Turbo!";
  const speech = (typeof formatPersonaText === 'function')
    ? formatPersonaText(sysEv.creator_tribute || fallbackSpeech)
    : fallbackSpeech;
  showAiSpeechToast(speech);
  speakUtterance(speech, "DEVOTED", "SYSTEM");
}

// --- SETTINGS ACCORDION INTERACTION ---

function toggleAccordion(accId) {
  if (isTouchScrolling || touchScrollDistance > 8) return;
  const group = document.getElementById(accId);
  if (!group) return;
  group.classList.toggle('active');
}

function toggleDynoPeakView() {
  showDynoPeak = !showDynoPeak;
  updateDynoBadgeUI();
}

function updateDynoBadgeUI(telemetryData) {
  const badge = document.getElementById('dynoBadge');
  if (!badge) return;
  const t = telemetryData || latestTelemetry || {};
  const curWhp = Math.round(t.virtual_whp || 0);
  const curWtq = Math.round(t.virtual_wtq || 0);
  const peakWhp = Math.round(t.peak_whp || 0);
  const peakWtq = Math.round(t.peak_wtq || 0);
  if (showDynoPeak && peakWhp > 0) {
    badge.innerText = `⚡ PEAK: ${peakWhp} WHP • ${peakWtq} WTQ`;
    badge.style.color = '#ff4081';
    badge.style.borderColor = '#ff4081';
  } else {
    badge.innerText = `⚡ DYNO: ${curWhp} WHP • ${curWtq} WTQ`;
    badge.style.color = 'var(--accent-pink)';
    badge.style.borderColor = 'rgba(255,64,129,0.4)';
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

  // If URL is external (Google, YouTube, Dart Forum), route through proxy to bypass X-Frame-Options

  let targetSrc = url;

  if (!url.startsWith('http://localhost') && !url.startsWith('/') && !url.startsWith('about:')) {

    targetSrc = '/api/browser/proxy?url=' + encodeURIComponent(url);

  }

  if (iframe) iframe.src = targetSrc;

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

// ============================================================================

// --- SETTINGS CATEGORY TABS & DYNAMIC AUDIO ROUTING ---

// ============================================================================

function switchSettingsCategory(catId) {

  const tabs = {

    ai: document.getElementById('tabSetCatAi'),

    audio: document.getElementById('tabSetCatAudio'),

    vehicle: document.getElementById('tabSetCatVehicle'),

    conn: document.getElementById('tabSetCatConn'),

    theme: document.getElementById('tabSetCatTheme'),

    system: document.getElementById('tabSetCatSystem')

  };

  Object.keys(tabs).forEach(k => {

    if (tabs[k]) {

      if (k === catId) tabs[k].classList.add('active');

      else tabs[k].classList.remove('active');

    }

  });

  const accs = {

    ai: document.getElementById('accAiGroup'),

    audio: document.getElementById('accSystemGroup'),

    vehicle: document.getElementById('accPowertrainGroup'),

    conn: document.getElementById('accSystemGroup'),

    theme: document.getElementById('accSystemGroup'),

    system: document.getElementById('accAboutGroup')

  };

  Object.values(accs).forEach(el => {

    if (el) el.classList.remove('active');

  });

  if (accs[catId]) {

    accs[catId].classList.add('active');

  }

  if (catId === 'audio') {

    loadDynamicAudioDevices();

    const c = document.getElementById('cardDynamicAudio');

    if (c) c.scrollIntoView({ behavior: 'smooth', block: 'nearest' });

  }

}

// --- PHASE 3: HOME SCREEN CARDS TOUCH REORDER ENGINE ---

function initHomeCardsTouchReorder() {

  const grid = document.querySelector('#screenHome .home-cards-grid');

  if (!grid || grid._reorderInitialized) return;

  grid._reorderInitialized = true;

  // Restore saved card order

  applySavedHomeCardOrder(grid);

  let draggedCard = null;

  let touchHoldTimer = null;

  let isReordering = false;

  grid.querySelectorAll('.launcher-card').forEach(card => {

    card.setAttribute('draggable', 'true');

    // Drag and Drop (Mouse / Touch)

    card.addEventListener('dragstart', (e) => {

      draggedCard = card;

      card.classList.add('dragging-card');

      e.dataTransfer.effectAllowed = 'move';

    });

    card.addEventListener('dragend', () => {

      if (draggedCard) draggedCard.classList.remove('dragging-card');

      grid.querySelectorAll('.launcher-card').forEach(c => c.classList.remove('drag-over'));

      draggedCard = null;

      saveHomeCardOrder(grid);

    });

    card.addEventListener('dragover', (e) => {

      e.preventDefault();

      if (!draggedCard || draggedCard === card) return;

      card.classList.add('drag-over');

    });

    card.addEventListener('dragleave', () => {

      card.classList.remove('drag-over');

    });

    card.addEventListener('drop', (e) => {

      e.preventDefault();

      card.classList.remove('drag-over');

      if (draggedCard && draggedCard !== card) {

        const cards = Array.from(grid.children);

        const fromIdx = cards.indexOf(draggedCard);

        const toIdx = cards.indexOf(card);

        if (fromIdx < toIdx) {

          card.after(draggedCard);

        } else {

          card.before(draggedCard);

        }

        saveHomeCardOrder(grid);

      }

    });

  });

}

function saveHomeCardOrder(grid) {

  const cards = Array.from(grid.querySelectorAll('.launcher-card'));

  const cardIdentifiers = cards.map(c => {

    const titleEl = c.querySelector('.card-title');

    return titleEl ? titleEl.innerText.trim() : c.className;

  });

  localStorage.setItem('carpi5_home_card_order', JSON.stringify(cardIdentifiers));

}

function applySavedHomeCardOrder(grid) {

  try {

    const saved = localStorage.getItem('carpi5_home_card_order');

    if (!saved) return;

    const order = JSON.parse(saved);

    if (!Array.isArray(order) || order.length === 0) return;

    const cards = Array.from(grid.querySelectorAll('.launcher-card'));

    const cardMap = {};

    cards.forEach(c => {

      const titleEl = c.querySelector('.card-title');

      const key = titleEl ? titleEl.innerText.trim() : c.className;

      cardMap[key] = c;

    });

    order.forEach(key => {

      if (cardMap[key]) {

        grid.appendChild(cardMap[key]);

      }

    });

  } catch (e) {

    console.warn("[HOME REORDER] Order restore error:", e);

  }

}

// Phase 3 Initialization Hook

window.addEventListener('DOMContentLoaded', () => {

  if (typeof initVrmControlsBarState === 'function') initVrmControlsBarState();

  if (typeof initHomeCardsTouchReorder === 'function') initHomeCardsTouchReorder();

});

setTimeout(() => {

  if (typeof initVrmControlsBarState === 'function') initVrmControlsBarState();

  if (typeof initHomeCardsTouchReorder === 'function') initHomeCardsTouchReorder();

}, 600);

// --- BOOT INITIALIZATION SEQUENCE ---
updateSystemClock();
setInterval(updateSystemClock, 1000);

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

// Hook into initial page startup
fetchSystemHealth();
setInterval(fetchSystemHealth, 3000);
fetchRelaysStatus();
fetchRomsList();
fetchTripLogs();

// Initialize Talking Head, Kinetic Touch Scrolling, and Brightness
// [OBSOLETE 2D FACE - DORMANT CODE] initWaifuTalkingHead();
const savedBrightness = localStorage.getItem('carpi5_brightness') || 100;
updateBrightnessFromSlider(savedBrightness);
const btnClock = document.getElementById('btnClockFormat');
if (btnClock) btnClock.innerText = is24HourClock ? "CLOCK: 24-HOUR (MILITARY)" : "CLOCK: 12-HOUR (AM/PM)";
['aiChatMessages', 'speechLogList', 'filesListView', 'screenSettings', 'screenGames'].forEach(id => {
  enableKineticTouchScroll(document.getElementById(id));
});

// Fetch available neural brains on startup
fetchAvailableNeuralBrains();
checkGoogleAuthStatus();
setTimeout(dismissBootSplash, 800);
