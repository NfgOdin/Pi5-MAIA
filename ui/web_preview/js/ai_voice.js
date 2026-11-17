// CarPi5 UI Module: AI Companion, Voice/Wake Engine, Animations Drawer, TTS Cache & Google OAuth

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
  const avatarPath = (pData && pData.avatar_image) ? pData.avatar_image : 'assets/pics/rum_avatar.png';
  const splashImg = (pData && pData.boot_splash_image) ? pData.boot_splash_image : 'assets/pics/splash.png';
  const splashVid = (pData && pData.boot_splash_video) ? pData.boot_splash_video : '';

  let displayName = "R.U.M.";
  let subtitleText = "Realtime Underhood MultiAir • The Forgotten Triplet";
  let statusBadgeText = "R.U.M. ACTIVE";
  let cardTitleText = "R.U.M.";
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

// --- ELEMENTARY MOTION DETECTOR (EMD) GESTURE CONTROLLER ---

function handleGestureEvent(gesture) {
  if (!gesture) return;
  console.log("[EMD GESTURE EVENT]", gesture);
  if (gesture === 'SWIPE_RIGHT') {
    nextTrack();
    showAiSpeechToast("👉 GESTURE: NEXT TRACK");
  } else if (gesture === 'SWIPE_LEFT') {
    prevTrack();
    showAiSpeechToast("👈 GESTURE: PREVIOUS TRACK");
  } else if (gesture === 'SWIPE_UP') {
    fetch('/api/avrcp/action', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action: 'volume_up' })
    }).catch(() => {});
    showAiSpeechToast("👆 GESTURE: VOLUME UP");
  } else if (gesture === 'SWIPE_DOWN') {
    if (typeof closeGpioModal === 'function') closeGpioModal();
    if (typeof closeDtcScanModal === 'function') closeDtcScanModal();
    navigateTo('home');
    showAiSpeechToast("👇 GESTURE: RETURN HOME");
  } else if (gesture === 'LOOM_PUSH') {
    togglePlayPause();
    showAiSpeechToast("✋ GESTURE: PLAY / PAUSE");
  }
}

function handleAiAction(action) {
  if (action && action.type === 'gesture') { handleGestureEvent(action.gesture); return; }
  if (!action) return;
  console.log("[AI COCKPIT ACTION]", action);
  if (typeof stopScreensaver === 'function') stopScreensaver();

  if (action.type === 'PIP_INTERACTION' || action.type === 'PIP_FEED') {
    showAiSpeechToast(action.speech);
    setWaifuEmotion(action.emotion || 'HAPPY_PROUD');
    if (action.action && typeof playVrmAction === 'function') {
      playVrmAction(action.action, 4500);
    }
    if (action.type === 'PIP_FEED') {
      if (typeof attachPipDropperToRum === 'function') attachPipDropperToRum();
      setTimeout(() => {
        if (typeof detachPipDropperFromRum === 'function') detachPipDropperFromRum();
      }, 5000);
    }
    return;
  }
  if (action.type === 'SHOWER_THOUGHT') {
    showAiSpeechToast(action.speech);
    setWaifuEmotion('THOUGHTFUL');
    return;
  }
  if (action.type === 'MORNING_DREAM') {
    showAiSpeechToast(action.speech);
    setWaifuEmotion('HAPPY_PROUD');
    if (typeof playVrmAction === 'function') {
      playVrmAction('action_standup.bvh', 5000);
    }
    return;
  }
  if (action.type === 'navigate') {
    const validScreens = ['home', 'gauges', 'ai', 'media', 'music', 'games', 'settings', 'dashcam', 'maintenance'];
    if (validScreens.includes(action.target)) {
      if (action.target === 'music') {
        openMusicPlayer();
      } else {
        navigateTo(action.target);
      }
    }
  } else if (action.type === 'launch') {
    if (action.target === 'kodi') {
      launchKodi();
    } else if (action.target === 'vlc') {
      launchVlc();
    } else if (action.target === 'stremio') {
      launchStremio();
    } else if (action.target === 'retroarch') {
      launchRetroArch();
    }
  } else if (action.type === 'action') {
    if (action.target === 'diagnostics') {
      openDtcScanModal();
    }
  } else if (action.type === 'media') {
    if (action.action === 'next') {
      nextTrack();
      showAiSpeechToast("⏭️ Next Track (Steering Wheel / Radio)");
    } else if (action.action === 'prev') {
      prevTrack();
      showAiSpeechToast("⏮️ Previous Track (Steering Wheel / Radio)");
    } else if (action.action === 'toggle') {
      togglePlayPause();
      showAiSpeechToast(realAudio.paused ? "⏸️ Paused" : "▶️ Playing");
    } else if (action.action === 'play') {
      if (realAudio.paused) togglePlayPause();
    } else if (action.action === 'pause') {
      if (!realAudio.paused) togglePlayPause();
      togglePlayPause();
      showAiSpeechToast(realAudio.paused ? "⏸️ Paused" : "▶️ Playing");
    }
  } else if (action.type === 'volume') {
    if (action.action === 'up') {
      adjustRadioVolume(5);
    } else if (action.action === 'down') {
      adjustRadioVolume(-5);
    } else if (action.action === 'mute') {
      toggleAudioMute();
    }
  } else if (action.type === 'rum_walk') {
    if (action.target === 'balcony' && typeof walkRumOutsideToBalcony === 'function') {
      walkRumOutsideToBalcony();
    } else if (action.target === 'inside' && typeof walkRumInsideRoom === 'function') {
      walkRumInsideRoom();
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

  // Do not duplicate chat replies or boot-stage audio milestones into user conversational chat
  if (src === 'CHAT' || src === 'INSTANT_BOOT' || src === 'NEURAL_BOOT') return;

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

      // Remote browser audio is streamed sequentially via SSE speech_seq -> /api/audio/speech_clip
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
  setMediaDuckState(true);

  if (currentScreen !== 'ai') {
    handleSpeechAutoShotgun(text, Math.max(2200, (text.length / 9.5) * 1000 + 400));
  }

  if (emotion) {
    setWaifuEmotion(emotion);
  }

  // Fallback timer only if SSE stream is disconnected
  const estimatedDurationMs = Math.max(2200, (text.length / 9.5) * 1000 + 300);
  rumGazeRetentionUntil = Math.max(rumGazeRetentionUntil, Date.now() + estimatedDurationMs + 9000);
  if (!eventSource || eventSource.readyState !== 1) {
    waifuSpeechEndTime = Date.now() + estimatedDurationMs;
    setTimeout(() => { if (!isHardwareSpeaking) setMediaDuckState(false); }, estimatedDurationMs);
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

  // 3. Fallback browser SpeechSynthesis ONLY for offline desktop browser preview (not on live Pi backend)
  const isDevPreview = window.location.protocol === 'file:';
  if (isDevPreview && 'speechSynthesis' in window) {
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

// --- HANDS-FREE WAKE WORD & LIVE CONVERSATION ENGINE (BACKEND PIPEWIRE USB MIC + PC BROWSER AUDIO/MIC BRIDGE) ---
let isWakeWordEnabled = true;
let isLiveConvoMode = false;
let isVoiceRecording = false;

// PC Remote Browser Audio & Microphone Bridge (auto-enabled on http:// laptop sessions, off on Pi 5 file:// kiosk)
let isPcAudioMode = (() => {
  try {
    const saved = localStorage.getItem('carpi5_pc_audio');
    if (saved !== null) return saved === 'true';
  } catch (e) {}
  return window.location.protocol !== 'file:';
})();
let _pcSpeechInitialized = false;
let _pcSpeechLastSeq = 0;
let _pcSpeechQueue = [];
let _pcSpeechPlaying = false;
let _pcAudioEl = null;
let _pcMicActive = false;
let _pcMicStream = null;
let _pcMicCtx = null;
let _pcMicSource = null;
let _pcMicProc = null;
let _pcMicChunks = [];
let _pcMicInSpeech = false;
let _pcMicSilenceFrames = 0;
let _pcMicNoiseRms = 0.01;
let _pcMicSampleRate = 48000;

function syncPcAudioButton() {
  const btn = document.getElementById('btnPcVoiceBridge');
  if (!btn) return;
  if (isPcAudioMode) {
    btn.classList.add('active');
    btn.innerText = '💻 PC AUDIO: ON';
    btn.style.color = '#38bdf8';
    btn.style.borderColor = '#38bdf8';
  } else {
    btn.classList.remove('active');
    btn.innerText = '💻 PC AUDIO: OFF';
    btn.style.color = '';
    btn.style.borderColor = '';
  }
}

function togglePcAudioMode() {
  isPcAudioMode = !isPcAudioMode;
  try { localStorage.setItem('carpi5_pc_audio', String(isPcAudioMode)); } catch (e) {}
  syncPcAudioButton();
  if (!isPcAudioMode) {
    _pcSpeechQueue = [];
    if (_pcAudioEl) {
      try { _pcAudioEl.pause(); } catch (e) {}
    }
    _pcSpeechPlaying = false;
    if (_pcMicActive) stopPcMicCapture(false);
    showAiSpeechToast('🔇 PC Audio/Mic OFF (Using Pi 5 speakers & USB mic).');
  } else {
    _playNextPcSpeechClip();
    showAiSpeechToast('💻 PC Audio/Mic ON! Tap 🎙️ to speak via your laptop mic & hear R.U.M. on your speakers.');
  }
}

function resetPcSpeechStreamBaseline() {
  _pcSpeechInitialized = false;
  _pcSpeechQueue = [];
}

function handleRemoteSpeechSeq(seq) {
  if (!seq || typeof seq !== 'number') return;
  if (!_pcSpeechInitialized) {
    _pcSpeechInitialized = true;
    _pcSpeechLastSeq = seq;
    return;
  }
  if (seq <= _pcSpeechLastSeq) return;
  if (!isPcAudioMode) {
    _pcSpeechLastSeq = seq;
    return;
  }
  const startSeq = Math.max(_pcSpeechLastSeq + 1, seq - 4);
  for (let s = startSeq; s <= seq; s++) {
    _pcSpeechQueue.push(s);
  }
  _pcSpeechLastSeq = seq;
  _playNextPcSpeechClip();
}

function _playNextPcSpeechClip() {
  if (!isPcAudioMode || _pcSpeechPlaying || _pcSpeechQueue.length === 0) return;
  const nextSeq = _pcSpeechQueue.shift();
  _pcSpeechPlaying = true;
  const audio = new Audio(`/api/audio/speech_clip?seq=${nextSeq}&t=${Date.now()}`);
  _pcAudioEl = audio;
  const done = () => {
    _pcSpeechPlaying = false;
    _playNextPcSpeechClip();
  };
  audio.onended = done;
  audio.onerror = done;
  audio.play().catch(err => {
    console.log('[PC AUDIO] Waiting for user tap to unlock browser playback:', err.name || err);
    _pcSpeechQueue.unshift(nextSeq);
    _pcSpeechPlaying = false;
  });
}

function _unlockPcAudioOnce() {
  if (isPcAudioMode && !_pcSpeechPlaying && _pcSpeechQueue.length > 0) {
    _playNextPcSpeechClip();
  }
}
window.addEventListener('pointerdown', _unlockPcAudioOnce, { passive: true });
window.addEventListener('keydown', _unlockPcAudioOnce, { passive: true });

function _encodeWav16kMono(floatSamples, inputRate) {
  const ratio = Math.max(1, inputRate / 16000);
  const outLen = Math.floor(floatSamples.length / ratio);
  const pcm = new Int16Array(outLen);
  for (let i = 0; i < outLen; i++) {
    const srcIdx = Math.min(floatSamples.length - 1, Math.floor(i * ratio));
    const s = Math.max(-1, Math.min(1, floatSamples[srcIdx]));
    pcm[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
  }
  const buf = new ArrayBuffer(44 + pcm.length * 2);
  const view = new DataView(buf);
  const writeStr = (off, str) => { for (let i = 0; i < str.length; i++) view.setUint8(off + i, str.charCodeAt(i)); };
  writeStr(0, 'RIFF');
  view.setUint32(4, 36 + pcm.length * 2, true);
  writeStr(8, 'WAVE');
  writeStr(12, 'fmt ');
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true);
  view.setUint16(22, 1, true);
  view.setUint32(24, 16000, true);
  view.setUint32(28, 32000, true);
  view.setUint16(32, 2, true);
  view.setUint16(34, 16, true);
  writeStr(36, 'data');
  view.setUint32(40, pcm.length * 2, true);
  for (let i = 0; i < pcm.length; i++) {
    view.setInt16(44 + i * 2, pcm[i], true);
  }
  return new Blob([buf], { type: 'audio/wav' });
}

function _flushPcMicUtterance() {
  if (_pcMicChunks.length === 0) return;
  let total = 0;
  for (const c of _pcMicChunks) total += c.length;
  const merged = new Float32Array(total);
  let off = 0;
  for (const c of _pcMicChunks) {
    merged.set(c, off);
    off += c.length;
  }
  _pcMicChunks = [];
  _pcMicInSpeech = false;
  _pcMicSilenceFrames = 0;

  if (merged.length < _pcMicSampleRate * 0.35) return;
  const wavBlob = _encodeWav16kMono(merged, _pcMicSampleRate);
  fetch('/api/ai/transcribe', {
    method: 'POST',
    headers: { 'Content-Type': 'audio/wav' },
    body: wavBlob
  })
    .then(r => r.json())
    .then(data => {
      const txt = (data && data.text || '').trim();
      if (txt) {
        console.log('[PC MIC] Transcribed:', txt);
        handleSpokenTranscript(txt, true);
      }
    })
    .catch(err => console.warn('[PC MIC] Transcribe error:', err));
}

async function startPcMicCapture() {
  if (_pcMicActive) return;
  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
    showAiSpeechToast('⚠️ Laptop mic requires http://localhost:8080 (secure origin) and microphone permission.');
    return;
  }
  try {
    const stream = await navigator.mediaDevices.getUserMedia({
      audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true }
    });
    const AudioCtx = window.AudioContext || window.webkitAudioContext;
    const ctx = new AudioCtx();
    const source = ctx.createMediaStreamSource(stream);
    const proc = ctx.createScriptProcessor(4096, 1, 1);

    _pcMicStream = stream;
    _pcMicCtx = ctx;
    _pcMicSource = source;
    _pcMicProc = proc;
    _pcMicSampleRate = ctx.sampleRate || 48000;
    _pcMicChunks = [];
    _pcMicInSpeech = false;
    _pcMicSilenceFrames = 0;
    _pcMicNoiseRms = 0.01;
    _pcMicActive = true;

    const preRoll = [];
    const maxPreRoll = 3;
    const framesPerChunk = 4096 / _pcMicSampleRate;
    const maxSilenceChunks = Math.max(4, Math.round(0.75 / framesPerChunk));
    const maxSpeechChunks = Math.max(25, Math.round(7.5 / framesPerChunk));

    proc.onaudioprocess = (ev) => {
      if (!_pcMicActive) return;
      // Pause capture while R.U.M. is speaking on laptop speakers so she doesn't hear herself
      if (_pcSpeechPlaying || isHardwareSpeaking) {
        _pcMicInSpeech = false;
        _pcMicChunks = [];
        preRoll.length = 0;
        return;
      }
      const input = ev.inputBuffer.getChannelData(0);
      const copy = new Float32Array(input);
      let sumSq = 0;
      for (let i = 0; i < copy.length; i++) sumSq += copy[i] * copy[i];
      const rms = Math.sqrt(sumSq / copy.length);

      if (!_pcMicInSpeech) {
        if (rms < 0.06) _pcMicNoiseRms = (_pcMicNoiseRms * 0.92) + (rms * 0.08);
        const trig = Math.max(0.015, _pcMicNoiseRms * 2.2);
        preRoll.push(copy);
        if (preRoll.length > maxPreRoll) preRoll.shift();
        if (rms >= trig) {
          _pcMicInSpeech = true;
          _pcMicSilenceFrames = 0;
          _pcMicChunks = preRoll.slice();
        }
      } else {
        _pcMicChunks.push(copy);
        const keep = Math.max(0.012, _pcMicNoiseRms * 1.7);
        if (rms < keep) _pcMicSilenceFrames++;
        else _pcMicSilenceFrames = 0;
        if (_pcMicSilenceFrames >= maxSilenceChunks || _pcMicChunks.length >= maxSpeechChunks) {
          _flushPcMicUtterance();
        }
      }
    };

    source.connect(proc);
    proc.connect(ctx.destination);
    syncVoiceButtonState(true, true, isWakeWordEnabled);
    showAiSpeechToast('🎙️ Laptop Mic LIVE! Speak to R.U.M. anytime — pause briefly to send.');
  } catch (err) {
    console.error('[PC MIC] Permission/init error:', err);
    showAiSpeechToast('⚠️ Could not open laptop microphone: ' + (err.message || err));
    stopPcMicCapture(false);
  }
}

function stopPcMicCapture(flushPending = true) {
  if (flushPending && _pcMicInSpeech) {
    _flushPcMicUtterance();
  }
  _pcMicActive = false;
  _pcMicInSpeech = false;
  _pcMicChunks = [];
  if (_pcMicProc) { try { _pcMicProc.disconnect(); } catch (e) {} _pcMicProc = null; }
  if (_pcMicSource) { try { _pcMicSource.disconnect(); } catch (e) {} _pcMicSource = null; }
  if (_pcMicCtx) { try { _pcMicCtx.close(); } catch (e) {} _pcMicCtx = null; }
  if (_pcMicStream) {
    try { _pcMicStream.getTracks().forEach(t => t.stop()); } catch (e) {}
    _pcMicStream = null;
  }
  syncVoiceButtonState(false, false, isWakeWordEnabled);
}

function initSpeechRecognition() {
  // Backend PipeWire USB microphone daemon is always active on Pi 5; sync PC audio bridge button too.
  syncPcAudioButton();
  const btn = document.getElementById('btnWakeWord');
  if (btn) btn.style.display = 'inline-flex';
  const cBtn = document.getElementById('btnLiveConvo');
  if (cBtn) cBtn.style.display = 'inline-flex';
}

function syncVoiceButtonState(convoActive, micCapturing, wakeEnabled) {
  if (_pcMicActive && !convoActive) {
    // Keep laptop mic's red active state intact while Pi 5 USB mic is idle
    convoActive = true;
    micCapturing = true;
  }
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
    btn.title = _pcMicActive
      ? "Laptop Microphone LIVE (Speak to R.U.M.! Tap to stop)"
      : "Live Voice Conversation Active (Speak freely to Rum! Tap to stop)";
  } else {
    btn.innerHTML = "🎙️";
    btn.classList.remove('recording');
    btn.style.borderColor = "";
    btn.style.boxShadow = "";
    btn.style.background = "";
    btn.title = isPcAudioMode
      ? "Speak to R.U.M. via Laptop Microphone"
      : "Toggle Live Voice Conversation Mode (USB Mic)";
  }
}

async function toggleLiveConversationMode() {
  if (isPcAudioMode) {
    if (_pcMicActive) {
      stopPcMicCapture(true);
      showAiSpeechToast('🎙️ Laptop Mic paused.');
    } else {
      await startPcMicCapture();
    }
    return;
  }
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
    'hey ram', 'hi ram', 'hello ram', 'okay ram', 'ok ram', 'ram',
    'hey rem', 'hi rem', 'hello rem', 'okay rem', 'ok rem', 'rem',
    'hey ron', 'hi ron', 'hello ron', 'okay ron', 'ok ron', 'ron',
    'hey run', 'hi run', 'hello run', 'okay run', 'ok run', 'run',
    'hey rob', 'hi rob', 'hello rob', 'okay rob', 'ok rob', 'rob',
    'hey rome', 'hi rome', 'hello rome', 'okay rome', 'rome',
    'hey room', 'hi room', 'hello room', 'okay room', 'room',
    'hey drum', 'hi drum', 'hello drum', 'drum',
    'r.u.m.', 'r.u.m'
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

  // =========================================================================
  // PHASE 16: VOICE INTENT AUTO-ACTUATION & COCKPIT BUS
  // =========================================================================
  // 1. In-Dash Audio Volume Controls
  if (cleanCmd.includes('volume up') || cleanCmd.includes('louder') || cleanCmd.includes('turn up') || cleanCmd.includes('turn it up')) {
    fetch('/api/cockpit/action', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ command: 'volume_up' })
    }).catch(() => {});
    const reply = "Turning it up for you, Dad!";
    appendChatMessage('user', rawText);
    appendChatMessage('assistant', reply);
    speakUtterance(reply);
    return;
  }
  if (cleanCmd.includes('volume down') || cleanCmd.includes('quieter') || cleanCmd.includes('turn down') || cleanCmd.includes('turn it down')) {
    fetch('/api/cockpit/action', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ command: 'volume_down' })
    }).catch(() => {});
    const reply = "Turned the volume down, Dad.";
    appendChatMessage('user', rawText);
    appendChatMessage('assistant', reply);
    speakUtterance(reply);
    return;
  }
  if (cleanCmd.includes('mute') && !cleanCmd.includes('unmute')) {
    fetch('/api/cockpit/action', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ command: 'mute' })
    }).catch(() => {});
    const reply = "Audio muted, Dad.";
    appendChatMessage('user', rawText);
    appendChatMessage('assistant', reply);
    speakUtterance(reply);
    return;
  }
  if (cleanCmd.includes('unmute')) {
    fetch('/api/cockpit/action', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ command: 'unmute' })
    }).catch(() => {});
    const reply = "Audio unmuted, Dad!";
    appendChatMessage('user', rawText);
    appendChatMessage('assistant', reply);
    speakUtterance(reply);
    return;
  }
  // 2. Cockpit Lighting & Obsidian Midnight Auto-Dimming
  if (cleanCmd.includes('night mode') || cleanCmd.includes('dark mode') || cleanCmd.includes('obsidian') || cleanCmd.includes('dim screen')) {
    fetch('/api/cockpit/action', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ command: 'night_mode' })
    }).catch(() => {});
    if (document.body) document.body.classList.add('obsidian-midnight');
    const reply = "Switching to Obsidian Midnight mode, easier on your eyes Dad!";
    appendChatMessage('user', rawText);
    appendChatMessage('assistant', reply);
    speakUtterance(reply);
    return;
  }
  if (cleanCmd.includes('day mode') || cleanCmd.includes('light mode') || cleanCmd.includes('brighten screen')) {
    fetch('/api/cockpit/action', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ command: 'day_mode' })
    }).catch(() => {});
    if (document.body) document.body.classList.remove('obsidian-midnight');
    const reply = "Day mode active, Dad!";
    appendChatMessage('user', rawText);
    appendChatMessage('assistant', reply);
    speakUtterance(reply);
    return;
  }
  // 3. Media Playback Auto-Actuation
  if (cleanCmd.includes('play music') || cleanCmd.includes('resume music') || cleanCmd.includes('play song') || cleanCmd.includes('start music')) {
    fetch('/api/media/player/control', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action: 'play' })
    }).catch(() => {});
    const reply = "Playing your music, Dad!";
    appendChatMessage('user', rawText);
    appendChatMessage('assistant', reply);
    speakUtterance(reply);
    return;
  }
  if (cleanCmd.includes('pause music') || cleanCmd.includes('pause audio') || cleanCmd.includes('stop music')) {
    fetch('/api/media/player/control', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action: 'pause' })
    }).catch(() => {});
    const reply = "Paused the music, Dad.";
    appendChatMessage('user', rawText);
    appendChatMessage('assistant', reply);
    speakUtterance(reply);
    return;
  }
  if (cleanCmd.includes('next song') || cleanCmd.includes('next track') || cleanCmd.includes('skip song') || cleanCmd.includes('skip track')) {
    fetch('/api/media/player/control', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action: 'next' })
    }).catch(() => {});
    const reply = "Skipping to the next track, Dad!";
    appendChatMessage('user', rawText);
    appendChatMessage('assistant', reply);
    speakUtterance(reply);
    return;
  }
  if (cleanCmd.includes('previous song') || cleanCmd.includes('prev song') || cleanCmd.includes('previous track') || cleanCmd.includes('prev track')) {
    fetch('/api/media/player/control', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action: 'prev' })
    }).catch(() => {});
    const reply = "Going back to the previous track!";
    appendChatMessage('user', rawText);
    appendChatMessage('assistant', reply);
    speakUtterance(reply);
    return;
  }
  // 4. In-Dash Screen Navigation
  if (cleanCmd.includes('canyon') || cleanCmd.includes('lap timer') || cleanCmd.includes('sector split') || cleanCmd.includes('pinal pass')) {
    navigateTo('canyon');
    const reply = "Opening Canyon Run and Thermal Studio, Dad!";
    appendChatMessage('user', rawText);
    appendChatMessage('assistant', reply);
    speakUtterance(reply);
    return;
  }
  if (cleanCmd.includes('open media') || cleanCmd.includes('show media') || cleanCmd.includes('music hub') || cleanCmd.includes('audio studio')) {
    navigateTo('media');
    const reply = "Opening Entertainment and Media Hub, Dad!";
    appendChatMessage('user', rawText);
    appendChatMessage('assistant', reply);
    speakUtterance(reply);
    return;
  }
  if (cleanCmd.includes('phone') || cleanCmd.includes('dialer') || cleanCmd.includes('contacts') || cleanCmd.includes('call log')) {
    navigateTo('phone');
    const reply = "Opening In-Cabin Phone Studio, Dad!";
    appendChatMessage('user', rawText);
    appendChatMessage('assistant', reply);
    speakUtterance(reply);
    return;
  }
  if (cleanCmd.includes('reset trip') || cleanCmd.includes('clear trip')) {
    fetch('/api/cockpit/action', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ command: 'reset_trip' })
    }).catch(() => {});
    const reply = "Trip meters cleared to zero, Dad!";
    appendChatMessage('user', rawText);
    appendChatMessage('assistant', reply);
    speakUtterance(reply);
    return;
  }
  // 5. Direct Vehicle Telemetry Queries
  if (cleanCmd.includes('where are we') || cleanCmd.includes('where am i') || cleanCmd.includes('location') || cleanCmd.includes('coordinates') || cleanCmd.includes('what road') || cleanCmd.includes('heading')) {
    navigateTo('maps');
    if (typeof recenterMap === 'function') recenterMap();
    let reply = "Waiting for satellite lock, Dad! Searching for GPS satellites above.";
    if (currentGpsData && currentGpsData.fix && currentGpsData.lat && currentGpsData.lon) {
      const lat = currentGpsData.lat.toFixed(4);
      const lon = Math.abs(currentGpsData.lon).toFixed(4);
      const alt = currentGpsData.altitude_ft ? Math.round(currentGpsData.altitude_ft) : 0;
      const card = currentGpsData.heading_cardinal || 'North';
      const spd = Math.round(currentGpsData.speed_mph || (latestTelemetry && latestTelemetry.speed_mph) || 0);
      reply = `We are cruising at ${spd} MPH, heading ${card} at ${alt} feet elevation. Coordinates: ${lat}°N, ${lon}°W!`;
    }
    appendChatMessage('user', rawText);
    appendChatMessage('assistant', reply);
    speakUtterance(reply);
    return;
  }
  if (cleanCmd.includes('map') || cleanCmd.includes('navigation') || cleanCmd.includes('gps') || cleanCmd.includes('route') || cleanCmd.includes('nav')) {
    navigateTo('maps');
    if (typeof recenterMap === 'function') recenterMap();
    const reply = "Switching to Cockpit Navigation! Offline Arizona map is active.";
    appendChatMessage('user', rawText);
    appendChatMessage('assistant', reply);
    speakUtterance(reply);
    return;
  }
  if (cleanCmd.includes('drag') || cleanCmd.includes('christmas tree') || cleanCmd.includes('launch control') || cleanCmd.includes('staging') || cleanCmd.includes('quarter mile')) {
    navigateTo('dragy');
    const reply = "Opening Drag Launch Control and Christmas Tree staging, Dad!";
    appendChatMessage('user', rawText);
    appendChatMessage('assistant', reply);
    speakUtterance(reply);
    return;
  }
  if (cleanCmd.includes('g force') || cleanCmd.includes('g-force') || cleanCmd.includes('lateral g') || cleanCmd.includes('friction circle')) {
    let latG = "0.00";
    let longG = "0.00";
    if (currentGpsData && currentGpsData.g_forces) {
      latG = (currentGpsData.g_forces.lateral || 0).toFixed(2);
      longG = (currentGpsData.g_forces.longitudinal || 0).toFixed(2);
    }
    const reply = `Live lateral cornering force is ${latG} Gs, longitudinal acceleration is ${longG} Gs, Dad!`;
    appendChatMessage('user', rawText);
    appendChatMessage('assistant', reply);
    speakUtterance(reply);
    return;
  }
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
    const dancePool = ['dance_side_groove', 'dance_rumba', 'dance_ontop', 'dance_headdrop', 'dance_pushback', 'joy', 'amusement'];
    const chosen = dancePool[Math.floor(Math.random() * dancePool.length)];
    playVrmAction(chosen, 5500, false);
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

// Master Animation Registry & Dynamic Drawer System (135+ BVH & VRMA Animations)
let vrmCurrentAnimCategory = 'all';
let vrmCurrentAnimSearch = '';

function openAnimationsDrawer() {
  const m = document.getElementById('animationsDrawerModal');
  if (m) {
    m.style.display = 'flex';
    renderAnimationsDrawer();
  }
}

function toggleAnimationsDrawer() {
  const m = document.getElementById('animationsDrawerModal');
  if (!m) return;
  if (m.style.display === 'flex') {
    closeAnimationsDrawer();
  } else {
    openAnimationsDrawer();
  }
}

function closeAnimationsDrawer() {
  const m = document.getElementById('animationsDrawerModal');
  if (m) m.style.display = 'none';
}

function filterAnimationCategory(cat, btnEl) {
  vrmCurrentAnimCategory = cat || 'all';
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
  renderAnimationsDrawer();
}

function handleAnimSearch(query) {
  vrmCurrentAnimSearch = (query || '').toLowerCase().trim();
  renderAnimationsDrawer();
}

function clearAnimSearch() {
  const input = document.getElementById('animSearchInput');
  if (input) input.value = '';
  vrmCurrentAnimSearch = '';
  renderAnimationsDrawer();
}

function getAnimCategoryAndMeta(key, isVrma) {
  const k = key.toLowerCase();
  let emoji = '🎭';
  let cat = 'motion';
  let label = key.replace(/_/g, ' ').replace(/-/g, ' ');
  label = label.replace(/^(action|pose|dance|exercise|hitarea|reaction)\s+/i, '');
  label = label.charAt(0).toUpperCase() + label.slice(1);
  if (k.includes('dance') || k.includes('rumba') || k.includes('spin') || k.includes('twist') || k.includes('step') || k.includes('groove') || k.includes('bubble_pop') || k.includes('level_up') || k.includes('dipping')) {
    cat = 'dance';
    emoji = '💃';
  } else if (k.includes('hit') || k.includes('reaction_groin') || k.includes('reaction_head')) {
    cat = 'combat';
    emoji = '💥';
  } else if (k.includes('exercise') || k.includes('crunch') || k.includes('jog') || k.includes('squat')) {
    cat = 'exercise';
    emoji = '🏃';
  } else if (k.includes('idle') || k.includes('sit') || k.includes('kneel') || k.includes('laying') || k.includes('rest') || k.includes('sunbathing') || k.includes('akimbo')) {
    cat = 'idles';
    emoji = '🛋️';
  } else if (k.includes('walk') || k.includes('crouch') || k.includes('standup') || k.includes('crawling') || k.includes('picking') || k.includes('jump') || k.includes('pat') || k.includes('gaming') || k.includes('action') || k.includes('hopscotch') || k.includes('superman') || k.includes('turn') || k.includes('run')) {
    cat = 'motion';
    emoji = '🚶';
  } else if (k.includes('pose') || k.includes('peace') || k.includes('shoot') || k.includes('model') || k.includes('greeting') || k.includes('show') || k.includes('wave') || k.includes('bow') || k.includes('nails')) {
    cat = 'poses';
    emoji = '✨';
  } else {
    const emotions = [
      'admiration', 'amusement', 'anger', 'annoyance', 'approval', 'caring', 'confusion',
      'curiosity', 'desire', 'disappointment', 'disapproval', 'disgust', 'embarrassment',
      'excitement', 'fear', 'gratitude', 'grief', 'joy', 'love', 'nervousness', 'optimism',
      'pride', 'realization', 'relief', 'remorse', 'sadness', 'surprise', 'neutral'
    ];
    for (let e of emotions) {
      if (k.includes(e)) {
        cat = 'reactions';
        emoji = '😊';
        break;
      }
    }
  }
  // Specific custom emoji mappings
  if (k.includes('gangnam')) emoji = '🕶️';
  if (k.includes('hiphop')) emoji = '🎧';
  if (k.includes('dab')) emoji = '🤙';
  if (k.includes('peace')) emoji = '✌️';
  if (k.includes('shoot')) emoji = '👉';
  if (k.includes('love')) emoji = '💖';
  if (k.includes('joy')) emoji = '😄';
  if (k.includes('anger')) emoji = '😡';
  if (k.includes('sadness')) emoji = '😢';
  if (k.includes('fear')) emoji = '😱';
  if (k.includes('laugh') || k.includes('amusement')) emoji = '😂';
  if (k.includes('crunches') || k.includes('crunch')) emoji = '💪';
  if (k.includes('jump')) emoji = '🦘';
  if (k.includes('crawl')) emoji = '🐛';
  if (k.includes('gaming')) emoji = '🎮';
  if (k.includes('sunbathing')) emoji = '🏖️';
  if (k.includes('groin')) emoji = '⚡';
  if (k.includes('headshot') || k.includes('head')) emoji = '🤕';
  if (k.includes('bubble_pop')) emoji = '🫧';
  if (k.includes('happy_dance')) emoji = '🥳';
  if (k.includes('level_up')) emoji = '⬆️';
  if (k.includes('polish_nails')) emoji = '💅';
  if (k.includes('bow')) emoji = '🙇‍♀️';
  if (k.includes('reading')) emoji = '📖';
  if (k.includes('frog')) emoji = '🐸';
  if (k.includes('superman')) emoji = '🦸‍♀️';
  if (k.includes('tiptoe')) emoji = '🩰';
  return { cat, emoji, label };
}

function getMasterAnimationsCatalog() {
  const master = [];
  const seen = new Set();
  // 1. All VRMA files
  if (typeof VRMA_MOTION_FILES !== 'undefined') {
    Object.keys(VRMA_MOTION_FILES).forEach(key => {
      const info = VRMA_MOTION_FILES[key];
      const { cat, emoji, label } = getAnimCategoryAndMeta(key, true);
      if (!seen.has(key)) {
        seen.add(key);
        master.push({
          key,
          file: info.file,
          type: 'VRMA',
          cat,
          emoji,
          label: info.label || label
        });
      }
    });
  }
  // 2. All BVH files from vrmBvhCatalog
  if (typeof vrmBvhCatalog !== 'undefined') {
    Object.keys(vrmBvhCatalog).forEach(key => {
      const fn = vrmBvhCatalog[key];
      if (!seen.has(key)) {
        seen.add(key);
        const { cat, emoji, label } = getAnimCategoryAndMeta(key, false);
        master.push({
          key,
          file: fn,
          type: 'BVH',
          cat,
          emoji,
          label
        });
      }
    });
  }
  return master;
}

function renderAnimationsDrawer() {
  const container = document.getElementById('animGridContainer');
  if (!container) return;
  const master = getMasterAnimationsCatalog();
  const search = vrmCurrentAnimSearch;
  const currentCat = vrmCurrentAnimCategory;
  // Update Category Counts in UI Tabs
  const counts = { all: master.length, poses: 0, dance: 0, reactions: 0, motion: 0, exercise: 0, combat: 0, idles: 0 };
  master.forEach(item => {
    if (counts[item.cat] !== undefined) counts[item.cat]++;
  });
  const countAllEl = document.getElementById('animCountAll');
  if (countAllEl) countAllEl.textContent = counts.all;
  const headerCountEl = document.getElementById('animHeaderCount');
  if (headerCountEl) headerCountEl.textContent = `(${counts.all})`;
  const countPosesEl = document.getElementById('animCountPoses');
  if (countPosesEl) countPosesEl.textContent = counts.poses;
  const countDanceEl = document.getElementById('animCountDance');
  if (countDanceEl) countDanceEl.textContent = counts.dance;
  const countReactionsEl = document.getElementById('animCountReactions');
  if (countReactionsEl) countReactionsEl.textContent = counts.reactions;
  const countMotionEl = document.getElementById('animCountMotion');
  if (countMotionEl) countMotionEl.textContent = counts.motion;
  const countExerciseEl = document.getElementById('animCountExercise');
  if (countExerciseEl) countExerciseEl.textContent = counts.exercise;
  const countCombatEl = document.getElementById('animCountCombat');
  if (countCombatEl) countCombatEl.textContent = counts.combat;
  const countIdlesEl = document.getElementById('animCountIdles');
  if (countIdlesEl) countIdlesEl.textContent = counts.idles;
  // Filter items
  const filtered = master.filter(item => {
    const matchesCat = (currentCat === 'all' || item.cat === currentCat);
    if (!matchesCat) return false;
    if (!search) return true;
    return (
      item.key.toLowerCase().includes(search) ||
      item.label.toLowerCase().includes(search) ||
      item.cat.toLowerCase().includes(search) ||
      item.type.toLowerCase().includes(search)
    );
  });
  if (filtered.length === 0) {
    container.innerHTML = `

      <div style="grid-column: 1 / -1; text-align:center; padding:30px 10px; color:var(--text-secondary); font-size:13px;">

        No animations match "<strong>${search}</strong>" in ${currentCat.toUpperCase()}.<br/>

        <button onclick="clearAnimSearch()" style="margin-top:10px; padding:6px 14px; background:rgba(255,255,255,0.1); border:1px solid #556; border-radius:6px; color:#fff; cursor:pointer;">Clear Search</button>

      </div>

    `;
    return;
  }
  container.innerHTML = filtered.map(item => {
    return `

      <button class="anim-card-btn" data-cat="${item.cat}" onclick="triggerDrawerAnim('${item.key}')" title="${item.label}" style="display:flex; flex-direction:column; align-items:center; justify-content:center; gap:6px; padding:12px 10px; background:rgba(255,255,255,0.06); border:1px solid rgba(255,255,255,0.12); border-radius:12px; cursor:pointer; transition:all 0.15s ease; min-height:86px; text-align:center; box-sizing:border-box;">

        <span class="anim-card-emoji" style="font-size:28px; line-height:1.1;">${item.emoji}</span>

        <span class="anim-card-name" style="font-size:13px; font-weight:800; color:#ffffff; line-height:1.25; word-break:break-word; max-width:100%; display:-webkit-box; -webkit-line-clamp:2; -webkit-box-orient:vertical; overflow:hidden;">${item.label}</span>

      </button>

    `;
  }).join('');
}

function triggerDrawerAnim(actionKey) {
  playVrmAction(actionKey, 4800, false);
  const m = document.getElementById('animationsDrawerModal');
  if (m) m.style.display = 'none';
  showAiSpeechToast(`Playing animation: ${actionKey}`);
}

function openVoiceCommandsModal() {
  const m = document.getElementById('voiceCommandsModal');
  if (m) m.style.display = 'flex';
}

function closeVoiceCommandsModal() {
  const m = document.getElementById('voiceCommandsModal');
  if (m) m.style.display = 'none';
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

// ==========================================

// R.U.M. VOICE SPEECH CACHE CONTROLLER

// ==========================================

let pendingDownsizeTier = null;

function loadTtsCacheStats() {

  fetch('/api/audio/cache')

    .then(r => r.json())

    .then(data => {

      if (!data || !data.cache) return;

      const c = data.cache;

      const limText = document.getElementById('ttsCacheLimitText');

      const usedText = document.getElementById('ttsCacheUsedText');

      const pctText = document.getElementById('ttsCachePctText');

      const countText = document.getElementById('ttsCacheCountText');

      const hitsText = document.getElementById('ttsCacheHitsText');

      const bar = document.getElementById('ttsCacheProgressBar');

      const limMb = c.limit_mb || 1024;

      const usedMb = c.total_mb || 0.0;

      const pct = c.usage_pct || 0.0;

      if (limText) limText.innerText = limMb >= 1024 ? `${(limMb / 1024).toFixed(0)} GB` : `${limMb} MB`;

      if (usedText) usedText.innerText = `${usedMb.toFixed(1)} MB`;

      if (pctText) pctText.innerText = `${pct.toFixed(1)}%`;

      if (countText) countText.innerText = c.total_phrases || 0;

      if (hitsText) hitsText.innerText = c.total_hits || 0;

      if (bar) bar.style.width = `${Math.min(100, Math.max(2, pct))}%`;

      // Update tier buttons active state

      document.querySelectorAll('#ttsCacheTierButtons .cache-tier-btn').forEach(btn => {

        const mb = parseInt(btn.getAttribute('data-mb'), 10);

        if (mb === limMb) {

          btn.style.background = "var(--accent-pink)";

          btn.style.color = "#000";

          btn.style.fontWeight = "900";

        } else {

          btn.style.background = "transparent";

          btn.style.color = "#c7d5e4";

          btn.style.fontWeight = "700";

        }

      });

    })

    .catch(e => console.warn("[TTS CACHE] Stats fetch error:", e));

}

function onSelectTtsCacheTier(targetMb) {

  fetch('/api/audio/cache/limit', {

    method: 'POST',

    headers: { 'Content-Type': 'application/json' },

    body: JSON.stringify({ limit_mb: targetMb, dry_run: true })

  })

    .then(r => r.json())

    .then(d => {

      if (d.impact && d.impact.needs_prune) {

        pendingDownsizeTier = targetMb;

        const desc = document.getElementById('ttsCacheWarningDesc');

        const targetStr = targetMb >= 1024 ? `${targetMb / 1024} GB` : `${targetMb} MB`;

        if (desc) {

          desc.innerHTML = `Your current speech cache uses <strong>${(d.impact.mb_to_delete + targetMb).toFixed(1)} MB</strong>. Lowering your reserve to <strong>${targetStr}</strong> will automatically prune approximately <strong>${d.impact.mb_to_delete} MB (${d.impact.phrases_to_delete} phrases)</strong> of older, least-frequently-used speech.<br><br>Frequently used phrases will be preserved. Proceed with downsize?`;

        }

        const m = document.getElementById('ttsCacheWarningModal');

        if (m) m.style.display = 'flex';

      } else {

        applyTtsCacheTier(targetMb);

      }

    })

    .catch(() => applyTtsCacheTier(targetMb));

}

function closeTtsCacheWarningModal() {

  const m = document.getElementById('ttsCacheWarningModal');

  if (m) m.style.display = 'none';

  pendingDownsizeTier = null;

}

function confirmTtsCacheDownsize() {

  if (pendingDownsizeTier) {

    applyTtsCacheTier(pendingDownsizeTier);

  }

  closeTtsCacheWarningModal();

}

function applyTtsCacheTier(targetMb) {

  fetch('/api/audio/cache/limit', {

    method: 'POST',

    headers: { 'Content-Type': 'application/json' },

    body: JSON.stringify({ limit_mb: targetMb, dry_run: false })

  })

    .then(r => r.json())

    .then(d => {

      loadTtsCacheStats();

      const targetStr = targetMb >= 1024 ? `${targetMb / 1024} GB` : `${targetMb} MB`;

      showAiSpeechToast(`Speech cache reserve set to ${targetStr}`);

    })

    .catch(e => console.error("Error setting cache limit:", e));

}

function clearTtsCache() {

  if (!confirm("Are you sure you want to clear all cached speech? Future responses will be re-synthesized.")) {

    return;

  }

  fetch('/api/audio/cache/clear', { method: 'POST' })

    .then(r => r.json())

    .then(d => {

      loadTtsCacheStats();

      showAiSpeechToast("Speech cache completely cleared");

    })

    .catch(e => console.error("Error clearing speech cache:", e));

}

// Phase 14: Voice Pre-Warming Suite Controls
let isTtsPrewarmPolling = false;

function triggerTtsPrewarm() {
  const btn = document.getElementById('btnTtsPrewarm');
  if (btn) {
    btn.disabled = true;
    btn.style.opacity = '0.6';
    btn.innerText = 'PRE-WARMING...';
  }
  const wrapper = document.getElementById('ttsPrewarmProgressWrapper');
  if (wrapper) wrapper.style.display = 'block';

  fetch('/api/tts/prewarm', { method: 'POST' })
    .then(res => res.json())
    .then(data => {
      startTtsPrewarmPolling();
    })
    .catch(err => {
      console.error('[TTS_PREWARM] Trigger failed:', err);
      if (btn) {
        btn.disabled = false;
        btn.style.opacity = '1.0';
        btn.innerText = '⚡ PRE-WARM VOICE';
      }
    });
}

function startTtsPrewarmPolling() {
  if (isTtsPrewarmPolling) return;
  isTtsPrewarmPolling = true;

  const pollInterval = setInterval(() => {
    fetch('/api/tts/prewarm')
      .then(res => res.json())
      .then(data => {
        const info = data.prewarm || {};
        const pct = info.pct || 0;
        const phrase = info.current_phrase || '';
        const isRunning = info.is_running;

        const pBar = document.getElementById('ttsPrewarmProgressBar');
        const pText = document.getElementById('ttsPrewarmPctText');
        const sText = document.getElementById('ttsPrewarmStatusText');
        const btn = document.getElementById('btnTtsPrewarm');

        if (pBar) pBar.style.width = pct + '%';
        if (pText) pText.innerText = pct + '%';
        if (sText) sText.innerText = phrase ? `Synthesizing: "${phrase}..."` : 'Pre-warming voice...';

        if (!isRunning && info.completed) {
          clearInterval(pollInterval);
          isTtsPrewarmPolling = false;
          if (sText) sText.innerText = '✅ Pre-warming complete! All phrases locked in RAM.';
          if (btn) {
            btn.disabled = false;
            btn.style.opacity = '1.0';
            btn.innerText = '⚡ PRE-WARM AGAIN';
          }
          if (typeof loadTtsCacheStats === 'function') {
            loadTtsCacheStats();
          }
        }
      })
      .catch(err => {
        clearInterval(pollInterval);
        isTtsPrewarmPolling = false;
      });
  }, 1000);
}

// Auto-load cache stats on boot
setTimeout(loadTtsCacheStats, 1500);
