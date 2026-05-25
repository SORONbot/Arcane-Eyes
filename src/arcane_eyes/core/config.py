import os
from pathlib import Path

# Base Path Logic
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent

# Storage Paths
DEFAULT_SAVE_PATH = Path(os.getenv("SAVE_PATH", str(PROJECT_ROOT / "recordings")))
DATABASE_PATH = Path(os.getenv("DATABASE_PATH", str(PROJECT_ROOT / "arcane_eyes.sqlite3")))
SETUP_QR_CREDENTIAL_CACHE_PATH = Path(
    os.getenv("SETUP_QR_CREDENTIAL_CACHE_PATH", str(PROJECT_ROOT / ".setup_qr_credentials"))
)
SETUP_QR_FERNET_KEY = os.getenv("SETUP_QR_FERNET_KEY", "")

# Network & Transport
DEFAULT_SCAN_RANGE = os.getenv("SCAN_RANGE", "192.168.100.0/24")
RTSP_TRANSPORT_TYPE = os.getenv("RTSP_TRANSPORT", "tcp")
RTSP_TIMEOUT = os.getenv("RTSP_TIMEOUT", "5000000") # microseconds

# ONVIF
ONVIF_DEFAULT_USER = os.getenv("ONVIF_DEFAULT_USER", "admin")
ONVIF_DEFAULT_PASSWORD = os.getenv("ONVIF_DEFAULT_PASSWORD", "")
ONVIF_PORT = int(os.getenv("ONVIF_PORT", "80"))

# Audio Settings
AUDIO_PORT = int(os.getenv("AUDIO_PORT", 8001))
AUDIO_FORMAT = os.getenv("AUDIO_FORMAT", "mulaw")
AUDIO_SAMPLE_RATE = os.getenv("AUDIO_SAMPLE_RATE", "8000")
AUDIO_CHANNELS = os.getenv("AUDIO_CHANNELS", "1")

# --- Derived Dictionaries for Services ---

RTSP_OPTIONS = {
    'rtsp_transport': RTSP_TRANSPORT_TYPE,
    'stimeout': RTSP_TIMEOUT
}

AUDIO_OPTIONS = {
    'ar': AUDIO_SAMPLE_RATE,
    'ac': AUDIO_CHANNELS
}

# Apply to OpenCV environment
os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = f"rtsp_transport;{RTSP_TRANSPORT_TYPE}"
