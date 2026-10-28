"""WebRTC engine shared by local and remote transports. One controller lease per host."""

import asyncio
import logging
import time
from concurrent.futures import ThreadPoolExecutor
from fractions import Fraction

from pydantic import ValidationError

from .input import InputSession
from .media_setup import media_permissions
from .protocol import INPUT_ADAPTER, MediaState, Ping

log = logging.getLogger("deskpad")


class Peer:
    def __init__(self, hub, owner, ice):
        from aiortc import RTCBundlePolicy, RTCConfiguration, RTCIceServer, RTCPeerConnection

        self.hub, self.owner = hub, owner
        self.pc = RTCPeerConnection(
            RTCConfiguration(
                iceServers=[RTCIceServer(**s) for s in ice], bundlePolicy=RTCBundlePolicy.MAX_BUNDLE
            )
        )
        self.session = InputSession(hub.native)
        self.channel = None
        self.closed = False
        self.last_message = time.monotonic()
        self.queue = asyncio.Queue(maxsize=128)
        self.tasks = []
        self.tracks = []
        self.media_workers = []
        self.media_on = {"video": False, "audio": False, "speakers": False}
        self.media_queues = {}
        self.started = time.monotonic()
        self.pc.on("datachannel", self._channel)

        @self.pc.on("connectionstatechange")
        async def changed():
            if self.pc.connectionState in ("failed", "closed"):
                await self.close()

        @self.pc.on("track")
        def received(track):
            self.tasks.append(asyncio.create_task(self._consume(track)))

    def send(self, value):
        import json

        if self.channel and self.channel.readyState == "open":
            if self.channel.bufferedAmount > 65536:
                asyncio.create_task(self.close())
                return
            self.channel.send(json.dumps(value))

    def _channel(self, channel):
        if self.channel or channel.label != "control" or not channel.ordered:
            asyncio.create_task(self.close())
            return
        self.channel = channel

        @channel.on("open")
        def opened():
            self.send(
                {
                    "type": "hello",
                    "protocol": 2,
                    "cursor": self.hub.native.position(),
                    "media": {
                        **media_permissions(
                            self.hub.settings, self.hub.service.snapshot()["media_setup"]
                        ),
                        "setup": self.hub.service.snapshot()["media_setup"],
                    },
                }
            )

        @channel.on("message")
        def message(raw):
            if not isinstance(raw, str) or len(raw) > 16384 or self.queue.full():
                asyncio.create_task(self.close())
                return
            self.last_message = time.monotonic()
            self.queue.put_nowait(raw)

        @channel.on("close")
        def disconnected():
            asyncio.create_task(self.close())

        self.tasks.extend([asyncio.create_task(self._input()), asyncio.create_task(self._watch())])
        # aiortc may emit datachannel after its state already became open.
        if channel.readyState == "open":
            opened()

    async def _input(self):
        loop = asyncio.get_running_loop()
        try:
            while not self.closed:
                raw = await self.queue.get()
                try:
                    message = INPUT_ADAPTER.validate_json(raw)
                except ValidationError:
                    self.send({"type": "error", "message": "Unsupported input message."})
                    continue
                if isinstance(message, MediaState):
                    kind = {"camera": "video", "microphone": "audio", "speakers": "speakers"}[
                        message.kind
                    ]
                    if (
                        message.enabled
                        and not media_permissions(
                            self.hub.settings, self.hub.service.snapshot()["media_setup"]
                        )[message.kind]
                    ):
                        self.send(
                            {
                                "type": "media-status",
                                "kind": kind,
                                "error": "Finish setup and enable this feature in Deskpad on your laptop first.",
                            }
                        )
                        continue
                    self.media_on[kind] = message.enabled
                    self.hub.service.media_state(
                        message.kind, "Starting" if message.enabled else "Idle"
                    )
                    queue = self.media_queues.get(kind)
                    if not message.enabled and queue is not None:
                        while not queue.empty():
                            queue.get_nowait()
                        queue.put_nowait("disable")
                elif isinstance(message, Ping):
                    self.send({"type": "pong", "timestamp": message.timestamp})
                else:
                    if self.hub.paused():
                        await self.close()
                        return
                    await loop.run_in_executor(
                        self.hub.input_executor, self.session.handle, message
                    )
                    if message.type == "move":
                        self.send({"type": "cursor", "position": self.hub.native.position()})
        except asyncio.CancelledError:
            pass
        except Exception:
            log.exception("RTC input failed")
            await self.close()

    async def _watch(self):
        while not self.closed:
            await asyncio.sleep(1)
            if (
                time.monotonic() - self.last_message > 8
                or self.hub.paused()
                or (
                    self.owner.startswith("local:")
                    and not self.hub.pairing.valid(self.hub.lease["token"])
                )
            ):
                await self.close()

    async def answer(self, sdp):
        from aiortc import RTCSessionDescription

        await self.pc.setRemoteDescription(RTCSessionDescription(sdp=sdp, type="offer"))
        desktop = desktop_track(self.hub, self)
        self.tracks.append(desktop)
        self.pc.addTrack(desktop)
        audio = system_audio_track(self.hub, self)
        self.tracks.append(audio)
        self.pc.addTrack(audio)
        answer = await self.pc.createAnswer()
        await self.pc.setLocalDescription(answer)
        self.tasks.append(asyncio.create_task(self._setup_timeout()))
        return self.pc.localDescription.sdp

    async def _setup_timeout(self):
        await asyncio.sleep(25)
        if self.pc.connectionState != "connected":
            await self.close()

    async def _consume(self, track):
        from .media_devices import MediaSink

        sink = MediaSink(track.kind, self.hub.settings)
        worker = ThreadPoolExecutor(max_workers=1, thread_name_prefix="deskpad-media-sink")
        self.media_workers.append(worker)
        loop = asyncio.get_running_loop()
        queue = asyncio.Queue(maxsize=2 if track.kind == "audio" else 1)
        self.media_queues[track.kind] = queue

        def enqueue(frame):
            if queue.full():
                queue.get_nowait()
            queue.put_nowait(frame)

        async def receive():
            try:
                while not self.closed:
                    frame = await track.recv()
                    if self.media_on[track.kind]:
                        enqueue(frame)
            except asyncio.CancelledError:
                pass
            except Exception:
                enqueue(None)

        receiver = asyncio.create_task(receive())
        try:
            while not self.closed:
                frame = await queue.get()
                if frame is None:
                    break
                if isinstance(frame, str):
                    await loop.run_in_executor(worker, sink.close)
                    continue
                enabled = self.media_on[track.kind] and (
                    self.hub.settings.camera
                    if track.kind == "video"
                    else self.hub.settings.microphone
                )
                written = await loop.run_in_executor(worker, sink.write, frame, enabled)
                feature = "camera" if track.kind == "video" else "microphone"
                if written and enabled:
                    self.hub.service.media_state(feature, "Active")
                if sink.error:
                    self.hub.service.media_state(feature, "Needs attention", sink.error)
                    self.send({"type": "media-status", "kind": track.kind, "error": sink.error})
                    sink.error = ""
        except asyncio.CancelledError:
            pass
        except Exception as error:
            if not self.closed:
                self.send({"type": "media-status", "kind": track.kind, "error": str(error)[:180]})
        finally:
            receiver.cancel()
            await asyncio.gather(receiver, return_exceptions=True)
            self.media_queues.pop(track.kind, None)
            await loop.run_in_executor(worker, sink.close)
            worker.shutdown(wait=False)

    async def close(self):
        if self.closed:
            return
        self.closed = True
        # Do not cancel the current task or recursively await pc.close from its callback.
        for task in self.tasks:
            if task is not asyncio.current_task():
                task.cancel()
        for track in self.tracks:
            track.stop()
        await asyncio.get_running_loop().run_in_executor(
            self.hub.input_executor, self.session.release
        )
        if self.hub.lease["id"] == self.owner:
            self.hub.lease.update(id=None, token=None, video=None)
        self.hub.peers.pop(self.owner, None)
        self.hub.service.update(connected=False)
        for name in ("camera", "microphone", "speakers"):
            self.hub.service.media_state(name, "Idle")
        await self.pc.close()


class RtcHub:
    def __init__(self, native, capture, executor, input_executor, lease, service, settings):
        self.native, self.capture = native, capture
        self.executor, self.input_executor = executor, input_executor
        self.lease, self.service, self.settings = lease, service, settings
        self.peers = {}

    def paused(self):
        return self.service.snapshot()["paused"]

    async def offer(self, owner, sdp, ice):
        if self.paused() or self.lease["id"] is not None:
            raise ValueError("Laptop is paused or already in use")
        if not isinstance(sdp, str) or not 1 <= len(sdp) <= 110000:
            raise ValueError("Invalid offer")
        peer = Peer(self, owner, ice)
        self.lease.update(id=owner, token=owner)
        self.peers[owner] = peer
        try:
            answer = await peer.answer(sdp)
            self.service.update(connected=True)
            return answer
        except BaseException:
            await peer.close()
            raise

    async def close(self):
        await asyncio.gather(*(p.close() for p in list(self.peers.values())))


def desktop_track(hub, peer):
    from aiortc import VideoStreamTrack
    from av import VideoFrame

    class DesktopTrack(VideoStreamTrack):
        def __init__(self):
            super().__init__()
            self.start = time.monotonic()
            self.next_frame = self.start

        async def recv(self):
            now = time.monotonic()
            await asyncio.sleep(max(0, self.next_frame - now))
            self.next_frame = time.monotonic() + 1 / hub.settings.fps
            image, bounds = await asyncio.get_running_loop().run_in_executor(
                hub.executor, hub.capture.image
            )
            frame = VideoFrame.from_image(image)
            frame.pts = int((time.monotonic() - self.start) * 90000)
            frame.time_base = Fraction(1, 90000)
            peer.send(
                {
                    "type": "frame",
                    "sequence": frame.pts,
                    "width": image.width,
                    "height": image.height,
                    "bounds": bounds,
                    "cursor": hub.native.position(),
                }
            )
            return frame

    return DesktopTrack()


def system_audio_track(hub, peer):
    from aiortc import AudioStreamTrack
    from av import AudioFrame

    from .media_devices import SystemAudio

    class OutputTrack(AudioStreamTrack):
        def __init__(self):
            super().__init__()
            self.audio = SystemAudio(hub.settings)
            self.worker = ThreadPoolExecutor(
                max_workers=1, thread_name_prefix="deskpad-system-audio"
            )
            self.pts = 0
            self.start = time.monotonic()

        async def recv(self):
            import numpy as np

            await asyncio.sleep(max(0, self.start + self.pts / 48000 - time.monotonic()))
            samples = await asyncio.get_running_loop().run_in_executor(
                self.worker, self.audio.read, peer.media_on["speakers"]
            )
            if self.audio.error:
                hub.service.media_state("speakers", "Needs attention", self.audio.error)
                peer.send({"type": "media-status", "kind": "speakers", "error": self.audio.error})
                self.audio.error = ""
            elif self.audio.active and peer.media_on["speakers"]:
                hub.service.media_state("speakers", "Active")
            frame = AudioFrame.from_ndarray(
                np.ascontiguousarray(samples.T), format="fltp", layout="stereo"
            )
            frame.sample_rate = 48000
            frame.pts, frame.time_base = self.pts, Fraction(1, 48000)
            self.pts += samples.shape[0]
            return frame

        def stop(self):
            if self.readyState == "ended":
                return
            super().stop()
            self.worker.submit(self.audio.close)
            self.worker.shutdown(wait=False)

    return OutputTrack()
