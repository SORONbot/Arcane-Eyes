import os
from pathlib import Path

# We go up 3 levels from /src/arcane_eyes/core to reach the project root
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
DEFAULT_SAVE_PATH = PROJECT_ROOT / "recordings"
CACHE_FILE_PATH = PROJECT_ROOT / ".eye_cache"

# Network Defaults
DEFAULT_SCAN_RANGE = os.getenv("SCAN_RANGE", "192.168.100.0/24")
RTSP_TRANSPORT_TYPE = "tcp"  # Standardizing on TCP for better stability

# Dictionary for PyAV/FFmpeg options
RTSP_OPTIONS = {
    'rtsp_transport': RTSP_TRANSPORT_TYPE,
    'stimeout': '5000000'  # 5-second timeout
}

# Audio Defaults
AUDIO_PORT = 8001
AUDIO_FORMAT = "mulaw"
AUDIO_OPTIONS = {
    'ar': '8000',  # Audio sample rate (8kHz)
    'ac': '1'      # Audio channels (1 = Mono)
}

# Apply to OpenCV environment
os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = f"rtsp_transport;{RTSP_TRANSPORT_TYPE}"