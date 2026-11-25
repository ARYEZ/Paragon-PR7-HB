"""Start PR7-HB.

    PR7-HB.exe [VIDEO | FOLDER]     the window (one per user: a later start hands its source to the running one)
    PR7-HB.exe --version
    PR7-HB.exe --selftest OUT.json  write a test video, scan it, encode it through the queue with a built-in preset
                                    and read the result back with the engine; writes what happened (CI checks the
                                    installed exe and its bundled HandBrakeCLI)
"""

from __future__ import annotations

import getpass
import hashlib
import json
import os
import sys

TIMEOUT_MS = 1500


def server_name() -> str:
    try:
        user = getpass.getuser()
    except Exception:  # noqa: BLE001
        user = "user"
    return "Paragon-PR7-HB-" + hashlib.sha1(user.encode()).hexdigest()[:12]


def hand_over(paths: list[str]) -> bool:
    from PySide6.QtNetwork import QLocalSocket
    s = QLocalSocket()
    s.connectToServer(server_name())
    if not s.waitForConnected(TIMEOUT_MS):
        return False
    s.write(json.dumps({"open": [os.path.abspath(p) for p in paths]}).encode() + b"\n")
    s.flush()
    s.waitForBytesWritten(TIMEOUT_MS)
    if not s.waitForDisconnected(TIMEOUT_MS):
        s.disconnectFromServer()
    return True


def listen(window):
    """Later starts bring this window to the front and open their source here (PR7-R's hand-off, with its Windows fix:
    data already waiting when the connection is accepted is read at once)."""
    from PySide6.QtNetwork import QLocalServer
    server = QLocalServer(window)
    QLocalServer.removeServer(server_name())
    if not server.listen(server_name()):
        return None

    def connection():
        sock = server.nextPendingConnection()
        if sock is None:
            return
        buf = bytearray()

        def read():
            buf.extend(bytes(sock.readAll()))
            if b"\n" not in buf:
                return
            try:
                msg = json.loads(buf.split(b"\n", 1)[0])
            except ValueError:
                msg = {}
            buf.clear()
            window.showNormal()
            window.raise_()
            window.activateWindow()
            paths = msg.get("open") or []
            if paths:
                window.open_source(paths[0])
            sock.disconnectFromServer()
        sock.readyRead.connect(read)
        if sock.bytesAvailable():
            read()
    server.newConnection.connect(connection)
    window.instance_server = server
    return server


def selftest(out: str) -> int:
    import tempfile
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    os.environ["PR7HB_DATA"] = tempfile.mkdtemp()
    from PySide6.QtCore import QSettings
    from PySide6.QtGui import QFontDatabase
    from PySide6.QtWidgets import QApplication
    QSettings.setDefaultFormat(QSettings.Format.IniFormat)
    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, tempfile.mkdtemp())
    app = QApplication.instance() or QApplication(sys.argv[:1])
    result: dict = {}
    try:
        from . import __version__, engine, queue, sample, theme
        from .main_window import MainWindow
        theme.load_fonts()
        work = tempfile.mkdtemp(prefix="pr7hb-selftest-")
        src = str(sample.clip(__import__("pathlib").Path(work) / "selftest clip.avi"))
        w = MainWindow(sync=True)
        w.answers.update({"say": lambda k, t: None, "confirm": lambda t: True, "overwrite": lambda n: "replace"})
        w.open_source(src)
        w.choose_preset("Fast 480p30")
        w.dest.setText(os.path.join(work, "out", "selftest clip.mp4"))
        w.dest_edited = True
        item = w.add_to_queue()
        w.queue.start()
        w.queue.wait(600)
        got = engine.scan(w.cli, item.job.dest)[0] if item and os.path.exists(item.job.dest) else None
        result = {"version": __version__, "engine": w.engine_version, "cli": w.cli,
                  "presets": len(w.builtin), "encoders": w.caps.video if w.caps else [],
                  "scanned": w.title is not None and (w.title.width, w.title.height) == (320, 180),
                  "state": item.state if item else None, "error": item.error if item else "no job",
                  "encoded": got is not None and got.codec == "h264" and len(got.audio) == 1,
                  "size": [got.width, got.height] if got else None,
                  "log": bool(item and item.log_path and os.path.exists(item.log_path)),
                  "fonts": "Inter" in QFontDatabase.families(), "done": item is not None and item.state == queue.DONE}
        w.close()
    except Exception as e:  # noqa: BLE001 - reported in the output
        import traceback
        result = {"error": f"{type(e).__name__}: {e}", "trace": traceback.format_exc()}
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(result, fh, indent=1)
    app.clipboard().clear()
    return 0 if result.get("encoded") else 1


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or not argv[0].startswith("--"):
        return _window(argv)
    # a command-line mode (the installer, CI): an unexpected error must end the process with a code; in the windowed
    # exe it would otherwise open an error box that waits for a click nobody gives
    try:
        return _command(argv)
    except SystemExit:
        raise
    except BaseException:  # noqa: BLE001 - reported, then a failing exit code
        import traceback
        if sys.stderr is not None:
            sys.stderr.write(traceback.format_exc())
        return 2


def _command(argv: list[str]) -> int:
    if argv[:1] == ["--version"]:
        from . import __version__
        print(__version__)
        return 0
    if argv[:1] == ["--selftest"] and len(argv) == 2:
        return selftest(argv[1])
    print(__doc__)
    return 1


def _window(argv: list[str]) -> int:
    from PySide6.QtWidgets import QApplication

    from . import settings, theme
    app = QApplication.instance() or QApplication(sys.argv[:1])
    app.setOrganizationName("Paragon")
    app.setApplicationName("PR7-HB")
    if hand_over(argv):
        return 0
    from . import finish
    theme.set_finish(finish.start(settings.get("finish", "obsidian")))
    theme.load_fonts()
    app.setPalette(theme.palette())
    from PySide6.QtGui import QIcon
    icon = os.path.join(os.path.dirname(__file__), "icons", "app.ico")
    if os.path.exists(icon):
        app.setWindowIcon(QIcon(icon))
    from .main_window import MainWindow
    w = MainWindow()
    # one finish for the family: follow a switch made in another family app (finish.py)
    from PySide6.QtCore import QTimer
    _follow = QTimer(w)
    _follow.timeout.connect(lambda: finish.follow(theme.FINISH, w.set_finish))
    _follow.start(2000)
    listen(w)
    w.show()
    if argv:
        QTimer.singleShot(0, lambda: w.open_source(argv[0]))
    from . import update_ui
    update_ui.start(w)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
