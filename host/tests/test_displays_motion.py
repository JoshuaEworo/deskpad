"""Monitor selection never writes the cursor except on explicit user selection."""

import asyncio
import time
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import pytest
from deskpad.capture import ScreenCapture
from deskpad.native import DemoInput, RelativeMotion, WindowsInput
from deskpad.protocol import INPUT_ADAPTER, Display
from deskpad.rtc import RtcHub
from deskpad.service import Service
from deskpad.settings import Settings
from pydantic import ValidationError


def screens():
    capture = ScreenCapture(demo=True)
    capture.demo_displays = [
        {"left": 0, "top": 0, "width": 1280, "height": 720},
        {"left": -1280, "top": 0, "width": 1280, "height": 720},
    ]
    return capture


def test_auto_follow_negative_coordinates_and_fixed_view():
    capture = screens()
    capture.cursor = lambda: (-50, 200)
    assert capture.active_display()["left"] == -1280
    assert capture.monitor == 2
    capture.follow_cursor = False
    capture.cursor = lambda: (200, 300)
    assert capture.active_display()["left"] == -1280
    capture.follow_cursor = True
    assert capture.active_display()["left"] == 0
    capture.configure_display(2)
    assert capture.active_display()["left"] == -1280  # explicit selection handoff
    capture._manual_until = 0
    assert capture.active_display()["left"] == 0


def test_hotplug_falls_back_and_frame_metadata_is_consistent():
    capture = screens()
    capture.follow_cursor = False
    capture.configure_display(2)
    metadata, _ = capture.frame()
    assert metadata["bounds"]["left"] == -1280
    assert metadata["monitor"] == 2 and len(metadata["displays"]) == 2
    capture.demo_displays = capture.demo_displays[:1]
    capture._display_refresh = time.monotonic() - 3
    assert capture.active_display()["left"] == 0
    assert capture.monitor == 1
    with pytest.raises(ValueError, match="no longer connected"):
        capture.configure_display(2)


def test_explicit_switch_focuses_once_and_auto_follow_is_read_only():
    async def scenario():
        native, capture = DemoInput(), screens()
        capture.cursor = native.position
        with ThreadPoolExecutor(1) as worker, ThreadPoolExecutor(1) as inputs:
            hub = RtcHub(native, capture, worker, inputs, {}, Service(), Settings())
            await hub.configure_display(Display(type="display", monitor=2))
            assert native.position() == (-640, 360)
            # Following is observation only; it cannot reposition a physical mouse.
            native.x, native.y = 40, 50
            capture._manual_until = 0
            await asyncio.get_running_loop().run_in_executor(worker, capture.active_display)
            assert capture.monitor == 1 and native.position() == (40, 50)
            await hub.configure_display(Display(type="display", follow_cursor=False))
            assert not capture.follow_cursor and native.position() == (40, 50)
            with pytest.raises(ValueError):
                await hub.configure_display(Display(type="display", monitor=32))
            assert native.position() == (40, 50)

    asyncio.run(scenario())


def test_idle_native_input_never_sets_cursor_and_fractional_motion_is_preserved():
    native = WindowsInput.__new__(WindowsInput)
    native.motion = RelativeMotion()
    point, calls = [100, 200], []
    native.position = lambda: tuple(point)

    def move(x, y):
        calls.append((x, y))
        point[:] = [x, y]
        return True

    native.user = SimpleNamespace(SetCursorPos=move)
    for _ in range(100):
        native.move(0, 0)
    assert calls == []
    for _ in range(4):
        native.move(0.25, 0)
    assert calls == [(101, 200)]
    for _ in range(4):
        native.move(-0.25, 0)
    assert calls[-1] == (100, 200) and len(calls) == 2
    # External mouse movement remains authoritative, with no saved absolute target.
    point[:] = [900, 600]
    native.move(2, 0)
    assert calls[-1] == (902, 600)
    native.focus_display({"left": 0, "top": 0, "width": 1280, "height": 720})
    assert len(calls) == 3  # already on that display: do not reset hover


@pytest.mark.parametrize("value", [0, 33, True, 1.5, "2"])
def test_display_requests_are_bounded_and_strict(value):
    with pytest.raises(ValidationError):
        INPUT_ADAPTER.validate_python({"type": "display", "monitor": value})


def test_capture_reenumerates_when_display_disappears_mid_grab(monkeypatch):
    import mss
    from PIL import Image

    calls = []

    class FakeMss:
        def __init__(self, left, broken):
            self.broken = broken
            self.monitors = [{}, {"left": left, "top": 0, "width": 2, "height": 2}]

        def close(self):
            calls.append("closed")

        def grab(self, bounds):
            calls.append(bounds["left"])
            if self.broken:
                raise RuntimeError("display removed")
            return SimpleNamespace(size=(2, 2), bgra=Image.new("RGBA", (2, 2)).tobytes())

    instances = iter([FakeMss(0, True), FakeMss(10, False)])
    monkeypatch.setattr(mss, "mss", lambda: next(instances))
    # Keep this regression independent of a Windows GPU capture backend.
    capture = ScreenCapture()
    capture._gpu_failed = True
    capture.cursor = lambda: (10, 1)
    image, bounds = capture.image()
    assert image.size == (2, 2) and bounds["left"] == 10
    assert calls == [0, "closed", 10]
    capture.close()


def test_terminal_capture_error_closes_peer_instead_of_leaving_blank_live_session():
    pytest.importorskip("aiortc")
    from deskpad.rtc import desktop_track

    async def scenario():
        class BrokenCapture:
            def image(self):
                raise RuntimeError("no displays")

        class FakePeer:
            closed = False
            messages = []

            def send(self, message):
                self.messages.append(message)

            async def close(self):
                self.closed = True

        with ThreadPoolExecutor(1) as worker:
            hub = SimpleNamespace(settings=Settings(), executor=worker, capture=BrokenCapture())
            peer = FakePeer()
            track = desktop_track(hub, peer)
            with pytest.raises(RuntimeError):
                await track.recv()
            await asyncio.sleep(0)
            assert peer.closed and peer.messages[-1]["type"] == "error"
            track.stop()

    asyncio.run(scenario())
