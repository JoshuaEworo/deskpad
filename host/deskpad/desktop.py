"""Deskpad desktop shell. Qt stays on the main thread; engine owns its asyncio loop."""

import argparse
import io
import logging
import os
import queue
import sys
import threading
import time
from pathlib import Path

import uvicorn

from . import updates
from .cli import local_ip
from .identity import Identity
from .media_setup import CAMERA_URL, MICROPHONE_URL, supported_cable
from .native import enable_dpi_awareness
from .qr import pairing_qr
from .server import create_app
from .service import Service
from .settings import Settings, state_directory

STYLE = """
QWidget { background:#101713; color:#edf2ef; font-family:'Segoe UI'; font-size:14px; }
QMainWindow { background:#101713; }
QLabel { background:transparent; }
QLabel#brand {font-size:22px;font-weight:700;}
QLabel#title {font-size:29px;font-weight:700;}
QLabel#section {font-size:19px;font-weight:600;}
QLabel#muted {color:#95a69c;}
QLabel#status {color:#b1e3c7;}
QLabel#code {font-family:Consolas;font-size:24px;color:#b1e3c7;}
QFrame#sidebar {border-right:1px solid #283a2f;}
QFrame#card {background:#17221b;border:1px solid #304537;border-radius:10px;}
QFrame#card QLabel, QFrame#card QCheckBox {background:transparent;}
QPushButton {background:#1b2921;border:1px solid #354c3e;border-radius:7px;padding:10px 15px;}
QPushButton:hover {background:#253a2d;border-color:#81ad92;}
QPushButton:pressed, QPushButton:checked {background:#2c4535;border-color:#b1e3c7;color:#b1e3c7;}
QPushButton#primary {background:#b1e3c7;color:#102317;border:0;font-weight:600;}
QPushButton#access {padding:7px 15px;}
QPushButton#nav {text-align:left;border:0;padding:13px 17px;background:transparent;}
QPushButton#nav:checked {background:#203328;color:#b1e3c7;}
QPushButton:disabled {color:#66796b;}
QLineEdit, QComboBox, QSpinBox {background:#111a15;border:1px solid #354c3e;border-radius:6px;padding:8px;}
QComboBox QAbstractItemView {background:#17221b;selection-background-color:#304b3a;}
QCheckBox {spacing:10px;padding:5px;}
QCheckBox::indicator {width:18px;height:18px;border:1px solid #5d7d68;border-radius:4px;}
QCheckBox::indicator:checked {background:#b1e3c7;}
QScrollArea {border:0;}
QToolTip {background:#203328;color:#edf2ef;border:1px solid #5d7d68;}
"""


class Engine:
    def __init__(self, settings, service, directory, demo):
        self.service, self.settings, self.directory = service, settings, directory
        self.demo = demo
        self.server = None
        self.thread = None

    def start(self):
        self.thread = threading.Thread(target=self.run, name="deskpad-engine", daemon=True)
        self.thread.start()

    def run(self):
        try:
            ip = local_ip()
            origins = [
                f"http://{host}:{self.settings.port}" for host in {ip, "localhost", "127.0.0.1"}
            ]
            app = create_app(
                state_path=self.directory / "devices.json",
                origins=origins,
                demo=self.demo,
                service=self.service,
                settings=self.settings,
                monitor=self.settings.monitor,
                fps=self.settings.fps,
                width=self.settings.width,
                quality=self.settings.quality,
                remote_identity=Identity(self.directory),
            )
            self.service.update(url=f"http://{ip}:{self.settings.port}")
            config = uvicorn.Config(
                app,
                host="0.0.0.0",
                port=self.settings.port,
                access_log=False,
                ws_max_size=131072,
                log_config=None,
                timeout_graceful_shutdown=5,
            )
            self.server = uvicorn.Server(config)
            self.server.run()
        except BaseException as error:
            logging.getLogger("deskpad").exception("Desktop engine stopped")
            self.service.update(error=f"Host could not start: {error}")
        finally:
            self.service.update(running=False)

    def stop(self):
        if self.server:
            self.server.should_exit = True
        if self.thread:
            self.thread.join(timeout=12)


def set_startup(enabled):
    if os.name != "nt":
        return
    import winreg

    with winreg.CreateKey(
        winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run"
    ) as key:
        if enabled:
            import subprocess

            command = (
                [sys.executable]
                if getattr(sys, "frozen", False)
                else [sys.executable, "-m", "deskpad.desktop"]
            )
            winreg.SetValueEx(key, "Deskpad", 0, winreg.REG_SZ, subprocess.list2cmdline(command))
        else:
            try:
                winreg.DeleteValue(key, "Deskpad")
            except FileNotFoundError:
                pass


def build_window(settings, service, directory, engine):
    from PySide6.QtCore import Qt, QTimer
    from PySide6.QtGui import QAction, QIcon, QPixmap
    from PySide6.QtWidgets import (
        QApplication,
        QCheckBox,
        QComboBox,
        QDialog,
        QFormLayout,
        QFrame,
        QHBoxLayout,
        QLabel,
        QLineEdit,
        QMainWindow,
        QMenu,
        QMessageBox,
        QPushButton,
        QScrollArea,
        QSpinBox,
        QStackedWidget,
        QSystemTrayIcon,
        QVBoxLayout,
        QWidget,
    )

    def label(text, name="", wrap=False):
        widget = QLabel(text)
        widget.setObjectName(name)
        widget.setTextFormat(Qt.TextFormat.PlainText)
        widget.setWordWrap(wrap)
        return widget

    def button(text, fn, name=""):
        widget = QPushButton(text)
        widget.setObjectName(name)
        widget.clicked.connect(fn)
        widget.setCursor(Qt.CursorShape.PointingHandCursor)
        return widget

    def card():
        frame = QFrame()
        frame.setObjectName("card")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(22, 20, 22, 20)
        layout.setSpacing(12)
        return frame, layout

    class Window(QMainWindow):
        def __init__(self):
            super().__init__()
            self.setWindowTitle("Deskpad")
            self.resize(980, 740)
            self.setMinimumSize(800, 650)
            # Use a raster Windows icon for the native window too. SVG rendering
            # plugins can be absent in a frozen build even with a correct EXE icon.
            icon_path = Path(__file__).with_name("icon.ico")
            icon = QIcon(
                str(
                    icon_path
                    if icon_path.exists()
                    else Path(__file__).with_name("static") / "icon.svg"
                )
            )
            self.setWindowIcon(icon)
            QApplication.instance().setWindowIcon(icon)
            self.tray = None
            self.notified = False
            self.last_qr = self.last_devices = self.last_pending = None
            self.last_error = ""
            self.quitting = False
            self.update_results = queue.SimpleQueue()
            self.update_busy = False
            self.update_release = self.update_installer = None
            self.update_checked = 0.0
            self.updates_configured = bool(updates.update_key())
            central = QWidget()
            self.setCentralWidget(central)
            outer = QHBoxLayout(central)
            outer.setContentsMargins(0, 0, 0, 0)
            outer.setSpacing(0)
            side = QFrame()
            side.setObjectName("sidebar")
            side.setFixedWidth(190)
            nav = QVBoxLayout(side)
            nav.setContentsMargins(16, 24, 16, 20)
            nav.setSpacing(10)
            brand = QHBoxLayout()
            mark = label("")
            mark.setPixmap(icon.pixmap(28, 28))
            brand.addWidget(mark)
            brand.addWidget(label("deskpad", "brand"), 1)
            nav.addLayout(brand)
            nav.addSpacing(26)
            self.pages = QStackedWidget()
            self.nav = []
            for index, text in enumerate(("Overview", "Devices", "Settings")):
                item = button(text, lambda checked=False, i=index: self.navigate(i), "nav")
                item.setCheckable(True)
                nav.addWidget(item)
                self.nav.append(item)
            nav.addStretch()
            nav.addWidget(label(f"Deskpad {updates.VERSION}", "muted"))
            outer.addWidget(side)
            outer.addWidget(self.pages, 1)
            self.overview()
            self.devices_page()
            self.settings_page()
            self.navigate(0)
            if QSystemTrayIcon.isSystemTrayAvailable():
                self.tray = QSystemTrayIcon(icon, self)
                menu = QMenu()
                for text, callback in (
                    ("Open Deskpad", self.reveal),
                    ("End phone session", lambda: service.command("disconnect")),
                    ("Pause / resume connections", self.pause),
                    ("Quit Deskpad", self.quit),
                ):
                    action = QAction(text, self)
                    action.triggered.connect(callback)
                    menu.addAction(action)
                self.tray.setContextMenu(menu)
                self.tray.activated.connect(
                    lambda reason: (
                        self.reveal()
                        if reason == QSystemTrayIcon.ActivationReason.Trigger
                        else None
                    )
                )
                self.tray.setToolTip("Deskpad")
                self.tray.show()
            self.timer = QTimer(self)
            self.timer.timeout.connect(self.refresh)
            self.timer.start(750)
            self.refresh()

        def page(self):
            body = QWidget()
            layout = QVBoxLayout(body)
            layout.setContentsMargins(30, 25, 30, 22)
            layout.setSpacing(16)
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setWidget(body)
            self.pages.addWidget(scroll)
            return layout

        def overview(self):
            layout = self.page()
            self.title = label("Starting Deskpad…", "title")
            self.status = label("Opening your desktop host", "status")
            heading = QHBoxLayout()
            heading.addWidget(self.title, 1)
            self.pause_button = button("Pause sharing", self.pause)
            heading.addWidget(self.pause_button)
            layout.addLayout(heading)
            layout.addWidget(self.status)
            frame, content = card()
            row = QHBoxLayout()
            self.qr = label("")
            self.qr.setFixedSize(204, 204)
            self.qr.setAlignment(Qt.AlignmentFlag.AlignCenter)
            row.addWidget(self.qr)
            text = QVBoxLayout()
            text.setContentsMargins(20, 0, 0, 0)
            text.addWidget(label("Pair your phone", "section"))
            text.addWidget(label("Scan with your phone camera.", wrap=True))
            self.instructions = label("Enter this code on your phone:", "muted", True)
            text.addWidget(self.instructions)
            self.pin = label("…", "code")
            text.addWidget(self.pin)
            text.addStretch()
            row.addLayout(text, 1)
            content.addLayout(row)
            self.address = label("", "muted", True)
            self.address.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            content.addWidget(self.address)
            qr_actions = QHBoxLayout()
            self.qr_timer = label("", "muted")
            qr_actions.addWidget(self.qr_timer, 1)
            qr_actions.addWidget(button("↻ Refresh QR", lambda: service.command("new-invite")))
            content.addLayout(qr_actions)
            row = QHBoxLayout()
            row.setContentsMargins(0, 6, 0, 0)
            row.addWidget(label("Access", "muted"))
            row.addStretch()
            self.local = button("Local only", lambda: self.remote_mode(False))
            self.anywhere = button("Anywhere", lambda: self.remote_mode(True))
            for item in (self.local, self.anywhere):
                item.setCheckable(True)
                item.setObjectName("access")
                row.addWidget(item)
            content.addLayout(row)
            self.setup_button = button("Finish remote setup", self.finish_setup, "primary")
            self.setup_button.hide()
            content.addWidget(self.setup_button)
            self.remote_status = label("Local only", "muted", True)
            content.addWidget(self.remote_status)
            layout.addWidget(frame)
            self.pending_box, self.pending_layout = card()
            layout.addWidget(self.pending_box)
            self.pending_box.hide()
            layout.addStretch()

        def devices_page(self):
            layout = self.page()
            layout.addWidget(label("Approved devices", "title"))
            layout.addWidget(
                label(
                    "Only approve phones you recognize. Revoking disconnects them immediately.",
                    "muted",
                    True,
                )
            )
            self.device_list = QVBoxLayout()
            layout.addLayout(self.device_list)
            layout.addStretch()

        def settings_page(self):
            layout = self.page()
            layout.addWidget(label("Settings", "title"))
            frame, content = card()
            form = QFormLayout()
            self.name = QLineEdit(settings.name)
            self.url = QLineEdit(settings.service_url)
            self.url.setPlaceholderText("https://your-deskpad.workers.dev")
            self.monitor = QSpinBox()
            self.monitor.setRange(1, 32)
            self.monitor.setValue(settings.monitor)
            self.width = QComboBox()
            self.width.addItems(["960", "1280", "1440", "1920"])
            self.width.setCurrentText(str(settings.width))
            self.fps = QComboBox()
            self.fps.addItems(["20", "30", "60"])
            self.fps.setCurrentText(str(settings.fps))
            for text, field in (
                ("Laptop name", self.name),
                ("Remote service", self.url),
                ("Monitor", self.monitor),
                ("Stream width", self.width),
                ("Target FPS", self.fps),
            ):
                form.addRow(text, field)
            content.addLayout(form)
            self.awake = QCheckBox("Keep laptop awake while a phone is connected")
            self.awake.setChecked(settings.keep_awake)
            self.login = QCheckBox("Launch Deskpad on start")
            self.login.setChecked(settings.launch_at_login)
            content.addWidget(self.awake)
            content.addWidget(self.login)
            content.addWidget(
                label("Opens Deskpad automatically when you sign in to Windows.", "muted", True)
            )
            layout.addWidget(frame)
            frame, content = card()
            content.addWidget(label("Phone camera & audio", "section"))
            content.addWidget(
                label(
                    "Enable a feature here and save. Then turn it on from your phone's menu.",
                    "muted",
                    True,
                )
            )
            self.media_labels = {}
            self.media_details = {}
            self.media_buttons = {}
            self.media_setup_seen = None
            self.media_outputs_seen = None
            self.camera = QCheckBox("Use phone as a webcam")
            self.mic = QCheckBox("Use phone as a microphone")
            self.speakers = QCheckBox("Hear laptop audio on phone")
            self.media_fields = {
                "camera": self.camera,
                "microphone": self.mic,
                "speakers": self.speakers,
            }
            self.mic_device = QComboBox()
            self.mic_device.addItem("Select a virtual microphone cable…", None)
            self.mic_device.setAccessibleName("Virtual microphone cable")
            for name, field in self.media_fields.items():
                feature = QVBoxLayout()
                feature.setSpacing(7)
                row = QHBoxLayout()
                field.setChecked(getattr(settings, name))
                field.setEnabled(False)
                row.addWidget(field, 1)
                status = label("Checking setup…", "muted")
                row.addWidget(status)
                self.media_labels[name] = status
                feature.addLayout(row)
                detail = label("Checking your Windows devices.", "muted", True)
                self.media_details[name] = detail
                feature.addWidget(detail)
                if name == "microphone":
                    feature.addWidget(self.mic_device)
                action = button(
                    "Setup & instructions", lambda checked=False, n=name: self.media_guide(n)
                )
                self.media_buttons[name] = action
                feature.addWidget(action, 0, Qt.AlignmentFlag.AlignLeft)
                content.addLayout(feature)
                field.toggled.connect(self.refresh_media_status)
            self.mic_device.currentIndexChanged.connect(self.refresh_media_status)
            self.media_refresh = button("Refresh devices", lambda: service.command("refresh-media"))
            content.addWidget(self.media_refresh, 0, Qt.AlignmentFlag.AlignLeft)
            layout.addWidget(frame)
            layout.addWidget(button("Save settings", self.save_settings, "primary"))
            self.save_note = label("", "muted", True)
            layout.addWidget(self.save_note)
            frame, content = card()
            content.addWidget(label("App updates", "section"))
            content.addWidget(label(f"Installed: {updates.VERSION}", "muted"))
            self.auto_update = QCheckBox("Check for updates automatically")
            self.auto_update.setChecked(settings.check_updates)
            self.auto_update.toggled.connect(self.update_preference)
            content.addWidget(self.auto_update)
            self.update_note = label(
                "Updates install only when you choose. Pairing and settings are kept.",
                "muted",
                True,
            )
            content.addWidget(self.update_note)
            self.update_notes = label("", "muted", True)
            self.update_notes.hide()
            content.addWidget(self.update_notes)
            row = QHBoxLayout()
            self.check_button = button("Check for updates", self.check_updates)
            self.install_button = button("Download update", self.install_update, "primary")
            self.install_button.hide()
            row.addWidget(self.check_button)
            row.addWidget(self.install_button)
            content.addLayout(row)
            layout.addWidget(frame)
            layout.addStretch()
            self.update_timer = QTimer(self)
            self.update_timer.timeout.connect(self.poll_updates)
            self.update_timer.start(250)

        def media_guide(self, name):
            titles = {
                "camera": "Phone as a webcam",
                "microphone": "Phone as a microphone",
                "speakers": "Laptop audio on your phone",
            }
            setup = service.snapshot().get("media_setup") or {}
            device = setup.get("camera", {}).get("device") or "OBS Virtual Camera"
            steps = {
                "camera": [
                    "One-time setup: install OBS Studio with its virtual camera component, then return here and Refresh devices. Skip this if a supported camera is already detected.",
                    "Enable Use phone as a webcam in Deskpad and Save settings.",
                    "Connect your phone using Anywhere mode for a secure link. Open its Deskpad menu and turn on Use phone camera. Allow camera access when your phone asks.",
                    f"In Zoom on this laptop, choose {device} as your camera. Deskpad supplies the picture directly; leave OBS's Start Virtual Camera off.",
                ],
                "microphone": [
                    "One-time setup: install VB-CABLE from VB-Audio and follow its restart instructions. Quit Deskpad from its system tray menu and reopen it after installation so Windows can report the new audio device.",
                    "Choose the detected virtual cable in Deskpad, enable Use phone as a microphone, and Save settings. Ordinary speakers are excluded from this list.",
                    "Connect your phone using Anywhere mode for a secure link. Open its Deskpad menu and turn on Use phone microphone. Allow microphone access when your phone asks.",
                    "In Zoom on this laptop, choose CABLE Output (VB-Audio Virtual Cable) as your microphone. For CABLE-A/B, choose the matching Output.",
                ],
                "speakers": [
                    "No extra virtual device is needed. Make sure Windows has a sound output selected.",
                    "Enable Hear laptop audio on phone and Save settings.",
                    "Connect your phone. Open its Deskpad menu and turn on Hear laptop audio. Your iPhone may require a tap to begin playback.",
                    "This sends laptop sound to your phone; it does not select a microphone or camera for Zoom. Use headphones if a call feeds sound back into your microphone.",
                ],
            }
            dialog = QDialog(self)
            dialog.setWindowTitle(titles[name])
            dialog.setMinimumWidth(460)
            dialog.setMaximumWidth(560)
            body = QVBoxLayout(dialog)
            body.setContentsMargins(24, 22, 24, 22)
            body.setSpacing(16)
            body.addWidget(label(titles[name], "section"))
            for index, step in enumerate(steps[name], 1):
                body.addWidget(label(f"{index}. {step}", wrap=True))
            if name in ("camera", "microphone"):
                import webbrowser

                url = CAMERA_URL if name == "camera" else MICROPHONE_URL
                body.addWidget(button("Open official download page", lambda: webbrowser.open(url)))
                body.addWidget(
                    label(
                        "Deskpad does not install third-party drivers automatically.", "muted", True
                    )
                )
            row = QHBoxLayout()

            def recheck():
                service.command("refresh-media")
                dialog.accept()

            row.addWidget(button("Check setup again", recheck, "primary"))
            row.addWidget(button("Done", dialog.accept))
            body.addLayout(row)
            dialog.exec()

        def refresh_media_status(self):
            snapshot = service.snapshot()
            setup = snapshot.get("media_setup")
            scanning = snapshot.get("media_scanning", False)
            self.media_refresh.setEnabled(not scanning)
            self.media_refresh.setText("Checking devices…" if scanning else "Refresh devices")
            if setup:
                outputs = setup["outputs"]
                if outputs != self.media_outputs_seen:
                    self.media_outputs_seen = outputs
                    current = self.mic_device.currentData()
                    self.mic_device.blockSignals(True)
                    self.mic_device.clear()
                    self.mic_device.addItem("Select a virtual microphone cable…", None)
                    for item in outputs:
                        self.mic_device.addItem(item["name"], item["id"])
                    selected = self.mic_device.findData(
                        current if current is not None else settings.microphone_output
                    )
                    if (
                        selected < 1
                        and len(outputs) == 1
                        and (
                            settings.microphone_output is None
                            or supported_cable(settings.microphone_output_name)
                        )
                    ):
                        selected = 1
                    self.mic_device.setCurrentIndex(max(0, selected))
                    self.mic_device.blockSignals(False)
            self.mic_device.setVisible(bool(setup and setup["outputs"]))
            self.mic_device.setEnabled(bool(setup and setup["outputs"]) and not scanning)
            for name, field in self.media_fields.items():
                info = (
                    setup[name]
                    if setup
                    else {
                        "ready": False,
                        "state": "Checking setup…",
                        "detail": "Checking your Windows devices.",
                    }
                )
                ready = info["ready"]
                if name == "microphone":
                    ready = ready and self.mic_device.currentData() is not None
                field.setEnabled(ready and not scanning)
                # Missing prerequisites cannot be represented as an enabled feature.
                if setup and not ready and field.isChecked():
                    field.blockSignals(True)
                    field.setChecked(False)
                    field.blockSignals(False)
                state, detail = info["state"], info["detail"]
                if name == "microphone" and info["ready"] and not ready:
                    state, detail = (
                        "Choose a cable",
                        "Select the virtual cable below, then enable and save.",
                    )
                elif ready:
                    pending_cable = (
                        name == "microphone"
                        and field.isChecked()
                        and (
                            self.mic_device.currentData() != settings.microphone_output
                            or self.mic_device.currentText() != settings.microphone_output_name
                        )
                    )
                    if field.isChecked() != getattr(settings, name) or pending_cable:
                        state = "Save to enable" if field.isChecked() else "Save to turn off"
                    elif field.isChecked():
                        activity = snapshot["media_activity"].get(name, {})
                        state = activity.get("state", "Idle")
                        if state == "Idle":
                            state = "Enabled on laptop"
                            detail = "Turn it on in your phone's Deskpad menu. " + detail
                        elif activity.get("error"):
                            detail = activity["error"]
                    else:
                        state = "Ready to enable"
                if scanning:
                    state = "Checking…"
                self.media_labels[name].setText(state)
                self.media_details[name].setText(detail)
                self.media_buttons[name].setText("How to use" if ready else "Set up")

        def update_preference(self, enabled):
            settings.check_updates = enabled
            settings.save(directory / "settings.json")

        def update_job(self, kind, operation):
            self.update_busy = True
            self.check_button.setEnabled(False)
            self.install_button.setEnabled(False)

            def run():
                try:
                    self.update_results.put((kind, operation()))
                except Exception as error:
                    # Do not display remote response bodies or signed payloads.
                    message = (
                        str(error)
                        if isinstance(error, ValueError)
                        else "Could not reach the update service. Try again later."
                    )
                    self.update_results.put(("error", message))

            threading.Thread(target=run, name="deskpad-updates", daemon=True).start()

        def check_updates(self):
            if self.update_busy:
                return
            self.update_checked = time.monotonic()
            self.update_note.setText("Checking for updates…")
            self.update_job("checked", updates.check_update)

        def install_update(self):
            if self.update_busy or not self.update_release:
                return
            if not updates.can_install():
                self.update_note.setText(
                    "This is a portable or source build. Install Deskpad with the Windows installer to enable in-app updates."
                )
                return
            if self.update_installer:
                if service.snapshot()["connected"]:
                    self.update_note.setText(
                        "Disconnect your phone before restarting to install the update."
                    )
                    return
                answer = QMessageBox.question(
                    self,
                    "Update Deskpad",
                    "Restart Deskpad and install this update? Your settings and paired phones will be kept.",
                )
                if answer != QMessageBox.StandardButton.Yes:
                    return
                try:
                    updates.launch_installer(self.update_installer, self.update_release)
                except Exception as error:
                    self.update_note.setText(
                        str(error)
                        if isinstance(error, ValueError)
                        else "Could not start the update installer. Your app is still open."
                    )
                    self.update_installer = None
                    self.install_button.setText("Download update")
                    return
                self.quit()
                return
            self.update_note.setText("Downloading update…")
            release = self.update_release
            self.update_job(
                "downloaded",
                lambda: updates.download_update(
                    release,
                    directory / "updates",
                    lambda percent: self.update_results.put(("progress", percent)),
                ),
            )

        def poll_updates(self):
            if (
                settings.check_updates
                and self.updates_configured
                and not self.update_busy
                and (not self.update_checked or time.monotonic() - self.update_checked >= 86400)
            ):
                self.check_updates()
            while not self.update_results.empty():
                kind, value = self.update_results.get()
                if kind == "progress":
                    self.update_note.setText(f"Downloading update… {value}%")
                    continue
                self.update_busy = False
                self.check_button.setEnabled(True)
                self.install_button.setEnabled(True)
                if kind == "error":
                    self.update_note.setText(value)
                elif kind == "checked":
                    self.update_release = value
                    self.update_installer = None
                    self.install_button.setText("Download update")
                    self.install_button.setVisible(value is not None)
                    self.update_notes.setVisible(value is not None)
                    self.update_notes.setText(value.notes if value else "")
                    self.update_note.setText(
                        f"Deskpad {value.version} is available." if value else "You're up to date."
                    )
                    if value and self.tray:
                        self.tray.showMessage(
                            "Deskpad update available",
                            f"Version {value.version} is ready. Open Settings → App updates to install.",
                        )
                elif kind == "downloaded":
                    self.update_installer = value
                    self.install_button.setText("Restart & install")
                    self.update_note.setText("Download verified. Ready when you are.")

        def navigate(self, index):
            self.pages.setCurrentIndex(index)
            for i, item in enumerate(self.nav):
                item.setChecked(i == index)

        def remote_mode(self, enabled):
            if enabled and not settings.service_url:
                self.navigate(2)
                self.save_note.setText(
                    "Remote access needs a deployed service URL. It is not live yet."
                )
                return
            settings.remote = enabled
            settings.save(directory / "settings.json")
            service.command("remote", enabled)

        def finish_setup(self):
            import webbrowser

            url = service.snapshot().get("setup_url", "")
            if url:
                webbrowser.open(url)

        def save_settings(self):
            try:
                changes = Settings(
                    **{
                        **settings.model_dump(),
                        "name": self.name.text().strip(),
                        "service_url": self.url.text().strip(),
                        "monitor": self.monitor.value(),
                        "width": int(self.width.currentText()),
                        "fps": int(self.fps.currentText()),
                        "keep_awake": self.awake.isChecked(),
                        "launch_at_login": self.login.isChecked(),
                        "camera": self.camera.isChecked(),
                        "microphone": self.mic.isChecked(),
                        "speakers": self.speakers.isChecked(),
                        "microphone_output": self.mic_device.currentData(),
                        "microphone_output_name": self.mic_device.currentText()
                        if self.mic_device.currentData() is not None
                        else "",
                    }
                )
                if changes.microphone and changes.microphone_output is None:
                    raise ValueError(
                        "Choose a virtual microphone cable first, or turn off phone microphone."
                    )
                set_startup(changes.launch_at_login)
                changes.save(directory / "settings.json")
                service.command("settings", changes.model_dump())
                self.save_note.setText(
                    "Saved. Media permission changes reconnect your phone. Then enable the feature in your phone's Deskpad menu."
                )
            except Exception as error:
                QMessageBox.warning(self, "Could not save settings", str(error))

        def pause(self):
            service.command("pause", not service.snapshot()["paused"])

        def clear_layout(self, layout):
            while layout.count():
                item = layout.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()

        def refresh(self):
            snapshot = service.snapshot()
            self.refresh_media_status()
            paused, connected = snapshot["paused"], snapshot["connected"]
            self.title.setText(
                "Connections paused"
                if paused
                else "Phone connected"
                if connected
                else "Ready to connect"
                if snapshot["running"]
                else "Host stopped"
            )
            self.status.setText(
                "Resume when you’re ready"
                if paused
                else settings.name
                + (" · sharing your desktop" if connected else " · your laptop is online")
            )
            self.pause_button.setText("Resume sharing" if paused else "Pause sharing")
            self.local.setChecked(not settings.remote)
            self.anywhere.setChecked(settings.remote)
            self.remote_status.setText(snapshot["remote_status"])
            self.remote_status.setVisible(
                settings.remote
                and snapshot["remote_status"] not in ("Available anywhere", "Local only")
            )
            remaining = max(0, int(snapshot.get("invite_until", 0) - time.time()))
            self.qr_timer.setText(
                f"Refreshes in {remaining // 60:02d}:{remaining % 60:02d}"
                if settings.remote and snapshot.get("remote_url")
                else ""
            )
            self.setup_button.setVisible(bool(snapshot.get("setup_url")))
            url = snapshot.get("remote_url", "") if settings.remote else snapshot["url"]
            if url != self.last_qr:
                self.last_qr = url
                if url:
                    ratio = self.qr.devicePixelRatioF()
                    image = pairing_qr(url, 204 * ratio)
                    output = io.BytesIO()
                    image.save(output, format="PNG")
                    pixmap = QPixmap()
                    pixmap.loadFromData(output.getvalue())
                    pixmap.setDevicePixelRatio(ratio)
                    self.qr.setPixmap(pixmap)
                else:
                    self.qr.clear()
                    self.qr.setText("Connecting…")
            self.address.setText(settings.service_url if settings.remote else snapshot["url"])
            self.instructions.setText(
                "Approve the matching code on this laptop."
                if settings.remote
                else "Enter this code on your phone:"
            )
            self.pin.setText("" if settings.remote else snapshot["pin"])
            pending = snapshot["pending"]
            if pending != self.last_pending:
                self.last_pending = pending
                self.clear_layout(self.pending_layout)
                self.pending_box.setVisible(bool(pending))
                for entry in pending:
                    self.pending_layout.addWidget(label(f"Pair {entry['name']}?", "section"))
                    self.pending_layout.addWidget(
                        label(f"Verify this code on your phone: {entry['code']}", "status")
                    )
                    row = QWidget()
                    buttons = QHBoxLayout(row)
                    buttons.addWidget(
                        button(
                            "Approve",
                            lambda checked=False, i=entry["id"]: service.command("approve", i),
                            "primary",
                        )
                    )
                    buttons.addWidget(
                        button(
                            "Reject",
                            lambda checked=False, i=entry["id"]: service.command("reject", i),
                        )
                    )
                    self.pending_layout.addWidget(row)
            devices = (snapshot["devices"], snapshot.get("local_devices", []))
            if devices != self.last_devices:
                self.last_devices = devices
                self.clear_layout(self.device_list)
                for entry in devices[0]:
                    frame, content = card()
                    content.addWidget(label(entry["name"], "section"))
                    content.addWidget(label("Approved for remote access", "muted"))
                    content.addWidget(
                        button(
                            "Revoke access",
                            lambda checked=False, i=entry["id"]: service.command("revoke", i),
                        )
                    )
                    self.device_list.addWidget(frame)
                for index, identifier in enumerate(devices[1], 1):
                    frame, content = card()
                    content.addWidget(label(f"Local phone {index}", "section"))
                    content.addWidget(
                        button(
                            "Revoke local access",
                            lambda checked=False, i=identifier: service.command("revoke-local", i),
                        )
                    )
                    self.device_list.addWidget(frame)
                if not any(devices):
                    self.device_list.addWidget(label("No approved phones yet.", "muted"))
            if snapshot["error"]:
                self.status.setText(snapshot["error"])
            if os.name == "nt":
                import ctypes

                ctypes.windll.kernel32.SetThreadExecutionState(
                    0x80000000 | (3 if connected and settings.keep_awake else 0)
                )

        def reveal(self):
            self.showNormal()
            self.raise_()
            self.activateWindow()

        def closeEvent(self, event):
            if self.tray and not self.quitting:
                event.ignore()
                self.hide()
                if not self.notified:
                    self.tray.showMessage(
                        "Deskpad is still running",
                        "Open Deskpad from the tray, or choose Quit to stop sharing.",
                    )
                    self.notified = True
            else:
                self.quit()
                event.accept()

        def quit(self):
            self.quitting = True
            self.timer.stop()
            if self.tray:
                self.tray.hide()
            engine.stop()
            QApplication.instance().quit()

    return Window()


def main():
    parser = argparse.ArgumentParser(description="Deskpad desktop companion")
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--screenshot", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    enable_dpi_awareness()
    directory = state_directory()
    directory.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(filename=directory / "deskpad.log", level=logging.WARNING)
    from PySide6.QtCore import QTimer
    from PySide6.QtNetwork import QLocalServer, QLocalSocket
    from PySide6.QtWidgets import QApplication, QMessageBox

    if os.name == "nt":
        import ctypes

        set_app_id = ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID
        set_app_id.argtypes = [ctypes.c_wchar_p]
        set_app_id.restype = ctypes.c_long
        set_app_id("Deskpad.Desktop")
    app = QApplication(sys.argv[:1])
    app.setApplicationName("Deskpad")
    app.setStyle("Fusion")
    app.setStyleSheet(STYLE)
    singleton = QLocalServer()
    singleton.setSocketOptions(QLocalServer.SocketOption.UserAccessOption)
    socket = QLocalSocket()
    import hashlib

    socket_name = "deskpad-" + hashlib.sha256(str(directory).encode()).hexdigest()[:16]
    socket.connectToServer(socket_name)
    if socket.waitForConnected(300):
        socket.write(b"open")
        socket.waitForBytesWritten(300)
        return
    QLocalServer.removeServer(socket_name)
    if not args.screenshot and not singleton.listen(socket_name):
        QMessageBox.critical(None, "Deskpad", "Could not open the desktop application lock.")
        return
    try:
        settings = Settings.load(directory / "settings.json")
    except Exception:
        QMessageBox.critical(
            None,
            "Deskpad",
            "Settings could not be read. Restore settings.json or remove it to reset settings.",
        )
        return
    service = Service()
    engine = Engine(settings, service, directory, args.demo)
    window = build_window(settings, service, directory, engine)

    def reveal():
        while singleton.hasPendingConnections():
            connection = singleton.nextPendingConnection()
            connection.close()
        window.reveal()

    singleton.newConnection.connect(reveal)
    window.show()
    from .window_icon import set_native_icon

    try:
        set_native_icon(window)
    except OSError:
        logging.warning("Native window icon could not be loaded")
    engine.start()
    app.aboutToQuit.connect(engine.stop)
    if args.screenshot:

        def capture():
            from .window_icon import verify_native_icon

            try:
                verify_native_icon(window)
                window.grab().save(str(args.screenshot))
            finally:
                window.quit()

        QTimer.singleShot(2500, capture)
    app.exec()


if __name__ == "__main__":
    main()
