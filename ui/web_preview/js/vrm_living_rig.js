/**
 * CarPi5 Living VRM Rig Subsystems
 * - Universal VRM 0.x / 1.0 + Biped capability calibrator
 * - LRU clip cache & Upper/Lower body track masking
 * - Dual-sync Viseme Lip-Sync (Backend 25Hz WAV timeline + PC Web Audio AnalyserNode)
 * - Smooth damped BlendShape + Facial-Bone Expression Engine & Micro-Saccades
 * - Verlet Spring-Bone Physics (VRM secondaryAnimation + heuristic hair/sleeve chains)
 * - Conversational State Machine (IDLE_ALIVE, LISTENING, THINKING, SPEAKING) & Adaptive Quality
 */

const VRM_CORE_PINNED_CLIPS = new Set([
  'neutral_idle', 'neutral_idle2', 'sit_idle', 'sit_idle2', 'walk_loop', 'jog_loop', 'greeting'
]);

class VrmClipLruCache {
  constructor(maxSize = 28) {
    this.maxSize = Math.max(2, Number(maxSize) || 28);
    this._map = new Map();
  }
  has(key) {
    return this._map.has(key);
  }
  get(key) {
    if (!this._map.has(key)) return undefined;
    const val = this._map.get(key);
    this._map.delete(key);
    this._map.set(key, val);
    return val;
  }
  set(key, clip) {
    if (!key || !clip) return;
    if (this._map.has(key)) {
      this._map.delete(key);
    }
    this._map.set(key, clip);
    this._evictIfNeeded();
  }
  clear() {
    this._map.clear();
  }
  keys() {
    return Array.from(this._map.keys());
  }
  get size() {
    return this._map.size;
  }
  _evictIfNeeded() {
    if (this._map.size <= this.maxSize) return;
    for (const k of this._map.keys()) {
      if (this._map.size <= this.maxSize) break;
      if (VRM_CORE_PINNED_CLIPS.has(k)) continue;
      this._map.delete(k);
    }
  }
}

function createVrmaClipStore(maxSize = 28) {
  const lru = new VrmClipLruCache(maxSize);
  return new Proxy({}, {
    get(_t, prop) {
      if (prop === '_lru') return lru;
      if (prop === 'size') return lru.size;
      if (typeof prop === 'symbol') return undefined;
      return lru.get(prop);
    },
    set(_t, prop, val) {
      if (typeof prop === 'string') lru.set(prop, val);
      return true;
    },
    has(_t, prop) {
      return typeof prop === 'string' && lru.has(prop);
    },
    ownKeys() {
      return lru.keys();
    },
    getOwnPropertyDescriptor(_t, prop) {
      if (typeof prop === 'string' && lru.has(prop)) {
        return { enumerable: true, configurable: true, value: lru.get(prop) };
      }
      return undefined;
    },
  });
}

const UPPER_BODY_HUMANOID_BONES = new Set([
  'spine', 'chest', 'upperChest', 'neck', 'head',
  'leftShoulder', 'leftUpperArm', 'leftLowerArm', 'leftHand',
  'rightShoulder', 'rightUpperArm', 'rightLowerArm', 'rightHand',
  'leftThumbProximal', 'leftThumbIntermediate', 'leftThumbDistal',
  'leftIndexProximal', 'leftIndexIntermediate', 'leftIndexDistal',
  'leftMiddleProximal', 'leftMiddleIntermediate', 'leftMiddleDistal',
  'leftRingProximal', 'leftRingIntermediate', 'leftRingDistal',
  'leftLittleProximal', 'leftLittleIntermediate', 'leftLittleDistal',
  'rightThumbProximal', 'rightThumbIntermediate', 'rightThumbDistal',
  'rightIndexProximal', 'rightIndexIntermediate', 'rightIndexDistal',
  'rightMiddleProximal', 'rightMiddleIntermediate', 'rightMiddleDistal',
  'rightRingProximal', 'rightRingIntermediate', 'rightRingDistal',
  'rightLittleProximal', 'rightLittleIntermediate', 'rightLittleDistal',
]);

function buildMaskedUpperBodyClip(baseClip, humanoidMap) {
  if (!baseClip || !Array.isArray(baseClip.tracks) || !humanoidMap || typeof THREE === 'undefined') {
    return baseClip;
  }
  const allowedUuids = new Set();
  UPPER_BODY_HUMANOID_BONES.forEach((hName) => {
    const bone = humanoidMap[hName];
    if (bone && bone.uuid) allowedUuids.add(bone.uuid);
  });
  if (allowedUuids.size === 0) return baseClip;

  const upperTracks = baseClip.tracks.filter((tr) => {
    const dot = tr.name.lastIndexOf('.');
    if (dot < 0) return false;
    const targetId = tr.name.substring(0, dot);
    const prop = tr.name.substring(dot + 1);
    return prop === 'quaternion' && allowedUuids.has(targetId);
  });
  if (upperTracks.length === 0) return baseClip;
  return new THREE.AnimationClip(`${baseClip.name}_upper`, baseClip.duration, upperTracks);
}

/**
 * Inspect GLTF/VRM 0.x + VRM 1.0 JSON metadata and extract morph targets & spring bone chains.
 */
function parseVrmCapabilities(gltf, root) {
  const caps = {
    version: 'procedural',
    hasMorphs: false,
    expressions: {}, // normalized preset -> [{ mesh, index, weight }]
    springGroups: [],
    colliders: [],
  };
  if (!root) return caps;

  const meshesByIdx = [];
  const meshesByName = {};
  const nodesByIdx = {};
  let parserJson = null;

  try {
    parserJson = gltf && gltf.parser && gltf.parser.json;
  } catch (e) {}

  root.traverse((obj) => {
    if (obj.isMesh && obj.morphTargetInfluences) {
      meshesByName[obj.name] = obj;
      meshesByIdx.push(obj);
      caps.hasMorphs = true;
    }
    if (obj.name) {
      nodesByIdx[obj.name] = obj;
    }
  });

  const bindMorph = (presetName, mesh, index, weight = 1.0) => {
    if (!mesh || !mesh.morphTargetInfluences || index < 0 || index >= mesh.morphTargetInfluences.length) return;
    const key = String(presetName || '').toLowerCase();
    if (!caps.expressions[key]) caps.expressions[key] = [];
    caps.expressions[key].push({ mesh, index, weight: Math.max(0.05, Math.min(1.0, weight)) });
  };

  // Alias map VRM 0.x <-> VRM 1.0
  const normPreset = (raw) => {
    const k = String(raw || '').toLowerCase();
    const map = {
      joy: 'happy', fun: 'relaxed', sorrow: 'sad', a: 'aa', i: 'ih', u: 'ou', e: 'ee', o: 'oh',
      blink_l: 'blinkleft', blink_r: 'blinkright',
      lookup: 'lookup', lookdown: 'lookdown', lookleft: 'lookleft', lookright: 'lookright',
    };
    return map[k] || k;
  };

  // 1. VRM 0.x blendShapeMaster + secondaryAnimation
  const vrm0 = parserJson && parserJson.extensions && parserJson.extensions.VRM;
  if (vrm0) {
    caps.version = '0.x';
    const groups = (vrm0.blendShapeMaster && vrm0.blendShapeMaster.blendShapeGroups) || [];
    groups.forEach((grp) => {
      const pName = normPreset(grp.presetName && grp.presetName !== 'unknown' ? grp.presetName : grp.name);
      (grp.binds || []).forEach((b) => {
        const nodeName = parserJson.nodes && parserJson.nodes[b.mesh] && parserJson.nodes[b.mesh].name;
        const targetMesh = (nodeName && meshesByName[nodeName]) || meshesByIdx[b.mesh];
        bindMorph(pName, targetMesh, b.index, (b.weight !== undefined ? b.weight / 100.0 : 1.0));
      });
    });

    const sec = vrm0.secondaryAnimation || {};
    (sec.colliderGroups || []).forEach((cg) => {
      const nName = parserJson.nodes && parserJson.nodes[cg.node] && parserJson.nodes[cg.node].name;
      const host = nName ? nodesByIdx[nName] : null;
      if (host && Array.isArray(cg.colliders)) {
        cg.colliders.forEach((col) => {
          caps.colliders.push({
            node: host,
            offset: col.offset || { x: 0, y: 0, z: 0 },
            radius: Math.max(0.02, col.radius || 0.05),
          });
        });
      }
    });
    (sec.boneGroups || []).forEach((bg) => {
      const rootNodes = [];
      (bg.bones || []).forEach((nodeIdx) => {
        const nName = parserJson.nodes && parserJson.nodes[nodeIdx] && parserJson.nodes[nodeIdx].name;
        const bn = nName ? nodesByIdx[nName] : null;
        if (bn) rootNodes.push(bn);
      });
      if (rootNodes.length > 0) {
        caps.springGroups.push({
          roots: rootNodes,
          stiffness: Math.max(0.15, Math.min(4.0, bg.stiffiness !== undefined ? bg.stiffiness : 1.1)),
          gravityPower: bg.gravityPower !== undefined ? bg.gravityPower : 0.25,
          dragForce: Math.max(0.1, Math.min(0.95, bg.dragForce !== undefined ? bg.dragForce : 0.45)),
          hitRadius: bg.hitRadius || 0.025,
        });
      }
    });
  }

  // 2. VRM 1.0 VRMC_vrm expressions + VRMC_springBone
  const vrm1 = parserJson && parserJson.extensions && parserJson.extensions.VRMC_vrm;
  if (vrm1) {
    caps.version = '1.0';
    const presetExprs = (vrm1.expressions && vrm1.expressions.preset) || {};
    Object.keys(presetExprs).forEach((pKey) => {
      const pDef = presetExprs[pKey];
      (pDef.morphTargetBinds || []).forEach((b) => {
        const nodeName = parserJson.nodes && parserJson.nodes[b.node] && parserJson.nodes[b.node].name;
        const targetMesh = nodeName ? meshesByName[nodeName] : null;
        bindMorph(normPreset(pKey), targetMesh, b.index, b.weight !== undefined ? b.weight : 1.0);
      });
    });
  }

  // 3. Heuristic fallback scan for morphTargetDictionary names & Biped secondary garment/hair chains
  if (caps.hasMorphs && Object.keys(caps.expressions).length === 0) {
    meshesByIdx.forEach((m) => {
      const dict = m.morphTargetDictionary || {};
      Object.keys(dict).forEach((morphName) => {
        const lower = morphName.toLowerCase();
        if (lower.includes('happy') || lower.includes('smile') || lower.includes('joy')) bindMorph('happy', m, dict[morphName], 1.0);
        else if (lower.includes('angry') || lower.includes('frown')) bindMorph('angry', m, dict[morphName], 1.0);
        else if (lower.includes('sad') || lower.includes('sorrow')) bindMorph('sad', m, dict[morphName], 1.0);
        else if (lower.includes('surpris')) bindMorph('surprised', m, dict[morphName], 1.0);
        else if (lower.includes('relax')) bindMorph('relaxed', m, dict[morphName], 1.0);
        else if (lower.includes('blink')) bindMorph('blink', m, dict[morphName], 1.0);
        else if (lower === 'aa' || lower.endsWith('_a')) bindMorph('aa', m, dict[morphName], 1.0);
        else if (lower === 'ih' || lower.endsWith('_i')) bindMorph('ih', m, dict[morphName], 1.0);
        else if (lower === 'ou' || lower.endsWith('_u')) bindMorph('ou', m, dict[morphName], 1.0);
        else if (lower === 'ee' || lower.endsWith('_e')) bindMorph('ee', m, dict[morphName], 1.0);
        else if (lower === 'oh' || lower.endsWith('_o')) bindMorph('oh', m, dict[morphName], 1.0);
      });
    });
  }

  // Heuristic skirt / ribbon / hair chains (keep Bone001 kimono sleeves on gravity drape solver)
  if (caps.springGroups.length === 0) {
    const chainRoots = [];
    ['Bone009', 'Bone013', 'Bone013_m', 'Bone027', 'Bone027_m', 'Bone031', 'Bone031_m'].forEach((bn) => {
      if (nodesByIdx[bn]) chainRoots.push(nodesByIdx[bn]);
    });
    if (chainRoots.length > 0) {
      caps.springGroups.push({
        roots: chainRoots,
        stiffness: 1.65,
        gravityPower: 0.14,
        dragForce: 0.52,
        hitRadius: 0.02,
        isHeuristicChain: true,
      });
    }
  }

  return caps;
}

/**
 * Lightweight Verlet Spring-Bone Solver for VRM hair, ribbons, sleeves, and car G-force sway.
 */
class VrmSpringBoneSolver {
  constructor() {
    this.chains = [];
    this.colliders = [];
    this._tmpParentWorldQ = typeof THREE !== 'undefined' ? new THREE.Quaternion() : null;
    this._tmpTargetPos = typeof THREE !== 'undefined' ? new THREE.Vector3() : null;
    this._tmpNextTail = typeof THREE !== 'undefined' ? new THREE.Vector3() : null;
    this._tmpImpulse = typeof THREE !== 'undefined' ? new THREE.Vector3() : null;
    this._tmpColWorld = typeof THREE !== 'undefined' ? new THREE.Vector3() : null;
  }

  initFromCapabilities(caps, root) {
    this.chains = [];
    this.colliders = (caps && caps.colliders) || [];
    if (!caps || !Array.isArray(caps.springGroups) || !root || typeof THREE === 'undefined') return;

    root.updateMatrixWorld(true);
    const seen = new Set();

    const walkBone = (bone, groupMeta) => {
      if (!bone || seen.has(bone.uuid)) return;
      seen.add(bone.uuid);
      if (bone.children && bone.children.length > 0) {
        const child = bone.children[0];
        const pW = new THREE.Vector3();
        const cW = new THREE.Vector3();
        bone.getWorldPosition(pW);
        child.getWorldPosition(cW);
        const len = cW.distanceTo(pW);
        if (len > 0.004 && len < 1.2) {
          const boneAxis = child.position.clone().normalize();
          this.chains.push({
            bone,
            child,
            boneLength: len,
            boneAxis,
            initialLocalQuat: bone.quaternion.clone(),
            currTail: cW.clone(),
            prevTail: cW.clone(),
            stiffness: groupMeta.stiffness || 1.2,
            gravityPower: groupMeta.gravityPower !== undefined ? groupMeta.gravityPower : 0.18,
            dragForce: groupMeta.dragForce !== undefined ? groupMeta.dragForce : 0.48,
            hitRadius: groupMeta.hitRadius || 0.02,
          });
        }
        bone.children.forEach((ch) => walkBone(ch, groupMeta));
      }
    };

    caps.springGroups.forEach((grp) => {
      (grp.roots || []).forEach((r) => walkBone(r, grp));
    });
  }

  step(delta, inertiaZ = 0, roll = 0) {
    if (!this.chains.length || typeof THREE === 'undefined') return;
    const dt = Math.min(0.033, Math.max(0.004, delta || 0.016));
    const gravY = -9.8 * dt * dt * 0.18;
    const accelX = -roll * 1.4 * dt * dt;
    const accelZ = -inertiaZ * 1.8 * dt * dt;

    for (let i = 0; i < this.chains.length; i++) {
      const c = this.chains[i];
      if (!c.bone || !c.bone.parent) continue;

      c.bone.parent.updateWorldMatrix(true, false);
      const boneWorldPos = new THREE.Vector3();
      c.bone.getWorldPosition(boneWorldPos);

      c.bone.parent.getWorldQuaternion(this._tmpParentWorldQ);
      const restWorldQ = this._tmpParentWorldQ.clone().multiply(c.initialLocalQuat);
      const restDir = c.boneAxis.clone().applyQuaternion(restWorldQ);

      // Inertia + damping + stiffness force + gravity/car G-force impulse
      const velX = (c.currTail.x - c.prevTail.x) * (1.0 - c.dragForce);
      const velY = (c.currTail.y - c.prevTail.y) * (1.0 - c.dragForce);
      const velZ = (c.currTail.z - c.prevTail.z) * (1.0 - c.dragForce);

      const nextTail = this._tmpNextTail.set(
        c.currTail.x + velX + restDir.x * (c.stiffness * dt * 0.85) + accelX,
        c.currTail.y + velY + restDir.y * (c.stiffness * dt * 0.85) + gravY * (c.gravityPower * 4.5),
        c.currTail.z + velZ + restDir.z * (c.stiffness * dt * 0.85) + accelZ
      );

      // Clamp to bone length
      const toTail = nextTail.sub(boneWorldPos);
      if (toTail.lengthSq() > 1e-8) {
        toTail.normalize().multiplyScalar(c.boneLength);
      } else {
        toTail.copy(restDir).multiplyScalar(c.boneLength);
      }
      const constrainedTail = boneWorldPos.clone().add(toTail);

      // Clamp maximum angular deflection (<= 38 deg) so cloth/hair never clips violently
      const curDir = constrainedTail.clone().sub(boneWorldPos).normalize();
      const dot = Math.max(-1, Math.min(1, curDir.dot(restDir)));
      if (dot < 0.78) {
        curDir.lerp(restDir, 0.35).normalize();
        constrainedTail.copy(boneWorldPos).add(curDir.multiplyScalar(c.boneLength));
      }

      c.prevTail.copy(c.currTail);
      c.currTail.copy(constrainedTail);

      // Apply local quaternion rotation aligning boneAxis to constrained target
      const invParentQ = this._tmpParentWorldQ.clone().invert();
      const localTargetDir = curDir.clone().applyQuaternion(invParentQ).applyQuaternion(c.initialLocalQuat.clone().invert()).normalize();
      const rotDelta = new THREE.Quaternion().setFromUnitVectors(c.boneAxis, localTargetDir);
      c.bone.quaternion.copy(c.initialLocalQuat).multiply(rotDelta);
    }
  }
}

/**
 * Dual-Sync 5-Vowel Viseme Player ('aa', 'ih', 'ou', 'ee', 'oh' + jaw aperture).
 */
class VrmSpeechVisemeController {
  constructor() {
    this.weights = { aa: 0, ih: 0, ou: 0, ee: 0, oh: 0, jawOpen: 0 };
    this._sseTimeline = null;
    this._sseStartMs = 0;
    this._pcAnalyser = null;
    this._pcFreqData = null;
    this._pcSourceEl = null;
    this._audioCtx = null;
    this._visemeCodeMap = { a: 'aa', i: 'ih', u: 'ou', e: 'ee', o: 'oh' };
  }

  setSseTimeline(timeline) {
    if (!timeline || !Array.isArray(timeline.amps)) return;
    this._sseTimeline = timeline;
    this._sseStartMs = Date.now();
  }

  clearSseTimeline() {
    this._sseTimeline = null;
  }

  attachPcAudioElement(audioEl) {
    if (!audioEl || typeof window === 'undefined') return;
    const AudioCtx = window.AudioContext || window.webkitAudioContext;
    if (!AudioCtx) return;
    try {
      if (!this._audioCtx) this._audioCtx = new AudioCtx();
      if (this._audioCtx.state === 'suspended') {
        this._audioCtx.resume().catch(() => {});
      }
      if (this._pcSourceEl !== audioEl) {
        const src = this._audioCtx.createMediaElementSource(audioEl);
        const analyser = this._audioCtx.createAnalyser();
        analyser.fftSize = 512;
        analyser.smoothingTimeConstant = 0.55;
        src.connect(analyser);
        analyser.connect(this._audioCtx.destination);
        this._pcAnalyser = analyser;
        this._pcFreqData = new Uint8Array(analyser.frequencyBinCount);
        this._pcSourceEl = audioEl;
      }
    } catch (e) {
      // Fallback cleanly to SSE timeline if AudioContext cannot bind
    }
  }

  sample(delta, time, isSpeaking) {
    const target = { aa: 0, ih: 0, ou: 0, ee: 0, oh: 0, jawOpen: 0 };
    const now = Date.now();

    if (isSpeaking) {
      let sampled = false;

      // Priority 1: Live PC Browser Web Audio FFT Formant Analyser
      if (this._pcAnalyser && this._pcFreqData && this._pcSourceEl && !this._pcSourceEl.paused && !this._pcSourceEl.ended) {
        this._pcAnalyser.getByteFrequencyData(this._pcFreqData);
        let sumLow = 0, sumMid = 0, sumHigh = 0;
        for (let i = 2; i < 12; i++) sumLow += this._pcFreqData[i];
        for (let i = 12; i < 34; i++) sumMid += this._pcFreqData[i];
        for (let i = 34; i < 72; i++) sumHigh += this._pcFreqData[i];
        const total = (sumLow + sumMid + sumHigh) / (70 * 255);
        const amp = Math.min(1.0, Math.max(0.0, total * 2.4));
        if (amp > 0.04) {
          sampled = true;
          target.jawOpen = amp;
          const rLow = sumLow / Math.max(1, sumLow + sumMid + sumHigh);
          const rHigh = sumHigh / Math.max(1, sumLow + sumMid + sumHigh);
          if (rHigh > 0.34) target.ee = amp * 0.85;
          else if (rLow > 0.45) target.ou = amp * 0.85;
          else if (rLow > 0.32) target.oh = amp * 0.85;
          else target.aa = amp * 0.90;
        }
      }

      // Priority 2: Backend Pre-Computed 25 Hz WAV RMS + Phoneme Vowel Timeline (Pi 5 speakers)
      if (!sampled && this._sseTimeline && this._sseTimeline.amps && this._sseTimeline.amps.length > 0) {
        const elapsedSec = Math.max(0, (now - this._sseStartMs) / 1000.0);
        const fps = this._sseTimeline.fps || 25;
        const idx = Math.floor(elapsedSec * fps);
        if (idx < this._sseTimeline.amps.length) {
          sampled = true;
          const amp = (this._sseTimeline.amps[idx] || 0) / 15.0;
          const code = (this._sseTimeline.visemes || '').charAt(idx) || '0';
          const key = this._visemeCodeMap[code];
          target.jawOpen = amp;
          if (key && amp > 0.08) target[key] = Math.min(1.0, amp * 1.05);
        }
      }

      // Priority 3: Smooth Syllable Formant Oscillation Fallback (file:// offline preview)
      if (!sampled) {
        const s1 = Math.sin(time * 17.5);
        const s2 = Math.sin(time * 10.7 + 0.7);
        const amp = Math.min(1.0, Math.max(0.0, s1 * 0.48 + s2 * 0.32 + 0.32));
        target.jawOpen = amp;
        const phase = Math.floor((time * 6.5) % 4);
        const keys = ['aa', 'ee', 'oh', 'ih'];
        target[keys[phase]] = amp * 0.85;
      }
    }

    const rate = Math.min(1.0, (delta || 0.016) * 24.0);
    Object.keys(this.weights).forEach((k) => {
      this.weights[k] += (target[k] - this.weights[k]) * rate;
    });
    return this.weights;
  }
}

/**
 * Facial Expression Controller bridging VRM Morph Targets + Biped Procedural Face Bones.
 */
class VrmExpressionController {
  constructor() {
    this.target = { happy: 0.25, angry: 0, sad: 0, relaxed: 0.2, surprised: 0, blush: 0.25, smirk: 0, browTilt: 0 };
    this.current = { happy: 0.25, angry: 0, sad: 0, relaxed: 0.2, surprised: 0, blush: 0.25, smirk: 0, browTilt: 0 };
    this._nextSaccadeMs = 0;
    this._saccadeYaw = 0;
    this._saccadePitch = 0;
  }

  setFacialPreset(preset) {
    if (!preset || typeof preset !== 'object') return;
    this.target = {
      happy: Math.max(0, Math.min(1, Number(preset.happy || 0))),
      angry: Math.max(0, Math.min(1, Number(preset.angry || 0))),
      sad: Math.max(0, Math.min(1, Number(preset.sad || 0))),
      relaxed: Math.max(0, Math.min(1, Number(preset.relaxed || 0))),
      surprised: Math.max(0, Math.min(1, Number(preset.surprised || 0))),
      blush: Math.max(0, Math.min(1, Number(preset.blush || 0))),
      smirk: Math.max(0, Math.min(1, Number(preset.smirk || 0))),
      browTilt: Math.max(-1, Math.min(1, Number(preset.brow_tilt !== undefined ? preset.brow_tilt : (preset.browTilt || 0)))),
    };
  }

  apply(delta, now, caps, bones, visemeWeights, blinkAmt, gazeYaw, gazePitch, isBlinkSuppressed) {
    const rate = Math.min(1.0, (delta || 0.016) * 7.5);
    Object.keys(this.current).forEach((k) => {
      this.current[k] += (this.target[k] - this.current[k]) * rate;
    });

    // Subtle iris micro-saccades so gaze stays organically alive
    if (now > this._nextSaccadeMs) {
      this._saccadeYaw = (Math.random() - 0.5) * 0.055;
      this._saccadePitch = (Math.random() - 0.5) * 0.032;
      this._nextSaccadeMs = now + 950 + Math.random() * 1700;
    }

    // 1. Apply to VRM 0.x/1.0 Morph Targets when supported by the loaded model
    if (caps && caps.hasMorphs && caps.expressions) {
      const exprs = caps.expressions;
      const setExpr = (key, val) => {
        const list = exprs[key];
        if (!list) return;
        const clamped = Math.max(0, Math.min(1, val));
        for (let i = 0; i < list.length; i++) {
          const bind = list[i];
          if (bind.mesh && bind.mesh.morphTargetInfluences) {
            bind.mesh.morphTargetInfluences[bind.index] = clamped * bind.weight;
          }
        }
      };

      setExpr('happy', this.current.happy);
      setExpr('angry', this.current.angry);
      setExpr('sad', this.current.sad);
      setExpr('relaxed', this.current.relaxed);
      setExpr('surprised', this.current.surprised);
      setExpr('blink', isBlinkSuppressed ? 0 : blinkAmt);
      setExpr('aa', visemeWeights.aa || 0);
      setExpr('ih', visemeWeights.ih || 0);
      setExpr('ou', visemeWeights.ou || 0);
      setExpr('ee', visemeWeights.ee || 0);
      setExpr('oh', visemeWeights.oh || 0);
    }

    // 2. Biped Procedural Face Bones (models without VRM BlendShape morph targets)
    if (!bones) return;
    const cur = this.current;
    const laughScale = (bones.lMouthCorner && bones.lMouthCorner.userData && bones.lMouthCorner.userData.restPos) ? 1 : 0;

    if (laughScale) {
      const lSmile = (cur.happy * 0.0085) + (cur.smirk * 0.003) - (cur.sad * 0.005);
      const rSmile = (cur.happy * 0.0085) - (cur.sad * 0.005);
      const cornerSpread = (visemeWeights.ee * 0.14) + (cur.happy * 0.08) - (visemeWeights.ou * 0.12);
      if (bones.lMouthCorner.userData.restPos) {
        bones.lMouthCorner.position.y = bones.lMouthCorner.userData.restPos.y + lSmile + (visemeWeights.ee * 0.003);
        bones.lMouthCorner.position.x = bones.lMouthCorner.userData.restPos.x * (1.0 + cornerSpread);
      }
      if (bones.rMouthCorner && bones.rMouthCorner.userData.restPos) {
        bones.rMouthCorner.position.y = bones.rMouthCorner.userData.restPos.y + rSmile + (visemeWeights.ee * 0.003);
        bones.rMouthCorner.position.x = bones.rMouthCorner.userData.restPos.x * (1.0 + cornerSpread);
      }
    }

    const jawAmt = visemeWeights.jawOpen || 0;
    const roundness = Math.max(visemeWeights.ou || 0, visemeWeights.oh || 0);
    if (bones.jaw && bones.jaw.userData && bones.jaw.userData.restPos) {
      bones.jaw.position.y = bones.jaw.userData.restPos.y - (0.0048 * jawAmt);
      bones.jaw.rotation.x = -0.055 * jawAmt;
    }
    if (bones.lLipLower && bones.lLipLower.userData && bones.lLipLower.userData.restPos) {
      bones.lLipLower.position.y = bones.lLipLower.userData.restPos.y - (0.0058 * jawAmt);
      bones.lLipLower.position.z = bones.lLipLower.userData.restPos.z + (0.0025 * roundness);
    }
    if (bones.rLipLower && bones.rLipLower.userData && bones.rLipLower.userData.restPos) {
      bones.rLipLower.position.y = bones.rLipLower.userData.restPos.y - (0.0058 * jawAmt);
      bones.rLipLower.position.z = bones.rLipLower.userData.restPos.z + (0.0025 * roundness);
    }
    if (bones.lLipUpper && bones.lLipUpper.userData && bones.lLipUpper.userData.restPos) {
      bones.lLipUpper.position.y = bones.lLipUpper.userData.restPos.y + (0.0026 * jawAmt);
    }
    if (bones.rLipUpper && bones.rLipUpper.userData && bones.rLipUpper.userData.restPos) {
      bones.rLipUpper.position.y = bones.rLipUpper.userData.restPos.y + (0.0026 * jawAmt);
    }

    // Eyebrows driven by emotional state + speech emphasis + surprise
    const browRaise = (cur.surprised * 0.011) + (cur.happy * 0.003) + (jawAmt * 0.0025);
    const browInnerTilt = cur.browTilt * 0.009;
    if (bones.lBrowIn && bones.lBrowIn.userData && bones.lBrowIn.userData.restPos) {
      bones.lBrowIn.position.y = bones.lBrowIn.userData.restPos.y + browRaise + browInnerTilt;
    }
    if (bones.rBrowIn && bones.rBrowIn.userData && bones.rBrowIn.userData.restPos) {
      bones.rBrowIn.position.y = bones.rBrowIn.userData.restPos.y + browRaise + browInnerTilt;
    }
    if (bones.lBrowOut && bones.lBrowOut.userData && bones.lBrowOut.userData.restPos) {
      bones.lBrowOut.position.y = bones.lBrowOut.userData.restPos.y + browRaise - (browInnerTilt * 0.45);
    }
    if (bones.rBrowOut && bones.rBrowOut.userData && bones.rBrowOut.userData.restPos) {
      bones.rBrowOut.position.y = bones.rBrowOut.userData.restPos.y + browRaise - (browInnerTilt * 0.45);
    }

    // Eyeballs: combine gauge gaze + micro-saccades continuously every frame!
    if (bones.lEyeball && bones.rEyeball) {
      const effYaw = (typeof THREE !== 'undefined')
        ? THREE.MathUtils.clamp((gazeYaw * 0.45) + this._saccadeYaw, -0.35, 0.35)
        : 0;
      const effPitch = (typeof THREE !== 'undefined')
        ? THREE.MathUtils.clamp((gazePitch * 0.45) + this._saccadePitch, -0.25, 0.25)
        : 0;
      bones.lEyeball.rotation.y = effYaw;
      bones.lEyeball.rotation.x = effPitch;
      bones.rEyeball.rotation.y = effYaw;
      bones.rEyeball.rotation.x = effPitch;
    }
  }
}

window.VRM_CORE_PINNED_CLIPS = VRM_CORE_PINNED_CLIPS;
window.VrmClipLruCache = VrmClipLruCache;
window.createVrmaClipStore = createVrmaClipStore;
window.buildMaskedUpperBodyClip = buildMaskedUpperBodyClip;
window.parseVrmCapabilities = parseVrmCapabilities;
window.VrmSpringBoneSolver = VrmSpringBoneSolver;
window.VrmSpeechVisemeController = VrmSpeechVisemeController;
window.VrmExpressionController = VrmExpressionController;

function selectVrmQualityPreset(mode) {
  if (typeof applyAdaptiveQualityPreset === 'function') applyAdaptiveQualityPreset(mode);
  document.querySelectorAll('.vrm-q-btn').forEach((b) => {
    const active = b.id === `btnVrmQual${mode}`;
    b.style.borderColor = active ? 'var(--accent-cyan, #38bdf8)' : '';
    b.style.background = active ? 'rgba(56, 189, 248, 0.22)' : '';
    b.style.color = active ? '#fff' : '';
  });
}

function selectVrmEmoteIntensity(mode) {
  if (typeof setVrmEmoteIntensity === 'function') setVrmEmoteIntensity(mode);
  document.querySelectorAll('.vrm-e-btn').forEach((b) => {
    const active = b.id === `btnVrmEmote${mode}`;
    b.style.borderColor = active ? 'var(--accent-pink, #ec4899)' : '';
    b.style.background = active ? 'rgba(236, 72, 153, 0.22)' : '';
    b.style.color = active ? '#fff' : '';
  });
}

window.selectVrmQualityPreset = selectVrmQualityPreset;
window.selectVrmEmoteIntensity = selectVrmEmoteIntensity;
window.addEventListener('DOMContentLoaded', () => {
  try {
    selectVrmQualityPreset(localStorage.getItem('carpi5_vrm_quality') || 'AUTO');
    selectVrmEmoteIntensity(localStorage.getItem('carpi5_vrm_emote_intensity') || 'EXPRESSIVE');
  } catch (e) {}
});
