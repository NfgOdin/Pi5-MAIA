#!/bin/bash
# setup_pi3_hotspot.sh - Standalone In-Car Wi-Fi Access Point & Dashcam Router for Raspberry Pi 3
# Configures Pi 3 onboard wlan0 as "CarPi-Cabin" AP on 192.168.4.1 while preserving eth0 direct link to Pi 5 (10.0.0.2).

set -e

HOTSPOT_SSID="CarPi-Cabin"
HOTSPOT_PASS="carpi2026"
HOTSPOT_IP="192.168.4.1/24"

echo "=== CarPi3 In-Cabin Wi-Fi Hotspot Provisioning ==="

# 1. Unblock Wi-Fi via rfkill if soft-blocked
rfkill unblock wifi || true

# 2. Check if NetworkManager is active
if systemctl is-active --quiet NetworkManager; then
    echo "[+] Using NetworkManager AP Mode (Bookworm / Modern OS)..."
    
    # Remove existing hotspot connection if present to ensure clean configuration
    nmcli con delete "CarPi-Hotspot" 2>/dev/null || true
    
    # Create high-speed 2.4GHz AP connection
    nmcli con add type wifi ifname wlan0 mode ap con-name "CarPi-Hotspot" ssid "$HOTSPOT_SSID" autoconnect yes
    nmcli con modify "CarPi-Hotspot" 802-11-wireless.band bg
    nmcli con modify "CarPi-Hotspot" 802-11-wireless.channel 6
    nmcli con modify "CarPi-Hotspot" 802-11-wireless-security.key-mgmt wpa-psk
    nmcli con modify "CarPi-Hotspot" 802-11-wireless-security.psk "$HOTSPOT_PASS"
    nmcli con modify "CarPi-Hotspot" ipv4.method shared ipv4.addresses "$HOTSPOT_IP"
    
    # Enable IP forwarding for USB mobile phone tethering
    sudo sysctl -w net.ipv4.ip_forward=1
    echo "net.ipv4.ip_forward=1" | sudo tee /etc/sysctl.d/99-carpi-routing.conf > /dev/null
    
    # Bring up the hotspot
    nmcli con up "CarPi-Hotspot"
    echo "[SUCCESS] Hotspot '$HOTSPOT_SSID' is LIVE on $HOTSPOT_IP!"
else
    echo "[+] Installing hostapd & dnsmasq fallback (Legacy OS)..."
    sudo apt-get update -y
    sudo apt-get install -y hostapd dnsmasq iptables
    
    # Enable IP forwarding for routing / tethering
    sudo sysctl -w net.ipv4.ip_forward=1
    echo "net.ipv4.ip_forward=1" | sudo tee /etc/sysctl.d/99-carpi-routing.conf > /dev/null
    
    # Configure static IP for wlan0 in dhcpcd.conf
    if ! grep -q "interface wlan0" /etc/dhcpcd.conf 2>/dev/null; then
        echo -e "\ninterface wlan0\n    static ip_address=192.168.4.1/24\n    nohook wpa_supplicant" | sudo tee -a /etc/dhcpcd.conf
    fi
    
    # Configure dnsmasq
    sudo mv /etc/dnsmasq.conf /etc/dnsmasq.conf.orig 2>/dev/null || true
    cat <<EOF | sudo tee /etc/dnsmasq.conf
interface=wlan0
dhcp-range=192.168.4.10,192.168.4.100,255.255.255.0,24h
domain=carpi.local
address=/carpi.local/192.168.4.1
EOF

    # Configure hostapd
    cat <<EOF | sudo tee /etc/hostapd/hostapd.conf
interface=wlan0
driver=nl80211
ssid=$HOTSPOT_SSID
hw_mode=g
channel=6
wmm_enabled=0
macaddr_acl=0
auth_algs=1
ignore_broadcast_ssid=0
wpa=2
wpa_passphrase=$HOTSPOT_PASS
wpa_key_mgmt=WPA-PSK
wpa_pairwise=TKIP
rsn_pairwise=CCMP
EOF

    echo 'DAEMON_CONF="/etc/hostapd/hostapd.conf"' | sudo tee /etc/default/hostapd > /dev/null
    sudo systemctl unmask hostapd
    sudo systemctl enable hostapd dnsmasq
    sudo systemctl restart hostapd dnsmasq
    echo "[SUCCESS] Hostapd Hotspot '$HOTSPOT_SSID' is LIVE on 192.168.4.1!"
fi

echo "=== Setup Complete! Connect phone to '$HOTSPOT_SSID' (Password: $HOTSPOT_PASS) ==="
