from dataclasses import dataclass, field
from enum import Enum, auto
from datetime import datetime


class ConnectionStatus(Enum):
    DISCONNECTED = auto()
    CONNECTING = auto()
    CONNECTED = auto()
    ERROR = auto()


@dataclass
class TrackInfo:
    kind: str
    codec: str = ""
    width: int | None = None
    height: int | None = None
    fps: float | None = None
    sample_rate: int | None = None
    channels: int | None = None

    def to_dict(self) -> dict:
        return {
            "kind": self.kind,
            "codec": self.codec,
            "width": self.width,
            "height": self.height,
            "fps": self.fps,
            "sample_rate": self.sample_rate,
            "channels": self.channels,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "TrackInfo":
        return cls(
            kind=data.get("kind", ""),
            codec=data.get("codec", ""),
            width=data.get("width"),
            height=data.get("height"),
            fps=data.get("fps"),
            sample_rate=data.get("sample_rate"),
            channels=data.get("channels"),
        )


@dataclass
class StreamProfile:
    token: str
    name: str
    uri: str
    onvif_encoding: str = ""
    onvif_width: int | None = None
    onvif_height: int | None = None
    video: TrackInfo | None = None
    audio: TrackInfo | None = None
    valid: bool = False
    source: str = "onvif"
    error: str = ""

    @property
    def width(self) -> int:
        return self.video.width if self.video and self.video.width else self.onvif_width or 0

    @property
    def height(self) -> int:
        return self.video.height if self.video and self.video.height else self.onvif_height or 0

    @property
    def pixels(self) -> int:
        return self.width * self.height

    @property
    def has_audio(self) -> bool:
        return self.audio is not None

    def label(self) -> str:
        resolution = f"{self.width}x{self.height}" if self.width and self.height else "unknown"
        codec = self.video.codec if self.video and self.video.codec else self.onvif_encoding or "unknown"
        audio = "A/V" if self.has_audio else "video"
        return f"{self.name or self.token} - {resolution} - {codec} - {audio}"

    def to_dict(self) -> dict:
        return {
            "token": self.token,
            "name": self.name,
            "uri": self.uri,
            "onvif_encoding": self.onvif_encoding,
            "onvif_width": self.onvif_width,
            "onvif_height": self.onvif_height,
            "video": self.video.to_dict() if self.video else None,
            "audio": self.audio.to_dict() if self.audio else None,
            "valid": self.valid,
            "source": self.source,
            "error": self.error,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "StreamProfile":
        video = data.get("video")
        audio = data.get("audio")
        return cls(
            token=data.get("token", ""),
            name=data.get("name", ""),
            uri=data.get("uri", ""),
            onvif_encoding=data.get("onvif_encoding", ""),
            onvif_width=data.get("onvif_width"),
            onvif_height=data.get("onvif_height"),
            video=TrackInfo.from_dict(video) if isinstance(video, dict) else None,
            audio=TrackInfo.from_dict(audio) if isinstance(audio, dict) else None,
            valid=bool(data.get("valid", False)),
            source=data.get("source", "onvif"),
            error=data.get("error", ""),
        )


@dataclass
class CameraCapability:
    device_info: dict = field(default_factory=dict)
    services: dict = field(default_factory=dict)
    profiles: list[StreamProfile] = field(default_factory=list)
    ptz_supported: bool = False
    ptz_token: str = ""
    recording_audio_mode: str = ""
    warnings: list[str] = field(default_factory=list)
    stale: bool = True
    updated_at: str = ""

    def valid_profiles(self) -> list[StreamProfile]:
        return [profile for profile in self.profiles if profile.valid and profile.uri]

    def profile_by_token(self, token: str) -> StreamProfile | None:
        return next((profile for profile in self.profiles if profile.token == token), None)

    def preview_profile(self, selected_token: str = "") -> StreamProfile | None:
        selected = self.profile_by_token(selected_token)
        if selected and selected.valid:
            return selected
        valid = self.valid_profiles()
        return min(valid, key=lambda profile: (profile.pixels or 10**12, profile.name)) if valid else None

    def detail_profile(self, selected_token: str = "") -> StreamProfile | None:
        selected = self.profile_by_token(selected_token)
        if selected and selected.valid:
            return selected
        valid = self.valid_profiles()
        return max(valid, key=lambda profile: (profile.pixels, profile.has_audio, profile.name)) if valid else None

    def recording_profile(self, selected_token: str = "") -> StreamProfile | None:
        selected = self.profile_by_token(selected_token)
        if selected and selected.valid:
            return selected
        valid = self.valid_profiles()
        with_audio = [profile for profile in valid if profile.has_audio]
        candidates = with_audio or valid
        return max(candidates, key=lambda profile: (profile.pixels, profile.has_audio, profile.name)) if candidates else None

    def to_dict(self) -> dict:
        return {
            "device_info": self.device_info,
            "services": self.services,
            "profiles": [profile.to_dict() for profile in self.profiles],
            "ptz_supported": self.ptz_supported,
            "ptz_token": self.ptz_token,
            "recording_audio_mode": self.recording_audio_mode,
            "warnings": self.warnings,
            "stale": self.stale,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "CameraCapability":
        return cls(
            device_info=data.get("device_info", {}) if isinstance(data.get("device_info", {}), dict) else {},
            services=data.get("services", {}) if isinstance(data.get("services", {}), dict) else {},
            profiles=[
                StreamProfile.from_dict(profile)
                for profile in data.get("profiles", [])
                if isinstance(profile, dict)
            ],
            ptz_supported=bool(data.get("ptz_supported", False)),
            ptz_token=data.get("ptz_token", ""),
            recording_audio_mode=data.get("recording_audio_mode", ""),
            warnings=list(data.get("warnings", [])) if isinstance(data.get("warnings", []), list) else [],
            stale=bool(data.get("stale", False)),
            updated_at=data.get("updated_at", ""),
        )


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
    capability: CameraCapability = field(default_factory=CameraCapability)
    selected_preview_profile: str = ""
    selected_detail_profile: str = ""

    @property
    def rtsp_url(self) -> str:
        """Default detail RTSP URL for legacy callers."""
        return self.detail_stream_url

    @property
    def fallback_rtsp_url(self) -> str:
        return f"rtsp://{self.ip}:{self.port}"

    @property
    def preview_stream_url(self) -> str:
        profile = self.capability.preview_profile(self.selected_preview_profile)
        return profile.uri if profile else self.fallback_rtsp_url

    @property
    def detail_stream_url(self) -> str:
        profile = self.capability.detail_profile(self.selected_detail_profile)
        return profile.uri if profile else self.fallback_rtsp_url

    @property
    def recording_stream_url(self) -> str:
        profile = self.capability.recording_profile(self.selected_detail_profile)
        return profile.uri if profile else self.fallback_rtsp_url

    @property
    def recording_uses_rtsp_audio(self) -> bool:
        profile = self.capability.recording_profile(self.selected_detail_profile)
        return bool(profile and profile.has_audio)

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
