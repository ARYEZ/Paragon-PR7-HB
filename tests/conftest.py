import os
import shutil
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["PARAGON_FAMILY_FILE"] = os.path.join(tempfile.mkdtemp(prefix="family-"), "finish")  # never the real choice
os.environ["PR7HB_DATA"] = tempfile.mkdtemp(prefix="pr7hb-data-")       # never the real data folder (presets, logs)
_SHARED_CACHE = os.path.join(tempfile.gettempdir(), "pr7hb-test-presets")  # built-in presets: read once per machine


def _cli():
    from pr7hb import engine
    try:
        return engine.find_cli()
    except engine.EngineNotFound:
        return None


CLI = _cli()
needs_cli = pytest.mark.skipif(CLI is None, reason="needs HandBrakeCLI (PR7HB_CLI, engine/ or PATH)")


@pytest.fixture(scope="session")
def qapp(tmp_path_factory):
    from PySide6.QtCore import QSettings
    from PySide6.QtWidgets import QApplication
    QSettings.setDefaultFormat(QSettings.Format.IniFormat)           # never the real settings
    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(tmp_path_factory.mktemp("settings")))
    app = QApplication.instance() or QApplication([])
    from pr7hb import theme
    theme.load_fonts()
    yield app
    app.clipboard().clear()                  # PySide's offscreen clipboard crashes at exit while it holds data


@pytest.fixture(scope="session")
def media(qapp, tmp_path_factory):
    """Real test videos written here (tools/sample_media.py): a 3 s clip with sound, a 2 s one without."""
    from pr7hb import sample as sample_media
    d = tmp_path_factory.mktemp("media")
    out = {"clip": str(sample_media.clip(d / "clip.avi")),
           "silent": str(sample_media.clip(d / "silent clip.avi", seconds=2, audio=False, size=(256, 144)))}
    if shutil.which("ffmpeg"):          # a source with chapters (HandBrake writes none for a one-chapter title)
        import subprocess
        src = sample_media.clip(d / "ten.avi", seconds=10)
        meta = d / "chapters.txt"
        meta.write_text(";FFMETADATA1\n" + "".join(f"[CHAPTER]\nTIMEBASE=1/1000\nSTART={a}\nEND={a + 5000}\n"
                                                    f"title=Part {i}\n" for i, a in enumerate((0, 5000), 1)))
        r = subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(src), "-i", str(meta), "-map_metadata", "1",
                            "-map_chapters", "1", "-c", "copy", str(d / "chapters.mkv")], capture_output=True)
        if r.returncode == 0:
            out["chapters"] = str(d / "chapters.mkv")
    return out


@pytest.fixture(scope="session")
def builtin(qapp):
    """HandBrake's built-in presets from the real engine, cached across test runs (they take ~40 CLI runs)."""
    if CLI is None:
        pytest.skip("needs HandBrakeCLI")
    from pr7hb import presets
    os.makedirs(_SHARED_CACHE, exist_ok=True)
    cached = os.path.join(_SHARED_CACHE, "builtin-presets.json")
    mine = os.path.join(presets.data_dir(), "builtin-presets.json")
    if os.path.exists(cached):
        shutil.copy(cached, mine)
    got = presets.builtin(CLI)
    shutil.copy(mine, cached)
    return got


@pytest.fixture
def window(qapp, builtin, tmp_path):
    """The real window on the real engine (scans and preset reading inline), saving into tmp_path."""
    from pr7hb import main_window, settings
    for k in ("default_preset", "name_pattern", "when_exists", "show_queue", "clear_done"):
        settings.set(k, "")
    settings.set("output_folder", str(tmp_path / "out"))
    settings.set("when_exists", "ask")
    w = main_window.MainWindow(cli=CLI, sync=True)
    w.answers.update({"say": lambda kind, text: None, "confirm": lambda t: True})
    w.show()
    yield w
    w.queue.stop()
    w.close()
    from PySide6.QtCore import QCoreApplication, QEvent
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    del w
    import gc
    gc.collect()          # on the main thread now, not later on some other thread (PR7-U's lesson)
