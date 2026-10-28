"""Windows CI: verified old release -> actual updater handoff -> new installed app."""

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx
from deskpad.identity import Identity, key_id
from deskpad.settings import Settings
from deskpad.updates import (
    REPOSITORY,
    VERSION,
    Release,
    download_update,
    update_key,
    verify_release,
)


def run():
    if os.name != "nt":
        raise RuntimeError("Installer acceptance requires Windows")
    # The previous public release is the baseline for the first updater upgrade.
    baseline_url = f"https://github.com/{REPOSITORY}/releases/download/v0.2.0-alpha.2/update.json"
    root = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory(prefix="deskpad-upgrade-") as temporary:
        stage = Path(temporary)
        env = {**os.environ, "LOCALAPPDATA": str(stage / "profile")}
        app_dir = stage / "installed"
        with httpx.Client(timeout=30, follow_redirects=True) as client:
            response = client.get(baseline_url)
            response.raise_for_status()
            old = verify_release(response.json(), update_key(), current="0.0.0")
        if old is None:
            raise RuntimeError("No valid baseline installer")
        print("Downloading and installing verified baseline", flush=True)
        old_installer = download_update(old, stage / "baseline")
        subprocess.run(
            [
                str(old_installer),
                "/VERYSILENT",
                "/SUPPRESSMSGBOXES",
                "/SP-",
                "/NORESTART",
                f"/DIR={app_dir}",
            ],
            env=env,
            check=True,
            timeout=180,
        )
        profile = stage / "profile/Deskpad"
        Settings(name="Upgrade acceptance", remote=False, check_updates=False).save(
            profile / "settings.json"
        )
        identity = Identity(profile)
        phone = Identity(stage / "test-phone")
        identity.approve(key_id(phone.public), phone.public, "Acceptance phone")
        before = (identity.public, identity.owner, identity.gate, identity.devices)
        print("Rendering baseline with saved settings and pairing", flush=True)
        # Render the old installed app, proving that it reads the seeded profile.
        subprocess.run(
            [str(app_dir / "Deskpad.exe"), "--demo", "--screenshot", str(stage / "before.png")],
            env=env,
            check=True,
            timeout=60,
        )
        if not (stage / "before.png").exists():
            raise RuntimeError("Baseline app did not render")
        installer = (
            old_installer
            if "--handoff-only" in sys.argv
            else root / "dist/Deskpad-Setup-Windows-x64.exe"
        )
        release = Release(
            VERSION,
            "",
            hashlib.sha256(installer.read_bytes()).hexdigest(),
            installer.stat().st_size,
            "CI acceptance",
        )
        # Run the real handoff from a disposable parent process. It must wait for
        # that parent to exit, verify the installer again, install, and restart.
        staged_installer = stage / "new/Deskpad-Setup.exe"
        staged_installer.parent.mkdir()
        import shutil

        shutil.copyfile(installer, staged_installer)
        code = "import sys; from pathlib import Path; from deskpad.updates import Release, launch_installer; sys.frozen=True; sys.executable=sys.argv[1]; launch_installer(Path(sys.argv[2]), Release(**__import__('json').loads(sys.argv[3])))"
        print("Starting updater helper from disposable parent", flush=True)
        subprocess.run(
            [
                sys.executable,
                "-c",
                code,
                str(app_dir / "Deskpad.exe"),
                str(staged_installer),
                json.dumps(release.__dict__),
            ],
            env=env,
            check=True,
            timeout=30,
        )
        marker = staged_installer.with_name("installed.txt")
        deadline = time.monotonic() + 180
        while time.monotonic() < deadline and not marker.exists():
            error = staged_installer.with_name("update-error.txt")
            if error.exists():
                raise RuntimeError(
                    "Updater helper reported an installation failure: "
                    + error.read_text(errors="replace")
                )
            time.sleep(1)
        if not marker.exists() or marker.read_text(encoding="utf-8-sig").strip() != release.sha256:
            runner = staged_installer.with_name("update-runner.log")
            detail = (
                runner.read_text(errors="replace")
                if runner.exists()
                else "No runner log was created"
            )
            raise RuntimeError(
                "Updater did not report a verified successful install: " + detail[-6000:]
            )
        print("Updater installed and restarted the app; checking persistence", flush=True)
        loaded = Identity(profile)
        assert (loaded.public, loaded.owner, loaded.gate, loaded.devices) == before
        assert Settings.load(profile / "settings.json").name == "Upgrade acceptance"
        # Stop only the disposable app started by this test, then render the
        # installed upgraded version and remove its test installation.
        stop_script = stage / "stop-test-app.ps1"
        stop_script.write_text(
            "param([string]$AppPath)\n$p = Get-Process Deskpad -ErrorAction SilentlyContinue | Where-Object { $_.Path -eq $AppPath }\n$p | Stop-Process -Force\n$p | Wait-Process -Timeout 30 -ErrorAction SilentlyContinue\n",
            encoding="utf-8",
        )
        subprocess.run(
            ["powershell", "-NoProfile", "-File", str(stop_script), str(app_dir / "Deskpad.exe")],
            check=True,
            timeout=40,
        )
        subprocess.run(
            [str(app_dir / "Deskpad.exe"), "--demo", "--screenshot", str(stage / "after.png")],
            env=env,
            check=True,
            timeout=60,
        )
        assert (stage / "after.png").exists()
        subprocess.run(
            [str(app_dir / "unins000.exe"), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART"],
            check=True,
            timeout=60,
        )
        assert (profile / "settings.json").exists()
    print(
        "Installed updater upgrade passed: parent exit, verification, restart, settings/pairing persistence and uninstall."
    )


if __name__ == "__main__":
    run()
