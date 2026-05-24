from arcane_eyes.core.models import CameraCapability, CameraDevice, StreamProfile, TrackInfo


def make_profile(token: str, width: int, height: int, audio: bool = False, codec: str = "hevc") -> StreamProfile:
    return StreamProfile(
        token=token,
        name=token,
        uri=f"rtsp://camera/{token}",
        video=TrackInfo(kind="video", codec=codec, width=width, height=height),
        audio=TrackInfo(kind="audio", codec="pcm_alaw") if audio else None,
        valid=True,
    )


def test_preview_uses_lowest_resolution_and_detail_uses_highest():
    capability = CameraCapability(profiles=[
        make_profile("main", 1920, 1080),
        make_profile("sub", 640, 360),
    ])

    assert capability.preview_profile().token == "sub"
    assert capability.detail_profile().token == "main"


def test_recording_prefers_audio_profile_then_resolution():
    capability = CameraCapability(profiles=[
        make_profile("main_video_only", 1920, 1080),
        make_profile("sub_audio", 640, 360, audio=True),
    ])

    assert capability.recording_profile().token == "sub_audio"


def test_device_falls_back_to_bare_rtsp_without_valid_profiles():
    device = CameraDevice(ip="192.168.100.25")

    assert device.preview_stream_url == "rtsp://192.168.100.25:554"
    assert device.detail_stream_url == "rtsp://192.168.100.25:554"


def test_selected_detail_profile_overrides_default():
    capability = CameraCapability(profiles=[
        make_profile("main", 1920, 1080),
        make_profile("sub", 640, 360),
    ])
    device = CameraDevice(ip="192.168.100.25", capability=capability, selected_detail_profile="sub")

    assert device.detail_stream_url == "rtsp://camera/sub"


def test_capability_serializes_recording_audio_mode():
    capability = CameraCapability(
        profiles=[make_profile("main", 1920, 1080, audio=True)],
        recording_audio_mode="rtsp",
    )

    restored = CameraCapability.from_dict(capability.to_dict())

    assert restored.recording_audio_mode == "rtsp"
