"""
profile.py — Generate OBS basic.ini for the QuickShare profile.
"""

from __future__ import annotations

import configparser
from pathlib import Path

from .detect import DetectionResult

PROFILE_NAME = "QuickShare"


def profile_dir(config_root: Path, profile_name: str = PROFILE_NAME) -> Path:
    return config_root / "basic" / "profiles" / profile_name


def profile_exists(config_root: Path, profile_name: str = PROFILE_NAME) -> bool:
    return (profile_dir(config_root, profile_name) / "basic.ini").exists()


def build_basic_ini(result: DetectionResult) -> configparser.RawConfigParser:
    """
    Build a RawConfigParser representing the QuickShare basic.ini.
    All values are strings as OBS expects them.
    """
    cfg = configparser.RawConfigParser()
    cfg.optionxform = str  # preserve key case (OBS is case-sensitive)

    # -----------------------------------------------------------------------
    # [General]
    # -----------------------------------------------------------------------
    cfg.add_section("General")
    cfg.set("General", "Name", PROFILE_NAME)

    # -----------------------------------------------------------------------
    # [Video]
    # -----------------------------------------------------------------------
    cfg.add_section("Video")
    cfg.set("Video", "BaseCX",  "1920")
    cfg.set("Video", "BaseCY",  "1080")
    cfg.set("Video", "OutputCX", "1920")
    cfg.set("Video", "OutputCY", "1080")
    cfg.set("Video", "FPSType",  "0")   # 0 = common FPS values
    cfg.set("Video", "FPSCommon", "30")
    cfg.set("Video", "FPSNum",   "30")
    cfg.set("Video", "FPSDen",   "1")
    cfg.set("Video", "ScaleType", "2")  # 2 = Lanczos

    # -----------------------------------------------------------------------
    # [Audio]
    # -----------------------------------------------------------------------
    cfg.add_section("Audio")
    cfg.set("Audio", "SampleRate", "48000")
    cfg.set("Audio", "ChannelSetup", "Stereo")

    # -----------------------------------------------------------------------
    # [Output]  — top-level mode selector
    # -----------------------------------------------------------------------
    cfg.add_section("Output")
    cfg.set("Output", "Mode", "Advanced")

    # -----------------------------------------------------------------------
    # [AdvOut]  — Advanced output settings
    # -----------------------------------------------------------------------
    cfg.add_section("AdvOut")
    cfg.set("AdvOut", "RecType",    "Standard")
    cfg.set("AdvOut", "RecTracks",  "1")
    # fragmented_mp4: crash-safe container that is already MP4 — no remux step
    # needed.  OBS writes the file incrementally (one fragment per GOP) so a
    # partial recording is always a valid MP4.  RecFormat is the OBS 28/29 key;
    # RecFormat2 is the OBS 30+ authoritative key.  We set both for compat.
    # Using "mp4" as the OBS 28/29 fallback (not crash-safe but functional).
    cfg.set("AdvOut", "RecFormat",  "mp4")
    cfg.set("AdvOut", "RecFormat2", "fragmented_mp4")
    cfg.set("AdvOut", "RecEncoder", result.encoder.obs_id)
    cfg.set("AdvOut", "RecFilePath", str(result.staging_dir))
    cfg.set("AdvOut", "RecFileNameWithoutSpace", "true")

    # CQP 23: good quality / size balance (lower = better quality, larger file)
    cfg.set("AdvOut", "RecCQP",     "23")
    cfg.set("AdvOut", "RecPreset",  "veryfast")   # ignored by HW encoders, used by x264

    # Audio tracks
    cfg.set("AdvOut", "RecAudioEncoder", "ffmpeg_aac")
    cfg.set("AdvOut", "RecAudioBitrate", "160")

    # Filename template: YYYY-MM-DD_HH-MM-SS
    cfg.set("AdvOut", "RecFilename", "%CCYY-%MM-%DD_%hh-%mm-%ss")

    # Streaming encoder (set reasonable defaults even if user isn't streaming)
    cfg.set("AdvOut", "Encoder",    result.encoder.obs_id)
    cfg.set("AdvOut", "ApplyServiceSettings", "true")

    # -----------------------------------------------------------------------
    # [SimpleOutput]  — kept minimal; user may switch to Simple mode
    # -----------------------------------------------------------------------
    cfg.add_section("SimpleOutput")
    cfg.set("SimpleOutput", "RecQuality",  "Small")
    cfg.set("SimpleOutput", "RecEncoder",  result.encoder.obs_id)
    cfg.set("SimpleOutput", "RecFormat",   "mp4")
    cfg.set("SimpleOutput", "RecFormat2",  "fragmented_mp4")
    cfg.set("SimpleOutput", "FilePath",    str(result.staging_dir))
    cfg.set("SimpleOutput", "RecRB",       "false")  # no replay buffer

    return cfg


def write_profile(result: DetectionResult, force: bool = False) -> Path:
    """
    Write basic.ini to the QuickShare profile directory.

    Args:
        result: DetectionResult from detect.run_detection()
        force:  If True, overwrite an existing profile. If False and profile
                exists, raises FileExistsError.

    Returns:
        Path to the written basic.ini file.
    """
    pdir = profile_dir(result.config_root)

    if pdir.exists() and not force:
        ini_path = pdir / "basic.ini"
        if ini_path.exists():
            raise FileExistsError(
                f"QuickShare profile already exists at {ini_path}.\n"
                "Run with --force to overwrite."
            )

    pdir.mkdir(parents=True, exist_ok=True)

    # Ensure staging dir exists
    result.staging_dir.mkdir(parents=True, exist_ok=True)

    cfg = build_basic_ini(result)
    ini_path = pdir / "basic.ini"

    with open(ini_path, "w", encoding="utf-8") as f:
        cfg.write(f, space_around_delimiters=False)

    return ini_path
