"""Test videos (pr7hb.sample): python tools/sample_media.py OUT_DIR"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pr7hb.sample import clip  # noqa: E402,F401

if __name__ == "__main__":
    from PySide6.QtGui import QGuiApplication
    app = QGuiApplication([])
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "media")
    out.mkdir(parents=True, exist_ok=True)
    print(clip(out / "clip.avi"))
