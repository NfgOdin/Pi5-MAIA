"""
google_auth.py - Google OAuth 2.0 Device Code Flow (RFC 8628) for CarPi5
Enables smart TV / in-dash vehicle authentication for Google Gemini AI.

Driver workflow:
1. Tap "Sign in with Google" on CarPi5 dashboard.
2. In-dash screen displays QR code with direct link (https://www.google.com/device?user_code=XXXX-XXXX).
3. Driver scans QR code with smartphone, taps "Allow".
4. CarPi5 securely receives OAuth credentials and Gemini AI is instantly activated!
"""

import os
import json
import time
import threading
import urllib.request
import urllib.parse
import urllib.error
from typing import Dict, Any, Optional

DEFAULT_TOKEN_FILE = os.path.join(os.path.dirname(__file__), "google_oauth_tokens.json")

# Standard Google OAuth Endpoints
DEVICE_CODE_URL = "https://oauth2.googleapis.com/device/code"
TOKEN_URL = "https://oauth2.googleapis.com/token"
USERINFO_URL = "https://www.googleapis.com/oauth2/v2/userinfo"

# Scopes needed for Gemini AI & Profile identification
OAUTH_SCOPES = "email profile https://www.googleapis.com/auth/generative-language"


class GoogleAuthManager:
    def __init__(self, token_file: Optional[str] = None):
        self.token_file = token_file or DEFAULT_TOKEN_FILE
        self.lock = threading.RLock()
        self.status = "idle"  # "idle", "pending", "authenticated", "error"
        self.current_user_code: Optional[str] = None
        self.current_verification_url: Optional[str] = None
        self.current_direct_url: Optional[str] = None
        self.poll_thread: Optional[threading.Thread] = None
        self.poll_cancel_event = threading.Event()
        self.last_error: Optional[str] = None

        # Stored credentials
        self.client_id = ""
        self.client_secret = ""
        self.access_token = ""
        self.refresh_token = ""
        self.expires_at = 0.0
        self.user_email = ""
        self.user_name = ""
        self.user_picture = ""

        self._load_tokens()

    def _load_tokens(self):
        with self.lock:
            if os.path.exists(self.token_file):
                try:
                    with open(self.token_file, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    self.client_id = data.get("client_id", "")
                    self.client_secret = data.get("client_secret", "")
                    self.access_token = data.get("access_token", "")
                    self.refresh_token = data.get("refresh_token", "")
                    self.expires_at = float(data.get("expires_at", 0.0))
                    self.user_email = data.get("email", "")
                    self.user_name = data.get("name", "")
                    self.user_picture = data.get("picture", "")

                    if self.refresh_token:
                        self.status = "authenticated"
                except Exception as e:
                    print(f"[GOOGLE_AUTH] Error loading tokens: {e}")

    def _save_tokens(self):
        with self.lock:
            data = {
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "access_token": self.access_token,
                "refresh_token": self.refresh_token,
                "expires_at": self.expires_at,
                "email": self.user_email,
                "name": self.user_name,
                "picture": self.user_picture
            }
            try:
                with open(self.token_file, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2)
            except Exception as e:
                print(f"[GOOGLE_AUTH] Error saving tokens: {e}")

    def save_client_credentials(self, client_id: str, client_secret: str = "") -> Dict[str, Any]:
        """Saves Google Cloud OAuth Client ID and optional secret."""
        with self.lock:
            self.client_id = client_id.strip()
            self.client_secret = client_secret.strip()
            self._save_tokens()
        return {"status": "ok", "client_id": self.client_id}

    def start_device_flow(self, client_id: Optional[str] = None, client_secret: Optional[str] = None) -> Dict[str, Any]:
        """Initiates the OAuth 2.0 Device Authorization Grant."""
        # Cancel any existing polling outside lock to avoid deadlock with poll thread
        self.poll_cancel_event.set()
        old_thread = self.poll_thread
        if old_thread and old_thread.is_alive() and old_thread is not threading.current_thread():
            old_thread.join(timeout=1.0)

        with self.lock:
            cid = client_id or self.client_id
            csec = client_secret or self.client_secret

            if not cid:
                return {
                    "status": "error",
                    "message": "Missing Google OAuth Client ID. Please configure your Client ID in Settings first."
                }

            self.client_id = cid
            self.client_secret = csec
            self.poll_cancel_event.clear()

            # Request device code from Google
            params = {
                "client_id": self.client_id,
                "scope": OAUTH_SCOPES
            }
            payload = urllib.parse.urlencode(params).encode("utf-8")
            req = urllib.request.Request(
                DEVICE_CODE_URL,
                data=payload,
                headers={"Content-Type": "application/x-www-form-urlencoded"}
            )

            try:
                with urllib.request.urlopen(req, timeout=8.0) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
            except Exception as e:
                err_msg = f"Failed to initiate Google Device Flow: {e}"
                print(f"[GOOGLE_AUTH] {err_msg}")
                self.status = "error"
                self.last_error = err_msg
                return {"status": "error", "message": err_msg}

            device_code = data.get("device_code")
            user_code = data.get("user_code")
            verification_url = data.get("verification_url", "https://www.google.com/device")
            expires_in = int(data.get("expires_in", 1800))
            interval = max(3, int(data.get("interval", 5)))

            # Direct pre-filled verification link
            direct_url = f"{verification_url}?user_code={user_code}" if user_code else verification_url

            self.status = "pending"
            self.current_user_code = user_code
            self.current_verification_url = verification_url
            self.current_direct_url = direct_url
            self.last_error = None

            # Spawn background polling thread
            self.poll_thread = threading.Thread(
                target=self._poll_token_loop,
                args=(device_code, interval, expires_in),
                daemon=True
            )
            self.poll_thread.start()

            return {
                "status": "pending",
                "user_code": user_code,
                "verification_url": verification_url,
                "direct_url": direct_url,
                "expires_in": expires_in,
                "interval": interval
            }

    def _poll_token_loop(self, device_code: str, interval: int, expires_in: int):
        """Polls Google token endpoint until user approves or code expires."""
        start_time = time.time()
        poll_interval = interval

        while not self.poll_cancel_event.is_set():
            if time.time() - start_time > expires_in:
                with self.lock:
                    self.status = "error"
                    self.last_error = "Device code expired. Please try again."
                break

            self.poll_cancel_event.wait(poll_interval)
            if self.poll_cancel_event.is_set():
                break

            params = {
                "client_id": self.client_id,
                "device_code": device_code,
                "grant_type": "urn:ietf:params:oauth:grant-type:device_code"
            }
            if self.client_secret:
                params["client_secret"] = self.client_secret

            payload = urllib.parse.urlencode(params).encode("utf-8")
            req = urllib.request.Request(
                TOKEN_URL,
                data=payload,
                headers={"Content-Type": "application/x-www-form-urlencoded"}
            )

            try:
                with urllib.request.urlopen(req, timeout=8.0) as resp:
                    token_data = json.loads(resp.read().decode("utf-8"))
                    # Success! User approved on their phone!
                    self._on_authorization_success(token_data)
                    break
            except urllib.error.HTTPError as e:
                try:
                    err_json = json.loads(e.read().decode("utf-8"))
                    err_code = err_json.get("error", "")
                    if err_code == "authorization_pending":
                        continue
                    elif err_code == "slow_down":
                        poll_interval += 2
                        continue
                    elif err_code == "access_denied":
                        with self.lock:
                            self.status = "error"
                            self.last_error = "Access was denied by the user."
                        break
                    elif err_code == "expired_token":
                        with self.lock:
                            self.status = "error"
                            self.last_error = "Code expired."
                        break
                    else:
                        with self.lock:
                            self.status = "error"
                            self.last_error = f"OAuth error: {err_code}"
                        break
                except Exception:
                    continue
            except Exception as ex:
                print(f"[GOOGLE_AUTH] Polling note: {ex}")
                continue

    def _on_authorization_success(self, token_data: Dict[str, Any]):
        """Called when user successfully authorizes on phone."""
        with self.lock:
            self.access_token = token_data.get("access_token", "")
            self.refresh_token = token_data.get("refresh_token", self.refresh_token)
            expires_in = int(token_data.get("expires_in", 3600))
            self.expires_at = time.time() + expires_in - 60
            self.status = "authenticated"
            self.last_error = None

            # Fetch user profile info
            try:
                user_info = self._fetch_userinfo(self.access_token)
                self.user_email = user_info.get("email", "")
                self.user_name = user_info.get("name", user_info.get("given_name", "Driver"))
                self.user_picture = user_info.get("picture", "")
            except Exception as e:
                print(f"[GOOGLE_AUTH] Error fetching userinfo: {e}")

            self._save_tokens()
            print(f"[GOOGLE_AUTH] Successfully authenticated as {self.user_name} ({self.user_email})")

    def _fetch_userinfo(self, access_token: str) -> Dict[str, Any]:
        req = urllib.request.Request(
            USERINFO_URL,
            headers={"Authorization": f"Bearer {access_token}"}
        )
        with urllib.request.urlopen(req, timeout=5.0) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def get_valid_access_token(self) -> Optional[str]:
        """Returns a valid access token, auto-refreshing if expired."""
        with self.lock:
            if not self.refresh_token:
                return None

            # If token is still fresh, return it
            if self.access_token and time.time() < self.expires_at:
                return self.access_token

            # Token expired or missing, refresh it!
            params = {
                "client_id": self.client_id,
                "refresh_token": self.refresh_token,
                "grant_type": "refresh_token"
            }
            if self.client_secret:
                params["client_secret"] = self.client_secret

            payload = urllib.parse.urlencode(params).encode("utf-8")
            req = urllib.request.Request(
                TOKEN_URL,
                data=payload,
                headers={"Content-Type": "application/x-www-form-urlencoded"}
            )

            try:
                with urllib.request.urlopen(req, timeout=8.0) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                    self.access_token = data.get("access_token", "")
                    expires_in = int(data.get("expires_in", 3600))
                    self.expires_at = time.time() + expires_in - 60
                    self._save_tokens()
                    return self.access_token
            except Exception as e:
                print(f"[GOOGLE_AUTH] Error refreshing token: {e}")
                return None

    def logout(self):
        """Clears stored tokens and resets authentication state."""
        with self.lock:
            self.poll_cancel_event.set()
            self.access_token = ""
            self.refresh_token = ""
            self.expires_at = 0.0
            self.user_email = ""
            self.user_name = ""
            self.user_picture = ""
            self.status = "idle"
            self.current_user_code = None
            self.current_verification_url = None
            self.current_direct_url = None
            self._save_tokens()
            print("[GOOGLE_AUTH] Logged out of Google account.")

    def get_status(self) -> Dict[str, Any]:
        """Returns the full public authentication status dictionary."""
        with self.lock:
            is_authed = bool(self.refresh_token and (self.access_token or self.status == "authenticated"))
            return {
                "authenticated": is_authed,
                "status": "authenticated" if is_authed else self.status,
                "user_code": self.current_user_code,
                "verification_url": self.current_verification_url,
                "direct_url": self.current_direct_url,
                "email": self.user_email,
                "name": self.user_name,
                "picture": self.user_picture,
                "has_client_id": bool(self.client_id),
                "client_id": self.client_id,
                "last_error": self.last_error
            }
