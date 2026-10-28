"""Assign the bundled mark to the actual native Windows taskbar window."""

import ctypes
import os
from pathlib import Path


def set_native_icon(window):
    if os.name != "nt":
        return
    path = Path(__file__).with_name("icon.ico")
    if not path.exists():
        return
    user = ctypes.WinDLL("user32", use_last_error=True)
    user.LoadImageW.argtypes = [
        ctypes.c_void_p,
        ctypes.c_wchar_p,
        ctypes.c_uint,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_uint,
    ]
    user.LoadImageW.restype = ctypes.c_void_p
    user.SendMessageW.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_size_t, ctypes.c_ssize_t]
    user.SendMessageW.restype = ctypes.c_ssize_t
    # Keep both handles alive for this window's lifetime. LR_LOADFROMFILE, IMAGE_ICON.
    handles = [user.LoadImageW(None, str(path), 1, size, size, 0x10) for size in (16, 48)]
    if not all(handles):
        raise OSError(ctypes.get_last_error(), "Could not load Deskpad window icon")
    for kind, handle in enumerate(handles):
        user.SendMessageW(int(window.winId()), 0x80, kind, handle)  # WM_SETICON
    window._native_icons = handles


def verify_native_icon(window):
    """Windows packaged-build smoke check, including pointer-safe native handles."""
    if os.name != "nt":
        return
    user = ctypes.WinDLL("user32", use_last_error=True)
    user.SendMessageW.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_size_t, ctypes.c_ssize_t]
    user.SendMessageW.restype = ctypes.c_ssize_t
    if window.windowIcon().isNull() or not all(
        user.SendMessageW(int(window.winId()), 0x7F, kind, 0) for kind in (0, 1)
    ):
        raise RuntimeError("Packaged window did not expose Deskpad taskbar icons")
