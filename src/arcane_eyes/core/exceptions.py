class CameraAppError(Exception):
    """Base exception for all errors in the IP Camera Streamer application."""
    def __init__(self, message: str, ip: str = None):
        super().__init__(message)
        self.ip = ip

class DiscoveryError(CameraAppError):
    """Raised when the network scanner fails to initialize or complete a scan."""
    pass

class CameraConnectionError(CameraAppError):
    """Raised when an RTSP stream or ONVIF service cannot be reached."""
    pass

class PTZError(CameraAppError):
    """Raised when a Pan-Tilt-Zoom command fails or the device is not PTZ-capable."""
    pass

class RecordingError(CameraAppError):
    """Raised when FFmpeg fails to start or the storage path is inaccessible."""
    pass

class ConfigurationError(CameraAppError):
    """Raised when invalid settings (like malformed IP ranges) are provided."""
    pass