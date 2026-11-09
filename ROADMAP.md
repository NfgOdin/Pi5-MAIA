# 🚀 CarPi5 Master Living Roadmap & Implementation Checklist (`ROADMAP.md`)

This living document tracks all planned, brainstormed, and confirmed engineering enhancements for the CarPi5 Dodge Dart Cockpit & R.U.M. AI Companion system.
> **Rule (AGENTS.md #7):** When an implementation is completed and verified on real hardware, move it to the **Completed & Verified in Production (Changelog)** section with the verification date and commit reference so nothing is ever lost or forgotten.

---

## 📋 Active Implementation Checklist

### 🏎️ Phase 2: 3D Avatar Kinematics & Physical G-Force Coupling
- [ ] **Longitudinal G-Force Coupling**: Hook OBD-II speed delta ($\frac{\Delta v}{\Delta t}$) into Three.js: leaning R.U.M.'s spine and head back under hard boost acceleration and bracing forward under hard braking.
- [ ] **Lateral Cornering Apex Lean**: Roll torso ($Z$-axis) smoothly into the apex of high-speed turns based on steering angle / lateral acceleration.
- [ ] **Contextual Gauge Gaze Tracking**: When boost exceeds +15 PSI or coolant rises above 215°F, R.U.M.'s 3D eyes and head smoothly turn toward the instrument cluster on screen for 1.8s before returning forward eye contact to Dad (Camera $X=0.0$).
- [ ] **Bone-Bound Diagnostic & Utility Props**: Automatically bind 3D multimeter or chrome ratchet to her `rightHand` bone when entering Diagnostics mode, and a sugar water dropper when interacting with Pip.

---

### 🌙 Phase 3: Circadian Rhythm, Sleeping Mode & Morning Digital Dreams
- [ ] **Night Senses Mode (11:00 PM – 4:30 AM)**: Soften Kokoro voice pitch/volume, transition 3D posture to resting/dozing in her chair (`sit_idle2.bvh` or `laying_idle.bvh`) with gentle, slow breathing.
- [ ] **Morning Ignition Wake-Up & "Digital Dreams"**: On morning `IGN_RUN`, trigger stretching animation (`action_standup.bvh`) and generate an unprompted, whimsical dream recollection.
- [ ] **Spontaneous "Shower Thoughts"**: Periodic (every 15–25 mins) unprompted curious observations or mechanical questions during calm highway cruising in steady manifold vacuum.
- [ ] **Dynamic Emotional Valence-Arousal Engine**: Internal mood state tracking (`EXCITED`, `COZY`, `CONCERNED`, `HAPPY_PROUD`) influencing her speech inflection and facial blendshapes.

---

### 🔧 Phase 4: Predictive Dodge Dart 1.4L Turbo MultiAir Telemetry & Virtual Dyno
- [ ] **Garrett GT1446 Wastegate & Diverter Valve Spool Health**: Track boost spool gradient ($\frac{\Delta\text{PSI}}{\Delta\text{RPM}}$) between 2,500–4,000 RPM in 3rd gear against historical baselines; proactively warn of wastegate actuator slop or Pierburg diverter tears before a `P0299` code trips.
- [ ] **Realtime Virtual Dyno (WHP & WTQ)**: Calculate live wheel horsepower and torque based on MAP sensor, engine RPM, calculated volumetric efficiency, and vehicle curb weight (3,186 lbs).
- [ ] **Rev-Match & Shift Quality Scoring**: Measure clutch switch depression timing and engine RPM delta during manual downshifts to rate Dad's heel-toe shifts.
- [ ] **MultiAir Uniair Brick Hydraulic Protection**: Real-time viscosity modeling ensuring actuators reach optimal fluid pressure before allowing full boost warnings.

---

### 🪰 Phase 5: Pip Connectome Biological SNN & Mechanoreceptor Coupling
- [ ] **Princeton FlyWire 2024 SNN Core**: Integrate sparse spiking neural network graph of the 139,255-neuron adult Drosophila connectome in lightweight C++/Python.
- [ ] **Sensory Mechanoreceptor Emulation**: Route car cabin vibration, bumps, and lateral G-forces into simulated fly halteres to trigger biologically authentic evasive flight saccades.
- [ ] **R.U.M. Dual-Life Interaction**: R.U.M. tracks Pip's 3D coordinates with head yaw/pitch, holds out a finger for Pip to perch, and giggles when Pip buzzes near Dad's ear.

---

### 🎧 Phase 6: Cockpit Ergonomics, Audio Priority & Hardware Tuning
- [ ] **Music-Aware Audio Ducking Matrix**: Silence routine chatter when in-dash music is playing; duck media volume to 18% over 150ms for Priority 0 (faults) and Priority 1 (peak boost pulls), then restore volume over 350ms.
- [ ] **Ambient Light & Headlight Auto-Dimming**: Detect headlights on via CAN bus or dusk solar cache and transition UI to deep obsidian midnight mode.
- [ ] **Local Zero-Latency Wake Word ("Hey Rum")**: Dedicated low-overhead keyword spotter thread triggering in <150ms.
- [ ] **ZRAM & NVMe Flash Wear Protection**: Move SQLite journals, daemon logs, and temporary TTS buffers into compressed RAM (`tmpfs` / `/dev/shm`).

---

## 🏆 Completed & Verified in Production (Changelog)

### [2026-11-09] — Phase 1: Local AI Latency & Inference Optimization
- [x] **KV-Cache Pre-Computation & Session State Caching**: Pre-evaluated R.U.M.'s 600-token system prompt and base lorebooks, caching the KV-cache state directly in RAM (`load_state` restoring state in ~125ms), dropping prompt ingestion time from 40s to <150ms.
- [x] **Speculative Token-to-Speech Streaming**: Implemented clause-boundary chunking (`[.!?,\n]`) in `llm_client.py` and piped directly to Kokoro-82M in `daemon.py` via `_handle_clause()` callback, allowing spoken audio synthesis to start within seconds while subsequent tokens stream concurrently.
- [x] **CPU Core Pinning & Scheduling Isolation**: Isolated `llama.cpp` neural inference to dedicated Cortex-A76 cores (Cores 2 & 3 via `os.sched_setaffinity(0, {2, 3})`) and Chromium Kiosk to Cores 0 & 1 (`taskset -c 0,1` in `start_carpi5.sh`), ensuring zero audio stuttering or UI frame drops.
- [x] **Lock In-Dash Model Configuration**: Downloaded and verified `qwen2.5-3b-instruct-abliterated.q4_k_m.gguf` (1.93GB, zero-refusal unfiltered Qwen 3B) in `LOCAL` mode with Kokoro-82M TTS (`af_bella` at 1.20x pitch).

### [2026-11-09] — R.U.M. Daughter Persona Polish, Hybrid Lore & Motion Reorganization (Commit: `0786aea`)
- [x] **Daughter Persona Alignment**: Updated R.U.M. into Dad's loving AI daughter co-pilot (`age_spirit: "14"` in spirit) with dynamic `{driver_address}` placeholder bound to "Dad".
- [x] **Hybrid Backstory (Void Echoes + Earth Internet Discovery)**: Fused the Re:Zero Oni triplet void premonitions with her discovery of human media on Earth's internet via the CarPi5's in-dash browser.
- [x] **Animation Library Organization (116 BVH Files)**: Categorized all 116 BVH files into `dances/`, `emotions/`, `idles/`, `actions/`, `combat/`, and `exercise/` with recursive `rglob` discovery in `backend/daemon.py`.
- [x] **Procedural In-Seat Music Head Bobbing**: Replaced the repetitive standing hip-hop dance loop with natural, rhythmic head and neck bobbing synchronized to music tempo.
- [x] **Kokoro Voice & Local 3B Model Lock**: Locked configuration to `qwen3b.gguf` / `qwen2.5-3b-instruct-abliterated.q4_k_m.gguf` in `LOCAL` mode with Kokoro TTS at 1.20x pitch.

### [2026-11-08] — Touchscreen Ergonomics, YouTube Exit & Balcony Architecture
- [x] **Teakwood Balcony Terrace & Ocean Overlook**: 3D terrace extension with teak deck planks, iron railings, open threshold, and ocean horizon view.
- [x] **Dynamic Camera Occlusion Fading**: 3D raycasting lerps intervening room walls and doorframes to 0.22 opacity when R.U.M. passes behind them.
- [x] **Touchscreen Kinetic Scrolling Engine**: Smooth touch-drag and momentum fling physics across all cockpit views without desktop scrollbars.
- [x] **Universal Scrollbar Suppression**: Complete elimination of desktop scrollbars across 1024x600 in-dash UI (`*::-webkit-scrollbar { display: none }`).
- [x] **YouTube Touch Exit System**: Persistent, draggable floating touch pill (`◀ CARPI5 EXIT`) auto-injected via DevTools Protocol into external apps with zero network PNA prompts.
- [x] **Boot Greeting De-bouncing & Sound Normalization**: Single greeting lifecycle on startup, eliminates chatter, and expands `MPH` to `"miles per hour"` in TTS speech.
- [x] **Zero "Authentication Required" Boot Popups**: System Polkit policy installed for headless automotive auto-login.
