# 🚗 CarPi5: Complete System & Engineering Manual

**Vehicle Platform:** 2013 Dodge Dart 1.4L Turbo MultiAir (Magneti Marelli 8GM ECU)  
**Hardware Core:** Dual-SBC Automotive Architecture (Raspberry Pi 5 Master + Raspberry Pi 3 Slave)  
**Display:** 7-Inch Capacitive Touchscreen (1024x600, 60Hz)  
**AI Companion:** R.U.M. (Realtime Underhood MultiAir — The Third Triplet)  
**Operating System:** DietPi Linux (Debian 12 Bookworm, 64-bit Real-Time Kernel)

---

## 📑 Table of Contents
1. [System Architecture & Dual-SBC Topology](#1-system-architecture--dual-sbc-topology)
2. [Operating Philosophy: Zero-Mock & Native Hardware Integration](#2-operating-philosophy-zero-mock--native-hardware-integration)
3. [OBD-II & CAN Bus Diagnostic Subsystem](#3-obd-ii--can-bus-diagnostic-subsystem)
4. [R.U.M. AI Companion & 3D Interactive Rig](#4-rum-ai-companion--3d-interactive-rig)
5. [In-Dash Telemetry & Gauge Cluster Engine](#5-in-dash-telemetry--gauge-cluster-engine)
6. [Automotive Touch Audio Suite & DSP Limiter](#6-automotive-touch-audio-suite--dsp-limiter)
7. [Windows 11 Native File Explorer](#7-windows-11-native-file-explorer)
8. [GPS Navigation & Dragy Performance Timer](#8-gps-navigation--dragy-performance-timer)
9. [Ethernet Dashcam Streaming & Loop Recording](#9-ethernet-dashcam-streaming--loop-recording)
10. [In-Car Troubleshooting & Emergency Reset Protocol](#10-in-car-troubleshooting--emergency-reset-protocol)

---

## 1. System Architecture & Dual-SBC Topology

The CarPi5 system distributes processing across two dedicated single-board computers connected over an isolated gigabit Ethernet bus:

```
+---------------------------------------------------------------------------------+
|                                 CARPI5 COCKPIT                                  |
|                                                                                 |
|   +--------------------------+                 +----------------------------+   |
|   |   Raspberry Pi 5 (8GB)   |  Ethernet IP    |    Raspberry Pi 3 (1GB)    |   |
|   |         MASTER           |<===============>|           SLAVE            |   |
|   |      192.168.0.131       |  192.168.0.141  |       192.168.0.141        |   |
|   +------------+-------------+                 +--------------+-------------+   |
|                |                                              |                 |
|   +------------v-------------+                 +--------------v-------------+   |
|   | 1024x600 Touch Display   |                 | Front Sony IMX219 Dashcam  |   |
|   | Three.js 3D VRM Engine   |                 | H.264 Loop Recording Daemon|   |
|   | 25Hz SSE Telemetry Server|                 | Low-Latency RTSP/MJPEG Feed|   |
|   | 10-Band WebAudio DSP EQ  |                 +----------------------------+   |
|   | Magneti Marelli 8GM OBD  |                                                  |
|   | NEO-6M / NEO-M8N GPS     |                                                  |
|   +--------------------------+                                                  |
+---------------------------------------------------------------------------------+
```

### Pinout & Bus Connections:
- **OBD-II CAN Bus:** Connected to the CAN-H (Pin 6) and CAN-L (Pin 14) of the Dodge Dart diagnostic port via MCP2515 CAN SPI interface or high-speed FTDI STN1110 / ELM327 USB bus at 500,000 baud.
- **GPS UART:** Quectel L80 / u-blox NEO-M8N connected to `/dev/ttyAMA0` (GPIO 14 TX, GPIO 15 RX) at 9600 baud.
- **Audio Output:** Low-noise 96kHz PCM DAC connected via I2S or USB DAC to the vehicle's aux/amplifier input.

---

## 2. Operating Philosophy: Zero-Mock & Native Hardware Integration

CarPi5 enforces a strict **Zero-Fake-Code** mandate:
- **Real Bus State:** When hardware (OBD-II, GPS, CAN bus, Dashcam) is offline, the system truthfully indicates disconnected status with real retry timers and diagnostic notifications.
- **Automotive Ergonomics:** All touch targets maintain a minimum size of $44\times 44\text{px}$ to ensure safe, effortless fingertip actuation while driving.
- **Instant Kiosk Boot:** Chromium boots into `--kiosk --incognito --disable-pinch` directly into the in-dash cockpit, bypassing desktop window managers.

---

## 3. OBD-II & CAN Bus Diagnostic Subsystem

The powertrain telemetry daemon directly interfaces with the Dodge Dart's **Magneti Marelli 8GM ECU** powering the 1.4L 16V Turbo MultiAir engine:

### Critical Monitored Parameters:
1. **Intake Manifold Pressure & Boost:** Monitored via PID `0x0B` (MAP) and converted to gauge pressure relative to barometric pressure (`0x33`). When below ambient, displayed in inches of mercury ($-30$ to $0\text{ inHg}$); on boost, displayed in positive PSI ($0$ to $+26\text{ PSI}$).
2. **MultiAir Solenoid & Oil Temperature:** MultiAir variable valve actuation relies on high-pressure engine oil. Solenoid health and oil temperature are continuously tracked; MultiAir actuation warnings fire if oil temperature exceeds $110^\circ\text{C}$ under high load.
3. **Gear Position Inference & Coasting Detection:**
   - **Forward Gears 1–6:** Calculated using live engine RPM, vehicle speed (VSS), final drive ratio ($4.118$), and gear ratios:
     - 1st Gear: $3.818$
     - 2nd Gear: $2.158$
     - 3rd Gear: $1.475$
     - 4th Gear: $1.067$
     - 5th Gear: $0.875$
     - 6th Gear: $0.744$
   - **Shifting vs. Coasting Logic:** When the clutch is depressed or in neutral while moving ($VSS > 3\text{ MPH}$):
     - Duration $< 2.5\text{ seconds}$: Displays shifting badge (`⚡ SHIFTING`).
     - Duration $\ge 2.5\text{ seconds}$: Switches automatically to coasting badge (`≈ COASTING`).
4. **DTC Diagnostic Codes:** Supports Reading (Mode 03), Clearing (Mode 04), and Freeze Frame Data (Mode 02) with human-readable diagnostic explanations for Dodge/Chrysler P-codes (e.g. `P0299` Turbo Underboost, `P1067` MultiAir Actuator Solenoid).

---

## 4. R.U.M. AI Companion & 3D Interactive Rig

**R.U.M.** (Realtime Underhood MultiAir) is the animated, in-dash voice copilot:
- **Character Lore:** The playful, purple-haired younger triplet sister to Rem and Ram from *Re:Zero*. She lives inside the Dodge Dart's ECU and dashboard, acting as your spirited mechanic, co-driver, and companion.
- **Forward Driver Eye Contact Rule:** R.U.M. always maintains direct forward eye contact ($Camera\ X = 0.0$) toward the driver. When looking around the room, she returns her gaze to the driver within 9 seconds.
- **Dynamic Camera Director:**
  - **FULL BODY (Default):** Smooth 3rd-person game character follow tracking her exact $X/Z$ coordinates head-to-toe.
  - **BUST / PORTRAIT:** Locked bust framing (shoulders to hair) continuously following her wherever she walks.
  - **AUTO ZOOM:** Wanders in full-body view, then automatically zooms straight into a head-and-shoulders close-up whenever she speaks to show lip-sync and facial expressions.
  - **ROOM:** Wide-angle diorama showing the entire 3D customizer room, door, and floor.
- **Shotgun Floating HUD Mode:**
  - Tapping shotgun pops R.U.M. into a draggable, non-intrusive floating HUD widget that rides shotgun across all cockpit screens (File Explorer, Gauges, Media, Diagnostics).
  - Features quick-action buttons: Zoom toggle (`🔍`), Minimize bubble (`— MIN`), Dock back to room (`↓ DOCK`), and Dismiss (`✕`).

---

## 5. In-Dash Telemetry & Gauge Cluster Engine

The live instrument cluster supports 8 high-contrast automotive themes designed for glare resistance and fast peripheral vision reading:
- **Available Themes:** Turbo Sport, Cyber Midnight, Minimalist Track, Analog Classic, JDM Neon, MultiAir Monza, Rally Apex, and Eco Blue.
- **Cluster Modes:**
  - **Standard 6-Gauge:** Tachometer, Speedometer, Boost/Vacuum, Coolant Temp, Oil Temp, Battery Voltage.
  - **Fullscreen 12-Gauge:** Adds Intake Air Temp (IAT), Throttle Position (TPS), Fuel Rail Pressure, Spark Timing Advance, Engine Load %, and Catalyst Temp.
- **Tactile Sound FX:** WebAudio synthetic click tones and rev warnings on high-RPM limits ($>6,200\text{ RPM}$).

---

## 6. Automotive Touch Audio Suite & DSP Limiter

The dedicated Studio Audio Suite (`screenAudioSuite`) features:
- **10-Band Graphic Equalizer:** Precision frequency bands ($31\text{Hz}$, $63\text{Hz}$, $125\text{Hz}$, $250\text{Hz}$, $500\text{Hz}$, $1\text{kHz}$, $2\text{kHz}$, $4\text{kHz}$, $8\text{kHz}$, $16\text{kHz}$) with $\pm 12\text{dB}$ slider travel and live numeric feedback.
- **Acoustic Presets:** Flat Studio, Bass Heavy (Sub-Bass boost for car cabins), Vocal Clarity, Rock / Live, Electronic Dance, and Custom User Curve.
- **Anti-Clip Dynamics Limiter:** Real-time WebAudio `DynamicsCompressorNode` preventing digital distortion and amplifier clipping when volume is pushed to maximum.

---

## 7. Windows 11 Native File Explorer

A desktop-class, full-window filesystem hub (`screenExplorer`):
- **Navigation Sidebar:** Quick Access (`This PC`, `Home`, `CarPi5 Workspace`, `Downloads`, `Music Library`, `Retro ROMs`) and Physical Drive Mounts (`System Root /`, `USB Flash Media`, `Pi 3 Dashcam`).
- **Drives Overview Viewport:** Displays storage capacity meters, used percentages, and free space for all connected block devices.
- **Automotive Touch Grid:** Oversized folder rows with high-contrast icon badges, file size chips, and single-touch file operations (`COPY`, `DEL`, `NEW FOLDER`).

---

## 8. GPS Navigation & Dragy Performance Timer

- **Dragy Performance Meter:**
  - Automated 0–60 MPH timer triggered via GPS velocity threshold ($VSS > 0.5\text{ MPH}$).
  - Live G-force accelerometer calculation derived from high-rate GPS velocity deltas.
  - Automatic slope and altitude correction to ensure dragy runs are valid.
- **Offline Mapping Subsystem:** High-speed vector tiles stored locally on NVMe/MicroSD providing nationwide road navigation without requiring mobile cellular connectivity.

---

## 9. Ethernet Dashcam Streaming & Loop Recording

- **Pi 3 Video Pipeline:** Captures 1080p @ 30fps H.264 video through the front camera.
- **Circular Buffer:** Stores footage in 3-minute chunked `.mp4` segments in `/home/nfgodin/CarPi5/storage/dashcam_videos/`.
- **G-Shock Incident Lock:** Sudden deceleration ($>1.2\text{G}$) automatically locks the current video chunk to prevent overwriting during driving incidents.
- **Live In-Dash Stream:** Low-latency video streamed via HTTP multipart MJPEG directly into the `screenDashcam` feed with full snapshot and playback capability.

---

## 10. In-Car Troubleshooting & Emergency Reset Protocol

### Quick Recovery Key Combos & Touch Actions:
1. **Force Cockpit Home:** Tap the prominent `🏠 HOME` button located in the top-left cockpit status bar from any screen.
2. **Reload Kiosk Browser (Clean Cache):** Press `F5` on any connected wireless keyboard or send CDP reload command:
   ```bash
   curl -s http://127.0.0.1:9222/json | grep -o '"webSocketDebuggerUrl": "[^"]*"'
   ```
3. **Restart CarPi5 Backend Daemon:**
   ```bash
   sudo systemctl restart carpi5.service
   ```
4. **CAN Bus Interface Reset:**
   ```bash
   sudo ip link set can0 down && sudo ip link set can0 up type can bitrate 500000
   ```
5. **Emergency Engine Health Check:** Navigate to `VEHICLE → DIAGNOSTICS` to scan for pending or active DTC trouble codes.
