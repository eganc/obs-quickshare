"""
drive.py — Google Drive sync dispatch.

Supports three modes:
  Mode A (local):  Move completed MP4 into local Google Drive folder.
                   Drive for Desktop handles the upload automatically.
  Mode B (rclone): Upload via rclone to a configured remote.
  Mode C (none):   Leave files in local output dir, no cloud sync.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

from .detect import DriveInfo

QUICKSHARE_SUBFOLDER = "OBS QuickShare"


def _drive_output_dir(drive: DriveInfo) -> Path | None:
    """
    Return the destination directory for completed MP4s.
    Creates the OBS QuickShare subfolder inside the Drive folder if needed.
    Returns None for Mode C.
    """
    if drive.mode == "local" and drive.path:
        dest = drive.path / QUICKSHARE_SUBFOLDER
        dest.mkdir(parents=True, exist_ok=True)
        return dest
    return None


def move_to_drive(mp4_path: Path, drive: DriveInfo, output_dir: Path) -> Path:
    """
    Move a completed MP4 to the appropriate destination.

    Mode A: move into Drive folder (Drive app handles upload)
    Mode B: copy to output_dir first, then rclone upload; original stays in output_dir
    Mode C: move into output_dir

    Returns the final path of the file.
    """
    if drive.mode == "local":
        dest_dir = _drive_output_dir(drive) or output_dir
        dest = dest_dir / mp4_path.name
        # Avoid overwriting if a file with same name already exists in dest
        dest = _unique_path(dest)
        shutil.move(str(mp4_path), dest)
        return dest

    elif drive.mode == "rclone":
        # Move to local output first
        local_dest = output_dir / mp4_path.name
        local_dest = _unique_path(local_dest)
        shutil.move(str(mp4_path), local_dest)
        # Then upload via rclone (non-blocking subprocess)
        _rclone_upload(local_dest, drive.rclone_remote)
        return local_dest

    else:  # mode == "none"
        dest = output_dir / mp4_path.name
        dest = _unique_path(dest)
        shutil.move(str(mp4_path), dest)
        return dest


def _unique_path(path: Path) -> Path:
    """
    If path already exists, append _2, _3, … until we find a free name.
    E.g. recording.mp4 → recording_2.mp4
    """
    if not path.exists():
        return path
    stem   = path.stem
    suffix = path.suffix
    parent = path.parent
    counter = 2
    while True:
        candidate = parent / f"{stem}_{counter}{suffix}"
        if not candidate.exists():
            return candidate
        counter += 1


def _rclone_upload(local_path: Path, remote: str | None) -> None:
    """
    Run rclone copy in a subprocess (fire-and-forget).
    Errors are printed to stderr but do not raise — the file is already safe locally.
    """
    if not remote:
        print("Warning: rclone mode selected but no remote name configured.", file=sys.stderr)
        return
    if not shutil.which("rclone"):
        print("Warning: rclone not found on PATH — skipping cloud upload.", file=sys.stderr)
        return

    cmd = [
        "rclone", "copy",
        str(local_path),
        f"{remote}:{QUICKSHARE_SUBFOLDER}/",
        "--progress",
    ]
    try:
        # Detach: we don't wait for completion — the file is already safely on disk
        subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            close_fds=True,
        )
    except OSError as e:
        print(f"Warning: failed to launch rclone: {e}", file=sys.stderr)


def describe_drive_mode(drive: DriveInfo) -> str:
    """Return a human-readable description of the active Drive mode."""
    if drive.mode == "local":
        return f"Google Drive (local folder: {drive.path / QUICKSHARE_SUBFOLDER})"
    elif drive.mode == "rclone":
        return f"rclone remote '{drive.rclone_remote}:{QUICKSHARE_SUBFOLDER}/'"
    else:
        return "Local only (no cloud sync)"
