"""The window driven like a user, checked by what lands on disk: every encode is read back by the real engine."""
import json
import os
import time

import pytest

from PySide6.QtCore import Qt

from conftest import CLI, needs_cli
from pr7hb import engine, presets, queue, settings, tabs

pytestmark = needs_cli


def encode(w, timeout=300):
    item = w.add_to_queue()
    assert item is not None
    w.queue.start()
    assert w.queue.wait(timeout)
    assert item.state == queue.DONE, item.error
    return engine.scan(CLI, item.job.dest)[0], item


def test_open_source_fills_the_window(window, media, tmp_path):
    w = window
    assert w.preset_name == presets.DEFAULT and w.preset["VideoEncoder"] == "x264"
    w.open_source(media["clip"])
    assert w.title is not None and w.source_name.text() == "clip.avi"
    assert w.source_info.text() == "320 × 180 · 10 FPS · MJPEG · 1 audio"
    assert w.duration.text() == "00:00:03" and w.range_mode.value() == "chapters"
    assert w.dest.text() == str(tmp_path / "out" / "clip.mp4")
    assert [(a.source, a.encoder) for a in w.audio_tracks] == [(1, "av_aac")]   # the preset's own choice
    assert "H.264 (x264), RF 22" in w.summary_tab.tracks.text()
    assert w.summary_tab.size.text() == "·  320 × 180 storage, 320 × 180 display"
    assert w.keys["add"].isEnabled() and w.keys["start"].isEnabled()


def test_the_tabs_changes_reach_the_file(window, media):
    w = window
    w.open_source(media["clip"])
    v = w.video_tab
    v.encoder.setCurrentIndex(v.encoder.findData("x265"))                 # Video: H.265
    assert w.preset["VideoEncoder"] == "x265" and w.modified and "(modified)" in w.preset_box.currentText()
    v.q.setValue(51 - 30)                                                   # RF 30 (the slider runs low-quality first)
    assert w.preset["VideoQualitySlider"] == 30.0 and v.q_label.text() == "RF 30"
    assert v.cq.isChecked() and (v.mode_a.isChecked() or v.mode_b.isChecked())    # two separate radio pairs
    v.mode_a.setChecked(True)                                               # 30 FPS constant, not peak
    assert w.preset["VideoFramerateMode"] == "cfr" and v.cq.isChecked()
    d = w.dims_tab
    d.limit.setCurrentIndex(d.limit.findData("640x360"))                  # the limit alone never upscales
    assert (w.preset["PictureWidth"], w.preset["PictureHeight"]) == (640, 360)
    w.preset.update(PictureWidth=160, PictureHeight=90)
    w.preset_edited()
    assert d.final.text().startswith("160 × 90 storage")
    w.summary_tab.format.setCurrentIndex(w.summary_tab.format.findData("av_mkv"))   # Summary: MKV
    assert w.dest.text().endswith("clip.mkv")
    got, item = encode(w)
    assert got.codec == "hevc" and (got.width, got.height) == (160, 90) and item.job.dest.endswith(".mkv")
    assert item.job.preset["PresetName"] == "Fast 1080p30 (modified)"


def test_audio_rows_are_the_files_tracks(window, media):
    w = window
    w.open_source(media["clip"])
    w.audio_tab.add_track(1)                                               # a second track from the same source
    assert len(w.audio_tracks) == 2
    enc = w.audio_tab.table.cellWidget(1, 1)
    enc.setCurrentIndex(enc.findData("ac3"))
    mix = w.audio_tab.table.cellWidget(1, 2)
    mix.setCurrentIndex(mix.findData("mono"))
    assert (w.audio_tracks[1].encoder, w.audio_tracks[1].mixdown) == ("ac3", "mono")
    got, _ = encode(w)
    assert [(a.codec, a.channels) for a in got.audio] == [("aac", 2), ("ac3", 1)]
    w.audio_tab.table.cellWidget(0, 7).click()                              # Remove, twice: no audio
    w.audio_tab.table.cellWidget(0, 7).click()
    assert w.audio_tracks == [] and w.audio_tab.count.text() == "No audio"
    w.dest.setText(w.dest.text().replace("clip.mp4", "silent.mp4"))
    got, _ = encode(w)
    assert got.audio == []
    w.reset_tracks()
    assert len(w.audio_tracks) == 1


def test_range_in_seconds_and_an_imported_subtitle(window, media, tmp_path):
    w = window
    w.open_source(media["clip"])
    w.range_mode.setCurrentIndex(w.range_mode.findData("seconds"))
    w.range_a.setValue(1)
    w.range_b.setValue(3)
    assert w.duration.text() == "00:00:02"
    srt = tmp_path / "clip.eng.srt"
    srt.write_text("1\n00:00:00,100 --> 00:00:01,000\nHello\n\n", encoding="utf-8")
    w.answers["open_any"] = str(srt)
    w.summary_tab.format.setCurrentIndex(w.summary_tab.format.findData("av_mkv"))
    w.import_subtitles()
    assert w.subtitle_tracks[-1].language == "eng" and "clip.eng.srt" in w.summary_tab.tracks.text()
    got, _ = encode(w)
    assert abs(got.duration - 2.0) < 0.35 and [s.language for s in got.subtitles] == ["eng"]


def test_the_file_exists_question(window, media, tmp_path):
    w = window
    w.open_source(media["clip"])
    os.makedirs(tmp_path / "out", exist_ok=True)
    (tmp_path / "out" / "clip.mp4").write_bytes(b"old")
    w.answers["overwrite"] = None                                           # Cancel
    assert w.add_to_queue() is None and w.queue.items == []
    w.answers["overwrite"] = "rename"
    it = w.add_to_queue()
    assert it.job.dest == str(tmp_path / "out" / "clip (2).mp4")
    it2 = w.add_to_queue()                                                  # the queue's own destinations count too
    assert it2.job.dest not in (it.job.dest, str(tmp_path / "out" / "clip.mp4"))
    settings.set("when_exists", "overwrite")
    w.queue.items.clear()
    it = w.add_to_queue()
    assert it.job.dest == str(tmp_path / "out" / "clip.mp4")
    w.dest.setText(media["clip"])
    assert w.make_job() is None and "source" in w.said[-1][1]


def test_presets_save_reapply_delete(window, media):
    w = window
    w.open_source(media["clip"])
    w.video_tab.q.setValue(51 - 28)
    w.answers["save_preset"] = ("My Archive", "RF 28 x264", True)
    w.save_new_preset()
    saved = json.load(open(presets.user_file(), encoding="utf-8"))["PresetList"]
    assert [p["PresetName"] for p in saved] == ["My Archive"] and saved[0]["VideoQualitySlider"] == 28.0
    assert w.preset_name == "My Archive" and not w.modified and w.default_preset() == "My Archive"
    w.choose_preset("Fast 480p30")
    assert w.preset["PictureWidth"] == 720
    w.choose_preset("My Archive")
    assert w.preset["VideoQualitySlider"] == 28.0
    w.answers["save_preset"] = ("Fast 1080p30", "", False)                   # HandBrake's own name: refused
    w.save_new_preset()
    assert "own presets" in w.said[-1][1]
    shown = {}
    w.answers["presets"] = lambda d: shown.setdefault("d", d)
    d = w.show_presets()
    tops = [d.tree.topLevelItem(i).text(0) for i in range(d.tree.topLevelItemCount())]
    assert "GENERAL" in tops and "CUSTOM PRESETS" in tops and "CLI DEFAULTS" not in tops
    assert d.selected().name == "My Archive" and d.b_delete.isEnabled()
    d.delete()
    assert presets.user() == [] and w.default_preset() == presets.DEFAULT


def test_presets_export_and_import_handbrakes_format(window, tmp_path):
    w = window
    w.answers["save_preset"] = ("Small", "", False)
    w.save_new_preset()
    p = presets.find(presets.user(), "Small")
    presets.export(p, str(tmp_path / "small.json"))
    presets.delete_user("Small")
    w.answers["open_any"] = str(tmp_path / "small.json")
    w.import_presets()
    assert presets.find(w.all_presets(), "Small") and "Imported 1 preset" in w.said[-1][1]
    # HandBrakeCLI itself reads the exported file
    r = engine.run(CLI, ["--preset-import-file", str(tmp_path / "small.json"), "-z"])
    assert "Small" in r.stdout + r.stderr


def test_a_folder_is_a_batch_and_add_all_queues_each(window, media, tmp_path):
    w = window
    folder = tmp_path / "batch"
    folder.mkdir()
    import shutil
    for n in ("a.avi", "b.avi"):
        shutil.copy(media["clip"], folder / n)
    (folder / "notes.txt").write_text("not a video")
    w.open_source(str(folder))
    assert w.source_name.text() == "a.avi" and len(w.batch) == 2 and w.acts["add_all"].isEnabled()
    assert w.add_all() == 2
    assert [os.path.basename(i.job.dest) for i in w.queue.items] == ["a.mp4", "b.mp4"]


def test_preview_frames_and_the_live_preview(window, media, qapp):
    w = window
    w.open_source(media["clip"])
    g = w.preview.grabber
    g.wait(30)
    assert len(w.preview.frames) >= 8 and w.preview.picture.image is not None
    assert w.preview.picture.caption.startswith("PREVIEW  ·  6 OF 10")
    w.preview.next.click()
    assert "7 OF 10" in w.preview.picture.caption
    opened = []
    w.answers["launch"] = lambda app_name, args: opened.append((app_name, args)) or True
    w.preview.play.click()                                                 # live preview from 00:00:01
    assert w.preview_queue.wait(120)
    assert opened and opened[0][0] == "PR7-M" and os.path.exists(opened[0][1][0])
    t = engine.scan(CLI, opened[0][1][0])[0]
    assert t.duration < 3.0                                                # from the preview's place to the end
    pw = w.show_preview()
    assert pw.picture.image is not None


def test_queue_window_log_and_when_done(window, media):
    w = window
    w.open_source(media["clip"])
    qw = w.show_queue()
    w.add_to_queue()
    assert qw.list.count() == 1 and qw.keys["start"].isEnabled() and not qw.keys["pause"].isEnabled()
    calls = []
    w.answers["system"] = calls.append
    qw.when.setCurrentIndex(qw.when.findData("shutdown"))
    qw.keys["start"].click()
    assert w.queue.wait(300)
    card = qw.list.itemWidget(qw.list.item(0))
    assert card.state.text() == "DONE" and "done in" in card.detail.text()
    import sys
    assert calls and calls[0][0] == ("shutdown" if sys.platform == "win32" else "systemctl")
    log = w.show_log()
    assert "Encode done" in log.text.toPlainText() or "HandBrake has exited" in log.text.toPlainText()
    assert qw.keys["clear"].isEnabled()
    qw.keys["clear"].click()
    assert qw.list.count() == 0


def test_filters_and_rotation_reach_the_file(window, media):
    w = window
    w.open_source(media["clip"])
    f = w.filters_tab
    f.gray.setChecked(True)
    f.deint.setCurrentIndex(f.deint.findData("decomb"))
    assert w.preset["PictureDeinterlaceFilter"] == "decomb" and f.deint_preset.isEnabled()
    w.dims_tab.rotate.setCurrentIndex(w.dims_tab.rotate.findData(90))
    assert w.preset["PictureRotate"] == "angle=90:hflip=0"
    assert "Grayscale" in w.summary_tab.filters.text() and "Decomb" in w.summary_tab.filters.text()
    got, _ = encode(w)
    assert (got.width, got.height) == (180, 320)                           # turned a quarter
    # grayscale: the encoded frame has no colour (read back through Qt Multimedia)
    from pr7hb.preview import Grabber
    frames = {}
    g = Grabber()
    g.frame.connect(lambda i, img: frames.setdefault(i, img))
    g.grab(_dest(w), [500])
    g.wait(20)
    c = frames[0].pixelColor(5, 5)
    assert abs(c.red() - c.green()) < 12 and abs(c.green() - c.blue()) < 12


def _dest(w):
    return [i.job.dest for i in w.queue.items][-1]


def test_options_change_the_destination(window, media, tmp_path):
    w = window
    w.open_source(media["clip"])

    def fill(d):
        d.folder.setText(str(tmp_path / "elsewhere"))
        d.pattern.setText("{source} - {preset}")
    w.answers["options"] = fill
    w.options()
    w._update_dest()
    assert w.dest.text() == str(tmp_path / "elsewhere" / "clip - Fast 1080p30.mp4")


def test_chapter_names_round_trip(window, media, tmp_path):
    w = window
    w.open_source(media["clip"])
    assert w.chapter_names == ["Chapter 1"] and "one chapter" in w.chapters_tab.note.text()
    if "chapters" not in media:
        pytest.skip("making a source with chapters needs ffmpeg")
    w.open_source(media["chapters"])
    assert w.chapter_names == ["Part 1", "Part 2"] and w.chapters_tab.note.text() == ""
    w.chapters_tab.table.item(1, 2).setText('The, End "Final"')            # HandBrake's file needs escapes for these
    assert w.chapter_names == ["Part 1", 'The, End "Final"']
    w.answers["save_file"] = str(tmp_path / "ch.csv")
    w.export_chapters()
    assert tabs.read_chapter_csv(str(tmp_path / "ch.csv")) == ["Part 1", 'The, End "Final"']
    got, _ = encode(w)
    assert [n for n, _ in got.chapters] == ["Part 1", 'The, End "Final"']


def test_selftest(tmp_path):
    from pr7hb import app
    out = tmp_path / "st.json"
    assert app.selftest(str(out)) == 0
    r = json.loads(out.read_text())
    assert r["encoded"] and r["done"] and r["presets"] > 20 and r["log"]


def test_version(capsys):
    from pr7hb import __version__, app
    assert app.main(["--version"]) == 0 and capsys.readouterr().out.strip() == __version__


def test_a_scan_failure_is_said(window, tmp_path):
    bad = tmp_path / "broken.mkv"
    bad.write_bytes(b"\x1aE\xdf\xa3 not really")
    window.open_source(str(bad))
    assert window.title is None and "No video found" in window.said[-1][1]
    empty = tmp_path / "empty"
    empty.mkdir()
    window.open_source(str(empty))
    assert "no videos" in window.said[-1][1]


def test_keys_follow_state(window, media):
    w = window
    assert not w.keys["add"].isEnabled() and not w.keys["pause"].isEnabled()
    w.open_source(media["clip"])
    assert w.keys["add"].isEnabled() and not w.acts["add_all"].isEnabled()
    time.sleep(0)
    assert w.tabs.tabText(3) == "VIDEO" and Qt is not None
