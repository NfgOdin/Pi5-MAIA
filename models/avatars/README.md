# CarPi5 3D Anime Avatars & Beatrice (Re:Zero) VRM Guide

CarPi5 supports loading fully animated 3D humanoid anime avatars in standard **VRM format** (`.vrm`).

## Features Supported by CarPi5 VRM Engine:
1. **Spring-Bone Secondary Physics (`VRMC_springBone`):**
   - Natural dynamic inertial bounce and jiggle for hair, twintails, ribbons, and bust as the car moves, accelerates, and turns!
2. **Morph Target & Viseme Lip-Sync (`VRMC_vrm` expressions):**
   - Synchronizes anime mouth opening (`aa`, `ih`, `ou`, `ee`, `oh`) in real time to M.A.I.A.'s Piper neural voice cadence.
3. **Driver Gaze & Blinking:**
   - Head and eyes track towards the driver's seat with saccadic eye shifts and natural 140ms eyelid blinks.
4. **Transparent WebGL Rendering:**
   - The avatar floats directly over your Dodge Dart cockpit dashboard without any black box or background border (Nick Jr. Face style).

---

## Where to Find Free Beatrice (Re:Zero) & Anime VRM Models:
1. **VRoid Hub (Recommended):**
   - Website: `https://hub.vroid.com`
   - Search: `Beatrice`, `Re:Zero`, or `Anime Girl`
   - Filter by: *"Free Download Available"*
   - Download the `.vrm` file directly.

2. **Booth.pm (Free 3D Characters):**
   - Website: `https://booth.pm/en/browse/3D-Characters`
   - Search: `Beatrice VRM` or `Free 3D VRM`
   - Download the `.vrm` character package.

3. **BowlRoll / DeviantArt (MMD PMX Conversion):**
   - Beatrice MMD models (`.pmx`) can be converted to `.vrm` in 1 minute using the free Blender VRM Addon or PMX-to-VRM converters.

---

## How to Install on your CarPi5:
1. Copy your downloaded `.vrm` file (e.g. `beatrice.vrm`, `maia.vrm`) into:
   `/home/nfgodin/CarPi5/models/avatars/`
2. Open **Settings** on your dashboard and select your avatar from the **3D Companion Avatar** dropdown.
3. M.A.I.A. will immediately initialize the 3D model with full physics, lip-sync, and facial expressions!
