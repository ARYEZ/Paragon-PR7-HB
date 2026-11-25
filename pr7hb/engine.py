"""HandBrake's engine, the official HandBrakeCLI (no Qt): finding it, scanning a source, what the build can encode,
a job's command line, and reading its progress.

PR7-HB has no video code of its own: like PR7-Z with 7-Zip, every scan and encode runs the unmodified HandBrakeCLI
(bundled in `engine/`). A job is a HandBrake *preset* (the chosen one with the tabs' changes) written to a temporary
preset file and given with --preset-import-file / --preset, plus the source, title, range, destination and the
explicit audio / subtitle tracks, the way HandBrake's own window hands a job to libhb."""

from __future__ import annotations

import copy
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

CLI_NAME = "HandBrakeCLI.exe" if sys.platform == "win32" else "HandBrakeCLI"
NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0          # CREATE_NO_WINDOW: no console flashes

CROP_MODES = [(0, "Automatic"), (1, "Loose"), (2, "None"), (3, "Custom")]   # PictureCropMode
CONTAINERS = {"av_mp4": ("MP4", ".mp4"), "av_mkv": ("MKV", ".mkv"), "av_webm": ("WebM", ".webm")}

# The names HandBrake's window shows for the CLI's encoder ids.
VIDEO_NAMES = {
    "x264": "H.264 (x264)", "x264_10bit": "H.264 10-bit (x264)", "x265": "H.265 (x265)",
    "x265_10bit": "H.265 10-bit (x265)", "x265_12bit": "H.265 12-bit (x265)", "svt_av1": "AV1 (SVT)",
    "svt_av1_10bit": "AV1 10-bit (SVT)", "mpeg4": "MPEG-4", "mpeg2": "MPEG-2", "VP8": "VP8", "VP9": "VP9",
    "VP9_10bit": "VP9 10-bit", "theora": "Theora", "ffv1": "FFV1",
    "nvenc_h264": "H.264 (NVEnc)", "nvenc_h265": "H.265 (NVEnc)", "nvenc_h265_10bit": "H.265 10-bit (NVEnc)",
    "nvenc_av1": "AV1 (NVEnc)", "nvenc_av1_10bit": "AV1 10-bit (NVEnc)",
    "qsv_h264": "H.264 (Intel QSV)", "qsv_h265": "H.265 (Intel QSV)", "qsv_h265_10bit": "H.265 10-bit (Intel QSV)",
    "qsv_av1": "AV1 (Intel QSV)", "qsv_av1_10bit": "AV1 10-bit (Intel QSV)",
    "vce_h264": "H.264 (AMD VCE)", "vce_h265": "H.265 (AMD VCE)", "vce_h265_10bit": "H.265 10-bit (AMD VCE)",
    "vce_av1": "AV1 (AMD VCE)", "mf_h264": "H.264 (MediaFoundation)", "mf_h265": "H.265 (MediaFoundation)",
}
AUDIO_NAMES = {
    "none": "None", "av_aac": "AAC (avcodec)", "ca_aac": "AAC (CoreAudio)", "ac3": "AC3", "eac3": "E-AC3",
    "mp3": "MP3", "vorbis": "Vorbis", "flac16": "FLAC 16-bit", "flac24": "FLAC 24-bit", "opus": "Opus",
    "copy": "Auto Passthru",
}
MIXDOWNS = [("mono", "Mono"), ("left_only", "Mono (left only)"), ("right_only", "Mono (right only)"),
            ("stereo", "Stereo"), ("dpl1", "Dolby Surround"), ("dpl2", "Dolby Pro Logic II"),
            ("5point1", "5.1 Channels"), ("6point1", "6.1 Channels"), ("7point1", "7.1 Channels"),
            ("5_2_lfe", "7.1 (5F/2R/LFE)")]
SAMPLERATES = ["auto", "8", "11.025", "12", "16", "22.05", "24", "32", "44.1", "48"]
FRAMERATES = ["auto", "5", "10", "12", "15", "20", "23.976", "24", "25", "29.97", "30", "48", "50", "59.94", "60",
              "72", "75", "90", "100", "120"]


class EngineNotFound(RuntimeError):
    pass


class ScanFailed(RuntimeError):
    pass


def audio_name(enc: str) -> str:
    if enc.startswith("copy:"):
        return enc[5:].upper().replace("DTSHD", "DTS-HD").replace("TRUEHD", "TrueHD") + " Passthru"
    return AUDIO_NAMES.get(enc, enc)


def video_name(enc: str) -> str:
    return VIDEO_NAMES.get(enc, enc)


# --------------------------------------------------------------------------- finding HandBrakeCLI
def _bundled() -> list[Path]:
    here = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1]))
    return [here / "engine" / CLI_NAME, Path(sys.executable).parent / "engine" / CLI_NAME]


def find_cli() -> str:
    """PR7HB_CLI, else the bundled engine, else an installed HandBrake (its CLI next to it), else PATH."""
    env = os.environ.get("PR7HB_CLI")
    if env:
        if os.path.isfile(env):
            return env
        raise EngineNotFound(f"PR7HB_CLI points at {env}, which isn't there")
    places = _bundled()
    if sys.platform == "win32":
        for root in (os.environ.get("ProgramFiles", r"C:\Program Files"), os.environ.get("LOCALAPPDATA", "")):
            places.append(Path(root) / "HandBrake" / CLI_NAME)
    for p in places:
        if p.is_file():
            return str(p)
    found = shutil.which(CLI_NAME) or shutil.which("HandBrakeCLI")
    if found:
        return found
    raise EngineNotFound("HandBrakeCLI wasn't found (PR7-HB's engine folder, an installed HandBrake, PATH)")


def run(cli: str, args: list[str], timeout: float = 120) -> subprocess.CompletedProcess:
    return subprocess.run([cli, *args], capture_output=True, text=True, encoding="utf-8", errors="replace",
                          timeout=timeout, creationflags=NO_WINDOW, stdin=subprocess.DEVNULL)


def version(cli: str) -> str:
    out = run(cli, ["--version"], 30).stdout
    m = re.search(r"HandBrake\s+(\S+)", out)
    return m.group(1) if m else ""


# --------------------------------------------------------------------------- "Label: {json}" blocks
def json_blocks(text: str) -> list[tuple[str, object]]:
    """HandBrakeCLI --json writes `Version: {...}`, `JSON Title Set: {...}`, `Progress: {...}` blocks among its
    other lines: (label, parsed object) for each complete one."""
    return BlockReader().feed(text)


class BlockReader:
    """Reads the blocks as they arrive in pieces (a running encode's stdout)."""

    _start = re.compile(r"^([A-Za-z][A-Za-z ]*): \{\s*$")

    def __init__(self):
        self.label: str | None = None
        self.lines: list[str] = []
        self.depth = 0
        self.rest = ""

    def feed(self, chunk: str) -> list[tuple[str, object]]:
        out = []
        data = self.rest + chunk.replace("\r\n", "\n").replace("\r", "\n")
        *lines, self.rest = data.split("\n")
        for line in lines:
            if self.label is None:
                m = self._start.match(line)
                if m:
                    self.label, self.lines, self.depth = m.group(1), ["{"], 1
                continue
            self.lines.append(line)
            self.depth += line.count("{") + line.count("[") - line.count("}") - line.count("]")
            if self.depth <= 0:
                try:
                    out.append((self.label, json.loads("\n".join(self.lines))))
                except ValueError:
                    pass
                self.label = None
        return out


# --------------------------------------------------------------------------- scanning
def _seconds(d: dict) -> float:
    if "Ticks" in d:
        return d["Ticks"] / 90000
    return d.get("Hours", 0) * 3600 + d.get("Minutes", 0) * 60 + d.get("Seconds", 0)


def hms(seconds: float) -> str:
    s = int(round(seconds))
    return f"{s // 3600:02d}:{s // 60 % 60:02d}:{s % 60:02d}"


@dataclass
class Track:
    number: int                 # HandBrake's track number (1-based)
    description: str
    language: str = "und"       # ISO 639-2 code
    codec: str = ""
    channels: int = 0
    kind: str = "audio"         # audio | subtitle
    source: str = ""            # subtitles: VOBSUB, PGS, SRT, SSA, CC608 ...


@dataclass
class Title:
    index: int
    path: str
    name: str
    duration: float
    width: int
    height: int
    fps: float
    codec: str
    bit_depth: int = 8
    hdr: bool = False
    par: tuple[int, int] = (1, 1)
    crop: tuple[int, int, int, int] = (0, 0, 0, 0)
    audio: list[Track] = field(default_factory=list)
    subtitles: list[Track] = field(default_factory=list)
    chapters: list[tuple[str, float]] = field(default_factory=list)
    frames: int = 0

    def label(self) -> str:
        return f"{self.index}  ·  {hms(self.duration)}"

    def describe(self) -> str:
        """The source line: "3840 × 2160 · 23.976 FPS · HEVC 10-bit HDR10 · 2 audio · 3 subtitles"."""
        bits = f" {self.bit_depth}-bit" if self.bit_depth > 8 else ""
        parts = [f"{self.width} × {self.height}", f"{self.fps:.3f}".rstrip("0").rstrip(".") + " FPS",
                 f"{self.codec.upper()}{bits}{' HDR' if self.hdr else ''}"]
        parts.append(f"{len(self.audio)} audio" if self.audio else "no audio")
        if self.subtitles:
            parts.append(f"{len(self.subtitles)} subtitle{'s' if len(self.subtitles) != 1 else ''}")
        return " · ".join(parts)


def parse_title(t: dict) -> Title:
    geo = t.get("Geometry", {})
    fr = t.get("FrameRate", {})
    fps = fr.get("Num", 0) / fr["Den"] if fr.get("Den") else 0.0
    colour = t.get("Color", {})
    par = geo.get("PAR", {})
    title = Title(index=t.get("Index", 1), path=t.get("Path", ""), name=t.get("Name", ""),
                  duration=_seconds(t.get("Duration", {})), width=geo.get("Width", 0), height=geo.get("Height", 0),
                  fps=fps, codec=t.get("VideoCodec", ""), bit_depth=colour.get("BitDepth", 8),
                  hdr=colour.get("Transfer") in (16, 18),                     # PQ (HDR10) / HLG
                  par=(par.get("Num", 1) or 1, par.get("Den", 1) or 1),
                  crop=tuple(t.get("Crop", [0, 0, 0, 0])[:4]))
    title.frames = int(round(title.duration * fps))
    for a in t.get("AudioList", []):
        title.audio.append(Track(a.get("TrackNumber", len(title.audio) + 1), a.get("Description", ""),
                                 a.get("LanguageCode", "und"), a.get("CodecName", ""), a.get("ChannelCount", 0)))
    for s in t.get("SubtitleList", []):
        title.subtitles.append(Track(s.get("TrackNumber", len(title.subtitles) + 1), s.get("Name", ""),
                                     s.get("LanguageCode", "und"), kind="subtitle", source=s.get("SourceName", "")))
    for c in t.get("ChapterList", []):
        title.chapters.append((c.get("Name", ""), _seconds(c.get("Duration", {}))))
    return title


def scan(cli: str, path: str, timeout: float = 300) -> list[Title]:
    """Every title in a file or a disc folder (VIDEO_TS / BDMV), as HandBrake's Open Source sees them."""
    r = run(cli, ["--json", "--scan", "-i", path, "-t", "0", "--previews", "1:0"], timeout)
    for label, obj in json_blocks(r.stdout):
        if label == "JSON Title Set" and isinstance(obj, dict):
            titles = [parse_title(t) for t in obj.get("TitleList", [])]
            if titles:
                main = obj.get("MainFeature", -1)
                titles.sort(key=lambda t: (t.index != main, t.index))      # the main feature first, as HandBrake
                return titles
    tail = [ln for ln in r.stderr.splitlines() if ln.strip()][-1:]
    raise ScanFailed(f"No video found in {os.path.basename(path)}" + (f" ({tail[0]})" if tail else ""))


# --------------------------------------------------------------------------- what this build can do
def _list_after(text: str, header: str) -> list[str]:
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if header in line:
            out = []
            for ln in lines[i + 1:]:
                if not ln.startswith("                               ") or not ln.strip():
                    break
                out.append(ln.strip())
            return out
    return []


@dataclass
class Capabilities:
    video: list[str]
    audio: list[str]
    cli: str = ""
    _cache: dict = field(default_factory=dict)

    def options(self, kind: str, encoder: str) -> list[str]:
        """An encoder's presets / tunes / profiles / levels (HandBrakeCLI --encoder-<kind>-list)."""
        key = (kind, encoder)
        if key not in self._cache:
            r = run(self.cli, [f"--encoder-{kind}-list", encoder], 30)
            text = r.stdout + r.stderr
            vals, on = [], False
            for ln in text.splitlines():
                if ln.startswith("Available --encoder-"):
                    on = True
                    continue
                if on:
                    if not ln.startswith("    ") or not ln.strip():
                        if vals:
                            break
                        continue
                    vals.extend(v.strip() for v in ln.split(",") if v.strip())
            self._cache[key] = vals
        return self._cache[key]


def capabilities(cli: str) -> Capabilities:
    r = run(cli, ["--help"], 30)
    text = r.stdout + r.stderr
    return Capabilities(_list_after(text, "-e, --encoder <string>"), _list_after(text, "-E, --aencoder <string>"),
                        cli)


# --------------------------------------------------------------------------- quality scales
def quality_scale(encoder: str) -> tuple[float, float, bool, str]:
    """(low end, high end, lower-is-better, label) of the constant-quality slider, as HandBrake's per encoder."""
    if encoder in ("mpeg4", "mpeg2"):
        return 1, 31, True, "QP"
    if encoder == "theora" or encoder.startswith("VP8"):
        return 0, 63, encoder != "theora", "Q"
    if encoder.startswith(("svt_av1", "VP9")):
        return 0, 63, True, "RF" if encoder.startswith("svt") else "CQ"
    if encoder.startswith(("qsv_",)):
        return 0, 51, True, "ICQ"
    if encoder.startswith(("vce_",)):
        return 0, 51, True, "QP"
    if encoder.startswith(("nvenc_",)):
        return 0, 51, True, "CQ"
    return 0, 51, True, "RF"


# --------------------------------------------------------------------------- jobs
@dataclass
class AudioTrack:
    source: int                 # the source track number
    encoder: str = "av_aac"
    mixdown: str = "stereo"
    bitrate: int = 160          # kbps (ignored by passthru / lossless)
    samplerate: str = "auto"
    gain: float = 0.0
    drc: float = 0.0
    name: str = ""


@dataclass
class SubtitleTrack:
    source: int | str           # a track number, "scan" (foreign audio scan) or a path to an .srt / .ass file
    forced_only: bool = False
    burn: bool = False
    default: bool = False
    language: str = "und"       # external files
    offset_ms: int = 0          # external files


@dataclass
class Job:
    source: str
    title: int
    dest: str
    preset: dict
    range_mode: str = "chapters"          # chapters | seconds | frames
    start: float = 1
    end: float = 1
    audio: list[AudioTrack] | None = None              # None: the preset's own track choice
    subtitles: list[SubtitleTrack] | None = None
    chapter_names: list[str] | None = None
    source_name: str = ""
    duration: float = 0.0                              # seconds the encode covers (for the queue's details)

    def describe(self) -> str:
        return f"→ {os.path.basename(self.dest)}  ·  {self.preset.get('PresetName', '')}"


PRESET_NAME = "PR7-HB job"     # the name a job's own preset file gives its one preset


def preset_file(job: Job, folder: str) -> str:
    p = copy.deepcopy(job.preset)
    p.update(PresetName=PRESET_NAME, Type=1, Default=False, Folder=False)
    path = os.path.join(folder, "job-preset.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"PresetList": [p], "VersionMajor": 47, "VersionMinor": 0, "VersionMicro": 0}, f, indent=1)
    return path


def _num(v: float) -> str:
    return f"{v:g}"


def job_args(job: Job, folder: str) -> list[str]:
    """HandBrakeCLI's arguments for a job (files it needs are written to `folder`)."""
    args = ["--json", "--preset-import-file", preset_file(job, folder), "--preset", PRESET_NAME,
            "-i", job.source, "-t", str(job.title), "-o", job.dest]
    if job.range_mode == "chapters":
        args += ["-c", f"{int(job.start)}-{int(job.end)}"]
    elif job.range_mode == "seconds":
        args += ["--start-at", f"seconds:{_num(job.start)}", "--stop-at", f"seconds:{_num(job.end - job.start)}"]
    elif job.range_mode == "frames":
        args += ["--start-at", f"frame:{int(job.start)}", "--stop-at", f"frame:{int(job.end - job.start)}"]
    if job.audio is not None:
        if not job.audio:
            args += ["-a", "none"]
        else:
            col = lambda f: ",".join(f(t) for t in job.audio)            # noqa: E731
            args += ["-a", col(lambda t: str(t.source)), "-E", col(lambda t: t.encoder),
                     "-B", col(lambda t: str(t.bitrate)), "-6", col(lambda t: t.mixdown),
                     "-R", col(lambda t: t.samplerate), "--gain", col(lambda t: _num(t.gain)),
                     "-D", col(lambda t: _num(t.drc))]
            if any(t.name for t in job.audio):
                args += ["-A", col(lambda t: t.name.replace(",", " "))]
    if job.subtitles is not None:
        inner = [s for s in job.subtitles if not isinstance(s.source, str) or s.source == "scan"]
        files = [s for s in job.subtitles if isinstance(s.source, str) and s.source != "scan"]
        if inner:
            args += ["-s", ",".join(str(s.source) for s in inner)]
            forced = [str(i + 1) for i, s in enumerate(inner) if s.forced_only]
            burned = [i + 1 for i, s in enumerate(inner) if s.burn]
            default = [i + 1 for i, s in enumerate(inner) if s.default]
            if forced:
                args += ["--subtitle-forced=" + ",".join(forced)]
            if burned:
                args += [f"--subtitle-burned={burned[0]}"]
            if default:
                args += [f"--subtitle-default={default[0]}"]
        elif not files:
            args += ["--subtitle", "none"]
        if files:
            srt = [s for s in files if s.source.lower().endswith(".srt")]
            ssa = [s for s in files if not s.source.lower().endswith(".srt")]
            for group, opt in ((srt, "srt"), (ssa, "ssa")):
                if not group:
                    continue
                args += [f"--{opt}-file", ",".join(s.source for s in group),
                         f"--{opt}-lang", ",".join(s.language for s in group),
                         f"--{opt}-offset", ",".join(str(s.offset_ms) for s in group)]
                burn = [i + 1 for i, s in enumerate(group) if s.burn]
                if burn:
                    args += [f"--{opt}-burn={burn[0]}"]
                default = [i + 1 for i, s in enumerate(group) if s.default]
                if default:
                    args += [f"--{opt}-default={default[0]}"]
    if job.chapter_names and job.preset.get("ChapterMarkers", True):
        path = os.path.join(folder, "chapters.csv")
        write_chapters(path, job.chapter_names)
        args += [f"--markers={path}"]
    return args


# --------------------------------------------------------------------------- chapter names
def _escape(name: str) -> str:
    """HandBrake's chapter file is "number,name" with backslash escapes, not CSV quoting: a quoted "a, b" arrives
    as `"a` (tried with HandBrakeCLI)."""
    return name.replace("\\", "\\\\").replace(",", "\\,").replace('"', '\\"').replace("\n", " ")


def write_chapters(path: str, names: list[str]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        for i, name in enumerate(names, 1):
            f.write(f"{i},{_escape(name)}\n")


def read_chapters(path: str) -> list[str]:
    """A HandBrake chapter file (backslash escapes; plain CSV quoting is understood too)."""
    found: dict[int, str] = {}
    with open(path, encoding="utf-8-sig") as f:
        for line in f:
            line = line.rstrip("\r\n")
            num, sep, rest = line.partition(",")
            if not sep or not num.strip().isdigit():
                continue
            if len(rest) >= 2 and rest[0] == rest[-1] == '"' and "\\" not in rest:
                name = rest[1:-1].replace('""', '"')
            else:
                out, esc = [], False
                for ch in rest:
                    if esc:
                        out.append(ch)
                        esc = False
                    elif ch == "\\":
                        esc = True
                    else:
                        out.append(ch)
                name = "".join(out)
            found[int(num)] = name
    return [found.get(i, "") for i in range(1, max(found, default=0) + 1)]


# --------------------------------------------------------------------------- the preset's own track choice
def _lang_ok(track: Track, langs: list[str]) -> bool:
    return not langs or "any" in langs or "und" in langs or track.language in langs


def default_audio(preset: dict, title: Title) -> list[AudioTrack]:
    """The tracks HandBrake picks for a preset: by AudioTrackSelectionBehavior (none / first / all) and
    AudioLanguageList, each one given every AudioList entry; passthru only for codecs in AudioCopyMask, else the
    fallback encoder."""
    behaviour = preset.get("AudioTrackSelectionBehavior", "first")
    langs = preset.get("AudioLanguageList", []) or []
    if behaviour == "none" or not title.audio:
        return []
    picked = [t for t in title.audio if _lang_ok(t, langs)] or title.audio[:1]
    if behaviour == "first":
        picked = picked[:1]
    mask = {m.split(":", 1)[1] for m in preset.get("AudioCopyMask", []) if ":" in m}
    out = []
    for t in picked:
        for e in preset.get("AudioList", []) or [{"AudioEncoder": "av_aac", "AudioMixdown": "stereo",
                                                   "AudioBitrate": 160}]:
            enc = e.get("AudioEncoder", "av_aac")
            codec = t.codec.lower().replace("_", "")
            if enc.startswith("copy"):
                want = enc[5:] if enc.startswith("copy:") else None
                if (want and want not in codec) or (not want and not any(m in codec for m in mask)):
                    enc = preset.get("AudioEncoderFallback", "av_aac")
            out.append(AudioTrack(t.number, enc, e.get("AudioMixdown", "stereo") or "stereo",
                                  int(e.get("AudioBitrate", 160) or 160), str(e.get("AudioSamplerate", "auto")),
                                  float(e.get("AudioTrackGainSlider", 0.0)), float(e.get("AudioTrackDRCSlider", 0.0))))
    return out


def default_subtitles(preset: dict, title: Title) -> list[SubtitleTrack]:
    out: list[SubtitleTrack] = []
    if preset.get("SubtitleAddForeignAudioSearch") and title.subtitles:
        out.append(SubtitleTrack("scan", forced_only=True,
                                 burn=preset.get("SubtitleBurnBehavior", "none") in ("foreign", "foreign_first")))
    behaviour = preset.get("SubtitleTrackSelectionBehavior", "none")
    langs = preset.get("SubtitleLanguageList", []) or []
    if behaviour != "none":
        picked = [t for t in title.subtitles if _lang_ok(t, langs)]
        if behaviour == "first":
            picked = picked[:1]
        out += [SubtitleTrack(t.number) for t in picked]
    return out


# --------------------------------------------------------------------------- the Summary tab
def summary(preset: dict, audio: list[AudioTrack], subtitles: list[SubtitleTrack], fps_note: str = "") -> list[str]:
    enc = preset.get("VideoEncoder", "x264")
    lo, hi, lower, label = quality_scale(enc)
    if preset.get("VideoQualityType", 2) == 2:
        q = f"{label} {preset.get('VideoQualitySlider', 22):g}"
    else:
        q = f"{preset.get('VideoAvgBitrate', 6000)} kbps" + (" 2-pass" if preset.get("VideoMultiPass") else "")
    rate = preset.get("VideoFramerate", "auto")
    mode = {"vfr": "variable", "cfr": "constant", "pfr": "peak"}.get(preset.get("VideoFramerateMode", "vfr"), "")
    fr = "same framerate as source" if rate in ("auto", "") else f"{rate} FPS {mode}"
    lines = [f"{video_name(enc)}, {q}, {fr}"]
    for a in audio:
        if a.encoder.startswith("copy") or a.encoder.startswith("flac"):
            lines.append(f"Track {a.source}: {audio_name(a.encoder)}")
        else:
            mix = dict(MIXDOWNS).get(a.mixdown, a.mixdown)
            lines.append(f"Track {a.source}: {audio_name(a.encoder)}, {mix}, {a.bitrate} kbps")
    for s in subtitles:
        what = "Foreign audio scan" if s.source == "scan" else (
            os.path.basename(s.source) if isinstance(s.source, str) else f"Subtitle track {s.source}")
        lines.append(what + (", burned in" if s.burn else "") + (", forced only" if s.forced_only else ""))
    if preset.get("ChapterMarkers", True):
        lines.append("Chapter markers")
    return lines


def output_size(preset: dict, title: Title) -> tuple[int, int]:
    """The encoded picture size (storage) for the Summary and Dimensions tabs: the source after crop, fitted
    into the preset's resolution limit (PictureWidth / PictureHeight; 0 = none), never upscaled unless allowed,
    rounded down to the modulus."""
    mode = preset.get("PictureCropMode", 0)         # 0 automatic, 1 loose, 2 none, 3 custom (HandBrake's codes)
    top, bottom, left, right = title.crop if mode in (0, 1) else (
        (preset.get("PictureTopCrop", 0), preset.get("PictureBottomCrop", 0), preset.get("PictureLeftCrop", 0),
         preset.get("PictureRightCrop", 0)) if mode == 3 else (0, 0, 0, 0))
    w, h = max(2, title.width - left - right), max(2, title.height - top - bottom)
    mw, mh = preset.get("PictureWidth", 0) or 0, preset.get("PictureHeight", 0) or 0
    scale = 1.0
    if mw and w * scale > mw:
        scale = mw / w
    if mh and h * scale > mh:
        scale = min(scale, mh / h)
    if preset.get("PictureAllowUpscaling") and preset.get("PictureUseMaximumSize") and (mw or mh):
        scale = min(mw / w if mw else 1e9, mh / h if mh else 1e9)       # HandBrake: grow to fill the limit
    if scale > 1 and not preset.get("PictureAllowUpscaling", False):
        scale = 1.0
    mod = int(preset.get("PictureModulus", 2) or 2)
    return max(mod, int(w * scale) // mod * mod), max(mod, int(h * scale) // mod * mod)


def dest_name(source: str, preset: dict, folder: str, pattern: str = "{source}", title: int = 1) -> str:
    """The destination HandBrake suggests: the pattern ({source}, {title}, {preset}) in the folder, with the
    container's extension."""
    stem = Path(source.rstrip("\\/")).stem if not os.path.isdir(source) else Path(source.rstrip("\\/")).name
    name = (pattern or "{source}").replace("{source}", stem).replace("{title}", str(title)).replace(
        "{preset}", preset.get("PresetName", ""))
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name).strip(" .") or stem
    ext = CONTAINERS.get(preset.get("FileFormat", "av_mp4"), ("MP4", ".mp4"))[1]
    return os.path.join(folder, name + ext)


def with_extension(dest: str, preset: dict) -> str:
    ext = CONTAINERS.get(preset.get("FileFormat", "av_mp4"), ("MP4", ".mp4"))[1]
    root, old = os.path.splitext(dest)
    return root + ext if old.lower() in (".mp4", ".m4v", ".mkv", ".webm", "") else dest + ext


# --------------------------------------------------------------------------- progress
@dataclass
class Progress:
    state: str = "WAITING"      # WORKING | MUXING | SEARCHING | WORKDONE ...
    fraction: float = 0.0       # of the whole job (passes included)
    rate: float = 0.0
    rate_avg: float = 0.0
    eta: int = -1
    pass_no: int = 1
    passes: int = 1
    error: int | None = None    # WORKDONE's Error (0 = done)

    def text(self) -> str:
        if self.state == "MUXING":
            return "Muxing…"
        if self.state == "SEARCHING":
            return "Foreign audio scan…"
        bits = [f"{self.fraction * 100:.2f} %"]
        if self.rate > 0:            # HandBrake reports 0 until it has measured
            bits.append(f"{self.rate:.1f} FPS" + (f" (average {self.rate_avg:.1f})" if self.rate_avg > 0 else ""))
        if self.eta >= 0:
            bits.append(f"ETA {hms(self.eta)}")
        if self.passes > 1:
            bits.insert(0, f"pass {self.pass_no} of {self.passes}")
        return "  ·  ".join(bits)


class ProgressParser:
    """Feeds a running encode's stdout (--json) and keeps the latest Progress."""

    def __init__(self):
        self.reader = BlockReader()
        self.progress = Progress()

    def feed(self, chunk: str) -> Progress:
        for label, obj in self.reader.feed(chunk):
            if label != "Progress" or not isinstance(obj, dict):
                continue
            p = self.progress
            p.state = obj.get("State", p.state)
            if p.state in ("WORKING", "SEARCHING"):
                w = obj.get("Working") or obj.get("Searching") or {}
                p.passes = max(1, int(w.get("PassCount", 1) or 1))
                p.pass_no = max(1, int(w.get("Pass", 1) or 1))
                frac = float(w.get("Progress", 0.0))
                p.fraction = min(1.0, ((p.pass_no - 1) + frac) / p.passes)
                p.rate, p.rate_avg = float(w.get("Rate", 0.0)), float(w.get("RateAvg", 0.0))
                p.eta = int(w.get("ETASeconds", -1)) if w.get("Hours", -1) != -1 else -1
            elif p.state == "WORKDONE":
                p.error = int((obj.get("WorkDone") or {}).get("Error", 0))
                if p.error == 0:
                    p.fraction = 1.0
        return self.progress


ERRORS = {0: "", 1: "cancelled", 2: "the settings were refused", 3: "a file couldn't be read",
          4: "the source couldn't be read", 5: "a file couldn't be written", 6: "it ran out of memory",
          7: "it was cancelled"}


def temp_folder() -> str:
    return tempfile.mkdtemp(prefix="pr7hb-")
