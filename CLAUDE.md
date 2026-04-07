# CLAUDE.md — OBS QuickShare

This file is loaded automatically by Claude Code. It provides full context for any new session.

## What This Project Is

`obs-quickshare` is a Python CLI tool that configures OBS Studio for a one-click async screen
recording workflow — a free, open-source async screen recorder. It installs an OBS profile, scene
collection, and launcher shortcut, then runs a file watcher that moves finished recordings to
Google Drive automatically.

**Canonical spec:** `SPEC.md` — read it before making architectural changes.

## Platform Priority

macOS first, then Windows, then Linux (best-effort). All platform branches are gated on
`platform.system()` checks; do not remove Windows/Linux branches even if testing on Mac.

## Module Responsibilities

| File | Responsibility |
|---|---|
| `obs_quickshare/detect.py` | OBS config root, version parse, encoder detection, Drive folder probe |
| `obs_quickshare/profile.py` | Write `basic.ini` (OBS profile settings) |
| `obs_quickshare/scenes.py` | Write `QuickShare.json` (OBS scene collection) |
| `obs_quickshare/shortcut.py` | Write `.command` / `.lnk` / `.desktop` launcher |
| `obs_quickshare/watcher.py` | watchdog file watcher + safe-move logic |
| `obs_quickshare/drive.py` | Mode A/B/C Drive sync dispatch |
| `obs_quickshare/cli.py` | argparse entry point, `install` / `uninstall` / `status` / `watch` |

## Key Design Rules (do not violate)

1. **Non-destructive**: `write_profile()` and `write_scene_collection()` raise `FileExistsError`
   if the target already exists and `force=False`. The CLI skips with a warning rather than
   aborting — let the user decide.

2. **Safe file move**: `watcher.py:_wait_until_stable()` must return `True` before any file is
   moved. It polls every 2 s, requires 3 consecutive stable-size checks AND confirms the file
   is not open by any process (`psutil`). Never bypass this check.

3. **No Drive API / credentials**: Mode A (local folder) relies on the Drive desktop app. The
   tool only moves files into the local sync folder. Never add OAuth or API key flows unless
   explicitly requested.

4. **No OBS plugins**: Everything is achieved through config files + OBS CLI flags. Do not add
   OBS WebSocket or plugin dependencies.

5. **Optional dependencies are truly optional**: `watchdog`, `psutil`, and `pywin32` are all
   guarded with try/except. The tool must be importable and partially functional without them.

## Google Drive Sync Modes

- **Mode A** (default): local Google Drive folder detected via `detect.py:_find_local_drive_folder_*()`.
  macOS primary path: `~/Library/CloudStorage/GoogleDrive-*/My Drive/`
- **Mode B**: rclone, activated when `--rclone-remote <name>` passed or rclone on PATH.
  Uses `drive.py:_rclone_upload()` — fire-and-forget subprocess.
- **Mode C**: local only, `~/Movies/OBS QuickShare/` (macOS) or `~/Videos/OBS QuickShare/`.

## OBS Config Paths

- macOS: `~/Library/Application Support/obs-studio/`
- Windows: `%APPDATA%\obs-studio\`
- Linux: `~/.config/obs-studio/` (XDG_CONFIG_HOME aware)

Profile path: `[config_root]/basic/profiles/QuickShare/basic.ini`
Scenes path:  `[config_root]/basic/scenes/QuickShare.json`

## Encoder Priority

1. `com.apple.videotoolbox_encoder_h264_hw` (macOS only)
2. `ffmpeg_nvenc` (NVIDIA)
3. `ffmpeg_hevc_nvenc` (NVIDIA HEVC)
4. `ffmpeg_amd_amf_h264` (AMD)
5. `obs_qsv11` (Intel)
6. `obs_x264` (software fallback)

Detection is plugin-file-presence based (see `detect.py:_plugin_present()`). If detection gives
wrong results on a user's system, the fix is in `_OBS_BINARY_DIRS` and `_ENCODER_PLUGIN_MAP`.

## Staging → Output Flow

```
OBS records  →  [staging_dir]/*.mkv
OBS remuxes  →  [staging_dir]/*.mp4  (MKV deleted by OBS)
watcher sees →  _wait_until_stable() passes
move         →  [output_dir]/*.mp4   (Drive folder or local)
Drive syncs  →  automatically (Mode A) or rclone (Mode B)
```

`staging_dir` = `[output_dir]/.staging/`
`output_dir`  = `~/Movies/OBS QuickShare/` (macOS default)

## CLI Commands

```
obs-quickshare install [--yes] [--force] [--rclone-remote NAME]
obs-quickshare uninstall [--yes]
obs-quickshare status
obs-quickshare watch [--rclone-remote NAME]
obs-quickshare --version
```

## Development Setup

```bash
pip install -e ".[dev]"
pytest
ruff check obs_quickshare/
```

## What's Not Implemented Yet (Roadmap)

- Login Item / startup service (auto-start watcher on login)
- Configurable resolution / FPS presets (currently hardcoded to 1080p30)
- Post-upload clipboard link (Drive API, opt-in)
- Homebrew formula
- Windows MSI / PyInstaller binary builds
- GitHub Actions CI pipeline
- Tests in `tests/` (stubs created, not yet written)
