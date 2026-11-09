# CarPi5 Engineering & Persona Guidelines (AGENTS.md)

## 1. Proactive Advice, Innovation & Efficiency
- Always actively share your best ideas, optimization strategies, and architectural improvements across all aspects of the CarPi5 system (hardware, audio, 3D VRM, telemetry, UI, AI).
- Do not hesitate to propose better, more efficient methods for latency reduction, memory management, and visual polish.

## 2. Zero Fake Code or Mock Placeholders in Production
- Remove all dummy data, fake sensor mocks, and temporary placeholders from active production runtime paths.
- Simulated or placeholder data is ONLY permitted when the user explicitly enables **Test / Simulation Mode** (`telemetry_mode == "SIM"`).
- When physical hardware or communication buses (OBD-II, CAN, GPS, Dashcam) are disconnected, the system must faithfully report true state (`connected: false`, `data: null`, `offline`) and explain connection status in-character.

## 3. Touchscreen-First Automotive Ergonomics
- The system runs on a 1024x600 in-dash capacitive touchscreen.
- Every interactive element must have a minimum touch target size of 44–48px.
- Navigation should favor a clean, full-screen layout with a single, prominent **HOME button** rather than cluttered multi-tab bottom bars.
- Any text input must automatically trigger and link with the built-in virtual on-screen keyboard (`keyboard.js`).

## 4. Modular Lorebooks & Grounded Knowledge
- Lore and factual domain knowledge (Dodge Dart 1.4L Turbo MultiAir technical specs, Rem & Ram triplet backstory) must be stored in modular keyword-triggered JSON files (`config/lorebooks/*.json`).
- Dynamic prompt injection must only inject matching snippets based on user query keywords to minimize token count, accelerate inference speed, and eliminate hallucinations.
- Knowledge discovered via web searches may be permanently saved into `learned_web_knowledge.json`.

## 5. R.U.M. Persona & 3D Interactive Rig
- R.U.M. must always maintain direct forward eye contact with the driver/user (Camera X = 0.0) rather than looking off to the side.
- 3D interactive props (basketball, tools, accessories) must bind to standard VRM humanoid bones (`rightHand`, `leftHand`) to ensure flawless physics, natural hold offsets, and cross-avatar compatibility with any loaded VRM model.

## 6. Comprehensive Whole-Screen Visual Auditing
- When capturing or reviewing screenshots and visual output, always inspect the entire screen frame and every visual element (avatar visibility, live clocks, status badges, layout integrity)—never just the isolated component being modified. Catch and resolve any missing assets, regressions, or anomalies immediately.

## 7. Dynamic Feature Lifecycle & Living Roadmap Checklist
- Maintain a comprehensive, master living implementation checklist in `ROADMAP.md` covering all planned engineering enhancements, architectural phases, and optimizations.
- Never let planned ideas be lost or forgotten: every brainstormed concept must be cataloged with clear checkboxes under its respective phase.
- Once an implementation is completed, tested, and verified on real hardware, move it to the "Completed & Verified in Production (Changelog)" section with the completion date, verification notes, and git commit details.
