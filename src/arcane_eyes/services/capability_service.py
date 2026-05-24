from datetime import datetime, UTC

from onvif import ONVIFCamera

from arcane_eyes.core.config import ONVIF_DEFAULT_PASSWORD, ONVIF_DEFAULT_USER, ONVIF_PORT
from arcane_eyes.core.models import CameraCapability, StreamProfile
from arcane_eyes.services.stream_probe_service import StreamProbeService


class OnvifCapabilityService:
    """Read-only ONVIF media/device discovery with partial-failure tolerance."""

    def __init__(self, port: int = ONVIF_PORT, default_user: str = ONVIF_DEFAULT_USER, default_password: str = ONVIF_DEFAULT_PASSWORD):
        self.port = port
        self.default_user = default_user
        self.default_password = default_password

    def discover(self, ip: str, username: str = "", password: str = "") -> CameraCapability:
        capability = CameraCapability(stale=False)
        user = username or self.default_user
        pwd = password if (username or password) else self.default_password

        try:
            camera = ONVIFCamera(ip, self.port, user, pwd)
        except Exception as exc:
            capability.warnings.append(f"ONVIF connection failed: {exc}")
            capability.stale = True
            return capability

        self._collect_device_info(camera, capability)
        self._collect_capabilities(camera, capability)
        media = self._create_service(camera, "media", capability)
        if media:
            self._collect_profiles(media, capability)
        ptz = self._create_service(camera, "ptz", capability)
        if ptz:
            self._collect_ptz(ptz, capability)

        capability.updated_at = datetime.now(UTC).isoformat()
        return capability

    def _collect_device_info(self, camera, capability: CameraCapability) -> None:
        try:
            info = camera.devicemgmt.GetDeviceInformation()
            capability.device_info = {
                "manufacturer": getattr(info, "Manufacturer", ""),
                "model": getattr(info, "Model", ""),
                "firmware_version": getattr(info, "FirmwareVersion", ""),
                "serial_number": getattr(info, "SerialNumber", ""),
                "hardware_id": getattr(info, "HardwareId", ""),
            }
        except Exception as exc:
            capability.warnings.append(f"GetDeviceInformation failed: {exc}")

    def _collect_capabilities(self, camera, capability: CameraCapability) -> None:
        try:
            caps = camera.devicemgmt.GetCapabilities({"Category": "All"})
            capability.services = {
                "media": self._service_uri(getattr(caps, "Media", None)),
                "ptz": self._service_uri(getattr(caps, "PTZ", None)),
                "imaging": self._service_uri(getattr(caps, "Imaging", None)),
                "events": self._service_uri(getattr(caps, "Events", None)),
                "device": self._service_uri(getattr(caps, "Device", None)),
            }
        except Exception as exc:
            capability.warnings.append(f"GetCapabilities failed: {exc}")

    def _collect_profiles(self, media, capability: CameraCapability) -> None:
        try:
            profiles = media.GetProfiles()
        except Exception as exc:
            capability.warnings.append(f"GetProfiles failed: {exc}")
            return

        for index, profile in enumerate(profiles, start=1):
            token = getattr(profile, "token", "") or f"profile_{index}"
            encoder = getattr(profile, "VideoEncoderConfiguration", None)
            resolution = getattr(encoder, "Resolution", None)
            stream = StreamProfile(
                token=token,
                name=getattr(profile, "Name", "") or token,
                uri="",
                onvif_encoding=getattr(encoder, "Encoding", "") if encoder else "",
                onvif_width=getattr(resolution, "Width", None) if resolution else None,
                onvif_height=getattr(resolution, "Height", None) if resolution else None,
            )
            try:
                uri_response = media.GetStreamUri({
                    "StreamSetup": {
                        "Stream": "RTP-Unicast",
                        "Transport": {"Protocol": "RTSP"},
                    },
                    "ProfileToken": token,
                })
                stream.uri = getattr(uri_response, "Uri", "") or ""
            except Exception as exc:
                stream.error = f"GetStreamUri failed: {exc}"
            capability.profiles.append(stream)

    def _collect_ptz(self, ptz, capability: CameraCapability) -> None:
        capability.ptz_supported = True
        try:
            configs = ptz.GetConfigurations()
            if configs:
                capability.ptz_token = getattr(configs[0], "token", "")
        except Exception as exc:
            capability.warnings.append(f"PTZ configuration discovery failed: {exc}")

    def _create_service(self, camera, service_name: str, capability: CameraCapability):
        try:
            return getattr(camera, f"create_{service_name}_service")()
        except Exception as exc:
            capability.warnings.append(f"{service_name.upper()} service unavailable: {exc}")
            return None

    @staticmethod
    def _service_uri(service) -> str:
        if not service:
            return ""
        return getattr(service, "XAddr", "") or ""


class CameraCapabilityEnrichmentService:
    def __init__(
        self,
        onvif_service: OnvifCapabilityService | None = None,
        probe_service: StreamProbeService | None = None,
    ):
        self.onvif_service = onvif_service or OnvifCapabilityService()
        self.probe_service = probe_service or StreamProbeService()

    def enrich(self, ip: str, username: str = "", password: str = "", port: int = 554) -> CameraCapability:
        capability = self.onvif_service.discover(ip, username=username, password=password)
        capability = self.probe_service.enrich(ip, capability, port=port)
        recording_profile = capability.recording_profile()
        capability.recording_audio_mode = "rtsp" if recording_profile and recording_profile.has_audio else "legacy_tcp"
        capability.stale = False
        capability.updated_at = datetime.now(UTC).isoformat()
        return capability
