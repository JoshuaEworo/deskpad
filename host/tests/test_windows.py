"""Windows ABI/packet tests; these never inject input into the runner's desktop."""

import ctypes
import sys

import pytest
from deskpad.native import WindowsInput

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows ABI only")


def test_native_input_layout_and_unicode_packets():
    native = WindowsInput()
    assert ctypes.sizeof(native.Input) == (40 if ctypes.sizeof(ctypes.c_void_p) == 8 else 28)
    packets = []
    native._send = lambda event: packets.append(
        (event.type, event.ki.wVk, event.ki.wScan, event.ki.dwFlags)
    )
    native.text("A😀\r\n\t")
    unicode_down = [scan for kind, vk, scan, flags in packets if kind == 1 and flags == 4]
    assert unicode_down == [0x41, 0xD83D, 0xDE00]
    assert (1, 0x0D, 0, 0) in packets
    assert (1, 9, 0, 0) in packets
    assert len(packets) == 10


def test_extended_key_packet_flags():
    native = WindowsInput()
    flags = []
    native._send = lambda event: flags.append(event.ki.dwFlags)
    native.key("ArrowRight", True)
    native.key("ArrowRight", False)
    assert flags == [1, 3]
