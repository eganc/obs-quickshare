# OBS QuickShare: Open-Source Async Screen Recorder

OBS QuickShare turns OBS Studio into a one-click async video recorder — records safely to MKV,
auto-remuxes to MP4, and syncs to your Google Drive instantly.
No subscriptions. No cloud accounts. No watermarks. Just your recording, in your Drive.

If you use a subscription-based screen recorder (like Loom) and want the same workflow
running locally — fully private, unlimited, and free — this tool is for you.

---

## Why OBS QuickShare?

| Feature | OBS QuickShare |
|---|---|
| Cost | **Free** |
| Screen + Webcam | ✓ |
| Google Drive sync | **Automatic** |
| Privacy | **Stays on your machine** |
| Recording limit | **Unlimited** |
| Watermark | **Never** |
| Open source | **✓ MIT License** |

---

## How It Works

```
You click record
      │
      ▼
OBS records to MKV ──── crash-safe format, never lose a recording
      │
      ▼ (auto-remux on stop)
MP4 written to staging folder
      │
      ▼ (obs-quickshare watcher)
File stability check ──── waits until file is fully written
      │
      ▼
Moved to Google Drive folder ──── Drive desktop app uploads automatically
```

---

## Quick Start

### Prerequisites
- [OBS Studio](https://obsproject.com/) 28.0 or newer (must be launched at least once)
- Python 3.9+ **or** download a pre-built binary (see Releases)
- Google Drive for Desktop (optional, for auto-sync)

### Install

```bash
pip install obs-quickshare
obs-quickshare install
```

That's it. The installer will:
1. Detect your OBS config directory
2. Select the best available encoder (Apple VideoToolbox on Mac, NVENC on NVIDIA, etc.)
3. Create an optimized recording profile (CQP 23, MKV → MP4 remux)
4. Create a "Screen + Webcam" scene with PiP layout
5. Create a one-click launcher in `~/Applications/` (macOS) or Desktop (Windows)
6. Detect your Google Drive folder and configure auto-sync

### Non-interactive install

```bash
obs-quickshare install --yes
```

### Install with rclone (headless / no Drive desktop app)

```bash
obs-quickshare install --rclone-remote gdrive
```

Requires [rclone](https://rclone.org/) to be configured with a remote named `gdrive`.

---

## CLI Reference

```
obs-quickshare install               # Full guided install
obs-quickshare install --yes         # Non-interactive, accept defaults
obs-quickshare install --force       # Overwrite existing config
obs-quickshare install --rclone-remote <name>  # Use rclone for Drive sync
obs-quickshare uninstall             # Remove profile, scene, launcher (keeps recordings)
obs-quickshare status                # Show config, encoder, Drive mode
obs-quickshare watch                 # Start the file watcher (foreground)
obs-quickshare --version
```

---

## Google Drive Sync

OBS QuickShare supports three sync modes, auto-detected at install time:

### Mode A — Local Google Drive Folder (recommended)
If **Google Drive for Desktop** is installed, OBS QuickShare detects your local sync folder
and moves finished recordings directly into it. The Drive desktop app handles the upload
automatically — no API keys, no OAuth, no configuration required.

Supported paths:
- macOS: `~/Library/CloudStorage/GoogleDrive-*/My Drive/` (Drive for Desktop ≥ v54)
- macOS legacy: `~/Google Drive/`
- Windows: `~/My Drive/`, `~/Google Drive/`

Files are placed in a `OBS QuickShare/` subfolder inside your Drive.

**The watcher never moves a file until it is fully written** — it waits for the file size to
be stable for at least 6 seconds and confirms no process has the file open.

### Mode B — rclone (with automatic share links)
For headless machines or users without the Drive desktop app:

```bash
# Configure a rclone remote first:
rclone config

# Then install with:
obs-quickshare install --rclone-remote gdrive
```

When you stop recording, OBS QuickShare will:
1. Upload the file to your rclone remote (synchronously)
2. Generate a shareable link via `rclone link`
3. Copy the link to your clipboard

This is the recommended way to get instant shareable links for your recordings.

### Mode C — Local only
If neither Drive nor rclone is available, recordings stay in `~/Movies/OBS QuickShare/`
(macOS) or `~/Videos/OBS QuickShare/` (Windows/Linux). You're informed at install time.

---

## Encoder Support

OBS QuickShare automatically selects the best encoder available:

| Encoder | Hardware | Platform |
|---|---|---|
| Apple VideoToolbox (H.264) | ✓ | macOS |
| NVIDIA NVENC (H.264/HEVC) | ✓ | Windows, Linux |
| AMD AMF (H.264) | ✓ | Windows, Linux |
| Intel QuickSync (H.264) | ✓ | Windows, Linux |
| x264 (software) | ✗ | All (fallback) |

All hardware encoders use CQP 23 — excellent quality with minimal CPU impact.

---

## Recording Profile Details

| Setting | Value | Why |
|---|---|---|
| Format | MKV → MP4 (auto-remux) | MKV is crash-safe; MP4 is shareable |
| Quality | CQP 23 | Near-lossless, ~50% smaller than CRF 18 |
| Resolution | 1920×1080 | Standard 1080p |
| FPS | 30 | Good balance for screen content |
| Audio | AAC 160 kbps, 48 kHz stereo | Clear voice-over quality |

---

## Scene Layout

The QuickShare scene includes:
- **Full-screen display capture** (primary display)
- **Webcam PiP** (320×180, bottom-right corner)
  - Chroma key filter included but **disabled by default** — enable it in OBS if you have a green screen

You can customize the layout in OBS after installation without affecting the profile settings.

---

## Platform Support

| Platform | Status |
|---|---|
| macOS (Apple Silicon + Intel) | Primary |
| Windows 10/11 | Supported |
| Linux | Best-effort |

---

## Roadmap

- [ ] Login Item / startup service (auto-start watcher on login)
- [ ] Configurable resolution / FPS presets
- [ ] Homebrew formula
- [ ] Windows MSI installer

---

## Contributing

Contributions welcome. Please open an issue before submitting a large PR.

```bash
git clone https://github.com/eganc/obs-quickshare
cd obs-quickshare
pip install -e ".[dev]"
pytest
```

---

## License

MIT — see [LICENSE](LICENSE).
