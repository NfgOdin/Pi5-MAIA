#!/usr/bin/env bash
# Configure Raspberry Pi 5 Rechargeable RTC Battery (Waveshare RTC-Battery-A / LIR2025)
set -euo pipefail

CONFIG_FILE="/boot/firmware/config.txt"
[ -f "$CONFIG_FILE" ] || CONFIG_FILE="/boot/config.txt"

if [ ! -f "$CONFIG_FILE" ]; then
  echo "[RTC] Could not locate /boot/firmware/config.txt or /boot/config.txt"
  exit 1
fi

if grep -qE '^\s*dtparam=rtc_bbat_vchg=' "$CONFIG_FILE"; then
  sudo sed -i 's/^\s*dtparam=rtc_bbat_vchg=.*/dtparam=rtc_bbat_vchg=3000000/' "$CONFIG_FILE"
  echo "[RTC] Updated existing rtc_bbat_vchg=3000000 in $CONFIG_FILE"
else
  echo "dtparam=rtc_bbat_vchg=3000000" | sudo tee -a "$CONFIG_FILE" >/dev/null
  echo "[RTC] Added dtparam=rtc_bbat_vchg=3000000 to $CONFIG_FILE"
fi

if [ -e /dev/rtc0 ]; then
  echo "[RTC] Syncing current system time to hardware clock /dev/rtc0..."
  sudo hwclock -w --verbose || true
fi

RTC_SYSFS="/sys/class/rtc/rtc0"
[ -d "$RTC_SYSFS" ] || RTC_SYSFS="/sys/devices/platform/soc/soc:rpi_rtc/rtc/rtc0"
if [ -d "$RTC_SYSFS" ]; then
  echo "[RTC] Current battery_voltage: $(cat "$RTC_SYSFS/battery_voltage" 2>/dev/null || echo 'N/A') uV"
  echo "[RTC] Current charging_voltage: $(cat "$RTC_SYSFS/charging_voltage" 2>/dev/null || echo 'N/A') uV"
fi

echo "[RTC] Done! Reboot Pi 5 once (sudo reboot) for trickle-charge dtparam to activate."
