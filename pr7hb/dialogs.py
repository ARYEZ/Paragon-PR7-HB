"""PR7-HB's other windows: the Queue, the Activity log, Presets, Save new preset, Options and the bigger Preview."""

from __future__ import annotations

import os

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QDesktopServices, QFont
from PySide6.QtCore import QUrl
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFrame, QGridLayout, QHBoxLayout,
                               QLabel, QLineEdit, QListWidget, QListWidgetItem, QPlainTextEdit, QProgressBar,
                               QPushButton, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget)

from . import engine, presets, queue, theme, widgets

WHEN_DONE = [("nothing", "Do nothing"), ("sleep", "Sleep"), ("shutdown", "Shut down"), ("quit", "Quit PR7-HB")]


def field(text: str) -> QLabel:
    lab = QLabel(text.upper())
    lab.setProperty("role", "field")
    return lab


def dim(text: str) -> QLabel:
    lab = QLabel(text)
    lab.setProperty("role", "dim")
    return lab


def toolbar(keys, owner) -> tuple[QWidget, dict]:
    bar = QWidget()
    lay = QHBoxLayout(bar)
    lay.setContentsMargins(16, 10, 16, 6)
    lay.setSpacing(6)
    made = {}
    for i, group in enumerate(keys):
        if i:
            sep = QLabel()
            sep.setFixedSize(1, 40)
            sep.setObjectName("sep")
            lay.addSpacing(8)
            lay.addWidget(sep)
            lay.addSpacing(8)
        for name, icon, label in group:
            k = widgets.KeyButton(icon, label)
            k.setFixedSize(QSize(92, 62))
            made[name] = k
            lay.addWidget(k)
    lay.addStretch(1)
    return bar, made


# --------------------------------------------------------------------------- the Queue
class JobCard(QWidget):
    def __init__(self, item: queue.Item):
        super().__init__()
        self.item = item
        g = QGridLayout(self)
        g.setContentsMargins(12, 8, 12, 8)
        g.setVerticalSpacing(4)
        self.title = QLabel()
        self.title.setStyleSheet("font-weight: 600;")
        g.addWidget(self.title, 0, 0)
        self.state = QLabel()
        g.addWidget(self.state, 0, 1, Qt.AlignmentFlag.AlignRight)
        self.detail = dim("")
        g.addWidget(self.detail, 1, 0, 1, 2)
        self.bar = QProgressBar()
        self.bar.setTextVisible(False)
        self.bar.setFixedHeight(8)
        g.addWidget(self.bar, 2, 0, 1, 2)
        self.refresh()

    def refresh(self):
        it = self.item
        self.title.setText(it.name())
        self.state.setText(it.state_text())
        colour = {queue.ENCODING: theme.LED_ORANGE, queue.PAUSED: theme.LED_ORANGE, queue.DONE: theme.TEXT,
                  queue.FAILED: theme.METER_RED}.get(it.state, theme.TEXT_DIM)
        self.state.setStyleSheet(f"color: {colour}; font-size: 10.5px; font-weight: 600;")
        self.detail.setText(it.detail())
        busy = it.state in (queue.ENCODING, queue.PAUSED)
        self.bar.setVisible(busy)
        self.bar.setValue(int(it.progress.fraction * 1000))
        self.bar.setRange(0, 1000)


class QueueWindow(QWidget):
    def __init__(self, win):
        super().__init__(None, Qt.WindowType.Window)
        self.win = win
        self.q: queue.Queue = win.queue
        self.setWindowTitle("Queue · PR7-HB")
        self.resize(1080, 620)
        self.setObjectName("queuewin")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        self.header = widgets.Header("QUEUE")
        lay.addWidget(self.header)
        bar, self.keys = toolbar([[("start", "play", "Start Queue"), ("pause", "pause", "Pause"),
                                   ("stop", "stop", "Stop")],
                                  [("remove", "close", "Remove"), ("retry", "refresh", "Retry"),
                                   ("clear", "trash", "Clear Done")]], self)
        lay.addWidget(bar)
        body = QHBoxLayout()
        body.setContentsMargins(16, 6, 16, 12)
        body.setSpacing(16)
        self.list = QListWidget()
        self.list.setSpacing(2)
        self.list.currentRowChanged.connect(lambda _: self.show_details())
        body.addWidget(self.list, 3)
        side = QFrame()
        side.setObjectName("side")
        sv = QGridLayout(side)
        sv.setContentsMargins(16, 14, 16, 14)
        sv.setVerticalSpacing(8)
        self.rows = {}
        for i, k in enumerate(("Source", "Title", "Destination", "Preset", "Video", "Audio", "Subtitles",
                               "Started", "Speed")):
            sv.addWidget(field(k), i, 0, Qt.AlignmentFlag.AlignTop)
            v = QLabel("")
            v.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            sv.addWidget(v, i, 1)
            self.rows[k] = v
        sv.setRowStretch(9, 1)
        row = QHBoxLayout()
        row.addWidget(field("When done"))
        self.when = QComboBox()
        for v, label in WHEN_DONE:
            self.when.addItem(label, v)
        row.addWidget(self.when, 1)
        sv.addLayout(row, 10, 0, 1, 2)
        sv.setColumnStretch(1, 1)
        body.addWidget(side, 2)
        lay.addLayout(body, 1)
        self.keys["start"].clicked.connect(self.q.start)
        self.keys["pause"].clicked.connect(lambda: self.q.resume() if self.q.paused else self.q.pause())
        self.keys["stop"].clicked.connect(self.q.stop)
        self.keys["remove"].clicked.connect(lambda: self._on_current(self.q.remove))
        self.keys["retry"].clicked.connect(lambda: self._on_current(self.q.retry))
        self.keys["clear"].clicked.connect(self.q.clear_done)
        self.q.changed.connect(self.changed)
        self.restyle()
        self.rebuild()

    def restyle(self):
        self.setStyleSheet(f"QWidget#queuewin {{ background: {theme.BACKGROUND}; }} "
                           f"QFrame#side {{ background: {theme.DOCK_TOP}; border: 1px solid {theme.PANEL_EDGE}; "
                           f"border-radius: 6px; }} QLabel#sep {{ background: {theme.PANEL_EDGE}; }}")
        self.header.update()
        self.rebuild()

    def _on_current(self, fn):
        it = self.current()
        if it is not None:
            fn(it)

    def current(self) -> queue.Item | None:
        row = self.list.currentRow()
        return self.q.items[row] if 0 <= row < len(self.q.items) else None

    def rebuild(self):
        keep = self.current()
        self.list.clear()
        for it in self.q.items:
            li = QListWidgetItem()
            card = JobCard(it)
            li.setSizeHint(card.sizeHint())
            self.list.addItem(li)
            self.list.setItemWidget(li, card)
        if self.q.items:
            self.list.setCurrentRow(self.q.items.index(keep) if keep in self.q.items else 0)
        self.show_details()
        self._enable()

    def changed(self, item):
        if item is None or self.list.count() != len(self.q.items):
            self.rebuild()
            return
        if item in self.q.items:
            row = self.q.items.index(item)
            card = self.list.itemWidget(self.list.item(row))
            if card is not None:
                card.refresh()
        if item is self.current():
            self.show_details()
        self._enable()

    def _enable(self):
        it = self.current()
        self.keys["start"].setEnabled(bool(self.q.waiting()) or self.q.paused)
        self.keys["pause"].setEnabled(self.q.current is not None)
        self.keys["stop"].setEnabled(self.q.current is not None)
        self.keys["remove"].setEnabled(it is not None)
        self.keys["retry"].setEnabled(it is not None and it.state in (queue.FAILED, queue.CANCELLED, queue.DONE))
        self.keys["clear"].setEnabled(any(i.state == queue.DONE for i in self.q.items))

    def show_details(self):
        it = self.current()
        if it is None:
            for v in self.rows.values():
                v.setText("")
            return
        j, p = it.job, it.job.preset
        rng = {"chapters": f"chapters {int(j.start)}-{int(j.end)}", "seconds": f"{engine.hms(j.start)} to "
               f"{engine.hms(j.end)}", "frames": f"frames {int(j.start)}-{int(j.end)}"}[j.range_mode]
        lines = engine.summary(p, j.audio or [], j.subtitles or [])
        audio = [ln.split(": ", 1)[1] for ln in lines if ln.startswith("Track ")]
        subs = [ln for ln in lines[1:] if not ln.startswith("Track ") and ln != "Chapter markers"]
        texts = {"Source": j.source, "Title": f"{j.title}  ·  {rng}", "Destination": j.dest,
                 "Preset": p.get("PresetName", ""), "Video": lines[0], "Audio": "  ·  ".join(audio) or "none",
                 "Subtitles": "  ·  ".join(subs) or "none"}
        import time
        texts["Started"] = time.strftime("%H:%M:%S", time.localtime(it.started)) if it.started else ""
        texts["Speed"] = it.progress.text() if it.state in (queue.ENCODING, queue.PAUSED) else (
            it.error if it.state == queue.FAILED else "")
        for k, v in texts.items():
            lab = self.rows[k]
            full = str(v)
            if "\\" in full or "/" in full and k in ("Source", "Destination"):
                full_e = lab.fontMetrics().elidedText(full, Qt.TextElideMode.ElideMiddle, 380)
                lab.setText(full_e)
                lab.setToolTip(full)
            else:
                lab.setWordWrap(True)
                lab.setText(full)

    def when_done(self) -> str:
        return self.when.currentData()


# --------------------------------------------------------------------------- the Activity log
class LogWindow(QWidget):
    def __init__(self, win):
        super().__init__(None, Qt.WindowType.Window)
        self.win = win
        self.setWindowTitle("Activity Log · PR7-HB")
        self.resize(900, 560)
        lay = QVBoxLayout(self)
        top = QHBoxLayout()
        top.addWidget(field("Activity log"))
        self.which = dim("")
        top.addWidget(self.which, 1)
        self.copy = QPushButton("Copy")
        self.folder = QPushButton("Open Log Folder")
        top.addWidget(self.copy)
        top.addWidget(self.folder)
        lay.addLayout(top)
        self.text = QPlainTextEdit()
        self.text.setReadOnly(True)
        mono = QFont("Consolas" if os.name == "nt" else "DejaVu Sans Mono")
        mono.setStyleHint(QFont.StyleHint.Monospace)
        mono.setPointSize(9)
        self.text.setFont(mono)
        lay.addWidget(self.text, 1)
        self.copy.clicked.connect(lambda: __import__("PySide6.QtWidgets", fromlist=["QApplication"]).QApplication
                                  .clipboard().setText(self.text.toPlainText()))
        self.folder.clicked.connect(self.open_folder)
        self.item: queue.Item | None = None
        win.queue.changed.connect(self._changed)

    def show_item(self, item: queue.Item | None):
        self.item = item
        self.which.setText(f"  {item.name()}  ·  {item.state}" if item else "  nothing encoded yet")
        self.text.setPlainText("\n".join(item.log) if item else "")
        self.text.verticalScrollBar().setValue(self.text.verticalScrollBar().maximum())

    def _changed(self, item):
        if item is not None and (item is self.item or self.item is None or self.item.state != queue.ENCODING):
            if item is self.item and len(item.log) > self.text.blockCount():
                for ln in item.log[self.text.blockCount():]:
                    self.text.appendPlainText(ln)
                self.which.setText(f"  {item.name()}  ·  {item.state}")
            elif item.state == queue.ENCODING:
                self.show_item(item)

    def open_folder(self):
        path = os.path.join(presets.data_dir(), "logs")
        os.makedirs(path, exist_ok=True)
        opener = self.win.answers.get("url", QDesktopServices.openUrl)
        opener(QUrl.fromLocalFile(path))


# --------------------------------------------------------------------------- Presets
class PresetsDialog(QDialog):
    """HandBrake's presets: by category, the user's own under Custom Presets; Apply, Save New, Delete, Make Default,
    Import, Export."""

    def __init__(self, win):
        super().__init__(win)
        self.win = win
        self.setWindowTitle("Presets · PR7-HB")
        self.resize(560, 620)
        lay = QVBoxLayout(self)
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.itemDoubleClicked.connect(lambda *_: self.apply())
        lay.addWidget(self.tree, 1)
        self.desc = dim("")
        self.desc.setWordWrap(True)
        lay.addWidget(self.desc)
        self.tree.currentItemChanged.connect(self._selected)
        keys = QHBoxLayout()
        self.b_apply = QPushButton("Apply")
        self.b_new = QPushButton("Save New…")
        self.b_delete = QPushButton("Delete")
        self.b_default = QPushButton("Make Default")
        self.b_import = QPushButton("Import…")
        self.b_export = QPushButton("Export…")
        for b in (self.b_apply, self.b_new, self.b_delete, self.b_default, self.b_import, self.b_export):
            keys.addWidget(b)
        lay.addLayout(keys)
        self.b_apply.clicked.connect(self.apply)
        self.b_new.clicked.connect(lambda: (win.save_new_preset(), self.fill()))
        self.b_delete.clicked.connect(self.delete)
        self.b_default.clicked.connect(self.make_default)
        self.b_import.clicked.connect(lambda: (win.import_presets(), self.fill()))
        self.b_export.clicked.connect(self.export)
        self.fill()

    def fill(self):
        self.tree.clear()
        cats: dict[str, QTreeWidgetItem] = {}
        default = self.win.default_preset()
        current = None
        for p in self.win.all_presets():
            parent = cats.get(p.category)
            if parent is None:
                parent = QTreeWidgetItem([p.category.upper()])
                parent.setFlags(Qt.ItemFlag.ItemIsEnabled)
                cats[p.category] = parent
                self.tree.addTopLevelItem(parent)
            it = QTreeWidgetItem([p.name + ("  (default)" if p.name == default else "")])
            it.setData(0, Qt.ItemDataRole.UserRole, p.name)
            parent.addChild(it)
            if p.name == self.win.preset_name:
                current = it
        self.tree.expandAll()
        if current is not None:
            self.tree.setCurrentItem(current)

    def selected(self) -> presets.Preset | None:
        it = self.tree.currentItem()
        name = it.data(0, Qt.ItemDataRole.UserRole) if it else None
        return presets.find(self.win.all_presets(), name) if name else None

    def _selected(self, *_):
        p = self.selected()
        self.desc.setText(p.description if p else "")
        for b in (self.b_apply, self.b_default, self.b_export):
            b.setEnabled(p is not None)
        self.b_delete.setEnabled(p is not None and not p.builtin)

    def apply(self):
        p = self.selected()
        if p is not None:
            self.win.choose_preset(p.name)

    def delete(self):
        p = self.selected()
        if p is not None and not p.builtin and self.win._ask("confirm", f'Delete the preset "{p.name}"?'):
            presets.delete_user(p.name)
            self.win.presets_changed()
            self.fill()

    def make_default(self):
        p = self.selected()
        if p is not None:
            self.win.set_default_preset(p.name)
            self.fill()

    def export(self):
        p = self.selected()
        if p is None:
            return
        path = self.win._ask("save_file", (f"{p.name}.json", "HandBrake presets (*.json)"))
        if path:
            presets.export(p, path)


class SavePresetDialog(QDialog):
    def __init__(self, parent, name: str):
        super().__init__(parent)
        self.setWindowTitle("Save New Preset")
        g = QGridLayout(self)
        g.addWidget(field("Name"), 0, 0)
        self.name = QLineEdit(name)
        g.addWidget(self.name, 0, 1)
        g.addWidget(field("Description"), 1, 0)
        self.desc = QLineEdit()
        g.addWidget(self.desc, 1, 1)
        self.default = QCheckBox("Make it the default preset")
        g.addWidget(self.default, 2, 1)
        box = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        box.accepted.connect(self.accept)
        box.rejected.connect(self.reject)
        g.addWidget(box, 3, 0, 1, 2)
        self.resize(460, 150)


# --------------------------------------------------------------------------- Options
class OptionsDialog(QDialog):
    changed = Signal()

    def __init__(self, win):
        super().__init__(win)
        from . import settings
        self.setWindowTitle("Options · PR7-HB")
        g = QGridLayout(self)
        g.setVerticalSpacing(10)
        g.addWidget(field("Output files"), 0, 0, 1, 3)
        g.addWidget(dim("Default folder"), 1, 0)
        self.folder = QLineEdit(win.output_folder())
        g.addWidget(self.folder, 1, 1)
        browse = QPushButton("Browse…")
        browse.clicked.connect(lambda: self.folder.setText(win._ask("folder", self.folder.text()) or self.folder.text()))
        g.addWidget(browse, 1, 2)
        g.addWidget(dim("File name"), 2, 0)
        self.pattern = QLineEdit(settings.get("name_pattern", "{source}"))
        self.pattern.setToolTip("{source} the source's name, {title} the title number, {preset} the preset")
        g.addWidget(self.pattern, 2, 1, 1, 2)
        g.addWidget(dim("When the file exists"), 3, 0)
        self.exists = QComboBox()
        self.exists.addItem("Ask", "ask")
        self.exists.addItem("Add a number", "rename")
        self.exists.addItem("Overwrite", "overwrite")
        self.exists.setCurrentIndex(max(0, self.exists.findData(settings.get("when_exists", "ask"))))
        g.addWidget(self.exists, 3, 1)
        g.addWidget(field("Queue"), 4, 0, 1, 3)
        self.show_queue = QCheckBox("Show the queue when encoding starts")
        self.show_queue.setChecked(settings.get_bool("show_queue", False))
        g.addWidget(self.show_queue, 5, 1, 1, 2)
        self.clear_done = QCheckBox("Remove finished jobs from the queue")
        self.clear_done.setChecked(settings.get_bool("clear_done", False))
        g.addWidget(self.clear_done, 6, 1, 1, 2)
        g.addWidget(field("Look"), 7, 0, 1, 3)
        g.addWidget(dim("Finish"), 8, 0)
        self.finish = QComboBox()
        self.finish.addItem("OBSIDIAN", "obsidian")
        self.finish.addItem("AURORA", "aurora")
        self.finish.setCurrentIndex(max(0, self.finish.findData(theme.FINISH)))
        g.addWidget(self.finish, 8, 1)
        from . import update_ui
        self.updates = QCheckBox("Check for updates automatically")
        self.updates.setChecked(update_ui.auto_enabled())
        g.addWidget(self.updates, 9, 1, 1, 2)
        g.addWidget(dim(f"Engine: {win.cli or 'not found'}" + (f"  ·  HandBrake {win.engine_version}"
                                                                  if win.engine_version else "")), 10, 0, 1, 3)
        box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        box.accepted.connect(self.accept)
        box.rejected.connect(self.reject)
        g.addWidget(box, 11, 0, 1, 3)
        self.resize(620, 380)

    def save(self, win):
        from . import settings, update_ui
        settings.set("output_folder", self.folder.text().strip())
        settings.set("name_pattern", self.pattern.text().strip() or "{source}")
        settings.set("when_exists", self.exists.currentData())
        settings.set("show_queue", self.show_queue.isChecked())
        settings.set("clear_done", self.clear_done.isChecked())
        update_ui.set_auto(self.updates.isChecked())
        if self.finish.currentData() != theme.FINISH:
            win.set_finish(self.finish.currentData())


# --------------------------------------------------------------------------- the bigger Preview
class PreviewWindow(QWidget):
    """The Preview key: the same frames, big, with previous / next and the live preview."""

    def __init__(self, win, panel):
        super().__init__(None, Qt.WindowType.Window)
        from .preview import Picture
        self.win, self.panel = win, panel
        self.setWindowTitle("Preview · PR7-HB")
        self.resize(1000, 640)
        lay = QVBoxLayout(self)
        self.picture = Picture()
        lay.addWidget(self.picture, 1)
        keys = QHBoxLayout()
        keys.addStretch(1)
        self.prev = widgets.SmallKey("back", "Previous preview")
        self.play = widgets.SmallKey("play", "Live preview")
        self.next = widgets.SmallKey("forward", "Next preview")
        for k in (self.prev, self.play, self.next):
            keys.addWidget(k)
        keys.addStretch(1)
        lay.addLayout(keys)
        self.prev.clicked.connect(lambda: self._go(-1))
        self.next.clicked.connect(lambda: self._go(1))
        self.play.clicked.connect(self.panel.play.click)
        if panel.grabber is not None:
            panel.grabber.frame.connect(lambda *_: self.sync())
        self.sync()

    def _go(self, by):
        self.panel.show_index(self.panel.index + by)
        self.sync()

    def sync(self):
        self.picture.image = self.panel.picture.image
        self.picture.crop = self.panel.picture.crop
        self.picture.caption = self.panel.picture.caption
        self.picture.update()
        self.prev.setEnabled(self.panel.prev.isEnabled())
        self.next.setEnabled(self.panel.next.isEnabled())
        self.play.setEnabled(self.panel.play.isEnabled())
