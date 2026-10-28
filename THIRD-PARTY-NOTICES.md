# Third-party components

Deskpad source is MIT licensed. Its distributions include separately licensed
components. Their licenses and copyright notices continue to apply.

- PySide6 / Qt Essentials / Shiboken: LGPLv3 and other applicable Qt notices.
  The Windows package uses separate dynamically loaded Qt DLLs (PyInstaller
  onedir). Do not convert it to a locked single-file distribution. Users may
  replace the Qt libraries. Qt source: https://code.qt.io/ and
  https://download.qt.io/official_releases/QtForPython/ .
- Python: PSF license. https://www.python.org/downloads/source/
- aiortc, aioice, PyAV, cryptography, FastAPI, Uvicorn, MSS, Pillow, qrcode,
  soundcard, sounddevice, pyvirtualcam and their dependencies: see installed
  dist-info license files included by the distribution build.
- FFmpeg libraries shipped by PyAV: licensing depends on the binary build and
  enabled codecs. Inspect the exact wheel and codec configuration before public
  binary release; do not assume every FFmpeg build is LGPL-only.
- OBS Virtual Camera and virtual audio cable drivers are not bundled or silently
  installed. Users of development media adapters supply those devices separately.

Binary redistribution, codec/patent review, code signing, and virtual-device
licensing/signing remain release gates. No signed release is claimed by this file.
