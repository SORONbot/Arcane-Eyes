from dataclasses import dataclass, field

from arcane_eyes.core.models import CameraCapability


CACHE_VERSION = "2"


@dataclass
class CameraCacheEntry:
    id: int
    ip: str
    display_name: str
    username: str = ""
    password: str = ""
    capability: CameraCapability = field(default_factory=CameraCapability)
    selected_preview_profile: str = ""
    selected_detail_profile: str = ""
    cache_version: str = CACHE_VERSION
    updated_at: str = ""
