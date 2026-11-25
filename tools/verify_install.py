"""Check a real install of PR7-HB-Setup.exe (CI, Windows): verify_install.py installed|uninstalled

`installed`: the files (the bundled HandBrakeCLI and Qt's FFmpeg plugin included), the Start menu entry, the uninstall
entry, and the installed exe's --selftest: a test video written, scanned, encoded through the queue with a built-in
preset by the bundled engine, and read back. `uninstalled`: all of it gone."""
import json
import os
import subprocess
import sys
import tempfile
import time
import winreg
from pathlib import Path

HKCU = winreg.HKEY_CURRENT_USER
APP = Path(os.environ["LOCALAPPDATA"]) / "Programs" / "PR7-HB"
SHORTCUT = Path(os.environ["APPDATA"]) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Paragon PR7-HB.lnk"
UNINSTALL = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\{5A2D8918-1C5C-456F-AFCF-1FBA498EA280}_is1"


def value(root, path, name=""):
    try:
        with winreg.OpenKey(root, path) as k:
            return winreg.QueryValueEx(k, name)[0]
    except OSError:
        return None


def check(ok, what, p):
    print(("ok    " if ok else "FAIL  ") + what)
    if not ok:
        p.append(what)


def installed():
    p = []
    exe = APP / "PR7-HB.exe"
    cli = APP / "_internal" / "engine" / "HandBrakeCLI.exe"
    for f in (exe, APP / "unins000.exe", cli, APP / "_internal" / "engine" / "doc" / "COPYING", APP / "NOTICE.md",
              APP / "_internal" / "pr7hb" / "fonts" / "Inter-Regular.ttf"):
        check(f.is_file(), f"file {f}", p)
    check(any(APP.rglob("ffmpegmediaplugin.dll")), "Qt Multimedia's FFmpeg plugin (preview frames)", p)
    check(SHORTCUT.is_file(), "Start menu shortcut", p)
    check(value(HKCU, UNINSTALL, "DisplayName") == "Paragon PR7-HB", "Installed apps entry", p)
    with tempfile.TemporaryDirectory() as d:
        out = Path(d) / "out.json"
        try:
            subprocess.run([str(exe), "--selftest", str(out)], timeout=600, check=False)
        except subprocess.TimeoutExpired:
            pass
        got = json.loads(out.read_text(encoding="utf-8")) if out.exists() else {}
        check(Path(got.get("cli") or "x").resolve() == cli.resolve(), f"the bundled engine is used ({got.get('cli')})",
              p)
        check(got.get("presets", 0) > 20 and got.get("fonts") is True, f"HandBrake's presets read ({got})", p)
        check(got.get("scanned") is True, "a test video is scanned", p)
        check(got.get("encoded") is True and got.get("done") is True and got.get("log") is True,
              "it's encoded through the queue to H.264 + AAC and read back, with a log", p)
    return p


def uninstalled():
    deadline = time.time() + 60
    while True:
        p = []
        check(not (APP / "PR7-HB.exe").exists(), "program files removed", p)
        check(not (APP / "_internal" / "engine").exists(), "the engine removed", p)
        check(not SHORTCUT.exists(), "Start menu shortcut removed", p)
        check(value(HKCU, UNINSTALL, "DisplayName") is None, "Installed apps entry removed", p)
        if not p or time.time() > deadline:
            return p
        print("... waiting for the uninstaller to finish")
        time.sleep(3)


if __name__ == "__main__":
    problems = {"installed": installed, "uninstalled": uninstalled}[sys.argv[1]]()
    print("\nALL OK" if not problems else f"\n{len(problems)} problem(s)")
    sys.exit(1 if problems else 0)
