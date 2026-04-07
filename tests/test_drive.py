"""
Tests for obs_quickshare.drive
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from obs_quickshare.detect import DriveInfo
from obs_quickshare.drive import (
    QUICKSHARE_SUBFOLDER,
    _rclone_upload,
    _unique_path,
    describe_drive_mode,
    move_to_drive,
)


# ---------------------------------------------------------------------------
# _unique_path
# ---------------------------------------------------------------------------

class TestUniquePath:
    def test_returns_path_when_free(self, tmp_path):
        p = tmp_path / "recording.mp4"
        assert _unique_path(p) == p

    def test_appends_counter_when_exists(self, tmp_path):
        p = tmp_path / "recording.mp4"
        p.write_bytes(b"")  # create the file
        result = _unique_path(p)
        assert result == tmp_path / "recording_2.mp4"

    def test_increments_until_free(self, tmp_path):
        p = tmp_path / "recording.mp4"
        (tmp_path / "recording.mp4").write_bytes(b"")
        (tmp_path / "recording_2.mp4").write_bytes(b"")
        result = _unique_path(p)
        assert result == tmp_path / "recording_3.mp4"

    def test_preserves_suffix(self, tmp_path):
        p = tmp_path / "clip.mkv"
        p.write_bytes(b"")
        result = _unique_path(p)
        assert result.suffix == ".mkv"
        assert result.name == "clip_2.mkv"


# ---------------------------------------------------------------------------
# describe_drive_mode
# ---------------------------------------------------------------------------

class TestDescribeDriveMode:
    def test_local_mode(self):
        drive = DriveInfo(mode="local", path=Path("/Users/me/Google Drive/My Drive"))
        desc = describe_drive_mode(drive)
        assert "Google Drive" in desc
        assert QUICKSHARE_SUBFOLDER in desc

    def test_rclone_mode(self):
        drive = DriveInfo(mode="rclone", rclone_remote="gdrive")
        desc = describe_drive_mode(drive)
        assert "gdrive" in desc
        assert QUICKSHARE_SUBFOLDER in desc

    def test_none_mode(self):
        drive = DriveInfo(mode="none")
        desc = describe_drive_mode(drive)
        assert "Local only" in desc or "local" in desc.lower()


# ---------------------------------------------------------------------------
# move_to_drive — Mode A (local)
# ---------------------------------------------------------------------------

class TestMoveToDriveLocalMode:
    def test_moves_to_drive_subfolder(self, tmp_path):
        drive_root = tmp_path / "My Drive"
        drive_root.mkdir()
        staging = tmp_path / "staging"
        staging.mkdir()
        mp4 = staging / "recording.mp4"
        mp4.write_bytes(b"fake video data")

        drive = DriveInfo(mode="local", path=drive_root)
        output_dir = tmp_path / "output"
        output_dir.mkdir()

        dest = move_to_drive(mp4, drive, output_dir)

        expected_dir = drive_root / QUICKSHARE_SUBFOLDER
        assert dest.parent == expected_dir
        assert dest.name == "recording.mp4"
        assert dest.exists()
        assert not mp4.exists()  # original moved

    def test_avoids_overwriting_existing_file(self, tmp_path):
        drive_root = tmp_path / "My Drive"
        dest_dir = drive_root / QUICKSHARE_SUBFOLDER
        dest_dir.mkdir(parents=True)
        # Pre-existing file
        (dest_dir / "recording.mp4").write_bytes(b"old")

        staging = tmp_path / "staging"
        staging.mkdir()
        mp4 = staging / "recording.mp4"
        mp4.write_bytes(b"new video data")

        drive = DriveInfo(mode="local", path=drive_root)
        output_dir = tmp_path / "output"
        output_dir.mkdir()

        dest = move_to_drive(mp4, drive, output_dir)
        assert dest.name == "recording_2.mp4"


# ---------------------------------------------------------------------------
# move_to_drive — Mode B (rclone)
# ---------------------------------------------------------------------------

class TestMoveToDriveRcloneMode:
    def test_moves_to_local_output_and_fires_rclone(self, tmp_path):
        staging = tmp_path / "staging"
        staging.mkdir()
        mp4 = staging / "recording.mp4"
        mp4.write_bytes(b"fake video data")

        output_dir = tmp_path / "output"
        output_dir.mkdir()

        drive = DriveInfo(mode="rclone", rclone_remote="gdrive")

        with patch("obs_quickshare.drive._rclone_upload") as mock_upload:
            dest = move_to_drive(mp4, drive, output_dir)

        assert dest.parent == output_dir
        assert dest.exists()
        mock_upload.assert_called_once_with(dest, "gdrive")


# ---------------------------------------------------------------------------
# move_to_drive — Mode C (none)
# ---------------------------------------------------------------------------

class TestMoveToDriveNoneMode:
    def test_moves_to_output_dir(self, tmp_path):
        staging = tmp_path / "staging"
        staging.mkdir()
        mp4 = staging / "recording.mp4"
        mp4.write_bytes(b"fake video data")

        output_dir = tmp_path / "output"
        output_dir.mkdir()

        drive = DriveInfo(mode="none")
        dest = move_to_drive(mp4, drive, output_dir)

        assert dest == output_dir / "recording.mp4"
        assert dest.exists()
        assert not mp4.exists()


# ---------------------------------------------------------------------------
# _rclone_upload
# ---------------------------------------------------------------------------

class TestRcloneUpload:
    def test_fires_popen(self, tmp_path):
        mp4 = tmp_path / "recording.mp4"
        mp4.write_bytes(b"data")
        with patch("obs_quickshare.drive.shutil.which", return_value="/usr/local/bin/rclone"), \
             patch("obs_quickshare.drive.subprocess.Popen") as mock_popen:
            _rclone_upload(mp4, remote="gdrive")
        mock_popen.assert_called_once()
        cmd = mock_popen.call_args[0][0]
        assert "rclone" in cmd[0]
        assert "copy" in cmd
        assert "gdrive:OBS QuickShare/" in cmd

    def test_no_op_when_no_remote(self, tmp_path, capsys):
        mp4 = tmp_path / "recording.mp4"
        with patch("obs_quickshare.drive.subprocess.Popen") as mock_popen:
            _rclone_upload(mp4, remote=None)
        mock_popen.assert_not_called()

    def test_no_op_when_rclone_not_on_path(self, tmp_path, capsys):
        mp4 = tmp_path / "recording.mp4"
        with patch("obs_quickshare.drive.shutil.which", return_value=None), \
             patch("obs_quickshare.drive.subprocess.Popen") as mock_popen:
            _rclone_upload(mp4, remote="gdrive")
        mock_popen.assert_not_called()

    def test_popen_failure_doesnt_raise(self, tmp_path):
        mp4 = tmp_path / "recording.mp4"
        with patch("obs_quickshare.drive.shutil.which", return_value="/usr/local/bin/rclone"), \
             patch("obs_quickshare.drive.subprocess.Popen", side_effect=OSError("boom")):
            # Must not raise
            _rclone_upload(mp4, remote="gdrive")
