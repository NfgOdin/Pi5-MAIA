#!/bin/bash
# CarPi5 Cockpit Autostart Script

# 1. Kill stale processes cleanly
pkill -f "python3 backend/daemon.py" || true
pkill -9 -f chromium || true
sleep 1

# 2. Clear stale Chromium singleton locks and crash status
rm -f /home/nfgodin/.config/chromium/Singleton*
if [ -f /home/nfgodin/.config/chromium/Default/Preferences ]; then
    sed -i 's/"exit_type":"Crashed"/"exit_type":"Normal"/' /home/nfgodin/.config/chromium/Default/Preferences 2>/dev/null || true
    sed -i 's/"exited_cleanly":false/"exited_cleanly":true/' /home/nfgodin/.config/chromium/Default/Preferences 2>/dev/null || true
fi

# 3. Start Python backend daemon
cd /home/nfgodin/CarPi5
nohup python3 backend/daemon.py < /dev/null > /home/nfgodin/CarPi5/daemon.log 2>&1 &

# 4. Set Wayland Environment
export WAYLAND_DISPLAY=wayland-0
export XDG_RUNTIME_DIR=/run/user/1000

# 5. Launch Chromium Kiosk natively on Wayland pointing to local cockpit
# Pinned to Cores 0 & 1 via taskset to guarantee 60fps UI while LLM runs on Cores 2 & 3
nohup taskset -c 0,1 /usr/lib/chromium/chromium \
  --ozone-platform=wayland \
  --kiosk \
  --remote-debugging-port=9222 \
  --password-store=basic \
  --noerrdialogs \
  --disable-infobars \
  --disable-extensions \
  --allow-file-access-from-files \
  --disable-web-security \
  --check-for-update-interval=31536000 \
  --disable-session-crashed-bubble \
  --disable-translate \
  --touch-events=enabled \
  --enable-pinch \
  --autoplay-policy=no-user-gesture-required \
  file:///home/nfgodin/CarPi5/ui/web_preview/index.html < /dev/null > /home/nfgodin/CarPi5/kiosk.log 2>&1 &

echo "CarPi5 Cockpit Started Successfully!"
