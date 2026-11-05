"""
avrcp_player.py - Bluetooth AVRCP Media Player Registration for CarPi5
Registers an AVRCP Target Player on BlueZ (/org/carpi5/player).
Broadcasts live track metadata (Title, Artist, Album, Genre, Duration) to Dodge Dart Uconnect 8.4 screen!
"""

import sys
import time
import threading
from typing import Dict, Any, Optional

class AvrcpPlayerManager:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self, action_callback=None):
        if self._initialized:
            return
        self._initialized = True

        self.action_callback = action_callback
        self.is_registered = False
        self.current_track: Dict[str, Any] = {
            "title": "CarPi5 In-Dash Audio",
            "artist": "Dodge Dart MultiAir",
            "album": "CarPi5",
            "genre": "Automotive",
            "duration_ms": 180000,
            "track_num": 1,
            "total_tracks": 1
        }
        self.playback_status = "playing"
        self._player_obj = None
        self._media_iface = None

        if sys.platform.startswith("linux"):
            threading.Thread(target=self._init_player, daemon=True).start()

    def _init_player(self):
        try:
            import dbus
            import dbus.service
            import dbus.mainloop.glib

            bus = dbus.SystemBus()

            class CarPiPlayer(dbus.service.Object):
                def __init__(self, bus_obj, path, parent):
                    super().__init__(bus_obj, path)
                    self.parent = parent

                @dbus.service.method('org.bluez.MediaPlayer1')
                def Play(self):
                    if self.parent.action_callback:
                        self.parent.action_callback({"type": "media", "action": "play"})

                @dbus.service.method('org.bluez.MediaPlayer1')
                def Pause(self):
                    if self.parent.action_callback:
                        self.parent.action_callback({"type": "media", "action": "pause"})

                @dbus.service.method('org.bluez.MediaPlayer1')
                def Next(self):
                    if self.parent.action_callback:
                        self.parent.action_callback({"type": "media", "action": "next"})

                @dbus.service.method('org.bluez.MediaPlayer1')
                def Previous(self):
                    if self.parent.action_callback:
                        self.parent.action_callback({"type": "media", "action": "prev"})

            player_path = "/org/carpi5/player"
            self._player_obj = CarPiPlayer(bus, player_path, self)

            media_obj = bus.get_object('org.bluez', '/org/bluez/hci0')
            self._media_iface = dbus.Interface(media_obj, 'org.bluez.Media1')

            self._register_with_bluez()
            print("[AVRCP METADATA] CarPi5 Media Player registered with BlueZ for Uconnect dash display!")
        except Exception as e:
            print(f"[AVRCP METADATA] Player init error: {e}")

    def _register_with_bluez(self):
        if not self._media_iface:
            return
        try:
            import dbus
            props = {
                'PlaybackStatus': self.playback_status,
                'Track': dbus.Dictionary({
                    'Title': self.current_track.get('title', 'Unknown Title'),
                    'Artist': self.current_track.get('artist', 'Unknown Artist'),
                    'Album': self.current_track.get('album', 'CarPi5 In-Dash'),
                    'Genre': self.current_track.get('genre', 'Music'),
                    'Duration': dbus.UInt32(int(self.current_track.get('duration_ms', 180000))),
                    'TrackNumber': dbus.UInt32(int(self.current_track.get('track_num', 1))),
                    'NumberOfTracks': dbus.UInt32(int(self.current_track.get('total_tracks', 1)))
                }, signature='sv')
            }
            try:
                self._media_iface.UnregisterPlayer("/org/carpi5/player")
            except Exception:
                pass

            self._media_iface.RegisterPlayer("/org/carpi5/player", props)
            self.is_registered = True
        except Exception as e:
            print(f"[AVRCP METADATA] Register error: {e}")

    def update_track(self, title: str, artist: str = "", album: str = "", genre: str = "", duration_sec: float = 0.0, track_num: int = 1, total_tracks: int = 1):
        """Updates the active track metadata and broadcasts it over Bluetooth AVRCP to Uconnect."""
        self.current_track = {
            "title": title or "Unknown Track",
            "artist": artist or "CarPi5 In-Dash Audio",
            "album": album or "CarPi5",
            "genre": genre or "Music",
            "duration_ms": int(duration_sec * 1000) if duration_sec > 0 else 180000,
            "track_num": track_num or 1,
            "total_tracks": total_tracks or 1
        }
        print(f"[AVRCP METADATA] Broadcasting to Car Radio Screen: '{title}' by '{artist}' (Album: '{album}')")
        if sys.platform.startswith("linux") and self._media_iface:
            threading.Thread(target=self._register_with_bluez, daemon=True).start()

    def set_status(self, status: str):
        self.playback_status = "playing" if status == "playing" else "paused"
        if sys.platform.startswith("linux") and self._media_iface:
            threading.Thread(target=self._register_with_bluez, daemon=True).start()
