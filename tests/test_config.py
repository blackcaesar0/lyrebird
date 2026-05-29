import pytest

import app.core.config as config
from app.core.config import Configuration, Session


@pytest.fixture
def temp_config(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "config_dir", tmp_path)
    monkeypatch.setattr(config, "config_path", tmp_path / "config.toml")
    monkeypatch.setattr(config, "session_path", tmp_path / "session.toml")
    return tmp_path


def test_load_config_creates_default(temp_config):
    cfg = config.load_config()
    assert isinstance(cfg, Configuration)
    assert cfg.buffer_size == config.DEFAULT_BUFFER_SIZE
    assert cfg.remember_last_preset is True
    assert config.config_path.exists()


def test_load_config_reads_values(temp_config):
    config.config_path.write_text(
        "[[config]]\nbuffer_size = 64\nremember_last_preset = false\n")
    cfg = config.load_config()
    assert cfg.buffer_size == 64
    assert cfg.remember_last_preset is False


def test_load_config_bad_buffer_falls_back(temp_config):
    config.config_path.write_text('[[config]]\nbuffer_size = "huge"\n')
    cfg = config.load_config()
    assert cfg.buffer_size == config.DEFAULT_BUFFER_SIZE


def test_load_config_empty_section(temp_config):
    config.config_path.write_text("# nothing here\n")
    cfg = config.load_config()
    assert cfg.buffer_size == config.DEFAULT_BUFFER_SIZE


def test_session_roundtrip(temp_config):
    session = Session(last_preset="Woman", last_pitch=2.5)
    config.save_session(session)
    assert config.session_path.exists()

    loaded = config.load_session()
    assert loaded.last_preset == "Woman"
    assert loaded.last_pitch == 2.5


def test_load_session_missing_returns_default(temp_config):
    loaded = config.load_session()
    assert loaded.last_preset is None
    assert loaded.last_pitch == 0.0


def test_save_session_without_preset(temp_config):
    config.save_session(Session(last_preset=None, last_pitch=1.0))
    loaded = config.load_session()
    assert loaded.last_preset is None
    assert loaded.last_pitch == 1.0
