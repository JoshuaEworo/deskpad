"""Read-only media setup discovery. This never captures or installs devices."""

import importlib.util
import os
import re

CAMERA_URL = "https://obsproject.com/download"
MICROPHONE_URL = "https://vb-audio.com/Cable/"


def supported_cable(name):
    # Only tested VB-CABLE playback endpoints. In particular, never list ordinary
    # speakers, loopback recording endpoints, or arbitrary output devices.
    return bool(re.search(r"\bCABLE(?:-[A-D])? Input\b.*\bVB-Audio", name, re.IGNORECASE))


def cable_outputs(devices, hostapis):
    candidates = {}
    for index, device in enumerate(devices):
        if device.get("max_output_channels", 0) < 2 or not supported_cable(device["name"]):
            continue
        api = hostapis[device["hostapi"]]["name"]
        # PortAudio reports the same cable through multiple Windows APIs. Prefer
        # WASAPI, then DirectSound, then MME, instead of showing duplicate options.
        rank = 0 if "WASAPI" in api else 1 if "DirectSound" in api else 2
        key = re.search(r"CABLE(?:-[A-D])? Input", device["name"], re.IGNORECASE)[0].casefold()
        value = {"id": index, "name": device["name"], "api": api, "rank": rank}
        if key not in candidates or rank < candidates[key]["rank"]:
            candidates[key] = value
    return sorted(candidates.values(), key=lambda value: value["name"])


def registered_cameras():
    if os.name != "nt":
        return []
    import winreg

    result = []
    category = r"CLSID\{860BB310-5D01-11D0-BD3B-00A0C911CE86}\Instance"
    try:
        with winreg.OpenKey(
            winreg.HKEY_CLASSES_ROOT, category, 0, winreg.KEY_READ | winreg.KEY_WOW64_64KEY
        ) as key:
            for index in range(winreg.QueryInfoKey(key)[0]):
                try:
                    with winreg.OpenKey(key, winreg.EnumKey(key, index)) as item:
                        name = winreg.QueryValueEx(item, "FriendlyName")[0]
                        if name in ("OBS Virtual Camera", "Unity Video Capture"):
                            result.append(name)
                except OSError:
                    continue
    except OSError:
        pass
    return sorted(set(result))


def has_module(name):
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError):
        return False


def unavailable(detail):
    return {"ready": False, "state": "Unavailable", "detail": detail}


def inspect_media():
    if os.name != "nt":
        return {
            **{
                name: unavailable("This feature requires the Windows desktop app.")
                for name in ("camera", "microphone", "speakers")
            },
            "outputs": [],
        }
    cameras = registered_cameras() if has_module("pyvirtualcam") else []
    result = {
        "camera": {
            "ready": bool(cameras),
            "state": "Ready" if cameras else "Setup required",
            "detail": f"In Zoom, choose {cameras[0]}."
            if cameras
            else "Install a supported virtual camera to use your phone in Zoom.",
            "device": cameras[0] if cameras else "",
        }
        if has_module("pyvirtualcam")
        else unavailable(
            "This Deskpad build is missing camera support. Install the full Windows app."
        ),
        "outputs": [],
    }
    if has_module("sounddevice"):
        try:
            import sounddevice as sd

            result["outputs"] = cable_outputs(sd.query_devices(), sd.query_hostapis())
            result["microphone"] = {
                "ready": bool(result["outputs"]),
                "state": "Ready" if result["outputs"] else "Setup required",
                "detail": "In Zoom, choose the cable's CABLE Output microphone."
                if result["outputs"]
                else "Install VB-CABLE to use your phone as a microphone in Zoom.",
            }
        except Exception:
            result["microphone"] = unavailable(
                "Windows audio devices could not be checked. Try Refresh devices."
            )
    else:
        result["microphone"] = unavailable(
            "This Deskpad build is missing microphone support. Install the full Windows app."
        )
    if has_module("soundcard") and has_module("sounddevice"):
        try:
            import sounddevice as sd

            apis = sd.query_hostapis()
            outputs = [
                api["default_output_device"]
                for api in apis
                if "WASAPI" in api["name"] and api["default_output_device"] >= 0
            ]
            speaker = sd.query_devices(outputs[0], "output") if outputs else None
            result["speakers"] = {
                "ready": speaker is not None,
                "state": "Ready" if speaker else "Setup required",
                "detail": f"Sends laptop sound from {speaker['name']} to your phone."
                if speaker
                else "Choose a Windows sound output, then Refresh devices.",
            }
        except Exception:
            result["speakers"] = unavailable(
                "Windows sound output could not be checked. Try Refresh devices."
            )
    else:
        result["speakers"] = unavailable(
            "This Deskpad build is missing laptop audio support. Install the full Windows app."
        )
    return result


def media_permissions(settings, setup):
    """Revalidate cached discovery against the user's selected cable and permissions."""
    allowed = {name: bool(getattr(settings, name)) for name in ("camera", "microphone", "speakers")}
    if not setup:
        return dict.fromkeys(allowed, False)
    if setup:
        for name in allowed:
            allowed[name] = allowed[name] and setup[name]["ready"]
    allowed["microphone"] = (
        allowed["microphone"]
        and supported_cable(settings.microphone_output_name)
        and settings.microphone_output is not None
    )
    if setup and allowed["microphone"]:
        allowed["microphone"] = any(
            value["id"] == settings.microphone_output
            and value["name"] == settings.microphone_output_name
            for value in setup["outputs"]
        )
    return allowed
