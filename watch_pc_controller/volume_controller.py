from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
from ctypes import cast, POINTER
from comtypes import CLSCTX_ALL

class VolumeController:
    def __init__(self):
        self._endpoint_volume = None
        self._init_endpoint()

    def _init_endpoint(self):
        speakers = AudioUtilities.GetSpeakers()
        if hasattr(speakers, "EndpointVolume") and speakers.EndpointVolume is not None:
            self._endpoint_volume = speakers.EndpointVolume
        elif hasattr(speakers, "Activate"):
            interface = speakers.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
            self._endpoint_volume = cast(interface, POINTER(IAudioEndpointVolume))
        elif hasattr(speakers, "_dev") and hasattr(speakers._dev, "Activate"):
            interface = speakers._dev.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
            self._endpoint_volume = cast(interface, POINTER(IAudioEndpointVolume))

    def get_volume(self) -> int:
        """Returns the current master volume percentage (0 to 100)."""
        if not self._endpoint_volume:
            self._init_endpoint()
        current_scalar = self._endpoint_volume.GetMasterVolumeLevelScalar()
        return int(round(current_scalar * 100))

    def is_muted(self) -> bool:
        """Returns True if the system audio is currently muted."""
        if not self._endpoint_volume:
            self._init_endpoint()
        return bool(self._endpoint_volume.GetMute())

    def set_volume(self, target_percent: int) -> dict:
        """Sets the volume to an absolute target percentage (0 to 100)."""
        if not self._endpoint_volume:
            self._init_endpoint()
        
        old_vol = self.get_volume()
        clamped_target = max(0, min(100, int(target_percent)))
        
        # If muted and setting volume > 0, unmute
        if clamped_target > 0 and self.is_muted():
            self._endpoint_volume.SetMute(0, None)

        self._endpoint_volume.SetMasterVolumeLevelScalar(clamped_target / 100.0, None)
        new_vol = self.get_volume()
        
        return {
            "type": "absolute",
            "action": "set",
            "old_volume": old_vol,
            "new_volume": new_vol,
            "target": clamped_target,
            "is_muted": self.is_muted()
        }

    def change_volume(self, delta_percent: int) -> dict:
        """Changes the volume relatively by delta_percent (+ for increase, - for decrease)."""
        if not self._endpoint_volume:
            self._init_endpoint()

        old_vol = self.get_volume()
        target = old_vol + int(delta_percent)
        clamped_target = max(0, min(100, target))

        if delta_percent > 0 and self.is_muted():
            self._endpoint_volume.SetMute(0, None)

        self._endpoint_volume.SetMasterVolumeLevelScalar(clamped_target / 100.0, None)
        new_vol = self.get_volume()

        return {
            "type": "relative",
            "action": "increase" if delta_percent > 0 else "decrease",
            "delta": delta_percent,
            "old_volume": old_vol,
            "new_volume": new_vol,
            "is_muted": self.is_muted()
        }

    def set_mute(self, mute: bool) -> dict:
        """Mutes or unmutes the audio."""
        if not self._endpoint_volume:
            self._init_endpoint()
        self._endpoint_volume.SetMute(1 if mute else 0, None)
        return {
            "type": "mute",
            "is_muted": bool(self.is_muted()),
            "volume": self.get_volume()
        }
