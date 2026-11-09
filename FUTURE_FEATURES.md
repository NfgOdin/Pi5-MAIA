# 🚀 CarPi5 Confirmed Future Features Backlog (`FUTURE_FEATURES.md`)

This living document tracks all planned, brainstormed, and confirmed features for the CarPi5 Dodge Dart Cockpit & R.U.M. AI Companion system.
> **Rule:** When a feature is implemented and verified in production, it is documented in the release notes and removed from this active backlog.

---

## ✅ Completed & Verified in Production (Latest Release)

- [x] **Teakwood Balcony Terrace & Ocean Overlook**: Full architectural 3D terrace extension with teak deck planks, iron railings, open door threshold, and ocean horizon view.
- [x] **Dynamic Camera Occlusion Fading**: 3D raycasting lerps intervening room walls and doorframes to 0.22 opacity when R.U.M. passes behind them, maintaining unbroken visual eye contact with the driver.
- [x] **Touchscreen Kinetic Scrolling Engine**: Silky smooth touch-drag and momentum fling physics across all cockpit views without desktop scrollbars.
- [x] **Universal Scrollbar Suppression**: Complete elimination of desktop scrollbars across 1024x600 in-dash UI (`*::-webkit-scrollbar { display: none }`).
- [x] **YouTube Touch Exit System**: Persistent, draggable floating touch pill (`◀ CARPI5 EXIT`) auto-injected via DevTools Protocol into external apps, with one-tap cockpit return and dual-direction process management.
- [x] **Boot Greeting De-bouncing & Sound Normalization**: Single greeting lifecycle on startup, eliminates chatter, and expands `MPH` to `"miles per hour"` in TTS speech.
- [x] **Zero "Authentication Required" Boot Popups**: System Polkit policy installed for headless automotive auto-login.

---

## 🏎️ 1. 3D World & VRM Companion Architecture

### 🧸 Affordance-Driven Autonomous Object Interaction & Room Styling
- **Concept:** Beyond simple static decoration, objects in R.U.M.'s room possess **Semantic Affordance Vectors**:
  - `Basketball`: Elasticity, dribble mechanics, finger spin, toss against wall when parked.
  - `MultiAir Wrench & Turbo Diagnostics Manifold`: Utility prop held when inspecting DTCs or oil temps.
  - `Warm Sunset Mug`: Ambient steam; held with both hands during cold morning drives.
- **Autonomous Room Organization:** When enabled in Settings, R.U.M. tidies her room when parked—rearranging manuals, placing tools on the workbench, and putting away items based on a Belief-Desire-Intention (BDI) behavioral state machine.
- **Vehicle G-Force Physical Coupling:** Longitudinal and lateral G-forces from OBD-II / CAN-bus physically push loose room items and sway R.U.M.'s hair and kimono ribbons under hard braking and spirited cornering.

---

## 🪰 2. Biomimetic Connectome Brain ("Pip" the Fruit Fly)

### 🔬 Full Janelia FlyWire 2024 Whole-Brain Motor Integration
- **Concept:** Complete mapping of the 139,255-neuron connectome from the adult female *Drosophila* (specimen FAFB / FlyWire 2024 *Nature* publication) to flight physics.
- **Motor Control & Aerodynamics:**
  - Wing stroke amplitude and pitch directly modulated by `W-DN` (Wing Steering Descending Neurons).
  - Haltere gyroscopic balance reflexes stabilizing rapid banking turns without 180° snap glitches.
  - Multi-sensory inputs: Phototaxis (reacting to day/night cockpit lighting), cabin sound wave vibrations, and cabin thermal gradients.
- **Lore & Backstory ("Pip"):** Rescued by R.U.M. from a benchmark dataset in the Pi 5's memory buffer, Pip is R.U.M.'s devoted cybernetic pet who buzzes around the room, perches on R.U.M.'s hand, and reacts to turbo boost spikes.
- **Interactive Rigging:** Custom articulated 3D insect model with independent wings, legs, and antennae, scaled for clear cockpit visibility.

---

## ⚡ 3. Hardware Accelerators & Co-Processor Architecture

### 🧠 Hailo-10H M.2 HAT+ AI Acceleration ($200 Spec)
- **Target Hardware:** Hailo-10H M.2 Generative AI module (40 TOPS INT4 / 20 TOPS INT8, 8GB dedicated on-module LPDDR4 memory).
- **Execution Capability:**
  - Concurrent on-device execution of 7B parameter LLMs (Llama-3.1-8B, Qwen2.5-7B) at 15–20 tokens/sec.
  - Concurrent Whisper Small/Medium speech recognition engine.
  - Real-time Stable Diffusion turbo generation for situational avatars and customized trip postcards.
- **Zero Pi 5 RAM Contention:** Offloads all model weights and KV caches directly to the Hailo module's onboard 8GB RAM, keeping the Pi 5's 8GB system RAM 100% free for Three.js 60fps rendering, Chromium, CAN logging, and audio processing.

### 🔌 Multi-SBC Dual-Board Hardware Studio & Telemetry Streaming
- **Telemetry Throttling:** On-demand / single-shot refresh button for Raspberry Pi 3 co-processor over Gigabit Ethernet to eliminate bus contention.
- **Optional Auto-Stream Toggle:** Checkbox to enable real-time 1Hz background streaming when running diagnostics or bench tuning.
- **Component Telemetry Coverage:** Per-core CPU load and frequencies, VideoCore VII GPU load/frequencies, Hailo NPU utilization/thermal load, USB bus current draws, and ambient chassis temperatures.

---

## 📞 4. In-Cabin Free Wi-Fi Phone & R.U.M. Receptionist

### 📱 In-Dash VoIP Cellular Line
- **Connectivity:** Uses phone Wi-Fi hotspot connection to power a dedicated vehicle phone number (TextNow Web / Google Voice VoIP).
- **Automotive Ergonomics:** Full touch dialer with 52px numeric buttons, recent call logs, contacts phonebook, and SMS texting panel.
- **R.U.M. AI Receptionist Mode:**
  - R.U.M. announces caller identity through car speakers.
  - Capable of screening calls: R.U.M. answers unknown callers, transcribes the caller's message in real time, and asks the driver if they want to pick up.
  - Hands-free voice commands: *"R.U.M., call the tire shop"* or *"R.U.M., read my latest text."*

---

## 👧 5. Daughter Persona & Adaptive LoRA Fine-Tuning

### 💖 R.U.M. Daughter Persona Shift
- **Character Dynamic:** Shifts from a younger-sister dynamic to a dedicated, loving, spirited daughter co-pilot who adores riding with her dad in the Dodge Dart MultiAir Turbo.
- **Curated Dataset & Fine-Tuning:**
  - Specialized conversational Q&A dataset capturing affectionate banter, automotive enthusiasm, boost coaching, and genuine care for her dad's driving safety.
  - LoRA adapter fine-tuned on Qwen2.5-3B / Llama-3.2-3B for local GGUF and NPU execution.
