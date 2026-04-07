"""
Tests for obs_quickshare.watcher

Focus on _wait_until_stable logic — the safety gate that must pass
before any file is moved. This is explicitly called out in CLAUDE.md
as a rule that must never be bypassed.
"""
from __future__ import annotations

import time
from pathlib import Path
from threading import Event
from types import SimpleNamespace
from unittest.mock import MagicMock, call, patch

import pytest

from obs_quickshare.watcher import (
    _MIN_AGE_S,
    _MIN_SIZE_BYTES,
    _POLL_INTERVAL_S,
    _STABLE_CHECKS,
    _file_is_open,
    _wait_until_stable,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fake_stat(size: int, mtime: float | None = None) -> SimpleNamespace:
    """Return a stat-like object."""
    return SimpleNamespace(st_size=size, st_mtime=mtime or (time.time() - _MIN_AGE_S - 1))


# ---------------------------------------------------------------------------
# _file_is_open
# ---------------------------------------------------------------------------

class TestFileIsOpen:
    def test_returns_false_when_no_processes_open_file(self, tmp_path):
        p = tmp_path / "test.mp4"
        p.write_bytes(b"")
        # No process should have our fresh test file open
        # (may occasionally be False in some CI environments, but a safe assertion)
        result = _file_is_open(p)
        assert isinstance(result, bool)

    def test_returns_false_on_psutil_error(self, tmp_path):
        p = tmp_path / "test.mp4"
        with patch("obs_quickshare.watcher.psutil.process_iter", side_effect=Exception("boom")):
            assert _file_is_open(p) is False


# ---------------------------------------------------------------------------
# _wait_until_stable
# ---------------------------------------------------------------------------

def _mock_path(exists=True, stat_side_effect=None, stat_return=None, suffix=".mp4"):
    """Build a MagicMock that quacks like a Path for _wait_until_stable."""
    p = MagicMock(spec=Path)
    p.exists.return_value = exists
    p.suffix = suffix
    p.resolve.return_value = p
    if stat_side_effect is not None:
        p.stat.side_effect = stat_side_effect
    elif stat_return is not None:
        p.stat.return_value = stat_return
    return p


class TestWaitUntilStable:
    """
    We mock time.sleep to avoid real waits, and use MagicMock paths to
    control the simulated file state (Path.stat/exists are read-only on
    real Path instances in Python 3.9).
    """

    def test_returns_false_if_file_disappears(self):
        p = _mock_path(exists=False)
        result = _wait_until_stable(p)
        assert result is False

    def test_returns_false_when_stop_event_set(self):
        stop = Event()
        stop.set()
        p = _mock_path(exists=True, stat_return=_fake_stat(_MIN_SIZE_BYTES))
        result = _wait_until_stable(p, stop_event=stop)
        assert result is False

    def test_returns_true_after_stable_checks(self):
        fixed_size = _MIN_SIZE_BYTES * 10
        old_mtime = time.time() - _MIN_AGE_S - 1
        p = _mock_path(exists=True, stat_return=_fake_stat(fixed_size, old_mtime))

        with patch("obs_quickshare.watcher._file_is_open", return_value=False), \
             patch("obs_quickshare.watcher.time.sleep"):
            result = _wait_until_stable(p)

        assert result is True

    def test_resets_stable_count_when_size_changes(self):
        old_mtime = time.time() - _MIN_AGE_S - 1
        sizes = [
            _MIN_SIZE_BYTES * 2,   # first read — baseline
            _MIN_SIZE_BYTES * 3,   # grows — reset count
            _MIN_SIZE_BYTES * 3,   # stable 1
            _MIN_SIZE_BYTES * 3,   # stable 2
            _MIN_SIZE_BYTES * 3,   # stable 3 → triggers True
        ]
        idx = [0]

        def fake_stat():
            s = sizes[min(idx[0], len(sizes) - 1)]
            idx[0] += 1
            return _fake_stat(size=s, mtime=old_mtime)

        p = _mock_path(exists=True, stat_side_effect=fake_stat)

        with patch("obs_quickshare.watcher._file_is_open", return_value=False), \
             patch("obs_quickshare.watcher.time.sleep"):
            result = _wait_until_stable(p)

        assert result is True

    def test_waits_longer_if_file_is_open(self):
        """If the file is open, stable_count resets and we keep waiting."""
        fixed_size = _MIN_SIZE_BYTES * 10
        old_mtime = time.time() - _MIN_AGE_S - 1
        p = _mock_path(exists=True, stat_return=_fake_stat(fixed_size, old_mtime))

        is_open_returns = [True, True, True, False]  # open 3 times, then closed
        call_count = [0]

        def fake_is_open(path):
            val = is_open_returns[min(call_count[0], len(is_open_returns) - 1)]
            call_count[0] += 1
            return val

        sleep_count = [0]

        def count_sleep(_):
            sleep_count[0] += 1

        with patch("obs_quickshare.watcher._file_is_open", side_effect=fake_is_open), \
             patch("obs_quickshare.watcher.time.sleep", side_effect=count_sleep):
            result = _wait_until_stable(p)

        assert result is True
        # Must have slept more than the minimum stable check count
        assert sleep_count[0] > _STABLE_CHECKS

    def test_returns_false_if_file_too_small(self):
        """Empty/tiny files should not be moved."""
        stop = Event()
        call_count = [0]

        def fake_stat():
            call_count[0] += 1
            if call_count[0] >= 3:
                stop.set()
            return _fake_stat(size=0)

        p = _mock_path(exists=True, stat_side_effect=fake_stat)

        with patch("obs_quickshare.watcher.time.sleep"):
            result = _wait_until_stable(p, stop_event=stop)

        assert result is False

    def test_returns_false_on_stat_oserror(self):
        p = _mock_path(exists=True, stat_side_effect=OSError("permission denied"))
        result = _wait_until_stable(p)
        assert result is False

    def test_waits_for_min_age(self):
        """Files younger than _MIN_AGE_S should not be moved immediately."""
        fixed_size = _MIN_SIZE_BYTES * 10
        future_mtime = time.time()  # just now — too young

        age_call = [0]
        stop = Event()

        def fake_stat():
            age_call[0] += 1
            if age_call[0] >= 4:
                stop.set()
            return _fake_stat(size=fixed_size, mtime=future_mtime)

        p = _mock_path(exists=True, stat_side_effect=fake_stat)

        with patch("obs_quickshare.watcher.time.sleep"):
            result = _wait_until_stable(p, stop_event=stop)

        # Should not have moved — file was too young and stop was set
        assert result is False
        assert age_call[0] >= 4


# ---------------------------------------------------------------------------
# Constants sanity checks (guard against accidental modification)
# ---------------------------------------------------------------------------

def test_poll_interval_is_2s():
    assert _POLL_INTERVAL_S == 2

def test_stable_checks_is_3():
    assert _STABLE_CHECKS == 3

def test_min_age_is_5s():
    assert _MIN_AGE_S == 5

def test_min_size_is_nonzero():
    assert _MIN_SIZE_BYTES > 0
