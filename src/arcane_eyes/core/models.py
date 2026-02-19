from dataclasses import dataclass, field
from enum import Enum, auto
from datetime import datetime

class ConnectionStatus(Enum):
    DISCONNECTED = auto()
    CONNECTING = auto()
    CONNECTED = auto()
    ERROR = auto()

@dataclass
class CameraDevice:
    """
    The primary data model for a camera.
    Encapsulates all identity and state information.
    """
    ip: str
    port: int = 554
    name: str = "Unknown Camera"
    username: str = ""
    password: str = ""
    status: ConnectionStatus = ConnectionStatus.DISCONNECTED

    @property
    def rtsp_url(self) -> str:
        """Constructs the RTSP string used by OpenCV."""
        return f"rtsp://{self.ip}:{self.port}"

    def __post_init__(self):
        """Logic to run after the object is created."""
        if self.name is None:
            self.name = f"Camera_{self.ip.replace('.', '_')}"

@dataclass(frozen=True)
class RecordingRequest:
    """
    An immutable data object representing a user's request to record.
    Matches the logic found in the RecordDialog.
    """
    target_ip: str
    output_path: str
    duration_minutes: int
    start_time: datetime = field(default_factory=datetime.now)


@dataclass
class StreamFrame:
    """
    A container for a single video frame and its associated metadata.
    Prevents passing 'is_recording' as a separate loose boolean.
    """
    data: object  # numpy array from OpenCV
    is_recording: bool = False
    timestamp: datetime = field(default_factory=datetime.now)