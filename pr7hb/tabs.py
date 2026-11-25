"""The seven settings tabs, as HandBrake's: Summary, Dimensions, Filters, Video, Audio, Subtitles, Chapters.

Every control reads from and writes into the window's working preset (a HandBrake preset dict), so what the tabs show
is exactly what HandBrakeCLI gets. Audio and subtitle rows are the job's explicit tracks (engine.AudioTrack /
SubtitleTrack), filled from the preset's own track choice when a source is opened or a preset chosen."""

from __future__ import annotations

import os

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QButtonGroup, QCheckBox, QComboBox, QDoubleSpinBox, QGridLayout, QHBoxLayout, QHeaderView, QLabel,
                               QLineEdit, QPushButton, QRadioButton, QSlider, QSpinBox, QTableWidget,
                               QTableWidgetItem, QVBoxLayout, QWidget)

from . import engine

DETELECINE = [("off", "Off"), ("default", "Default")]
COMB = [("off", "Off"), ("default", "Default"), ("permissive", "Permissive"), ("fast", "Fast")]
DEINTERLACE = [("off", "Off"), ("yadif", "Yadif"), ("decomb", "Decomb"), ("bwdif", "Bwdif")]
DEINTERLACE_PRESETS = {"yadif": [("default", "Default"), ("skip-spatial", "Skip spatial check"), ("bob", "Bob")],
                       "decomb": [("default", "Default"), ("bob", "Bob"), ("eedi2", "EEDI2"), ("eedi2bob", "EEDI2 Bob")],
                       "bwdif": [("default", "Default"), ("bob", "Bob")], "off": [("default", "Default")]}
STRENGTHS = [("ultralight", "Ultralight"), ("light", "Light"), ("medium", "Medium"), ("strong", "Strong"),
             ("stronger", "Stronger"), ("verystrong", "Very strong")]
DEBLOCK = [("off", "Off")] + STRENGTHS
DENOISE = [("off", "Off"), ("nlmeans", "NLMeans"), ("hqdn3d", "HQDN3D")]
DENOISE_PRESETS = STRENGTHS[:4]
DENOISE_TUNES = [("none", "None"), ("film", "Film"), ("grain", "Grain"), ("highmotion", "High motion"),
                 ("animation", "Animation"), ("tape", "Tape"), ("sprite", "Sprite")]
CHROMA = [("off", "Off")] + STRENGTHS
SHARPEN = [("off", "Off"), ("unsharp", "Unsharp"), ("lapsharp", "LapSharp")]
SHARPEN_TUNES = {"unsharp": [("none", "None"), ("ultrafine", "Ultrafine"), ("fine", "Fine"), ("medium", "Medium"),
                             ("coarse", "Coarse"), ("verycoarse", "Very coarse")],
                 "lapsharp": [("none", "None"), ("film", "Film"), ("grain", "Grain"), ("animation", "Animation"),
                              ("sprite", "Sprite")], "off": [("none", "None")]}
COLORSPACE = [("off", "Off"), ("bt.2020", "BT.2020"), ("bt.709", "BT.709"), ("bt.601-6-525", "BT.601 SMPTE-C"),
              ("bt.601-6-625", "BT.601 EBU")]
LIMITS = [("0x0", "None"), ("7680x4320", "4320p 8K Ultra HD"), ("3840x2160", "2160p 4K Ultra HD"),
          ("2560x1440", "1440p 2.5K Quad HD"), ("1920x1080", "1080p Full HD"), ("1280x720", "720p HD"),
          ("720x576", "576p PAL SD"), ("720x480", "480p NTSC SD"), ("640x360", "360p")]   # "WxH": Qt keeps strings
ANAMORPHIC = [("off", "Off"), ("auto", "Automatic"), ("loose", "Loose")]
ROTATIONS = [(0, "0°"), (90, "90°"), (180, "180°"), (270, "270°")]


def field(text: str) -> QLabel:
    lab = QLabel(text.upper())
    lab.setProperty("role", "field")
    return lab


def dim(text: str) -> QLabel:
    lab = QLabel(text)
    lab.setProperty("role", "dim")
    return lab


class Choice(QComboBox):
    """A combo of (value, label) pairs; a value the preset holds that isn't listed is added (so it round-trips)."""

    def set_items(self, items, value=None):
        self.blockSignals(True)
        self.clear()
        for v, label in items:
            self.addItem(label, v)
        if value is not None:
            self.set_value(value)
        self.blockSignals(False)

    def set_value(self, value):
        self.blockSignals(True)
        i = self.findData(value)
        if i < 0 and value is not None:
            self.addItem(str(value).capitalize() if isinstance(value, str) else str(value), value)
            i = self.count() - 1
        self.setCurrentIndex(max(0, i))
        self.blockSignals(False)

    def value(self):
        return self.currentData()


class Tab(QWidget):
    """A tab bound to the window's working preset (`win.preset`): `load()` reads it, controls write it back and
    call `win.preset_edited()`."""

    def __init__(self, win):
        super().__init__()
        self.win = win
        self.loading = False

    @property
    def p(self) -> dict:
        return self.win.preset

    def write(self, **values):
        if self.loading:
            return
        self.p.update(values)
        self.win.preset_edited(self)

    def choice(self, key, items) -> Choice:
        c = Choice()
        c.set_items(items)
        c.currentIndexChanged.connect(lambda _=0, k=key, c=c: self.write(**{k: c.value()}))
        return c

    def check(self, key, text) -> QCheckBox:
        b = QCheckBox(text)
        b.toggled.connect(lambda on, k=key: self.write(**{k: on}))
        return b

    def load(self):
        self.loading = True
        try:
            self.fill()
        finally:
            self.loading = False

    def fill(self):
        pass


# --------------------------------------------------------------------------- Summary
class SummaryTab(Tab):
    def __init__(self, win, preview):
        super().__init__(win)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.setSpacing(24)
        left = QVBoxLayout()
        left.setSpacing(8)
        row = QHBoxLayout()
        row.addWidget(field("Format"))
        self.format = self.choice("FileFormat", [(k, v[0]) for k, v in engine.CONTAINERS.items()])
        self.format.setFixedWidth(120)
        row.addWidget(self.format)
        row.addStretch(1)
        left.addLayout(row)
        self.optimize = self.check("Optimize", "Web optimized")
        self.align = self.check("AlignAVStart", "Align A/V start")
        self.meta = self.check("MetadataPassthrough", "Passthru common metadata")
        for w in (self.optimize, self.align, self.meta):
            left.addWidget(w)
        left.addSpacing(10)
        left.addWidget(field("Tracks"))
        self.tracks = QLabel()
        self.tracks.setTextFormat(Qt.TextFormat.PlainText)
        self.tracks.setWordWrap(True)
        left.addWidget(self.tracks)
        left.addSpacing(10)
        left.addWidget(field("Filters"))
        self.filters = QLabel()
        self.filters.setWordWrap(True)
        left.addWidget(self.filters)
        left.addSpacing(10)
        left.addWidget(field("Size"))
        self.size = QLabel("·  open a source")
        left.addWidget(self.size)
        left.addStretch(1)
        lay.addLayout(left, 1)
        lay.addWidget(preview, 1)

    def fill(self):
        p = self.p
        self.format.set_value(p.get("FileFormat", "av_mp4"))
        self.optimize.setChecked(bool(p.get("Optimize")))
        self.align.setChecked(bool(p.get("AlignAVStart")))
        self.meta.setChecked(bool(p.get("MetadataPassthrough", True)))
        mp4 = p.get("FileFormat", "av_mp4") == "av_mp4"
        self.optimize.setEnabled(mp4)
        self.align.setEnabled(mp4)
        self.refresh()

    def refresh(self):
        win = self.win
        lines = engine.summary(self.p, win.audio_tracks, win.subtitle_tracks)
        self.tracks.setText("\n".join("·  " + ln for ln in lines))
        self.filters.setText("\n".join("·  " + ln for ln in filter_summary(self.p)) or "·  None")
        t = win.title
        if t is None:
            self.size.setText("·  open a source")
        else:
            w, h = engine.output_size(self.p, t)
            self.size.setText(f"·  {w} × {h} storage, {display_width(self.p, t, w, h)} × {h} display")


def display_width(p: dict, t: engine.Title, w: int, h: int) -> int:
    if p.get("PicturePAR", "auto") == "off" or not t.par or t.par[0] == t.par[1]:
        return w
    return int(round(w * t.par[0] / t.par[1]))


def filter_summary(p: dict) -> list[str]:
    out = []
    if p.get("PictureDetelecine", "off") != "off":
        out.append("Detelecine")
    if p.get("PictureDeinterlaceFilter", "off") != "off":
        out.append(f"{dict(DEINTERLACE).get(p['PictureDeinterlaceFilter'], p['PictureDeinterlaceFilter'])}, "
                   f"{p.get('PictureDeinterlacePreset', 'default').capitalize()}")
    if p.get("PictureDeblockPreset", "off") != "off":
        out.append(f"Deblock, {p['PictureDeblockPreset'].capitalize()}")
    if p.get("PictureDenoiseFilter", "off") != "off":
        out.append(f"Denoise ({dict(DENOISE).get(p['PictureDenoiseFilter'])}), "
                   f"{p.get('PictureDenoisePreset', 'medium').capitalize()}")
    if p.get("PictureChromaSmoothPreset", "off") != "off":
        out.append(f"Chroma smooth, {p['PictureChromaSmoothPreset'].capitalize()}")
    if p.get("PictureSharpenFilter", "off") != "off":
        out.append(f"Sharpen ({dict(SHARPEN).get(p['PictureSharpenFilter'])}), "
                   f"{p.get('PictureSharpenPreset', 'medium').capitalize()}")
    if p.get("PictureColorspacePreset", "off") != "off":
        out.append(f"Colorspace: {dict(COLORSPACE).get(p['PictureColorspacePreset'], p['PictureColorspacePreset'])}")
    if p.get("VideoGrayScale"):
        out.append("Grayscale")
    rot = p.get("PictureRotate", "angle=0:hflip=0")
    if rot not in ("angle=0:hflip=0", "", None):
        out.append("Rotate / flip: " + rot.replace("angle=", "").replace(":hflip=1", ", flipped").replace(":hflip=0", "")
                   + "°")
    return out


# --------------------------------------------------------------------------- Dimensions
def parse_rotate(text: str) -> tuple[int, bool]:
    angle, flip = 0, False
    for part in (text or "").split(":"):
        k, _, v = part.partition("=")
        if k == "angle":
            angle = int(v or 0)
        elif k == "hflip":
            flip = v == "1"
    return angle, flip


class DimensionsTab(Tab):
    def __init__(self, win):
        super().__init__(win)
        g = QGridLayout(self)
        g.setContentsMargins(18, 16, 18, 16)
        g.setHorizontalSpacing(14)
        g.setVerticalSpacing(10)
        g.addWidget(field("Orientation and cropping"), 0, 0, 1, 4)
        g.addWidget(dim("Rotation"), 1, 0)
        self.rotate = Choice()
        self.rotate.set_items(ROTATIONS)
        self.rotate.currentIndexChanged.connect(self._rotate)
        g.addWidget(self.rotate, 1, 1)
        self.flip = QCheckBox("Flip horizontally")
        self.flip.toggled.connect(self._rotate)
        g.addWidget(self.flip, 1, 2)
        g.addWidget(dim("Cropping"), 2, 0)
        self.crop = self.choice("PictureCropMode", engine.CROP_MODES)
        g.addWidget(self.crop, 2, 1)
        self.sides = {}
        row = QHBoxLayout()
        for key, label in (("PictureTopCrop", "Top"), ("PictureBottomCrop", "Bottom"), ("PictureLeftCrop", "Left"),
                           ("PictureRightCrop", "Right")):
            s = QSpinBox()
            s.setRange(0, 4000)
            s.setSingleStep(2)
            s.valueChanged.connect(lambda v, k=key: self.write(**{k: v}))
            self.sides[key] = s
            row.addWidget(dim(label))
            row.addWidget(s)
        row.addStretch(1)
        g.addLayout(row, 3, 1, 1, 3)
        g.setRowMinimumHeight(4, 12)
        g.addWidget(field("Resolution and scaling"), 5, 0, 1, 4)
        g.addWidget(dim("Resolution limit"), 6, 0)
        self.limit = Choice()
        self.limit.currentIndexChanged.connect(self._limit)
        g.addWidget(self.limit, 6, 1)
        g.addWidget(dim("Anamorphic"), 7, 0)
        self.par = self.choice("PicturePAR", ANAMORPHIC)
        g.addWidget(self.par, 7, 1)
        self.upscale = self.check("PictureAllowUpscaling", "Allow upscaling")
        self.optimal = self.check("PictureUseMaximumSize", "Optimal size")
        g.addWidget(self.optimal, 8, 1)
        g.addWidget(self.upscale, 8, 2)
        g.setRowMinimumHeight(9, 12)
        g.addWidget(field("Final dimensions"), 10, 0, 1, 4)
        self.final = QLabel("open a source")
        self.final.setStyleSheet("font-weight: 600;")
        g.addWidget(self.final, 11, 0, 1, 4)
        g.setColumnStretch(3, 1)
        g.setRowStretch(12, 1)

    def _rotate(self, *_):
        self.write(PictureRotate=f"angle={self.rotate.value() or 0}:hflip={1 if self.flip.isChecked() else 0}")

    def _limit(self, *_):
        w, h = (int(x) for x in (self.limit.value() or "0x0").split("x"))
        self.write(PictureWidth=w, PictureHeight=h)

    def fill(self):
        p = self.p
        angle, flip = parse_rotate(p.get("PictureRotate", ""))
        self.rotate.set_value(angle)
        self.flip.setChecked(flip)
        self.crop.set_value(p.get("PictureCropMode", 0))
        custom = p.get("PictureCropMode", 0) == 3
        t = self.win.title
        for i, (key, s) in enumerate(self.sides.items()):
            s.setValue(int(p.get(key, 0)) if custom or t is None else int(t.crop[i]))
            s.setEnabled(custom)
        w, h = int(p.get("PictureWidth", 0) or 0), int(p.get("PictureHeight", 0) or 0)
        cur = f"{w}x{h}"
        items = list(LIMITS)
        if cur not in [v for v, _ in items]:
            items.append((cur, f"Custom {w} × {h}"))
        self.limit.set_items(items, cur)
        self.par.set_value(p.get("PicturePAR", "auto"))
        self.upscale.setChecked(bool(p.get("PictureAllowUpscaling")))
        self.optimal.setChecked(bool(p.get("PictureUseMaximumSize", True)))
        if t is not None:
            w, h = engine.output_size(p, t)
            self.final.setText(f"{w} × {h} storage  ·  {display_width(p, t, w, h)} × {h} display  ·  "
                               f"source {t.width} × {t.height}")


# --------------------------------------------------------------------------- Filters
class FiltersTab(Tab):
    def __init__(self, win):
        super().__init__(win)
        g = QGridLayout(self)
        g.setContentsMargins(18, 16, 18, 16)
        g.setHorizontalSpacing(14)
        g.setVerticalSpacing(10)
        r = 0

        def row(label, *ws):
            nonlocal r
            g.addWidget(field(label), r, 0)
            for i, w in enumerate(ws):
                g.addWidget(w, r, 1 + i)
            r += 1
        self.detelecine = self.choice("PictureDetelecine", DETELECINE)
        row("Detelecine", self.detelecine)
        self.comb = self.choice("PictureCombDetectPreset", COMB)
        row("Interlace detection", self.comb)
        self.deint = self.choice("PictureDeinterlaceFilter", DEINTERLACE)
        self.deint_preset = self.choice("PictureDeinterlacePreset", DEINTERLACE_PRESETS["decomb"])
        row("Deinterlace", self.deint, self.deint_preset)
        self.deblock = self.choice("PictureDeblockPreset", DEBLOCK)
        row("Deblock", self.deblock)
        self.denoise = self.choice("PictureDenoiseFilter", DENOISE)
        self.denoise_preset = self.choice("PictureDenoisePreset", DENOISE_PRESETS)
        self.denoise_tune = self.choice("PictureDenoiseTune", DENOISE_TUNES)
        row("Denoise", self.denoise, self.denoise_preset, self.denoise_tune)
        self.chroma = self.choice("PictureChromaSmoothPreset", CHROMA)
        row("Chroma smooth", self.chroma)
        self.sharpen = self.choice("PictureSharpenFilter", SHARPEN)
        self.sharpen_preset = self.choice("PictureSharpenPreset", STRENGTHS)
        self.sharpen_tune = self.choice("PictureSharpenTune", SHARPEN_TUNES["unsharp"])
        row("Sharpen", self.sharpen, self.sharpen_preset, self.sharpen_tune)
        self.colorspace = self.choice("PictureColorspacePreset", COLORSPACE)
        row("Colourspace", self.colorspace)
        self.gray = self.check("VideoGrayScale", "Grayscale")
        g.addWidget(self.gray, r, 1)
        g.setColumnStretch(4, 1)
        g.setRowStretch(r + 1, 1)

    def fill(self):
        p = self.p
        for c, key, default in ((self.detelecine, "PictureDetelecine", "off"), (self.comb, "PictureCombDetectPreset", "off"),
                                (self.deint, "PictureDeinterlaceFilter", "off"), (self.deblock, "PictureDeblockPreset", "off"),
                                (self.denoise, "PictureDenoiseFilter", "off"),
                                (self.chroma, "PictureChromaSmoothPreset", "off"), (self.sharpen, "PictureSharpenFilter", "off"),
                                (self.colorspace, "PictureColorspacePreset", "off")):
            c.set_value(p.get(key, default))
        d = p.get("PictureDeinterlaceFilter", "off")
        self.deint_preset.set_items(DEINTERLACE_PRESETS.get(d, DEINTERLACE_PRESETS["off"]),
                                    p.get("PictureDeinterlacePreset", "default"))
        self.deint_preset.setEnabled(d != "off")
        self.denoise_preset.set_value(p.get("PictureDenoisePreset", "medium"))
        self.denoise_tune.set_value(p.get("PictureDenoiseTune", "none"))
        on = p.get("PictureDenoiseFilter", "off") != "off"
        self.denoise_preset.setEnabled(on)
        self.denoise_tune.setEnabled(on and p.get("PictureDenoiseFilter") == "nlmeans")
        s = p.get("PictureSharpenFilter", "off")
        self.sharpen_preset.set_value(p.get("PictureSharpenPreset", "medium"))
        self.sharpen_tune.set_items(SHARPEN_TUNES.get(s, SHARPEN_TUNES["off"]), p.get("PictureSharpenTune", "none"))
        self.sharpen_preset.setEnabled(s != "off")
        self.sharpen_tune.setEnabled(s != "off")
        self.gray.setChecked(bool(p.get("VideoGrayScale")))


# --------------------------------------------------------------------------- Video
class VideoTab(Tab):
    def __init__(self, win):
        super().__init__(win)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(18, 16, 18, 16)
        lay.setSpacing(30)
        left = QGridLayout()
        left.setVerticalSpacing(10)
        left.addWidget(field("Video encoder"), 0, 0)
        self.encoder = Choice()
        self.encoder.currentIndexChanged.connect(self._encoder)
        left.addWidget(self.encoder, 0, 1)
        left.addWidget(field("Framerate (FPS)"), 1, 0)
        self.rate = Choice()
        self.rate.set_items([(r, "Same as source" if r == "auto" else r) for r in engine.FRAMERATES])
        self.rate.currentIndexChanged.connect(self._rate)
        left.addWidget(self.rate, 1, 1)
        self.mode_a, self.mode_b = QRadioButton(), QRadioButton()
        self.mode_group = QButtonGroup(self)        # siblings: without groups Qt makes all four radios one set
        self.mode_group.addButton(self.mode_a)
        self.mode_group.addButton(self.mode_b)
        self.mode_a.toggled.connect(self._rate)
        left.addWidget(self.mode_a, 2, 1)
        left.addWidget(self.mode_b, 3, 1)
        left.setRowMinimumHeight(4, 14)
        left.addWidget(field("Encoder options"), 5, 0, 1, 2)
        left.addWidget(dim("Preset"), 6, 0)
        self.speed = QSlider(Qt.Orientation.Horizontal)
        self.speed.valueChanged.connect(self._speed)
        self.speed_label = QLabel()
        row = QHBoxLayout()
        row.addWidget(self.speed, 1)
        row.addWidget(self.speed_label)
        left.addLayout(row, 6, 1)
        left.addWidget(dim("Tune"), 7, 0)
        self.tune = Choice()
        self.tune.currentIndexChanged.connect(self._tune)
        left.addWidget(self.tune, 7, 1)
        left.addWidget(dim("Profile"), 8, 0)
        self.profile = self.choice("VideoProfile", [("auto", "auto")])
        left.addWidget(self.profile, 8, 1)
        left.addWidget(dim("Level"), 9, 0)
        self.level = self.choice("VideoLevel", [("auto", "auto")])
        left.addWidget(self.level, 9, 1)
        self.fastdecode = QCheckBox("Fast decode")
        self.fastdecode.toggled.connect(self._tune)
        left.addWidget(self.fastdecode, 10, 1)
        left.addWidget(dim("Advanced"), 11, 0)
        self.extra = QLineEdit()
        self.extra.setPlaceholderText("encoder options, e.g. aq-mode=3:psy-rd=1.5")
        self.extra.textEdited.connect(lambda t: self.write(VideoOptionExtra=t))
        left.addWidget(self.extra, 11, 1)
        left.setRowStretch(12, 1)
        lay.addLayout(left, 1)
        right = QVBoxLayout()
        right.setSpacing(10)
        right.addWidget(field("Quality"))
        self.cq = QRadioButton("Constant quality")
        self.cq.toggled.connect(self._qtype)
        right.addWidget(self.cq)
        self.q = QSlider(Qt.Orientation.Horizontal)
        self.q.valueChanged.connect(self._q)
        self.q_label = QLabel()
        self.q_label.setStyleSheet("font-weight: 600;")
        row = QHBoxLayout()
        row.addSpacing(26)
        row.addWidget(self.q, 1)
        row.addWidget(self.q_label)
        right.addLayout(row)
        ends = QHBoxLayout()
        ends.addSpacing(26)
        ends.addWidget(dim("Low quality"))
        ends.addStretch(1)
        ends.addWidget(dim("Placebo quality"))
        ends.addSpacing(54)
        right.addLayout(ends)
        self.q_hint = dim("")
        right.addWidget(self.q_hint)
        right.addSpacing(10)
        self.abr = QRadioButton("Average bitrate (kbps)")
        self.quality_group = QButtonGroup(self)
        self.quality_group.addButton(self.cq)
        self.quality_group.addButton(self.abr)
        right.addWidget(self.abr)
        row = QHBoxLayout()
        row.addSpacing(26)
        self.bitrate = QSpinBox()
        self.bitrate.setRange(50, 200000)
        self.bitrate.setFixedWidth(110)
        self.bitrate.valueChanged.connect(lambda v: self.write(VideoAvgBitrate=v))
        row.addWidget(self.bitrate)
        self.two = self.check("VideoMultiPass", "Multi-pass encoding")
        self.turbo = self.check("VideoTurboMultiPass", "Turbo analysis pass")
        row.addWidget(self.two)
        row.addWidget(self.turbo)
        row.addStretch(1)
        right.addLayout(row)
        right.addStretch(1)
        lay.addLayout(right, 1)
        self._presets: list[str] = []

    # quality slider: whole steps (HandBrake's default granularity), lower-is-better scales shown inverted
    def _scale(self):
        return engine.quality_scale(self.p.get("VideoEncoder", "x264"))

    def _encoder(self, *_):
        if self.loading:
            return
        enc = self.encoder.value()
        caps = self.win.caps
        self.p["VideoEncoder"] = enc
        if caps:   # keep the encoder's own choices valid, as HandBrake resets them
            pres = caps.options("preset", enc)
            if self.p.get("VideoPreset") not in pres:
                self.p["VideoPreset"] = "medium" if "medium" in pres else (pres[len(pres) // 2] if pres else "")
            if self.p.get("VideoProfile") not in caps.options("profile", enc):
                self.p["VideoProfile"] = "auto"
            if self.p.get("VideoLevel") not in caps.options("level", enc):
                self.p["VideoLevel"] = "auto"
            tunes = caps.options("tune", enc)
            self.p["VideoTune"] = ",".join(t for t in self.p.get("VideoTune", "").split(",") if t in tunes)
        lo, hi, lower, _ = engine.quality_scale(enc)
        if not lo <= float(self.p.get("VideoQualitySlider", 22)) <= hi:
            self.p["VideoQualitySlider"] = 22.0 if hi == 51 else 30.0
        self.win.preset_edited(self)
        self.load()

    def _rate(self, *_):
        if self.loading:
            return
        rate = self.rate.value()
        if rate == "auto":
            mode = "vfr" if self.mode_a.isChecked() else "cfr"
        else:
            mode = "cfr" if self.mode_a.isChecked() else "pfr"
        self.write(VideoFramerate=rate, VideoFramerateMode=mode)
        self._mode_labels(rate)

    def _mode_labels(self, rate):
        if rate == "auto":
            self.mode_a.setText("Variable framerate")
            self.mode_b.setText("Constant framerate")
        else:
            self.mode_a.setText("Constant framerate")
            self.mode_b.setText("Peak framerate")

    def _speed(self, v):
        if 0 <= v < len(self._presets):
            self.speed_label.setText(self._presets[v])
            self.write(VideoPreset=self._presets[v])

    def _tune(self, *_):
        if self.loading:
            return
        tunes = [self.tune.value()] if self.tune.value() not in (None, "", "none") else []
        if self.fastdecode.isChecked():
            tunes.append("fastdecode")
        self.write(VideoTune=",".join(tunes))

    def _qtype(self, *_):
        if self.loading:
            return
        self.write(VideoQualityType=2 if self.cq.isChecked() else 1)
        self._enable()

    def _q(self, v):
        lo, hi, lower, label = self._scale()
        value = (hi - v + lo) if lower else v
        self.q_label.setText(f"{label} {value:g}")
        self.write(VideoQualitySlider=float(value))

    def _enable(self):
        cq = self.p.get("VideoQualityType", 2) == 2
        self.q.setEnabled(cq)
        for w in (self.bitrate, self.two):
            w.setEnabled(not cq)
        self.turbo.setEnabled(not cq and bool(self.p.get("VideoMultiPass")))

    def fill(self):
        p = self.p
        caps = self.win.caps
        enc = p.get("VideoEncoder", "x264")
        names = caps.video if caps else [enc]
        self.encoder.set_items([(e, engine.video_name(e)) for e in names], enc)
        rate = p.get("VideoFramerate", "auto") or "auto"
        self.rate.set_value(rate)
        self._mode_labels(rate)
        mode = p.get("VideoFramerateMode", "vfr")
        (self.mode_a if (mode == "vfr" if rate == "auto" else mode == "cfr") else self.mode_b).setChecked(True)
        self._presets = caps.options("preset", enc) if caps else [p.get("VideoPreset", "medium")]
        self.speed.setRange(0, max(0, len(self._presets) - 1))
        cur = p.get("VideoPreset", "medium")
        self.speed.setValue(self._presets.index(cur) if cur in self._presets else 0)
        self.speed_label.setText(cur)
        self.speed.setEnabled(bool(self._presets))
        tunes = [t for t in (caps.options("tune", enc) if caps else []) if t != "fastdecode"]
        chosen = [t for t in p.get("VideoTune", "").split(",") if t]
        self.tune.set_items([("none", "None")] + [(t, t) for t in tunes],
                            next((t for t in chosen if t != "fastdecode"), "none"))
        self.fastdecode.setChecked("fastdecode" in chosen)
        self.fastdecode.setEnabled(caps is None or "fastdecode" in caps.options("tune", enc))
        prof = caps.options("profile", enc) if caps else []
        self.profile.set_items([(x, x) for x in (prof or ["auto"])], p.get("VideoProfile", "auto"))
        lev = caps.options("level", enc) if caps else []
        self.level.set_items([(x, x) for x in (lev or ["auto"])], p.get("VideoLevel", "auto"))
        self.extra.setText(p.get("VideoOptionExtra", ""))
        lo, hi, lower, label = engine.quality_scale(enc)
        self.q.setRange(int(lo), int(hi))
        v = float(p.get("VideoQualitySlider", 22))
        self.q.setValue(int(round((hi - v + lo) if lower else v)))
        self.q_label.setText(f"{label} {v:g}")
        self.q_hint.setText("      Lower RF = better picture, bigger file. 18-22 is near the source for 1080p."
                            if label == "RF" and hi == 51 else f"      {'Lower' if lower else 'Higher'} {label} = "
                                                              "better picture, bigger file.")
        (self.cq if p.get("VideoQualityType", 2) == 2 else self.abr).setChecked(True)
        self.bitrate.setValue(int(p.get("VideoAvgBitrate", 6000) or 6000))
        self.two.setChecked(bool(p.get("VideoMultiPass")))
        self.turbo.setChecked(bool(p.get("VideoTurboMultiPass")))
        self._enable()


# --------------------------------------------------------------------------- Audio
class TrackTable(QTableWidget):
    def __init__(self, headers):
        super().__init__(0, len(headers))
        self.setHorizontalHeaderLabels([h.upper() for h in headers])
        self.verticalHeader().setVisible(False)
        self.horizontalHeader().setStretchLastSection(False)
        self.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.setShowGrid(False)


class AudioTab(Tab):
    COLS = ["Source track", "Encoder", "Mixdown", "Samplerate", "Bitrate", "Gain", "DRC", ""]

    def __init__(self, win):
        super().__init__(win)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 14, 16, 14)
        keys = QHBoxLayout()
        self.add = QPushButton("Add Track")
        self.add_all = QPushButton("Add All Tracks")
        self.reset = QPushButton("Reset to Preset")
        for b in (self.add, self.add_all, self.reset):
            keys.addWidget(b)
        keys.addStretch(1)
        self.count = dim("")
        keys.addWidget(self.count)
        lay.addLayout(keys)
        self.table = TrackTable(self.COLS)
        lay.addWidget(self.table, 1)
        self.add.clicked.connect(self.add_track)
        self.add_all.clicked.connect(self.add_all_tracks)
        self.reset.clicked.connect(self.win.reset_tracks)

    def _template(self) -> engine.AudioTrack:
        e = (self.p.get("AudioList") or [{}])[0]
        return engine.AudioTrack(1, e.get("AudioEncoder", "av_aac"), e.get("AudioMixdown", "stereo") or "stereo",
                                 int(e.get("AudioBitrate", 160) or 160))

    def add_track(self, source: int | None = None):
        t = self.win.title
        if t is None or not t.audio:
            return
        used = {a.source for a in self.win.audio_tracks}
        nxt = source or next((a.number for a in t.audio if a.number not in used), t.audio[0].number)
        tr = self._template()
        tr.source = nxt
        if tr.encoder.startswith("copy"):
            tr.encoder = self.p.get("AudioEncoderFallback", "av_aac")
        self.win.audio_tracks.append(tr)
        self.win.tracks_edited()

    def add_all_tracks(self):
        t = self.win.title
        if t is None:
            return
        used = {a.source for a in self.win.audio_tracks}
        for a in t.audio:
            if a.number not in used:
                self.add_track(a.number)

    def fill(self):
        t = self.win.title
        tracks = self.win.audio_tracks
        caps = self.win.caps
        encoders = caps.audio if caps else sorted({a.encoder for a in tracks} | {"av_aac"})
        self.table.setRowCount(len(tracks))
        src = [(a.number, f"{a.number}: {a.description}") for a in (t.audio if t else [])]
        for r, tr in enumerate(tracks):
            def put(col, w):
                self.table.setCellWidget(r, col, w)
            c = Choice()
            c.set_items(src or [(tr.source, str(tr.source))], tr.source)
            c.currentIndexChanged.connect(lambda _=0, tr=tr, c=c: self._set(tr, source=c.value()))
            put(0, c)
            e = Choice()
            e.set_items([(x, engine.audio_name(x)) for x in encoders], tr.encoder)
            e.currentIndexChanged.connect(lambda _=0, tr=tr, e=e: self._set(tr, encoder=e.value()))
            put(1, e)
            passthru = tr.encoder.startswith("copy") or tr.encoder == "none"
            m = Choice()
            m.set_items(engine.MIXDOWNS, tr.mixdown)
            m.setEnabled(not passthru)
            m.currentIndexChanged.connect(lambda _=0, tr=tr, m=m: self._set(tr, mixdown=m.value()))
            put(2, m)
            s = Choice()
            s.set_items([(x, "Auto" if x == "auto" else f"{x} kHz") for x in engine.SAMPLERATES], tr.samplerate)
            s.setEnabled(not passthru)
            s.currentIndexChanged.connect(lambda _=0, tr=tr, s=s: self._set(tr, samplerate=s.value()))
            put(3, s)
            b = Choice()
            b.set_items([(x, f"{x} kbps") for x in (64, 80, 96, 112, 128, 160, 192, 224, 256, 320, 384, 448, 640)],
                        tr.bitrate)
            b.setEnabled(not passthru and not tr.encoder.startswith("flac"))
            b.currentIndexChanged.connect(lambda _=0, tr=tr, b=b: self._set(tr, bitrate=b.value()))
            put(4, b)
            g = QDoubleSpinBox()
            g.setRange(-20, 20)
            g.setSuffix(" dB")
            g.setValue(tr.gain)
            g.setEnabled(not passthru)
            g.valueChanged.connect(lambda v, tr=tr: self._set(tr, gain=v, reload=False))
            put(5, g)
            d = QDoubleSpinBox()
            d.setRange(0, 4)
            d.setSingleStep(0.5)
            d.setValue(tr.drc)
            d.setEnabled(not passthru)
            d.valueChanged.connect(lambda v, tr=tr: self._set(tr, drc=v, reload=False))
            put(6, d)
            x = QPushButton("Remove")
            x.clicked.connect(lambda _=False, tr=tr: self._remove(tr))
            put(7, x)
        n = len(tracks)
        self.count.setText("No audio" if not n else f"{n} track{'s' if n != 1 else ''}")
        has = t is not None and bool(t.audio)
        self.add.setEnabled(has)
        self.add_all.setEnabled(has)

    def _set(self, tr, reload=True, **values):
        if self.loading:
            return
        for k, v in values.items():
            setattr(tr, k, v)
        self.win.tracks_edited(reload=reload)

    def _remove(self, tr):
        if tr in self.win.audio_tracks:
            self.win.audio_tracks.remove(tr)
        self.win.tracks_edited()


# --------------------------------------------------------------------------- Subtitles
class SubtitlesTab(Tab):
    COLS = ["Source", "Forced only", "Burn in", "Default", ""]

    def __init__(self, win):
        super().__init__(win)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 14, 16, 14)
        keys = QHBoxLayout()
        self.add = QPushButton("Add Track")
        self.scan = QPushButton("Add Foreign Audio Scan")
        self.imp = QPushButton("Import Subtitle File…")
        self.reset = QPushButton("Reset to Preset")
        for b in (self.add, self.scan, self.imp, self.reset):
            keys.addWidget(b)
        keys.addStretch(1)
        lay.addLayout(keys)
        self.table = TrackTable(self.COLS)
        lay.addWidget(self.table, 1)
        self.note = dim("Only one subtitle can be burned in. MP4 holds text subtitles; picture subtitles (PGS, "
                        "VobSub) need MKV or burning in.")
        self.note.setWordWrap(True)
        lay.addWidget(self.note)
        self.add.clicked.connect(self.add_track)
        self.scan.clicked.connect(self.add_scan)
        self.imp.clicked.connect(self.win.import_subtitles)
        self.reset.clicked.connect(self.win.reset_tracks)

    def add_track(self):
        t = self.win.title
        if t is None or not t.subtitles:
            return
        used = {s.source for s in self.win.subtitle_tracks}
        nxt = next((s.number for s in t.subtitles if s.number not in used), t.subtitles[0].number)
        self.win.subtitle_tracks.append(engine.SubtitleTrack(nxt))
        self.win.tracks_edited()

    def add_scan(self):
        if not any(s.source == "scan" for s in self.win.subtitle_tracks):
            self.win.subtitle_tracks.insert(0, engine.SubtitleTrack("scan", forced_only=True, burn=True))
            self._one_burn(self.win.subtitle_tracks[0])
            self.win.tracks_edited()

    def _one_burn(self, keep):
        for s in self.win.subtitle_tracks:
            if s is not keep:
                s.burn = False

    def fill(self):
        t = self.win.title
        tracks = self.win.subtitle_tracks
        self.table.setRowCount(len(tracks))
        inner = [(s.number, f"{s.number}: {s.description}") for s in (t.subtitles if t else [])]
        for r, st in enumerate(tracks):
            if st.source == "scan":
                self.table.setCellWidget(r, 0, QLabel("  Foreign audio scan"))
            elif isinstance(st.source, str):
                self.table.setCellWidget(r, 0, QLabel(f"  {os.path.basename(st.source)}  ({st.language})"))
            else:
                c = Choice()
                c.set_items(inner or [(st.source, str(st.source))], st.source)
                c.currentIndexChanged.connect(lambda _=0, st=st, c=c: self._set(st, source=c.value()))
                self.table.setCellWidget(r, 0, c)
            for col, attr in ((1, "forced_only"), (2, "burn"), (3, "default")):
                b = QCheckBox()
                b.setChecked(getattr(st, attr))
                b.toggled.connect(lambda on, st=st, a=attr: self._set(st, **{a: on}))
                holder = QWidget()
                hl = QHBoxLayout(holder)
                hl.setContentsMargins(12, 0, 0, 0)
                hl.addWidget(b)
                self.table.setCellWidget(r, col, holder)
            x = QPushButton("Remove")
            x.clicked.connect(lambda _=False, st=st: self._remove(st))
            self.table.setCellWidget(r, 4, x)
        has = t is not None and bool(t.subtitles)
        self.add.setEnabled(has)
        self.scan.setEnabled(has)

    def _set(self, st, **values):
        if self.loading:
            return
        for k, v in values.items():
            setattr(st, k, v)
        if values.get("burn"):
            self._one_burn(st)                       # HandBrake: one burned-in subtitle at most
        if values.get("default"):
            for s in self.win.subtitle_tracks:
                if s is not st:
                    s.default = False
        self.win.tracks_edited()

    def _remove(self, st):
        if st in self.win.subtitle_tracks:
            self.win.subtitle_tracks.remove(st)
        self.win.tracks_edited()


# --------------------------------------------------------------------------- Chapters
class ChaptersTab(Tab):
    def __init__(self, win):
        super().__init__(win)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 14, 16, 14)
        keys = QHBoxLayout()
        self.markers = self.check("ChapterMarkers", "Create chapter markers")
        keys.addWidget(self.markers)
        keys.addStretch(1)
        self.imp = QPushButton("Import…")
        self.exp = QPushButton("Export…")
        keys.addWidget(self.imp)
        keys.addWidget(self.exp)
        lay.addLayout(keys)
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["CHAPTER", "DURATION", "NAME"])
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table.setShowGrid(False)
        self.table.itemChanged.connect(self._edited)
        lay.addWidget(self.table, 1)
        self.note = dim("")
        lay.addWidget(self.note)
        self.imp.clicked.connect(self.win.import_chapters)
        self.exp.clicked.connect(self.win.export_chapters)

    def fill(self):
        t = self.win.title
        names = self.win.chapter_names
        self.markers.setChecked(bool(self.p.get("ChapterMarkers", True)))
        chapters = t.chapters if t else []
        self.table.blockSignals(True)
        self.table.setRowCount(len(chapters))
        for i, (_, secs) in enumerate(chapters):
            for col, text in ((0, str(i + 1)), (1, engine.hms(secs)), (2, names[i] if i < len(names) else "")):
                it = QTableWidgetItem(text)
                if col < 2:
                    it.setFlags(it.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.table.setItem(i, col, it)
        self.table.blockSignals(False)
        self.table.setEnabled(bool(self.p.get("ChapterMarkers", True)))
        self.note.setText("This source has one chapter: HandBrake writes no chapter markers for it."
                          if t is not None and len(chapters) < 2 else "")

    def _edited(self, item):
        if self.loading or item.column() != 2:
            return
        names = self.win.chapter_names
        while len(names) <= item.row():
            names.append("")
        names[item.row()] = item.text()


def read_chapter_csv(path: str) -> list[str]:
    return engine.read_chapters(path)


def write_chapter_csv(path: str, names: list[str]) -> None:
    engine.write_chapters(path, names)
