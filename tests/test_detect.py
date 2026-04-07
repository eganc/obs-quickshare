"""
Tests for obs_quickshare.detect
"""
from __future__ import annotations

import configparser
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from obs_quickshare.detect import (
    DriveInfo,
    EncoderInfo,
    _find_local_drive_folder_linux,
    _find_local_drive_folder_macos,
    _find_local_drive_folder_windows,
    _parse_version,
    _plugin_present,
    default_output_dir,
    default_staging_dir,
    detect_drive,
    detect_encoder,
    obs_config_root,
    obs_version,
    run_detection,
)


# ---------------------------------------------------------------------------
# obs_config_root
# ---------------------------------------------------------------------------

class TestObsConfigRoot:
    def test_darwin(self):
        with patch("obs_quickshare.detect.SYSTEM", "Darwin"):
            path = obs_config_root()
        assert path == Path.home() / "Library" / "Application Support" / "obs-studio"

    def test_windows(self, monkeypatch):
        monkeypatch.setenv("APPDATA", r"C:\Users\user\AppData\Roaming")
        with patch("obs_quickshare.detect.SYSTEM", "Windows"):
            path = obs_config_root()
        assert path == Path(r"C:\Users\user\AppData\Roaming") / "obs-studio"

    def test_windows_missing_appdata(self, monkeypatch):
        monkeypatch.delenv("APPDATA", raising=False)
        with patch("obs_quickshare.detect.SYSTEM", "Windows"):
            with pytest.raises(EnvironmentError):
                obs_config_root()

    def test_linux_default(self, monkeypatch):
        monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
        with patch("obs_quickshare.detect.SYSTEM", "Linux"):
            path = obs_config_root()
        assert path == Path.home() / ".config" / "obs-studio"

    def test_linux_xdg(self, monkeypatch):
        monkeypatch.setenv("XDG_CONFIG_HOME", "/custom/config")
        with patch("obs_quickshare.detect.SYSTEM", "Linux"):
            path = obs_config_root()
        assert path == Path("/custom/config") / "obs-studio"


# ---------------------------------------------------------------------------
# obs_version / _parse_version
# ---------------------------------------------------------------------------

class TestParseVersion:
    def test_typical(self):
        assert _parse_version("30.1.2") == (30, 1, 2)

    def test_two_parts(self):
        assert _parse_version("30.1") == (30, 1)

    def test_invalid(self):
        assert _parse_version("bad") == (0, 0, 0)

    def test_extra_parts_truncated(self):
        # Only first 3 parts matter
        result = _parse_version("30.1.2.9")
        assert result == (30, 1, 2)


class TestObsVersion:
    def test_reads_version(self, tmp_path):
        global_ini = tmp_path / "global.ini"
        cfg = configparser.ConfigParser()
        cfg["General"] = {"Version": "30.2.0"}
        with open(global_ini, "w") as f:
            cfg.write(f)
        assert obs_version(tmp_path) == "30.2.0"

    def test_missing_file(self, tmp_path):
        assert obs_version(tmp_path) is None

    def test_missing_key(self, tmp_path):
        global_ini = tmp_path / "global.ini"
        global_ini.write_text("[General]\n")
        assert obs_version(tmp_path) is None


# ---------------------------------------------------------------------------
# detect_encoder / _plugin_present
# ---------------------------------------------------------------------------

class TestDetectEncoder:
    def test_returns_encoder_info(self):
        result = detect_encoder()
        assert isinstance(result, EncoderInfo)
        assert result.obs_id
        assert result.label

    def test_fallback_to_x264_when_no_plugins(self):
        with patch("obs_quickshare.detect._plugin_present", return_value=False):
            encoder = detect_encoder()
        assert encoder.obs_id == "obs_x264"
        assert encoder.is_hardware is False

    def test_apple_videotoolbox_darwin(self):
        def fake_plugin(enc_id):
            return enc_id == "com.apple.videotoolbox_encoder_h264_hw"

        with patch("obs_quickshare.detect.SYSTEM", "Darwin"), \
             patch("obs_quickshare.detect._plugin_present", side_effect=fake_plugin):
            encoder = detect_encoder()
        assert encoder.obs_id == "com.apple.videotoolbox_encoder_h264_hw"
        assert encoder.is_hardware is True

    def test_nvidia_nvenc_wins_over_software(self):
        def fake_plugin(enc_id):
            return enc_id == "ffmpeg_nvenc"

        with patch("obs_quickshare.detect.SYSTEM", "Linux"), \
             patch("obs_quickshare.detect._plugin_present", side_effect=fake_plugin):
            encoder = detect_encoder()
        assert encoder.obs_id == "ffmpeg_nvenc"
        assert encoder.is_hardware is True

    def test_apple_videotoolbox_skipped_on_non_darwin(self):
        """Apple HW encoder must not be selected on Windows/Linux."""
        def fake_plugin(enc_id):
            return True  # all plugins "present"

        with patch("obs_quickshare.detect.SYSTEM", "Linux"), \
             patch("obs_quickshare.detect._plugin_present", side_effect=fake_plugin):
            encoder = detect_encoder()
        assert encoder.obs_id != "com.apple.videotoolbox_encoder_h264_hw"


class TestPluginPresent:
    def test_no_matching_dir(self):
        with patch("obs_quickshare.detect._OBS_BINARY_DIRS", {"Darwin": []}), \
             patch("obs_quickshare.detect.SYSTEM", "Darwin"):
            assert _plugin_present("obs_x264") is False

    def test_finds_plugin_by_filename_fragment(self, tmp_path):
        plugin_file = tmp_path / "obs-x264.so"
        plugin_file.touch()
        with patch("obs_quickshare.detect._OBS_BINARY_DIRS", {"Linux": [tmp_path]}), \
             patch("obs_quickshare.detect.SYSTEM", "Linux"):
            assert _plugin_present("obs_x264") is True

    def test_missing_plugin_file(self, tmp_path):
        # dir exists but plugin file is absent
        with patch("obs_quickshare.detect._OBS_BINARY_DIRS", {"Linux": [tmp_path]}), \
             patch("obs_quickshare.detect.SYSTEM", "Linux"):
            assert _plugin_present("obs_x264") is False


# ---------------------------------------------------------------------------
# default_output_dir / default_staging_dir
# ---------------------------------------------------------------------------

class TestDefaultDirs:
    def test_darwin_output(self):
        with patch("obs_quickshare.detect.SYSTEM", "Darwin"):
            d = default_output_dir()
        assert d == Path.home() / "Movies" / "OBS QuickShare"

    def test_windows_output(self):
        with patch("obs_quickshare.detect.SYSTEM", "Windows"):
            d = default_output_dir()
        assert d == Path.home() / "Videos" / "OBS QuickShare"

    def test_linux_output(self):
        with patch("obs_quickshare.detect.SYSTEM", "Linux"):
            d = default_output_dir()
        assert d == Path.home() / "Videos" / "OBS QuickShare"

    def test_staging_dir_is_dotted_subdir(self):
        out = Path("/tmp/obs-out")
        staging = default_staging_dir(out)
        assert staging == out / ".staging"

    def test_staging_dir_uses_default_output(self):
        with patch("obs_quickshare.detect.SYSTEM", "Darwin"):
            staging = default_staging_dir()
        assert staging.name == ".staging"
        assert staging.parent == Path.home() / "Movies" / "OBS QuickShare"


# ---------------------------------------------------------------------------
# Drive detection
# ---------------------------------------------------------------------------

class TestFindLocalDriveFolderMacos:
    def test_finds_cloud_storage(self, tmp_path):
        drive_dir = tmp_path / "GoogleDrive-user@example.com" / "My Drive"
        drive_dir.mkdir(parents=True)
        with patch("obs_quickshare.detect.Path.home", return_value=tmp_path / "fake_home"), \
             patch("obs_quickshare.detect.glob.glob") as mock_glob:
            mock_glob.return_value = [str(drive_dir)]
            # Patch cloud_storage.exists() to return True
            with patch("pathlib.Path.exists", return_value=True):
                result = _find_local_drive_folder_macos()
            assert result == drive_dir

    def test_returns_none_when_not_found(self, tmp_path):
        with patch("pathlib.Path.exists", return_value=False), \
             patch("obs_quickshare.detect.glob.glob", return_value=[]):
            result = _find_local_drive_folder_macos()
        assert result is None


class TestFindLocalDriveFolderWindows:
    def test_returns_none_when_not_found(self, tmp_path):
        with patch("pathlib.Path.exists", return_value=False):
            result = _find_local_drive_folder_windows()
        assert result is None

    def test_finds_my_drive(self, tmp_path):
        drive_dir = tmp_path / "My Drive"
        drive_dir.mkdir(parents=True)
        with patch("obs_quickshare.detect.Path.home", return_value=tmp_path):
            result = _find_local_drive_folder_windows()
        assert result == drive_dir


class TestFindLocalDriveFolderLinux:
    def test_returns_none_when_not_found(self, tmp_path):
        with patch("obs_quickshare.detect.Path.home", return_value=tmp_path):
            result = _find_local_drive_folder_linux()
        assert result is None

    def test_finds_google_drive_dir(self, tmp_path):
        drive_dir = tmp_path / "Google Drive"
        drive_dir.mkdir()
        with patch("obs_quickshare.detect.Path.home", return_value=tmp_path):
            result = _find_local_drive_folder_linux()
        assert result == drive_dir


class TestDetectDrive:
    def test_mode_a_local_found(self):
        fake_path = Path("/Users/test/Library/CloudStorage/GoogleDrive-x/My Drive")
        with patch("obs_quickshare.detect.SYSTEM", "Darwin"), \
             patch("obs_quickshare.detect._find_local_drive_folder_macos",
                   return_value=fake_path):
            info = detect_drive()
        assert info.mode == "local"
        assert info.path == fake_path

    def test_mode_b_rclone(self):
        with patch("obs_quickshare.detect.SYSTEM", "Darwin"), \
             patch("obs_quickshare.detect._find_local_drive_folder_macos",
                   return_value=None), \
             patch("obs_quickshare.detect.shutil.which", return_value="/usr/local/bin/rclone"):
            info = detect_drive(rclone_remote="gdrive")
        assert info.mode == "rclone"
        assert info.rclone_remote == "gdrive"

    def test_mode_c_no_drive_no_rclone(self):
        with patch("obs_quickshare.detect.SYSTEM", "Darwin"), \
             patch("obs_quickshare.detect._find_local_drive_folder_macos",
                   return_value=None), \
             patch("obs_quickshare.detect.shutil.which", return_value=None):
            info = detect_drive()
        assert info.mode == "none"

    def test_rclone_ignored_if_no_executable(self):
        with patch("obs_quickshare.detect.SYSTEM", "Darwin"), \
             patch("obs_quickshare.detect._find_local_drive_folder_macos",
                   return_value=None), \
             patch("obs_quickshare.detect.shutil.which", return_value=None):
            info = detect_drive(rclone_remote="gdrive")
        assert info.mode == "none"


# ---------------------------------------------------------------------------
# run_detection
# ---------------------------------------------------------------------------

class TestRunDetection:
    def test_raises_if_obs_missing(self, tmp_path):
        with patch("obs_quickshare.detect.obs_config_root", return_value=tmp_path / "nonexistent"):
            with pytest.raises(RuntimeError, match="OBS config directory not found"):
                run_detection()

    def test_returns_detection_result(self, tmp_path):
        # Create minimal OBS config dir
        obs_root = tmp_path / "obs-studio"
        obs_root.mkdir()

        with patch("obs_quickshare.detect.obs_config_root", return_value=obs_root), \
             patch("obs_quickshare.detect.obs_version", return_value="30.1.0"), \
             patch("obs_quickshare.detect._plugin_present", return_value=False), \
             patch("obs_quickshare.detect._find_local_drive_folder_macos", return_value=None), \
             patch("obs_quickshare.detect.shutil.which", return_value=None), \
             patch("obs_quickshare.detect.SYSTEM", "Darwin"):
            result = run_detection()

        assert result.config_root == obs_root
        assert result.obs_version == "30.1.0"
        assert result.version_ok is True
        assert result.encoder.obs_id == "obs_x264"

    def test_warns_on_old_version(self, tmp_path):
        obs_root = tmp_path / "obs-studio"
        obs_root.mkdir()

        with patch("obs_quickshare.detect.obs_config_root", return_value=obs_root), \
             patch("obs_quickshare.detect.obs_version", return_value="27.2.4"), \
             patch("obs_quickshare.detect._plugin_present", return_value=False), \
             patch("obs_quickshare.detect._find_local_drive_folder_macos", return_value=None), \
             patch("obs_quickshare.detect.shutil.which", return_value=None), \
             patch("obs_quickshare.detect.SYSTEM", "Darwin"):
            result = run_detection()

        assert result.version_ok is False
        assert any("28.0" in w for w in result.warnings)

    def test_warns_when_version_unknown(self, tmp_path):
        obs_root = tmp_path / "obs-studio"
        obs_root.mkdir()

        with patch("obs_quickshare.detect.obs_config_root", return_value=obs_root), \
             patch("obs_quickshare.detect.obs_version", return_value=None), \
             patch("obs_quickshare.detect._plugin_present", return_value=False), \
             patch("obs_quickshare.detect._find_local_drive_folder_macos", return_value=None), \
             patch("obs_quickshare.detect.shutil.which", return_value=None), \
             patch("obs_quickshare.detect.SYSTEM", "Darwin"):
            result = run_detection()

        assert any("OBS version" in w for w in result.warnings)

    def test_warns_on_software_encoder(self, tmp_path):
        obs_root = tmp_path / "obs-studio"
        obs_root.mkdir()

        with patch("obs_quickshare.detect.obs_config_root", return_value=obs_root), \
             patch("obs_quickshare.detect.obs_version", return_value="30.0.0"), \
             patch("obs_quickshare.detect._plugin_present", return_value=False), \
             patch("obs_quickshare.detect._find_local_drive_folder_macos", return_value=None), \
             patch("obs_quickshare.detect.shutil.which", return_value=None), \
             patch("obs_quickshare.detect.SYSTEM", "Darwin"):
            result = run_detection()

        assert any("x264" in w for w in result.warnings)
