# Paragon PR7-HB: notes for Claude

**Paragon PR7-HB** is the owner's personal video converter: Python (**PySide6**) that **works the way HandBrake
works**, in the Paragon family look (PR7-Z ... PR7-PM, PR7-SM `ARYEZ/Paragon-PR7-SM`). Windows 10/11 x64 is the target;
it runs on Linux for tests. The owner writes Python; explain the why.

## How it's built

- **No video code of our own** (PR7-Z's rule): every scan and encode runs the official HandBrakeCLI, unmodified.
  CI downloads the pinned Windows release (1.11.2, SHA-256 checked in build.yml) into `engine/` (git-ignored), the
  spec bundles it as `_internal/engine`. `engine.find_cli`: PR7HB_CLI, bundled, an installed HandBrake, PATH (tests on
  Linux: Ubuntu's `handbrake-cli`). To update: change the version and SHA-256 in build.yml, NOTICE, CHANGELOG.
- `pr7hb/engine.py` (no Qt): `scan` (`--json --scan -t 0`; `json_blocks` / `BlockReader` read the `Label: {...}`
  blocks), `Title` / `Track`, `capabilities` (encoders from `--help`, per-encoder presets / tunes / profiles / levels
  from `--encoder-*-list`), `quality_scale` per encoder. **A job is a HandBrake preset**: `job_args` writes the working
  preset to a temporary preset file (`--preset-import-file` + `--preset "PR7-HB job"`) and adds source, title, range
  (`-c` / `--start-at` + `--stop-at`, a duration), destination and the explicit tracks (`-a -E -B -6 -R --gain -D`,
  `-s`, `--srt-file`...). `default_audio` / `default_subtitles` = the preset's own track choice. Chapter names:
  `write_chapters` uses HandBrake's backslash escapes (CSV quoting breaks: `"a, b"` arrives as `"a`); HandBrake writes
  no markers for a one-chapter title. `ProgressParser` (WORKING / MUXING / WORKDONE, passes). PictureCropMode: 0 auto,
  1 loose, 2 none, 3 custom.
- `pr7hb/presets.py` (no Qt): built-ins via `-z` and `--preset NAME --preset-export NAME` (**--preset-export alone
  exports the current, i.e. default, settings under the name**), cached in <data>/builtin-presets.json per engine
  (`CACHE_VERSION`); `usable` hides hardware presets the build can't run and "CLI Defaults"; the user's presets in
  <data>/presets.json in HandBrake's format. <data> = %APPDATA%\Paragon\PR7-HB, **PR7HB_DATA** in tests.
- `pr7hb/queue.py`: `Queue` runs one job at a time in a QProcess (stdout -> progress, stderr -> the item's log, saved
  to <data>/logs); Pause = psutil suspend (HandBrakeCLI on Windows reads keys from the console, not a pipe); Stop
  kills and removes the half-written file; `wait()` for tests / selftest.
- `pr7hb/tabs.py`: the seven tabs bound to `win.preset` (`Tab.write` -> `win.preset_edited`); audio / subtitle rows
  are `win.audio_tracks` / `subtitle_tracks` (`tracks_edited`). Radios that are siblings need QButtonGroups (else Qt
  makes them one set). Combo data that Qt converts (tuples) breaks findData: use strings ("640x360").
- `pr7hb/preview.py`: frames via QMediaPlayer + QVideoSink (play + pause once, then seek: a seek while stopped gives
  nothing); `PreviewPanel` (10 frames, crop dimmed); live preview = a 15 s encode in `win.preview_queue`, opened in
  PR7-M via `family.launch` (else the default player).
- `pr7hb/main_window.py`: source -> title / range -> preset -> tabs -> Save as; `make_job`, `_settle_dest` (ask /
  rename / overwrite), `add_all` (a folder batch or every title), `when_done` (`answers["system"]` in tests).
  `dialogs.py`: QueueWindow, LogWindow, PresetsDialog, SavePresetDialog, OptionsDialog, PreviewWindow. `_ask` /
  `answers` / `said`; `sync=True` runs scans inline.
- `pr7hb/app.py`: one window per user (QLocalSocket hand-off of a source, PR7-R's Windows fix); command-line modes
  never let an error escape (PR7-IS's lesson); `--selftest OUT.json` (writes a video with `sample.py`, scans,
  encodes through the queue, reads it back; CI runs it on the installed exe).
- `pr7hb/sample.py`: test AVIs in pure Python (PR7-M's Motion-JPEG writer plus a PCM track). Tests make a
  two-chapter MKV with ffmpeg when it's there (skipped otherwise).
- Installer `installer/pr7hb.iss` (per user, AppId {5A2D8918-1C5C-456F-AFCF-1FBA498EA280} permanent; desktopicon);
  CI installs it, `tools/verify_install.py installed|uninstalled`. Spec: file details, no UPX, Qt Multimedia kept,
  PyInstaller's bootloader built in CI, Defender scan (PR7-F's false-positive fix).
- Updates: `pr7hb/updates.py` / `update_ui.py` (the family's files, keep them in step; with PR7-U installed,
  update_ui offers it); `family.py`: the family's AppIds (PR7-HB included).
- `pr7hb/finish.py` (no Qt): the family's finish (OBSIDIAN / AURORA), one choice for every app:
  HKCU\Software\Paragon\Family "Finish" (a file elsewhere; PARAGON_FAMILY_FILE in tests, conftest). `finish.start`
  at start-up, `set_finish` saves it, app.py's 2 s timer `finish.follow`s another app's switch. The same file in every
  family app: keep them in step.

## The look (family rules)

- Theme is PR7-SM's (OBSIDIAN + AURORA) plus tab and slider rules. Colours: the family's only; Inter; labels UPPER
  CASE; file names keep their case.
- The PR7-HB mark: PR7 `Logo.cpp` geometry plus H (new, the dash's height for its bar) and B (PR7-CB's); icon "7HB"
  by `tools/make_icon.py`, wizard art by `tools/make_installer_art.py`. Mock-up: `tools/mockup.py`. Check visuals
  with `QT_SCALE_FACTOR=2 python tools/screenshots.py OUT` (the real window on a generated video).

## Rules

- Behaviour questions: do what HandBrake does (presets, tabs, queue, defaults).
- Tests: `python -m pytest` (offscreen) with the real HandBrakeCLI on generated videos; encodes are checked by
  scanning the result. Never the real settings or data folder (conftest).
- Releases: bump `__version__` in `pr7hb/__init__.py` and add a `## x.y.z` section to CHANGELOG.md, then push: CI
  publishes that version by itself once every check has passed. Run workflow / `v*` tags still work.
