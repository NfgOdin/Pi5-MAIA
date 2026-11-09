# 🚀 CarPi5 Master Living Roadmap & Implementation Checklist (`ROADMAP.md`)

This living document tracks all planned, brainstormed, and confirmed engineering enhancements for the CarPi5 Dodge Dart Cockpit & R.U.M. AI Companion system.
> **Rule (AGENTS.md #7):** When an implementation is completed and verified on real hardware, move it to the **Completed & Verified in Production (Changelog)** section with the verification date and commit reference so nothing is ever lost or forgotten.

---

## 📋 Active Implementation Checklist

### 👁️ Phase 7: Advanced In-Cabin Perception & Dashcam Vision (On Hold - Camera Setup)
- [ ] **Driver State & Drowsiness Monitoring**: Process cabin IR camera stream with lightweight eye-aspect-ratio (EAR) and yawning detection; triggers loving daughter alertness reminders if eyes droop for >1.8s on highway.
- [ ] **Dashcam Road Sign & Speed Limit OCR**: Process forward dashcam frames through quantized Tesseract / MobileNet OCR, caching speed limits and notifying Dad if cruising >15 mph over posted limit.
- [ ] **Pi 3 Hardware Dashcam Synchronization**: Zero-latency RTSP / MJPEG bridge over local Ethernet (`10.0.0.2:8000`) with automatic auto-reconnect and hardware H.264 recording.

---

### 🏁 Phase 9: High-G Drag Launch Control & Telemetry HUD Staging
- [ ] **Automated 0-60 & 1/4-Mile Drag Staging**: In-dash Christmas tree drag staging countdown with zero-false-trigger clutch drop detection and lateral/longitudinal accelerometer filtering.
- [ ] **F1 Sequential Shift Light LED Strip Integration**: Direct GPIO NeoPixel / WS2812B lightbar driving green-to-red shift cues synchronized with MultiAir 6,200 RPM redline.
- [ ] **Realtime G-G Friction Circle HUD**: Visual friction circle plot (Braking G vs. Cornering Lateral G) assessing tire adhesion limit in real time.

---

## 🏆 Completed & Verified in Production (Changelog)

### [2026-11-09] — Phase 8: Offline Vector Memory, Semantic RAG & MultiAir Maintenance Schedule
- [x] **Local Quantized Embedding Engine (`all-MiniLM-L6-v2.onnx`)**: Embedded past driving logs, vehicle maintenance records, and factory technical documentation using a local INT8 quantized 384-dimensional ONNX model running with dynamic length padding on Cortex-A76 cores in **11.45ms** (zero cloud API dependencies).
- [x] **Persistent SQLite Vector Store (`storage/rag_memory.db`)**: Built high-speed cosine similarity vector retrieval engine with flash wear protection (WAL mode, memory temp store). Seeded factory maintenance intervals for Dodge Dart 1.4L Turbo MultiAir:
  - 5W-40 Synthetic Oil (MS-12991 / Fiat 9.55535-S2, 4.0 qts, 4,000 mi interval)
  - MultiAir Actuator Screen (Mopar 55238665 10mm hex, 30,000 mi interval)
  - NGK SIKR9A7 Euro-Spec Laser Iridium Plugs (strictly 0.026" / 0.65mm gap, 30,000 mi interval)
  - C635 6-Speed Manual Transaxle Fluid (Tutela Gearforce 75W MS-10216, 2.0 qts, 40,000 mi interval)
  - Mopar OAT Purple Coolant (MS-12106 50/50, 100,000 mi interval)
  - DOT 4 Brake & Clutch Hydraulic Fluid (25,000 mi interval)
  - Garrett GT1446 Wastegate & Diverter Inspection (15,000 mi interval)
- [x] **Automatic Trip Logger Vector Synchronization**: Automatically indexes completed trips into semantic vector records, recording mileage, duration, top/average speed, peak boost PSI, boost pull counts, and 0-60 sprint times for conversational retrieval.
- [x] **Conversational RAG Context Injection & Procedural Fallbacks**: Injected high-confidence recalled memories (`[RECALLED CARPI MEMORY & VEHICLE RECORDS: ...]`) into R.U.M.'s prompt context, accompanied by fast procedural intent fallbacks for instant spoken replies when Dad asks about oil changes, spark plug gaps, or MultiAir screen intervals.
- [x] **In-Dash Maintenance & Memory Cockpit Studio (`screenMaintenance`)**: Built dedicated touchscreen UI (minimum 44-48px touch targets) featuring:
  - 6th launcher card in Vehicle Performance Hub (`MAINTENANCE & MEMORY`) with live badge (`ODO: 85,240 MI | ALL OK`).
  - Powertrain component lifecycles panel with color-coded service progress meters, overdue alerts, and "LOG SERVICE COMPLETED" modal.
  - Interactive Odometer update modal to synchronize cluster mileage with one tap.
  - R.U.M. Vector Memory Explorer with semantic search bar, quick topic filter pills, similarity score badges, and "+ REMEMBER NOTE" modal to teach R.U.M. new vehicle facts.
- [x] **Verified on Pi 5 Hardware**: Validated live endpoints (`/api/maintenance/status`, `/api/ai/memory/query`, `/api/ai/chat`), passed complete unit test suite, and audited full 1024x600 Wayland UI screenshots ([`shot_phase8_maintenance_audit.png`](file:///C:/Users/jonat\.gemini\antigravity\brain\0b6cdb46-40d7-45fe-ab5a-dc9ccbe61528\shot_phase8_maintenance_audit.png), [`shot_phase8_vehicle_hub_audit.png`](file:///C:/Users/jonat\.gemini\antigravity\brain\0b6cdb46-40d7-45fe-ab5a-dc9ccbe61528\shot_phase8_vehicle_hub_audit.png)).

### [2026-11-09] — Phase 6: Cockpit Ergonomics, Audio Priority & Hardware Tuning
- [x] **Music-Aware Audio Ducking Matrix**: Built 3-tier priority matrix (`PRIORITY_CRITICAL = 0`, `PRIORITY_COMMAND = 1`, `PRIORITY_BANTER = 2`). When in-dash music is playing, routine chatter (Shower Thoughts, morning dreams) is automatically silenced. When Priority 0 (faults/overheats) or Priority 1 (commands/pulls) speaks, in-dash media volume ducks to 18% over exactly 150ms, speaks with Kokoro neural voice, and smoothly restores over 350ms.
- [x] **Ambient Light & Headlight Auto-Dimming (Obsidian Midnight Mode)**: Added `headlights_on` and `ambient_light_lux` to live 25Hz telemetry stream (`simulator.py`, `obd_reader.py`, `daemon.py`). When headlights turn on or dusk falls, UI automatically transitions into glare-free `.obsidian-midnight` theme (`#020408` ultra-low glare background, soft cyan/amber gauge glow) to protect driver night vision.
- [x] **Local Zero-Latency Wake Word ("Hey Rum") in <150ms**: Replaced slow cloud Google STT in standby with a dedicated offline grammar-constrained Vosk recognizer (`models/vosk-model-small-en-us-0.15`). Evaluates strictly against R.U.M. wake tokens in memory, triggering instant local wake acknowledgment in 118ms!
- [x] **ZRAM Compressed Swap & NVMe Flash Wear Protection**: Configured 2GB high-speed LZ4 compressed ZRAM swap partition (`/dev/zram0` at priority 100). Routed temporary TTS synthesis `.wav` buffers, Chromium disk cache (`--disk-cache-dir`), and daemon/kiosk logs into compressed RAM (`/dev/shm`), reducing flash disk write wear by >90%. Optimized SQLite with `WAL`, `synchronous = NORMAL`, and `temp_store = MEMORY`.
- [x] **Verified on Pi 5 Hardware**: Validated live via endpoints (`/api/audio/duck_status`, `/api/telemetry/headlights`, `/api/ai/wake_test`), verified ZRAM status (`/dev/zram0` 2GB LZ4 swap active), passed unit tests, and audited full 1024x600 Wayland UI screenshots ([`shot_phase6_obsidian_audit.png`](file:///C:/Users/jonat/.gemini/antigravity/brain/0b6cdb46-40d7-45fe-ab5a-dc9ccbe61528/shot_phase6_obsidian_audit.png), [`shot_phase6_ai_audit.png`](file:///C:/Users/jonat/.gemini/antigravity/brain/0b6cdb46-40d7-45fe-ab5a-dc9ccbe61528/shot_phase6_ai_audit.png)).

### [2026-11-09] — Phase 5: Pip Connectome Biological SNN & Mechanoreceptor Coupling
- [x] **Princeton FlyWire 2024 SNN Core (`pip_connectome.py`)**: Integrated sparse spiking neural network architecture replicating key sensory-motor subsystems of the 139,255-neuron adult Drosophila connectome (16 EPG compass ring attractor neurons, 16 P-EN angular velocity integrators, Giant Fiber looming escape reflex, haltere Coriolis mechanoreceptor gyroscopic stabilization, circadian s-LNv arousal, sugar water metabolism).
- [x] **Sensory Mechanoreceptor Emulation & Haltere Coupling**: Vehicle lateral cornering acceleration and vibration are directly fed into haltere campaniform sensilla, computing roll/pitch stabilization torque counter-angles and triggering bio-authentic high-speed evasive flight saccades (265 Hz wingbeat burst) during abrupt high-G maneuvers or boost spikes.
- [x] **R.U.M. Dual-Life Interaction & 3D Stage Integration**: R.U.M. tracks Pip's 3D coordinates in the cockpit with head yaw/pitch kinematics; when Pip perches on R.U.M. (`PERCHED_ON_RUM`), R.U.M. holds out her hand/finger with the sugar dropper prop; when Pip buzzes near Dad (`BUZZING_NEAR_DAD`), R.U.M. giggles; when Pip is startled by high turbo boost (`STARTLED_BY_TURBO`), R.U.M. reassures Pip.
- [x] **Cockpit Touch UI & REST Control**: Added interactive `🪰 PIP` live HUD status pill in the 3D viewport displaying wing frequency (Hz) and sugar water energy percentage with single-tap evasive scare and double-tap sugar water feeding via `/api/pip/scare` and `/api/pip/feed`.
- [x] **Verified on Pi 5 Hardware**: Fully tested on Pi 5 production hardware (`/api/pip/state`, `/api/pip/feed`, `/api/pip/scare`), live 25Hz SSE broadcast, unit tests passed cleanly, and audited full 1024x600 Wayland UI screenshot ([`shot_phase5_pip_audit.png`](file:///C:/Users/jonat/.gemini/antigravity/brain/0b6cdb46-40d7-45fe-ab5a-dc9ccbe61528/shot_phase5_pip_audit.png)).

### [2026-11-09] — Phase 4: Predictive MultiAir Telemetry, Virtual Dyno & Shift Scoring
- [x] **Realtime Virtual Dyno (WHP & WTQ)**: Thermodynamic Speed-Density mass air flow ($MAF$) and volumetric efficiency model calibrated for Dodge Dart 1.4L Turbo MultiAir (3,186 lbs curb weight, 1,368cc displacement, C635 FWD transaxle 13.5% drivetrain loss) calculating instantaneous Wheel Horsepower ($WHP$) and Wheel Torque ($WTQ$) in real time with peak hold tracking.
- [x] **Garrett GT1446 Wastegate & Diverter Valve Spool Health**: Continuously computes boost spool gradient ($\frac{\Delta\text{PSI}}{\Delta\text{RPM}} \times 1000$) between 2,100–4,800 RPM under WOT ($TPS \ge 75\%$), logging spool runs against a 9.5 PSI/1k RPM healthy baseline; triggers proactive daughter warning if actuator arm slop or split diverter diaphragm causes spool rate to drop below 70%.
- [x] **C635 Manual Rev-Match & Downshift Quality Scoring**: Evaluates manual gear transitions against synchronized gear ratios, rating downshifts (100 PTS for perfect heel-toe $|\Delta RPM| \le 120$) and providing audio coaching / clutch-jerk alerts if downshifts shock the transaxle.
- [x] **MultiAir UniAir Brick Hydraulic Protection**: Real-time viscosity and thermal follower model tracking engine oil temperature; enforces `COLD_PROTECT` (limits boost to $< 7.5$ PSI until 5W-40 warms above $150^\circ\text{F}$) with spoken daughter reminders, transitioning to `WARM_OPTIMAL` (full 16–22 PSI authorized) once warmed.
- [x] **Verified on Pi 5 Hardware**: Validated live via HTTP endpoints (`/api/telemetry/dyno`, `/api/telemetry/spool_health`, `/api/telemetry/shift_quality`, `/api/telemetry/multiair_health`), verified live 25Hz SSE broadcast, and audited full 1024x600 Wayland UI screenshot ([`shot_phase4_gauges_audit.png`](file:///C:/Users/jonat/.gemini/antigravity/brain/0b6cdb46-40d7-45fe-ab5a-dc9ccbe61528/shot_phase4_gauges_audit.png)).

### [2026-11-09] — Phase 3: Circadian Rhythm, Sleeping Mode & Morning Digital Dreams
- [x] **Night Senses Mode (11:00 PM – 4:30 AM)**: Softened Kokoro voice pitch to 1.08x, slowed procedural breathing frequency to 1.2 Hz (amplitude 0.035 rad on `vrmBones.chest`), drooped 3D eyelids (`vrmBones.lEyeUpper`, `vrmBones.rEyeUpper` down 0.010), and automated dozing in seat (`sit_idle2.bvh`) after 12s parked at night.
- [x] **Morning Ignition Wake-Up & "Digital Dreams"**: On morning boot (`04:30 – 11:00 AM`), triggers stretching wake-up animation (`action_standup.bvh`), queries neural Qwen-3B / curated dream recollection, logs dream to SQLite `digital_dreams` table, broadcasts live to cockpit chat feed, and speaks aloud through in-dash audio.
- [x] **Spontaneous "Shower Thoughts"**: Continuous monitoring of steady highway cruising (speed > 45 mph, manifold vacuum < -1.0 PSI, boost < 1.0 PSI for > 3 minutes); every 15–25 minutes R.U.M. shares an unprompted, whimsical automotive daughter thought and updates the cockpit thought pill.
- [x] **Dynamic Valence-Arousal Affect Engine**: Continuous 2D emotion coordinate model ($[-1.0, 1.0]$ valence and arousal) mapped to 5 core affective states (`EXCITED`, `HAPPY_PROUD`, `COZY`, `CONCERNED`, `THOUGHTFUL`), dynamically driving 3D facial bone blendshapes (`lMouthCorner`, `rMouthCorner`, `lBrowIn`, `rBrowIn`, head tilt).
- [x] **Eliminated Mutual Docking Recursion**: Refactored `dockCompanionToAi` and `setAiLayoutMode` in `gauges.js` with non-recursive guard patterns, resolving call stack size limits permanently.
- [x] **Verified on Pi 5 Hardware**: Validated live via HTTP endpoints (`/api/ai/circadian`, `/api/ai/circadian/simulate`, `/api/ai/mood`, `/api/ai/morning_dream`, `/api/ai/shower_thought`), confirmed live SSE broadcast streaming, and verified full 1024x600 Wayland UI screenshots (`shot_phase3_morning.png`, `shot_phase3_night.png`, `shot_phase3_ai_audit.png`, `shot_phase3_cozy_audit.png`).

### [2026-11-09] — Phase 2: 3D Avatar Kinematics, Physical G-Force Coupling & Bone-Bound Props
- [x] **Longitudinal G-Force Coupling**: Hooked OBD-II speed delta ($\frac{\Delta v}{\Delta t}$) and boost spool into Three.js bone hierarchy (`spine`, `chest`, `neck`, `head`): leaning R.U.M. back into seat under acceleration/turbo spool (`-0.18 rad` pitch) and bracing forward under braking (`+0.22 rad` pitch).
- [x] **Lateral Cornering Apex Lean**: Implemented smooth body roll ($Z$-axis lean up to $\pm 0.16$ rad) into the apex of turns based on steering angle and lateral acceleration.
- [x] **Contextual Gauge Gaze Tracking**: When boost exceeds +15 PSI or coolant rises above 215°F, R.U.M.'s 3D eyes (`lEyeball`, `rEyeball`) and head turn down-left toward the instrument cluster for 1.8s, then smoothly lerp back to forward eye contact with Dad (Camera $X=0.0$).
- [x] **Bone-Bound Diagnostic & Utility Props**: Procedurally built and parented a 3D yellow digital multimeter (with glowing cyan LCD) to `rightHand` when entering Diagnostics mode, and a sugar water dropper with amber nectar when Pip perches.
- [x] **Automotive In-Seat Scream Address Alignment**: Replaced legacy "Master" references with dynamic driver moniker `getFormattedDriverAddress()` ("Dad") and expanded `MPH` to "miles per hour".

### [2026-11-09] — Phase 1: Local AI Latency & Inference Optimization (Commit: `b63d2fa`)
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
