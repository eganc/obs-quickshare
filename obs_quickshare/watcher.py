"""
watcher.py — Watch the staging directory for completed MP4s and move them.

Safety rules before a file is considered "done":
  1. File size has been stable for 3 consecutive 2-second polls (6 s minimum wait).
  2. No process has the file open (checked via psutil / lsof).
  3. File is at least 5 seconds old.
  4. File is > 0 bytes.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path
from threading import Event, Lock, Thread
from typing import Callable

_PRINT_LOCK = Lock()  # serialise multi-file progress lines


def _fmt_size(n: int) -> str:
    if n < 1024:
        return f"{n} B"
    if n < 1024 ** 2:
        return f"{n / 1024:.1f} KB"
    if n < 1024 ** 3:
        return f"{n / 1024 ** 2:.1f} MB"
    return f"{n / 1024 ** 3:.2f} GB"


def _status(label: str, msg: str, end: str = "\n") -> None:
    """Thread-safe status print. Use end='\r' for in-place updates."""
    with _PRINT_LOCK:
        line = f"[quickshare] {label}: {msg}"
        # Pad to 80 chars so \r overwrites the previous line cleanly
        print(f"{line:<80}", end=end, flush=True)

try:
    import psutil
    _PSUTIL_AVAILABLE = True
except ImportError:
    _PSUTIL_AVAILABLE = False

try:
    from watchdog.events import FileCreatedEvent, FileMovedEvent, PatternMatchingEventHandler
    from watchdog.observers import Observer
    _WATCHDOG_AVAILABLE = True
except ImportError:
    _WATCHDOG_AVAILABLE = False

from .detect import DriveInfo
from .drive import move_to_drive
from .share import copy_to_clipboard, get_share_link

# Tuning parameters
_POLL_INTERVAL_S   = 2      # seconds between size checks
_STABLE_CHECKS     = 3      # number of consecutive stable checks required
_MIN_AGE_S         = 5      # minimum file age in seconds before we consider it
_MIN_SIZE_BYTES    = 1024   # ignore obvious zero/empty artefacts


def _file_is_open(path: Path) -> bool:
    """Return True if any process currently has this file open.

    Falls back to False (optimistic) when psutil is not installed, relying on
    the stable-size checks alone to guard against incomplete files.
    """
    if not _PSUTIL_AVAILABLE:
        return False

    try:
        for proc in psutil.process_iter(["open_files"]):
            try:
                open_files = proc.info.get("open_files") or []
                for f in open_files:
                    if Path(f.path) == path.resolve():
                        return True
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
    except Exception:
        pass
    return False


def _wait_until_stable(
    path: Path,
    stop_event: Event | None = None,
    status_cb: Callable[[str], None] | None = None,
) -> bool:
    """
    Block until the file is stable (not growing, not open).
    Returns True when the file is ready, False if stop_event is set before that.
    Calls status_cb(message) on each poll cycle so the caller can show progress.
    """
    stable_count = 0
    last_size    = -1

    while True:
        if stop_event and stop_event.is_set():
            return False

        if not path.exists():
            return False

        try:
            stat  = path.stat()
            size  = stat.st_size
            age_s = time.time() - stat.st_mtime
        except OSError:
            return False

        if size < _MIN_SIZE_BYTES:
            stable_count = 0
            last_size = size
            if status_cb:
                status_cb(f"{_fmt_size(size)}  (waiting for data …)")
            time.sleep(_POLL_INTERVAL_S)
            continue

        if age_s < _MIN_AGE_S:
            if status_cb:
                status_cb(f"{_fmt_size(size)}  (age {age_s:.0f}s < {_MIN_AGE_S}s)")
            time.sleep(_POLL_INTERVAL_S)
            continue

        if size == last_size:
            stable_count += 1
        else:
            stable_count = 0

        last_size = size

        if status_cb:
            bar = "█" * stable_count + "░" * (_STABLE_CHECKS - stable_count)
            open_flag = "  file open" if _file_is_open(path) else ""
            status_cb(f"{_fmt_size(size)}  [{bar}] {stable_count}/{_STABLE_CHECKS}{open_flag}")

        if stable_count >= _STABLE_CHECKS:
            if not _file_is_open(path):
                return True
            else:
                stable_count = 0

        time.sleep(_POLL_INTERVAL_S)


# ---------------------------------------------------------------------------
# Watchdog-based watcher
# ---------------------------------------------------------------------------

class _MP4Handler(PatternMatchingEventHandler if _WATCHDOG_AVAILABLE else object):  # type: ignore
    """Handle new .mp4 files appearing in the staging directory."""

    def __init__(
        self,
        staging_dir: Path,
        output_dir: Path,
        drive: DriveInfo,
        on_moved: Callable[[Path, Path], None] | None = None,
        stop_event: Event | None = None,
    ):
        if _WATCHDOG_AVAILABLE:
            super().__init__(patterns=["*.mp4"], ignore_directories=True, case_sensitive=False)
        self._staging_dir = staging_dir
        self._output_dir  = output_dir
        self._drive       = drive
        self._on_moved    = on_moved
        self._stop_event  = stop_event
        self._in_flight: set[Path] = set()

    def _handle_new_mp4(self, src_path: Path) -> None:
        """Spawns a thread to wait-and-move a single MP4."""
        if src_path in self._in_flight:
            return
        self._in_flight.add(src_path)

        def worker():
            name = src_path.name
            try:
                _status(name, "detected — waiting to stabilise …")

                def on_progress(msg: str) -> None:
                    _status(name, msg, end="\r")

                ready = _wait_until_stable(
                    src_path,
                    stop_event=self._stop_event,
                    status_cb=on_progress,
                )
                # End the in-place progress line
                print(flush=True)

                if not ready:
                    return

                _status(name, "stable — moving to output …")
                dest = move_to_drive(src_path, self._drive, self._output_dir)
                _status(name, f"saved → {dest}")

                if self._on_moved:
                    self._on_moved(src_path, dest)

                # Retrieve share link (blocks for Drive sync or rclone upload)
                def on_share_status(msg: str) -> None:
                    _status(name, msg, end="\r")

                link = get_share_link(dest, self._drive, status_cb=on_share_status)
                print(flush=True)  # end any \r line

                if link:
                    _status(name, f"share link → {link}")
                    if copy_to_clipboard(link):
                        _status(name, "link copied to clipboard ✓")
                else:
                    _status(name, "no share link available")

            except FileNotFoundError:
                # Duplicate watchdog event — first worker already moved the file.
                _status(name, "already moved (duplicate event, skipping)")
            except Exception as e:
                print(f"[quickshare] Error processing {name}: {e}", file=sys.stderr)
            finally:
                self._in_flight.discard(src_path)

        t = Thread(target=worker, daemon=True, name=f"move-{src_path.name}")
        t.start()

    # watchdog event callbacks
    def on_created(self, event: FileCreatedEvent) -> None:
        self._handle_new_mp4(Path(event.src_path))

    def on_moved(self, event: FileMovedEvent) -> None:
        # OBS remux writes to a temp name then renames — catch the rename
        dest = Path(event.dest_path)
        if dest.suffix.lower() == ".mp4":
            self._handle_new_mp4(dest)


class FileWatcher:
    """
    High-level watcher that monitors the staging directory.

    Usage:
        watcher = FileWatcher(staging_dir, output_dir, drive)
        watcher.start()
        # ... runs until watcher.stop() is called
    """

    def __init__(
        self,
        staging_dir: Path,
        output_dir: Path,
        drive: DriveInfo,
        on_moved: Callable[[Path, Path], None] | None = None,
    ):
        self._staging_dir = staging_dir
        self._output_dir  = output_dir
        self._drive       = drive
        self._on_moved    = on_moved
        self._stop_event  = Event()
        self._observer    = None

    def start(self) -> None:
        """Start watching. Blocks until stop() is called."""
        self._staging_dir.mkdir(parents=True, exist_ok=True)
        self._output_dir.mkdir(parents=True, exist_ok=True)

        if not _WATCHDOG_AVAILABLE:
            print(
                "Warning: 'watchdog' package not installed. "
                "Falling back to polling-only mode.",
                file=sys.stderr,
            )
            self._poll_loop()
            return

        handler = _MP4Handler(
            staging_dir=self._staging_dir,
            output_dir=self._output_dir,
            drive=self._drive,
            on_moved=self._on_moved,
            stop_event=self._stop_event,
        )
        self._observer = Observer()
        self._observer.schedule(handler, str(self._staging_dir), recursive=False)
        self._observer.start()
        print(f"[watcher] Watching {self._staging_dir} …", flush=True)

        try:
            while not self._stop_event.is_set():
                time.sleep(1)
        finally:
            self._observer.stop()
            self._observer.join()

    def stop(self) -> None:
        self._stop_event.set()

    def start_background(self) -> Thread:
        """Start the watcher in a background daemon thread."""
        t = Thread(target=self.start, daemon=True, name="obs-quickshare-watcher")
        t.start()
        return t

    # ------------------------------------------------------------------
    # Fallback: simple polling loop (no watchdog)
    # ------------------------------------------------------------------

    def _poll_loop(self) -> None:
        """Poll the staging directory every 5 s for new MP4s."""
        seen: set[Path] = set()
        print(f"[watcher] Polling {self._staging_dir} every 5 s …", flush=True)

        while not self._stop_event.is_set():
            if self._staging_dir.exists():
                for mp4 in self._staging_dir.glob("*.mp4"):
                    if mp4 not in seen:
                        seen.add(mp4)
                        # Reuse the same per-file worker logic
                        handler = _MP4Handler(
                            staging_dir=self._staging_dir,
                            output_dir=self._output_dir,
                            drive=self._drive,
                            on_moved=self._on_moved,
                            stop_event=self._stop_event,
                        )
                        handler._handle_new_mp4(mp4)

            time.sleep(5)
