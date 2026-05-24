from fractions import Fraction

import av

from arcane_eyes.core.config import RTSP_OPTIONS
from arcane_eyes.core.models import CameraCapability, StreamProfile, TrackInfo


class StreamProbeService:
    """Validates RTSP URLs and records the actual media tracks exposed by FFmpeg."""

    def probe_profile(self, profile: StreamProfile) -> StreamProfile:
        try:
            with av.open(profile.uri, options=RTSP_OPTIONS) as container:
                video_stream = next(iter(container.streams.video), None)
                audio_stream = next(iter(container.streams.audio), None)

                if video_stream:
                    profile.video = TrackInfo(
                        kind="video",
                        codec=video_stream.codec_context.name or "",
                        width=video_stream.codec_context.width or None,
                        height=video_stream.codec_context.height or None,
                        fps=self._rate_to_float(video_stream.average_rate),
                    )

                if audio_stream:
                    profile.audio = TrackInfo(
                        kind="audio",
                        codec=audio_stream.codec_context.name or "",
                        sample_rate=audio_stream.codec_context.sample_rate or None,
                        channels=audio_stream.codec_context.channels or None,
                    )

                profile.valid = profile.video is not None
                if not profile.valid:
                    profile.error = "No video track found."
        except Exception as exc:
            profile.valid = False
            profile.error = str(exc)
        return profile

    def enrich(self, ip: str, capability: CameraCapability, port: int = 554) -> CameraCapability:
        profiles = capability.profiles or [
            StreamProfile(
                token="fallback_rtsp",
                name="Fallback RTSP",
                uri=f"rtsp://{ip}:{port}",
                source="fallback",
            )
        ]

        capability.profiles = [self.probe_profile(profile) for profile in profiles]
        if not capability.valid_profiles() and not any(profile.source == "fallback" for profile in capability.profiles):
            fallback = self.probe_profile(StreamProfile(
                token="fallback_rtsp",
                name="Fallback RTSP",
                uri=f"rtsp://{ip}:{port}",
                source="fallback",
            ))
            capability.profiles.append(fallback)

        for profile in capability.profiles:
            if profile.error:
                capability.warnings.append(f"{profile.name or profile.token}: {profile.error}")
        return capability

    @staticmethod
    def _rate_to_float(rate: Fraction | None) -> float | None:
        if not rate:
            return None
        try:
            return round(float(rate), 3)
        except (TypeError, ZeroDivisionError):
            return None
