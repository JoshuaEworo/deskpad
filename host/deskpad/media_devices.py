"""Explicitly enabled Windows media adapters. No driver downloads or silent installs."""

import time


class MediaSink:
    def __init__(self, kind, settings):
        self.kind, self.settings = kind, settings
        self.device = None
        self.resampler = None
        self.error = ""
        self.retry_at = 0

    def write(self, frame, enabled):
        if not enabled:
            self.close()
            return
        if time.monotonic() < self.retry_at:
            return
        try:
            if self.kind == "video":
                import pyvirtualcam

                # Stable device format; phone orientation/resolution may change mid-session.
                image = frame.reformat(width=1280, height=720, format="rgb24").to_ndarray()
                if self.device is None:
                    self.device = pyvirtualcam.Camera(width=1280, height=720, fps=30)
                self.device.send(image)
            else:
                import sounddevice as sd
                from av import AudioResampler

                if self.settings.microphone_output is None:
                    raise RuntimeError(
                        "Choose an installed virtual microphone cable output in desktop Settings."
                    )
                if self.device is None:
                    target = sd.query_devices(self.settings.microphone_output, "output")
                    if (
                        not self.settings.microphone_output_name
                        or target["name"] != self.settings.microphone_output_name
                    ):
                        raise RuntimeError(
                            "The audio device changed. Reselect the virtual cable in desktop Settings."
                        )
                    self.device = sd.RawOutputStream(
                        samplerate=48000,
                        channels=2,
                        dtype="int16",
                        device=self.settings.microphone_output,
                        blocksize=960,
                    )
                    self.device.start()
                    self.resampler = AudioResampler(format="s16", layout="stereo", rate=48000)
                for converted in self.resampler.resample(frame):
                    self.device.write(converted.to_ndarray().tobytes())
        except Exception as error:
            self.close()
            self.retry_at = time.monotonic() + 15
            self.error = (
                f"{'Camera' if self.kind == 'video' else 'Microphone'} bridge unavailable: {error}"[
                    :220
                ]
            )

    def close(self):
        if self.device:
            self.device.close()
            self.device = None
        self.resampler = None


class SystemAudio:
    def __init__(self, settings):
        self.settings = settings
        self.context = self.recorder = None
        self.error = ""
        self.retry_at = 0

    def read(self):
        import numpy as np

        if not self.settings.speakers:
            self.close()
            return np.zeros((960, 2), dtype=np.float32)
        if time.monotonic() < self.retry_at:
            return np.zeros((960, 2), dtype=np.float32)
        try:
            import soundcard as sc

            if self.recorder is None:
                speaker = (
                    sc.get_speaker(self.settings.speaker_input)
                    if self.settings.speaker_input
                    else sc.default_speaker()
                )
                loopback = sc.get_microphone(speaker.id, include_loopback=True)
                self.context = loopback.recorder(samplerate=48000, channels=2, blocksize=960)
                self.recorder = self.context.__enter__()
            return self.recorder.record(numframes=960).astype(np.float32)
        except Exception as error:
            self.close()
            self.retry_at = time.monotonic() + 15
            self.error = f"Laptop audio unavailable: {error}"[:220]
            return np.zeros((960, 2), dtype=np.float32)

    def close(self):
        if self.context:
            self.context.__exit__(None, None, None)
        self.context = self.recorder = None
