// CarPi5 UI Module: Interactive Touch-First Persona Builder Wizard

let _pbMode = 'create'; // 'create' | 'edit'
let _pbActiveTab = 'identity';
let _pbDraft = {};
let _pbCatalogs = {
  personas: {},
  avatars: [],
  vrma: [],
  pics: [],
  voices: ['af_nicole', 'af_bella', 'af_heart', 'af_sky', 'af_nova', 'am_adam'],
  ackFolders: ['default']
};

const _PB_TOUCH_ZONES = [
  { key: 'head_top', label: 'Headpat' },
  { key: 'mouth', label: 'Face / Boop' },
  { key: 'shoulders', label: 'Shoulders' },
  { key: 'arms', label: 'Arms' },
  { key: 'hands', label: 'Hands' },
  { key: 'stomach', label: 'Tickle / Mid' },
  { key: 'legs', label: 'Legs' },
  { key: 'feet', label: 'Feet' },
  { key: 'back', label: 'Back / Peekaboo' },
  { key: 'butt', label: 'Butt (Adult Only)', adultOnly: true },
  { key: 'groin', label: 'Groin (Adult Only)', adultOnly: true }
];

function _pbHexToRgba(hex, alpha) {
  const m = /^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i.exec(String(hex || '').trim());
  if (!m) return `rgba(192, 132, 252, ${alpha})`;
  return `rgba(${parseInt(m[1], 16)}, ${parseInt(m[2], 16)}, ${parseInt(m[3], 16)}, ${alpha})`;
}

function _pbSlugId(nameOrId) {
  return String(nameOrId || '')
    .toUpperCase()
    .replace(/[^A-Z0-9_-]/g, '_')
    .replace(/^_+|_+$/g, '')
    .replace(/_+/g, '_')
    .slice(0, 32);
}

function _pbBuildDefaultDraft(templateId) {
  const pool = _pbCatalogs.personas || window.allPersonas || {};
  const tplKey = (templateId && pool[templateId]) ? templateId : (getDefaultPersonaId ? getDefaultPersonaId() : 'RUM');
  const base = JSON.parse(JSON.stringify(pool[tplKey] || {}));
  base.id = '';
  base.name = '';
  base.display_short_name = '';
  base.full_name = '';
  base.default = false;
  base.acknowledgments_folder = 'default';
  base.age_spirit = base.age_spirit || '8';
  if (!base.vrm_defaults) base.vrm_defaults = {};
  if (!base.vrm_defaults.model_file && _pbCatalogs.avatars.length > 0) {
    base.vrm_defaults.model_file = _pbCatalogs.avatars[0];
  }
  base.vrm_defaults.status_badge = '{persona_name} ACTIVE';
  base.vrm_defaults.card_title = '{persona_name}';
  base.vrm_defaults.hud_title = '{persona_name} • SHOTGUN';
  base.vrm_defaults.banner_quote = '{driver_address}! Ready to ride shotgun!';
  base.vrm_defaults.idle_overlay = 'Watching the road with you, {driver_address}!';
  return base;
}

async function openPersonaBuilder(mode = 'create', targetId = '') {
  _pbMode = (mode === 'edit') ? 'edit' : 'create';
  const modal = document.getElementById('personaBuilderModal');
  if (!modal) return;
  modal.style.display = 'flex';

  const statusEl = document.getElementById('pbStatusMsg');
  if (statusEl) statusEl.innerText = 'Loading voices, 3D avatars & animations...';

  try {
    const reqs = [
      fetch('/api/ai/personas').then(r => r.ok ? r.json() : {}).catch(() => ({})),
      fetch('/api/ai/voices').then(r => r.ok ? r.json() : {}).catch(() => ({})),
      fetch('/api/models/avatars').then(r => r.ok ? r.json() : []).catch(() => []),
      fetch('/api/models/vrma').then(r => r.ok ? r.json() : {}).catch(() => ({})),
      fetch('/api/assets/pics').then(r => r.ok ? r.json() : {}).catch(() => ({}))
    ];
    const activeTarget = targetId || (window.currentAiSettings && window.currentAiSettings.personality) || '';
    if (_pbMode === 'edit' && activeTarget) {
      reqs.push(
        fetch(`/api/ai/personas?id=${encodeURIComponent(activeTarget)}`)
          .then(r => r.ok ? r.json() : null)
          .catch(() => null)
      );
    }

    const [personasMap, voiceData, avatarList, vrmaData, picsData, targetResp] = await Promise.all(reqs);
    if (personasMap && typeof personasMap === 'object' && !personasMap.error) {
      _pbCatalogs.personas = personasMap;
    } else {
      _pbCatalogs.personas = window.allPersonas || {};
    }
    if (Array.isArray(voiceData.kokoro_voices) && voiceData.kokoro_voices.length > 0) {
      _pbCatalogs.voices = voiceData.kokoro_voices;
    }
    if (Array.isArray(voiceData.acknowledgments_folders) && voiceData.acknowledgments_folders.length > 0) {
      _pbCatalogs.ackFolders = voiceData.acknowledgments_folders;
    }
    _pbCatalogs.avatars = Array.isArray(avatarList)
      ? avatarList.map(a => (typeof a === 'string' ? a : a.name)).filter(Boolean)
      : [];
    _pbCatalogs.vrma = Array.isArray(vrmaData.files)
      ? vrmaData.files.map(f => f.action || String(f.name || '').replace(/\.vrma$/i, '')).filter(Boolean)
      : [];
    _pbCatalogs.pics = Array.isArray(picsData.pics) ? picsData.pics : ['assets/pics/splash.png'];

    if (_pbMode === 'edit' && targetResp && targetResp.persona) {
      _pbDraft = JSON.parse(JSON.stringify(targetResp.persona));
    } else if (_pbMode === 'edit' && activeTarget && _pbCatalogs.personas[activeTarget]) {
      _pbDraft = JSON.parse(JSON.stringify(_pbCatalogs.personas[activeTarget]));
    } else {
      _pbMode = 'create';
      _pbDraft = _pbBuildDefaultDraft(activeTarget);
    }

    _pbPopulateDropdownOptions();
    syncBuilderFormFromDraft();
    switchPersonaBuilderTab('identity');
    if (statusEl) statusEl.innerText = _pbMode === 'edit' ? `Editing ${_pbDraft.name || _pbDraft.id}` : 'New Persona Ready';
  } catch (err) {
    console.error('[PERSONA BUILDER] Init error:', err);
    if (statusEl) statusEl.innerText = 'Error loading catalogs: ' + (err.message || err);
  }
}

function closePersonaBuilder() {
  const modal = document.getElementById('personaBuilderModal');
  if (modal) modal.style.display = 'none';
}

function switchPersonaBuilderTab(tabKey) {
  _pbActiveTab = tabKey || 'identity';
  const tabs = ['identity', 'vrm', 'voice', 'dialogue'];
  tabs.forEach((k) => {
    const btn = document.getElementById(`pbTabBtn_${k}`);
    const pane = document.getElementById(`pbTabPane_${k}`);
    const active = (k === _pbActiveTab);
    if (btn) btn.classList.toggle('active', active);
    if (pane) pane.style.display = active ? 'block' : 'none';
  });
}

function _pbSetSelectOptions(el, items, currentVal, includeCustomFallback = true) {
  if (!el) return;
  const uniq = Array.from(new Set(items.filter(Boolean)));
  if (includeCustomFallback && currentVal && !uniq.includes(currentVal)) {
    uniq.unshift(currentVal);
  }
  el.innerHTML = uniq.map(v => `<option value="${escapeHtml(v)}">${escapeHtml(v)}</option>`).join('');
  if (currentVal !== undefined && currentVal !== null) {
    el.value = String(currentVal);
  }
}

function _pbPopulateDropdownOptions() {
  const tplSel = document.getElementById('pbTemplateSelect');
  if (tplSel) {
    const pool = _pbCatalogs.personas || {};
    tplSel.innerHTML = Object.keys(pool).map(k => {
      const p = pool[k];
      return `<option value="${escapeHtml(k)}">Clone: ${escapeHtml(p.name || k)}</option>`;
    }).join('');
  }

  _pbSetSelectOptions(document.getElementById('pbVrmModel'), _pbCatalogs.avatars, (_pbDraft.vrm_defaults || {}).model_file);
  _pbSetSelectOptions(document.getElementById('pbAvatarImg'), _pbCatalogs.pics, _pbDraft.avatar_image || 'assets/pics/splash.png');
  _pbSetSelectOptions(document.getElementById('pbSplashImg'), _pbCatalogs.pics, _pbDraft.boot_splash_image || 'assets/pics/splash.png');

  const idleClips = Array.from(new Set(['neutral_idle', 'neutral_idle2', 'sit_idle', 'sit_idle2.bvh', ..._pbCatalogs.vrma]));
  const walkClips = Array.from(new Set(['walk', 'walk_loop', 'action_walk', ..._pbCatalogs.vrma]));
  const vrmDef = _pbDraft.vrm_defaults || {};
  _pbSetSelectOptions(document.getElementById('pbDefaultIdle'), idleClips, vrmDef.default_idle || 'neutral_idle');
  _pbSetSelectOptions(document.getElementById('pbNightSitIdle'), idleClips, vrmDef.night_sit_idle || 'sit_idle');
  _pbSetSelectOptions(document.getElementById('pbWalkClip'), walkClips, vrmDef.walk_clip || 'walk');

  const parsedV = (typeof parseVoiceBlendSpec === 'function')
    ? parseVoiceBlendSpec(_pbDraft.kokoro_voice)
    : { blend: false, voiceA: _pbDraft.kokoro_voice || 'af_bella', voiceB: 'af_heart', mixPct: 65 };
  _pbSetSelectOptions(document.getElementById('pbKokoroVoice'), _pbCatalogs.voices, parsedV.voiceA);
  _pbSetSelectOptions(document.getElementById('pbKokoroVoiceB'), _pbCatalogs.voices, parsedV.voiceB);
  _pbSetSelectOptions(document.getElementById('pbAckFolder'), _pbCatalogs.ackFolders, _pbDraft.acknowledgments_folder || 'default');
}

function _pbRenderTouchCheckboxes() {
  const box = document.getElementById('pbTouchZonesGrid');
  if (!box) return;
  const age = String(_pbDraft.age_spirit || '').toLowerCase().trim();
  const isAdult = (age === 'adult');
  const banned = new Set((_pbDraft.banned_touch_zones || []).map(z => String(z).toLowerCase()));
  const touchMap = _pbDraft.touch_interactions || {};

  box.innerHTML = _PB_TOUCH_ZONES.map((z) => {
    const lockedBySafety = Boolean(z.adultOnly && !isAdult);
    const enabled = !lockedBySafety && !banned.has(z.key) && Boolean(touchMap[z.key] || !z.adultOnly);
    return `
      <label class="pb-touch-chip ${enabled ? 'checked' : ''} ${lockedBySafety ? 'locked' : ''}">
        <input type="checkbox" id="pbTz_${z.key}" ${enabled ? 'checked' : ''} ${lockedBySafety ? 'disabled' : ''} onchange="_pbOnTouchZoneToggle('${z.key}', this.checked)">
        <span>${escapeHtml(z.label)}</span>
      </label>
    `;
  }).join('');
}

function _pbOnTouchZoneToggle(zoneKey, isEnabled) {
  if (!_pbDraft.touch_interactions) _pbDraft.touch_interactions = {};
  const banned = new Set((_pbDraft.banned_touch_zones || []).map(z => String(z).toLowerCase()));
  if (isEnabled) {
    banned.delete(zoneKey);
    if (!_pbDraft.touch_interactions[zoneKey]) {
      _pbDraft.touch_interactions[zoneKey] = {
        emotion: 'HAPPY',
        hud_label: `${_pbDraft.name || 'COMPANION'} • ${zoneKey.toUpperCase()}`,
        animations: ['greeting'],
        duration_ms: 3000,
        lines: [`Right here beside you in the Dart, {driver_address}!`]
      };
    }
  } else {
    banned.add(zoneKey);
  }
  _pbDraft.banned_touch_zones = Array.from(banned);
  _pbRenderTouchCheckboxes();
  _pbRefreshRawJsonArea();
}

function syncBuilderFormFromDraft() {
  const titleEl = document.getElementById('pbModalTitle');
  const tplWrap = document.getElementById('pbTemplateWrap');
  const delBtn = document.getElementById('pbBtnDelete');
  const dupBtn = document.getElementById('pbBtnDuplicate');
  const personaCount = Object.keys(_pbCatalogs.personas || {}).length;

  if (titleEl) {
    titleEl.innerText = _pbMode === 'edit'
      ? `✏️ EDIT PERSONA: ${_pbDraft.name || _pbDraft.id}`
      : '✨ CREATE NEW PERSONA';
  }
  if (tplWrap) tplWrap.style.display = _pbMode === 'create' ? 'flex' : 'none';
  if (delBtn) delBtn.disabled = (_pbMode !== 'edit' || personaCount <= 1);
  if (dupBtn) dupBtn.style.display = (_pbMode === 'edit') ? 'inline-flex' : 'none';

  const setVal = (id, v) => {
    const el = document.getElementById(id);
    if (el) el.value = (v === undefined || v === null) ? '' : String(v);
  };
  const setChk = (id, v) => {
    const el = document.getElementById(id);
    if (el) el.checked = Boolean(v);
  };

  setVal('pbIdInput', _pbDraft.id || '');
  const idInput = document.getElementById('pbIdInput');
  if (idInput) idInput.readOnly = (_pbMode === 'edit');
  setVal('pbNameInput', _pbDraft.name || '');
  setVal('pbShortNameInput', _pbDraft.display_short_name || _pbDraft.name || '');
  setVal('pbIconInput', _pbDraft.icon || '✨');
  setVal('pbDriverTitle', _pbDraft.driver_address_default || 'Dad');
  setVal('pbSubtitle', _pbDraft.subtitle || '');
  setVal('pbBackstory', _pbDraft.backstory || '');
  setVal('pbPrompt', _pbDraft.prompt || '');
  setChk('pbSetDefaultChk', Boolean(_pbDraft.default));

  const vrmDef = _pbDraft.vrm_defaults || {};
  setVal('pbVrmModel', vrmDef.model_file || '');
  setVal('pbAvatarImg', _pbDraft.avatar_image || 'assets/pics/splash.png');
  setVal('pbSplashImg', _pbDraft.boot_splash_image || 'assets/pics/splash.png');
  setVal('pbSplashTitle', _pbDraft.boot_splash_title || '');
  setVal('pbSplashSub', _pbDraft.boot_splash_subtitle || '');
  const rawFraming = String(vrmDef.framing_mode || 'FULL_BODY').toUpperCase();
  setVal('pbFramingMode', rawFraming === 'FULL' ? 'FULL_BODY' : rawFraming);
  const sc = Number(vrmDef.scale || 1.18);
  setVal('pbVrmScale', sc.toFixed(2));
  const scLbl = document.getElementById('pbVrmScaleLbl');
  if (scLbl) scLbl.innerText = sc.toFixed(2) + 'x';
  const sp = Number(vrmDef.spring_physics_scale !== undefined ? vrmDef.spring_physics_scale : 1.0);
  setVal('pbSpringScale', sp.toFixed(2));
  const spLbl = document.getElementById('pbSpringScaleLbl');
  if (spLbl) spLbl.innerText = sp.toFixed(2) + 'x';
  setVal('pbAccentColor', vrmDef.accent_color || '#c084fc');
  setVal('pbDefaultIdle', vrmDef.default_idle || 'neutral_idle');
  setVal('pbNightSitIdle', vrmDef.night_sit_idle || 'sit_idle');
  setVal('pbWalkClip', vrmDef.walk_clip || 'walk');
  setChk('pbSleeveBonesChk', Array.isArray(vrmDef.sleeve_bones) && vrmDef.sleeve_bones.length > 0);
  detectVrmBoneHints(vrmDef.model_file || '', false);

  setVal('pbVoiceEngine', String(_pbDraft.voice_engine || 'KOKORO').toUpperCase());
  const parsedV = (typeof parseVoiceBlendSpec === 'function')
    ? parseVoiceBlendSpec(_pbDraft.kokoro_voice)
    : { blend: false, voiceA: _pbDraft.kokoro_voice || 'af_bella', voiceB: 'af_heart', mixPct: 65 };
  setVal('pbKokoroVoice', parsedV.voiceA);
  setVal('pbKokoroVoiceB', parsedV.voiceB);
  setChk('pbBlendToggle', parsedV.blend);
  const bRow = document.getElementById('pbBlendRow');
  if (bRow) bRow.style.display = parsedV.blend ? 'grid' : 'none';
  setVal('pbBlendMix', parsedV.mixPct);
  const bmLbl = document.getElementById('pbBlendMixLbl');
  if (bmLbl) bmLbl.innerText = `${parsedV.mixPct}% / ${100 - parsedV.mixPct}%`;
  const pitch = Number(_pbDraft.tts_pitch !== undefined ? _pbDraft.tts_pitch : (_pbDraft.pitch_factor || 1.12));
  setVal('pbPitchSlider', pitch.toFixed(2));
  const pLbl = document.getElementById('pbPitchLbl');
  if (pLbl) pLbl.innerText = pitch.toFixed(2) + 'x';
  const spd = Number(_pbDraft.speech_speed !== undefined ? _pbDraft.speech_speed : 1.00);
  setVal('pbSpeedSlider', spd.toFixed(2));
  const spdLbl = document.getElementById('pbSpeedLbl');
  if (spdLbl) spdLbl.innerText = spd.toFixed(2) + 'x';
  setVal('pbElevenVoiceId', _pbDraft.elevenlabs_voice_id || 'cgSgspJ2msm6clMCkdW9');
  setVal('pbAckFolder', _pbDraft.acknowledgments_folder || 'default');

  const age = String(_pbDraft.age_spirit || '8').toLowerCase().trim();
  const safetyMode = (age === 'adult') ? 'ADULT' : ((age === 'tactical') ? 'TACTICAL' : 'KID_SAFE');
  ['KID_SAFE', 'TACTICAL', 'ADULT'].forEach((k) => {
    const btn = document.getElementById(`pbSafe_${k}`);
    if (btn) btn.classList.toggle('active', k === safetyMode);
  });

  const wake = _pbDraft.wake_words || {};
  setVal('pbWakePrefix', wake.canonical_prefix || '');
  setVal('pbWakeExactReply', wake.exact_reply || '');
  setVal('pbWakeList', Array.isArray(wake.prefixes) ? wake.prefixes.join(', ') : '');
  const greets = _pbDraft.greetings || {};
  setVal('pbFirstChatIntro', greets.first_chat_intro || '');
  const morningList = (greets.instant && Array.isArray(greets.instant.morning)) ? greets.instant.morning : [];
  setVal('pbMorningGreeting', morningList[0] || '');
  const fillers = Array.isArray(_pbDraft.thinking_fillers) ? _pbDraft.thinking_fillers : [];
  setVal('pbThinkingFillers', fillers.join(' | '));

  const callouts = _pbDraft.copilot_callouts || {};
  setVal('pbCalloutCoolant', callouts.coolant_high || '');
  setVal('pbCalloutColdOil', callouts.cold_multiair || '');
  setVal('pbCalloutPull', callouts.pull_debrief || '');
  setVal('pbCalloutShift', callouts.perfect_rev_match || '');
  setVal('pbCalloutSpeed', callouts.speed_100 || '');
  setVal('pbCalloutDragy', callouts.dragy_0_60 || '');

  _pbRenderTouchCheckboxes();
  _pbRefreshRawJsonArea();
}

function syncDraftFromBuilderForm() {
  const val = (id, fb = '') => {
    const el = document.getElementById(id);
    return el ? el.value : fb;
  };
  const chk = (id) => Boolean(document.getElementById(id) && document.getElementById(id).checked);

  const name = val('pbNameInput').trim() || 'Companion';
  const rawId = val('pbIdInput').trim();
  _pbDraft.id = _pbMode === 'edit' ? (_pbDraft.id || _pbSlugId(rawId || name)) : _pbSlugId(rawId || name);
  _pbDraft.name = name;
  _pbDraft.display_short_name = val('pbShortNameInput').trim() || name.replace(/\./g, '');
  _pbDraft.full_name = _pbDraft.full_name || `${name} Cockpit AI Companion`;
  _pbDraft.icon = val('pbIconInput').trim() || '✨';
  _pbDraft.driver_address_default = val('pbDriverTitle').trim() || 'Dad';
  _pbDraft.subtitle = val('pbSubtitle').trim() || `${name} • Cockpit AI Companion`;
  _pbDraft.archetype = _pbDraft.subtitle;
  _pbDraft.backstory = val('pbBackstory').trim();
  _pbDraft.description = _pbDraft.backstory ? _pbDraft.backstory.slice(0, 220) : _pbDraft.subtitle;
  _pbDraft.prompt = val('pbPrompt').trim();
  _pbDraft.default = chk('pbSetDefaultChk');
  _pbDraft.avatar_image = val('pbAvatarImg', 'assets/pics/splash.png').trim();
  _pbDraft.boot_splash_image = val('pbSplashImg', 'assets/pics/splash.png').trim();
  _pbDraft.boot_splash_title = val('pbSplashTitle').trim() || `${name} • CARPI5`;
  _pbDraft.boot_splash_subtitle = val('pbSplashSub').trim() || _pbDraft.subtitle;

  const accent = val('pbAccentColor', '#c084fc').trim() || '#c084fc';
  if (!_pbDraft.vrm_defaults) _pbDraft.vrm_defaults = {};
  Object.assign(_pbDraft.vrm_defaults, {
    model_file: val('pbVrmModel').trim(),
    framing_mode: val('pbFramingMode', 'FULL_BODY'),
    scale: parseFloat(val('pbVrmScale', '1.18')) || 1.18,
    spring_physics_scale: parseFloat(val('pbSpringScale', '1.0')) || 1.0,
    default_idle: val('pbDefaultIdle', 'neutral_idle'),
    night_sit_idle: val('pbNightSitIdle', 'sit_idle'),
    walk_clip: val('pbWalkClip', 'walk'),
    sleeve_bones: chk('pbSleeveBonesChk') ? ['Bone001', 'Bone001_m'] : [],
    accent_color: accent,
    bubble_bg: _pbHexToRgba(accent, 0.14),
    glow_color: _pbHexToRgba(accent, 0.45),
    status_badge: `${name} ACTIVE`,
    card_title: name,
    hud_title: `${_pbDraft.icon} ${_pbDraft.display_short_name} • SHOTGUN`,
    banner_quote: `{driver_address}! ${name} is right here riding shotgun with you!`,
    idle_overlay: `${name} is watching the road with you, {driver_address}!`
  });

  _pbDraft.voice_engine = val('pbVoiceEngine', 'KOKORO').toUpperCase();
  const blendOn = chk('pbBlendToggle');
  _pbDraft.kokoro_voice = (typeof formatVoiceBlendSpec === 'function')
    ? formatVoiceBlendSpec(val('pbKokoroVoice', 'af_sky'), blendOn, val('pbKokoroVoiceB', 'af_heart'), val('pbBlendMix', '65'))
    : val('pbKokoroVoice', 'af_bella');
  const pVal = parseFloat(val('pbPitchSlider', '1.12')) || 1.12;
  _pbDraft.tts_pitch = pVal;
  _pbDraft.pitch_factor = pVal;
  _pbDraft.speech_speed = parseFloat(val('pbSpeedSlider', '1.00')) || 1.00;
  _pbDraft.elevenlabs_voice_id = val('pbElevenVoiceId', '').trim();
  _pbDraft.acknowledgments_folder = val('pbAckFolder', 'default').trim().toLowerCase() || 'default';

  const wRaw = val('pbWakeList', '');
  const wakeList = wRaw.split(',').map(s => s.trim().toLowerCase()).filter(Boolean);
  if (!_pbDraft.wake_words) _pbDraft.wake_words = {};
  _pbDraft.wake_words.canonical_prefix = val('pbWakePrefix').trim() || `Hey ${_pbDraft.display_short_name}`;
  _pbDraft.wake_words.exact_reply = val('pbWakeExactReply').trim() || `Right here, {driver_address}! ${_pbDraft.display_short_name} listening!`;
  if (wakeList.length > 0) _pbDraft.wake_words.prefixes = wakeList;
  if (!Array.isArray(_pbDraft.wake_words.standalone) || _pbDraft.wake_words.standalone.length === 0) {
    _pbDraft.wake_words.standalone = [_pbDraft.display_short_name.toLowerCase()];
  }

  if (!_pbDraft.greetings) _pbDraft.greetings = {};
  _pbDraft.greetings.first_chat_intro = val('pbFirstChatIntro').trim();
  const mGreet = val('pbMorningGreeting').trim();
  if (mGreet) {
    if (!_pbDraft.greetings.instant) _pbDraft.greetings.instant = {};
    _pbDraft.greetings.instant.morning = [mGreet];
  }
  const fRaw = val('pbThinkingFillers', '');
  if (fRaw.trim()) {
    _pbDraft.thinking_fillers = fRaw.split('|').map(s => s.trim()).filter(Boolean);
  }

  if (!_pbDraft.copilot_callouts) _pbDraft.copilot_callouts = {};
  const setCo = (k, id) => {
    const v = val(id).trim();
    if (v) _pbDraft.copilot_callouts[k] = v;
  };
  setCo('coolant_high', 'pbCalloutCoolant');
  setCo('cold_multiair', 'pbCalloutColdOil');
  setCo('pull_debrief', 'pbCalloutPull');
  setCo('perfect_rev_match', 'pbCalloutShift');
  setCo('speed_100', 'pbCalloutSpeed');
  setCo('dragy_0_60', 'pbCalloutDragy');
}

function _pbRefreshRawJsonArea() {
  const rawEl = document.getElementById('pbRawJsonArea');
  if (rawEl) {
    rawEl.value = JSON.stringify(_pbDraft, null, 2);
    const vBadge = document.getElementById('pbRawJsonStatus');
    if (vBadge) vBadge.innerText = '● VALID JSON';
  }
}

function onBuilderFormChanged() {
  if (_pbMode === 'create') {
    const nameVal = (document.getElementById('pbNameInput') || {}).value || '';
    const idEl = document.getElementById('pbIdInput');
    if (idEl && !idEl._userEdited && nameVal.trim()) {
      idEl.value = _pbSlugId(nameVal);
    }
    const shortEl = document.getElementById('pbShortNameInput');
    if (shortEl && !shortEl._userEdited && nameVal.trim()) {
      shortEl.value = nameVal.trim().toUpperCase().slice(0, 14);
    }
  }
  syncDraftFromBuilderForm();
  _pbRefreshRawJsonArea();
}

function onRawJsonInput(rawStr) {
  const vBadge = document.getElementById('pbRawJsonStatus');
  try {
    const parsed = JSON.parse(rawStr);
    if (parsed && typeof parsed === 'object') {
      _pbDraft = parsed;
      if (vBadge) {
        vBadge.innerText = '● VALID JSON (SYNCED)';
        vBadge.style.color = 'var(--accent-green)';
      }
      syncBuilderFormFromDraft();
    }
  } catch (e) {
    if (vBadge) {
      vBadge.innerText = '⚠️ JSON SYNTAX ERROR';
      vBadge.style.color = 'var(--accent-red)';
    }
  }
}

function applyBuilderTemplate(templateId) {
  if (_pbMode !== 'create') return;
  const keepName = (document.getElementById('pbNameInput') || {}).value || '';
  const keepId = (document.getElementById('pbIdInput') || {}).value || '';
  _pbDraft = _pbBuildDefaultDraft(templateId);
  if (keepName) _pbDraft.name = keepName;
  if (keepId) _pbDraft.id = _pbSlugId(keepId);
  syncBuilderFormFromDraft();
}

function applyBuilderSafetyPreset(preset) {
  if (preset === 'ADULT') {
    _pbDraft.age_spirit = 'adult';
    _pbDraft.banned_touch_zones = (_pbDraft.banned_touch_zones || []).filter(z => z !== 'butt' && z !== 'groin');
  } else if (preset === 'TACTICAL') {
    _pbDraft.age_spirit = 'tactical';
    const b = new Set((_pbDraft.banned_touch_zones || []).map(z => z.toLowerCase()));
    b.add('butt');
    b.add('groin');
    _pbDraft.banned_touch_zones = Array.from(b);
  } else {
    _pbDraft.age_spirit = '8';
    const b = new Set((_pbDraft.banned_touch_zones || []).map(z => z.toLowerCase()));
    b.add('butt');
    b.add('groin');
    _pbDraft.banned_touch_zones = Array.from(b);
  }
  syncBuilderFormFromDraft();
}

function selectBuilderIcon(emoji) {
  const el = document.getElementById('pbIconInput');
  if (el) el.value = emoji;
  onBuilderFormChanged();
}

function selectBuilderColor(hex) {
  const el = document.getElementById('pbAccentColor');
  if (el) el.value = hex;
  onBuilderFormChanged();
}

function detectVrmBoneHints(modelName, applyChoice = true) {
  const hintEl = document.getElementById('pbSleeveHint');
  const chkEl = document.getElementById('pbSleeveBonesChk');
  let detectedSleeve = false;
  if (modelName && modelName === window.currentVrmModelName && typeof vrmModel !== 'undefined' && vrmModel) {
    detectedSleeve = Boolean(vrmModel.getObjectByName('Bone001') || vrmModel.getObjectByName('Bone001_m'));
  } else if (/^(rum|rem)\.vrm$/i.test(String(modelName || ''))) {
    detectedSleeve = true;
  }
  if (applyChoice && chkEl) {
    chkEl.checked = detectedSleeve;
    onBuilderFormChanged();
  }
  if (hintEl) {
    hintEl.innerText = detectedSleeve
      ? 'Kimono sleeve bones detected (Bone001 / Bone001_m).'
      : 'Standard arm/outfit rigging (no kimono sleeve override needed).';
  }
}

async function uploadPersonaAsset(inputEl, kind) {
  const file = inputEl && inputEl.files && inputEl.files[0];
  if (!file) return;
  const statusEl = document.getElementById('pbStatusMsg');
  const endpoint = (kind === 'vrm')
    ? `/api/models/avatars/upload?name=${encodeURIComponent(file.name)}`
    : `/api/assets/pics/upload?name=${encodeURIComponent(file.name)}`;
  if (statusEl) statusEl.innerText = `Uploading ${file.name}...`;
  try {
    const resp = await fetch(endpoint, {
      method: 'POST',
      headers: { 'Content-Type': 'application/octet-stream' },
      body: file
    });
    const res = await resp.json();
    if (!resp.ok || res.status !== 'ok') {
      if (statusEl) statusEl.innerText = `Upload failed: ${res.message || resp.status}`;
      return;
    }
    if (kind === 'vrm') {
      _pbCatalogs.avatars.push(res.name);
      _pbSetSelectOptions(document.getElementById('pbVrmModel'), _pbCatalogs.avatars, res.name);
      detectVrmBoneHints(res.name, true);
    } else {
      _pbCatalogs.pics.push(res.path);
      _pbSetSelectOptions(document.getElementById('pbAvatarImg'), _pbCatalogs.pics, res.path);
      _pbSetSelectOptions(document.getElementById('pbSplashImg'), _pbCatalogs.pics, document.getElementById('pbSplashImg')?.value || res.path);
      onBuilderFormChanged();
    }
    if (statusEl) statusEl.innerText = `Uploaded ${res.name}!`;
  } catch (err) {
    if (statusEl) statusEl.innerText = `Upload error: ${err.message || err}`;
  } finally {
    inputEl.value = '';
  }
}

function toggleBuilderVoiceBlend(on) {
  const bRow = document.getElementById('pbBlendRow');
  if (bRow) bRow.style.display = on ? 'grid' : 'none';
  onBuilderFormChanged();
}

function testBuilderVoice() {
  syncDraftFromBuilderForm();
  const sample = `Hello! This is ${_pbDraft.name || 'your co-pilot'} testing a natural voice inside your Dodge Dart!`;
  fetch('/api/ai/speak', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      text: sample,
      source: 'BUILDER_PREVIEW',
      emotion: 'HAPPY',
      tts_engine: _pbDraft.voice_engine,
      kokoro_voice: _pbDraft.kokoro_voice,
      tts_pitch: _pbDraft.tts_pitch,
      speech_speed: _pbDraft.speech_speed
    })
  }).catch(() => {});
  const statusEl = document.getElementById('pbStatusMsg');
  if (statusEl) statusEl.innerText = `Speaking preview (${_pbDraft.kokoro_voice} • speed ${_pbDraft.speech_speed}x • pitch ${_pbDraft.tts_pitch}x)`;
}

async function autofillBuilderDialogue(useLlm = false) {
  syncDraftFromBuilderForm();
  const statusEl = document.getElementById('pbStatusMsg');
  if (statusEl) statusEl.innerText = useLlm ? 'Generating dialogue with AI...' : 'Generating wake words & template callouts...';
  try {
    const resp = await fetch('/api/ai/personas/autofill', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        name: _pbDraft.name,
        display_short_name: _pbDraft.display_short_name,
        age_spirit: _pbDraft.age_spirit,
        subtitle: _pbDraft.subtitle,
        prompt: _pbDraft.prompt,
        template_id: (document.getElementById('pbTemplateSelect') || {}).value || '',
        use_llm: Boolean(useLlm)
      })
    });
    const res = await resp.json();
    if (res && res.status === 'ok' && res.fields) {
      Object.assign(_pbDraft, res.fields);
      syncBuilderFormFromDraft();
      if (statusEl) statusEl.innerText = res.fields.ai_generated ? '✨ AI Dialogue Auto-Filled!' : '✨ Template & Wake Words Generated!';
    }
  } catch (err) {
    if (statusEl) statusEl.innerText = 'Autofill error: ' + (err.message || err);
  }
}

async function savePersonaBuilder(activateNow = false) {
  syncDraftFromBuilderForm();
  const statusEl = document.getElementById('pbStatusMsg');
  if (!_pbDraft.name || !_pbDraft.id) {
    if (statusEl) statusEl.innerText = 'Please enter a Persona Name first.';
    switchPersonaBuilderTab('identity');
    return;
  }
  if (statusEl) statusEl.innerText = 'Saving persona to Pi 5...';
  try {
    const resp = await fetch('/api/ai/personas/save', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ persona: _pbDraft, set_active: Boolean(activateNow) })
    });
    const res = await resp.json();
    if (!resp.ok || res.status !== 'ok') {
      if (statusEl) statusEl.innerText = `Save failed: ${res.message || resp.status}`;
      return;
    }
    const saved = res.persona || _pbDraft;
    if (!window.allPersonas) window.allPersonas = {};
    window.allPersonas[saved.id] = saved;
    if (typeof fetchAiHistory === 'function') await fetchAiHistory();
    if (activateNow && typeof changePersona === 'function') {
      changePersona(saved.id);
    }
    closePersonaBuilder();
    if (typeof showToastNotification === 'function') {
      showToastNotification(activateNow ? `Saved & Activated ${saved.name}!` : `Saved Persona ${saved.name}!`);
    }
  } catch (err) {
    if (statusEl) statusEl.innerText = 'Save error: ' + (err.message || err);
  }
}

function duplicatePersonaInBuilder() {
  syncDraftFromBuilderForm();
  _pbMode = 'create';
  _pbDraft.id = `${_pbDraft.id || 'CUSTOM'}_COPY`.slice(0, 32);
  _pbDraft.name = `${_pbDraft.name || 'Companion'} Copy`;
  _pbDraft.display_short_name = `${_pbDraft.display_short_name || _pbDraft.name}2`;
  _pbDraft.default = false;
  syncBuilderFormFromDraft();
  switchPersonaBuilderTab('identity');
  const statusEl = document.getElementById('pbStatusMsg');
  if (statusEl) statusEl.innerText = 'Cloned to New Persona draft — customize & Save!';
}

function exportPersonaJson() {
  syncDraftFromBuilderForm();
  const blob = new Blob([JSON.stringify(_pbDraft, null, 2)], { type: 'application/json' });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = `${(_pbDraft.id || 'persona').toLowerCase()}.json`;
  document.body.appendChild(a);
  a.click();
  setTimeout(() => {
    URL.revokeObjectURL(a.href);
    a.remove();
  }, 150);
}

async function deletePersonaFromBuilder() {
  if (_pbMode !== 'edit' || !_pbDraft.id) return;
  const pId = _pbDraft.id;
  if (!window.confirm(`Delete persona '${_pbDraft.name || pId}' from Pi 5?`)) return;
  const statusEl = document.getElementById('pbStatusMsg');
  try {
    const resp = await fetch('/api/ai/personas/delete', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ id: pId })
    });
    const res = await resp.json();
    if (!resp.ok || res.status !== 'ok') {
      if (statusEl) statusEl.innerText = `Delete blocked: ${res.message || resp.status}`;
      return;
    }
    if (window.allPersonas) delete window.allPersonas[pId];
    if (typeof fetchAiHistory === 'function') await fetchAiHistory();
    if (res.active_persona && typeof changePersona === 'function') {
      changePersona(res.active_persona);
    }
    closePersonaBuilder();
    if (typeof showToastNotification === 'function') {
      showToastNotification(`Deleted persona ${pId}.`);
    }
  } catch (err) {
    if (statusEl) statusEl.innerText = 'Delete error: ' + (err.message || err);
  }
}

window.openPersonaBuilder = openPersonaBuilder;
window.closePersonaBuilder = closePersonaBuilder;
window.switchPersonaBuilderTab = switchPersonaBuilderTab;
window.onBuilderFormChanged = onBuilderFormChanged;
window.onRawJsonInput = onRawJsonInput;
window.applyBuilderTemplate = applyBuilderTemplate;
window.applyBuilderSafetyPreset = applyBuilderSafetyPreset;
window.selectBuilderIcon = selectBuilderIcon;
window.selectBuilderColor = selectBuilderColor;
window.detectVrmBoneHints = detectVrmBoneHints;
window.uploadPersonaAsset = uploadPersonaAsset;
window.testBuilderVoice = testBuilderVoice;
window.toggleBuilderVoiceBlend = toggleBuilderVoiceBlend;
window.autofillBuilderDialogue = autofillBuilderDialogue;
window.savePersonaBuilder = savePersonaBuilder;
window.duplicatePersonaInBuilder = duplicatePersonaInBuilder;
window.exportPersonaJson = exportPersonaJson;
window.deletePersonaFromBuilder = deletePersonaFromBuilder;
