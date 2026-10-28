"""Signed, bounded desktop updates. Never trust URLs or hashes from unsigned metadata."""

import base64
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

import httpx
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

VERSION = "0.2.0-alpha.3"
MAX_INSTALLER = 300 * 1024 * 1024
REPOSITORY = "JoshuaEworo/deskpad"
FEED = f"https://github.com/{REPOSITORY}/releases/download/update-channel/update.json"


def version_key(value):
    match = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)(?:-alpha\.(\d+))?", value)
    if not match:
        raise ValueError("Unsupported update version")
    a, b, c, alpha = match.groups()
    return (int(a), int(b), int(c), alpha is None, int(alpha or 0))


def trusted_asset(url):
    parsed = urlparse(url)
    return (
        parsed.scheme == "https"
        and parsed.netloc == "github.com"
        and not parsed.query
        and not parsed.fragment
        and parsed.path.startswith(f"/{REPOSITORY}/releases/download/v")
        and parsed.path.endswith("/Deskpad-Setup-Windows-x64.exe")
        and not any(part in (".", "..") for part in parsed.path.split("/"))
    )


@dataclass(frozen=True)
class Release:
    version: str
    url: str
    sha256: str
    size: int
    notes: str


def verify_release(envelope, public_key, current=VERSION, now=None):
    try:
        payload = base64.b64decode(envelope["payload"], validate=True)
        if len(payload) > 16384:
            raise ValueError("Update information too large")
        Ed25519PublicKey.from_public_bytes(base64.b64decode(public_key, validate=True)).verify(
            base64.b64decode(envelope["signature"], validate=True), payload
        )
        data = json.loads(payload)
        now = time.time() if now is None else now
        if data["platform"] != "windows-x64" or not (
            data["published"] - 300 <= now < data["expires"] <= data["published"] + 366 * 86400
        ):
            raise ValueError("Update information expired or incompatible")
        release = Release(**{key: data[key] for key in Release.__dataclass_fields__})
        if (
            not trusted_asset(release.url)
            or release.url
            != f"https://github.com/{REPOSITORY}/releases/download/v{release.version}/Deskpad-Setup-Windows-x64.exe"
            or not re.fullmatch(r"[0-9a-f]{64}", release.sha256)
            or type(release.size) is not int
            or not 0 < release.size <= MAX_INSTALLER
            or not isinstance(release.notes, str)
            or len(release.notes) > 8000
        ):
            raise ValueError("Invalid update information")
        return release if version_key(release.version) > version_key(current) else None
    except (KeyError, TypeError, InvalidSignature, json.JSONDecodeError) as error:
        raise ValueError("Update signature or information is invalid") from error


def update_key():
    config = Path(__file__).with_name("update-key.json")
    return json.loads(config.read_text()).get("public_key", "") if config.exists() else ""


def check_update(public_key=None, client=None):
    public_key = update_key() if public_key is None else public_key
    if not public_key:
        raise ValueError("Updates are not published yet. Your installed app is still usable.")
    with (
        httpx.Client(timeout=20, follow_redirects=True) if client is None else client as connection
    ):
        with connection.stream("GET", FEED) as response:
            if response.status_code == 404:
                raise ValueError("No published update channel yet.")
            response.raise_for_status()
            body = bytearray()
            for chunk in response.iter_bytes():
                body.extend(chunk)
                if len(body) > 32768:
                    raise ValueError("Update information too large")
        return verify_release(json.loads(body), public_key)


def download_update(release, directory, progress=lambda _: None, client=None):
    directory.mkdir(parents=True, exist_ok=True)
    # A unique directory avoids executing a stale installer from an earlier attempt.
    target = Path(tempfile.mkdtemp(prefix="update-", dir=directory)) / "Deskpad-Setup.exe"
    digest, count = hashlib.sha256(), 0
    last_percent = -1
    try:
        with (
            httpx.Client(timeout=60, follow_redirects=True)
            if client is None
            else client as connection
        ):
            with connection.stream("GET", release.url) as response, target.open("xb") as output:
                response.raise_for_status()
                if response.url.scheme != "https":
                    raise ValueError("Insecure update download")
                for chunk in response.iter_bytes():
                    count += len(chunk)
                    if count > release.size:
                        raise ValueError("Update download exceeds signed size")
                    digest.update(chunk)
                    output.write(chunk)
                    percent = int(count * 100 / release.size)
                    if percent != last_percent:
                        progress(percent)
                        last_percent = percent
        if count != release.size or digest.hexdigest() != release.sha256:
            raise ValueError("Update download could not be verified. Nothing was installed.")
        return target
    except BaseException:
        target.unlink(missing_ok=True)
        target.parent.rmdir()
        raise


def can_install():
    return (
        os.name == "nt"
        and getattr(sys, "frozen", False)
        and Path(sys.executable).with_name("unins000.exe").exists()
    )


def launch_installer(installer, release):
    if not can_install():
        raise ValueError("Install Deskpad with its installer first to enable in-app installation.")
    # Verify again immediately before handing off. PowerShell verifies again after shutdown.
    if hashlib.sha256(installer.read_bytes()).hexdigest() != release.sha256:
        raise ValueError("Update installer changed; download it again.")
    helper = installer.with_name("install.ps1")
    helper.write_text(
        """param([string]$Installer, [string]$Hash, [int]$ParentId, [string]$AppDir)
$ErrorActionPreference = 'Stop'
try {
    Write-Output 'Waiting for Deskpad to exit'
    if (Get-Process -Id $ParentId -ErrorAction SilentlyContinue) {
        try {
            Wait-Process -Id $ParentId -Timeout 60 -ErrorAction Stop
        } catch {
            # The parent may exit between Get-Process and Wait-Process.
            if (Get-Process -Id $ParentId -ErrorAction SilentlyContinue) { throw }
        }
    }
    $stream = [System.IO.File]::OpenRead($Installer)
    $sha = [System.Security.Cryptography.SHA256]::Create()
    try {
        $actual = [System.BitConverter]::ToString($sha.ComputeHash($stream)).Replace('-', '').ToLowerInvariant()
    } finally {
        $stream.Dispose()
        $sha.Dispose()
    }
    if ($actual -ne $Hash) { throw 'Installer verification failed' }
    $installArguments = '/VERYSILENT /SUPPRESSMSGBOXES /SP- /NORESTART /NOCLOSEAPPLICATIONS /NORESTARTAPPLICATIONS /DIR="' + $AppDir + '" /LOG="' + (Join-Path (Split-Path $Installer) 'install.log') + '"'
    Write-Output 'Starting verified installer'
    $process = Start-Process -FilePath $Installer -ArgumentList $installArguments -PassThru -Wait
    if ($process.ExitCode -ne 0) { throw ('Installer failed: ' + $process.ExitCode) }
    Start-Process -FilePath (Join-Path $AppDir 'Deskpad.exe')
    Set-Content -LiteralPath (Join-Path (Split-Path $Installer) 'installed.txt') -Value $Hash
} catch {
    [System.IO.File]::WriteAllText((Join-Path (Split-Path $Installer) 'update-error.txt'), ($_ | Out-String))
    if ($env:GITHUB_ACTIONS -ne 'true') {
        Add-Type -AssemblyName PresentationFramework
        [System.Windows.MessageBox]::Show('Deskpad update failed. Your settings and pairing are kept. Open Deskpad again and retry. Details are in ' + (Split-Path $Installer), 'Deskpad update') | Out-Null
    }
    exit 1
}
""",
        encoding="utf-8",
    )
    powershell = Path(os.environ["SystemRoot"]) / "System32/WindowsPowerShell/v1.0/powershell.exe"
    # Windows children survive parent exit without DETACHED_PROCESS. Give the
    # console-hosted helper valid handles even when Deskpad itself is windowed.
    with installer.with_name("update-runner.log").open("ab") as output:
        subprocess.Popen(
            [
                str(powershell),
                "-NoProfile",
                "-NonInteractive",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(helper),
                "-Installer",
                str(installer),
                "-Hash",
                release.sha256,
                "-ParentId",
                str(os.getpid()),
                "-AppDir",
                str(Path(sys.executable).parent),
            ],
            # Do not inherit PowerShell 7/custom module paths into Windows PowerShell 5.
            env={**os.environ, "PSModulePath": str(powershell.parent / "Modules")},
            creationflags=subprocess.CREATE_NO_WINDOW,
            stdin=subprocess.DEVNULL,
            stdout=output,
            stderr=subprocess.STDOUT,
            close_fds=True,
        )
