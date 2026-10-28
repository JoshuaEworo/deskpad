import sys
from types import SimpleNamespace

import pytest
from deskpad import media_setup
from deskpad.media_setup import cable_outputs, media_permissions, supported_cable
from deskpad.settings import Settings


def test_only_supported_virtual_cable_outputs_are_offered():
    devices = [
        {"name": "Speakers (Realtek(R) Audio)", "max_output_channels": 2, "hostapi": 0},
        {"name": "CABLE Input (VB-Audio Virtual Cable)", "max_output_channels": 2, "hostapi": 0},
        {"name": "CABLE Input (VB-Audio Virtual Cable)", "max_output_channels": 2, "hostapi": 1},
        {"name": "CABLE Output (VB-Audio Virtual Cable)", "max_output_channels": 0, "hostapi": 1},
    ]
    outputs = cable_outputs(devices, [{"name": "MME"}, {"name": "Windows WASAPI"}])
    assert len(outputs) == 1 and outputs[0]["id"] == 2
    assert supported_cable("CABLE-A Input (VB-Audio Cable A)")
    assert not supported_cable("Speakers (Realtek(R) Audio)")
    assert not supported_cable("CABLE Output (VB-Audio Virtual Cable)")


def ready_setup():
    return {
        **{
            name: {"ready": True, "state": "Ready", "detail": "Detected"}
            for name in ("camera", "microphone", "speakers")
        },
        "outputs": [{"id": 2, "name": "CABLE Input (VB-Audio Virtual Cable)"}],
    }


def test_permission_is_separate_from_setup_and_cable_identity():
    setup = ready_setup()
    settings = Settings(
        camera=True,
        microphone=True,
        speakers=True,
        microphone_output=2,
        microphone_output_name="CABLE Input (VB-Audio Virtual Cable)",
    )
    assert all(media_permissions(settings, setup).values())
    assert not any(media_permissions(settings, None).values())
    setup["camera"]["ready"] = False
    assert not media_permissions(settings, setup)["camera"]
    settings.microphone_output_name = "Speakers (Realtek(R) Audio)"
    assert not media_permissions(settings, setup)["microphone"]
    settings.microphone_output_name = "CABLE Input (VB-Audio Virtual Cable)"
    settings.microphone_output = 3
    assert not media_permissions(settings, setup)["microphone"]
    settings.camera = settings.microphone = settings.speakers = False
    assert not any(media_permissions(settings, ready_setup()).values())


def test_inspection_detects_setup_without_opening_camera_or_audio(monkeypatch):
    monkeypatch.setattr(media_setup, "os", SimpleNamespace(name="nt"))
    monkeypatch.setattr(media_setup, "has_module", lambda _: True)
    monkeypatch.setattr(media_setup, "registered_cameras", lambda: ["OBS Virtual Camera"])

    def forbidden(*args, **kwargs):
        raise AssertionError("Setup check tried to capture media")

    monkeypatch.setitem(sys.modules, "pyvirtualcam", SimpleNamespace(Camera=forbidden))
    monkeypatch.setitem(sys.modules, "soundcard", SimpleNamespace(default_speaker=forbidden))
    devices = [
        {"name": "CABLE Input (VB-Audio Virtual Cable)", "max_output_channels": 2, "hostapi": 0}
    ]
    monkeypatch.setitem(
        sys.modules,
        "sounddevice",
        SimpleNamespace(
            query_devices=lambda *args: devices if not args else {"name": "Realtek speakers"},
            query_hostapis=lambda: [{"name": "Windows WASAPI", "default_output_device": 1}],
            RawOutputStream=forbidden,
        ),
    )
    result = media_setup.inspect_media()
    assert all(result[name]["ready"] for name in ("camera", "microphone", "speakers"))
    assert result["camera"]["device"] == "OBS Virtual Camera"
    assert len(result["outputs"]) == 1


def test_missing_devices_have_setup_states_and_physical_speakers_are_not_a_cable(monkeypatch):
    monkeypatch.setattr(media_setup, "os", SimpleNamespace(name="nt"))
    monkeypatch.setattr(media_setup, "has_module", lambda _: True)
    monkeypatch.setattr(media_setup, "registered_cameras", lambda: [])
    monkeypatch.setitem(
        sys.modules,
        "sounddevice",
        SimpleNamespace(
            query_devices=lambda *args: [
                {"name": "Speakers (Realtek(R) Audio)", "max_output_channels": 2, "hostapi": 0}
            ],
            query_hostapis=lambda: [{"name": "MME", "default_output_device": -1}],
        ),
    )
    result = media_setup.inspect_media()
    assert result["outputs"] == []
    for name in ("camera", "microphone", "speakers"):
        assert not result[name]["ready"]
        assert result[name]["state"] == "Setup required"


def test_legacy_physical_speaker_selection_never_opens_output(monkeypatch):
    pytest.importorskip("av")
    from deskpad.media_devices import MediaSink

    def forbidden(*args, **kwargs):
        raise AssertionError("Phone microphone opened physical speakers")

    monkeypatch.setitem(sys.modules, "sounddevice", SimpleNamespace(RawOutputStream=forbidden))
    settings = Settings(
        microphone=True, microphone_output=2, microphone_output_name="Speakers (Realtek(R) Audio)"
    )
    sink = MediaSink("audio", settings)
    sink.write(object(), True)
    assert "virtual microphone" in sink.error
    assert sink.device is None
