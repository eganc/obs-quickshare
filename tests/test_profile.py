"""
Tests for obs_quickshare.profile
"""
from __future__ import annotations

import configparser
from pathlib import Path
from unittest.mock import patch

import pytest

from obs_quickshare.detect import DetectionResult, DriveInfo, EncoderInfo
from obs_quickshare.profile import (
    PROFILE_NAME,
    build_basic_ini,
    profile_dir,
    profile_exists,
    write_profile,
)


def _make_detection_result(tmp_path: Path) -> DetectionResult:
    staging = tmp_path / "staging"
    output = tmp_path / "output"
    return DetectionResult(
        config_root=tmp_path / "obs-studio",
        obs_version="30.1.0",
        version_ok=True,
        encoder=EncoderInfo(
            obs_id="com.apple.videotoolbox_encoder_h264_hw",
            label="Apple VideoToolbox (H.264 HW)",
            is_hardware=True,
        ),
        output_dir=output,
        staging_dir=staging,
        drive=DriveInfo(mode="none"),
        warnings=[],
    )


# ---------------------------------------------------------------------------
# profile_dir / profile_exists
# ---------------------------------------------------------------------------

class TestProfileDir:
    def test_path_structure(self, tmp_path):
        result = profile_dir(tmp_path)
        assert result == tmp_path / "basic" / "profiles" / PROFILE_NAME

    def test_custom_profile_name(self, tmp_path):
        result = profile_dir(tmp_path, profile_name="MyProfile")
        assert result == tmp_path / "basic" / "profiles" / "MyProfile"


class TestProfileExists:
    def test_returns_false_when_missing(self, tmp_path):
        assert profile_exists(tmp_path) is False

    def test_returns_true_when_present(self, tmp_path):
        ini = tmp_path / "basic" / "profiles" / PROFILE_NAME / "basic.ini"
        ini.parent.mkdir(parents=True)
        ini.write_text("[General]\nName=QuickShare\n")
        assert profile_exists(tmp_path) is True


# ---------------------------------------------------------------------------
# build_basic_ini
# ---------------------------------------------------------------------------

class TestBuildBasicIni:
    def setup_method(self):
        # Use a temp path without touching disk
        self.result = DetectionResult(
            config_root=Path("/fake/obs-studio"),
            obs_version="30.1.0",
            version_ok=True,
            encoder=EncoderInfo(
                obs_id="obs_x264",
                label="Software x264 (H.264)",
                is_hardware=False,
            ),
            output_dir=Path("/fake/output"),
            staging_dir=Path("/fake/output/.staging"),
            drive=DriveInfo(mode="none"),
            warnings=[],
        )

    def test_has_required_sections(self):
        cfg = build_basic_ini(self.result)
        for section in ("General", "Video", "Audio", "Output", "AdvOut", "SimpleOutput"):
            assert cfg.has_section(section), f"Missing section: {section}"

    def test_general_name(self):
        cfg = build_basic_ini(self.result)
        assert cfg.get("General", "Name") == PROFILE_NAME

    def test_video_1080p30(self):
        cfg = build_basic_ini(self.result)
        assert cfg.get("Video", "BaseCX") == "1920"
        assert cfg.get("Video", "BaseCY") == "1080"
        assert cfg.get("Video", "FPSCommon") == "30"

    def test_audio_48khz_stereo(self):
        cfg = build_basic_ini(self.result)
        assert cfg.get("Audio", "SampleRate") == "48000"
        assert cfg.get("Audio", "ChannelSetup") == "Stereo"

    def test_output_advanced_mode(self):
        cfg = build_basic_ini(self.result)
        assert cfg.get("Output", "Mode") == "Advanced"

    def test_rec_encoder_uses_detected_encoder(self):
        cfg = build_basic_ini(self.result)
        assert cfg.get("AdvOut", "RecEncoder") == "obs_x264"

    def test_hardware_encoder_propagated(self):
        hw_result = DetectionResult(
            config_root=Path("/fake/obs-studio"),
            obs_version="30.1.0",
            version_ok=True,
            encoder=EncoderInfo(
                obs_id="ffmpeg_nvenc",
                label="NVIDIA NVENC (H.264)",
                is_hardware=True,
            ),
            output_dir=Path("/fake/output"),
            staging_dir=Path("/fake/output/.staging"),
            drive=DriveInfo(mode="none"),
            warnings=[],
        )
        cfg = build_basic_ini(hw_result)
        assert cfg.get("AdvOut", "RecEncoder") == "ffmpeg_nvenc"

    def test_staging_dir_in_config(self):
        cfg = build_basic_ini(self.result)
        assert cfg.get("AdvOut", "RecFilePath") == str(self.result.staging_dir)

    def test_auto_remux_enabled(self):
        cfg = build_basic_ini(self.result)
        assert cfg.get("AdvOut", "RemuxAfterRecord") == "true"

    def test_mkv_format(self):
        cfg = build_basic_ini(self.result)
        assert cfg.get("AdvOut", "RecFormat") == "mkv"

    def test_preserves_key_case(self):
        """OBS is case-sensitive; keys must NOT be lowercased."""
        cfg = build_basic_ini(self.result)
        # configparser normalises keys to lowercase by default;
        # build_basic_ini overrides this with optionxform = str
        assert cfg.has_option("Video", "BaseCX")
        assert cfg.has_option("Video", "BaseCY")


# ---------------------------------------------------------------------------
# write_profile
# ---------------------------------------------------------------------------

class TestWriteProfile:
    def test_creates_file(self, tmp_path):
        result = _make_detection_result(tmp_path)
        result.config_root.mkdir(parents=True)
        ini_path = write_profile(result)
        assert ini_path.exists()
        assert ini_path.name == "basic.ini"

    def test_profile_dir_created(self, tmp_path):
        result = _make_detection_result(tmp_path)
        result.config_root.mkdir(parents=True)
        write_profile(result)
        assert profile_dir(result.config_root).exists()

    def test_staging_dir_created(self, tmp_path):
        result = _make_detection_result(tmp_path)
        result.config_root.mkdir(parents=True)
        write_profile(result)
        assert result.staging_dir.exists()

    def test_raises_file_exists_error_without_force(self, tmp_path):
        result = _make_detection_result(tmp_path)
        result.config_root.mkdir(parents=True)
        write_profile(result)  # first write
        with pytest.raises(FileExistsError):
            write_profile(result)  # second write — no force

    def test_force_overwrites_existing(self, tmp_path):
        result = _make_detection_result(tmp_path)
        result.config_root.mkdir(parents=True)
        first = write_profile(result)
        first.write_text("[General]\nName=OLD\n")  # corrupt it
        write_profile(result, force=True)
        cfg = configparser.ConfigParser()
        cfg.read(first)
        assert cfg.get("General", "Name") == PROFILE_NAME

    def test_file_is_valid_ini(self, tmp_path):
        result = _make_detection_result(tmp_path)
        result.config_root.mkdir(parents=True)
        ini_path = write_profile(result)
        cfg = configparser.ConfigParser()
        cfg.read(ini_path)
        assert cfg.has_section("General")
        assert cfg.has_section("Video")
        assert cfg.has_section("AdvOut")
