"""
Tests for obs_quickshare.shortcut
"""
from __future__ import annotations

import stat
from pathlib import Path
from unittest.mock import patch

import pytest

from obs_quickshare.shortcut import (
    OBS_FLAGS,
    PROFILE_NAME,
    COLLECTION_NAME,
    find_obs_binary,
    shortcut_exists,
    write_shortcut,
    _macos_shortcut_path,
    _linux_shortcut_path,
)


# ---------------------------------------------------------------------------
# find_obs_binary
# ---------------------------------------------------------------------------

class TestFindObsBinary:
    def test_returns_none_when_nothing_exists(self):
        with patch("pathlib.Path.exists", return_value=False):
            assert find_obs_binary("Darwin") is None
            assert find_obs_binary("Windows") is None
            assert find_obs_binary("Linux") is None

    def test_returns_first_existing_binary_darwin(self, tmp_path):
        obs = tmp_path / "OBS"
        obs.write_bytes(b"")
        from obs_quickshare import shortcut
        original = shortcut._OBS_BINARY.get("Darwin", [])
        try:
            shortcut._OBS_BINARY["Darwin"] = [tmp_path / "NoExist", obs]
            result = find_obs_binary("Darwin")
            assert result == obs
        finally:
            shortcut._OBS_BINARY["Darwin"] = original

    def test_unknown_system_returns_none(self):
        result = find_obs_binary("FreeBSD")
        assert result is None


# ---------------------------------------------------------------------------
# macOS shortcut
# ---------------------------------------------------------------------------

class TestMacosShortcut:
    def _make_home(self, tmp_path):
        home = tmp_path / "home"
        home.mkdir()
        return home

    def test_creates_command_file(self, tmp_path):
        home = self._make_home(tmp_path)
        obs_bin = tmp_path / "OBS"
        obs_bin.write_bytes(b"")

        with patch("obs_quickshare.shortcut.platform.system", return_value="Darwin"), \
             patch("obs_quickshare.shortcut.Path.home", return_value=home), \
             patch("obs_quickshare.shortcut.find_obs_binary", return_value=obs_bin):
            dest = write_shortcut()

        assert dest.exists()
        assert dest.suffix == ".command"

    def test_command_file_is_executable(self, tmp_path):
        home = self._make_home(tmp_path)
        obs_bin = tmp_path / "OBS"
        obs_bin.write_bytes(b"")

        with patch("obs_quickshare.shortcut.platform.system", return_value="Darwin"), \
             patch("obs_quickshare.shortcut.Path.home", return_value=home), \
             patch("obs_quickshare.shortcut.find_obs_binary", return_value=obs_bin):
            dest = write_shortcut()

        mode = dest.stat().st_mode
        assert mode & stat.S_IXUSR, "File should be user-executable"

    def test_command_file_contains_obs_flags(self, tmp_path):
        home = self._make_home(tmp_path)
        obs_bin = tmp_path / "OBS"
        obs_bin.write_bytes(b"")

        with patch("obs_quickshare.shortcut.platform.system", return_value="Darwin"), \
             patch("obs_quickshare.shortcut.Path.home", return_value=home), \
             patch("obs_quickshare.shortcut.find_obs_binary", return_value=obs_bin):
            dest = write_shortcut()

        content = dest.read_text()
        assert "--profile" in content
        assert PROFILE_NAME in content
        assert "--collection" in content
        assert COLLECTION_NAME in content
        assert "--startrecording" in content

    def test_command_file_contains_obs_binary_path(self, tmp_path):
        home = self._make_home(tmp_path)
        obs_bin = tmp_path / "MyOBS"
        obs_bin.write_bytes(b"")

        with patch("obs_quickshare.shortcut.platform.system", return_value="Darwin"), \
             patch("obs_quickshare.shortcut.Path.home", return_value=home), \
             patch("obs_quickshare.shortcut.find_obs_binary", return_value=obs_bin):
            dest = write_shortcut()

        content = dest.read_text()
        assert str(obs_bin) in content

    def test_raises_file_exists_without_force(self, tmp_path):
        home = self._make_home(tmp_path)
        obs_bin = tmp_path / "OBS"
        obs_bin.write_bytes(b"")

        with patch("obs_quickshare.shortcut.platform.system", return_value="Darwin"), \
             patch("obs_quickshare.shortcut.Path.home", return_value=home), \
             patch("obs_quickshare.shortcut.find_obs_binary", return_value=obs_bin):
            write_shortcut()
            with pytest.raises(FileExistsError):
                write_shortcut()

    def test_force_overwrites(self, tmp_path):
        home = self._make_home(tmp_path)
        obs_bin = tmp_path / "OBS"
        obs_bin.write_bytes(b"")

        with patch("obs_quickshare.shortcut.platform.system", return_value="Darwin"), \
             patch("obs_quickshare.shortcut.Path.home", return_value=home), \
             patch("obs_quickshare.shortcut.find_obs_binary", return_value=obs_bin):
            dest = write_shortcut()
            dest.write_text("# old content")
            write_shortcut(force=True)

        content = dest.read_text()
        assert "# old content" not in content
        assert "--profile" in content

    def test_no_obs_binary_uses_default_path(self, tmp_path):
        """Even if OBS binary is not found, a shortcut is still written."""
        home = self._make_home(tmp_path)

        with patch("obs_quickshare.shortcut.platform.system", return_value="Darwin"), \
             patch("obs_quickshare.shortcut.Path.home", return_value=home), \
             patch("obs_quickshare.shortcut.find_obs_binary", return_value=None):
            dest = write_shortcut()

        assert dest.exists()
        content = dest.read_text()
        assert "--profile" in content


# ---------------------------------------------------------------------------
# Linux shortcut
# ---------------------------------------------------------------------------

class TestLinuxShortcut:
    def test_creates_desktop_file(self, tmp_path):
        home = tmp_path / "home"
        home.mkdir()
        obs_bin = tmp_path / "obs"
        obs_bin.write_bytes(b"")

        with patch("obs_quickshare.shortcut.platform.system", return_value="Linux"), \
             patch("obs_quickshare.shortcut.Path.home", return_value=home), \
             patch("obs_quickshare.shortcut.find_obs_binary", return_value=obs_bin):
            dest = write_shortcut()

        assert dest.suffix == ".desktop"
        content = dest.read_text()
        assert "[Desktop Entry]" in content
        assert "Exec=" in content
        assert PROFILE_NAME in content

    def test_desktop_file_is_executable(self, tmp_path):
        home = tmp_path / "home"
        home.mkdir()
        obs_bin = tmp_path / "obs"
        obs_bin.write_bytes(b"")

        with patch("obs_quickshare.shortcut.platform.system", return_value="Linux"), \
             patch("obs_quickshare.shortcut.Path.home", return_value=home), \
             patch("obs_quickshare.shortcut.find_obs_binary", return_value=obs_bin):
            dest = write_shortcut()

        assert dest.stat().st_mode & stat.S_IXUSR


# ---------------------------------------------------------------------------
# shortcut_exists
# ---------------------------------------------------------------------------

class TestShortcutExists:
    def test_returns_false_when_missing(self, tmp_path):
        with patch("obs_quickshare.shortcut.platform.system", return_value="Darwin"), \
             patch("obs_quickshare.shortcut.Path.home", return_value=tmp_path):
            assert shortcut_exists() is False

    def test_returns_true_after_creation(self, tmp_path):
        home = tmp_path / "home"
        home.mkdir()
        obs_bin = tmp_path / "OBS"
        obs_bin.write_bytes(b"")

        with patch("obs_quickshare.shortcut.platform.system", return_value="Darwin"), \
             patch("obs_quickshare.shortcut.Path.home", return_value=home), \
             patch("obs_quickshare.shortcut.find_obs_binary", return_value=obs_bin):
            write_shortcut()
            assert shortcut_exists() is True
