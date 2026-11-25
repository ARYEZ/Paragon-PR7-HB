"""Presets (no Qt): HandBrake's built-in ones, read from the engine itself, and the user's own, kept in HandBrake's
own JSON preset format so files go both ways (HandBrake's Import / Export reads and writes the same thing).

Built-in presets come from `HandBrakeCLI -z` (names and categories) and `--preset NAME --preset-export NAME` (each
preset's full settings: --preset-export alone writes the current, i.e. default, settings under the name). That is ~40 runs, so the result is cached in the data folder per engine (path, size, modified time)."""

from __future__ import annotations

import copy
import json
import os
import re
import sys
from dataclasses import dataclass

from . import engine

DEFAULT = "Fast 1080p30"       # HandBrake's default preset
USER_CATEGORY = "Custom Presets"
CACHE_VERSION = 2              # bump whenever reading the built-in presets changes: old caches are then read again


def data_dir() -> str:
    d = os.environ.get("PR7HB_DATA") or (
        os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "Paragon", "PR7-HB") if sys.platform == "win32"
        else os.path.join(os.path.expanduser("~"), ".local", "share", "paragon", "pr7-hb"))
    os.makedirs(d, exist_ok=True)
    return d


@dataclass
class Preset:
    name: str
    category: str
    description: str
    settings: dict
    builtin: bool = True


def parse_list(text: str) -> list[tuple[str, str, str]]:
    """`HandBrakeCLI -z`: "Category/" lines, 4-space preset names, 8-space description lines -> (category, name,
    description)."""
    out: list[tuple[str, str, str]] = []
    category = ""
    for line in text.splitlines():
        if not line.strip() or line.startswith("["):
            continue
        if re.match(r"^\S.*/\s*$", line):
            category = line.strip().rstrip("/")
        elif re.match(r"^ {4}\S", line) and category:
            out.append((category, line.strip(), ""))
        elif re.match(r"^ {8}\S", line) and out:
            c, n, d = out[-1]
            out[-1] = (c, n, (d + " " + line.strip()).strip())
    return out


def _fingerprint(cli: str) -> str:
    st = os.stat(cli)
    return f"{CACHE_VERSION}|{os.path.abspath(cli)}|{st.st_size}|{int(st.st_mtime)}"


def builtin(cli: str, progress=None) -> list[Preset]:
    cache = os.path.join(data_dir(), "builtin-presets.json")
    key = _fingerprint(cli)
    try:
        with open(cache, encoding="utf-8") as f:
            data = json.load(f)
        if data.get("engine") == key:
            return [Preset(**p) for p in data["presets"]]
    except (OSError, ValueError, KeyError, TypeError):
        pass
    r = engine.run(cli, ["-z"], 60)
    listed = parse_list(r.stdout + "\n" + r.stderr)
    out = []
    for i, (cat, name, desc) in enumerate(listed):
        if progress:
            progress(i, len(listed))
        # --preset-export saves the *current* settings under a name: select the preset first, or it's the defaults
        e = engine.run(cli, ["--preset", name, "--preset-export", name], 60)
        try:
            text = e.stdout[e.stdout.index("{"):]
            settings = json.loads(text)["PresetList"][0]
        except (ValueError, KeyError, IndexError):
            continue
        out.append(Preset(name, cat, desc or settings.get("PresetDescription", ""), settings))
    if out:
        tmp = cache + ".part"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"engine": key, "presets": [p.__dict__ for p in out]}, f)
        os.replace(tmp, cache)
    return out


# --------------------------------------------------------------------------- the user's presets
def user_file() -> str:
    return os.path.join(data_dir(), "presets.json")


def _flatten(items: list, category: str = USER_CATEGORY) -> list[Preset]:
    out = []
    for it in items:
        if it.get("Folder"):
            out += _flatten(it.get("ChildrenArray", []), it.get("PresetName", category))
        elif it.get("PresetName"):
            out.append(Preset(it["PresetName"], category, it.get("PresetDescription", ""), it, False))
    return out


def load_file(path: str) -> list[Preset]:
    """Presets from a HandBrake preset file (one preset or folders of them)."""
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    items = data.get("PresetList", []) if isinstance(data, dict) else []
    return _flatten(items)


def user() -> list[Preset]:
    try:
        return load_file(user_file())
    except (OSError, ValueError):
        return []


def _write(path: str, presets: list[Preset]) -> None:
    items = []
    for p in presets:
        s = copy.deepcopy(p.settings)
        s.update(PresetName=p.name, PresetDescription=p.description, Type=1, Folder=False, Default=False)
        items.append(s)
    tmp = path + ".part"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"PresetList": items, "VersionMajor": 47, "VersionMinor": 0, "VersionMicro": 0}, f, indent=1)
    os.replace(tmp, path)


def save_user(preset: Preset) -> None:
    """Add or replace (same name) one of the user's presets."""
    mine = [p for p in user() if p.name != preset.name]
    preset.builtin = False
    preset.category = USER_CATEGORY
    mine.append(preset)
    _write(user_file(), mine)


def delete_user(name: str) -> bool:
    mine = user()
    kept = [p for p in mine if p.name != name]
    if len(kept) == len(mine):
        return False
    _write(user_file(), kept)
    return True


def export(preset: Preset, path: str) -> None:
    _write(path, [preset])


def import_file(path: str) -> list[Preset]:
    """HandBrake's Import: every preset in the file joins the user's presets."""
    got = load_file(path)
    for p in got:
        save_user(p)
    return got


def usable(presets: list[Preset], video_encoders: list[str]) -> list[Preset]:
    """The presets this engine can run, as HandBrake shows them: hardware presets only for encoders the build has
    (NVEnc, QSV, VCE, VideoToolbox, MediaFoundation), and not the "CLI Defaults" stand-in."""
    have = set(video_encoders)
    return [p for p in presets if p.category != "CLI Defaults" and not p.settings.get("PresetDisabled")
            and (not p.builtin or p.settings.get("VideoEncoder", "x264") in have)]


def find(presets: list[Preset], name: str) -> Preset | None:
    for p in presets:
        if p.name == name:
            return p
    return None
