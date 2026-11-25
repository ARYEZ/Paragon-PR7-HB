"""The engine against the real HandBrakeCLI: scans of real files, real encodes checked by reading the result back."""
import os

import pytest

from conftest import CLI, needs_cli
from pr7hb import engine, presets

pytestmark = needs_cli


def test_scan_reads_the_title(media):
    t = engine.scan(CLI, media["clip"])[0]
    assert (t.width, t.height) == (320, 180) and abs(t.duration - 3) < 0.2 and round(t.fps) == 10
    assert t.codec == "mjpeg" and len(t.audio) == 1 and t.audio[0].channels == 2 and t.audio[0].number == 1
    assert t.label().endswith("00:00:03") and "320 × 180 · 10 FPS · MJPEG · 1 audio" == t.describe()
    assert engine.scan(CLI, media["silent"])[0].audio == []


def test_scan_of_something_that_isnt_a_video(tmp_path):
    bad = tmp_path / "notes.txt"
    bad.write_text("not a video")
    with pytest.raises(engine.ScanFailed, match="notes.txt"):
        engine.scan(CLI, str(bad))


def test_the_build_lists_its_encoders():
    caps = engine.capabilities(CLI)
    assert "x264" in caps.video and "x265" in caps.video and "av_aac" in caps.audio and "copy:aac" in caps.audio
    assert "slow" in caps.options("preset", "x264") and "film" in caps.options("tune", "x264")
    assert "main10" in caps.options("profile", "x265_10bit") and "auto" in caps.options("level", "x265")


def test_builtin_presets_are_handbrakes(builtin):
    names = [p.name for p in builtin]
    fast = presets.find(builtin, presets.DEFAULT)
    assert fast and fast.category == "General" and fast.settings["VideoEncoder"] == "x264" and len(names) > 20
    assert {"General", "Web", "Devices", "Matroska"} <= {p.category for p in builtin}
    # each preset's own settings, not the defaults under its name (--preset-export alone gives those)
    av1 = presets.find(builtin, "Very Fast 2160p60 4K AV1").settings
    assert av1["VideoEncoder"].startswith("svt_av1") and av1["PictureWidth"] == 3840 and av1["VideoFramerate"] == "60"
    small = presets.find(builtin, "Fast 480p30").settings
    assert (small["PictureWidth"], small["PictureHeight"], small["VideoFramerate"]) == (720, 480, "30")
    shown = presets.usable(builtin, engine.capabilities(CLI).video)
    assert presets.find(shown, presets.DEFAULT) and not any(p.category == "CLI Defaults" for p in shown)
    assert all(p.settings["VideoEncoder"] in engine.capabilities(CLI).video for p in shown)    # no NVEnc here
    mkv = presets.find(builtin, "H.265 MKV 1080p30").settings
    assert mkv["FileFormat"] == "av_mkv" and mkv["VideoEncoder"].startswith("x265")


def test_parse_list():
    text = "[12:00:00] hb_init\nGeneral/\n    Fast 1080p30\n        H.264 video (up to 1080p30) and AAC\n" \
           "        stereo audio.\nWeb/\n    Discord Nitro Small 2-4 Minutes 480p30\n"
    assert presets.parse_list(text) == [("General", "Fast 1080p30", "H.264 video (up to 1080p30) and AAC stereo audio."),
                                        ("Web", "Discord Nitro Small 2-4 Minutes 480p30", "")]


def _probe(path):
    """What HandBrake itself reads back from an encoded file."""
    return engine.scan(CLI, path)[0]


def _encode(job, tmp_path):
    import subprocess
    args = engine.job_args(job, str(tmp_path))
    r = subprocess.run([CLI, *args], capture_output=True, text=True, timeout=300)
    p = engine.ProgressParser()
    p.feed(r.stdout)
    return r, p.progress


def test_a_job_encodes_with_the_tabs_changes(media, builtin, tmp_path):
    preset = dict(presets.find(builtin, "Fast 480p30").settings)
    preset.update(VideoEncoder="x265", VideoQualitySlider=30, FileFormat="av_mkv", PictureWidth=160, PictureHeight=90)
    dest = str(tmp_path / "out.mkv")
    job = engine.Job(media["clip"], 1, dest, preset, "seconds", 0.5, 2.5)
    r, prog = _encode(job, tmp_path)
    assert r.returncode == 0 and prog.state == "WORKDONE" and prog.error == 0 and prog.fraction == 1.0
    t = _probe(dest)
    assert (t.width, t.height) == (160, 90) and t.codec == "hevc" and abs(t.duration - 2.0) < 0.35
    assert len(t.audio) == 1


def test_explicit_audio_tracks_and_no_audio(media, builtin, tmp_path):
    preset = dict(presets.find(builtin, "Fast 480p30").settings)
    job = engine.Job(media["clip"], 1, str(tmp_path / "two.mp4"), preset, "chapters", 1, 1,
                     audio=[engine.AudioTrack(1, "av_aac", "stereo", 96), engine.AudioTrack(1, "ac3", "mono", 128)])
    r, prog = _encode(job, tmp_path)
    assert prog.error == 0
    t = _probe(str(tmp_path / "two.mp4"))
    assert [a.codec for a in t.audio] == ["aac", "ac3"] and [a.channels for a in t.audio] == [2, 1]
    job = engine.Job(media["clip"], 1, str(tmp_path / "none.mp4"), preset, "chapters", 1, 1, audio=[])
    _encode(job, tmp_path)
    assert _probe(str(tmp_path / "none.mp4")).audio == []


def test_external_subtitles_are_muxed(media, builtin, tmp_path):
    srt = tmp_path / "clip.srt"
    srt.write_text("1\n00:00:00,200 --> 00:00:01,200\nFirst line\n\n", encoding="utf-8")
    preset = dict(presets.find(builtin, "Fast 480p30").settings)
    preset["FileFormat"] = "av_mkv"
    job = engine.Job(media["clip"], 1, str(tmp_path / "subs.mkv"), preset, "chapters", 1, 1,
                     subtitles=[engine.SubtitleTrack(str(srt), language="eng", default=True)])
    r, prog = _encode(job, tmp_path)
    assert prog.error == 0, r.stderr[-500:]
    t = _probe(str(tmp_path / "subs.mkv"))
    assert len(t.subtitles) == 1 and t.subtitles[0].language == "eng"


def test_progress_parser_reads_pieces_and_passes():
    p = engine.ProgressParser()
    p.feed('Progress: {\n    "State": "WORKING",\n    "Working": {\n        "ETASeconds": 760,\n')
    assert p.progress.state == "WAITING"                                   # half a block: nothing yet
    p.feed('        "Hours": 0,\n        "Pass": 2,\n        "PassCount": 2,\n        "Progress": 0.5,\n'
           '        "Rate": 63.2,\n        "RateAvg": 61.8\n    }\n}\n')
    pr = p.progress
    assert pr.state == "WORKING" and pr.fraction == 0.75 and pr.eta == 760 and pr.rate == 63.2
    assert pr.text() == "pass 2 of 2  ·  75.00 %  ·  63.2 FPS (average 61.8)  ·  ETA 00:12:40"
    q = engine.Progress(state="WORKING", fraction=0.2, rate=0.0)
    assert q.text() == "20.00 %"                                            # no rate measured yet: none shown
    p.feed('Progress: {\n "State": "WORKDONE",\n "WorkDone": {\n  "Error": 3\n }\n}\n')
    assert p.progress.error == 3 and engine.ERRORS[3]


def test_default_tracks_follow_the_preset():
    t = engine.Title(1, "x", "x", 60, 1920, 1080, 25, "h264")
    t.audio = [engine.Track(1, "English AC3 5.1", "eng", "ac3", 6), engine.Track(2, "Deutsch AAC", "deu", "aac", 2)]
    t.subtitles = [engine.Track(1, "English", "eng", kind="subtitle"), engine.Track(2, "Deutsch", "deu", kind="subtitle")]
    preset = {"AudioTrackSelectionBehavior": "first", "AudioLanguageList": ["deu"], "AudioCopyMask": ["copy:aac"],
              "AudioEncoderFallback": "av_aac",
              "AudioList": [{"AudioEncoder": "copy:aac", "AudioMixdown": "stereo", "AudioBitrate": 160}],
              "SubtitleAddForeignAudioSearch": True, "SubtitleBurnBehavior": "foreign",
              "SubtitleTrackSelectionBehavior": "all", "SubtitleLanguageList": ["eng"]}
    a = engine.default_audio(preset, t)
    assert [(x.source, x.encoder) for x in a] == [(2, "copy:aac")]               # German first; AAC can pass through
    preset["AudioLanguageList"] = ["eng"]
    assert [(x.source, x.encoder) for x in engine.default_audio(preset, t)] == [(1, "av_aac")]   # AC3: the fallback
    preset["AudioTrackSelectionBehavior"] = "all"
    preset["AudioLanguageList"] = []
    assert [x.source for x in engine.default_audio(preset, t)] == [1, 2]
    s = engine.default_subtitles(preset, t)
    assert [(x.source, x.burn, x.forced_only) for x in s] == [("scan", True, True), (1, False, False)]


def test_output_size_and_names():
    t = engine.Title(1, "x", "x", 60, 3840, 2160, 24, "hevc", crop=(140, 140, 0, 0))
    assert engine.output_size({"PictureWidth": 1920, "PictureHeight": 1080, "PictureCropMode": 0}, t) == (1920, 940)    # 2160 - 280 cropped, halved
    assert engine.output_size({"PictureWidth": 0, "PictureHeight": 0, "PictureCropMode": 2}, t) == (3840, 2160)  # none
    assert engine.output_size({"PictureCropMode": 3, "PictureLeftCrop": 40, "PictureRightCrop": 40}, t) == (3760, 2160)
    small = engine.Title(1, "x", "x", 60, 640, 360, 24, "h264")
    assert engine.output_size({"PictureWidth": 1920, "PictureHeight": 1080}, small) == (640, 360)   # no upscaling
    assert engine.output_size({"PictureWidth": 1920, "PictureHeight": 1080, "PictureAllowUpscaling": True},
                              small) == (640, 360)                       # allowed, but not asked for (Optimal size)
    assert engine.output_size({"PictureWidth": 1920, "PictureHeight": 1080, "PictureAllowUpscaling": True,
                               "PictureUseMaximumSize": True}, small) == (1920, 1080)
    d = engine.dest_name(r"D:\Footage\ELSEWORLD master.mkv".replace("\\", os.sep), {"FileFormat": "av_mp4"}, "out")
    assert d == os.path.join("out", "ELSEWORLD master.mp4")
    assert engine.with_extension("a/b.mp4", {"FileFormat": "av_mkv"}) == "a/b.mkv"
    assert engine.dest_name("x/clip.avi", {"FileFormat": "av_webm", "PresetName": "Web"}, "o",
                            "{source} - {preset}") == os.path.join("o", "clip - Web.webm")
