"""Configuration and session persistence for Lyrebird.

``config.toml``  - user editable settings (buffer size, ...).
``session.toml`` - machine written state remembering the last used preset and
                   pitch so they can be restored on the next launch.
"""

import toml

from dataclasses import dataclass
from pathlib import Path

DEFAULT_BUFFER_SIZE = 128


@dataclass
class Configuration:
    buffer_size: int = DEFAULT_BUFFER_SIZE
    # Restore the last used preset/pitch when Lyrebird starts.
    remember_last_preset: bool = True
    # PulseAudio/PipeWire source to capture from. "" or "auto" auto-detects the
    # system default microphone (recommended). Set a specific source name to
    # override (see `pactl list short sources`).
    input_device: str = ""


@dataclass
class Session:
    """Last-used UI state, persisted between runs."""
    last_preset: str = None
    last_pitch: float = 0.0


config_dir = Path(Path.home() / ".config" / "lyrebird")
config_path = Path(config_dir / "config.toml")
presets_path = Path(config_dir / "presets.toml")
presets_old_path = Path(config_dir / "presets.toml.old")
session_path = Path(config_dir / "session.toml")


def _as_bool(value, default):
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes", "on")
    return default


def load_config():
    """Load ``config.toml`` and return a :class:`Configuration`.

    Missing or partially malformed values fall back to defaults rather than
    raising, so a stray edit can't prevent the app from starting.
    """
    create_config()

    with open(config_path, 'r') as f:
        parsed = toml.loads(f.read())

    sections = parsed.get('config', [])
    config = sections[0] if sections else {}

    try:
        buffer_size = int(config.get('buffer_size', DEFAULT_BUFFER_SIZE))
    except (TypeError, ValueError):
        print("[warning] Invalid buffer_size in config.toml, using default")
        buffer_size = DEFAULT_BUFFER_SIZE

    remember = _as_bool(config.get('remember_last_preset', True), True)
    input_device = str(config.get('input_device', '') or '')

    return Configuration(buffer_size=buffer_size, remember_last_preset=remember,
                         input_device=input_device)


def create_config_dir():
    config_dir.mkdir(parents=True, exist_ok=True)


CONFIG_CONTENTS = '''
# Configuration file for Lyrebird
# The following parameters are configurable
# buffer_size = The buffer size to use for sox. Higher = better quality, at
# the cost of higher latency. Default value is 128
# remember_last_preset = Restore the last used preset and pitch on launch.
# input_device = Source to capture from. Leave blank (or "auto") to use the
#   system default microphone. To override, set a source name from
#   `pactl list short sources`.
[[config]]
buffer_size = 128
remember_last_preset = true
input_device = ""
'''


def create_config():
    create_config_dir()
    if not config_path.exists():
        with open(config_path, 'w') as f:
            f.write(CONFIG_CONTENTS)


def load_session():
    """Load the persisted session state, returning defaults if absent/invalid."""
    if not session_path.exists():
        return Session()
    try:
        with open(session_path, 'r') as f:
            data = toml.loads(f.read()).get('session', {})
        last_preset = data.get('last_preset') or None
        try:
            last_pitch = float(data.get('last_pitch', 0.0))
        except (TypeError, ValueError):
            last_pitch = 0.0
        return Session(last_preset=last_preset, last_pitch=last_pitch)
    except Exception as e:
        print(f"[warning] Failed to read session.toml: {e}")
        return Session()


def save_session(session):
    """Persist the given :class:`Session` to ``session.toml``."""
    create_config_dir()
    data = {'session': {'last_pitch': session.last_pitch}}
    if session.last_preset is not None:
        data['session']['last_preset'] = session.last_preset
    try:
        with open(session_path, 'w') as f:
            f.write(toml.dumps(data))
    except Exception as e:
        print(f"[warning] Failed to write session.toml: {e}")
