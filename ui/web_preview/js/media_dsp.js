// CarPi5 UI Module: Media Player, 10-Band DSP Equalizer, Audio Routing, Launchers & Dashcam

function publishNowPlaying(status = 'playing') {
  if (!realPlaylist || realPlaylist.length === 0) return;
  const t = realPlaylist[realTrackIdx] || {};
  const dur = (realAudio.duration && !isNaN(realAudio.duration) && realAudio.duration > 0) ? realAudio.duration : (t.duration || 180);
  fetch('/api/media/now_playing', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      title: t.title || "Track",
      artist: t.artist || "Unknown Artist",
      album: t.album || "CarPi5 In-Dash",
      genre: t.genre || "In-Dash Audio",
      year: t.year || "2024",
      duration: dur,
      track_num: realTrackIdx + 1,
      total_tracks: realPlaylist.length,
      status: status
    })
  }).catch(() => {});
}

// ==========================================
// R.U.M. SMART AUDIO DUCKING & SUBWOOFER HUD

// ==========================================
let mediaPreDuckingVolume = null;
let duckingRampInterval = null;

function setMediaDuckState(isDucking) {
  if (typeof realAudio === 'undefined' || !realAudio) return;
  if (realAudio.paused && mediaPreDuckingVolume === null) return;
  clearInterval(duckingRampInterval);
  if (isDucking) {
    if (mediaPreDuckingVolume === null) {
      mediaPreDuckingVolume = realAudio.volume;
    }
    const targetVolume = Math.max(0.08, mediaPreDuckingVolume * 0.18);
    rampAudioVolume(targetVolume, 150);
  } else {
    if (mediaPreDuckingVolume !== null) {
      const restoreVolume = mediaPreDuckingVolume;
      mediaPreDuckingVolume = null;
      rampAudioVolume(restoreVolume, 350);
    }
  }
}

function rampAudioVolume(target, durationMs) {
  if (typeof realAudio === 'undefined' || !realAudio) return;
  const startVol = realAudio.volume;
  const startTime = Date.now();
  duckingRampInterval = setInterval(() => {
    const elapsed = Date.now() - startTime;
    const progress = Math.min(1.0, elapsed / durationMs);
    const current = startVol + (target - startVol) * (progress * (2 - progress));
    realAudio.volume = Math.max(0, Math.min(1, current));
    if (progress >= 1.0) {
      clearInterval(duckingRampInterval);
    }
  }, 25);
}
// Digital Subwoofer Gain & Peak Clipping Indicator
let currentSubGain = 0;
let clipAnalyser = null;
let isAntiClipEnabled = true;
try {
  const savedAnti = localStorage.getItem('carpi5_anticlip_enabled');
  if (savedAnti !== null) isAntiClipEnabled = (savedAnti === 'true');
} catch (e) {}
let autoClipLimiterNode = null;
let isSubsonicFilterActive = true;
try {
  const savedSub = localStorage.getItem('carpi5_subsonic_active');
  if (savedSub !== null) isSubsonicFilterActive = (savedSub === 'true');
} catch (e) {}
let subsonicFilter = null;
let currentSubBassFreq = 45;
try {
  const savedFreq = localStorage.getItem('carpi5_sub_freq');
  if (savedFreq) currentSubBassFreq = parseInt(savedFreq) || 45;
} catch (e) {}
let currentPlaybackSpeed = 1.0;
let isPitchLocked = true;
let clipMonitorStarted = false;
let lastClipAlertTime = 0;
const timeDomainBuffer = new Float32Array(256);

function onSubGainChange(val) {
  currentSubGain = parseFloat(val);
  const label = document.getElementById('subGainVal');
  if (label) {
    label.innerText = (currentSubGain >= 0 ? '+' : '') + currentSubGain.toFixed(1) + ' dB';
    if (currentSubGain > 6) {
      label.style.color = '#ff5252';
    } else if (currentSubGain > 0) {
      label.style.color = '#c084fc';
    } else {
      label.style.color = 'var(--text-secondary)';
    }
  }
  if (typeof subBassFilter !== 'undefined' && subBassFilter && typeof audioCtx !== 'undefined' && audioCtx) {
    try {
      subBassFilter.gain.setTargetAtTime(currentSubGain, audioCtx.currentTime, 0.02);
    } catch (e) {}
  }
}

function startClipMonitor() {
  if (clipMonitorStarted) return;
  clipMonitorStarted = true;

  function checkAudioClip() {
    if (clipAnalyser && typeof realAudio !== 'undefined' && realAudio && !realAudio.paused) {
      clipAnalyser.getFloatTimeDomainData(timeDomainBuffer);
      let peak = 0;
      for (let i = 0; i < timeDomainBuffer.length; i++) {
        const abs = Math.abs(timeDomainBuffer[i]);
        if (abs > peak) peak = abs;
      }
      const now = Date.now();
      if (peak >= 0.96) {
        lastClipAlertTime = now;
      }
      // Check real-time limiter reduction in dB
      let reduction = 0;
      if (typeof autoClipLimiterNode !== 'undefined' && autoClipLimiterNode && isAntiClipEnabled) {
        try {
          reduction = autoClipLimiterNode.reduction; // dB value <= 0
        } catch (e) {}
      }
      // Update Limiter Meter in Audio Suite if open
      const meterFill = document.getElementById('limiterMeterFill');
      const meterText = document.getElementById('limiterMeterText');
      if (meterFill && meterText) {
        const redDb = Math.abs(reduction);
        const pct = Math.min(100, (redDb / 12) * 100);
        meterFill.style.width = pct + '%';
        if (isAntiClipEnabled) {
          meterText.innerText = redDb > 0.1 ? `-${redDb.toFixed(1)} dB (LIMITING CLIPS)` : '0.0 dB (TRANSPARENT)';
          meterText.style.color = redDb > 0.1 ? '#00b0ff' : 'var(--text-secondary)';
        } else {
          meterText.innerText = 'BYPASSED (RAW SIGNAL)';
          meterText.style.color = '#ff5252';
        }
      }
      const badge = document.getElementById('subClipBadge');
      if (badge) {
        if (isAntiClipEnabled && reduction < -0.8) {
          badge.innerText = `🛡️ -${Math.abs(reduction).toFixed(0)}dB`;
          badge.style.background = 'rgba(0, 176, 255, 0.25)';
          badge.style.color = '#00b0ff';
          badge.style.borderColor = '#00b0ff';
          badge.style.boxShadow = '0 0 10px rgba(0, 176, 255, 0.6)';
        } else if (now - lastClipAlertTime < 350) {
          if (isAntiClipEnabled) {
            badge.innerText = '🛡️ CLAMP';
            badge.style.background = 'rgba(0, 230, 118, 0.25)';
            badge.style.color = 'var(--accent-green)';
            badge.style.borderColor = 'var(--accent-green)';
            badge.style.boxShadow = '0 0 10px rgba(0, 230, 118, 0.6)';
          } else {
            badge.innerText = '⚡ CLIP';
            badge.style.background = 'rgba(255, 23, 68, 0.4)';
            badge.style.color = '#ff1744';
            badge.style.borderColor = '#ff1744';
            badge.style.boxShadow = '0 0 12px rgba(255, 23, 68, 0.8)';
          }
        } else if (peak >= 0.82) {
          badge.innerText = 'WARM';
          badge.style.background = 'rgba(255, 171, 0, 0.2)';
          badge.style.color = '#ffab00';
          badge.style.borderColor = 'rgba(255, 171, 0, 0.4)';
          badge.style.boxShadow = 'none';
        } else {
          badge.innerText = 'CLEAN';
          badge.style.background = 'rgba(0, 230, 118, 0.15)';
          badge.style.color = 'var(--accent-green)';
          badge.style.borderColor = 'rgba(0, 230, 118, 0.3)';
          badge.style.boxShadow = 'none';
        }
      }
    }
    requestAnimationFrame(checkAudioClip);
  }
  requestAnimationFrame(checkAudioClip);
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

  realAudio.addEventListener('loadedmetadata', () => {
    publishNowPlaying(realAudio.paused ? 'paused' : 'playing');
    const durEl = document.getElementById('trackDuration');
    if (durEl && !isNaN(realAudio.duration)) {
      durEl.innerText = formatTime(realAudio.duration);
    }
  });
  realAudio.addEventListener('play', () => {
    const playBtn = document.getElementById('playPauseBtn');
    if (playBtn) playBtn.innerText = "⏸️";
    renderRealTracklist();
    publishNowPlaying('playing');
  });
  realAudio.addEventListener('pause', () => {
    const playBtn = document.getElementById('playPauseBtn');
    if (playBtn) playBtn.innerText = "▶️";
    renderRealTracklist();
    publishNowPlaying('paused');
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

  // Volume bar (Linked to PipeWire & Car Radio Master Gain)
  const volBar = document.getElementById('mediaVolBar');
  const volLabel = document.getElementById('volLabel');
  if (volBar) {
    volBar.addEventListener('input', (e) => {
      const val = parseInt(e.target.value);
      realAudio.volume = Math.min(1.0, val / 100);
      if (volLabel) volLabel.innerText = `${val}%`;
      fetch('/api/audio/volume', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ volume: val })
      }).catch(() => {});
    });
  }
  // Setup Bluetooth AVRCP MediaSession handlers for Steering Wheel & Car Radio buttons
  setupMediaSessionHandlers();
  // Setup Linux Kernel AVRCP Keyboard listener for /dev/input/event10
  setupHardwareMediaKeys();
  // Load Equalizer
  initAudioEqualizer();

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

      <button class="cluster-action-btn" style="padding:4px 10px; font-size:10px; font-weight:800; border-color:${idx === realTrackIdx && !realAudio.paused ? 'var(--accent-blue)' : '#222'}; background:${idx === realTrackIdx && !realAudio.paused ? 'rgba(0,176,255,0.2)' : 'transparent'}; color:#fff;">${idx === realTrackIdx && !realAudio.paused ? '🔊 NOW PLAYING' : '▶ PLAY'}</button>

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
  // Update MediaSession & BlueZ AVRCP metadata for Dodge Dart Uconnect 8.4 radio screen!
  if ('mediaSession' in navigator) {
    try {
      navigator.mediaSession.metadata = new MediaMetadata({
        title: t.title || "Track",
        artist: t.artist || "CarPi5 In-Dash Audio",
        album: t.album || "CarPi5 In-Dash",
        artwork: [
          { src: '/assets/pics/splash.png', sizes: '512x512', type: 'image/png' }
        ]
      });
    } catch (e) {}
  }
  // Publish directly to BlueZ AVRCP Target so the dash screen shows Title, Artist, Album!
  publishNowPlaying(autoPlay ? 'playing' : 'paused');

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
  folderPath: "~/Pictures",
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

function launchYouTube(mode = 'video') {
  const isMusic = (mode === 'music');
  const title = isMusic ? 'YouTube Music' : 'YouTube Cinema';
  showAiSpeechToast("Launching " + title + "... Use floating ◀ CARPI5 EXIT button to return.");
  if (typeof speakUtterance === 'function') {
    speakUtterance("Launching " + title + "!");
  }
  fetch('/api/media/launch_youtube', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ mode: mode })
  })
    .then(r => r.json())
    .then(data => {
      console.log('[YOUTUBE] Launch response:', data);
      updateExternalAppUi(true, title);
    })
    .catch(err => {
      console.warn('[YOUTUBE] Launch error, opening web fallback:', err);
      const url = isMusic ? 'https://music.youtube.com' : 'https://www.youtube.com';
      window.open(url, '_blank');
    });
}

function closeExternalApp() {
  showAiSpeechToast('Closing external app...');
  fetch('/api/media/close_external_app', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' }
  })
    .then(r => r.json())
    .then(data => {
      console.log('[EXTERNAL_APP] Closed:', data);
      updateExternalAppUi(false);
      showAiSpeechToast('Returned to CarPi5 Cockpit.');
    })
    .catch(err => {
      console.error('[EXTERNAL_APP] Close failed:', err);
    });
}

function updateExternalAppUi(isActive, title = 'External App') {
  const badge = document.getElementById('youtubeStatusBadge');
  const btnClose = document.getElementById('btnYtClose');
  if (badge) {
    if (isActive) {
      badge.textContent = 'ACTIVE (RUNNING)';
      badge.style.background = 'rgba(0, 230, 118, 0.2)';
      badge.style.borderColor = 'rgba(0, 230, 118, 0.6)';
      badge.style.color = '#00e676';
    } else {
      badge.textContent = 'HD CINEMA & MUSIC';
      badge.style.background = 'rgba(255, 0, 0, 0.15)';
      badge.style.borderColor = 'rgba(255, 0, 0, 0.35)';
      badge.style.color = '#ff4d4d';
    }
  }
  if (btnClose) {
    btnClose.style.display = isActive ? 'inline-flex' : 'none';
  }
}

function checkExternalAppStatus() {
  fetch('/api/media/external_app_status')
    .then(r => r.json())
    .then(data => {
      if (data && data.status === 'ok') {
        updateExternalAppUi(data.active, data.title);
      }
    })
    .catch(() => {});
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
    'PS1': '~/.config/retroarch/cores/pcsx_rearmed_libretro.so',
    'N64': '~/.config/retroarch/cores/parallel_n64_libretro.so',
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

// --- AUDIO OUTPUT ROUTING (PIPEWIRE / WIREPLUMBER) ---

function fetchAudioDevices() {

  fetch('/api/audio/devices')

    .then(r => r.json())

    .then(data => {

      const isBt = (data.sinks || []).some(s => s.is_bluetooth && s.is_default);

      const btnCar = document.getElementById('btnAudioCar');

      const btnHdmi = document.getElementById('btnAudioHdmi');

      const label = document.getElementById('audioCurrentSinkLabel');

      const chk = document.getElementById('chkAutoRouteAudio');

      if (chk && data.auto_route !== undefined) chk.checked = !!data.auto_route;

      if (btnCar && btnHdmi) {

        if (isBt) {

          btnCar.classList.add('active');

          btnCar.style.borderColor = '#00e676';

          btnCar.style.color = '#00e676';

          btnHdmi.classList.remove('active');

          btnHdmi.style.borderColor = '';

          btnHdmi.style.color = '';

        } else {

          btnHdmi.classList.add('active');

          btnHdmi.style.borderColor = '#00b0ff';

          btnHdmi.style.color = '#00b0ff';

          btnCar.classList.remove('active');

          btnCar.style.borderColor = '';

          btnCar.style.color = '';

        }

      }

      const activeSink = (data.sinks || []).find(s => s.is_default);

      if (label && activeSink) {

        label.innerText = `Active Sink: ${activeSink.name} (${Math.round(activeSink.volume * 100)}% Vol)`;

      }

    })

    .catch(err => console.warn("[AUDIO] Fetch devices error:", err));

}

function setAudioOutput(target) {

  showAiSpeechToast(`Switching audio output to ${target}...`);

  fetch('/api/audio/output', {

    method: 'POST',

    headers: { 'Content-Type': 'application/json' },

    body: JSON.stringify({ sink: target })

  })

  .then(r => r.json())

  .then(res => {

    showAiSpeechToast(res.message || `Audio routed to ${target}`);

    setTimeout(fetchAudioDevices, 800);

  })

  .catch(err => showAiSpeechToast("Audio switch error: " + err));

}

function toggleAutoRouteAudio(enabled) {

  fetch('/api/audio/output', {

    method: 'POST',

    headers: { 'Content-Type': 'application/json' },

    body: JSON.stringify({ auto_route: enabled })

  })

  .then(() => {

    showAiSpeechToast(enabled ? "Auto-audio routing enabled (prefers car speakers)." : "Auto-audio routing disabled (manual output mode).");

    fetchAudioDevices();

  });

}

// Periodic audio check

setInterval(fetchAudioDevices, 6000);

// =========================================================================

// 10-BAND STUDIO GRAPHIC EQUALIZER & HARDWARE DSP AUDIO SYSTEM

// =========================================================================

let audioCtx = null;

let audioSourceNode = null;

let eqFilters = [];

let subBassFilter = null;

let isEqBypassed = false;

let isAudioMuted = false;

const EQ_FREQS = [32, 64, 125, 250, 500, 1000, 2000, 4000, 8000, 16000];

const EQ_PRESETS = {

  SUICIDEBOYS: [+10, +8, +3, -2, -1, +2, +3, +2, +5, +6],

  METALCORE:   [+4,  +6, +5, -1, -3, +2, +6, +5, +4, +3],

  DUBSTEP:     [+12, +9, +4,  0, -1, +4, +6, +4, +7, +8],

  ROCK:        [+3,  +6, +5, +2, +3, +3, +4, +3, +3, +2],

  VOCAL:       [-6,  -3,  0, +1, +3, +6, +6, +4, +2,  0],

  FLAT:        [ 0,   0,  0,  0,  0,  0,  0,  0,  0,  0]

};

let currentEqGains = [+10, +8, +3, -2, -1, +2, +3, +2, +5, +6];

let currentEqPreset = 'SUICIDEBOYS';

function initAudioEqualizer() {

  try {

    const saved = localStorage.getItem('carpi5_eq_gains');

    if (saved) {

      currentEqGains = JSON.parse(saved);

    } else {

      currentEqGains = [...EQ_PRESETS.BASS];

    }

    const savedPreset = localStorage.getItem('carpi5_eq_preset');

    if (savedPreset) currentEqPreset = savedPreset;

  } catch (e) {}

  // Lazily connect Web Audio API on first user interaction / playback

  const connectWebAudio = () => {

    if (audioCtx) return;

    try {

      const AudioContext = window.AudioContext || window.webkitAudioContext;

      audioCtx = new AudioContext();

      audioSourceNode = audioCtx.createMediaElementSource(realAudio);

      // Create 10-band peaking filters

      eqFilters = EQ_FREQS.map((freq, idx) => {

        const filter = audioCtx.createBiquadFilter();

        if (idx === 0) {

          filter.type = 'lowshelf';

        } else if (idx === EQ_FREQS.length - 1) {

          filter.type = 'highshelf';

        } else {

          filter.type = 'peaking';

          filter.Q.value = 1.4;

        }

        filter.frequency.value = freq;

        filter.gain.value = currentEqGains[idx] || 0;

        return filter;

      });

      // 1. Subsonic High-Pass Filter (Protection for subwoofers below 28Hz)

      subsonicFilter = audioCtx.createBiquadFilter();

      subsonicFilter.type = 'highpass';

      subsonicFilter.frequency.value = isSubsonicFilterActive ? 28 : 10;

      subsonicFilter.Q.value = 0.707;

      // 2. Sub-Bass Shelf / Peaking Filter

      subBassFilter = audioCtx.createBiquadFilter();

      subBassFilter.type = 'lowshelf';

      subBassFilter.frequency.value = currentSubBassFreq || 45;

      subBassFilter.gain.value = currentSubGain || 0;

      // 3. Connect: Source -> Subsonic -> SubBass -> 10-Band EQ

      audioSourceNode.connect(subsonicFilter);

      subsonicFilter.connect(subBassFilter);

      let prev = subBassFilter;

      eqFilters.forEach(f => {

        prev.connect(f);

        prev = f;

      });

      // 4. Hardware Dynamics Compressor / Anti-Clip Brickwall Limiter

      autoClipLimiterNode = audioCtx.createDynamicsCompressor();

      autoClipLimiterNode.threshold.value = isAntiClipEnabled ? -1.5 : 0.0;

      autoClipLimiterNode.knee.value = 0.0;

      autoClipLimiterNode.ratio.value = isAntiClipEnabled ? 20.0 : 1.0;

      autoClipLimiterNode.attack.value = 0.003;

      autoClipLimiterNode.release.value = 0.150;

      prev.connect(autoClipLimiterNode);

      // 5. Peak Analyser & Master Destination

      clipAnalyser = audioCtx.createAnalyser();

      clipAnalyser.fftSize = 256;

      clipAnalyser.smoothingTimeConstant = 0.3;

      autoClipLimiterNode.connect(clipAnalyser);

      clipAnalyser.connect(audioCtx.destination);

      startClipMonitor();

      console.log("[AUDIO SUITE] Studio DSP Pipeline (10-Band EQ + Subsonic + Anti-Clip Limiter) active!");

    } catch (e) {

      console.warn("[EQUALIZER] Web Audio connect note:", e);

    }

  };

  realAudio.addEventListener('play', connectWebAudio, { once: true });

  window.addEventListener('click', connectWebAudio, { once: true });

}

function renderEqSliders() {

  const container = document.getElementById('eqSlidersGrid');

  if (!container) return;

  container.innerHTML = '';

  EQ_FREQS.forEach((freq, idx) => {

    const val = currentEqGains[idx] || 0;

    const label = freq >= 1000 ? `${freq / 1000}k` : `${freq}`;

    const col = document.createElement('div');

    col.style.cssText = 'display:flex; flex-direction:column; align-items:center; justify-content:space-between; height:100%;';

    col.innerHTML = `
      <div style="font-size:9.5px; font-weight:800; font-family:var(--font-mono); color:${val > 0 ? '#00e676' : (val < 0 ? '#ff5252' : '#8c9ba5')}; min-height:14px;" id="eqDb_${idx}">${val >= 0 ? '+' : ''}${val}</div>
      <input type="range" class="eq-vertical-slider" min="-12" max="12" step="1" value="${val}" oninput="setEqBandGain(${idx}, this.value)" style="writing-mode:bt-lr; -webkit-appearance:slider-vertical; width:18px; height:110px; accent-color:var(--accent-purple); cursor:pointer;">
      <div style="font-size:9.5px; font-weight:800; color:var(--text-secondary); margin-top:4px;">${label}</div>
    `;

    container.appendChild(col);

  });

  // Highlight active preset button

  ['suicideboys', 'metalcore', 'dubstep', 'rock', 'vocal'].forEach(p => {

    const btn = document.getElementById(`btnEqPreset_${p}`);

    if (btn) {

      if (p.toUpperCase() === currentEqPreset) {

        btn.classList.add('active');

        btn.style.boxShadow = '0 0 10px rgba(168,85,247,0.5)';

      } else {

        btn.classList.remove('active');

        btn.style.boxShadow = 'none';

      }

    }

  });

}

function setEqBandGain(idx, val) {

  val = parseInt(val);

  currentEqGains[idx] = val;

  const dbEl = document.getElementById(`eqDb_${idx}`);

  if (dbEl) {

    dbEl.innerText = `${val >= 0 ? '+' : ''}${val}`;

    dbEl.style.color = val > 0 ? '#00e676' : (val < 0 ? '#ff5252' : '#8c9ba5');

  }

  if (eqFilters[idx] && !isEqBypassed) {

    eqFilters[idx].gain.value = val;

  }

  try {

    localStorage.setItem('carpi5_eq_gains', JSON.stringify(currentEqGains));

  } catch (e) {}

}

function resetEqToFlat() {

  currentEqGains = [0, 0, 0, 0, 0, 0, 0, 0, 0, 0];

  currentEqPreset = 'FLAT';

  try {

    localStorage.setItem('carpi5_eq_preset', 'FLAT');

    localStorage.setItem('carpi5_eq_gains', JSON.stringify(currentEqGains));

  } catch (e) {}

  if (eqFilters.length > 0 && !isEqBypassed) {

    eqFilters.forEach(f => f.gain.value = 0);

  }

  const chk = document.getElementById('chkSubBassBoost');

  if (chk) chk.checked = false;

  if (subBassFilter) subBassFilter.gain.value = 0;

  renderEqSliders();

  showAiSpeechToast("↺ Equalizer Reset to Flat (0 dB)");

}

function applyEqPreset(presetKey) {

  const curve = EQ_PRESETS[presetKey];

  if (!curve) return;

  currentEqPreset = presetKey;

  currentEqGains = [...curve];

  try {

    localStorage.setItem('carpi5_eq_preset', presetKey);

    localStorage.setItem('carpi5_eq_gains', JSON.stringify(currentEqGains));

  } catch (e) {}

  if (eqFilters.length > 0 && !isEqBypassed) {

    eqFilters.forEach((f, i) => {

      f.gain.value = currentEqGains[i] || 0;

    });

  }

  renderEqSliders();

  showAiSpeechToast(`Sound DSP: Applied ${presetKey.replace('_', ' ')} Preset`);

}

function toggleBassBoost(checked) {

  if (subBassFilter) {

    subBassFilter.gain.value = checked ? 6.0 : 0.0;

  }

  showAiSpeechToast(checked ? "Subwoofer Bass Boost: +6 dB @ 45Hz Active" : "Subwoofer Bass Boost: Off");

}

function toggleEqBypass() {

  isEqBypassed = !isEqBypassed;

  const btn = document.getElementById('btnEqBypass');

  if (isEqBypassed) {

    if (eqFilters.length > 0) eqFilters.forEach(f => f.gain.value = 0);

    if (subBassFilter) subBassFilter.gain.value = 0;

    if (btn) {

      btn.innerText = "DSP: BYPASSED";

      btn.style.borderColor = "#ff5252";

      btn.style.color = "#ff5252";

    }

    showAiSpeechToast("Equalizer Bypassed (Flat Output)");

  } else {

    if (eqFilters.length > 0) {

      eqFilters.forEach((f, i) => f.gain.value = currentEqGains[i] || 0);

    }

    const chk = document.getElementById('chkSubBassBoost');

    if (subBassFilter && chk && chk.checked) subBassFilter.gain.value = 6.0;

    if (btn) {

      btn.innerText = "DSP: ACTIVE";

      btn.style.borderColor = "#22c55e";

      btn.style.color = "#4ade80";

    }

    showAiSpeechToast("Equalizer DSP Engaged");

  }

}

// Master Radio Volume Controls

function adjustRadioVolume(delta) {

  fetch('/api/audio/volume', {

    method: 'POST',

    headers: { 'Content-Type': 'application/json' },

    body: JSON.stringify({ delta: delta })

  })

  .then(r => r.json())

  .then(() => {

    syncRadioVolumeUI();

  });

}

function toggleAudioMute() {

  fetch('/api/audio/volume', {

    method: 'POST',

    headers: { 'Content-Type': 'application/json' },

    body: JSON.stringify({ action: 'mute' })

  })

  .then(r => r.json())

  .then(() => {

    syncRadioVolumeUI();

  });

}

function syncRadioVolumeUI() {

  fetch('/api/audio/volume')

    .then(r => r.json())

    .then(data => {

      const volBar = document.getElementById('mediaVolBar');

      const volLabel = document.getElementById('volLabel');

      if (volBar && data.volume !== undefined) {

        volBar.value = data.volume;

      }

      if (volLabel && data.volume !== undefined) {

        volLabel.innerText = data.muted ? "MUTED" : `${data.volume}%`;

        volLabel.style.color = data.muted ? "#ff5252" : "var(--text-secondary)";

      }

    });

}

// Bluetooth AVRCP & Steering Wheel Button Handlers

function setupMediaSessionHandlers() {

  if ('mediaSession' in navigator) {

    try {

      navigator.mediaSession.setActionHandler('play', () => {

        realAudio.play().catch(() => {});

      });

      navigator.mediaSession.setActionHandler('pause', () => {

        realAudio.pause();

      });

      navigator.mediaSession.setActionHandler('previoustrack', () => {

        prevTrack();

      });

      navigator.mediaSession.setActionHandler('nexttrack', () => {

        nextTrack();

      });

      navigator.mediaSession.setActionHandler('seekto', (details) => {

        if (details.seekTime && realAudio.duration) {

          realAudio.currentTime = details.seekTime;

        }

      });

      console.log("[AVRCP] MediaSession action handlers registered for steering wheel controls!");

    } catch (e) {

      console.warn("[AVRCP] MediaSession handler note:", e);

    }

  }

}

function setupHardwareMediaKeys() {

  window.addEventListener('keydown', (e) => {

    if (e.key === 'MediaTrackNext' || e.keyCode === 176) {

      nextTrack();

    } else if (e.key === 'MediaTrackPrevious' || e.keyCode === 177) {

      prevTrack();

    } else if (e.key === 'MediaPlayPause' || e.keyCode === 179) {

      togglePlayPause();

    }

  });

}

// ========================================================

// CARPI5 IN-DASH AUDIO SUITE & DSP STUDIO CONTROLS

// ========================================================

function openAudioSuiteModal() {

  const m = document.getElementById('modalEqualizer');

  if (m) {

    m.style.display = 'flex';

    renderEqSliders();

    syncAudioSuiteUI();

  }

}

// Keep backward compatibility for existing buttons

function openEqualizerModal() {

  openAudioSuiteModal();

}

function closeAudioSuiteModal() {

  const m = document.getElementById('modalEqualizer');

  if (m) m.style.display = 'none';

}

function closeEqualizerModal() {

  closeAudioSuiteModal();

}

function switchAudioSuiteTab(tabKey) {

  ['eq', 'anticlip', 'tempo', 'uconnect'].forEach(t => {

    const pane = document.getElementById(`audioTabPane_${t}`);

    const btn = document.getElementById(`audioTabBtn_${t}`);

    if (pane) pane.style.display = (t === tabKey ? 'block' : 'none');

    if (btn) {

      if (t === tabKey) {

        btn.classList.add('active');

        btn.style.borderColor = '#c084fc';

        btn.style.color = '#fff';

        btn.style.background = 'rgba(168, 85, 247, 0.25)';

      } else {

        btn.classList.remove('active');

        btn.style.borderColor = 'rgba(255, 255, 255, 0.08)';

        btn.style.color = 'var(--text-secondary)';

        btn.style.background = 'rgba(0, 0, 0, 0.25)';

      }

    }

  });

}

function syncAudioSuiteUI() {

  // Sync Limiter

  const chkLimiter = document.getElementById('chkAutoLimiter');

  if (chkLimiter) chkLimiter.checked = isAntiClipEnabled;

  const statusBadge = document.getElementById('antiClipStatusBadge');

  if (statusBadge) {

    statusBadge.innerText = isAntiClipEnabled ? "ACTIVE (ZERO DISTORTION)" : "BYPASSED (RAW)";

    statusBadge.style.color = isAntiClipEnabled ? "var(--accent-green)" : "#ff5252";

    statusBadge.style.borderColor = isAntiClipEnabled ? "rgba(0,230,118,0.4)" : "rgba(255,82,82,0.4)";

  }

  // Sync Subsonic Filter

  const chkSub = document.getElementById('chkSubsonicFilter');

  if (chkSub) chkSub.checked = isSubsonicFilterActive;

  // Sync Sub Frequency Buttons

  ['35', '45', '60'].forEach(f => {

    const btn = document.getElementById(`btnSubFreq_${f}`);

    if (btn) {

      if (parseInt(f) === currentSubBassFreq) {

        btn.classList.add('active');

        btn.style.boxShadow = '0 0 10px rgba(192, 132, 252, 0.5)';

      } else {

        btn.classList.remove('active');

        btn.style.boxShadow = 'none';

      }

    }

  });

  // Sync Speed & Tempo

  const speedSlider = document.getElementById('mediaSpeedSlider');

  if (speedSlider) speedSlider.value = currentPlaybackSpeed;

  const speedLabel = document.getElementById('speedValLabel');

  if (speedLabel) {

    let modeText = "";

    if (currentPlaybackSpeed === 1.0) modeText = " (Normal)";

    else if (currentPlaybackSpeed === 0.8) modeText = " (Slowed & Throwed)";

    else if (currentPlaybackSpeed < 1.0) modeText = " (Slowed)";

    else if (currentPlaybackSpeed === 1.25) modeText = " (Nightcore)";

    else modeText = " (Fast)";

    speedLabel.innerText = `${currentPlaybackSpeed.toFixed(2)}x${modeText}`;

  }

  // Sync Pitch Lock

  const chkPitch = document.getElementById('chkPitchLock');

  if (chkPitch) chkPitch.checked = isPitchLocked;

  const pitchStatus = document.getElementById('pitchLockStatus');

  if (pitchStatus) {

    pitchStatus.innerText = isPitchLocked ? "🔒 NATURAL VOCAL PITCH LOCKED" : "📼 ANALOG TAPE / VINYL PITCH (Authentic Pitch Shift)";

    pitchStatus.style.color = isPitchLocked ? "var(--accent-blue)" : "var(--accent-purple)";

  }

  // Sync Uconnect Dash Track Text

  const dashTrack = document.getElementById('uconnectDashText');

  const tTitle = document.getElementById('trackTitle')?.innerText || "CarPi5 In-Dash";

  const tArtist = document.getElementById('trackArtist')?.innerText || "Dodge Dart";

  if (dashTrack) dashTrack.innerText = `${tArtist} - ${tTitle}`;

}

function toggleAntiClipLimiter(enable) {

  isAntiClipEnabled = !!enable;

  try {

    localStorage.setItem('carpi5_anticlip_enabled', isAntiClipEnabled ? 'true' : 'false');

  } catch (e) {}

  if (autoClipLimiterNode) {

    autoClipLimiterNode.threshold.value = isAntiClipEnabled ? -1.5 : 0.0;

    autoClipLimiterNode.ratio.value = isAntiClipEnabled ? 20.0 : 1.0;

  }

  syncAudioSuiteUI();

  showAiSpeechToast(isAntiClipEnabled ? "Anti-Clip Limiter: ACTIVE (Zero Digital Clipping)" : "Anti-Clip Limiter: Bypassed");

}

function toggleSubsonicFilter(enable) {

  isSubsonicFilterActive = !!enable;

  try {

    localStorage.setItem('carpi5_subsonic_active', isSubsonicFilterActive ? 'true' : 'false');

  } catch (e) {}

  if (subsonicFilter) {

    subsonicFilter.frequency.value = isSubsonicFilterActive ? 28 : 10;

  }

  syncAudioSuiteUI();

  showAiSpeechToast(isSubsonicFilterActive ? "Subsonic Filter: 28Hz Subwoofer Protection Active" : "Subsonic Filter: Inactive");

}

function setSubBassFrequency(freq) {

  currentSubBassFreq = parseInt(freq) || 45;

  try {

    localStorage.setItem('carpi5_sub_freq', currentSubBassFreq.toString());

  } catch (e) {}

  if (subBassFilter) {

    subBassFilter.frequency.value = currentSubBassFreq;

  }

  syncAudioSuiteUI();

  showAiSpeechToast(`Subwoofer Bass Tuned to ${currentSubBassFreq} Hz`);

}

function setPlaybackTempo(rate) {

  rate = parseFloat(rate);

  if (isNaN(rate) || rate < 0.25 || rate > 4.0) rate = 1.0;

  currentPlaybackSpeed = rate;

  if (typeof realAudio !== 'undefined' && realAudio) {

    realAudio.playbackRate = currentPlaybackSpeed;

    realAudio.preservesPitch = isPitchLocked;

  }

  syncAudioSuiteUI();

  showAiSpeechToast(`Playback Speed: ${rate.toFixed(2)}x`);

}

function togglePitchLock(locked) {

  isPitchLocked = !!locked;

  if (typeof realAudio !== 'undefined' && realAudio) {

    realAudio.preservesPitch = isPitchLocked;

  }

  syncAudioSuiteUI();

  showAiSpeechToast(isPitchLocked ? "Pitch Lock: Natural Vocal Preserved" : "Pitch Lock Off: Authentic Tape / Vinyl Pitch Shift");

}

function resyncUconnectDashDisplay() {

  const currentTitle = document.getElementById('trackTitle')?.innerText || "CarPi5 In-Dash";

  const currentArtist = document.getElementById('trackArtist')?.innerText || "Dodge Dart";

  fetch('/api/media/now_playing', {

    method: 'POST',

    headers: { 'Content-Type': 'application/json' },

    body: JSON.stringify({

      title: currentTitle,

      artist: currentArtist,

      album: "CarPi5 In-Dash",

      genre: "Music",

      duration: realAudio?.duration || 180,

      track_num: (typeof currentTrackIndex !== 'undefined' ? currentTrackIndex + 1 : 1),

      total_tracks: (typeof playlist !== 'undefined' ? playlist.length : 1),

      status: realAudio?.paused ? 'paused' : 'playing'

    })

  })

  .then(r => r.json())

  .then(data => {

    showAiSpeechToast(`🚗 Dash Display Re-Synced: ${currentArtist} - ${currentTitle}`);

    const dashStatus = document.getElementById('uconnectDashText');

    if (dashStatus) dashStatus.innerText = `${currentArtist} - ${currentTitle}`;

  })

  .catch(err => {

    showAiSpeechToast("Uconnect Sync Broadcast sent");

  });

}

// ==========================================

// CARPI3 ETHERNET DASHCAM & REPLAY CONTROLLER

// ==========================================

let dashcamStatusTimer = null;

function initDashcamController() {

  refreshDashcamStatus();

  refreshDashcamClips();

  const img = document.getElementById('dashcamLiveImg');

  if (img) {

    // Refresh live MJPEG stream source

    img.src = '/dashcam/stream.mjpg?t=' + Date.now();

  }

  if (dashcamStatusTimer) clearInterval(dashcamStatusTimer);

  dashcamStatusTimer = setInterval(refreshDashcamStatus, 4000);

}

function refreshDashcamStatus() {

  fetch('/dashcam/api/status')

    .then(r => r.json())

    .then(data => {

      const sub = document.getElementById('dashcamSubStatus');

      const badge = document.getElementById('dashcamSourceBadge');

      const storeText = document.getElementById('dashcamStorageText');

      const homeBadge = document.getElementById('homeDashcamBadge');

      if (data && data.online) {

        if (sub) sub.innerText = 'Link: Direct Ethernet 10.0.0.2 • Uptime: ' + Math.floor(data.uptime_sec / 60) + 'm • Source: ' + (data.source || 'testpattern').toUpperCase();

        if (badge) {

          if (data.source === 'csi') {

            badge.innerText = 'SENSOR: SONY IMX219 (CSI RIBBON ACTIVE)';

            badge.style.color = '#00e676';

          } else if (data.source === 'usb') {

            badge.innerText = 'SENSOR: USB WEBCAM (' + (data.device || 'v4l2') + ')';

            badge.style.color = '#00e676';

          } else {

            badge.innerText = 'SENSOR: TEST PATTERN (WAITING ON SENSOR)';

            badge.style.color = '#ffab00';

          }

        }

        if (storeText && data.disk) {

          storeText.innerText = 'Pi 3 Storage: ' + data.disk.used_gb + ' GB used / ' + data.disk.total_gb + ' GB (' + data.disk.used_percent + '%)';

        }

        if (homeBadge) {

          homeBadge.innerHTML = '🎥 CARPI3: ' + (data.source === 'testpattern' ? 'SIM' : 'ONLINE');

        }

      }

    })

    .catch(err => {

      const sub = document.getElementById('dashcamSubStatus');

      if (sub) sub.innerText = 'Link: Connecting to Pi 3 (10.0.0.2:8000)...';

    });

}

function refreshDashcamClips() {

  fetch('/dashcam/api/clips')

    .then(r => r.json())

    .then(data => {

      const container = document.getElementById('dashcamClipsList');

      const countBadge = document.getElementById('dashcamClipCountBadge');

      if (!container) return;

      const clips = (data && data.clips) ? data.clips : [];

      if (countBadge) countBadge.innerText = clips.length + ' CLIPS';

      if (clips.length === 0) {

        container.innerHTML = '<div style="text-align:center; padding:30px; color:var(--text-secondary); font-size:12px;">No clips recorded yet.<br><span style="font-size:10px;">Clips save automatically every 3 minutes.</span></div>';

        return;

      }

      let html = '';

      clips.forEach(clip => {

        html += '<div style="background:rgba(255,255,255,0.03); border:1px solid #1c2636; border-radius:8px; padding:10px 12px; display:flex; justify-content:space-between; align-items:center;">';

        html += '  <div>';

        html += '    <div style="font-size:12px; font-weight:800; color:#fff; font-family:var(--font-mono);">🎬 ' + clip.filename + '</div>';

        html += '    <div style="font-size:10px; color:var(--text-secondary); margin-top:2px;">' + clip.created_at + ' • ' + clip.size_mb + ' MB</div>';

        html += '  </div>';

        html += '  <div style="display:flex; gap:6px;">';

        html += '    <button onclick="playDashcamClip(\'' + clip.filename + '\', \'/dashcam' + clip.url + '\')" class="cluster-action-btn" style="padding:4px 10px; font-size:11px; border-color:var(--accent-blue); color:var(--accent-blue); font-weight:800;">▶ PLAY</button>';

        html += '  </div>';

        html += '</div>';

      });

      container.innerHTML = html;

    })

    .catch(() => {});

}

function playDashcamClip(filename, url) {

  const wrapper = document.getElementById('clipPlayerWrapper');

  const video = document.getElementById('clipPlayer');

  const title = document.getElementById('activeClipTitle');

  if (wrapper && video && title) {

    wrapper.style.display = 'block';

    title.innerText = filename;

    video.src = url;

    video.play().catch(() => {});

  }

}

function closeClipPlayer() {

  const wrapper = document.getElementById('clipPlayerWrapper');

  const video = document.getElementById('clipPlayer');

  if (wrapper && video) {

    video.pause();

    video.src = '';

    wrapper.style.display = 'none';

  }

}

function toggleDashcamFullscreen() {

  const pane = document.getElementById('dashcamLiveImg') ? document.getElementById('dashcamLiveImg').parentElement : null;

  if (!pane) return;

  

  if (!document.fullscreenElement) {

    pane.requestFullscreen().then(() => {

      let exitBtn = document.getElementById('dashcamTouchExitBtn');

      if (!exitBtn) {

        exitBtn = document.createElement('button');

        exitBtn.id = 'dashcamTouchExitBtn';

        exitBtn.innerText = '✕ EXIT FULLSCREEN';

        exitBtn.style.position = 'absolute';

        exitBtn.style.top = '16px';

        exitBtn.style.right = '16px';

        exitBtn.style.zIndex = '999999';

        exitBtn.style.padding = '12px 20px';

        exitBtn.style.fontSize = '14px';

        exitBtn.style.fontWeight = '900';

        exitBtn.style.background = 'rgba(255,51,68,0.85)';

        exitBtn.style.color = '#fff';

        exitBtn.style.border = '2px solid #fff';

        exitBtn.style.borderRadius = '12px';

        exitBtn.style.boxShadow = '0 4px 15px rgba(0,0,0,0.6)';

        exitBtn.onclick = function(e) {

          e.stopPropagation();

          document.exitFullscreen().catch(() => {});

        };

        pane.appendChild(exitBtn);

      } else {

        exitBtn.style.display = 'block';

      }

    }).catch(() => {});

  } else {

    document.exitFullscreen().catch(() => {});

  }

}

document.addEventListener('fullscreenchange', () => {

  if (!document.fullscreenElement) {

    const exitBtn = document.getElementById('dashcamTouchExitBtn');

    if (exitBtn) exitBtn.style.display = 'none';

  }

});

// Hook into navigateTo

const origNavigateTo = window.navigateTo;

window.navigateTo = function(screenName) {

  if (screenName === 'dashcam') {

    initDashcamController();

  }

  if (origNavigateTo) origNavigateTo(screenName);

};

document.addEventListener('DOMContentLoaded', () => {

  const img = document.getElementById('dashcamLiveImg');

  if (img) {

    img.onclick = toggleDashcamFullscreen;

  }

});

// ========================================================

// CARPI5 MEDIA HUB & BADASS IN-DASH AUDIO STUDIO EXTENSION

// ========================================================

let isShuffleActive = false;

let isRepeatActive = false;

let visualizerAnimationId = null;

function openMusicPlayer() {

  navigateTo('music');

  startMusicVisualizer();

}

function launchStremio() {

  showAiSpeechToast("Launching Stremio Cinema...");

  fetch('/api/media/launch_stremio', { method: 'POST' })

    .then(r => r.json())

    .then(data => {

      console.log("[STREMIO] Launch response:", data);

    })

    .catch(err => {

      console.warn("[STREMIO] Launch error, opening web fallback:", err);

      window.open('https://web.stremio.com', '_blank');

    });

}

function toggleShuffle() {

  isShuffleActive = !isShuffleActive;

  const btn = document.getElementById('btnShuffleToggle');

  if (btn) {

    btn.style.opacity = isShuffleActive ? '1' : '0.65';

    btn.style.color = isShuffleActive ? 'var(--accent-blue)' : '#fff';

  }

  showAiSpeechToast(isShuffleActive ? "Shuffle: ON" : "Shuffle: OFF");

}

function toggleRepeat() {

  isRepeatActive = !isRepeatActive;

  const btn = document.getElementById('btnRepeatToggle');

  if (btn) {

    btn.style.opacity = isRepeatActive ? '1' : '0.65';

    btn.style.color = isRepeatActive ? 'var(--accent-blue)' : '#fff';

  }

  showAiSpeechToast(isRepeatActive ? "Repeat: ON" : "Repeat: OFF");

}

function filterPlaylistTracks(query) {

  const q = (query || '').toLowerCase().trim();

  const listEl = document.getElementById('mediaTrackList');

  if (!listEl) return;

  const items = listEl.querySelectorAll('.music-track-item');

  items.forEach(item => {

    const text = item.innerText.toLowerCase();

    item.style.display = (!q || text.includes(q)) ? 'flex' : 'none';

  });

}

function rescanMusicLibrary() {

  showAiSpeechToast("Scanning audio files...");

  fetch('/api/media/tracks')

    .then(r => r.json())

    .then(data => {

      let list = [];

      if (Array.isArray(data)) {

        list = data;

      } else if (data && Array.isArray(data.tracks)) {

        list = data.tracks;

      }

      if (list.length > 0) {

        realPlaylist = list;

        renderRealTracklist();

        showAiSpeechToast(`Found ${realPlaylist.length} tracks`);

      } else {

        showAiSpeechToast("No tracks found");

      }

    })

    .catch(e => console.error("Error rescanning tracks:", e));

}

// Hook realAudio events for vinyl spin and visualizer

realAudio.addEventListener('play', () => {

  const art = document.getElementById('musicAlbumArtBox');

  if (art) art.classList.add('vinyl-spinning');

  startMusicVisualizer();

});

realAudio.addEventListener('pause', () => {

  const art = document.getElementById('musicAlbumArtBox');

  if (art) art.classList.remove('vinyl-spinning');

});

realAudio.addEventListener('ended', () => {

  const art = document.getElementById('musicAlbumArtBox');

  if (art) art.classList.remove('vinyl-spinning');

  if (isRepeatActive) {

    realAudio.currentTime = 0;

    realAudio.play().catch(() => {});

  } else if (isShuffleActive && realPlaylist.length > 1) {

    let nextIdx = Math.floor(Math.random() * realPlaylist.length);

    if (nextIdx === realTrackIdx) nextIdx = (nextIdx + 1) % realPlaylist.length;

    loadTrack(nextIdx, true);

  } else {

    nextTrack();

  }

});

// Canvas Spectrum Equalizer Visualizer

function startMusicVisualizer() {

  if (visualizerAnimationId) return;

  const canvas = document.getElementById('musicSpectrumCanvas');

  if (!canvas) return;

  const ctx = canvas.getContext('2d');

  const barCount = 28;

  const barWidth = 7;

  const gap = 3;

  let phases = Array(barCount).fill(0).map(() => Math.random() * Math.PI * 2);

  function renderFrame() {

    if (currentScreen !== 'music') {

      visualizerAnimationId = null;

      return;

    }

    ctx.clearRect(0, 0, canvas.width, canvas.height);

    const isPlaying = !realAudio.paused && realAudio.currentTime > 0;

    for (let i = 0; i < barCount; i++) {

      let height = 3;

      if (isPlaying) {

        phases[i] += 0.08 + (i * 0.005);

        const wave = Math.sin(phases[i]) * 0.5 + 0.5;

        const bassBoost = (i < 8) ? 1.4 : 1.0;

        height = Math.max(3, wave * (canvas.height - 4) * bassBoost);

      }

      const x = i * (barWidth + gap);

      const y = canvas.height - height;

      // Color gradient: cyan to purple/pink

      const grad = ctx.createLinearGradient(0, canvas.height, 0, 0);

      grad.addColorStop(0, '#00b0ff');

      grad.addColorStop(0.7, '#00e676');

      grad.addColorStop(1, '#ff4081');

      ctx.fillStyle = grad;

      ctx.fillRect(x, y, barWidth, height);

    }

    visualizerAnimationId = requestAnimationFrame(renderFrame);

  }

  visualizerAnimationId = requestAnimationFrame(renderFrame);

}

// Update top marquee when track loads

const origLoadTrack = window.loadTrack;

window.loadTrack = function(idx, autoPlay = true) {

  if (origLoadTrack) origLoadTrack(idx, autoPlay);

  if (realPlaylist && realPlaylist[idx]) {

    const t = realPlaylist[idx];

    const marquee = document.getElementById('musicTopMarquee');

    if (marquee) marquee.innerText = `${t.title || 'Track'} — ${t.artist || 'CarPi5'}`;

  }

};

function loadDynamicAudioDevices() {

  fetch('/api/audio/devices')

    .then(r => r.json())

    .then(data => {

      populateAudioDropdowns(data);

    })

    .catch(err => console.error('[AUDIO] Devices error:', err));

}

function populateAudioDropdowns(data) {

  const sinkSelect = document.getElementById('audioOutputSinkSelect');

  const sourceSelect = document.getElementById('audioInputSourceSelect');

  const sinkLabel = document.getElementById('audioCurrentSinkLabel');

  const sourceLabel = document.getElementById('audioCurrentSourceLabel');

  if (sinkSelect && data.sinks) {

    let html = '';

    data.sinks.forEach(s => {

      const isSel = s.id === data.active_sink_id || s.is_default;

      const type = s.is_bluetooth ? '📻 Bluetooth Uconnect' : (s.name.toLowerCase().includes('hdmi') ? '🖥️ HDMI Display' : '🎧 Audio Device');

      html += `<option value="${s.id}" ${isSel ? 'selected' : ''}>${type} (${s.name})</option>`;

      if (isSel && sinkLabel) {

        sinkLabel.innerText = `Active Output: ${s.name} (${Math.round((s.volume || 1.0) * 100)}% Vol)`;

      }

    });

    sinkSelect.innerHTML = html;

  }

  if (sourceSelect && data.sources) {

    let html = '';

    data.sources.forEach(src => {

      const isSel = src.id === data.active_source_id || src.is_default;

      const type = src.is_bluetooth ? '📱 Bluetooth Mic' : '🎙️ Microphone';

      html += `<option value="${src.id}" ${isSel ? 'selected' : ''}>${type} (${src.name})</option>`;

      if (isSel && sourceLabel) {

        sourceLabel.innerText = `Active Mic: ${src.name}`;

      }

    });

    sourceSelect.innerHTML = html;

  }

}

function onSelectAudioOutputSink(sinkId) {

  if (!sinkId) return;

  fetch('/api/audio/output', {

    method: 'POST',

    headers: { 'Content-Type': 'application/json' },

    body: JSON.stringify({ sink: sinkId })

  })

    .then(r => r.json())

    .then(() => {

      showAiSpeechToast("Audio output switched!");

      loadDynamicAudioDevices();

    });

}

function onSelectAudioInputSource(sourceId) {

  if (!sourceId) return;

  fetch('/api/audio/input', {

    method: 'POST',

    headers: { 'Content-Type': 'application/json' },

    body: JSON.stringify({ source: sourceId })

  })

    .then(r => r.json())

    .then(() => {

      showAiSpeechToast("Microphone source switched!");

      loadDynamicAudioDevices();

    });

}

// --- PHASE 3: DEDICATED FULL AUDIO SUITE EQ GRID ---

function renderFullAudioSuiteEqGrid() {

  const container = document.getElementById('fullAudioSuiteEqGrid');

  if (!container) return;

  container.innerHTML = '';

  EQ_FREQS.forEach((freq, idx) => {

    const val = currentEqGains[idx] || 0;

    const label = freq >= 1000 ? `${freq / 1000}k` : `${freq}`;

    const col = document.createElement('div');

    col.style.cssText = 'display:flex; flex-direction:column; align-items:center; justify-content:space-between; height:185px; flex:1; min-width:44px; padding:0 4px;';

    col.innerHTML = `
      <div style="font-size:11px; font-weight:800; font-family:var(--font-mono); color:${val > 0 ? '#00e676' : (val < 0 ? '#ff5252' : '#8c9ba5')}; min-height:16px;" id="fullEqDb_${idx}">${val >= 0 ? '+' : ''}${val} dB</div>
      <input type="range" class="eq-vertical-slider" min="-12" max="12" step="1" value="${val}" oninput="setFullEqBandGain(${idx}, this.value)" style="writing-mode:bt-lr; -webkit-appearance:slider-vertical; width:28px; height:130px; accent-color:var(--accent-purple); cursor:pointer;">
      <div style="font-size:11px; font-weight:800; color:#fff; margin-top:6px;">${label}Hz</div>
    `;

    container.appendChild(col);

  });

}

function setFullEqBandGain(idx, val) {

  setEqBandGain(idx, val);

  const dbEl = document.getElementById(`fullEqDb_${idx}`);

  if (dbEl) {

    val = parseInt(val);

    dbEl.innerText = `${val >= 0 ? '+' : ''}${val} dB`;

    dbEl.style.color = val > 0 ? '#00e676' : (val < 0 ? '#ff5252' : '#8c9ba5');

  }

}
