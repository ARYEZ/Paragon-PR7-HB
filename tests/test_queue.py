"""The queue running the real HandBrakeCLI: jobs in order, progress, failures, stop, pause, the logs."""
import os
import time

from conftest import CLI, needs_cli
from pr7hb import engine, presets, queue

pytestmark = needs_cli


def _job(media, builtin, dest, **kw):
    preset = dict(presets.find(builtin, "Fast 480p30").settings)
    preset.update(kw.pop("preset", {}))
    return engine.Job(kw.pop("source", media["clip"]), 1, str(dest), preset, "chapters", 1, 1, **kw)


def test_jobs_run_in_order_and_leave_logs(qapp, media, builtin, tmp_path):
    q = queue.Queue(CLI)
    a = q.add(_job(media, builtin, tmp_path / "a.mp4"))
    b = q.add(_job(media, builtin, tmp_path / "out" / "b.mkv", preset={"FileFormat": "av_mkv"}))
    seen, done = [], []
    q.changed.connect(lambda it: seen.append((it.name(), it.state)) if it else None)
    q.done.connect(lambda: done.append(True))
    q.start()
    assert q.wait(300)
    assert a.state == b.state == queue.DONE and done == [True] and not q.running
    assert (tmp_path / "a.mp4").stat().st_size > 1000 and (tmp_path / "out" / "b.mkv").exists()   # folder made
    assert engine.scan(CLI, str(tmp_path / "out" / "b.mkv"))[0].width == 320
    order = [s for s in seen if s[1] == queue.ENCODING]
    assert order[0][0] == "clip.avi" and a.started <= b.started and a.progress.fraction == 1.0
    assert os.path.exists(a.log_path) and "Encode done" in open(a.log_path, encoding="utf-8").read()
    assert a.detail().startswith("→ a.mp4  ·  done in 00:00:")


def test_a_failure_doesnt_stop_the_queue(qapp, media, builtin, tmp_path):
    bad = tmp_path / "broken.avi"
    bad.write_bytes(b"RIFF....AVI garbage")
    q = queue.Queue(CLI)
    x = q.add(_job(media, builtin, tmp_path / "x.mp4", source=str(bad)))
    y = q.add(_job(media, builtin, tmp_path / "y.mp4"))
    q.start()
    assert q.wait(300)
    assert x.state == queue.FAILED and x.error and not (tmp_path / "x.mp4").exists()
    assert y.state == queue.DONE
    q.retry(x)
    assert x.state == queue.WAITING and x.error == ""
    q.remove(x)
    q.clear_done()
    assert q.items == []


def test_stop_cancels_and_removes_the_half_file(qapp, media, builtin, tmp_path):
    long = tmp_path / "long.avi"
    from pr7hb import sample as sample_media
    sample_media.clip(long, seconds=40, fps=25, size=(1280, 720))
    q = queue.Queue(CLI)
    it = q.add(_job(media, builtin, tmp_path / "long.mp4", source=str(long),
                    preset={"VideoEncoder": "x265", "VideoPreset": "slow", "PictureWidth": 1280,
                            "PictureHeight": 720}))
    q.start()
    end = time.time() + 60
    while it.progress.fraction <= 0 and time.time() < end:
        qapp.processEvents()
        time.sleep(0.05)
    assert it.state == queue.ENCODING and 0 < it.progress.fraction < 1
    assert q.pause() and it.state == queue.PAUSED
    f = it.progress.fraction
    for _ in range(10):
        qapp.processEvents()
        time.sleep(0.05)
    assert it.progress.fraction - f < 0.05                       # suspended: (almost) nothing more
    q.stop()
    assert q.wait(30)
    assert it.state == queue.CANCELLED and not (tmp_path / "long.mp4").exists() and not q.running


def test_human_sizes():
    assert queue.human(312_000_000) == "312 MB" and queue.human(1_240_000_000) == "1.24 GB"
    assert queue.human(900) == "900 bytes"
