import cv2
import numpy as np
from typing import Tuple
from arcane_eyes.core.interfaces import IStreamProcessor
from arcane_eyes.core.models import StreamFrame


class StreamService(IStreamProcessor):
    """
    Standardizes video frame processing for Arcane Eyes.
    Handles resizing, aspect ratio preservation, and UI conversion.
    """

    def __init__(self, target_width: int = 640, target_height: int = 480):
        self.target_width = target_width
        self.target_height = target_height

    def process_frame(self, frame: np.ndarray, is_recording: bool = False) -> StreamFrame:
        """
        Resizes the frame while maintaining aspect ratio and adds metadata.
        """
        orig_h, orig_w = frame.shape[:2]
        aspect_ratio = orig_w / orig_h

        # Calculate new dimensions
        if orig_w > orig_h:
            new_w = self.target_width
            new_h = int(self.target_width / aspect_ratio)
        else:
            new_h = self.target_height
            new_w = int(self.target_height * aspect_ratio)

        resized = cv2.resize(frame, (new_w, new_h))

        # If recording, we could add a visual indicator here at the service level
        if is_recording:
            cv2.circle(resized, (20, 20), 8, (0, 0, 255), -1)

        return StreamFrame(data=resized, is_recording=is_recording)

    def convert_for_ui(self, frame_data: np.ndarray) -> np.ndarray:
        """
        Converts BGR (OpenCV) to RGB for UI display.
        Actual QImage conversion happens in the UI layer to keep this service framework-agnostic.
        """
        return cv2.cvtColor(frame_data, cv2.COLOR_BGR2RGB)