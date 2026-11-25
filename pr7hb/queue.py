"""The queue: HandBrake's encode queue, running HandBrakeCLI one job at a time in a QProcess.

stdout (--json) goes through engine.ProgressParser; stderr is HandBrake's activity log, kept per job and saved to
<data>/logs as HandBrake does. Pause suspends the encoder process (psutil): HandBrakeCLI on Windows reads its pause
key from the console keyboard, not from a pipe, so there's nothing to type at it."""

from __future__ import annotations

import os
import shutil
import time
from dataclasses import dataclass, field

from PySide6.QtCore import QObject, QProcess, QTimer, Signal

from . import engine, presets

WAITING, ENCODING, PAUSED, DONE, FAILED, CANCELLED = "waiting", "encoding", "paused", "done", "failed", "cancelled"


@dataclass
class Item:
    job: engine.Job
    state: str = WAITING
    progress: engine.Progress = field(default_factory=engine.Progress)
    log: list[str] = field(default_factory=list)
    started: float = 0.0
    finished: float = 0.0
    error: str = ""
    log_path: str = ""

    def name(self) -> str:
        return os.path.basename(self.job.source.rstrip("\\/"))

    def state_text(self) -> str:
        if self.state == ENCODING:
            return f"ENCODING  {self.progress.fraction * 100:.0f} %"
        return self.state.upper()

    def detail(self) -> str:
        if self.state == DONE:
            took = engine.hms(self.finished - self.started)
            sizes = ""
            try:
                a, b = os.path.getsize(self.job.source), os.path.getsize(self.job.dest)
                sizes = f"  ·  {human(a)} → {human(b)}"
            except OSError:
                pass
            return f"→ {os.path.basename(self.job.dest)}  ·  done in {took}{sizes}"
        if self.state == FAILED:
            return f"→ {os.path.basename(self.job.dest)}  ·  {self.error}"
        return self.job.describe()


def human(n: float) -> str:
    for unit in ("bytes", "KB", "MB", "GB", "TB"):
        if n < 1000 or unit == "TB":
            return f"{n:.0f} {unit}" if unit == "bytes" else f"{n:.2f} {unit}".replace(".00 ", " ")
        n /= 1000
    return ""


class Queue(QObject):
    changed = Signal(object)          # an Item (or None: the list itself changed)
    done = Signal()                   # nothing left to encode

    def __init__(self, cli: str | None = None, parent=None):
        super().__init__(parent)
        self.cli = cli
        self.items: list[Item] = []
        self.current: Item | None = None
        self.proc: QProcess | None = None
        self.running = False          # Start was pressed and not stopped
        self.paused = False
        self._parser: engine.ProgressParser | None = None
        self._folder = ""
        self._err = ""
        self._tick = QTimer(self)
        self._tick.setInterval(250)
        self._tick.timeout.connect(self._read)

    # -------------------------------------------------------------- the list
    def add(self, job: engine.Job) -> Item:
        item = Item(job)
        self.items.append(item)
        self.changed.emit(None)
        return item

    def remove(self, item: Item) -> None:
        if item is self.current:
            self.stop()
        if item in self.items:
            self.items.remove(item)
        self.changed.emit(None)

    def retry(self, item: Item) -> None:
        if item.state in (FAILED, CANCELLED, DONE):
            item.state, item.error, item.progress, item.log = WAITING, "", engine.Progress(), []
            self.changed.emit(item)
            if self.running and self.current is None:
                self._next()

    def clear_done(self) -> None:
        self.items = [i for i in self.items if i.state != DONE]
        self.changed.emit(None)

    def waiting(self) -> list[Item]:
        return [i for i in self.items if i.state == WAITING]

    def move(self, item: Item, by: int) -> None:
        i = self.items.index(item)
        j = max(0, min(len(self.items) - 1, i + by))
        self.items.insert(j, self.items.pop(i))
        self.changed.emit(None)

    # -------------------------------------------------------------- running
    def start(self) -> None:
        if self.paused:
            self.resume()
            return
        self.running = True
        if self.current is None:
            self._next()

    def _next(self) -> None:
        nxt = next((i for i in self.items if i.state == WAITING), None)
        if nxt is None:
            self.running = False
            self.done.emit()
            return
        self._run(nxt)

    def _run(self, item: Item) -> None:
        self.current = item
        item.state, item.started, item.progress, item.log, item.error = ENCODING, time.time(), engine.Progress(), [], ""
        self._folder = engine.temp_folder()
        self._parser = engine.ProgressParser()
        self._err = ""
        os.makedirs(os.path.dirname(os.path.abspath(item.job.dest)) or ".", exist_ok=True)
        try:
            args = engine.job_args(item.job, self._folder)
            cli = self.cli or engine.find_cli()
        except (OSError, engine.EngineNotFound) as e:
            self._finish(item, FAILED, str(e))
            return
        item.log.append(f"PR7-HB: {cli} " + " ".join(f'"{a}"' if " " in a else a for a in args))
        self.proc = QProcess(self)
        self.proc.setProgram(cli)
        self.proc.setArguments(args)
        self.proc.finished.connect(self._ended)
        self.proc.errorOccurred.connect(self._error)
        self.proc.start()
        self._tick.start()
        self.changed.emit(item)

    def _read(self) -> None:
        p, item = self.proc, self.current
        if p is None or item is None:
            return
        out = bytes(p.readAllStandardOutput()).decode("utf-8", "replace")
        if out:
            item.progress = self._parser.feed(out)
        err = bytes(p.readAllStandardError()).decode("utf-8", "replace")
        if err:
            text = self._err + err.replace("\r\n", "\n").replace("\r", "\n")
            *lines, self._err = text.split("\n")
            item.log.extend(ln for ln in lines if ln.strip())
        if out or err:
            self.changed.emit(item)

    def _error(self, err) -> None:
        if err == QProcess.ProcessError.FailedToStart and self.current is not None:
            self._tick.stop()
            self._finish(self.current, FAILED, "HandBrakeCLI couldn't be started")

    def _ended(self, code: int, _status) -> None:
        self._read()
        self._tick.stop()
        item = self.current
        if item is None:
            return
        if item.state == CANCELLED:
            self._finish(item, CANCELLED, "stopped")
            return
        err = item.progress.error
        if code == 0 and (err in (None, 0)) and os.path.exists(item.job.dest):
            self._finish(item, DONE)
        else:
            why = engine.ERRORS.get(err or 0) or next(
                (ln.split("] ", 1)[-1] for ln in reversed(item.log) if "rror" in ln or "No title" in ln),
                f"HandBrakeCLI ended with code {code}")
            self._finish(item, FAILED, why)

    def _finish(self, item: Item, state: str, error: str = "") -> None:
        item.state, item.error, item.finished = state, error, time.time()
        if state in (FAILED, CANCELLED) and os.path.exists(item.job.dest) and item.started:
            try:                                            # a half-written file isn't a video: HandBrake removes it
                os.remove(item.job.dest)
            except OSError:
                pass
        item.log_path = self._save_log(item)
        if self._folder:
            shutil.rmtree(self._folder, ignore_errors=True)
            self._folder = ""
        self.proc = None
        self.current = None
        self.paused = False
        self.changed.emit(item)
        if self.running:
            QTimer.singleShot(0, self._next)

    def _save_log(self, item: Item) -> str:
        folder = os.path.join(presets.data_dir(), "logs")
        os.makedirs(folder, exist_ok=True)
        stamp = time.strftime("%Y-%m-%d %H-%M-%S", time.localtime(item.started or time.time()))
        path = os.path.join(folder, f"{os.path.splitext(item.name())[0]} {stamp}.txt")
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write("\n".join(item.log) + "\n")
        except OSError:
            return ""
        return path

    def pause(self) -> bool:
        if self.proc is None or self.paused or self.current is None:
            return False
        try:
            import psutil
            psutil.Process(int(self.proc.processId())).suspend()
        except Exception:
            return False
        self.paused = True
        self.current.state = PAUSED
        self.changed.emit(self.current)
        return True

    def resume(self) -> bool:
        if self.proc is None or not self.paused or self.current is None:
            return False
        try:
            import psutil
            psutil.Process(int(self.proc.processId())).resume()
        except Exception:
            return False
        self.paused = False
        self.current.state = ENCODING
        self.changed.emit(self.current)
        return True

    def stop(self) -> None:
        """Stop the running encode (it's marked cancelled and its half-written file removed) and the queue."""
        self.running = False
        if self.proc is not None and self.current is not None:
            if self.paused:
                self.resume()
            self.current.state = CANCELLED
            self.proc.kill()
            self.proc.waitForFinished(5000)

    def wait(self, timeout: float = 300) -> bool:
        """Tests and --encode: spin events until nothing is running."""
        from PySide6.QtCore import QCoreApplication, QEventLoop
        end = time.time() + timeout
        while (self.current is not None or (self.running and self.waiting())) and time.time() < end:
            QCoreApplication.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 50)
            time.sleep(0.01)
        return self.current is None
