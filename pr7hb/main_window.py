"""PR7-HB's window, HandBrake's way: Open Source -> title / range -> preset -> the seven tabs -> Save as -> Add to
Queue / Start. The working preset (`self.preset`, a HandBrake preset dict) is what the tabs edit; a job is that preset
plus the source, title, range, destination and the explicit tracks.

Everything that asks goes through `_ask(kind, payload)` (tests set `answers[kind]`); scans and the preset reading
run on worker threads unless `sync` is True (tests)."""

from __future__ import annotations

import copy
import os
import subprocess
import sys
import threading

from PySide6.QtCore import QObject, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QAction, QActionGroup, QDesktopServices, QKeySequence
from PySide6.QtWidgets import (QApplication, QComboBox, QDoubleSpinBox, QFileDialog, QFrame, QGridLayout,
                               QHBoxLayout, QInputDialog, QLabel, QLineEdit, QMainWindow, QMessageBox, QProgressBar,
                               QPushButton, QTabWidget, QVBoxLayout, QWidget)

from . import __version__, engine, family, finish, presets, queue, settings, tabs, theme, widgets
from .dialogs import (WHEN_DONE, LogWindow, OptionsDialog, PresetsDialog, PreviewWindow, QueueWindow,
                      SavePresetDialog, toolbar)
from .preview import PreviewPanel

VIDEO_EXTS = {"mp4", "m4v", "mkv", "mov", "avi", "wmv", "webm", "mpg", "mpeg", "ts", "m2ts", "mts", "flv", "vob", "3gp",
              "ogv", "mxf", "dv", "divx", "asf", "rm", "rmvb", "f4v", "y4m"}
LIVE_SECONDS = 15


class _Bridge(QObject):
    scanned = Signal(object, object, object)       # path, titles | None, error | None
    presets_read = Signal(object, object)          # list of presets, error


def is_disc_folder(path: str) -> bool:
    return os.path.isdir(path) and (os.path.basename(path.rstrip("\\/")).upper() in ("VIDEO_TS", "BDMV")
                                    or any(os.path.isdir(os.path.join(path, d)) for d in ("VIDEO_TS", "BDMV")))


def videos_in(folder: str) -> list[str]:
    try:
        names = sorted(os.listdir(folder), key=str.casefold)
    except OSError:
        return []
    return [os.path.join(folder, n) for n in names
            if n.rsplit(".", 1)[-1].lower() in VIDEO_EXTS and os.path.isfile(os.path.join(folder, n))]


def free_name(path: str) -> str:
    root, ext = os.path.splitext(path)
    n = 2
    while os.path.exists(path):
        path = f"{root} ({n}){ext}"
        n += 1
    return path


class MainWindow(QMainWindow):
    def __init__(self, cli: str | None = None, sync: bool = False):
        super().__init__()
        self.sync = sync
        self.answers: dict = {}
        self.said: list = []
        self.bridge = _Bridge()
        self.bridge.scanned.connect(self._scanned)
        self.bridge.presets_read.connect(self._presets_read)
        try:
            self.cli = cli or engine.find_cli()
        except engine.EngineNotFound:
            self.cli = None
        self.engine_version = ""
        self.caps: engine.Capabilities | None = None
        self.builtin: list[presets.Preset] = []
        self.preset: dict = {}
        self.preset_name = ""
        self.modified = False
        self.titles: list[engine.Title] = []
        self.title: engine.Title | None = None
        self.source = ""
        self.batch: list[str] = []
        self.audio_tracks: list[engine.AudioTrack] = []
        self.subtitle_tracks: list[engine.SubtitleTrack] = []
        self.chapter_names: list[str] = []
        self.dest_edited = False
        self.queue = queue.Queue(self.cli, self)
        self.queue.changed.connect(self._queue_changed)
        self.queue.done.connect(self._queue_done)
        self.preview_queue = queue.Queue(self.cli, self)
        self.preview_queue.changed.connect(self._preview_changed)
        self.queue_window: QueueWindow | None = None
        self.log_window: LogWindow | None = None
        self.preview_window: PreviewWindow | None = None
        self.setWindowTitle("Paragon PR7-HB")
        self.resize(1180, 880)
        self._build()
        self.restyle()
        if self.cli:
            try:
                self.engine_version = engine.version(self.cli)
                self.caps = engine.capabilities(self.cli)
            except (OSError, subprocess.SubprocessError):
                self.caps = None
        self._load_presets()
        self._enable()

    # ================================================================ building
    def _build(self):
        central = QWidget()
        central.setObjectName("central")
        self.setCentralWidget(central)
        lay = QVBoxLayout(central)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        self.header = widgets.Header("VIDEO CONVERTER")
        lay.addWidget(self.header)
        bar, self.keys = toolbar([[("open", "open", "Open Source")],
                                  [("add", "add", "Add to Queue"), ("start", "play", "Start"),
                                   ("pause", "pause", "Pause")],
                                  [("queue", "playlist", "Queue"), ("preview", "eye", "Preview"),
                                   ("log", "file", "Activity Log")],
                                  [("presets", "list", "Presets")]], self)
        lay.addWidget(bar)
        self.keys["open"].clicked.connect(self.open_source_dialog)
        self.keys["add"].clicked.connect(self.add_to_queue)
        self.keys["start"].clicked.connect(self.start_encode)
        self.keys["pause"].clicked.connect(self.pause_encode)
        self.keys["queue"].clicked.connect(self.show_queue)
        self.keys["preview"].clicked.connect(self.show_preview)
        self.keys["log"].clicked.connect(self.show_log)
        self.keys["presets"].clicked.connect(self.show_presets)

        src = QWidget()
        g = QGridLayout(src)
        g.setContentsMargins(18, 4, 18, 4)
        g.setHorizontalSpacing(10)
        g.setVerticalSpacing(8)
        g.addWidget(tabs.field("Source"), 0, 0)
        self.source_name = QLabel("Open a video file or a disc folder")
        self.source_name.setStyleSheet("font-weight: 600; font-size: 13px;")
        g.addWidget(self.source_name, 0, 1, 1, 3)
        self.source_info = tabs.dim("")
        g.addWidget(self.source_info, 0, 4, 1, 6)
        g.addWidget(tabs.field("Title"), 1, 0)
        self.title_box = QComboBox()
        self.title_box.setMinimumWidth(190)
        self.title_box.currentIndexChanged.connect(self._title_chosen)
        g.addWidget(self.title_box, 1, 1)
        g.addWidget(tabs.field("Range"), 1, 2, Qt.AlignmentFlag.AlignRight)
        self.range_mode = tabs.Choice()
        self.range_mode.set_items([("chapters", "Chapters"), ("seconds", "Seconds"), ("frames", "Frames")])
        self.range_mode.setFixedWidth(110)
        self.range_mode.currentIndexChanged.connect(self._range_mode)
        g.addWidget(self.range_mode, 1, 3)
        self.range_a, self.range_b = QDoubleSpinBox(), QDoubleSpinBox()
        for s in (self.range_a, self.range_b):
            s.setFixedWidth(96)
            s.setDecimals(0)
            s.valueChanged.connect(self._range_changed)
        g.addWidget(self.range_a, 1, 4)
        g.addWidget(tabs.dim("through"), 1, 5)
        g.addWidget(self.range_b, 1, 6)
        g.addWidget(tabs.field("Duration"), 1, 7, Qt.AlignmentFlag.AlignRight)
        self.duration = QLabel("--:--:--")
        g.addWidget(self.duration, 1, 8)
        g.addWidget(tabs.field("Preset"), 2, 0)
        self.preset_box = QComboBox()
        self.preset_box.setMinimumWidth(320)
        self.preset_box.activated.connect(self._preset_chosen)
        g.addWidget(self.preset_box, 2, 1, 1, 3)
        self.save_preset = QPushButton("Save New Preset")
        self.save_preset.clicked.connect(self.save_new_preset)
        g.addWidget(self.save_preset, 2, 4, 1, 3)
        g.setColumnStretch(9, 1)
        lay.addWidget(src)

        self.preview = PreviewPanel()
        self.preview.live.connect(self.live_preview)
        self.tabs = QTabWidget()
        self.summary_tab = tabs.SummaryTab(self, self.preview)
        self.dims_tab = tabs.DimensionsTab(self)
        self.filters_tab = tabs.FiltersTab(self)
        self.video_tab = tabs.VideoTab(self)
        self.audio_tab = tabs.AudioTab(self)
        self.subs_tab = tabs.SubtitlesTab(self)
        self.chapters_tab = tabs.ChaptersTab(self)
        self.all_tabs = [self.summary_tab, self.dims_tab, self.filters_tab, self.video_tab, self.audio_tab,
                         self.subs_tab, self.chapters_tab]
        for t, name in zip(self.all_tabs, ("SUMMARY", "DIMENSIONS", "FILTERS", "VIDEO", "AUDIO", "SUBTITLES",
                                           "CHAPTERS")):
            self.tabs.addTab(t, name)
        holder = QWidget()
        hl = QVBoxLayout(holder)
        hl.setContentsMargins(16, 8, 16, 0)
        hl.addWidget(self.tabs)
        lay.addWidget(holder, 1)

        dest = QWidget()
        dl = QHBoxLayout(dest)
        dl.setContentsMargins(18, 6, 18, 8)
        dl.setSpacing(10)
        dl.addWidget(tabs.field("Save as"))
        self.dest = QLineEdit()
        self.dest.textEdited.connect(lambda _: setattr(self, "dest_edited", True))
        dl.addWidget(self.dest, 1)
        browse = QPushButton("Browse…")
        browse.clicked.connect(self.browse_dest)
        dl.addWidget(browse)
        lay.addWidget(dest)

        self.status = QFrame()
        self.status.setObjectName("status")
        sl = QHBoxLayout(self.status)
        sl.setContentsMargins(16, 6, 16, 6)
        self.status_field = tabs.field("")
        self.status_bar = QProgressBar()
        self.status_bar.setTextVisible(False)
        self.status_bar.setFixedWidth(260)
        self.status_bar.setRange(0, 1000)
        self.status_text = tabs.dim("Ready")
        self.when_label = tabs.dim("")
        sl.addWidget(self.status_field)
        sl.addWidget(self.status_bar)
        sl.addWidget(self.status_text)
        sl.addStretch(1)
        sl.addWidget(self.when_label)
        lay.addWidget(self.status)
        self.status_bar.hide()
        self._menus()

    def _act(self, menu, text, slot, keys=None, key=None, checkable=False):
        a = QAction(text, self)
        if keys:
            a.setShortcut(QKeySequence(keys))
        a.setCheckable(checkable)
        a.triggered.connect(lambda *_: slot())
        menu.addAction(a)
        if key:
            self.acts[key] = a
        return a

    def _menus(self):
        self.acts: dict[str, QAction] = {}
        mb = self.menuBar()
        m = mb.addMenu("&File")
        self._act(m, "Open Source…", self.open_source_dialog, "Ctrl+O", "open")
        self._act(m, "Open Folder…", self.open_folder_dialog, "Ctrl+Shift+O", "open_folder")
        m.addSeparator()
        self._act(m, "Options…", self.options, "Ctrl+,", "options")
        m.addSeparator()
        self._act(m, "Exit", self.close, "Alt+F4")
        m = mb.addMenu("&Queue")
        self._act(m, "Add to Queue", self.add_to_queue, "Ctrl+B", "add")
        self._act(m, "Add All to Queue", self.add_all, "Ctrl+Shift+B", "add_all")
        m.addSeparator()
        self._act(m, "Start Encoding", self.start_encode, "Ctrl+E", "start")
        self._act(m, "Pause Encoding", self.pause_encode, "Ctrl+Shift+E", "pause")
        self._act(m, "Stop Encoding", self.queue.stop, None, "stop")
        m.addSeparator()
        self._act(m, "Show Queue", self.show_queue, "Ctrl+Q", "queue")
        m = mb.addMenu("&Presets")
        self._act(m, "Presets…", self.show_presets, "Ctrl+T", "presets")
        self._act(m, "Save New Preset…", self.save_new_preset, "Ctrl+S", "save_preset")
        self._act(m, "Make Current the Default", lambda: self.set_default_preset(self.preset_name), None, "default")
        m.addSeparator()
        self._act(m, "Import Presets…", self.import_presets, None, "import")
        m = mb.addMenu("&View")
        self._act(m, "Preview", self.show_preview, "Ctrl+P", "preview")
        self._act(m, "Activity Log", self.show_log, "Ctrl+L", "log")
        m.addSeparator()
        fm = m.addMenu("Finish")
        group = QActionGroup(self)
        self.finish_acts = {}
        for name in ("obsidian", "aurora"):
            a = self._act(fm, name.upper(), lambda n=name: self.set_finish(n), checkable=True)
            group.addAction(a)
            self.finish_acts[name] = a
        self.finish_acts[theme.FINISH].setChecked(True)
        m = mb.addMenu("&Help")
        self._act(m, "Check for Updates…", self.check_updates, None, "updates")
        self._act(m, "About PR7-HB", self.about, None, "about")

    # ================================================================ look
    def restyle(self):
        app = QApplication.instance()
        if app is not None:
            app.setPalette(theme.palette())
            app.setStyleSheet(theme.stylesheet())
        self.centralWidget().setStyleSheet(
            f"QWidget#central {{ background: {theme.BACKGROUND}; }} QLabel#sep {{ background: {theme.PANEL_EDGE}; }} "
            f"QFrame#status {{ background: {theme.TAB_FRAME}; border-top: 1px solid {theme.PANEL_EDGE}; }}")
        self.header.update()
        for w in (self.queue_window,):
            if w is not None:
                w.restyle()
        for a_name, a in getattr(self, "finish_acts", {}).items():
            a.setChecked(a_name == theme.FINISH)

    def set_finish(self, name: str):
        theme.set_finish(name)
        finish.set(theme.FINISH)                 # every family app follows (finish.py)
        settings.set("finish", theme.FINISH)
        self.restyle()

    # ================================================================ asking
    def _ask(self, kind: str, payload=None):
        if kind in self.answers:
            a = self.answers[kind]
            return a(payload) if callable(a) else a
        if kind == "confirm":
            return QMessageBox.question(self, "PR7-HB", payload) == QMessageBox.StandardButton.Yes
        if kind == "overwrite":
            box = QMessageBox(QMessageBox.Icon.Question, "PR7-HB", f"{payload} already exists. Replace it?",
                              parent=self)
            rep = box.addButton("Replace", QMessageBox.ButtonRole.AcceptRole)
            ren = box.addButton("Add a Number", QMessageBox.ButtonRole.ActionRole)
            box.addButton(QMessageBox.StandardButton.Cancel)
            box.exec()
            return "replace" if box.clickedButton() is rep else "rename" if box.clickedButton() is ren else None
        if kind == "open_file":
            return QFileDialog.getOpenFileName(self, "Open Source", payload or "",
                                               "Videos (" + " ".join(f"*.{e}" for e in sorted(VIDEO_EXTS))
                                               + ");;All files (*)")[0]
        if kind == "folder":
            return QFileDialog.getExistingDirectory(self, "Choose a Folder", payload or "")
        if kind == "save_file":
            name, filt = payload
            return QFileDialog.getSaveFileName(self, "Save", name, filt)[0]
        if kind == "open_any":
            return QFileDialog.getOpenFileName(self, "Open", "", payload)[0]
        if kind == "save_preset":
            d = SavePresetDialog(self, payload)
            return (d.name.text().strip(), d.desc.text().strip(), d.default.isChecked()) if d.exec() else None
        if kind == "text":
            text, ok = QInputDialog.getText(self, "PR7-HB", payload)
            return text if ok else None
        return None

    def _say(self, kind: str, text: str):
        self.said.append((kind, text))
        if "say" in self.answers:
            self.answers["say"](kind, text)
            return
        icon = QMessageBox.Icon.Warning if kind == "error" else QMessageBox.Icon.Information
        QMessageBox(icon, "PR7-HB", text, parent=self).exec()

    def _background(self, fn, done):
        if self.sync:
            done(*fn())
            return
        threading.Thread(target=lambda: done(*fn()), daemon=True).start()

    # ================================================================ presets
    def _load_presets(self):
        if not self.cli:
            self._presets_read([], "HandBrakeCLI wasn't found")
            return
        self.status_text.setText("Reading HandBrake's presets…")

        def work():
            try:
                return presets.builtin(self.cli), None
            except Exception as e:      # noqa: BLE001 - shown to the user, never fatal
                return [], str(e)
        self._background(work, lambda got, err: self.bridge.presets_read.emit(got, err))

    def _presets_read(self, got, err):
        self.builtin = got or []
        if err:
            self.status_text.setText(f"No engine: {err}")
        else:
            self.status_text.setText("Ready")
        self.fill_preset_box()
        self.choose_preset(self.default_preset())

    def all_presets(self) -> list[presets.Preset]:
        shown = presets.usable(self.builtin, self.caps.video) if self.caps else list(self.builtin)
        return shown + presets.user()

    def default_preset(self) -> str:
        name = settings.get("default_preset", presets.DEFAULT)
        return name if presets.find(self.all_presets(), name) else presets.DEFAULT

    def set_default_preset(self, name: str):
        if presets.find(self.all_presets(), name):
            settings.set("default_preset", name)
            self.fill_preset_box()

    def presets_changed(self):
        self.fill_preset_box()

    def fill_preset_box(self):
        box = self.preset_box
        box.blockSignals(True)
        box.clear()
        last = None
        for p in self.all_presets():
            if p.category != last:
                if last is not None:
                    box.insertSeparator(box.count())
                box.addItem(p.category.upper(), None)
                item = box.model().item(box.count() - 1)
                if item is not None:
                    item.setEnabled(False)
                last = p.category
            box.addItem("    " + p.name, p.name)
        self._show_preset_name()
        box.blockSignals(False)

    def _show_preset_name(self):
        box = self.preset_box
        i = box.findData(self.preset_name)
        if i >= 0:
            box.setItemText(i, "    " + self.preset_name + ("  (modified)" if self.modified else ""))
            box.setCurrentIndex(i)
        for j in range(box.count()):
            d = box.itemData(j)
            if d and d != self.preset_name:
                box.setItemText(j, "    " + d)

    def _preset_chosen(self, index: int):
        name = self.preset_box.itemData(index)
        if name:
            self.choose_preset(name)

    def choose_preset(self, name: str):
        p = presets.find(self.all_presets(), name) or presets.find(self.all_presets(), presets.DEFAULT)
        if p is None:
            return
        self.preset = copy.deepcopy(p.settings)
        self.preset_name = p.name
        self.modified = False
        self.reset_tracks(reload=False)
        self._show_preset_name()
        self._update_dest()
        self.reload_tabs()

    def preset_edited(self, sender=None):
        self.modified = True
        self._show_preset_name()
        if sender is self.summary_tab:
            self._update_dest()
        for t in self.all_tabs:
            if t is not sender and t not in (self.audio_tab, self.subs_tab):
                t.load()
        if sender is self.summary_tab:
            self.summary_tab.load()
        self.preview.set_crop(self._crop())

    def save_new_preset(self):
        got = self._ask("save_preset", self.preset_name + (" (custom)" if not self.modified else ""))
        if not got:
            return
        name, desc, default = got
        if not name:
            return
        if any(p.name == name and p.builtin for p in self.all_presets()):
            self._say("error", f'"{name}" is one of HandBrake\'s own presets. Choose another name.')
            return
        presets.save_user(presets.Preset(name, presets.USER_CATEGORY, desc, copy.deepcopy(self.preset), False))
        self.preset_name, self.modified = name, False
        self.preset["PresetName"] = name
        if default:
            settings.set("default_preset", name)
        self.fill_preset_box()

    def import_presets(self):
        path = self._ask("open_any", "HandBrake presets (*.json);;All files (*)")
        if not path:
            return
        try:
            got = presets.import_file(path)
        except (OSError, ValueError) as e:
            self._say("error", f"That file isn't a HandBrake preset file ({e}).")
            return
        self.fill_preset_box()
        self._say("info", f"Imported {len(got)} preset{'s' if len(got) != 1 else ''}.")

    # ================================================================ source
    def open_source_dialog(self):
        path = self._ask("open_file", os.path.dirname(self.source) if self.source else "")
        if path:
            self.open_source(path)

    def open_folder_dialog(self):
        path = self._ask("folder", os.path.dirname(self.source) if self.source else "")
        if path:
            self.open_source(path)

    def open_source(self, path: str):
        """A file, a disc folder (VIDEO_TS / BDMV) or a folder of videos (a batch: Add All queues each one)."""
        path = os.path.abspath(path)
        if os.path.isdir(path) and not is_disc_folder(path):
            files = videos_in(path)
            if not files:
                self._say("error", f"There are no videos in {path}.")
                return
            self.batch = files
            path = files[0]
        else:
            self.batch = []
        if not self.cli:
            self._say("error", "HandBrakeCLI wasn't found, so nothing can be scanned.")
            return
        self.source_name.setText(os.path.basename(path.rstrip("\\/")))
        self.source_info.setText("Scanning…")
        self._enable(scanning=True)

        def work():
            try:
                return path, engine.scan(self.cli, path), None
            except (engine.ScanFailed, OSError, subprocess.SubprocessError) as e:
                return path, None, str(e)
        self._background(work, lambda p, t, e: self.bridge.scanned.emit(p, t, e))

    def _scanned(self, path, titles, error):
        if error or not titles:
            self.source_info.setText("")
            self.source_name.setText("Open a video file or a disc folder")
            self.titles, self.title, self.source = [], None, ""
            self._enable()
            self._say("error", error or "No titles found.")
            return
        self.source = path
        self.titles = titles
        self.title_box.blockSignals(True)
        self.title_box.clear()
        for t in titles:
            self.title_box.addItem(t.label(), t.index)
        self.title_box.blockSignals(False)
        self.dest_edited = False
        self.load_title(titles[0])
        if self.batch:
            self.source_info.setText(self.source_info.text() + f"  ·  folder of {len(self.batch)} videos")

    def _title_chosen(self, i: int):
        if 0 <= i < len(self.titles):
            self.load_title(self.titles[i])

    def load_title(self, t: engine.Title):
        self.title = t
        self.source_info.setText(t.describe())
        self.range_mode.set_value("chapters")
        self._range_mode()
        self.chapter_names = [name or f"Chapter {i}" for i, (name, _) in enumerate(t.chapters, 1)]
        self.reset_tracks(reload=False)
        self._update_dest()
        self.reload_tabs()
        self.preview.load(t)
        self.preview.set_crop(self._crop())
        self._enable()

    def _crop(self):
        t, p = self.title, self.preset
        if t is None:
            return (0, 0, 0, 0)
        mode = p.get("PictureCropMode", 0)
        if mode in (0, 1):
            return t.crop
        if mode == 3:
            return (p.get("PictureTopCrop", 0), p.get("PictureBottomCrop", 0), p.get("PictureLeftCrop", 0),
                    p.get("PictureRightCrop", 0))
        return (0, 0, 0, 0)

    def _range_mode(self, *_):
        t, mode = self.title, self.range_mode.value()
        for s in (self.range_a, self.range_b):
            s.blockSignals(True)
        if t is None:
            hi = 1
        elif mode == "chapters":
            hi = max(1, len(t.chapters))
        elif mode == "seconds":
            hi = max(1, int(t.duration))
        else:
            hi = max(1, t.frames)
        lo = 1 if mode == "chapters" else 0
        for s in (self.range_a, self.range_b):
            s.setRange(lo, hi)
            s.setSuffix(" s" if mode == "seconds" else "")
        self.range_a.setValue(lo)
        self.range_b.setValue(hi)
        for s in (self.range_a, self.range_b):
            s.blockSignals(False)
        self._range_changed()

    def _range_changed(self, *_):
        a, b = self.range_a.value(), self.range_b.value()
        if b < a:
            self.range_b.blockSignals(True)
            self.range_b.setValue(a)
            self.range_b.blockSignals(False)
            b = a
        self.duration.setText(engine.hms(self.covered()) if self.title else "--:--:--")

    def covered(self) -> float:
        """Seconds the chosen range covers."""
        t = self.title
        if t is None:
            return 0.0
        mode, a, b = self.range_mode.value(), self.range_a.value(), self.range_b.value()
        if mode == "chapters":
            return sum(sec for _, sec in t.chapters[int(a) - 1:int(b)]) or t.duration
        if mode == "seconds":
            return b - a
        return (b - a) / t.fps if t.fps else 0.0

    # ================================================================ tracks
    def reset_tracks(self, reload: bool = True):
        if self.title is None:
            self.audio_tracks, self.subtitle_tracks = [], []
        else:
            self.audio_tracks = engine.default_audio(self.preset, self.title)
            self.subtitle_tracks = engine.default_subtitles(self.preset, self.title)
        if reload:
            self.tracks_edited()

    def tracks_edited(self, reload: bool = True):
        if reload:
            self.audio_tab.load()
            self.subs_tab.load()
        self.summary_tab.refresh()

    def import_subtitles(self):
        path = self._ask("open_any", "Subtitles (*.srt *.ass *.ssa);;All files (*)")
        if path:
            lang = "und"
            low = os.path.basename(path).lower()
            for code in ("eng", "fra", "deu", "spa", "ita", "nld", "por", "jpn"):
                if f".{code}." in low or low.endswith(f".{code}.srt"):
                    lang = code
            self.subtitle_tracks.append(engine.SubtitleTrack(path, language=lang))
            self.tracks_edited()

    def import_chapters(self):
        path = self._ask("open_any", "Chapter names (*.csv);;All files (*)")
        if path:
            names = tabs.read_chapter_csv(path)
            for i, n in enumerate(names):
                if i < len(self.chapter_names):
                    self.chapter_names[i] = n or self.chapter_names[i]
            self.chapters_tab.load()

    def export_chapters(self):
        path = self._ask("save_file", ("chapters.csv", "Chapter names (*.csv)"))
        if path:
            tabs.write_chapter_csv(path, self.chapter_names)

    def reload_tabs(self):
        for t in self.all_tabs:
            t.load()

    # ================================================================ destination
    def output_folder(self) -> str:
        folder = settings.get("output_folder", "")
        if folder:
            return folder
        videos = os.path.join(os.path.expanduser("~"), "Videos")
        return videos if os.path.isdir(videos) else os.path.expanduser("~")

    def _update_dest(self):
        if not self.source:
            return
        if self.dest_edited and self.dest.text():
            self.dest.setText(engine.with_extension(self.dest.text(), self.preset))
            return
        t = self.title.index if self.title else 1
        self.dest.setText(engine.dest_name(self.source, self.preset, self.output_folder(),
                                           settings.get("name_pattern", "{source}"), t))

    def browse_dest(self):
        ext = engine.CONTAINERS.get(self.preset.get("FileFormat", "av_mp4"), ("MP4", ".mp4"))
        path = self._ask("save_file", (self.dest.text(), f"{ext[0]} files (*{ext[1]})"))
        if path:
            self.dest.setText(engine.with_extension(path, self.preset))
            self.dest_edited = True

    # ================================================================ jobs
    def make_job(self, source: str | None = None, title: engine.Title | None = None,
                 dest: str | None = None) -> engine.Job | None:
        t = title or self.title
        if t is None:
            self._say("error", "Open a source first.")
            return None
        dest = dest or self.dest.text().strip()
        if not dest:
            self._say("error", "Choose where to save the video (Save as).")
            return None
        src = source or self.source
        if os.path.abspath(dest) == os.path.abspath(src):
            self._say("error", "The destination is the source file. Choose another name.")
            return None
        same_title = t is self.title
        if same_title:
            mode, a, b = self.range_mode.value(), self.range_a.value(), self.range_b.value()
        else:
            mode, a, b = "chapters", 1, max(1, len(t.chapters))
        p = copy.deepcopy(self.preset)
        p["PresetName"] = self.preset_name + (" (modified)" if self.modified else "")
        audio = copy.deepcopy(self.audio_tracks) if same_title else engine.default_audio(self.preset, t)
        subs = copy.deepcopy(self.subtitle_tracks) if same_title else engine.default_subtitles(self.preset, t)
        names = list(self.chapter_names) if same_title else None
        return engine.Job(src, t.index, dest, p, mode, a, b, audio=audio, subtitles=subs, chapter_names=names,
                          source_name=os.path.basename(src), duration=self.covered() if same_title else t.duration)

    def _settle_dest(self, job: engine.Job) -> bool:
        """The destination is free (or the user said what to do): False to cancel."""
        taken = os.path.exists(job.dest) or any(i.job.dest == job.dest and i.state != queue.DONE
                                                for i in self.queue.items)
        if not taken:
            return True
        rule = settings.get("when_exists", "ask")
        if rule == "ask":
            rule = self._ask("overwrite", os.path.basename(job.dest))
        if rule == "rename":
            used = {i.job.dest for i in self.queue.items}
            d = free_name(job.dest)
            while d in used:
                d = free_name(os.path.splitext(d)[0] + " " + os.path.splitext(d)[1])
            job.dest = d
            return True
        return rule in ("replace", "overwrite")

    def add_to_queue(self) -> queue.Item | None:
        job = self.make_job()
        if job is None or not self._settle_dest(job):
            return None
        return self.queue.add(job)

    def add_all(self) -> int:
        """Every title of a disc, or every video of an opened folder, with the current settings."""
        added = 0
        if self.batch:
            for path in self.batch:
                try:
                    t = engine.scan(self.cli, path)[0] if path != self.source else self.title
                except (engine.ScanFailed, OSError, subprocess.SubprocessError):
                    continue
                dest = engine.dest_name(path, self.preset, os.path.dirname(self.dest.text()) or self.output_folder(),
                                        settings.get("name_pattern", "{source}"))
                job = self.make_job(path, t, dest)
                if job and self._settle_dest(job):
                    self.queue.add(job)
                    added += 1
        else:
            for t in self.titles:
                root, ext = os.path.splitext(self.dest.text())
                dest = self.dest.text() if len(self.titles) == 1 else f"{root} - title {t.index}{ext}"
                job = self.make_job(None, t, dest)
                if job and self._settle_dest(job):
                    self.queue.add(job)
                    added += 1
        return added

    def start_encode(self):
        """HandBrake's Start: the queue if it has work, else the current job."""
        if self.queue.paused:
            self.queue.resume()
            return
        if not self.queue.waiting() and self.queue.current is None:
            if self.add_to_queue() is None:
                return
        if settings.get_bool("show_queue", False):
            self.show_queue()
        self.queue.start()

    def pause_encode(self):
        if self.queue.paused:
            self.queue.resume()
        else:
            self.queue.pause()

    def _queue_changed(self, item):
        cur = self.queue.current
        if cur is not None:
            n = self.queue.items.index(cur) + 1 if cur in self.queue.items else 1
            total = len([i for i in self.queue.items if i.state in (queue.WAITING, queue.ENCODING, queue.PAUSED)])
            done = len([i for i in self.queue.items[:n - 1] if i.state != queue.WAITING])
            self.status_field.setText(("PAUSED" if self.queue.paused else "ENCODING")
                                      + f" {done + 1} OF {done + total}")
            self.status_bar.show()
            self.status_bar.setValue(int(cur.progress.fraction * 1000))
            self.status_text.setText(cur.progress.text())
        else:
            self.status_field.setText("")
            self.status_bar.hide()
            waiting = len(self.queue.waiting())
            self.status_text.setText(f"Ready  ·  {waiting} job{'s' if waiting != 1 else ''} in the queue" if waiting
                                     else "Ready")
        if item is not None and item.state == queue.DONE and settings.get_bool("clear_done", False):
            QTimer.singleShot(0, lambda: self.queue.remove(item) if item in self.queue.items else None)
        when = self.queue_window.when_done() if self.queue_window else "nothing"
        self.when_label.setText(f"When done: {dict(WHEN_DONE)[when]}"
                                if cur is not None else "")
        self._enable()

    def _queue_done(self):
        failed = [i for i in self.queue.items if i.state == queue.FAILED]
        when = self.queue_window.when_done() if self.queue_window else "nothing"
        if failed and when == "nothing":
            self._say("error", f"{len(failed)} job{'s' if len(failed) != 1 else ''} failed: "
                      + "; ".join(f"{i.name()} ({i.error})" for i in failed[:3]))
        self.when_done(when)

    def when_done(self, action: str):
        """HandBrake's When done: nothing, sleep, shut down (a minute's warning, cancellable) or quit."""
        run = self.answers.get("system", lambda args: subprocess.Popen(args, creationflags=engine.NO_WINDOW))
        if action == "quit":
            QTimer.singleShot(0, self.close)
        elif action == "shutdown" and sys.platform == "win32":
            run(["shutdown", "/s", "/t", "60", "/c", "PR7-HB finished encoding. Run 'shutdown /a' to cancel."])
        elif action == "sleep" and sys.platform == "win32":
            run(["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"])
        elif action in ("shutdown", "sleep"):
            run(["systemctl", "poweroff" if action == "shutdown" else "suspend"])

    # ================================================================ live preview
    def live_preview(self, at: float):
        """A short encode with these settings from the preview's place, opened in PR7-M (the family's player) when
        it's installed, else the default player."""
        if self.title is None:
            return
        folder = os.path.join(presets.data_dir(), "preview")
        os.makedirs(folder, exist_ok=True)
        ext = engine.CONTAINERS.get(self.preset.get("FileFormat", "av_mp4"), ("MP4", ".mp4"))[1]
        dest = os.path.join(folder, f"live preview{ext}")
        end = min(self.title.duration, at + LIVE_SECONDS)
        job = engine.Job(self.source, self.title.index, dest, copy.deepcopy(self.preset), "seconds", at, end,
                         audio=copy.deepcopy(self.audio_tracks), subtitles=copy.deepcopy(self.subtitle_tracks))
        if self.preview_queue.current is not None:
            self.preview_queue.stop()
        self.preview_queue.items.clear()
        if os.path.exists(dest):
            try:
                os.remove(dest)
            except OSError:
                pass
        self.preview_queue.add(job)
        self.preview_queue.start()

    def _preview_changed(self, item):
        if item is None:
            return
        if item.state == queue.ENCODING:
            self.preview.picture.caption = f"LIVE PREVIEW  ·  ENCODING {item.progress.fraction * 100:.0f} %"
            self.preview.picture.update()
        elif item.state == queue.DONE:
            self.preview.show_index(self.preview.index)
            self.open_media(item.job.dest)
        elif item.state == queue.FAILED:
            self.preview.show_index(self.preview.index)
            self._say("error", f"The live preview couldn't be made: {item.error}")

    def open_media(self, path: str):
        launch = self.answers.get("launch", family.launch)
        if launch("PR7-M", [path]):
            return
        opener = self.answers.get("url", QDesktopServices.openUrl)
        opener(QUrl.fromLocalFile(path))

    # ================================================================ other windows
    def show_queue(self):
        if self.queue_window is None:
            self.queue_window = QueueWindow(self)
        self.queue_window.show()
        self.queue_window.raise_()
        return self.queue_window

    def show_log(self):
        if self.log_window is None:
            self.log_window = LogWindow(self)
        cur = self.queue.current or (self.queue.items[-1] if self.queue.items else None)
        self.log_window.show_item(cur)
        self.log_window.show()
        self.log_window.raise_()
        return self.log_window

    def show_presets(self):
        d = PresetsDialog(self)
        if "presets" in self.answers:
            return self.answers["presets"](d)
        d.exec()
        return d

    def show_preview(self):
        if self.preview_window is None:
            self.preview_window = PreviewWindow(self, self.preview)
        self.preview_window.sync()
        self.preview_window.show()
        self.preview_window.raise_()
        return self.preview_window

    def options(self):
        d = OptionsDialog(self)
        if "options" in self.answers:
            self.answers["options"](d)
            d.save(self)
            return d
        if d.exec():
            d.save(self)
            self._update_dest()
        return d

    def check_updates(self):
        from . import update_ui
        update_ui.check(self, manual=True)

    def about(self):
        self._say("info", f"Paragon PR7-HB {__version__}\nA video converter that works the way HandBrake works.\n"
                          f"Engine: HandBrake {self.engine_version or '(not found)'} (HandBrakeCLI, GPL 2), "
                          "unmodified.")

    # ================================================================ state
    def _enable(self, scanning: bool = False):
        have = self.title is not None and not scanning
        for k in ("add", "start"):
            self.keys[k].setEnabled(have or (k == "start" and bool(self.queue.waiting())))
        self.keys["pause"].setEnabled(self.queue.current is not None)
        self.keys["preview"].setEnabled(have)
        self.keys["open"].setEnabled(not scanning and bool(self.cli))
        for k in ("add", "add_all"):
            self.acts[k].setEnabled(have)
        self.acts["add_all"].setEnabled(have and (bool(self.batch) or len(self.titles) > 1))
        self.acts["pause"].setEnabled(self.queue.current is not None)
        self.acts["stop"].setEnabled(self.queue.current is not None)
        self.title_box.setEnabled(have and len(self.titles) > 1)
        for w in (self.range_mode, self.range_a, self.range_b):
            w.setEnabled(have)

    def closeEvent(self, e):
        if self.queue.current is not None and not self._ask("confirm", "An encode is running. Stop it and quit?"):
            e.ignore()
            return
        self.queue.stop()
        self.preview_queue.stop()
        if self.preview.grabber is not None:
            self.preview.grabber.stop()
        for w in (self.queue_window, self.log_window, self.preview_window):
            if w is not None:
                w.close()
        super().closeEvent(e)

