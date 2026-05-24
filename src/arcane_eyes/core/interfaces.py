from abc import ABC, abstractmethod
from typing import List, Callable
import numpy as np

class IPTZController(ABC):
    """
    Interface for Pan-Tilt-Zoom control.
    """

    @abstractmethod
    def move(self, pan: float, tilt: float) -> None:
        """
        Starts continuous movement in the direction of x (pan) and y (tilt).
        """
        pass

    @abstractmethod
    def stop(self) -> None:
        """
        Sends a stop command to the camera to halt all active movement.
        """
        pass


class IDiscoveryService(ABC):
    """Interface for finding cameras on the network."""

    @abstractmethod
    def scan(self, network_range: str) -> List[str]:
        """Synchronously scan a network and return a list of found IPs."""
        pass

    @abstractmethod
    def start_async_scan(self, network_range: str, on_found: Callable[[str], None]) -> None:
        """Start a background scan that triggers a callback for each camera found."""
        pass


class IStreamProcessor(ABC):
    """Interface for processing raw video frames."""

    @abstractmethod
    def process_frame(self, frame: np.ndarray) -> np.ndarray:
        """Apply transformations like resizing or overlays."""
        pass

    @abstractmethod
    def convert_for_ui(self, frame: np.ndarray) -> object:
        """Convert a BGR frame to a format the UI can display (e.g., QImage)."""
        pass


class IVideoRecorder(ABC):
    """Interface for managing video recording tasks."""

    @abstractmethod
    def start(self, rtsp_url: str, output_path: str, duration_minutes: int, use_rtsp_audio: bool = False) -> None:
        """
        Initialize and start the recording process.
        Requires the rtsp_url to open the stream via PyAV or other backends.
        """
        pass

    @abstractmethod
    def stop(self) -> None:
        """Gracefully stop recording and finalize the file."""
        pass

    @property
    @abstractmethod
    def is_recording(self) -> bool:
        """Return the current status of the recorder."""
        pass
