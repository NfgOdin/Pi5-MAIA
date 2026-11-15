# 🚀 CarPi5 Confirmed Future Features Backlog (`FUTURE_FEATURES.md`)

This living document tracks all planned, brainstormed, and confirmed features for the CarPi5 Dodge Dart Cockpit & R.U.M. AI Companion system.
> **Rule (AGENTS.md #7):** When a feature is implemented and verified in production, it is documented in `ROADMAP.md` and moved to the Completed section here so nothing is ever lost or forgotten.

---

## 📋 Active Implementation Backlog

### 👁️ 1. Advanced In-Cabin Perception & Dashcam Vision (Phase 7)
- **Driver State & Drowsiness Monitoring**: Process cabin IR camera stream with lightweight eye-aspect-ratio (EAR) and yawning detection; triggers loving daughter alertness reminders if eyes droop for >1.8s on highway.
- **Dashcam Road Sign & Speed Limit OCR**: Process forward dashcam frames through quantized Tesseract / MobileNet OCR, caching speed limits and notifying Dad if cruising >15 mph over posted limit.
- **Pi 3 Hardware Dashcam Synchronization**: Zero-latency RTSP / MJPEG bridge over local Ethernet (`10.0.0.2:8000`) with automatic auto-reconnect and hardware H.264 recording.

### 🧸 2. 3D World & VRM Companion Architecture
- **Affordance-Driven Autonomous Object Interaction & Room Styling**:
  - Objects possess **Semantic Affordance Vectors**: `Basketball` (elasticity, dribble mechanics), `MultiAir Wrench` (held during DTC inspection), `Sunset Mug` (ambient steam).
  - Autonomous Room Organization when parked based on Belief-Desire-Intention (BDI) state machine.
  - Physical G-force coupling physically swaying loose room items and R.U.M.'s hair and ribbons.

### ⚡ 3. Hardware Accelerators & Co-Processor Architecture
- **Hailo-10H M.2 HAT+ AI Acceleration ($200 Spec)**:
  - 40 TOPS INT4 / 20 TOPS INT8 with 8GB dedicated on-module LPDDR4 memory.
  - Concurrent execution of 7B parameter LLMs (Qwen2.5-7B) at 15–20 tokens/sec.
  - Offloads model weights and KV caches entirely from Pi 5 system RAM.
- **Multi-SBC Dual-Board Hardware Studio & Telemetry Streaming**:
  - Telemetry throttling with on-demand refresh for Raspberry Pi 3 co-processor over Gigabit Ethernet.
  - Component telemetry coverage: per-core load, VideoCore VII GPU load, Hailo NPU thermals, USB current draws.

### 👧 4. Adaptive LoRA Fine-Tuning & Dynamic Knowledge Graph
- **Curated Dataset & Fine-Tuning**:
  - Specialized conversational Q&A dataset capturing affectionate banter, automotive enthusiasm, boost coaching, and driving safety.
  - LoRA adapter fine-tuned on Qwen2.5-3B for local GGUF and NPU execution.

---

## 🏆 Completed & Verified in Production (Latest Release)

- [x] **Canyon Run Sector Split Lap Timer & Brake/Tire Thermal Degradation Telemetry (Phase 18)**: Calibrated thermodynamic rotor fade and 4-corner tire adhesion model for Dodge Dart 1.4L Turbo MultiAir with regional Arizona twisties sector timing.
- [x] **Voice Intent Auto-Actuation & Media Bus (Phase 16)**: Spoken voice intents for volume, lighting, night mode, screen navigation, and media playback.
- [x] **In-Cabin Hands-Free Phone, Family Kinship & AI Receptionist Studio (Phase 15)**: Dual-provider telephony (Bluetooth HFP & VoIP), daughter-centric kinship contact book, and automated in-character screening for unknown callers.
- [x] **Permanent TTS Voice Library & SQLite WAL Caching (Phase 14)**: Crash-safe SQLite WAL audio registry, clause memoization, and offline pre-warming suite.
- [x] **Cockpit AEC, Fast-CAN Batching & WebGL Thermal Hardening (Phase 13)**: Native WebRTC AEC + RNNoise filter chain, hybrid multi-PID CAN query batching, and WebGL thermal throttling.
- [x] **Living Memory, Episodic RAG & Relationship Bond Engine (Phase 12)**: 4-layer cognitive memory architecture, post-drive "dream" consolidation, R.U.M. personal trip diary, and bond progression milestones.
- [x] **Offline Turn-by-Turn Route Navigation & OSM Speed Limit HUD (Phase 11)**: Regional topological routing engine, OSM speed limit snapping with MUTCD R2-1 badge, and glassmorphic top navigation HUD banner.
- [x] **Biomimetic Connectome Brain ("Pip" the Fruit Fly - Phase 5)**: Princeton FlyWire 2024 adult Drosophila connectome SNN with mechanoreceptor haltere coupling.
- [x] **Teakwood Balcony Terrace & Ocean Overlook**: 3D architectural extension with dynamic camera occlusion fading and touchscreen kinetic scrolling.
- [x] **Zero "Authentication Required" Boot Popups**: System Polkit policy installed for headless automotive auto-login.
