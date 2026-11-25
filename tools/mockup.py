"""Mock-up pictures of PR7-HB, drawn offscreen with real Qt widgets in the family theme (every file, size and number is
made up): QT_SCALE_FACTOR=2 python tools/mockup.py OUT_DIR

1_main.png       the window: source, preset, the Summary tab, destination, an encode running (OBSIDIAN)
2_video.png      the Video tab: encoder, framerate, constant quality, encoder preset (AURORA)
3_queue.png      the Queue: jobs with their state, the selected job's details, When done (OBSIDIAN)
"""
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QPointF, QRectF, Qt  # noqa: E402
from PySide6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap  # noqa: E402
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QFrame, QGridLayout, QHBoxLayout,  # noqa: E402
                               QLabel, QLineEdit, QListWidget, QListWidgetItem, QProgressBar, QPushButton,
                               QRadioButton, QSlider, QSpinBox, QTabWidget, QVBoxLayout, QWidget)

from pr7hb import theme, widgets  # noqa: E402

out = Path(sys.argv[1] if len(sys.argv) > 1 else "docs/mockup")
out.mkdir(parents=True, exist_ok=True)
app = QApplication([])
theme.load_fonts()
app.setFont(QFont("Inter", 10))


def style():
    app.setPalette(theme.palette())
    app.setStyleSheet(theme.stylesheet())


def field(text):
    lab = QLabel(text.upper())
    lab.setProperty("role", "field")
    return lab


def dim(text):
    lab = QLabel(text)
    lab.setProperty("role", "dim")
    return lab


def combo(*items, width=None):
    c = QComboBox()
    c.addItems(list(items))
    if width:
        c.setFixedWidth(width)
    return c


def button(text, primary=False):
    b = QPushButton(text)
    if primary:
        b.setStyleSheet(f"QPushButton {{ background: {theme.qss_gradient()}; color: #FFFFFF; border: none; "
                        f"font-weight: 600; padding: 6px 16px; border-radius: 5px; }}")
    return b


def toolbar(keys):
    bar = QWidget()
    lay = QHBoxLayout(bar)
    lay.setContentsMargins(16, 10, 16, 6)
    lay.setSpacing(6)
    for i, group in enumerate(keys):
        if i:
            sep = QLabel()
            sep.setFixedSize(1, 40)
            sep.setStyleSheet(f"background: {theme.PANEL_EDGE};")
            lay.addSpacing(8)
            lay.addWidget(sep)
            lay.addSpacing(8)
        for icon, label in group:
            k = widgets.KeyButton(icon, label)
            k.setFixedSize(92, 62)
            lay.addWidget(k)
    lay.addStretch(1)
    return bar


class Preview(QWidget):
    """A made-up frame of the source: dusk over ruins, in family colours (onyx sky into red and orange)."""

    def __init__(self, caption):
        super().__init__()
        self.caption = caption
        self.setMinimumSize(420, 236)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect()).adjusted(0, 0, -1, -22)
        sky = QLinearGradient(r.topLeft(), r.bottomLeft())
        for pos, c in ((0, "#07050A"), (.45, "#2A0A12"), (.72, "#B5281F"), (.86, "#E8702A"), (1, "#3A1A12")):
            sky.setColorAt(pos, QColor(c))
        p.fillRect(r, sky)
        sun = QColor("#FFB066")
        p.setBrush(sun)
        p.setPen(Qt.NoPen)
        p.drawEllipse(QPointF(r.center().x() + 60, r.top() + r.height() * .74), 26, 26)
        hills = QPainterPath(QPointF(r.left(), r.bottom()))
        for x, y in ((0, .78), (.12, .7), (.22, .76), (.35, .62), (.47, .74), (.6, .68), (.74, .8), (.88, .7), (1, .76)):
            hills.lineTo(r.left() + x * r.width(), r.top() + y * r.height())
        hills.lineTo(r.right(), r.bottom())
        p.fillPath(hills, QColor("#050406"))
        for x, h in ((.16, .26), (.2, .34), (.24, .22), (.66, .3), (.7, .4), (.75, .28)):   # ruined columns
            p.fillRect(QRectF(r.left() + x * r.width(), r.top() + (.74 - h) * r.height(), 9, h * r.height()),
                       QColor("#050406"))
        p.setPen(QPen(QColor(theme.PANEL_EDGE), 1))
        p.setBrush(Qt.NoBrush)
        p.drawRect(r)
        p.setPen(QColor(theme.TEXT_DIM))
        f = QFont("Inter", 1)
        f.setPixelSize(11)
        p.setFont(f)
        p.drawText(QRectF(0, r.bottom() + 4, self.width(), 18), Qt.AlignCenter, self.caption)


def source_rows():
    box = QWidget()
    g = QGridLayout(box)
    g.setContentsMargins(18, 4, 18, 4)
    g.setHorizontalSpacing(10)
    g.setVerticalSpacing(8)
    g.addWidget(field("Source"), 0, 0)
    name = QLabel("ELSEWORLD_master.mkv")
    name.setStyleSheet("font-weight: 600; font-size: 13px;")
    g.addWidget(name, 0, 1, 1, 2)
    g.addWidget(dim("3840 × 2160 · 23.976 FPS · HEVC 10-bit HDR10 · 2 audio · 3 subtitles"), 0, 3, 1, 6)
    g.addWidget(field("Title"), 1, 0)
    g.addWidget(combo("1  ·  01:42:13", "2  ·  00:04:51 (trailer)", width=190), 1, 1)
    g.addWidget(field("Range"), 1, 2, Qt.AlignRight)
    g.addWidget(combo("Chapters", "Seconds", "Frames", width=110), 1, 3)
    a, b = QSpinBox(), QSpinBox()
    for s, v in ((a, 1), (b, 24)):
        s.setRange(1, 24)
        s.setValue(v)
        s.setFixedWidth(64)
    g.addWidget(a, 1, 4)
    g.addWidget(dim("through"), 1, 5)
    g.addWidget(b, 1, 6)
    g.addWidget(field("Duration"), 1, 7, Qt.AlignRight)
    g.addWidget(QLabel("01:42:13"), 1, 8)
    g.addWidget(field("Preset"), 2, 0)
    g.addWidget(combo("Fast 1080p30", "HQ 2160p60 4K HEVC Surround", "Paragon · Archive H.265 10-bit"), 2, 1, 1, 3)
    g.addWidget(button("Save New Preset"), 2, 4, 1, 3)
    g.setColumnStretch(9, 1)
    return box


def destination(path):
    box = QWidget()
    lay = QHBoxLayout(box)
    lay.setContentsMargins(18, 6, 18, 8)
    lay.setSpacing(10)
    lay.addWidget(field("Save as"))
    e = QLineEdit(path)
    lay.addWidget(e, 1)
    lay.addWidget(button("Browse…"))
    return box


def summary_tab():
    w = QWidget()
    lay = QHBoxLayout(w)
    lay.setContentsMargins(16, 14, 16, 14)
    lay.setSpacing(24)
    left = QVBoxLayout()
    left.setSpacing(8)
    row = QHBoxLayout()
    row.addWidget(field("Format"))
    row.addWidget(combo("MP4", "MKV", "WebM", width=120))
    row.addStretch(1)
    left.addLayout(row)
    for text, on in (("Web optimized", True), ("Align A/V start", False), ("Passthru common metadata", True)):
        c = QCheckBox(text)
        c.setChecked(on)
        left.addWidget(c)
    left.addSpacing(10)
    left.addWidget(field("Tracks"))
    for text in ("H.264 (x264), 30 FPS peak framerate", "AAC (avcodec), Stereo, 160 kbps",
                 "English · AC3 5.1 passthru", "Foreign audio scan, burned in", "Chapter markers"):
        left.addWidget(QLabel("·  " + text))
    left.addSpacing(10)
    left.addWidget(field("Filters"))
    left.addWidget(QLabel("·  Decomb, Default"))
    left.addWidget(QLabel("·  Colorspace: BT.709 (HDR10 tone-mapped)"))
    left.addSpacing(10)
    left.addWidget(field("Size"))
    left.addWidget(QLabel("·  1920 × 1080 storage, 1920 × 1080 display"))
    left.addStretch(1)
    lay.addLayout(left, 1)
    right = QVBoxLayout()
    right.addWidget(Preview("PREVIEW  ·  7 OF 10  ·  00:51:06"))
    keys = QHBoxLayout()
    keys.addStretch(1)
    for icon, tip in (("back", "Previous preview"), ("play", "Live preview"), ("forward", "Next preview")):
        keys.addWidget(widgets.SmallKey(icon, tip))
    keys.addStretch(1)
    right.addLayout(keys)
    lay.addLayout(right, 1)
    return w


def video_tab():
    w = QWidget()
    lay = QHBoxLayout(w)
    lay.setContentsMargins(18, 16, 18, 16)
    lay.setSpacing(30)
    left = QGridLayout()
    left.setVerticalSpacing(10)
    left.addWidget(field("Video encoder"), 0, 0)
    left.addWidget(combo("H.265 10-bit (x265)", "H.264 (x264)", "AV1 10-bit (SVT)", "H.265 (NVEnc)"), 0, 1)
    left.addWidget(field("Framerate (FPS)"), 1, 0)
    left.addWidget(combo("Same as source", "23.976", "25", "29.97", "30", "50", "59.94", "60"), 1, 1)
    cfr, pfr = QRadioButton("Constant framerate"), QRadioButton("Peak framerate (variable)")
    pfr.setChecked(True)
    left.addWidget(cfr, 2, 1)
    left.addWidget(pfr, 3, 1)
    left.setRowMinimumHeight(4, 14)
    left.addWidget(field("Encoder options"), 5, 0, 1, 2)
    left.addWidget(dim("Preset"), 6, 0)
    preset = QSlider(Qt.Horizontal)
    preset.setRange(0, 9)
    preset.setValue(6)
    row = QHBoxLayout()
    row.addWidget(preset, 1)
    row.addWidget(QLabel("slow"))
    left.addLayout(row, 6, 1)
    left.addWidget(dim("Tune"), 7, 0)
    left.addWidget(combo("None", "Film", "Animation", "Grain"), 7, 1)
    left.addWidget(dim("Profile"), 8, 0)
    left.addWidget(combo("main10", "auto", "main"), 8, 1)
    left.addWidget(dim("Level"), 9, 0)
    left.addWidget(combo("Auto", "5.1", "5.0", "4.1"), 9, 1)
    left.addWidget(QCheckBox("Fast decode"), 10, 1)
    left.addWidget(dim("Advanced"), 11, 0)
    left.addWidget(QLineEdit("aq-mode=3:psy-rd=1.5"), 11, 1)
    left.setRowStretch(12, 1)
    lay.addLayout(left, 1)
    right = QVBoxLayout()
    right.setSpacing(10)
    right.addWidget(field("Quality"))
    cq = QRadioButton("Constant quality")
    cq.setChecked(True)
    right.addWidget(cq)
    rf = QSlider(Qt.Horizontal)
    rf.setRange(0, 51)
    rf.setInvertedAppearance(True)
    rf.setValue(22)
    row = QHBoxLayout()
    row.addSpacing(26)
    row.addWidget(rf, 1)
    rfv = QLabel("RF 22")
    rfv.setStyleSheet("font-weight: 600;")
    row.addWidget(rfv)
    right.addLayout(row)
    ends = QHBoxLayout()
    ends.addSpacing(26)
    ends.addWidget(dim("Low quality"))
    ends.addStretch(1)
    ends.addWidget(dim("Placebo quality"))
    ends.addSpacing(44)
    right.addLayout(ends)
    right.addWidget(dim("      Lower RF = better picture, bigger file. 18-22 is near the source for 1080p."))
    right.addSpacing(10)
    right.addWidget(QRadioButton("Average bitrate (kbps)"))
    row = QHBoxLayout()
    row.addSpacing(26)
    br = QLineEdit("6000")
    br.setFixedWidth(100)
    br.setEnabled(False)
    row.addWidget(br)
    two, turbo = QCheckBox("2-pass encoding"), QCheckBox("Turbo first pass")
    two.setEnabled(False)
    turbo.setEnabled(False)
    row.addWidget(two)
    row.addWidget(turbo)
    row.addStretch(1)
    right.addLayout(row)
    right.addStretch(1)
    lay.addLayout(right, 1)
    return w


def window(tab: str):
    w = QWidget()
    w.setObjectName("win")
    w.setStyleSheet(f"QWidget#win {{ background: {theme.BACKGROUND}; }}")
    lay = QVBoxLayout(w)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(0)
    lay.addWidget(widgets.Header("VIDEO CONVERTER"))
    lay.addWidget(toolbar([[("open", "Open Source")],
                           [("add", "Add to Queue"), ("play", "Start"), ("pause", "Pause")],
                           [("playlist", "Queue"), ("eye", "Preview"), ("file", "Activity Log")],
                           [("list", "Presets")]]))
    lay.addWidget(source_rows())
    tabs = QTabWidget()
    tabs.setDocumentMode(False)
    blank = QWidget
    for name, page in (("SUMMARY", summary_tab() if tab == "summary" else blank()), ("DIMENSIONS", blank()),
                       ("FILTERS", blank()), ("VIDEO", video_tab() if tab == "video" else blank()),
                       ("AUDIO", blank()), ("SUBTITLES", blank()), ("CHAPTERS", blank())):
        tabs.addTab(page, name)
    tabs.setCurrentIndex(0 if tab == "summary" else 3)
    holder = QWidget()
    hl = QVBoxLayout(holder)
    hl.setContentsMargins(16, 8, 16, 0)
    hl.addWidget(tabs)
    lay.addWidget(holder, 1)
    lay.addWidget(destination(r"C:\Users\Studio\Videos\Exports\ELSEWORLD_master.mp4"))
    status = QFrame()
    status.setStyleSheet(f"QFrame {{ background: {theme.TAB_FRAME}; border-top: 1px solid {theme.PANEL_EDGE}; }}")
    sl = QHBoxLayout(status)
    sl.setContentsMargins(16, 6, 16, 6)
    if tab == "summary":
        bar = QProgressBar()
        bar.setValue(42)
        bar.setTextVisible(False)
        bar.setFixedWidth(260)
        sl.addWidget(field("Encoding 1 of 3"))
        sl.addWidget(bar)
        sl.addWidget(dim("42.17 %  ·  63.2 FPS (average 61.8)  ·  ETA 00:12:40"))
        sl.addStretch(1)
        sl.addWidget(dim("When done: Do nothing"))
    else:
        sl.addWidget(dim("Ready  ·  3 jobs in the queue"))
        sl.addStretch(1)
    lay.addWidget(status)
    w.resize(1180, 860)
    return w


def queue():
    w = QWidget()
    w.setObjectName("win")
    w.setStyleSheet(f"QWidget#win {{ background: {theme.BACKGROUND}; }}")
    lay = QVBoxLayout(w)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(0)
    lay.addWidget(widgets.Header("QUEUE"))
    lay.addWidget(toolbar([[("play", "Start Queue"), ("pause", "Pause"), ("stop", "Stop")],
                           [("close", "Remove"), ("refresh", "Retry"), ("trash", "Clear Done")]]))
    body = QHBoxLayout()
    body.setContentsMargins(16, 6, 16, 12)
    body.setSpacing(16)
    jobs = QListWidget()
    jobs.setSpacing(2)
    rows = [("ELSEWORLD_master.mkv", "→ ELSEWORLD_master.mp4  ·  Fast 1080p30", "ENCODING  42 %", 42),
            ("Interview_A_cam2.mov", "→ Interview_A_cam2.mkv  ·  Paragon · Archive H.265 10-bit", "WAITING", None),
            ("Drone_0042.mp4", "→ Drone_0042.mp4  ·  Fast 1080p30", "WAITING", None),
            ("Teaser_v3.mov", "→ Teaser_v3.mp4  ·  done in 00:03:12  ·  1.24 GB → 312 MB", "DONE", 100),
            ("Old_VHS_rip.avi", "→ Old_VHS_rip.mp4  ·  the source has no video track", "FAILED", None)]
    for name, detail, state, pct in rows:
        item = QListWidgetItem()
        card = QWidget()
        cl = QGridLayout(card)
        cl.setContentsMargins(12, 8, 12, 8)
        cl.setVerticalSpacing(4)
        t = QLabel(name)
        t.setStyleSheet("font-weight: 600;")
        cl.addWidget(t, 0, 0)
        s = QLabel(state)
        colour = {"ENCODING  42 %": theme.LED_ORANGE, "DONE": theme.TEXT, "FAILED": theme.METER_RED}.get(state,
                                                                                                           theme.TEXT_DIM)
        s.setStyleSheet(f"color: {colour}; font-size: 10.5px; font-weight: 600;")
        cl.addWidget(s, 0, 1, Qt.AlignRight)
        cl.addWidget(dim(detail), 1, 0, 1, 2)
        if pct is not None and pct < 100:
            bar = QProgressBar()
            bar.setValue(pct)
            bar.setTextVisible(False)
            bar.setFixedHeight(8)
            cl.addWidget(bar, 2, 0, 1, 2)
        item.setSizeHint(card.sizeHint())
        jobs.addItem(item)
        jobs.setItemWidget(item, card)
    jobs.setCurrentRow(0)
    body.addWidget(jobs, 3)
    side = QFrame()
    side.setStyleSheet(f"QFrame#side {{ background: {theme.DOCK_TOP}; border: 1px solid {theme.PANEL_EDGE}; "
                       f"border-radius: 6px; }}")
    side.setObjectName("side")
    sv = QGridLayout(side)
    sv.setContentsMargins(16, 14, 16, 14)
    sv.setVerticalSpacing(8)
    details = [("Source", "D:\\Footage\\ELSEWORLD_master.mkv"), ("Title", "1  ·  chapters 1-24  ·  01:42:13"),
               ("Destination", "C:\\Users\\Studio\\Videos\\Exports\\ELSEWORLD_master.mp4"), ("Preset", "Fast 1080p30"),
               ("Video", "H.264 (x264)  ·  RF 22  ·  30 FPS peak"), ("Audio", "AAC Stereo 160 kbps  ·  AC3 5.1 passthru"),
               ("Subtitles", "Foreign audio scan, burned in"), ("Started", "14:02:51  ·  elapsed 00:09:16"),
               ("Speed", "63.2 FPS (average 61.8)  ·  ETA 00:12:40")]
    for i, (k, v) in enumerate(details):
        sv.addWidget(field(k), i, 0, Qt.AlignTop)
        lab = QLabel(v)
        if "\\" in v:                                    # a path: one line, shortened in the middle (Qt can't wrap it)
            lab.setText(lab.fontMetrics().elidedText(v, Qt.ElideMiddle, 380))
            lab.setToolTip(v)
        else:
            lab.setWordWrap(True)
        sv.addWidget(lab, i, 1)
    sv.setRowStretch(len(details), 1)
    row = QHBoxLayout()
    row.addWidget(field("When done"))
    row.addWidget(combo("Do nothing", "Sleep", "Shut down", "Quit PR7-HB"), 1)
    sv.addLayout(row, len(details) + 1, 0, 1, 2)
    sv.setColumnStretch(1, 1)
    body.addWidget(side, 2)
    lay.addLayout(body, 1)
    w.resize(1180, 640)
    return w


def shoot(widget, name):
    widget.show()
    app.processEvents()
    widget.grab().save(str(out / name))
    widget.close()


theme.set_finish("obsidian")
style()
shoot(window("summary"), "1_main.png")
theme.set_finish("aurora")
style()
shoot(window("video"), "2_video.png")
theme.set_finish("obsidian")
style()
shoot(queue(), "3_queue.png")
print("ok", out)
