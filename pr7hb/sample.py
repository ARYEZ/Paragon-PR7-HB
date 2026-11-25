"""Real test videos made here, in pure Python (no downloads, no FFmpeg): tests, the self-test and screenshots.

clip(): a Motion-JPEG AVI (PR7-M's writer: each second its own colour, every frame numbered, Qt draws the JPEGs) with,
when `audio` is on, a second stream of 16-bit PCM stereo (a tone), interleaved per frame as AVI players expect.
HandBrake (libavformat) reads it like any camera AVI."""
from __future__ import annotations

import math
import struct
from pathlib import Path

COLOURS = ["#C2183F", "#E2502A", "#F07A2A", "#7A2230", "#D83A6A", "#FFB070"]


def colour_of(frame: int, fps: int) -> str:
    return COLOURS[(frame // fps) % len(COLOURS)]


def _jpeg(index: int, fps: int, size: tuple[int, int]) -> bytes:
    from PySide6.QtCore import QBuffer, QIODevice, QRectF, Qt
    from PySide6.QtGui import QColor, QFont, QImage, QPainter
    img = QImage(size[0], size[1], QImage.Format.Format_RGB32)
    img.fill(QColor(colour_of(index, fps)))
    p = QPainter(img)
    f = QFont()
    f.setPixelSize(size[1] // 3)
    f.setBold(True)
    p.setFont(f)
    p.setPen(QColor("#FFFFFF"))
    p.drawText(QRectF(0, 0, size[0], size[1]), Qt.AlignmentFlag.AlignCenter, str(index))
    p.end()
    buf = QBuffer()
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    img.save(buf, "JPG", 85)
    return bytes(buf.data())


def _chunk(fourcc: bytes, data: bytes) -> bytes:
    return fourcc + struct.pack("<I", len(data)) + data + (b"\0" if len(data) % 2 else b"")


def _list(kind: bytes, data: bytes) -> bytes:
    return b"LIST" + struct.pack("<I", len(data) + 4) + kind + data


def clip(path: Path, seconds: float = 3.0, fps: int = 10, size: tuple[int, int] = (320, 180), audio: bool = True,
         rate: int = 22050) -> Path:
    count = int(seconds * fps)
    frames = [_jpeg(i, fps, size) for i in range(count)]
    per = rate // fps                                     # audio samples per video frame
    sound = []
    for n in range(count):
        block = bytearray()
        for i in range(n * per, (n + 1) * per):
            v = int(9000 * math.sin(2 * math.pi * 440 * i / rate))
            block += struct.pack("<hh", v, v)
        sound.append(bytes(block))
    w, h = size
    biggest = max(len(f) for f in frames)
    streams = 2 if audio else 1
    avih = struct.pack("<10I4I", 1_000_000 // fps, (biggest + per * 4) * fps, 0, 0x10, count, 0, streams,
                       biggest, w, h, 0, 0, 0, 0)
    vstrh = b"vids" + b"MJPG" + struct.pack("<IHHIIIIIIiI4h", 0, 0, 0, 0, 1, fps, 0, count, biggest, -1, 0, 0, 0, w, h)
    vstrf = struct.pack("<IiiHH4sIiiII", 40, w, h, 1, 24, b"MJPG", w * h * 3, 0, 0, 0, 0)
    strls = _list(b"strl", _chunk(b"strh", vstrh) + _chunk(b"strf", vstrf))
    if audio:
        astrh = b"auds" + b"\0\0\0\0" + struct.pack("<IHHIIIIIIiI4h", 0, 0, 0, 0, 1, rate, 0, count * per, per * 4,
                                                     -1, 4, 0, 0, 0, 0)
        astrf = struct.pack("<HHIIHH", 1, 2, rate, rate * 4, 4, 16)
        strls += _list(b"strl", _chunk(b"strh", astrh) + _chunk(b"strf", astrf))
    hdrl = _list(b"hdrl", _chunk(b"avih", avih) + strls)
    movi, index, offset = bytearray(), bytearray(), 4
    for n, f in enumerate(frames):
        for fourcc, data in ((b"00dc", f), (b"01wb", sound[n])) if audio else ((b"00dc", f),):
            c = _chunk(fourcc, data)
            index += fourcc + struct.pack("<III", 0x10, offset, len(data))
            movi += c
            offset += len(c)
    body = b"AVI " + hdrl + _list(b"movi", bytes(movi)) + _chunk(b"idx1", bytes(index))
    path.write_bytes(b"RIFF" + struct.pack("<I", len(body)) + body)
    return path

