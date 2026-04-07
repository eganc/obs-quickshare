"""
detect.py — Locate OBS config, detect encoder, find Google Drive folder.
"""

from __future__ import annotations

import configparser
import glob
import os
import platform
import shutil
from dataclasses import dataclass, field
from pathlib import Path

# ---------------------------------------------------------------------------
# Platform helpers
# ---------------------------------------------------------------------------

SYSTEM = platform.system()  # "Darwin", "Windows", "Linux"


def obs_config_root() -> Path:
    """Return the OBS Studio config root directory for the current platform."""
    if SYSTEM == "Darwin":
        return Path.home() / "Library" / "Application Support" / "obs-studio"
    elif SYSTEM == "Windows":
        appdata = os.environ.get("APPDATA")
        if not appdata:
            raise OSError("APPDATA environment variable not set")
        return Path(appdata) / "obs-studio"
    else:  # Linux / BSD
        xdg = os.environ.get("XDG_CONFIG_HOME")
        if xdg:
            return Path(xdg) / "obs-studio"
        return Path.home() / ".config" / "obs-studio"


def obs_version(config_root: Path) -> str | None:
    """
    Parse OBS version from global.ini.
    Returns version string like "30.1.2" or None if unreadable.
    """
    global_ini = config_root / "global.ini"
    if not global_ini.exists():
        return None
    cfg = configparser.ConfigParser()
    cfg.read(global_ini, encoding="utf-8")
    return cfg.get("General", "Version", fallback=None)


def _parse_version(v: str) -> tuple[int, ...]:
    """Convert "30.1.2" → (30, 1, 2)."""
    try:
        return tuple(int(x) for x in v.split(".")[:3])
    except ValueError:
        return (0, 0, 0)


# ---------------------------------------------------------------------------
# Encoder detection
# ---------------------------------------------------------------------------

# Priority-ordered list of (obs_encoder_id, human_label, platform_filter)
# platform_filter: None = all platforms, "Darwin" / "Windows" / "Linux" = restricted
_ENCODER_CANDIDATES: list[tuple[str, str, str | None]] = [
    # OBS 30+ uses dot-notation IDs; OBS 28–29 used underscore IDs.
    # List new first so modern installs get the right encoder written to basic.ini.
    ("com.apple.videotoolbox.videoencoder.ave.avc",  "Apple VideoToolbox (H.264 HW)", "Darwin"),
    ("com.apple.videotoolbox_encoder_h264_hw",       "Apple VideoToolbox (H.264 HW)", "Darwin"),
    ("ffmpeg_nvenc",                                  "NVIDIA NVENC (H.264)",          None),
    ("ffmpeg_hevc_nvenc",                             "NVIDIA NVENC (HEVC)",           None),
    ("ffmpeg_amd_amf_h264",                           "AMD AMF (H.264)",               None),
    ("obs_qsv11",                                     "Intel QuickSync (H.264)",       None),
    ("obs_x264",                                      "Software x264 (H.264)",         None),
]

# OBS writes encoder capability info under plugin_config on some versions,
# but the most reliable cross-platform probe is to check which encoder plugins
# are present as shared libraries alongside the OBS binary.
_OBS_BINARY_DIRS: dict[str, list[Path]] = {
    "Darwin": [
        Path("/Applications/OBS.app/Contents/MacOS"),
        Path("/Applications/OBS.app/Contents/PlugIns"),
    ],
    "Windows": [
        Path(r"C:\Program Files\obs-studio\bin\64bit"),
        Path(r"C:\Program Files\obs-studio\obs-plugins\64bit"),
    ],
    "Linux": [
        Path("/usr/lib/obs-plugins"),
        Path("/usr/local/lib/obs-plugins"),
        Path(Path.home() / ".local" / "lib" / "obs-plugins"),
    ],
}

# Map from encoder id prefix → plugin library name fragment
_ENCODER_PLUGIN_MAP: dict[str, str] = {
    "com.apple.videotoolbox": "mac-videotoolbox",
    "ffmpeg_nvenc":           "obs-ffmpeg",
    "ffmpeg_hevc_nvenc":      "obs-ffmpeg",
    "ffmpeg_amd_amf_h264":    "obs-ffmpeg",   # AMF is bundled in obs-ffmpeg on Windows
    "obs_qsv11":              "obs-qsv11",
    "obs_x264":               "obs-x264",
}


def _plugin_present(encoder_id: str) -> bool:
    """Heuristic: check whether the plugin library for this encoder exists on disk."""
    fragment = _ENCODER_PLUGIN_MAP.get(encoder_id.split("_")[0] + "_" + encoder_id.split("_")[1]
                                       if encoder_id.count("_") >= 1 else encoder_id)
    if fragment is None:
        # Try matching by first two underscore-segments
        for key, val in _ENCODER_PLUGIN_MAP.items():
            if encoder_id.startswith(key):
                fragment = val
                break
    if fragment is None:
        return False

    search_dirs = _OBS_BINARY_DIRS.get(SYSTEM, [])
    for d in search_dirs:
        if not d.exists():
            continue
        # Look for any file whose name contains the fragment
        for f in d.iterdir():
            if fragment in f.name:
                return True
    return False


@dataclass
class EncoderInfo:
    obs_id: str
    label: str
    is_hardware: bool


def detect_encoder() -> EncoderInfo:
    """
    Return the best available encoder for the current system.
    Falls back to software x264 if nothing hardware is found.
    """
    for obs_id, label, plat in _ENCODER_CANDIDATES:
        if plat and plat != SYSTEM:
            continue
        if _plugin_present(obs_id):
            return EncoderInfo(
                obs_id=obs_id,
                label=label,
                is_hardware=(obs_id != "obs_x264"),
            )

    # Ultimate fallback — x264 is always bundled
    return EncoderInfo(obs_id="obs_x264", label="Software x264 (H.264)", is_hardware=False)


# ---------------------------------------------------------------------------
# Output / staging directories
# ---------------------------------------------------------------------------

def default_output_dir() -> Path:
    """User-visible folder where finished MP4s land."""
    if SYSTEM == "Darwin":
        return Path.home() / "Movies" / "OBS QuickShare"
    elif SYSTEM == "Windows":
        return Path.home() / "Videos" / "OBS QuickShare"
    else:
        return Path.home() / "Videos" / "OBS QuickShare"


def default_staging_dir(output_dir: Path | None = None) -> Path:
    """Hidden staging folder where OBS writes MKV/MP4 before we move them."""
    base = output_dir or default_output_dir()
    return base / ".staging"


# ---------------------------------------------------------------------------
# Google Drive folder detection
# ---------------------------------------------------------------------------

@dataclass
class DriveInfo:
    mode: str           # "local", "rclone", "none"
    path: Path | None = None          # local Drive folder root
    rclone_remote: str | None = None  # rclone remote name


def _find_local_drive_folder_macos() -> Path | None:
    """
    Probe macOS for a Google Drive for Desktop sync folder.
    Returns the 'My Drive' root path or None.
    """
    # Drive for Desktop ≥ v54 mounts under CloudStorage
    cloud_storage = Path.home() / "Library" / "CloudStorage"
    if cloud_storage.exists():
        pattern = str(cloud_storage / "GoogleDrive-*" / "My Drive")
        matches = glob.glob(pattern)
        if matches:
            return Path(matches[0])

    # Older Drive for Desktop / Backup and Sync
    for candidate in [
        Path.home() / "Google Drive" / "My Drive",
        Path.home() / "Google Drive",
    ]:
        if candidate.exists():
            return candidate

    return None


def _find_local_drive_folder_windows() -> Path | None:
    """Probe Windows for a Google Drive for Desktop sync folder."""
    home = Path.home()
    for candidate in [
        home / "My Drive",
        home / "Google Drive" / "My Drive",
        home / "Google Drive",
    ]:
        if candidate.exists():
            return candidate

    # Drive for Desktop on Windows may use a custom path stored in registry,
    # but that requires winreg. Check the most common default locations only.
    return None


def _find_local_drive_folder_linux() -> Path | None:
    home = Path.home()
    for candidate in [
        home / "Google Drive",
        home / "GoogleDrive",
    ]:
        if candidate.exists():
            return candidate
    return None


def detect_drive(rclone_remote: str | None = None) -> DriveInfo:
    """
    Determine which Drive sync mode to use.

    Priority:
      1. Local Google Drive folder (Mode A) — if Drive for Desktop is installed
      2. rclone (Mode B)                    — if remote name provided and rclone on PATH
      3. Local-only fallback (Mode C)
    """
    # Mode A: local folder
    if SYSTEM == "Darwin":
        drive_path = _find_local_drive_folder_macos()
    elif SYSTEM == "Windows":
        drive_path = _find_local_drive_folder_windows()
    else:
        drive_path = _find_local_drive_folder_linux()

    if drive_path:
        return DriveInfo(mode="local", path=drive_path)

    # Mode B: rclone
    if rclone_remote and shutil.which("rclone"):
        return DriveInfo(mode="rclone", rclone_remote=rclone_remote)

    if not rclone_remote and shutil.which("rclone"):
        # rclone present but no remote specified — note it but don't use it
        pass

    return DriveInfo(mode="none")


# ---------------------------------------------------------------------------
# Full detection summary
# ---------------------------------------------------------------------------

@dataclass
class DetectionResult:
    config_root: Path
    obs_version: str | None
    version_ok: bool            # True if OBS >= 28.0
    encoder: EncoderInfo
    output_dir: Path
    staging_dir: Path
    drive: DriveInfo
    warnings: list[str] = field(default_factory=list)


def run_detection(rclone_remote: str | None = None) -> DetectionResult:
    """
    Run all detection checks and return a DetectionResult.
    Raises RuntimeError if OBS config root is missing (OBS never launched).
    """
    config_root = obs_config_root()
    warnings: list[str] = []

    if not config_root.exists():
        raise RuntimeError(
            f"OBS config directory not found at {config_root}.\n"
            "Please launch OBS Studio at least once before running obs-quickshare."
        )

    version = obs_version(config_root)
    version_ok = True
    if version:
        if _parse_version(version) < (28, 0, 0):
            version_ok = False
            warnings.append(
                f"OBS version {version} detected. Version 28.0 or newer is recommended "
                "for full hardware encoder and auto-remux support."
            )
    else:
        warnings.append("Could not determine OBS version — proceeding anyway.")

    encoder = detect_encoder()
    if not encoder.is_hardware:
        warnings.append(
            "No hardware encoder detected. Falling back to software x264. "
            "CPU usage during recording will be higher."
        )

    output_dir = default_output_dir()
    staging_dir = default_staging_dir(output_dir)
    drive = detect_drive(rclone_remote=rclone_remote)

    return DetectionResult(
        config_root=config_root,
        obs_version=version,
        version_ok=version_ok,
        encoder=encoder,
        output_dir=output_dir,
        staging_dir=staging_dir,
        drive=drive,
        warnings=warnings,
    )
