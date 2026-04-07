"""
scenes.py — Generate the QuickShare OBS scene collection JSON.

Scene layout:
  - Full-screen display capture (bottom layer)
  - Webcam PiP at 320×180, bottom-right corner (top layer)
    with a chroma key filter attached (disabled by default)
"""

from __future__ import annotations

import json
import platform
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


def _display_capture_source(system: str) -> dict:
    """Return an OBS display capture source dict appropriate for the platform."""
    if system == "Darwin":
        source_id = "display_capture"
        settings = {
            "display_uuid": "",   # empty = default display
            "show_cursor": True,
            "crop_mode": 0,
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
            "device": "",       # empty = first available device
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
        "bounds_type": 0,
        "bounds_align": 0,
        "bounds": {"x": 0.0, "y": 0.0},
        "crop_left": 0,
        "crop_top": 0,
        "crop_right": 0,
        "crop_bottom": 0,
        "scale_filter": 0,
        "blend_type": 0,
        "blend_method": 0,
        "pos": {"x": x, "y": y},
        "rot": 0.0,
        "scale": {"x": w / 1920.0, "y": h / 1080.0},
        "group_id": 0,
        "private_settings": {},
    }


def build_scene_collection() -> dict:
    """
    Build the full OBS scene collection dict.
    Compatible with OBS 28+ scene collection format (version 2).
    """
    system = platform.system()

    display_source = _display_capture_source(system)
    webcam_source  = _webcam_source()

    # Scene items: display (id=1) is drawn first (bottom), webcam (id=2) on top
    screen_item = _scene_item(display_source, item_id=1,
                              x=0.0, y=0.0, w=1920.0, h=1080.0)
    webcam_item = _scene_item(webcam_source, item_id=2,
                              x=float(PIP_X), y=float(PIP_Y),
                              w=float(PIP_W), h=float(PIP_H))

    scene_source = {
        "id": "scene",
        "uuid": _make_uuid(),
        "name": SCENE_NAME,
        "flags": 0,
        "settings": {
            "custom_size": False,
            "id_counter": 2,
            "items": [screen_item, webcam_item],
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

    return {
        "AuxAudioDevice1": {"flags": 0, "id": "wasapi_input_capture" if system == "Windows"
                            else "coreaudio_input_capture", "muted": False,
                            "name": "Mic/Aux", "settings": {}, "volume": 1.0},
        "DesktopAudioDevice1": {"flags": 0, "id": "wasapi_output_capture" if system == "Windows"
                                else "coreaudio_output_capture", "muted": False,
                                "name": "Desktop Audio", "settings": {}, "volume": 1.0},
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
        "sources": [display_source, webcam_source, scene_source],
        "transition_duration": 300,
        "transitions": [],
        "version": 2,
    }


def collection_path(config_root: Path, collection_name: str = COLLECTION_NAME) -> Path:
    return config_root / "basic" / "scenes" / f"{collection_name}.json"


def collection_exists(config_root: Path, collection_name: str = COLLECTION_NAME) -> bool:
    return collection_path(config_root, collection_name).exists()


def write_scene_collection(config_root: Path, force: bool = False) -> Path:
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
    data = build_scene_collection()

    with open(dest, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)

    return dest
