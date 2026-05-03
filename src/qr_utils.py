"""
Generate QR code image from invite link for sharing in Telegram.
"""
import io
from pathlib import Path

import qrcode


def qr_image_bytes(url: str, size: int = 10, border: int = 2) -> bytes:
    """Return PNG bytes for a QR code encoding `url`."""
    qr = qrcode.QRCode(version=1, box_size=size, border=border)
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf.getvalue()
