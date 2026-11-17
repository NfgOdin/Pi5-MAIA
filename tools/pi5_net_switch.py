#!/usr/bin/env python3
"""Interactive switcher between Pi 3-only Ethernet routing and Home Wi-Fi on CarPi5."""

import getpass
import re
import select
import socket
import socketserver
import sys
import threading
import webbrowser
from pathlib import Path

try:
    import paramiko
except ImportError:
    print("ERROR: Python package 'paramiko' is not installed.")
    print("Install it once with: pip install paramiko")
    sys.exit(1)


REPO_ROOT = Path(__file__).resolve().parent.parent
CREDS_FILE = REPO_ROOT / "scratch" / "device_credentials.md"

PI3_HOSTS = ["CarPi3.local", "192.168.0.161", "10.42.0.1"]
PI5_ETH_IP = "10.0.0.1"
PI5_DIRECT_HOSTS = ["CarPi.local", "192.168.0.131"]


def load_credentials():
    """Load SSH credentials from local gitignored scratch/device_credentials.md."""
    creds = {
        "pi5_user": "nfgodin",
        "pi5_pass": None,
        "pi3_user": "nfgodin",
        "pi3_pass": None,
    }
    if CREDS_FILE.exists():
        text = CREDS_FILE.read_text(encoding="utf-8", errors="replace")
        section = None
        for line in text.splitlines():
            if line.startswith("## Pi 5"):
                section = "pi5"
            elif line.startswith("## Pi 3"):
                section = "pi3"
            elif section:
                m_user = re.search(r"\*\*SSH Username:\*\*\s*`([^`]+)`", line)
                m_pass = re.search(r"\*\*SSH Password:\*\*\s*`([^`]+)`", line)
                if m_user:
                    creds[f"{section}_user"] = m_user.group(1)
                if m_pass:
                    creds[f"{section}_pass"] = m_pass.group(1)

    if not creds["pi3_pass"]:
        creds["pi3_pass"] = getpass.getpass("Pi 3 SSH password: ")
    if not creds["pi5_pass"]:
        creds["pi5_pass"] = getpass.getpass("Pi 5 SSH password: ")
    return creds


def tcp_open(host, port=22, timeout=2.0):
    """Return True if host:port accepts a TCP connection quickly."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def connect_pi5(creds):
    """Connect to Pi 5, preferring SSH jump through Pi 3 so it works in Pi3-only mode too."""
    for p3_host in PI3_HOSTS:
        if not tcp_open(p3_host, 22, timeout=2.0):
            continue
        p3 = paramiko.SSHClient()
        p3.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        try:
            print(f"[*] Jumping through Pi 3 ({p3_host}) -> Pi 5 ({PI5_ETH_IP})...")
            p3.connect(p3_host, username=creds["pi3_user"], password=creds["pi3_pass"], timeout=6)
            chan = p3.get_transport().open_channel(
                "direct-tcpip", (PI5_ETH_IP, 22), ("127.0.0.1", 0)
            )
            p5 = paramiko.SSHClient()
            p5.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            p5.connect(
                PI5_ETH_IP,
                username=creds["pi5_user"],
                password=creds["pi5_pass"],
                sock=chan,
                timeout=6,
            )
            print(f"[OK] Connected to Pi 5 via Pi 3 jump ({p3_host} -> {PI5_ETH_IP})")
            return p5, p3
        except Exception as exc:
            p3.close()
            print(f"[!] Jump via {p3_host} failed: {exc}")

    for p5_host in PI5_DIRECT_HOSTS:
        if not tcp_open(p5_host, 22, timeout=2.0):
            continue
        p5 = paramiko.SSHClient()
        p5.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        try:
            print(f"[*] Connecting directly to Pi 5 ({p5_host})...")
            p5.connect(p5_host, username=creds["pi5_user"], password=creds["pi5_pass"], timeout=6)
            print(f"[OK] Connected directly to Pi 5 ({p5_host})")
            return p5, None
        except Exception as exc:
            p5.close()
            print(f"[!] Direct connection to {p5_host} failed: {exc}")

    raise RuntimeError(
        "Could not reach Pi 5 via Pi 3 (CarPi3.local / 192.168.0.161 / 10.42.0.1) "
        "or directly (CarPi.local / 192.168.0.131)."
    )


def run_remote(p5, creds, shell_cmd, timeout=25):
    """Run a shell command on Pi 5 with sudo stdin password support."""
    pw = creds["pi5_pass"].replace("'", "'\"'\"'")
    wrapped = f"SUDO_PASS='{pw}'\n{shell_cmd}"
    _, out, err = p5.exec_command(wrapped, timeout=timeout)
    stdout_text = out.read().decode(errors="replace").strip()
    stderr_lines = [
        l for l in err.read().decode(errors="replace").splitlines()
        if "[sudo] password" not in l
    ]
    return stdout_text, "\n".join(stderr_lines).strip()


def show_status(p5, creds):
    """Display active interfaces, routes, DNS, and internet connectivity on Pi 5."""
    cmd = r"""
echo "=== INTERFACES ==="
ip -br addr
echo "=== ACTIVE CONNECTIONS ==="
nmcli -f NAME,TYPE,DEVICE,AUTOCONNECT,STATE con show
echo "=== ROUTES ==="
ip route
echo "=== INTERNET CHECK ==="
ping -c 1 -W 3 1.1.1.1 >/dev/null 2>&1 && echo "Ping 1.1.1.1: OK" || echo "Ping 1.1.1.1: FAILED"
curl -sI --max-time 5 https://www.google.com | head -n 1 || echo "HTTPS Check: FAILED"
"""
    out, err = run_remote(p5, creds, cmd, timeout=20)
    print("\n" + out)
    if err:
        print("STDERR:", err)


def set_pi3_only(p5, creds):
    """Disable Pi 5 Wi-Fi autoconnect and route all traffic strictly through Pi 3 (10.0.0.2)."""
    cmd = r"""
echo "$SUDO_PASS" | sudo -S nmcli con modify Midgard connection.autoconnect no 2>/dev/null || true
echo "$SUDO_PASS" | sudo -S nmcli con modify Moran connection.autoconnect no 2>/dev/null || true
echo "$SUDO_PASS" | sudo -S nmcli con down Midgard 2>/dev/null || true
echo "$SUDO_PASS" | sudo -S nmcli dev disconnect wlan0 2>/dev/null || true
echo "$SUDO_PASS" | sudo -S nmcli con modify "Wired connection 1" ipv4.route-metric 500 ipv4.gateway 10.0.0.2 ipv4.dns "1.1.1.1 8.8.8.8" ipv4.dns-priority 100
echo "$SUDO_PASS" | sudo -S nmcli con up "Wired connection 1"
sleep 1
echo "=== NEW MODE: PI 3 ONLY (WI-FI OFF) ==="
ip -br addr
echo "--- ROUTES ---"
ip route
echo "--- TEST ---"
ping -c 2 -W 3 1.1.1.1 || true
"""
    print("\n[*] Switching Pi 5 to Pi 3 ONLY mode...")
    out, err = run_remote(p5, creds, cmd, timeout=25)
    print(out)
    if err:
        print("STDERR:", err)


def set_home_wifi(p5, creds):
    """Enable Midgard Home Wi-Fi on Pi 5 with Pi 3 Ethernet kept as metric-900 fallback."""
    cmd = r"""
echo "$SUDO_PASS" | sudo -S nmcli con modify "Wired connection 1" ipv4.route-metric 900 ipv4.gateway 10.0.0.2 ipv4.dns "1.1.1.1 8.8.8.8" ipv4.dns-priority 200
echo "$SUDO_PASS" | sudo -S nmcli con up "Wired connection 1"
echo "$SUDO_PASS" | sudo -S nmcli con modify Midgard connection.autoconnect yes
echo "$SUDO_PASS" | sudo -S nmcli con up Midgard
sleep 2
echo "=== NEW MODE: HOME WI-FI (Midgard + Pi 3 Fallback) ==="
ip -br addr
echo "--- ROUTES ---"
ip route
"""
    print("\n[*] Switching Pi 5 to Home Wi-Fi (Midgard) mode...")
    out, err = run_remote(p5, creds, cmd, timeout=30)
    print(out)
    if err:
        print("STDERR:", err)


def open_dashboard_tunnel(creds, local_port=8080, open_browser=True):
    """Forward localhost:8080 to Pi 5:8080 (through Pi 3 if needed) and open browser."""
    ssh_client = None
    target_host = PI5_ETH_IP
    target_port = 8080

    for p3_host in PI3_HOSTS:
        if not tcp_open(p3_host, 22, timeout=2.0):
            continue
        p3 = paramiko.SSHClient()
        p3.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        try:
            print(f"[*] Opening dashboard tunnel via Pi 3 ({p3_host} -> {PI5_ETH_IP}:8080)...")
            p3.connect(p3_host, username=creds["pi3_user"], password=creds["pi3_pass"], timeout=6)
            ssh_client = p3
            target_host = PI5_ETH_IP
            break
        except Exception as exc:
            p3.close()
            print(f"[!] Pi 3 tunnel setup via {p3_host} failed: {exc}")

    if ssh_client is None:
        for p5_host in PI5_DIRECT_HOSTS:
            if not tcp_open(p5_host, 22, timeout=2.0):
                continue
            p5 = paramiko.SSHClient()
            p5.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            try:
                print(f"[*] Opening direct dashboard tunnel to Pi 5 ({p5_host}:8080)...")
                p5.connect(p5_host, username=creds["pi5_user"], password=creds["pi5_pass"], timeout=6)
                ssh_client = p5
                target_host = "127.0.0.1"
                break
            except Exception as exc:
                p5.close()
                print(f"[!] Direct tunnel via {p5_host} failed: {exc}")

    if ssh_client is None:
        raise RuntimeError("Could not reach Pi 3 or Pi 5 over SSH to open dashboard tunnel.")

    transport = ssh_client.get_transport()

    class _ForwardHandler(socketserver.BaseRequestHandler):
        def handle(self):
            try:
                chan = transport.open_channel(
                    "direct-tcpip",
                    (target_host, target_port),
                    self.request.getpeername(),
                )
            except Exception as exc:
                print(f"[!] Tunnel channel error: {exc}")
                return
            if chan is None:
                return
            try:
                while True:
                    r, _, _ = select.select([self.request, chan], [], [], 1.0)
                    if self.request in r:
                        data = self.request.recv(16384)
                        if not data:
                            break
                        chan.sendall(data)
                    if chan in r:
                        data = chan.recv(16384)
                        if not data:
                            break
                        self.request.sendall(data)
            except OSError:
                pass
            finally:
                try:
                    chan.close()
                except Exception:
                    pass

    class _ReuseThreadingTCPServer(socketserver.ThreadingTCPServer):
        allow_reuse_address = True
        daemon_threads = True

    server = _ReuseThreadingTCPServer(("127.0.0.1", local_port), _ForwardHandler)
    url = f"http://localhost:{local_port}"
    print(f"[OK] Dashboard tunnel active at {url} -> {target_host}:{target_port}")
    print("     Press Ctrl+C to close the tunnel.")
    if open_browser:
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[*] Closing dashboard tunnel...")
    finally:
        server.shutdown()
        server.server_close()
        ssh_client.close()


def main():
    print("==============================================")
    print("      CarPi5 Network Mode Switcher")
    print("==============================================")
    print("  [1] Pi 3 ONLY       (Wi-Fi OFF, Ethernet via Pi 3)")
    print("  [2] Home Wi-Fi      (Midgard ON, Pi 3 Ethernet fallback)")
    print("  [3] Check Status    (View current interfaces & routes)")
    print("  [4] Open Dashboard  (SSH tunnel -> http://localhost:8080)")
    print("  [Q] Quit")
    print("==============================================")

    choice = sys.argv[1].strip().lower() if len(sys.argv) > 1 else input("Select option (1/2/3/4/Q): ").strip().lower()
    if choice in ("q", "quit", "exit", ""):
        return

    if choice not in ("1", "2", "3", "4"):
        print(f"Unknown option: {choice}")
        sys.exit(1)

    creds = load_credentials()
    if choice == "4":
        open_dashboard_tunnel(creds)
        return

    p5, jump = connect_pi5(creds)
    try:
        if choice == "1":
            set_pi3_only(p5, creds)
        elif choice == "2":
            set_home_wifi(p5, creds)
        elif choice == "3":
            show_status(p5, creds)
    finally:
        p5.close()
        if jump is not None:
            jump.close()


if __name__ == "__main__":
    main()
