import av
import threading
import time
import queue
from urllib.parse import urlparse

from arcane_eyes.core.interfaces import IVideoRecorder
from arcane_eyes.core.exceptions import RecordingError


class PyAVRecorderService(IVideoRecorder):
    def __init__(self):
        self._output_container = None
        self._is_recording = False
        self._lock = threading.Lock()
        self._end_time = 0
        self._packet_queue = queue.Queue(maxsize=300)

        # IDE Fix: Initialize dynamically assigned attributes
        self._out_video = None
        self._out_audio = None

        # Cross-thread communication flag
        self._video_ready_event = threading.Event()

    def start(self, rtsp_url: str, output_path: str, duration_minutes: int) -> None:
        try:
            with self._lock:
                from arcane_eyes.core.config import RTSP_OPTIONS, AUDIO_PORT, AUDIO_FORMAT, AUDIO_OPTIONS

                parsed_url = urlparse(rtsp_url)
                ip = parsed_url.hostname
                audio_url = f"tcp://{ip}:{AUDIO_PORT}"

                video_input = av.open(rtsp_url, options=RTSP_OPTIONS)
                audio_input = av.open(audio_url, format=AUDIO_FORMAT, options=AUDIO_OPTIONS)
                self._output_container = av.open(output_path, mode='w')

                in_video = video_input.streams.video[0]
                self._out_video = self._output_container.add_stream_from_template(in_video)

                in_audio = audio_input.streams.audio[0]
                self._out_audio = self._output_container.add_stream('aac', rate=int(AUDIO_OPTIONS['ar']))

                self._is_recording = True
                self._end_time = time.time() + (duration_minutes * 60)
                self._video_ready_event.clear()

            threading.Thread(target=self._video_reader, args=(video_input,), daemon=True).start()
            threading.Thread(target=self._audio_reader, args=(audio_input, in_audio), daemon=True).start()
            threading.Thread(target=self._muxer_loop, daemon=True).start()

        except Exception as e:
            raise RecordingError(f"PyAV failed to initialize streams: {str(e)}")

    def _video_reader(self, container):
        try:
            first_keyframe_found = False
            start_pts = None
            start_dts = None

            for packet in container.demux(video=0):
                if not self._is_recording: break
                if packet.dts is None: continue

                if not first_keyframe_found:
                    if packet.is_keyframe:
                        first_keyframe_found = True
                        start_pts = packet.pts
                        start_dts = packet.dts
                        # Signal the audio thread that we are ready!
                        self._video_ready_event.set()
                    else:
                        continue

                # Rebase timestamps to start near 0
                if packet.pts is not None and start_pts is not None:
                    packet.pts -= start_pts
                if packet.dts is not None and start_dts is not None:
                    packet.dts -= start_dts

                self._packet_queue.put(('video', packet))
        finally:
            container.close()

    def _audio_reader(self, container, audio_stream):
        try:
            # Wait until the video thread catches a keyframe
            while self._is_recording and not self._video_ready_event.is_set():
                self._video_ready_event.wait(timeout=0.5)

            for packet in container.demux(audio_stream):
                if not self._is_recording: break

                for frame in packet.decode():
                    for aac_packet in self._out_audio.encode(frame):
                        self._packet_queue.put(('audio', aac_packet))
        finally:
            container.close()

    def _muxer_loop(self):
        try:
            while self._is_recording and time.time() < self._end_time:
                try:
                    stream_type, packet = self._packet_queue.get(timeout=1.0)

                    with self._lock:
                        if stream_type == 'video':
                            packet.stream = self._out_video
                        elif stream_type == 'audio':
                            packet.stream = self._out_audio

                        self._output_container.mux(packet)
                except queue.Empty:
                    continue
        finally:
            self.stop()
            with self._lock:
                if self._output_container:
                    self._output_container.close()
                    self._output_container = None

    def stop(self) -> None:
        with self._lock:
            self._is_recording = False

    @property
    def is_recording(self) -> bool:
        return self._is_recording