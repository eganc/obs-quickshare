"""
Tests for obs_quickshare.cli
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from obs_quickshare.cli import (
    _confirm,
    build_parser,
    cmd_install,
    cmd_status,
    cmd_uninstall,
)
from obs_quickshare.detect import DetectionResult, DriveInfo, EncoderInfo


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fake_detection(tmp_path: Path) -> DetectionResult:
    obs_root = tmp_path / "obs-studio"
    obs_root.mkdir(parents=True)
    return DetectionResult(
        config_root=obs_root,
        obs_version="30.1.0",
        version_ok=True,
        encoder=EncoderInfo(
            obs_id="obs_x264",
            label="Software x264 (H.264)",
            is_hardware=False,
        ),
        output_dir=tmp_path / "output",
        staging_dir=tmp_path / "output" / ".staging",
        drive=DriveInfo(mode="none"),
        warnings=[],
    )


def _make_install_args(yes=True, force=False, rclone_remote=None):
    args = MagicMock()
    args.yes = yes
    args.force = force
    args.rclone_remote = rclone_remote
    return args


# ---------------------------------------------------------------------------
# build_parser
# ---------------------------------------------------------------------------

class TestBuildParser:
    def test_has_install_command(self):
        parser = build_parser()
        args = parser.parse_args(["install"])
        assert args.command == "install"

    def test_has_uninstall_command(self):
        parser = build_parser()
        args = parser.parse_args(["uninstall"])
        assert args.command == "uninstall"

    def test_has_status_command(self):
        parser = build_parser()
        args = parser.parse_args(["status"])
        assert args.command == "status"

    def test_has_watch_command(self):
        parser = build_parser()
        args = parser.parse_args(["watch"])
        assert args.command == "watch"

    def test_install_yes_flag(self):
        parser = build_parser()
        args = parser.parse_args(["install", "--yes"])
        assert args.yes is True

    def test_install_force_flag(self):
        parser = build_parser()
        args = parser.parse_args(["install", "--force"])
        assert args.force is True

    def test_install_rclone_remote(self):
        parser = build_parser()
        args = parser.parse_args(["install", "--rclone-remote", "gdrive"])
        assert args.rclone_remote == "gdrive"

    def test_no_command_sets_none(self):
        parser = build_parser()
        args = parser.parse_args([])
        assert args.command is None

    def test_version_flag(self, capsys):
        parser = build_parser()
        with pytest.raises(SystemExit) as exc_info:
            parser.parse_args(["--version"])
        assert exc_info.value.code == 0


# ---------------------------------------------------------------------------
# _confirm
# ---------------------------------------------------------------------------

class TestConfirm:
    def test_default_yes_on_empty_input(self):
        with patch("builtins.input", return_value=""):
            assert _confirm("Continue?", default=True) is True

    def test_default_no_on_empty_input(self):
        with patch("builtins.input", return_value=""):
            assert _confirm("Continue?", default=False) is False

    def test_y_returns_true(self):
        with patch("builtins.input", return_value="y"):
            assert _confirm("Continue?") is True

    def test_n_returns_false(self):
        with patch("builtins.input", return_value="n"):
            assert _confirm("Continue?") is False

    def test_yes_full_word(self):
        with patch("builtins.input", return_value="yes"):
            assert _confirm("Continue?") is True

    def test_keyboard_interrupt_returns_false(self):
        with patch("builtins.input", side_effect=KeyboardInterrupt):
            assert _confirm("Continue?") is False

    def test_eof_returns_false(self):
        with patch("builtins.input", side_effect=EOFError):
            assert _confirm("Continue?") is False


# ---------------------------------------------------------------------------
# cmd_install
# ---------------------------------------------------------------------------

class TestCmdInstall:
    def test_returns_1_when_obs_missing(self):
        args = _make_install_args()
        with patch("obs_quickshare.cli.run_detection",
                   side_effect=RuntimeError("OBS not found")):
            result = cmd_install(args)
        assert result == 1

    def test_returns_0_on_success(self, tmp_path):
        result_obj = _fake_detection(tmp_path)
        args = _make_install_args()

        with patch("obs_quickshare.cli.run_detection", return_value=result_obj), \
             patch("obs_quickshare.cli.profile_exists", return_value=False), \
             patch("obs_quickshare.cli.write_profile", return_value=tmp_path / "basic.ini"), \
             patch("obs_quickshare.cli.collection_exists", return_value=False), \
             patch("obs_quickshare.cli.write_scene_collection",
                   return_value=tmp_path / "QuickShare.json"), \
             patch("obs_quickshare.cli.shortcut_exists", return_value=False), \
             patch("obs_quickshare.cli.write_shortcut",
                   return_value=tmp_path / "OBS QuickShare.command"):
            rc = cmd_install(args)

        assert rc == 0

    def test_skips_existing_profile_without_force(self, tmp_path, capsys):
        result_obj = _fake_detection(tmp_path)
        args = _make_install_args(force=False)

        with patch("obs_quickshare.cli.run_detection", return_value=result_obj), \
             patch("obs_quickshare.cli.profile_exists", return_value=True), \
             patch("obs_quickshare.cli.write_profile") as mock_write_profile, \
             patch("obs_quickshare.cli.collection_exists", return_value=False), \
             patch("obs_quickshare.cli.write_scene_collection",
                   return_value=tmp_path / "QuickShare.json"), \
             patch("obs_quickshare.cli.shortcut_exists", return_value=False), \
             patch("obs_quickshare.cli.write_shortcut",
                   return_value=tmp_path / "OBS QuickShare.command"):
            cmd_install(args)

        mock_write_profile.assert_not_called()

    def test_force_overwrites_existing_profile(self, tmp_path):
        result_obj = _fake_detection(tmp_path)
        args = _make_install_args(force=True)

        with patch("obs_quickshare.cli.run_detection", return_value=result_obj), \
             patch("obs_quickshare.cli.profile_exists", return_value=True), \
             patch("obs_quickshare.cli.write_profile",
                   return_value=tmp_path / "basic.ini") as mock_wp, \
             patch("obs_quickshare.cli.collection_exists", return_value=True), \
             patch("obs_quickshare.cli.write_scene_collection",
                   return_value=tmp_path / "QuickShare.json"), \
             patch("obs_quickshare.cli.shortcut_exists", return_value=True), \
             patch("obs_quickshare.cli.write_shortcut",
                   return_value=tmp_path / "OBS QuickShare.command"):
            cmd_install(args)

        mock_wp.assert_called_once_with(result_obj, force=True)


# ---------------------------------------------------------------------------
# cmd_status
# ---------------------------------------------------------------------------

class TestCmdStatus:
    def test_returns_1_when_obs_missing(self):
        args = MagicMock()
        with patch("obs_quickshare.cli.run_detection",
                   side_effect=RuntimeError("OBS not found")):
            result = cmd_status(args)
        assert result == 1

    def test_returns_0_on_success(self, tmp_path):
        result_obj = _fake_detection(tmp_path)
        args = MagicMock()

        with patch("obs_quickshare.cli.run_detection", return_value=result_obj), \
             patch("obs_quickshare.cli.profile_exists", return_value=True), \
             patch("obs_quickshare.cli.collection_exists", return_value=True), \
             patch("obs_quickshare.cli.shortcut_exists", return_value=True):
            rc = cmd_status(args)

        assert rc == 0

    def test_incomplete_install_prints_instructions(self, tmp_path, capsys):
        result_obj = _fake_detection(tmp_path)
        args = MagicMock()

        with patch("obs_quickshare.cli.run_detection", return_value=result_obj), \
             patch("obs_quickshare.cli.profile_exists", return_value=False), \
             patch("obs_quickshare.cli.collection_exists", return_value=False), \
             patch("obs_quickshare.cli.shortcut_exists", return_value=False):
            cmd_status(args)

        captured = capsys.readouterr()
        assert "install" in captured.out.lower()


# ---------------------------------------------------------------------------
# cmd_uninstall
# ---------------------------------------------------------------------------

class TestCmdUninstall:
    def test_returns_1_when_obs_missing(self):
        args = MagicMock()
        args.yes = True
        with patch("obs_quickshare.cli.run_detection",
                   side_effect=RuntimeError("OBS not found")):
            result = cmd_uninstall(args)
        assert result == 1

    def test_aborts_without_yes(self, tmp_path, capsys):
        result_obj = _fake_detection(tmp_path)
        args = MagicMock()
        args.yes = False

        with patch("obs_quickshare.cli.run_detection", return_value=result_obj), \
             patch("obs_quickshare.cli._confirm", return_value=False):
            rc = cmd_uninstall(args)

        assert rc == 0
        captured = capsys.readouterr()
        assert "Aborted" in captured.out

    def test_removes_profile_and_scenes(self, tmp_path):
        result_obj = _fake_detection(tmp_path)

        # Create the files that uninstall should remove
        profile_dir = result_obj.config_root / "basic" / "profiles" / "QuickShare"
        profile_dir.mkdir(parents=True)
        scenes_file = result_obj.config_root / "basic" / "scenes" / "QuickShare.json"
        scenes_file.parent.mkdir(parents=True)
        scenes_file.write_text("{}")

        args = MagicMock()
        args.yes = True

        with patch("obs_quickshare.cli.run_detection", return_value=result_obj), \
             patch("obs_quickshare.shortcut._macos_shortcut_path",
                   return_value=tmp_path / "nonexistent.command"):
            cmd_uninstall(args)

        assert not profile_dir.exists()
        assert not scenes_file.exists()
