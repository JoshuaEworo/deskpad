"""Deskpad desktop shell. Qt stays on the main thread; engine owns its asyncio loop."""

import argparse
import io
import logging
import os
import sys
import threading
from pathlib import Path

import qrcode
import uvicorn

from .cli import local_ip
from .identity import Identity
from .native import enable_dpi_awareness
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
            icon = QIcon(str(Path(__file__).with_name("static") / "icon.svg"))
            self.setWindowIcon(icon)
            self.tray = None
            self.notified = False
            self.last_qr = self.last_devices = self.last_pending = None
            self.last_error = ""
            self.quitting = False
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
            nav.addWidget(label("▣  deskpad", "brand"))
            nav.addSpacing(26)
            self.pages = QStackedWidget()
            self.nav = []
            for index, text in enumerate(("Overview", "Devices", "Settings")):
                item = button(text, lambda checked=False, i=index: self.navigate(i), "nav")
                item.setCheckable(True)
                nav.addWidget(item)
                self.nav.append(item)
            nav.addStretch()
            nav.addWidget(label("Deskpad Alpha · 0.2", "muted"))
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
                    ("Disconnect phone", lambda: service.command("disconnect")),
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
            layout.addWidget(self.title)
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
            content.addWidget(button("Refresh pairing QR", lambda: service.command("new-invite")))
            layout.addWidget(frame)
            frame, content = card()
            content.addWidget(label("Connection access", "section"))
            row = QHBoxLayout()
            self.local = button("Local only", lambda: self.remote_mode(False))
            self.anywhere = button("Anywhere", lambda: self.remote_mode(True))
            for item in (self.local, self.anywhere):
                item.setCheckable(True)
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
            row = QHBoxLayout()
            row.addWidget(label("Runs quietly in your system tray.", "muted"))
            self.pause_button = button("Pause connections", self.pause)
            row.addWidget(self.pause_button)
            layout.addLayout(row)

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
            self.login = QCheckBox("Launch Deskpad when I sign in")
            self.login.setChecked(settings.launch_at_login)
            content.addWidget(self.awake)
            content.addWidget(self.login)
            layout.addWidget(frame)
            frame, content = card()
            content.addWidget(label("Phone camera & audio", "section"))
            content.addWidget(
                label(
                    "Allow each feature here, then turn it on from your phone. Camera and microphone need installed virtual devices; they are not bundled Deskpad drivers yet.",
                    "muted",
                    True,
                )
            )
            self.camera = QCheckBox("Allow phone camera → installed virtual camera")
            self.camera.setChecked(settings.camera)
            self.mic = QCheckBox("Allow phone microphone → selected virtual audio output")
            self.mic.setChecked(settings.microphone)
            self.speakers = QCheckBox("Allow laptop audio → phone speaker")
            self.speakers.setChecked(settings.speakers)
            for field in (self.camera, self.mic, self.speakers):
                content.addWidget(field)
            self.mic_device = QComboBox()
            self.mic_device.addItem("Select a virtual audio cable output…", None)
            try:
                import sounddevice as sd

                for index, device in enumerate(sd.query_devices()):
                    if device["max_output_channels"] >= 2:
                        self.mic_device.addItem(str(device["name"]), index)
            except Exception:
                pass
            chosen = self.mic_device.findData(settings.microphone_output)
            self.mic_device.setCurrentIndex(max(0, chosen))
            content.addWidget(self.mic_device)
            content.addWidget(
                label(
                    "Select the cable's recording endpoint in Zoom. Do not select physical speakers here, or your microphone will play aloud.",
                    "muted",
                    True,
                )
            )
            layout.addWidget(frame)
            layout.addWidget(button("Save settings", self.save_settings, "primary"))
            self.save_note = label("", "muted", True)
            layout.addWidget(self.save_note)
            layout.addStretch()

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
                set_startup(changes.launch_at_login)
                changes.save(directory / "settings.json")
                service.command("settings", changes.model_dump())
                self.save_note.setText(
                    "Saved. New stream settings apply to subsequent frames; device changes apply on reconnect."
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
            self.pause_button.setText("Resume connections" if paused else "Pause connections")
            self.local.setChecked(not settings.remote)
            self.anywhere.setChecked(settings.remote)
            self.remote_status.setText(snapshot["remote_status"])
            self.setup_button.setVisible(bool(snapshot.get("setup_url")))
            url = snapshot.get("remote_url", "") if settings.remote else snapshot["url"]
            if url != self.last_qr:
                self.last_qr = url
                if url:
                    image = qrcode.make(url, box_size=6, border=3)
                    output = io.BytesIO()
                    image.save(output, format="PNG")
                    pixmap = QPixmap()
                    pixmap.loadFromData(output.getvalue())
                    self.qr.setPixmap(
                        pixmap.scaled(
                            204,
                            204,
                            Qt.AspectRatioMode.KeepAspectRatio,
                            Qt.TransformationMode.FastTransformation,
                        )
                    )
                else:
                    self.qr.clear()
                    self.qr.setText("Connecting…")
            self.address.setText(settings.service_url if settings.remote else snapshot["url"])
            self.instructions.setText(
                "Approve the matching code on this laptop.\nQR expires after 10 minutes."
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
    engine.start()
    app.aboutToQuit.connect(engine.stop)
    if args.screenshot:

        def capture():
            window.grab().save(str(args.screenshot))
            window.quit()

        QTimer.singleShot(2500, capture)
    app.exec()


if __name__ == "__main__":
    main()
