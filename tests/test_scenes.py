"""
Tests for obs_quickshare.scenes
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from obs_quickshare.scenes import (
    COLLECTION_NAME,
    SCENE_NAME,
    _display_capture_source,
    _scene_item,
    _webcam_source,
    build_scene_collection,
    collection_exists,
    collection_path,
    write_scene_collection,
)


# ---------------------------------------------------------------------------
# _display_capture_source
# ---------------------------------------------------------------------------

class TestDisplayCaptureSource:
    def test_darwin_uses_display_capture(self):
        src = _display_capture_source("Darwin")
        assert src["id"] == "display_capture"
        assert src["name"] == "Screen"
        assert isinstance(src["uuid"], str) and len(src["uuid"]) > 0

    def test_windows_uses_monitor_capture(self):
        src = _display_capture_source("Windows")
        assert src["id"] == "monitor_capture"

    def test_linux_uses_xshm(self):
        src = _display_capture_source("Linux")
        assert src["id"] == "xshm_input"

    def test_has_required_keys(self):
        src = _display_capture_source("Darwin")
        for key in ("id", "uuid", "name", "settings", "enabled", "filters"):
            assert key in src, f"Missing key: {key}"

    def test_filters_empty(self):
        src = _display_capture_source("Darwin")
        assert src["filters"] == []


# ---------------------------------------------------------------------------
# _webcam_source
# ---------------------------------------------------------------------------

class TestWebcamSource:
    def test_darwin_uses_av_capture(self):
        with patch("obs_quickshare.scenes.platform.system", return_value="Darwin"):
            src = _webcam_source()
        assert src["id"] == "av_capture_input_v2"
        assert src["name"] == "Webcam"

    def test_windows_uses_dshow(self):
        with patch("obs_quickshare.scenes.platform.system", return_value="Windows"):
            src = _webcam_source()
        assert src["id"] == "dshow_input"

    def test_linux_uses_v4l2(self):
        with patch("obs_quickshare.scenes.platform.system", return_value="Linux"):
            src = _webcam_source()
        assert src["id"] == "v4l2_input"

    def test_has_chroma_key_filter_disabled(self):
        with patch("obs_quickshare.scenes.platform.system", return_value="Darwin"):
            src = _webcam_source()
        assert len(src["filters"]) == 1
        filt = src["filters"][0]
        assert filt["id"] == "chroma_key_filter_v2"
        assert filt["enabled"] is False


# ---------------------------------------------------------------------------
# _scene_item
# ---------------------------------------------------------------------------

class TestSceneItem:
    def test_position_and_scale(self):
        fake_source = {"name": "Screen", "uuid": "abc-123"}
        item = _scene_item(fake_source, item_id=1, x=0.0, y=0.0, w=1920.0, h=1080.0)
        assert item["pos"] == {"x": 0.0, "y": 0.0}
        assert item["scale"] == {"x": 1.0, "y": 1.0}

    def test_pip_scale(self):
        fake_source = {"name": "Webcam", "uuid": "def-456"}
        item = _scene_item(fake_source, item_id=2, x=1580.0, y=880.0, w=320.0, h=180.0)
        assert abs(item["scale"]["x"] - 320.0 / 1920.0) < 1e-9
        assert abs(item["scale"]["y"] - 180.0 / 1080.0) < 1e-9
        assert item["id"] == 2
        assert item["source_uuid"] == "def-456"
        assert item["visible"] is True


# ---------------------------------------------------------------------------
# build_scene_collection
# ---------------------------------------------------------------------------

class TestBuildSceneCollection:
    def _build(self, system="Darwin"):
        with patch("obs_quickshare.scenes.platform.system", return_value=system):
            return build_scene_collection()

    def test_name(self):
        data = self._build()
        assert data["name"] == COLLECTION_NAME

    def test_current_scene(self):
        data = self._build()
        assert data["current_scene"] == SCENE_NAME
        assert data["current_program_scene"] == SCENE_NAME

    def test_version_2(self):
        data = self._build()
        assert data["version"] == 2

    def test_has_three_sources(self):
        # display, webcam, scene
        data = self._build()
        assert len(data["sources"]) == 3

    def test_scene_source_last(self):
        data = self._build()
        scene_src = data["sources"][-1]
        assert scene_src["id"] == "scene"
        assert scene_src["name"] == SCENE_NAME

    def test_scene_has_two_items(self):
        data = self._build()
        scene_src = data["sources"][-1]
        items = scene_src["settings"]["items"]
        assert len(items) == 2

    def test_screen_item_is_fullscreen(self):
        data = self._build()
        scene_src = data["sources"][-1]
        screen_item = scene_src["settings"]["items"][0]
        assert screen_item["scale"] == {"x": 1.0, "y": 1.0}
        assert screen_item["pos"] == {"x": 0.0, "y": 0.0}

    def test_webcam_item_is_pip(self):
        data = self._build()
        scene_src = data["sources"][-1]
        webcam_item = scene_src["settings"]["items"][1]
        # PiP is bottom-right, not full screen
        assert webcam_item["scale"]["x"] < 1.0
        assert webcam_item["pos"]["x"] > 0

    def test_audio_devices_present(self):
        data = self._build()
        assert "AuxAudioDevice1" in data
        assert "DesktopAudioDevice1" in data

    def test_windows_audio_uses_wasapi(self):
        data = self._build(system="Windows")
        assert data["AuxAudioDevice1"]["id"] == "wasapi_input_capture"
        assert data["DesktopAudioDevice1"]["id"] == "wasapi_output_capture"

    def test_darwin_audio_uses_coreaudio(self):
        data = self._build(system="Darwin")
        assert data["AuxAudioDevice1"]["id"] == "coreaudio_input_capture"
        assert data["DesktopAudioDevice1"]["id"] == "coreaudio_output_capture"

    def test_uuids_are_unique(self):
        data = self._build()
        uuids = [s["uuid"] for s in data["sources"]]
        assert len(uuids) == len(set(uuids))

    def test_serialisable_to_json(self):
        data = self._build()
        serialised = json.dumps(data)
        assert json.loads(serialised) == data


# ---------------------------------------------------------------------------
# collection_path / collection_exists / write_scene_collection
# ---------------------------------------------------------------------------

class TestCollectionPath:
    def test_path_structure(self, tmp_path):
        path = collection_path(tmp_path)
        assert path == tmp_path / "basic" / "scenes" / f"{COLLECTION_NAME}.json"

    def test_custom_name(self, tmp_path):
        path = collection_path(tmp_path, collection_name="MyCollection")
        assert path.name == "MyCollection.json"


class TestCollectionExists:
    def test_returns_false_when_missing(self, tmp_path):
        assert collection_exists(tmp_path) is False

    def test_returns_true_when_present(self, tmp_path):
        p = collection_path(tmp_path)
        p.parent.mkdir(parents=True)
        p.write_text("{}")
        assert collection_exists(tmp_path) is True


class TestWriteSceneCollection:
    def test_creates_valid_json(self, tmp_path):
        with patch("obs_quickshare.scenes.platform.system", return_value="Darwin"):
            dest = write_scene_collection(tmp_path)
        assert dest.exists()
        data = json.loads(dest.read_text())
        assert data["name"] == COLLECTION_NAME

    def test_raises_file_exists_error_without_force(self, tmp_path):
        with patch("obs_quickshare.scenes.platform.system", return_value="Darwin"):
            write_scene_collection(tmp_path)
            with pytest.raises(FileExistsError):
                write_scene_collection(tmp_path)

    def test_force_overwrites(self, tmp_path):
        with patch("obs_quickshare.scenes.platform.system", return_value="Darwin"):
            dest = write_scene_collection(tmp_path)
            dest.write_text('{"name": "OLD"}')  # corrupt it
            write_scene_collection(tmp_path, force=True)
        data = json.loads(dest.read_text())
        assert data["name"] == COLLECTION_NAME

    def test_creates_parent_dirs(self, tmp_path):
        obs_root = tmp_path / "obs-studio"
        with patch("obs_quickshare.scenes.platform.system", return_value="Darwin"):
            write_scene_collection(obs_root)
        assert (obs_root / "basic" / "scenes").is_dir()
