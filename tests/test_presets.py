import pytest

import app.core.config as config
import app.core.presets as presets
from app.core.presets import Preset


@pytest.fixture
def temp_config(tmp_path, monkeypatch):
    """Redirect config/preset paths to a temporary directory."""
    monkeypatch.setattr(config, "config_dir", tmp_path)
    monkeypatch.setattr(config, "config_path", tmp_path / "config.toml")
    monkeypatch.setattr(config, "presets_path", tmp_path / "presets.toml")
    monkeypatch.setattr(config, "presets_old_path", tmp_path / "presets.toml.old")
    monkeypatch.setattr(config, "session_path", tmp_path / "session.toml")
    return tmp_path


def test_preset_dictionary_omits_none():
    preset = Preset("Test", pitch_value=2.0)
    d = preset.dictionary()
    assert d == {"name": "Test", "pitch_value": 2.0}


def test_preset_matches():
    a = Preset("Man", -1.5, None, None)
    b = Preset("Man", -1.5, None, None)
    c = Preset("Man", -2.0, None, None)
    assert a.matches(b)
    assert not a.matches(c)


def test_validate_preset_fields_valid():
    preset, error = presets.validate_preset_fields("Cool", "3.5", "4", "6")
    assert error is None
    assert preset.name == "Cool"
    assert preset.pitch_value == 3.5
    assert preset.downsample_amount == 4
    assert preset.volume_boost == 6


def test_validate_preset_fields_optional_blank():
    preset, error = presets.validate_preset_fields("Cool", "", "", "")
    assert error is None
    assert preset.pitch_value is None
    assert preset.downsample_amount is None
    assert preset.volume_boost is None


def test_validate_preset_clamps_pitch():
    preset, error = presets.validate_preset_fields("Loud", "50", None, None)
    assert error is None
    assert preset.pitch_value == 10.0


def test_validate_preset_rejects_empty_name():
    preset, error = presets.validate_preset_fields("  ", None, None, None)
    assert preset is None
    assert "empty" in error.lower()


def test_validate_preset_rejects_reserved_name():
    preset, error = presets.validate_preset_fields("Man", None, None, None)
    assert preset is None
    assert "reserved" in error.lower()


def test_validate_preset_rejects_bad_pitch():
    preset, error = presets.validate_preset_fields("X", "abc", None, None)
    assert preset is None


def test_validate_preset_rejects_bad_downsample():
    preset, error = presets.validate_preset_fields("X", None, "0", None)
    assert preset is None


def test_add_and_delete_custom_preset(temp_config):
    preset, error = presets.validate_preset_fields("MyVoice", "1.0", None, None)
    assert error is None

    presets.add_custom_preset(preset)
    loaded = presets.load_custom_presets()
    assert any(p.name == "MyVoice" for p in loaded)

    presets.delete_custom_preset("MyVoice")
    loaded = presets.load_custom_presets()
    assert not any(p.name == "MyVoice" for p in loaded)


def test_add_custom_preset_replaces_same_name(temp_config):
    p1, _ = presets.validate_preset_fields("Dup", "1.0", None, None)
    p2, _ = presets.validate_preset_fields("Dup", "2.0", None, None)
    presets.add_custom_preset(p1)
    presets.add_custom_preset(p2)

    loaded = [p for p in presets.load_custom_presets() if p.name == "Dup"]
    assert len(loaded) == 1
    assert loaded[0].pitch_value == 2.0
