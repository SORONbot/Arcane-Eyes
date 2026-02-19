from onvif import ONVIFCamera
from arcane_eyes.core.interfaces import IPTZController
from arcane_eyes.core.exceptions import PTZError


class OnvifPTZService(IPTZController):
    """
    Service for controlling Pan-Tilt-Zoom functions via the ONVIF protocol.
    Wraps complex profile and token management into simple directional commands.
    """

    def __init__(self, ip: str, port: int = 80, user: str = 'admin', pwd: str = ''):
        self.ip = ip
        try:
            # Initialize connection to the physical hardware
            self.cam = ONVIFCamera(ip, port, user, pwd)
            self.ptz = self.cam.create_ptz_service()
            self.media = self.cam.create_media_service()

            # Professional systems usually target the first available profile
            profiles = self.media.GetProfiles()
            if not profiles:
                raise PTZError("No media profiles found on device", ip=ip)

            self.token = profiles[0].token
            self._active = True
        except Exception as e:
            self._active = False
            raise PTZError(f"PTZ Initialization failed: {str(e)}", ip=ip)

    def move(self, x: float, y: float) -> None:
        """
        Triggers continuous movement.
        x: Pan speed (-1.0 to 1.0)
        y: Tilt speed (-1.0 to 1.0)
        """
        if not self._active:
            return

        try:
            self.ptz.ContinuousMove({
                'ProfileToken': self.token,
                'Velocity': {'PanTilt': {'x': x, 'y': y}}
            })
        except Exception as e:
            # We raise a custom error so the UI can log it properly
            raise PTZError(f"Failed to execute move: {str(e)}", ip=self.ip)

    def stop(self) -> None:
        """Immediately halts all camera movement."""
        if not self._active:
            return

        try:
            self.ptz.Stop({'ProfileToken': self.token})
        except Exception as e:
            raise PTZError(f"Failed to stop movement: {str(e)}", ip=self.ip)