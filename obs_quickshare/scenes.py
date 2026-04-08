"""
scenes.py — Generate the QuickShare OBS scene collection JSON.

Scene layout:
  - Full-screen display capture (bottom layer)
  - Webcam PiP at 320×180, bottom-right corner (top layer, optional)
    with a chroma key filter attached (disabled by default)
"""

from __future__ import annotations

import json
import platform
import re
import subprocess
import uuid
from pathlib import Path

COLLECTION_NAME = "QuickShare"
SCENE_NAME = "QuickShare"

# PiP dimensions and position (1920×1080 canvas)
PIP_W = 320
PIP_H = 180
PIP_X = 1920 - PIP_W - 20  # 20 px right margin  → 1580
PIP_Y = 1080 - PIP_H - 20  # 20 px bottom margin → 880


def _make_uuid() -> str:
    return str(uuid.uuid4())


def _first_camera_device_id() -> str:
    """Return the AVFoundation unique ID of the first available camera on macOS.

    Falls back to empty string if detection fails; OBS will prompt the user to
    select a device when the source properties are opened.
    """
    try:
        out = subprocess.check_output(
            ["system_profiler", "SPCameraDataType"],
            text=True, stderr=subprocess.DEVNULL, timeout=5,
        )
        match = re.search(r"Unique ID:\s*(\S+)", out)
        if match:
            return match.group(1)
    except Exception:
        pass
    return ""


def _display_capture_source(system: str,
                            capture_mode: str = "display",
                            capture_target: str = "") -> dict:
    """Return an OBS display capture source dict appropriate for the platform.

    macOS source IDs by OBS version:
      OBS 30+ (macOS 12.3+): "screen_capture"  — ScreenCaptureKit-based.
                              Supports hide_obs to exclude OBS from the capture.
      OBS 28–29:             "display_capture"  — legacy CoreGraphics API.

    capture_mode controls what is captured (macOS only; ignored on Win/Linux):
      "display"  — full display (default); type=0
      "app"      — all windows of one application; type=2
                   capture_target must be the app bundle ID, e.g. "com.apple.Safari"
      "window"   — single window picker; type=1
                   OBS will show a window selector the first time the source loads
    """
    if system == "Darwin":
        source_id = "screen_capture"
        if capture_mode == "app":
            settings: dict = {
                "type": 2,
                "application": capture_target,
                "show_cursor": True,
                "hide_obs": True,
            }
        elif capture_mode == "window":
            settings = {
                "type": 1,
                "show_cursor": True,
                "hide_obs": True,
            }
        else:  # "display" (default)
            settings = {
                "type": 0,
                "display": "",    # empty = primary display
                "show_cursor": True,
                "hide_obs": True,
            }
    elif system == "Windows":
        source_id = "monitor_capture"
        settings = {
            "monitor": 0,
            "show_cursor": True,
            "compatibility": False,
        }
    else:  # Linux
        source_id = "xshm_input"
        settings = {
            "screen": 0,
            "show_cursor": True,
        }

    return {
        "id": source_id,
        "uuid": _make_uuid(),
        "name": "Screen",
        "flags": 0,
        "settings": settings,
        "mixers": 0,
        "sync": 0,
        "volume": 1.0,
        "balance": 0.5,
        "enabled": True,
        "muted": False,
        "push-to-mute": False,
        "push-to-mute-delay": 0,
        "push-to-talk": False,
        "push-to-talk-delay": 0,
        "hotkeys": {},
        "deinterlace_field_order": 0,
        "deinterlace_mode": 0,
        "filters": [],
        "versioned_id": source_id,
    }


def _webcam_source() -> dict:
    """Return an OBS video capture source (webcam) with a chroma key filter."""
    chroma_key_filter = {
        "id": "chroma_key_filter_v2",
        "uuid": _make_uuid(),
        "name": "Chroma Key",
        "enabled": False,   # disabled by default — user can enable in OBS
        "settings": {
            "color_type": 1,  # 1 = green
            "opacity": 1.0,
            "contrast": 0.0,
            "brightness": 0.0,
            "gamma": 0.0,
            "similarity": 80,
            "smoothness": 5,
            "spill": 100,
        },
    }

    if platform.system() == "Darwin":
        source_id = "av_capture_input_v2"
        settings: dict = {
            "device": _first_camera_device_id(),
            "use_preset": True,
            "preset": "AVCaptureSessionPreset1280x720",
        }
    elif platform.system() == "Windows":
        source_id = "dshow_input"
        settings = {
            "video_device_id": "default",
            "res_type": 0,
        }
    else:
        source_id = "v4l2_input"
        settings = {
            "device_id": "/dev/video0",
        }

    return {
        "id": source_id,
        "uuid": _make_uuid(),
        "name": "Webcam",
        "flags": 0,
        "settings": settings,
        "mixers": 0,
        "sync": 0,
        "volume": 1.0,
        "balance": 0.5,
        "enabled": True,
        "muted": False,
        "push-to-mute": False,
        "push-to-mute-delay": 0,
        "push-to-talk": False,
        "push-to-talk-delay": 0,
        "hotkeys": {},
        "deinterlace_field_order": 0,
        "deinterlace_mode": 0,
        "filters": [chroma_key_filter],
        "versioned_id": source_id,
    }


def _scene_item(source: dict, item_id: int, x: float, y: float,
                w: float, h: float) -> dict:
    """Build a scene item (source reference with transform)."""
    return {
        "id": item_id,
        "name": source["name"],
        "source_uuid": source["uuid"],
        "visible": True,
        "locked": False,
        "align": 5,  # top-left alignment
        "bounds_type": 2,  # OBS_BOUNDS_SCALE_INNER — scale to fit, keep aspect ratio
        "bounds_align": 0,
        "bounds": {"x": w, "y": h},
        "crop_left": 0,
        "crop_top": 0,
        "crop_right": 0,
        "crop_bottom": 0,
        "scale_filter": 0,
        "blend_type": 0,
        "blend_method": 0,
        "pos": {"x": x, "y": y},
        "rot": 0.0,
        "scale": {"x": 1.0, "y": 1.0},
        "group_id": 0,
        "private_settings": {},
    }


def build_scene_collection(capture_mode: str = "display",
                           capture_target: str = "",
                           include_webcam: bool = False,
                           include_mic: bool = False) -> dict:
    """
    Build the full OBS scene collection dict.
    Compatible with OBS 28+ scene collection format (version 2).

    capture_mode / capture_target: see _display_capture_source().
    include_webcam: add a webcam PiP source (bottom-right corner).
    include_mic: add a microphone audio source (system default device).
    """
    system = platform.system()

    display_source = _display_capture_source(system, capture_mode, capture_target)

    scene_items = []
    sources = [display_source]
    item_id = 1

    screen_item = _scene_item(display_source, item_id=item_id,
                              x=0.0, y=0.0, w=1920.0, h=1080.0)
    scene_items.append(screen_item)
    item_id += 1

    if include_webcam:
        webcam_source = _webcam_source()
        webcam_item = _scene_item(webcam_source, item_id=item_id,
                                  x=float(PIP_X), y=float(PIP_Y),
                                  w=float(PIP_W), h=float(PIP_H))
        scene_items.append(webcam_item)
        sources.append(webcam_source)
        item_id += 1

    scene_source = {
        "id": "scene",
        "uuid": _make_uuid(),
        "name": SCENE_NAME,
        "flags": 0,
        "settings": {
            "custom_size": False,
            "id_counter": item_id - 1,
            "items": scene_items,
        },
        "mixers": 0,
        "sync": 0,
        "volume": 1.0,
        "balance": 0.5,
        "enabled": True,
        "muted": False,
        "push-to-mute": False,
        "push-to-mute-delay": 0,
        "push-to-talk": False,
        "push-to-talk-delay": 0,
        "hotkeys": {},
        "deinterlace_field_order": 0,
        "deinterlace_mode": 0,
        "filters": [],
        "versioned_id": "scene",
    }
    sources.append(scene_source)

    collection: dict = {
        "current_program_scene": SCENE_NAME,
        "current_scene": SCENE_NAME,
        "current_transition": "FadeTransition",
        "modules": {},
        "name": COLLECTION_NAME,
        "preview_locked": False,
        "quick_transitions": [],
        "saved_projectors": [],
        "scaling_enabled": False,
        "scaling_level": 0,
        "scaling_off_x": 0.0,
        "scaling_off_y": 0.0,
        "scene_order": [{"name": SCENE_NAME}],
        "sources": sources,
        "transition_duration": 300,
        "transitions": [],
        "version": 2,
    }

    if include_mic:
        mic_id = "wasapi_input_capture" if system == "Windows" else "coreaudio_input_capture"
        collection["AuxAudioDevice1"] = {
            "flags": 0, "id": mic_id, "muted": False,
            "name": "Mic/Aux", "settings": {}, "volume": 1.0,
        }

    return collection


def collection_path(config_root: Path, collection_name: str = COLLECTION_NAME) -> Path:
    return config_root / "basic" / "scenes" / f"{collection_name}.json"


def collection_exists(config_root: Path, collection_name: str = COLLECTION_NAME) -> bool:
    return collection_path(config_root, collection_name).exists()


def write_scene_collection(config_root: Path, force: bool = False,
                           capture_mode: str = "display",
                           capture_target: str = "",
                           include_webcam: bool = False,
                           include_mic: bool = False) -> Path:
    """
    Write QuickShare.json to the OBS scenes directory.

    Raises FileExistsError if the collection already exists and force=False.
    Returns the path to the written file.
    """
    dest = collection_path(config_root)

    if dest.exists() and not force:
        raise FileExistsError(
            f"QuickShare scene collection already exists at {dest}.\n"
            "Run with --force to overwrite."
        )

    dest.parent.mkdir(parents=True, exist_ok=True)
    data = build_scene_collection(capture_mode, capture_target, include_webcam, include_mic)

    with open(dest, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)

    return dest
