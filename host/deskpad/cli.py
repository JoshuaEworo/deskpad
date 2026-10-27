import argparse
import os
import socket
from pathlib import Path

import qrcode
import uvicorn

from .native import enable_dpi_awareness
from .server import create_app


def local_ip():
    # UDP connect selects the route without transmitting a packet.
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
        try:
            probe.connect(("192.0.2.1", 80))
            return probe.getsockname()[0]
        except OSError:
            return "127.0.0.1"


def main():
    parser = argparse.ArgumentParser(description="Deskpad: your desktop above, controls below")
    parser.add_argument("--demo", action="store_true", help="Synthetic desktop, no real input")
    parser.add_argument(
        "--bind", default="0.0.0.0", help="Listen address (default: all IPv4 interfaces)"
    )
    parser.add_argument("--advertise", help="Laptop's LAN IPv4 address shown in the QR code")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--monitor", type=int, default=1, help="MSS display index, starting at 1")
    parser.add_argument("--fps", type=int, default=20, choices=range(5, 31), metavar="5-30")
    parser.add_argument("--width", type=int, default=1440, choices=(960, 1280, 1440, 1920))
    parser.add_argument("--quality", type=int, default=75, choices=range(40, 91), metavar="40-90")
    parser.add_argument(
        "--forget-devices", action="store_true", help="Revoke all remembered phones"
    )
    args = parser.parse_args()
    enable_dpi_awareness()
    state = (
        Path(os.environ.get("LOCALAPPDATA", Path.home() / ".local" / "share"))
        / "Deskpad"
        / "devices.json"
    )
    if args.forget_devices:
        state.unlink(missing_ok=True)
        print("Remembered phones removed.")
        return
    if not Path(__file__).with_name("static").joinpath("index.html").exists():
        parser.error("Phone UI missing. Run npm ci && npm run build in web/ first.")
    ip = args.advertise or (args.bind if args.bind != "0.0.0.0" else local_ip())
    origins = list({f"http://{host}:{args.port}" for host in (ip, "localhost", "127.0.0.1")})
    app = create_app(
        state_path=state,
        origins=origins,
        demo=args.demo,
        monitor=args.monitor,
        fps=args.fps,
        width=args.width,
        quality=args.quality,
    )
    url = f"http://{ip}:{args.port}"
    print(f"\nDeskpad {'DEMO' if args.demo else 'WINDOWS HOST'}\nOpen {url}\n")
    qr = qrcode.QRCode(border=1)
    qr.add_data(url)
    qr.print_ascii(invert=True)
    print(f"\nPairing code: {app.state.pairing.pin}\n")
    print("Use a trusted home Wi-Fi network. Keep this window open. Ctrl+C stops sharing.\n")
    uvicorn.run(app, host=args.bind, port=args.port, ws_max_size=16384, access_log=False)


if __name__ == "__main__":
    main()
