"""Screenshots of the real PR7-HB window on the real engine (a generated test video; nothing of the user's):
QT_SCALE_FACTOR=2 python tools/screenshots.py OUT_DIR

main.png (Summary, an encode running, OBSIDIAN), video.png (the Video tab, AURORA), queue.png (OBSIDIAN)."""
import os
import sys
import tempfile
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["PR7HB_DATA"] = os.environ.get("PR7HB_SHOTS_DATA") or tempfile.mkdtemp()
_family = Path(tempfile.mkdtemp()) / "finish"
_family.write_text("obsidian")
os.environ["PARAGON_FAMILY_FILE"] = str(_family)
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PySide6.QtCore import QSettings  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

QSettings.setDefaultFormat(QSettings.Format.IniFormat)
QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, tempfile.mkdtemp())

from pr7hb import sample, settings, theme  # noqa: E402
from pr7hb.main_window import MainWindow  # noqa: E402

out = Path(sys.argv[1] if len(sys.argv) > 1 else "docs/screenshots")
out.mkdir(parents=True, exist_ok=True)
app = QApplication([])
theme.load_fonts()
work = Path(tempfile.mkdtemp())
src = sample.clip(work / "ELSEWORLD_master.avi", seconds=60, fps=24, size=(1280, 720))
settings.set("output_folder", str(work / "Exports"))


def spin(seconds):
    end = time.time() + seconds
    while time.time() < end:
        app.processEvents()
        time.sleep(0.02)


w = MainWindow(sync=True)
w.answers.update({"say": lambda k, t: None, "confirm": lambda t: True, "overwrite": lambda n: "replace"})
w.resize(1180, 880)
w.show()
w.open_source(str(src))
w.preview.grabber.wait(30)
spin(0.5)
w.queue.add(w.make_job())
w.preset["VideoEncoder"] = "x265"
w.preset_edited()
w.dest.setText(str(work / "Exports" / "ELSEWORLD_master (x265).mp4"))
w.queue.add(w.make_job())
w.queue.start()
end = time.time() + 60
while (w.queue.current is None or w.queue.current.progress.fraction < 0.2) and time.time() < end:
    app.processEvents()
    time.sleep(0.05)
spin(0.3)
w.grab().save(str(out / "main.png"))
qw = w.show_queue()
qw.resize(1080, 560)
spin(0.5)
qw.grab().save(str(out / "queue.png"))
w.queue.stop()
w.queue.wait(20)
qw.close()
w.set_finish("aurora")
w.tabs.setCurrentIndex(3)
spin(0.3)
w.grab().save(str(out / "video.png"))
w.set_finish("obsidian")
w.close()
print("ok", out)
