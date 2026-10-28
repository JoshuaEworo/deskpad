"""Pairing QR rasterization without unevenly resampling its module grid."""

import qrcode


def pairing_qr(url, physical_size):
    qr = qrcode.QRCode(box_size=1, border=4)
    qr.add_data(url)
    qr.make(fit=True)
    modules = len(qr.get_matrix())
    pitch = max(1, int(physical_size) // modules)
    qr.box_size = pitch
    return qr.make_image().convert("RGBA")
