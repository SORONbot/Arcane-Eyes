from arcane_eyes.core.models import CameraCapability, StreamProfile
from arcane_eyes.services.capability_service import OnvifCapabilityService
from arcane_eyes.services.stream_probe_service import StreamProbeService


class FakeCodecContext:
    def __init__(self, name, width=None, height=None, sample_rate=None, channels=None):
        self.name = name
        self.width = width
        self.height = height
        self.sample_rate = sample_rate
        self.channels = channels


class FakeStream:
    def __init__(self, stream_type, context, average_rate=None):
        self.type = stream_type
        self.codec_context = context
        self.average_rate = average_rate


class FakeStreams:
    def __init__(self, video=None, audio=None):
        self.video = video or []
        self.audio = audio or []


class FakeContainer:
    def __init__(self, streams):
        self.streams = streams

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


def test_stream_probe_records_actual_video_and_audio_tracks(monkeypatch):
    def fake_open(_uri, options=None):
        return FakeContainer(FakeStreams(
            video=[FakeStream("video", FakeCodecContext("hevc", width=1920, height=1080), average_rate=12)],
            audio=[FakeStream("audio", FakeCodecContext("pcm_alaw", sample_rate=8000, channels=1))],
        ))

    monkeypatch.setattr("arcane_eyes.services.stream_probe_service.av.open", fake_open)
    capability = CameraCapability(profiles=[
        StreamProfile(
            token="main",
            name="mainStream",
            uri="rtsp://192.168.100.25:554/0/av0",
            onvif_encoding="H264",
        )
    ])

    enriched = StreamProbeService().enrich("192.168.100.25", capability)

    profile = enriched.valid_profiles()[0]
    assert profile.video.codec == "hevc"
    assert profile.audio.codec == "pcm_alaw"
    assert profile.onvif_encoding == "H264"


def test_stream_probe_adds_bare_rtsp_fallback_when_onvif_profiles_fail(monkeypatch):
    calls = []

    def fake_open(uri, options=None):
        calls.append(uri)
        if uri.endswith("/bad"):
            raise RuntimeError("unreachable")
        return FakeContainer(FakeStreams(
            video=[FakeStream("video", FakeCodecContext("hevc", width=640, height=360))]
        ))

    monkeypatch.setattr("arcane_eyes.services.stream_probe_service.av.open", fake_open)
    capability = CameraCapability(profiles=[
        StreamProfile(token="bad", name="bad", uri="rtsp://192.168.100.25/bad")
    ])

    enriched = StreamProbeService().enrich("192.168.100.25", capability)

    assert "rtsp://192.168.100.25:554" in calls
    assert enriched.valid_profiles()[0].token == "fallback_rtsp"


class AttrObject:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


class FakeDeviceMgmt:
    def GetDeviceInformation(self):
        return AttrObject(
            Manufacturer="EYEPLUS",
            Model="EYEPLUS_DEV",
            FirmwareVersion="57.0.0.1",
            SerialNumber="12345679890",
            HardwareId="88",
        )

    def GetCapabilities(self, _request):
        return AttrObject(
            Media=AttrObject(XAddr="http://camera/onvif/Media"),
            PTZ=AttrObject(XAddr="http://camera/onvif/PTZ"),
        )


class FakeMediaService:
    def GetProfiles(self):
        return [
            AttrObject(
                token="Profile_1",
                Name="mainStream",
                VideoEncoderConfiguration=AttrObject(
                    Encoding="H264",
                    Resolution=AttrObject(Width=1920, Height=1080),
                ),
            )
        ]

    def GetStreamUri(self, request):
        assert request["ProfileToken"] == "Profile_1"
        return AttrObject(Uri="rtsp://192.168.100.25:554/0/av0")


class FakePtzService:
    def GetConfigurations(self):
        raise RuntimeError("HTTP 400")


class FakeOnvifCamera:
    def __init__(self, *_args):
        self.devicemgmt = FakeDeviceMgmt()

    def create_media_service(self):
        return FakeMediaService()

    def create_ptz_service(self):
        return FakePtzService()


def test_onvif_discovery_collects_profiles_and_keeps_ptz_warning(monkeypatch):
    monkeypatch.setattr("arcane_eyes.services.capability_service.ONVIFCamera", FakeOnvifCamera)

    capability = OnvifCapabilityService().discover("192.168.100.25")

    assert capability.device_info["manufacturer"] == "EYEPLUS"
    assert capability.profiles[0].uri == "rtsp://192.168.100.25:554/0/av0"
    assert capability.profiles[0].onvif_encoding == "H264"
    assert capability.ptz_supported is True
    assert any("PTZ configuration discovery failed" in warning for warning in capability.warnings)
