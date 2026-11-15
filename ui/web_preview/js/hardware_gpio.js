// CarPi5 UI Module: SBC Hardware Specs, Pi 3 Monitor, ROMs & GPIO/Relay Studio

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
      // Pi 5 hardware metrics updated successfully
    })
    .catch(err => console.warn("[SBC] Health fetch error:", err));
}
let currentSbcTab = 'PI5';
let latestPi3Health = null;

function switchSbcTab(tab) {
  currentSbcTab = (tab || 'PI5').toUpperCase();
  const p5 = document.getElementById('panePi5Health');
  const p3 = document.getElementById('panePi3Health');
  const btn5 = document.getElementById('tabBtnPi5');
  const btn3 = document.getElementById('tabBtnPi3');
  const title = document.getElementById('sbcModalTitle');
  if (currentSbcTab === 'PI5') {
    if (p5) p5.style.display = 'block';
    if (p3) p3.style.display = 'none';
    if (btn5) {
      btn5.style.background = 'var(--accent-pink, #ff4081)';
      btn5.style.color = '#fff';
    }
    if (btn3) {
      btn3.style.background = 'transparent';
      btn3.style.color = 'var(--text-secondary, #8c9ba5)';
    }
    if (title) title.innerText = 'RASPBERRY PI 5 (COCKPIT HOST)';
    fetchSystemHealth();
  } else {
    if (p5) p5.style.display = 'none';
    if (p3) p3.style.display = 'block';
    if (btn3) {
      btn3.style.background = 'var(--accent-cyan, #00e5ff)';
      btn3.style.color = '#000';
    }
    if (btn5) {
      btn5.style.background = 'transparent';
      btn5.style.color = 'var(--text-secondary, #8c9ba5)';
    }
    if (title) title.innerText = 'RASPBERRY PI 3 (DASHCAM COPROCESSOR)';
    fetchPi3Health();
  }
}

function fetchPi3Health() {
  fetch('/api/dashcam/api/status')
    .then(r => r.json())
    .then(d => {
      latestPi3Health = d;
      if (!d || !d.online) return;
      const hw = d.hardware || {};
      const mTemp = document.getElementById('modalPi3Temp');
      const mTempF = document.getElementById('modalPi3TempF');
      const mCpu = document.getElementById('modalPi3Cpu');
      const mRam = document.getElementById('modalPi3Ram');
      const mRamPct = document.getElementById('modalPi3RamPct');
      const mUptime = document.getElementById('modalPi3Uptime');
      const mStatus = document.getElementById('modalPi3StatusMsg');
      const mDiskText = document.getElementById('modalPi3DiskText');
      const mDiskBar = document.getElementById('modalPi3DiskBar');
      if (mTemp && hw.temp_c != null) mTemp.innerText = `${hw.temp_c.toFixed(1)} °C`;
      if (mTempF && hw.temp_f != null) mTempF.innerText = `${hw.temp_f.toFixed(1)} °F`;
      if (mCpu && hw.cpu_pct != null) mCpu.innerText = `${Math.round(hw.cpu_pct)} %`;
      if (mRam && hw.ram_used_mb != null && hw.ram_total_mb != null) {
        mRam.innerText = `${hw.ram_used_mb} / ${hw.ram_total_mb} MB`;
      }
      if (mRamPct && hw.ram_pct != null) mRamPct.innerText = `${Math.round(hw.ram_pct)}% Used`;
      if (mUptime && hw.system_uptime) mUptime.innerText = hw.system_uptime;
      if (mStatus) {
        mStatus.innerText = d.recording ? "Recording Active" : "Camera Online (Idle Preview)";
        mStatus.style.color = d.recording ? "var(--accent-green)" : "var(--accent-cyan)";
      }
      if (d.disk) {
        if (mDiskText) mDiskText.innerText = `${d.disk.free_gb} GB Free / ${d.disk.total_gb} GB Total (${d.disk.used_percent}% Used)`;
        if (mDiskBar) mDiskBar.style.width = `${Math.min(100, Math.max(0, d.disk.used_percent))}%`;
      }
    })
    .catch(err => console.warn("[PI3] Health fetch error:", err));
}

function refreshSbcHealth() {
  fetchSystemHealth();
  fetchPi3Health();
}

function openSystemHealthModal() {
  const m = document.getElementById('sbcHealthModal');
  if (m) {
    m.style.display = 'flex';
    m.classList.add('open');
  }
  refreshSbcHealth();
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
    container.innerHTML = '<div style="color:var(--text-secondary); font-size:12px; padding:16px; grid-column:1/-1;">No ROMs found for this platform. Place ROM files in ~/Roms.</div>';
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

let activeGpioPinsList = [];
let selectedGpioPin = null;
const PIN_COLOR_MAP = {
  'power_5v':  '#ef4444',
  'power_3v3': '#f97316',
  'ground':    '#475569',
  'i2c':       '#00e5ff',
  'spi':       '#a855f7',
  'uart':      '#38bdf8',
  'pwm':       '#eab308',
  'gpio':      '#22c55e'
};

function getPinCategory(p) {
  if (p.name.includes('5V')) return 'power_5v';
  if (p.name.includes('3.3V')) return 'power_3v3';
  if (p.type === 'ground' || p.name.includes('Ground')) return 'ground';
  if (p.name.includes('SDA') || p.name.includes('SCL')) return 'i2c';
  if (p.name.includes('MOSI') || p.name.includes('MISO') || p.name.includes('SCLK') || p.name.includes('CE')) return 'spi';
  if (p.name.includes('TXD') || p.name.includes('RXD')) return 'uart';
  if (p.pwm || (p.name && p.name.includes('PWM'))) return 'pwm';
  return 'gpio';
}

function fetchGpioPins() {
  fetch('/api/gpio/pins')
    .then(r => r.json())
    .then(pins => {
      activeGpioPinsList = pins || [];
      renderGpioBoardStudio();
      if (!selectedGpioPin && activeGpioPinsList.length > 0) {
        // Default to BCM 17 (Pin 11) or first GPIO
        const def = activeGpioPinsList.find(p => p.bcm === 17) || activeGpioPinsList[10];
        selectGpioPinForInspector(def);
      } else if (selectedGpioPin) {
        const fresh = activeGpioPinsList.find(p => p.pin === selectedGpioPin.pin);
        if (fresh) selectGpioPinForInspector(fresh, true);
      }
    })
    .catch(err => console.warn('[GPIO] Pins fetch error:', err));
}

function renderGpioBoardStudio() {
  const grid = document.getElementById('gpioPinsGrid');
  if (!grid || !activeGpioPinsList.length) return;
  // Render dual-column physical header: Pins 1-40 (Odd left, Even right)
  let html = '';
  for (let i = 0; i < 20; i++) {
    const oddPin = activeGpioPinsList[i * 2];       // Pins 1, 3, 5...
    const evenPin = activeGpioPinsList[i * 2 + 1];  // Pins 2, 4, 6...
    [oddPin, evenPin].forEach(p => {
      if (!p) return;
      const cat = getPinCategory(p);
      const dotColor = PIN_COLOR_MAP[cat] || '#22c55e';
      const isSelected = selectedGpioPin && selectedGpioPin.pin === p.pin;
      const isGpio = p.bcm !== null;
      const stateBadge = p.state
        ? `<span style="font-size:9px; font-weight:900; color:#22c55e; background:rgba(34,197,94,0.18); padding:2px 6px; border-radius:4px;">HIGH</span>`
        : `<span style="font-size:9px; font-weight:800; color:#64748b; background:rgba(255,255,255,0.05); padding:2px 6px; border-radius:4px;">LOW</span>`;
      html += `

        <div onclick="onGpioPinClicked(${p.pin})" style="display:flex; align-items:center; justify-content:space-between; background:${isSelected ? 'rgba(34,197,94,0.12)' : '#0d131d'}; border:1.5px solid ${isSelected ? 'var(--accent-green)' : '#1a2333'}; border-radius:6px; padding:6px 10px; cursor:pointer; min-height:42px; transition:border-color 0.15s ease;">

          <div style="display:flex; align-items:center; gap:8px;">

            <span style="display:inline-block; width:12px; height:12px; border-radius:50%; background:${dotColor}; box-shadow:0 0 6px ${dotColor}; flex-shrink:0;"></span>

            <span style="font-size:10px; font-weight:900; color:#94a3b8; width:22px;">P${p.pin}</span>

            <div>

              <div style="font-size:11px; font-weight:800; color:#fff; line-height:1.2;">${p.name.split(' (')[0]}</div>

              <div style="font-size:9px; color:var(--text-secondary);">${p.bcm !== null ? `BCM ${p.bcm}` : cat.replace('_', ' ').toUpperCase()}</div>

            </div>

          </div>

          <div>${isGpio ? stateBadge : `<span style="font-size:8px; font-weight:800; color:#64748b;">${cat.toUpperCase()}</span>`}</div>

        </div>

      `;
    });
  }
  grid.innerHTML = html;
}

function onGpioPinClicked(pinNum) {
  const p = activeGpioPinsList.find(x => x.pin === pinNum);
  if (p) selectGpioPinForInspector(p);
}

function selectGpioPinForInspector(p, keepInputFocus = false) {
  selectedGpioPin = p;
  renderGpioBoardStudio();
  const numBadge = document.getElementById('inspPinNumBadge');
  const stateBadge = document.getElementById('inspPinStateBadge');
  const nameEl = document.getElementById('inspPinName');
  const descEl = document.getElementById('inspPinDesc');
  const toggleBtn = document.getElementById('btnToggleOutput');
  const labelInput = document.getElementById('inspPinLabelInput');
  if (numBadge) numBadge.innerText = `PIN ${p.pin}`;
  if (nameEl) nameEl.innerText = p.name;
  if (descEl) descEl.innerText = p.bcm !== null ? `BCM ${p.bcm} • ${p.type.toUpperCase()}` : p.type.toUpperCase();
  const isHigh = !!p.state;
  if (stateBadge) {
    stateBadge.innerText = isHigh ? 'STATE: HIGH (3.3V)' : 'STATE: LOW (0.0V)';
    stateBadge.style.color = isHigh ? 'var(--accent-green)' : '#94a3b8';
    stateBadge.style.background = isHigh ? 'rgba(34,197,94,0.2)' : '#1c2636';
  }
  if (toggleBtn) {
    toggleBtn.innerText = isHigh ? '🔴 TURN OFF (DRIVE LOW)' : '⚡ TURN ON (DRIVE HIGH)';
    toggleBtn.style.borderColor = isHigh ? '#ef4444' : '#22c55e';
    toggleBtn.style.color = isHigh ? '#ef4444' : '#22c55e';
  }
  // Load custom label if present
  if (labelInput && !keepInputFocus) {
    labelInput.value = localStorage.getItem(`carpi5_gpio_label_${p.pin}`) || '';
  }
  // Mode UI sync
  const curMode = p.mode || (p.pwm ? 'PWM' : 'OUT');
  updateInspectorModeUI(curMode);
}

function updateInspectorModeUI(mode) {
  const outSec = document.getElementById('inspOutputSection');
  const inSec = document.getElementById('inspInputSection');
  const pwmSec = document.getElementById('inspPwmSection');
  if (outSec) outSec.style.display = (mode === 'OUT') ? 'flex' : 'none';
  if (inSec) inSec.style.display = (mode === 'IN') ? 'flex' : 'none';
  if (pwmSec) pwmSec.style.display = (mode === 'PWM') ? 'flex' : 'none';
  ['btnModeOut', 'btnModeIn', 'btnModePwm'].forEach(id => {
    const b = document.getElementById(id);
    if (b) b.classList.remove('active');
  });
  if (mode === 'OUT') document.getElementById('btnModeOut')?.classList.add('active');
  else if (mode === 'IN') document.getElementById('btnModeIn')?.classList.add('active');
  else if (mode === 'PWM') document.getElementById('btnModePwm')?.classList.add('active');
}

function setPinModeFromInspector(mode) {
  if (!selectedGpioPin || selectedGpioPin.bcm === null) return;
  selectedGpioPin.mode = mode;
  updateInspectorModeUI(mode);
  showAiSpeechToast(`Set BCM ${selectedGpioPin.bcm} to ${mode}`);
}

function toggleSelectedPinState() {
  if (!selectedGpioPin || selectedGpioPin.bcm === null) return;
  toggleRelay(selectedGpioPin.bcm);
  setTimeout(fetchGpioPins, 120);
}

function pulseSelectedPin() {
  if (!selectedGpioPin || selectedGpioPin.bcm === null) return;
  fetch('/api/gpio/pulse', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ bcm: selectedGpioPin.bcm, duration: 0.5 })
  })
    .then(r => r.json())
    .then(() => {
      showAiSpeechToast(`Pulsed BCM ${selectedGpioPin.bcm} (0.5s)`);
      setTimeout(fetchGpioPins, 100);
      setTimeout(fetchGpioPins, 600);
    });
}

function onPwmSliderChange(val) {
  const text = document.getElementById('inspPwmValueText');
  if (text) text.innerText = `${val}%`;
  if (selectedGpioPin && selectedGpioPin.bcm !== null) {
    fetch('/api/gpio/pwm', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ bcm: selectedGpioPin.bcm, duty_cycle: parseFloat(val) / 100.0 })
    }).catch(err => console.warn('[GPIO] PWM send err:', err));
  }
}

function setPwmPreset(val) {
  const slider = document.getElementById('inspPwmSlider');
  if (slider) slider.value = val;
  onPwmSliderChange(val);
  if (selectedGpioPin && selectedGpioPin.bcm !== null) {
    showAiSpeechToast(`PWM BCM ${selectedGpioPin.bcm}: ${val}%`);
  }
}

function saveSelectedPinLabel() {
  if (!selectedGpioPin) return;
  const input = document.getElementById('inspPinLabelInput');
  if (input) {
    const val = input.value.trim();
    localStorage.setItem(`carpi5_gpio_label_${selectedGpioPin.pin}`, val);
    showAiSpeechToast(`Saved label: ${val || 'Default'}`);
  }
}

// ==========================================
// DUAL-SBC HARDWARE & PERIPHERALS STUDIO

// ==========================================
let hardwareStudioActive = false;
let hardwareStudioTimer = null;
let pi3AutoStreamTimer = null;
let pi3AutoStreamEnabled = false;

function startHardwareStudioLoop() {
  hardwareStudioActive = true;
  refreshDetailedHardwareSpecs(true);
  if (hardwareStudioTimer) clearInterval(hardwareStudioTimer);
  hardwareStudioTimer = setInterval(() => {
    if (hardwareStudioActive && currentScreen === 'hardware') {
      refreshDetailedHardwareSpecs(false);
    }
  }, 1600);
  if (pi3AutoStreamEnabled) {
    startPi3AutoStream();
  }
}

function stopHardwareStudioLoop() {
  hardwareStudioActive = false;
  if (hardwareStudioTimer) {
    clearInterval(hardwareStudioTimer);
    hardwareStudioTimer = null;
  }
  stopPi3AutoStream();
}

function startPi3AutoStream() {
  stopPi3AutoStream();
  refreshPi3HardwareStats(false);
  pi3AutoStreamTimer = setInterval(() => {
    if (hardwareStudioActive && pi3AutoStreamEnabled && currentScreen === 'hardware') {
      refreshPi3HardwareStats(false);
    }
  }, 2500);
}

function stopPi3AutoStream() {
  if (pi3AutoStreamTimer) {
    clearInterval(pi3AutoStreamTimer);
    pi3AutoStreamTimer = null;
  }
}

function togglePi3AutoStream(chk) {
  pi3AutoStreamEnabled = !!(chk && chk.checked);
  const badge = document.getElementById('hwPi3StatusBadge');
  if (pi3AutoStreamEnabled) {
    if (badge) {
      badge.textContent = 'AUTO-STREAMING (2.5s)';
      badge.className = 'hw-badge hw-badge-cyan';
    }
    startPi3AutoStream();
  } else {
    stopPi3AutoStream();
    if (badge) {
      badge.textContent = 'STANDBY / ON-DEMAND';
      badge.className = 'hw-badge hw-badge-yellow';
    }
  }
}

function refreshDetailedHardwareSpecs(force = false) {
  fetch('/api/system/detailed_specs')
    .then(r => r.json())
    .then(data => {
      // 1. Header Uptime
      const uptimePill = document.getElementById('hwUptimePill');
      if (uptimePill && data.uptime_str) {
        uptimePill.textContent = 'UPTIME: ' + data.uptime_str;
      }
      // 2. CPU Overall & Cores
      const cpu = data.cpu || {};
      const totalCpuBadge = document.getElementById('hwCpuTotalBadge');
      if (totalCpuBadge) {
        totalCpuBadge.textContent = 'OVERALL: ' + (cpu.total_pct || 0) + '%';
      }
      const cores = cpu.cores || [];
      cores.forEach((c) => {
        const id = c.id;
        const freqEl = document.getElementById(`hwCore${id}Freq`);
        const fillEl = document.getElementById(`hwCore${id}Fill`);
        const valEl = document.getElementById(`hwCore${id}Val`);
        if (freqEl) freqEl.textContent = (c.freq_ghz ? c.freq_ghz.toFixed(2) : '2.40') + ' GHz';
        if (fillEl) {
          const pct = Math.max(0, Math.min(100, c.pct || 0));
          fillEl.style.width = pct + '%';
          if (pct > 80) fillEl.style.background = 'var(--accent-red, #ef4444)';
          else if (pct > 55) fillEl.style.background = 'var(--accent-yellow, #eab308)';
          else fillEl.style.background = '#00f0ff';
        }
        if (valEl) valEl.textContent = (c.pct || 0).toFixed(1) + '%';
      });
      // 3. SoC Thermal & Voltage
      const soc = data.soc || {};
      const socTempEl = document.getElementById('hwSocTemp');
      const socTempFEl = document.getElementById('hwSocTempF');
      const coreVoltEl = document.getElementById('hwCoreVolt');
      const underVoltEl = document.getElementById('hwUnderVolt');
      const throttleBadge = document.getElementById('hwThrottleBadge');
      if (socTempEl && soc.temp_c != null) socTempEl.textContent = soc.temp_c.toFixed(1) + ' °C';
      if (socTempFEl && soc.temp_f != null) socTempFEl.textContent = soc.temp_f.toFixed(1) + ' °F';
      if (coreVoltEl && soc.voltage_v != null) coreVoltEl.textContent = soc.voltage_v.toFixed(4) + ' V';
      if (underVoltEl) {
        underVoltEl.textContent = soc.under_voltage ? 'LOW VOLTAGE' : 'NOMINAL';
        underVoltEl.style.color = soc.under_voltage ? '#ef4444' : '#10b981';
      }
      if (throttleBadge) {
        if (soc.is_throttled) {
          throttleBadge.textContent = 'THERMAL THROTTLED';
          throttleBadge.className = 'hw-badge hw-badge-red';
        } else if (soc.under_voltage) {
          throttleBadge.textContent = 'UNDER-VOLTAGE';
          throttleBadge.className = 'hw-badge hw-badge-yellow';
        } else {
          throttleBadge.textContent = (soc.throttled_hex || '0x0') + ' NOMINAL';
          throttleBadge.className = 'hw-badge hw-badge-green';
        }
      }
      // 4. VideoCore VII GPU
      const gpu = data.gpu || {};
      const v3dEl = document.getElementById('hwGpuV3dClock');
      const gpuCoreEl = document.getElementById('hwGpuCoreClock');
      const gpuMemEl = document.getElementById('hwGpuMem');
      if (v3dEl) v3dEl.textContent = (gpu.v3d_clock_mhz || 960) + ' MHz';
      if (gpuCoreEl) gpuCoreEl.textContent = (gpu.core_clock_mhz || 910) + ' MHz';
      if (gpuMemEl) gpuMemEl.textContent = (gpu.gpu_mem_mb || 8) + ' MB';
      // 5. Hailo-10H NPU Accelerator
      const npu = data.npu || {};
      const npuBadge = document.getElementById('hwNpuStatusBadge');
      const npuTops = document.getElementById('hwNpuTops');
      const npuRam = document.getElementById('hwNpuRam');
      const npuLive = document.getElementById('hwNpuLive');
      const npuNode = document.getElementById('hwNpuNode');
      if (npuBadge) {
        npuBadge.textContent = npu.detected ? 'NPU ACTIVE • 40 TOPS' : 'SLOT READY • M.2 HAT+';
        npuBadge.className = npu.detected ? 'hw-badge hw-badge-green' : 'hw-badge hw-badge-purple';
      }
      if (npuTops) npuTops.textContent = npu.tops_capacity || '40 TOPS';
      if (npuRam) npuRam.textContent = npu.onboard_ram || '8 GB';
      if (npuLive) {
        npuLive.textContent = npu.detected ? 'ONLINE (ACTIVE)' : 'READY / UNPOPULATED';
        npuLive.style.color = npu.detected ? '#10b981' : '#fbbf24';
      }
      if (npuNode && npu.nodes && npu.nodes.length) {
        npuNode.textContent = npu.nodes[0];
      }
      // 6. Memory & Storage
      const ram = data.ram || {};
      const ramText = document.getElementById('hwRamText');
      const ramFill = document.getElementById('hwRamFill');
      if (ramText) ramText.textContent = `${ram.used_mb || 0} MB / ${ram.total_mb || 8058} MB (${(ram.pct || 0).toFixed(1)}%)`;
      if (ramFill) ramFill.style.width = Math.min(100, ram.pct || 0) + '%';
      const swapText = document.getElementById('hwSwapText');
      const swapFill = document.getElementById('hwSwapFill');
      if (swapText) swapText.textContent = `${ram.swap_used_mb || 0} MB / ${ram.swap_total_mb || 2047} MB (${(ram.swap_pct || 0).toFixed(1)}%)`;
      if (swapFill) swapFill.style.width = Math.min(100, ram.swap_pct || 0) + '%';
      const st = data.storage || {};
      const stText = document.getElementById('hwStorageText');
      const stFill = document.getElementById('hwStorageFill');
      if (stText) stText.textContent = `${st.used_gb || 0} GB / ${st.total_gb || 0} GB (${(st.pct || 0).toFixed(1)}%)`;
      if (stFill) stFill.style.width = Math.min(100, st.pct || 0) + '%';
      // 7. Peripherals List
      const periph = data.peripherals || {};
      const periphList = document.getElementById('hwPeriphList');
      if (periphList && periph.usb_devices && periph.usb_devices.length) {
        let itemsHtml = '';
        periph.usb_devices.forEach(u => {
          itemsHtml += `<div class="hw-periph-item"><span class="hw-periph-tag">USB</span><span class="hw-periph-name">${u}</span></div>`;
        });
        itemsHtml += `<div class="hw-periph-item"><span class="hw-periph-tag">PCIe</span><span class="hw-periph-name">Raspberry Pi RP1 PCIe 2.0 Southbridge Controller</span></div>`;
        if (periph.interfaces) {
          periph.interfaces.forEach(net => {
            itemsHtml += `<div class="hw-periph-item"><span class="hw-periph-tag" style="border-color:#3b82f6; color:#60a5fa;">NET</span><span class="hw-periph-name">${net.name}: ${net.ip} (${net.speed_mbps || 100} Mbps)</span></div>`;
          });
        }
        periphList.innerHTML = itemsHtml;
      }
    })
    .catch(err => {
      console.warn('[HW_STUDIO] Failed fetching specs:', err);
    });
}

function refreshPi3HardwareStats(force = false) {
  const btn = document.getElementById('btnRefreshPi3');
  const badge = document.getElementById('hwPi3StatusBadge');
  const notice = document.getElementById('hwPi3Notice');
  if (btn) btn.textContent = '⏳ QUERYING...';
  fetch('/api/system/pi3_hardware')
    .then(r => r.json())
    .then(data => {
      if (btn) btn.textContent = '🔄 REFRESH PI 3 STATS';
      if (data.connected && data.status === 'ONLINE') {
        if (badge) {
          badge.textContent = `ONLINE (${data.host || '10.0.0.2'})`;
          badge.className = 'hw-badge hw-badge-green';
        }
        const hw = data.hardware || {};
        const elCpu = document.getElementById('hwPi3Cpu');
        const elLoad = document.getElementById('hwPi3Load');
        const elTemp = document.getElementById('hwPi3Temp');
        const elTempF = document.getElementById('hwPi3TempF');
        const elRam = document.getElementById('hwPi3Ram');
        const elRamPct = document.getElementById('hwPi3RamPct');
        const elCam = document.getElementById('hwPi3Camera');
        const elRec = document.getElementById('hwPi3Rec');
        if (elCpu) elCpu.textContent = (hw.cpu_pct != null ? hw.cpu_pct.toFixed(1) + '%' : '--');
        if (elLoad) elLoad.textContent = '1m Load: ' + (hw.load_1m != null ? hw.load_1m.toFixed(2) : '--');
        if (elTemp) elTemp.textContent = (hw.temp_c != null ? hw.temp_c.toFixed(1) + ' °C' : '--');
        if (elTempF) elTempF.textContent = (hw.temp_f != null ? hw.temp_f.toFixed(1) + ' °F' : '--');
        if (elRam) elRam.textContent = (hw.ram_used_mb != null ? `${hw.ram_used_mb} / ${hw.ram_total_mb} MB` : '--');
        if (elRamPct) elRamPct.textContent = (hw.ram_pct != null ? `${hw.ram_pct}% Utilized` : '1 GB LPDDR2');
        if (elCam) elCam.textContent = data.recording ? '🔴 RECORDING' : 'READY';
        if (elRec) elRec.textContent = `Clips: ${data.clip_count != null ? data.clip_count : (data.disk && data.disk.clip_count ? data.disk.clip_count : '--')}`;
        if (notice) notice.innerHTML = `✅ <b>Connected:</b> ${data.model || 'Raspberry Pi 3 Model B'} on ${data.host}. Telemetry refreshed at ${data.last_updated}.`;
      } else {
        if (badge) {
          badge.textContent = 'OFFLINE / STANDBY';
          badge.className = 'hw-badge hw-badge-yellow';
        }
        const elCpu = document.getElementById('hwPi3Cpu');
        const elTemp = document.getElementById('hwPi3Temp');
        const elRam = document.getElementById('hwPi3Ram');
        const elCam = document.getElementById('hwPi3Camera');
        if (elCpu) elCpu.textContent = 'OFFLINE';
        if (elTemp) elTemp.textContent = 'STANDBY';
        if (elRam) elRam.textContent = 'STANDBY';
        if (elCam) elCam.textContent = 'OFFLINE';
        if (notice) notice.innerHTML = `⚠️ <b>${data.message || 'Pi 3 Co-Processor not reachable on direct Ethernet (10.0.0.2).'}</b> (Single-shot query completed without consuming bus bandwidth).`;
      }
    })
    .catch(err => {
      if (btn) btn.textContent = '🔄 REFRESH PI 3 STATS';
      if (badge) {
        badge.textContent = 'OFFLINE';
        badge.className = 'hw-badge hw-badge-yellow';
      }
      if (notice) notice.textContent = 'Failed connecting to Pi 3 co-processor proxy: ' + err.message;
    });
}

window.startHardwareStudioLoop = startHardwareStudioLoop;

window.stopHardwareStudioLoop = stopHardwareStudioLoop;

window.refreshDetailedHardwareSpecs = refreshDetailedHardwareSpecs;

window.refreshPi3HardwareStats = refreshPi3HardwareStats;

window.togglePi3AutoStream = togglePi3AutoStream;
