#!/bin/bash
# CarPi5 Cockpit Autostart Script
export PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:$PATH"

# 1. Kill stale processes cleanly
pkill -f "python3 backend/daemon.py" || true
pkill -9 -f chromium || true
sleep 1

# 2. Flash Wear Protection & RAM Buffer Setup (tmpfs /dev/shm)
mkdir -p /dev/shm/carpi5_audio /dev/shm/chromium_cache
chmod 777 /dev/shm/carpi5_audio /dev/shm/chromium_cache 2>/dev/null || true
touch /dev/shm/daemon.log /dev/shm/kiosk.log
chmod 666 /dev/shm/daemon.log /dev/shm/kiosk.log 2>/dev/null || true
ln -sf /dev/shm/daemon.log /home/nfgodin/CarPi5/daemon.log 2>/dev/null || true
ln -sf /dev/shm/kiosk.log /home/nfgodin/CarPi5/kiosk.log 2>/dev/null || true

# 2b. Provision PipeWire DSP Acoustic Echo Cancellation (AEC)
mkdir -p /home/nfgodin/.config/pipewire/pipewire.conf.d/
cp -u /home/nfgodin/CarPi5/config/pipewire/carpi-dsp.conf /home/nfgodin/.config/pipewire/pipewire.conf.d/carpi-dsp.conf 2>/dev/null || true

# 3. ZRAM Compressed Swap Initialization (2GB lz4)
modprobe zram 2>/dev/null || true
if [ -e /sys/block/zram0 ] && ! swapon --show | grep -q "/dev/zram0"; then
    echo 1 > /sys/block/zram0/reset 2>/dev/null || true
    echo lz4 > /sys/block/zram0/comp_algorithm 2>/dev/null || true
    echo 2G > /sys/block/zram0/disksize 2>/dev/null || true
    mkswap /dev/zram0 >/dev/null 2>&1 || true
    swapon -p 100 /dev/zram0 2>/dev/null || true
fi

# 4. Clear stale Chromium singleton locks and crash status
rm -f /home/nfgodin/.config/chromium/Singleton*
if [ -f /home/nfgodin/.config/chromium/Default/Preferences ]; then
    sed -i 's/"exit_type":"Crashed"/"exit_type":"Normal"/' /home/nfgodin/.config/chromium/Default/Preferences 2>/dev/null || true
    sed -i 's/"exited_cleanly":false/"exited_cleanly":true/' /home/nfgodin/.config/chromium/Default/Preferences 2>/dev/null || true
fi

# 5. Start Python backend daemon (Logs to /dev/shm in RAM)
cd /home/nfgodin/CarPi5
nohup python3 backend/daemon.py < /dev/null > /dev/shm/daemon.log 2>&1 &

# 6. Set Wayland Environment
export WAYLAND_DISPLAY=wayland-0
export XDG_RUNTIME_DIR=/run/user/1000

# 7. Launch Chromium Kiosk natively on Wayland pointing to local cockpit
# Pinned to Cores 0 & 1 via taskset to guarantee 60fps UI while LLM runs on Cores 2 & 3
# Disk cache isolated to RAM (/dev/shm/chromium_cache) to prevent NVMe/SD wear
nohup taskset -c 0,1 /usr/lib/chromium/chromium \
  --ozone-platform=wayland \
  --kiosk \
  --remote-debugging-port=9222 \
  --remote-allow-origins=* \
  --password-store=basic \
  --noerrdialogs \
  --disable-infobars \
  --disable-extensions \
  --allow-file-access-from-files \
  --user-data-dir=/home/nfgodin/.config/chromium \
  --disable-web-security \
  --check-for-update-interval=31536000 \
  --disable-session-crashed-bubble \
  --disable-translate \
  --touch-events=enabled \
  --enable-pinch \
  --autoplay-policy=no-user-gesture-required \
  --disk-cache-dir=/dev/shm/chromium_cache \
  --disk-cache-size=33554432 \
  file:///home/nfgodin/CarPi5/ui/web_preview/index.html < /dev/null > /dev/shm/kiosk.log 2>&1 &

echo "CarPi5 Cockpit Started Successfully with ZRAM & Flash Protection!"
