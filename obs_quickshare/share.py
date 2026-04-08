"""
share.py — Retrieve a shareable link for a completed recording.

Only Mode B (rclone) is supported:
  Runs `rclone link` after a synchronous upload.

Mode A (local Drive) and Mode C (none) return None — no cloud destination.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path
from typing import Callable, Optional

from .detect import DriveInfo

StatusCb = Optional[Callable[[str], None]]


def get_share_link(
    dest_path: Path,
    drive: DriveInfo,
    status_cb: StatusCb = None,
) -> str | None:
    """
    Return a shareable URL for dest_path, or None if unavailable.

    Only Mode B (rclone) generates share links. Mode A and C return None.

    status_cb is called with short status strings during waits so the
    caller can display progress without blocking on a return value.
    """
    if drive.mode == "rclone":
        return _rclone_link(dest_path, drive.rclone_remote, status_cb)
    return None


def copy_to_clipboard(text: str) -> bool:
    """Copy text to the system clipboard. Returns True on success."""
    try:
        if sys.platform == "darwin":
            subprocess.run(["pbcopy"], input=text.encode(), check=True)
        elif sys.platform == "win32":
            subprocess.run(["clip"], input=text.encode(), check=True)
        else:
            # Try xclip then xdotool
            if shutil.which("xclip"):
                subprocess.run(
                    ["xclip", "-selection", "clipboard"],
                    input=text.encode(), check=True,
                )
            elif shutil.which("xdotool"):
                subprocess.run(["xdotool", "type", text], check=True)
            else:
                return False
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Mode B — rclone link
# ---------------------------------------------------------------------------

def _rclone_link(
    local_path: Path,
    remote: str | None,
    status_cb: StatusCb,
) -> str | None:
    """Get a shareable link via `rclone link` (Mode B)."""
    if not remote or not shutil.which("rclone"):
        return None

    from .drive import QUICKSHARE_SUBFOLDER
    remote_path = f"{remote}:{QUICKSHARE_SUBFOLDER}/{local_path.name}"

    if status_cb:
        status_cb("Getting share link from rclone …")
    try:
        result = subprocess.run(
            ["rclone", "link", remote_path],
            capture_output=True, text=True, timeout=30,
        )
        link = result.stdout.strip()
        return link if (link and link.startswith("http")) else None
    except Exception as e:
        if status_cb:
            status_cb(f"rclone link failed: {e}")
        return None
