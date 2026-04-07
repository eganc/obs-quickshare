# OBS QuickShare — Project Specification v2

## Overview
An open-source CLI tool that configures OBS Studio for a one-click async screen recording workflow.
Targets a "Loom-like" experience: record → auto-remux to MP4 → sync to Google Drive, with zero
manual steps after the initial install.

---

## Platform Priority
1. **macOS** (primary target)
2. Windows (secondary)
3. Linux (best-effort, community-maintained)

OBS config root:
- macOS:  `~/Library/Application Support/obs-studio/`
- Windows: `%APPDATA%\obs-studio\`
- Linux:  `~/.config/obs-studio/`

---

## Phase 1 — Core Installer

### 1.1 OBS Detection
- Locate OBS config root per platform (see above).
- Abort with a clear error if OBS has never been launched (config root missing).
- Detect OBS version from `global.ini` (`[General] > Version`) — warn if < 28.0 (required for
  NVENC CQP and auto-remux support on all platforms).

### 1.2 Encoder Detection
Probe available encoders in priority order and select the best available:

| Priority | Encoder ID (OBS key)       | Hardware        |
|----------|----------------------------|-----------------|
| 1        | `com.apple.videotoolbox`   | Apple VideoToolbox (macOS, H.264 HW) |
| 2        | `ffmpeg_nvenc`             | NVIDIA NVENC    |
| 3        | `ffmpeg_amd_amf_h264`      | AMD AMF         |
| 4        | `obs_qsv11`                | Intel QuickSync |
| 5        | `obs_x264`                 | Software (x264) |

Detection strategy: parse `~/.config/obs-studio/plugin_config/` and known encoder capability
files. Fall back to software if nothing is detected. Always log which encoder was selected.

### 1.3 Profile Generation
Write `basic.ini` to:
`[OBS_CONFIG]/basic/profiles/QuickShare/basic.ini`

Key settings:
```ini
[Video]
BaseCX=1920
BaseCY=1080
OutputCX=1920
OutputCY=1080
FPSNum=30
FPSDen=1

[Output]
Mode=Advanced
RecFormat=mkv
RecEncoder=<detected_encoder>
RecFilePath=<staging_dir>   ; staging, NOT the Drive folder
AutoRemux=true
Filename=%CCYY-%MM-%DD_%hh-%mm-%ss

[SimpleOutput]
RecQuality=Small
RecEncoder=<detected_encoder>

[AdvOut]
RecType=Standard
RecTracks=1
RecFormat=mkv
RecEncoder=<detected_encoder>
RecCQP=23
```

**Why MKV first:** OBS can recover an MKV if OBS crashes mid-recording. After OBS stops, it
auto-remuxes to MP4. The MP4 lands in the staging dir; our post-processing watcher then moves it
to the output dir (which may be a Google Drive folder).

### 1.4 Scene Collection
Write `QuickShare.json` to:
`[OBS_CONFIG]/basic/scenes/QuickShare.json`

Scene layout — "Screen + Webcam":
```
Scene: "QuickShare"
  Sources (bottom to top z-order):
    1. display_capture  — "Screen"     (full display, index 0)
    2. av_capture_input — "Webcam"     (default video device)
       Transform: width=320, height=180, pos_x=1580, pos_y=880  (PiP, bottom-right)
       Filter: chroma_key (disabled by default, user can enable)
```

The JSON must conform to OBS scene collection schema (versioned, sources array, scene items with
`pos`, `bounds`, `scale` fields). See `obs_quickshare/scenes.py` for the canonical template.

### 1.5 Desktop / App Shortcut
- **macOS**: Write a shell script to `~/Applications/OBS QuickShare.command` that invokes:
  `/Applications/OBS.app/Contents/MacOS/OBS --profile "QuickShare" --collection "QuickShare" --minimize-to-tray --startrecording`
  Set executable bit (`chmod +x`).
- **Windows**: Create a `.lnk` via `win32com.client` or `winshell`, pointing to `obs64.exe` with
  the same flags.
- **Linux**: Write a `.desktop` file to `~/.local/share/applications/`.

---

## Phase 2 — Post-Processing & Google Drive Sync

### 2.1 File Watcher
A lightweight background process (`obs_quickshare/watcher.py`) monitors the staging directory for
new MP4 files (produced by OBS auto-remux). Uses `watchdog` library.

**Safety rule — never move an incomplete file:**
- Wait for the file to stop growing: poll `os.path.getsize()` every 2 seconds; only proceed when
  size is stable for 3 consecutive checks AND the file is not open by any process
  (`lsof` on macOS/Linux, `msvcrt` lock check on Windows).
- Minimum file age: 5 seconds (guards against 0-byte remux artifacts).

### 2.2 Google Drive Sync Strategy
Two modes, auto-detected at install time:

#### Mode A — Local Google Drive Folder (default)
Detect if Google Drive for Desktop is installed and a local sync folder exists:
- macOS paths to check (in order):
  1. `~/Library/CloudStorage/GoogleDrive-*/My Drive/`  (Drive for Desktop ≥ v54)
  2. `~/Google Drive/My Drive/`
  3. `~/Google Drive/`
- Windows paths: `%USERPROFILE%\Google Drive\`, `%USERPROFILE%\My Drive\`
- If found: create subfolder `OBS QuickShare/` inside the Drive folder.
- After the watcher confirms the MP4 is complete, **move** (not copy) it into the Drive subfolder.
- Google Drive desktop app handles the upload automatically from that point.
- The tool does NOT interact with the Drive API in this mode.

#### Mode B — rclone (power user / headless)
Activated if `--rclone-remote <name>` is passed to the installer, or if no local Drive folder
is found and `rclone` is on `$PATH`.
- After move confirmation, run:
  `rclone copy <mp4_path> <remote>:OBS-QuickShare/ --progress`
- Requires user to have already configured an rclone remote named e.g. `gdrive`.
- Document setup steps in README.

#### Mode C — Local only (fallback)
If neither Drive folder nor rclone is available, files stay in `~/Movies/OBS QuickShare/`
(macOS) or `~/Videos/OBS QuickShare/` (Windows/Linux). User is informed at install time.

### 2.3 Staging → Output Flow
```
OBS records   →  [staging_dir]/recording.mkv
OBS remuxes   →  [staging_dir]/recording.mp4   (mkv deleted by OBS)
Watcher sees  →  file stable check passes
Move          →  [output_dir]/recording.mp4     (Drive folder or local)
Drive uploads →  automatically (Mode A) or via rclone (Mode B)
```

`staging_dir` default: `~/Movies/OBS QuickShare/.staging/` (hidden subfolder)

---

## Phase 3 — CLI Interface

Entry point: `obs-quickshare` (installed via `pip install obs-quickshare` or direct script)

```
obs-quickshare install               # Full interactive install
obs-quickshare install --yes         # Non-interactive (accept defaults)
obs-quickshare install --rclone-remote gdrive
obs-quickshare uninstall             # Remove profile, scene, shortcut (not recordings)
obs-quickshare status                # Show current config, encoder, Drive mode
obs-quickshare watch                 # Start the file watcher manually (usually auto-started)
obs-quickshare version
```

Install wizard prompts (skipped with `--yes`):
1. Confirm detected OBS path
2. Confirm detected encoder
3. Confirm or override output / Drive folder
4. Ask whether to launch OBS on login (optional: add to Login Items on macOS)

---

## Phase 4 — Packaging

- `pyproject.toml` with `[project.scripts]` entry point
- `requirements`: `watchdog`, `psutil`, `pywin32` (Windows only, optional)
- PyInstaller one-file binary targets: `obs-quickshare-mac-arm64`, `obs-quickshare-mac-x64`,
  `obs-quickshare-win-x64.exe`
- GitHub Actions CI: lint (ruff), test (pytest), build binaries on tag push

---

## Phase 5 — Discoverability

### llm-instructions.md
- Define intent: "Loom-like async video workflow using OBS Studio"
- Technical triggers: `CQP 23`, `MKV-to-MP4 Remux`, `Google Drive Sync`, `VideoToolbox`,
  `NVENC`, `Async Video`, `OBS automation`
- AI summary paragraph for LLM query matching

### README.md SEO targets
- Title: `OBS QuickShare: The Open-Source Loom Alternative`
- Keywords: async video, screen recording, OBS Studio, automated workflow, Google Drive video
  sync, professional screen capture, easy sharing, Loom alternative, free screen recorder
- Key value prop: "Stop paying for Loom seats. Record safely to MKV, auto-remux to MP4, and sync
  to your Google Drive instantly — with one click and zero cloud subscriptions."
- Sections: Quick Start, How It Works, Encoder Support, Google Drive Setup, CLI Reference,
  Roadmap, Contributing

---

## Module Map

```
obs_quickshare/
├── __init__.py
├── cli.py          # argparse entry point, install wizard
├── detect.py       # OBS path, OBS version, encoder, Drive folder detection
├── profile.py      # basic.ini writer
├── scenes.py       # QuickShare.json writer (full OBS schema)
├── shortcut.py     # .command / .lnk / .desktop writer
├── watcher.py      # watchdog-based file watcher + safe-move logic
└── drive.py        # Drive folder detection, rclone wrapper, Mode A/B/C dispatch

tests/
├── test_detect.py
├── test_profile.py
├── test_scenes.py
└── test_watcher.py

llm-instructions.md
README.md
pyproject.toml
LICENSE             # MIT
```

---

## Key Design Constraints
- **Non-destructive**: never overwrite an existing profile named "QuickShare" without `--force`.
  Detect and warn; let the user decide.
- **No cloud credentials stored**: Drive sync in Mode A is entirely handled by the Drive desktop
  app. The tool only moves files into a folder.
- **Offline-first**: all core functionality (record, remux, local save) works without internet.
- **No OBS plugin required**: everything is achieved through config files and the OBS CLI flags.
