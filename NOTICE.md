# Notices

- **HandBrake** (HandBrakeCLI 1.11.2, GNU General Public License v2): PR7-HB's engine, shipped **unmodified** as a
  separate program in `_internal\engine` with its own licence (`engine\doc\COPYING`) and notices. It is the official
  Windows build from https://github.com/HandBrake/HandBrake/releases/tag/1.11.2 (CI checks its SHA-256). Its complete
  source code is at that page (`HandBrake-1.11.2-source.tar.bz2`) and at https://github.com/HandBrake/HandBrake.
  PR7-HB runs it as a separate process and contains none of its code.
- **Qt / PySide6** (LGPL v3), shipped unmodified as separate libraries; Qt Multimedia's FFmpeg (LGPL 2.1) reads the
  preview frames.
- **psutil** (BSD 3-Clause) pauses and resumes the encoder.
- **Inter** typeface (SIL Open Font License 1.1): `pr7hb/fonts/OFL-LICENSE.txt`.
- HandBrake is the model for how PR7-HB behaves; its window's code and artwork are not used.
