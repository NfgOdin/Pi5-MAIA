"""
avrcp_player.py - Bluetooth AVRCP Media Player & MPRIS Broadcaster for CarPi5
Registers an AVRCP Target Player directly on BlueZ (/org/carpi5/player)
implementing the official BlueZ Media1 / MPRIS2 specification.

Broadcasts real-time Track Metadata (Title, Artist, Album, Genre, Duration)
directly to the Dodge Dart Uconnect 8.4 radio touchscreen and instrument cluster!
"""

import os
import sys
import time
import threading
from typing import Dict, Any, Optional

PLAYER_IFACE = 'org.mpris.MediaPlayer2.Player'
MEDIA_IFACE = 'org.bluez.Media1'
PROPS_IFACE = 'org.freedesktop.DBus.Properties'

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
        self.playback_status = "paused"
        self._player_obj = None
        self._media_iface = None
        self._sys_bus = None
        self._session_bus = None
        self._mpris_session_player = None

        if sys.platform.startswith("linux"):
            threading.Thread(target=self._init_player, daemon=True).start()

    def _init_player(self):
        try:
            import dbus
            import dbus.bus
            import dbus.service
            import dbus.mainloop.glib
            from gi.repository import GLib

            # D-Bus GLib Main Loop is REQUIRED for asynchronous signals and object export
            glib_dbus = dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
            self._glib_loop = GLib.MainLoop()
            threading.Thread(target=self._glib_loop.run, daemon=True).start()

            # Connect with attached mainloop (using dedicated BusConnection to avoid un-attached singleton)
            try:
                self._sys_bus = dbus.bus.BusConnection(dbus.Bus.TYPE_SYSTEM, mainloop=glib_dbus)
            except Exception:
                self._sys_bus = dbus.SystemBus(mainloop=glib_dbus)

            parent = self

            class BlueZMprisPlayer(dbus.service.Object):
                def __init__(self, bus, path):
                    super().__init__(bus, path)

                # ==========================================
                # org.mpris.MediaPlayer2.Player (Official BlueZ Spec)
                # ==========================================
                @dbus.service.method(PLAYER_IFACE)
                def Play(self):
                    print("[AVRCP REMOTE] Received PLAY from Car Radio / Steering Wheel", flush=True)
                    if parent.action_callback:
                        parent.action_callback({"type": "media", "action": "play"})

                @dbus.service.method(PLAYER_IFACE)
                def Pause(self):
                    print("[AVRCP REMOTE] Received PAUSE from Car Radio / Steering Wheel", flush=True)
                    if parent.action_callback:
                        parent.action_callback({"type": "media", "action": "pause"})

                @dbus.service.method(PLAYER_IFACE)
                def PlayPause(self):
                    print("[AVRCP REMOTE] Received PLAY/PAUSE toggle", flush=True)
                    if parent.action_callback:
                        parent.action_callback({"type": "media", "action": "toggle"})

                @dbus.service.method(PLAYER_IFACE)
                def Stop(self):
                    if parent.action_callback:
                        parent.action_callback({"type": "media", "action": "pause"})

                @dbus.service.method(PLAYER_IFACE)
                def Next(self):
                    print("[AVRCP REMOTE] Received NEXT TRACK from Car Radio / Steering Wheel", flush=True)
                    if parent.action_callback:
                        parent.action_callback({"type": "media", "action": "next"})

                @dbus.service.method(PLAYER_IFACE)
                def Previous(self):
                    print("[AVRCP REMOTE] Received PREV TRACK from Car Radio / Steering Wheel", flush=True)
                    if parent.action_callback:
                        parent.action_callback({"type": "media", "action": "prev"})

                # ==========================================
                # org.bluez.MediaPlayer1 (Legacy BlueZ Fallback)
                # ==========================================
                @dbus.service.method('org.bluez.MediaPlayer1')
                def BluezPlay(self):
                    self.Play()

                @dbus.service.method('org.bluez.MediaPlayer1')
                def BluezPause(self):
                    self.Pause()

                @dbus.service.method('org.bluez.MediaPlayer1')
                def BluezNext(self):
                    self.Next()

                @dbus.service.method('org.bluez.MediaPlayer1')
                def BluezPrevious(self):
                    self.Previous()

                # ==========================================
                # org.mpris.MediaPlayer2 (Root interface)
                # ==========================================
                @dbus.service.method('org.mpris.MediaPlayer2')
                def Raise(self): pass

                @dbus.service.method('org.mpris.MediaPlayer2')
                def Quit(self): pass

                # ==========================================
                # org.freedesktop.DBus.Properties
                # ==========================================
                @dbus.service.method(PROPS_IFACE, in_signature='ss', out_signature='v')
                def Get(self, interface, prop):
                    return self.GetAll(interface).get(prop)

                @dbus.service.method(PROPS_IFACE, in_signature='s', out_signature='a{sv}')
                def GetAll(self, interface):
                    if interface == PLAYER_IFACE:
                        return dbus.Dictionary({
                            'PlaybackStatus': dbus.String('Playing' if parent.playback_status == 'playing' else 'Paused'),
                            'Position': dbus.Int64(0),
                            'Metadata': parent._build_mpris_metadata_dict(),
                            'Volume': dbus.Double(1.0),
                            'Rate': dbus.Double(1.0),
                            'MinimumRate': dbus.Double(1.0),
                            'MaximumRate': dbus.Double(1.0),
                            'CanGoNext': dbus.Boolean(True),
                            'CanGoPrevious': dbus.Boolean(True),
                            'CanPlay': dbus.Boolean(True),
                            'CanPause': dbus.Boolean(True),
                            'CanSeek': dbus.Boolean(False),
                            'CanControl': dbus.Boolean(True)
                        }, signature='sv')
                    elif interface == 'org.bluez.MediaPlayer1':
                        return dbus.Dictionary({
                            'PlaybackStatus': dbus.String(parent.playback_status),
                            'Track': parent._build_bluez_track_dict()
                        }, signature='sv')
                    elif interface == 'org.mpris.MediaPlayer2':
                        return dbus.Dictionary({
                            'CanQuit': dbus.Boolean(False),
                            'CanRaise': dbus.Boolean(False),
                            'HasTrackList': dbus.Boolean(False),
                            'Identity': dbus.String('CarPi5 In-Dash Audio'),
                            'SupportedUriSchemes': dbus.Array([], signature='s'),
                            'SupportedMimeTypes': dbus.Array([], signature='s')
                        }, signature='sv')
                    return dbus.Dictionary({}, signature='sv')

                @dbus.service.signal(PROPS_IFACE, signature='sa{sv}as')
                def PropertiesChanged(self, interface, changed_props, invalidated_props):
                    pass

            self._player_obj = BlueZMprisPlayer(self._sys_bus, '/org/carpi5/player')

            media_obj = self._sys_bus.get_object('org.bluez', '/org/bluez/hci0')
            self._media_iface = dbus.Interface(media_obj, MEDIA_IFACE)

            try:
                self._media_iface.UnregisterPlayer(dbus.ObjectPath('/org/carpi5/player'))
            except Exception:
                pass

            # Register with BlueZ using empty dictionary as per official BlueZ Media1 spec
            self._media_iface.RegisterPlayer(dbus.ObjectPath('/org/carpi5/player'), {})
            self.is_registered = True
            print("[AVRCP METADATA] Official BlueZ Media1 Player registered on /org/bluez/hci0!", flush=True)

            # 2. Also register on Session Bus for mpris-proxy compatibility
            try:
                if 'DBUS_SESSION_BUS_ADDRESS' not in os.environ:
                    if os.path.exists('/run/user/1000/bus'):
                        os.environ['XDG_RUNTIME_DIR'] = '/run/user/1000'
                        os.environ['DBUS_SESSION_BUS_ADDRESS'] = 'unix:path=/run/user/1000/bus'

                self._session_bus = dbus.SessionBus()
                self._session_bus_name = dbus.service.BusName('org.mpris.MediaPlayer2.carpi5', self._session_bus)
                self._mpris_session_player = BlueZMprisPlayer(self._session_bus, '/org/mpris/MediaPlayer2')
                print("[AVRCP METADATA] Session Bus MPRIS v2 broadcaster registered!", flush=True)
            except Exception as s_err:
                print(f"[AVRCP METADATA] Session Bus bridge note: {s_err}", flush=True)

        except Exception as e:
            print(f"[AVRCP METADATA] Player init error: {e}", flush=True)

    def _build_mpris_metadata_dict(self):
        import dbus
        trk_num = self.current_track.get('track_num', 1)
        dur_us = int(self.current_track.get('duration_ms', 180000)) * 1000
        return dbus.Dictionary({
            'mpris:trackid': dbus.ObjectPath(f'/org/mpris/MediaPlayer2/Track/{trk_num}'),
            'mpris:length': dbus.Int64(dur_us),
            'xesam:title': dbus.String(self.current_track.get('title', 'Unknown Track')),
            'xesam:artist': dbus.Array([dbus.String(self.current_track.get('artist', 'In-Dash Audio'))], signature='s'),
            'xesam:album': dbus.String(self.current_track.get('album', 'CarPi5 In-Dash')),
            'xesam:genre': dbus.Array([dbus.String(self.current_track.get('genre', 'Music'))], signature='s'),
            'xesam:trackNumber': dbus.Int32(int(trk_num))
        }, signature='sv')

    def _build_bluez_track_dict(self):
        import dbus
        return dbus.Dictionary({
            'Title': dbus.String(self.current_track.get('title', 'Unknown Title')),
            'Artist': dbus.String(self.current_track.get('artist', 'In-Dash Audio')),
            'Album': dbus.String(self.current_track.get('album', 'CarPi5 In-Dash')),
            'Genre': dbus.String(self.current_track.get('genre', 'Music')),
            'Duration': dbus.UInt32(int(self.current_track.get('duration_ms', 180000))),
            'TrackNumber': dbus.UInt32(int(self.current_track.get('track_num', 1))),
            'NumberOfTracks': dbus.UInt32(int(self.current_track.get('total_tracks', 1)))
        }, signature='sv')

    def update_track(self, title: str, artist: str = "", album: str = "", genre: str = "", duration_sec: float = 0.0, track_num: int = 1, total_tracks: int = 1):
        """Updates the active track metadata and broadcasts it over Bluetooth AVRCP to Uconnect."""
        self.current_track = {
            "title": title or "Unknown Track",
            "artist": artist or "In-Dash Audio",
            "album": album or "CarPi5",
            "genre": genre or "Music",
            "duration_ms": int(duration_sec * 1000) if duration_sec > 0 else 180000,
            "track_num": track_num or 1,
            "total_tracks": total_tracks or 1
        }
        print(f"[AVRCP METADATA] Broadcasting to Uconnect Dash Screen: '{title}' by '{artist}' (Album: '{album}', {int(duration_sec)}s)", flush=True)

        # 1. Fire on MPRIS2.Player interface (BlueZ uses this for AVRCP Title, Artist, Album)
        if self._player_obj:
            try:
                import dbus
                m_meta = self._build_mpris_metadata_dict()
                changed_mpris = dbus.Dictionary({'Metadata': m_meta}, signature='sv')
                self._player_obj.PropertiesChanged(PLAYER_IFACE, changed_mpris, dbus.Array([], signature='s'))

                # 2. Fire on legacy BlueZ interface
                b_track = self._build_bluez_track_dict()
                changed_bluez = dbus.Dictionary({'Track': b_track}, signature='sv')
                self._player_obj.PropertiesChanged('org.bluez.MediaPlayer1', changed_bluez, dbus.Array([], signature='s'))
            except Exception as err:
                print(f"[AVRCP METADATA] PropertiesChanged error: {err}", flush=True)

        if self._mpris_session_player:
            try:
                import dbus
                m_meta = self._build_mpris_metadata_dict()
                changed_mpris = dbus.Dictionary({'Metadata': m_meta}, signature='sv')
                self._mpris_session_player.PropertiesChanged(PLAYER_IFACE, changed_mpris, dbus.Array([], signature='s'))
            except Exception:
                pass

        # 3. Dynamic GAP Device Alias Fallback for Legacy Radios (e.g. 2013-2016 Dodge Dart Uconnect 8.4)
        # When Uconnect ignores AVRCP 1.5 metadata packets, it falls back to displaying the Bluetooth Adapter Alias!
        if self._sys_bus:
            try:
                import dbus
                clean_artist = (artist or "").strip()
                clean_title = (title or "").strip()
                if clean_artist and clean_title:
                    alias_str = f"{clean_artist} - {clean_title}"[:32]
                elif clean_title:
                    alias_str = clean_title[:32]
                else:
                    alias_str = "CarPi"
                adapter = self._sys_bus.get_object('org.bluez', '/org/bluez/hci0')
                props = dbus.Interface(adapter, 'org.freedesktop.DBus.Properties')
                props.Set('org.bluez.Adapter1', 'Alias', dbus.String(alias_str), timeout=1.5)
                print(f"[AVRCP LEGACY SYNC] Broadcasted to Dodge Dart Uconnect Display: '{alias_str}'", flush=True)
            except Exception as e:
                print(f"[AVRCP LEGACY SYNC] Note: {e}", flush=True)

    def get_status(self) -> Dict[str, Any]:
        return {
            "connected": self.is_registered,
            "playback_status": self.playback_status,
            "current_track": dict(self.current_track)
        }

    def set_status(self, status: str):
        self.playback_status = "playing" if status == "playing" else "paused"
        if self._player_obj:
            try:
                import dbus
                m_status = 'Playing' if self.playback_status == 'playing' else 'Paused'
                changed = dbus.Dictionary({'PlaybackStatus': dbus.String(m_status)}, signature='sv')
                self._player_obj.PropertiesChanged(PLAYER_IFACE, changed, dbus.Array([], signature='s'))
                self._player_obj.PropertiesChanged('org.bluez.MediaPlayer1', dbus.Dictionary({'PlaybackStatus': dbus.String(self.playback_status)}, signature='sv'), dbus.Array([], signature='s'))
            except Exception:
                pass

        if self._mpris_session_player:
            try:
                import dbus
                m_status = 'Playing' if self.playback_status == 'playing' else 'Paused'
                changed = dbus.Dictionary({'PlaybackStatus': dbus.String(m_status)}, signature='sv')
                self._mpris_session_player.PropertiesChanged(PLAYER_IFACE, changed, dbus.Array([], signature='s'))
            except Exception:
                pass
