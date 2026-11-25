"""Preview pictures, as HandBrake's: ten frames spread over the title, the crop shown, and a live preview (a short
encode with the current settings) opened in PR7-M.

HandBrakeCLI can't hand out preview images, so the frames come from Qt Multimedia (FFmpeg) seeking a paused player:
a seek while stopped delivers nothing, so the player is started and paused once first."""

from __future__ import annotations

import time

from PySide6.QtCore import QObject, QRectF, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPen
from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget

from . import engine, theme, widgets

COUNT = 10


class Grabber(QObject):
    """Frames at given times (ms) of a file, one after another; `frame(index, QImage)` for each."""

    frame = Signal(int, QImage)
    finished = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        from PySide6.QtMultimedia import QMediaPlayer, QVideoSink
        self.player = QMediaPlayer(self)
        self.sink = QVideoSink(self)
        self.player.setVideoSink(self.sink)
        self.sink.videoFrameChanged.connect(self._frame)
        self.player.mediaStatusChanged.connect(self._status)
        self.todo: list[tuple[int, int]] = []
        self.current: tuple[int, int] | None = None
        self.ready = False
        self._timeout = QTimer(self)
        self._timeout.setSingleShot(True)
        self._timeout.timeout.connect(self._skip)

    def grab(self, path: str, times_ms: list[int]) -> None:
        self.todo = list(enumerate(times_ms))
        self.current = None
        self.ready = False
        self.player.stop()
        self.player.setSource(QUrl.fromLocalFile(path))

    def stop(self) -> None:
        self.todo = []
        self.current = None
        self._timeout.stop()
        self.player.stop()

    def _status(self, status) -> None:
        from PySide6.QtMultimedia import QMediaPlayer
        if status == QMediaPlayer.MediaStatus.LoadedMedia and not self.ready:
            self.ready = True
            self.player.setAudioOutput(None)
            self.player.play()
            self.player.pause()
            self._next()
        elif status == QMediaPlayer.MediaStatus.InvalidMedia:
            self.todo = []
            self.finished.emit()

    def _next(self) -> None:
        if not self.todo:
            self.current = None
            self.player.stop()
            self.finished.emit()
            return
        self.current = self.todo.pop(0)
        self._timeout.start(4000)
        self.player.setPosition(self.current[1])

    def _frame(self, f) -> None:
        if self.current is None or not f.isValid():
            return
        if abs(f.startTime() // 1000 - self.current[1]) > 1500:        # an older frame still on its way
            return
        img = f.toImage()
        if img.isNull():
            return
        self._timeout.stop()
        idx = self.current[0]
        self.current = None
        self.frame.emit(idx, img.copy())
        QTimer.singleShot(0, self._next)

    def _skip(self) -> None:
        self.current = None
        self._next()

    def wait(self, timeout: float = 20) -> None:
        from PySide6.QtCore import QCoreApplication
        end = time.time() + timeout
        while (self.todo or self.current is not None or not self.ready) and time.time() < end:
            QCoreApplication.processEvents()
            time.sleep(0.01)


def positions(duration: float, count: int = COUNT) -> list[int]:
    """HandBrake's preview spacing: count frames evenly inside the title, never the very first or last frame."""
    return [int(duration * 1000 * (i + 1) / (count + 1)) for i in range(count)]


class Picture(QWidget):
    """One preview frame, fitted, with the crop dimmed and the caption under it."""

    def __init__(self):
        super().__init__()
        self.image: QImage | None = None
        self.crop = (0, 0, 0, 0)
        self.caption = "OPEN A SOURCE TO SEE PREVIEWS"
        self.setMinimumSize(360, 220)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        r = QRectF(self.rect()).adjusted(0, 0, -1, -24)
        p.fillRect(r, QColor("#050406"))
        if self.image is not None and not self.image.isNull():
            iw, ih = self.image.width(), self.image.height()
            k = min(r.width() / iw, r.height() / ih)
            box = QRectF(r.center().x() - iw * k / 2, r.center().y() - ih * k / 2, iw * k, ih * k)
            p.drawImage(box, self.image)
            top, bottom, left, right = self.crop
            shade = QColor(0, 0, 0, 150)
            p.fillRect(QRectF(box.left(), box.top(), box.width(), top * k), shade)
            p.fillRect(QRectF(box.left(), box.bottom() - bottom * k, box.width(), bottom * k), shade)
            p.fillRect(QRectF(box.left(), box.top() + top * k, left * k, box.height() - (top + bottom) * k), shade)
            p.fillRect(QRectF(box.right() - right * k, box.top() + top * k, right * k,
                              box.height() - (top + bottom) * k), shade)
            if any(self.crop):
                p.setPen(QPen(QColor(theme.ACCENT), 1, Qt.PenStyle.DashLine))
                p.drawRect(QRectF(box.left() + left * k, box.top() + top * k, box.width() - (left + right) * k,
                                  box.height() - (top + bottom) * k))
        p.setPen(QPen(QColor(theme.PANEL_EDGE), 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRect(r)
        p.setPen(QColor(theme.TEXT_DIM))
        f = QFont("Inter", 1)
        f.setPixelSize(11)
        f.setWeight(QFont.Weight.DemiBold)
        p.setFont(f)
        p.drawText(QRectF(0, r.bottom() + 5, self.width(), 18), Qt.AlignmentFlag.AlignCenter, self.caption)


class PreviewPanel(QWidget):
    live = Signal(float)              # seconds into the title: encode a short clip from here

    def __init__(self):
        super().__init__()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.picture = Picture()
        lay.addWidget(self.picture, 1)
        keys = QHBoxLayout()
        keys.addStretch(1)
        self.prev = widgets.SmallKey("back", "Previous preview")
        self.play = widgets.SmallKey("play", "Live preview (a 15 s encode with these settings)")
        self.next = widgets.SmallKey("forward", "Next preview")
        for k in (self.prev, self.play, self.next):
            keys.addWidget(k)
        keys.addStretch(1)
        lay.addLayout(keys)
        self.frames: dict[int, QImage] = {}
        self.times: list[int] = []
        self.index = 0
        self.grabber: Grabber | None = None
        self.prev.clicked.connect(lambda: self.show_index(self.index - 1))
        self.next.clicked.connect(lambda: self.show_index(self.index + 1))
        self.play.clicked.connect(lambda: self.live.emit(self.times[self.index] / 1000 if self.times else 0.0))
        self._enable()

    def load(self, title: engine.Title | None) -> None:
        self.frames.clear()
        self.index = COUNT // 2 if title else 0
        if self.grabber is not None:
            self.grabber.stop()
        if title is None:
            self.times = []
            self.picture.image = None
            self.picture.caption = "OPEN A SOURCE TO SEE PREVIEWS"
            self.picture.update()
            self._enable()
            return
        self.times = positions(title.duration)
        self.picture.image = None
        self.picture.caption = "READING PREVIEWS…"
        self.picture.update()
        if self.grabber is None:
            self.grabber = Grabber(self)
            self.grabber.frame.connect(self._got)
        self.grabber.grab(title.path, self.times)
        self._enable()

    def _got(self, idx: int, img: QImage) -> None:
        self.frames[idx] = img
        if idx == self.index or self.picture.image is None:
            self.show_index(self.index)

    def set_crop(self, crop) -> None:
        self.picture.crop = tuple(crop)
        self.picture.update()

    def show_index(self, i: int) -> None:
        if not self.times:
            return
        self.index = max(0, min(len(self.times) - 1, i))
        self.picture.image = self.frames.get(self.index)
        self.picture.caption = f"PREVIEW  ·  {self.index + 1} OF {len(self.times)}  ·  " \
                               f"{engine.hms(self.times[self.index] / 1000)}"
        self.picture.update()
        self._enable()

    def _enable(self) -> None:
        on = bool(self.times)
        self.prev.setEnabled(on and self.index > 0)
        self.next.setEnabled(on and self.index < len(self.times) - 1)
        self.play.setEnabled(on)

