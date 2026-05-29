from app.core.audio import build_sox_command, parse_pactl_short, PITCH_MULTIPLIER
from app.core.presets import Preset


def test_build_sox_command_pitch_only():
    preset = Preset("Man", pitch_value=-1.5)
    cmd = build_sox_command(-1.5, preset, 128)

    assert cmd[0] == "sox"
    assert "--buffer" in cmd
    assert cmd[cmd.index("--buffer") + 1] == "128"
    # Pitch is scaled by the multiplier (cents).
    assert "pitch" in cmd
    assert cmd[cmd.index("pitch") + 1] == str(-1.5 * PITCH_MULTIPLIER)
    # No boost / downsample -> reset no-ops appended.
    assert cmd[cmd.index("vol") + 1] == "0"
    assert cmd[cmd.index("downsample") + 1] == "1"


def test_build_sox_command_with_effects():
    preset = Preset("Bad Mic", downsample_amount=8, volume_boost=6)
    cmd = build_sox_command(0, preset, 64)

    assert cmd[cmd.index("--buffer") + 1] == "64"
    assert cmd[cmd.index("vol") + 1] == "6dB"
    assert cmd[cmd.index("downsample") + 1] == "8"


def test_build_sox_command_honors_buffer_size():
    # Regression: the buffer size used to be hardcoded to 17.
    preset = Preset("Off", pitch_value=0.0)
    cmd = build_sox_command(0, preset, 256)
    assert cmd[cmd.index("--buffer") + 1] == "256"


def test_build_sox_command_with_new_effects():
    preset = Preset("Spooky", pitch_value=0.0, reverb=90, echo=True, tremolo=20.0)
    cmd = build_sox_command(0, preset, 128)
    assert "tremolo" in cmd
    assert cmd[cmd.index("tremolo") + 1] == "20.0"
    assert "reverb" in cmd
    assert cmd[cmd.index("reverb") + 1] == "90"
    assert "echo" in cmd


def test_build_sox_command_omits_unset_new_effects():
    preset = Preset("Plain", pitch_value=0.0)
    cmd = build_sox_command(0, preset, 128)
    assert "tremolo" not in cmd
    assert "reverb" not in cmd
    assert "echo" not in cmd


def test_parse_pactl_short():
    text = (
        "30\tmodule-null-sink\tsink_name=Lyrebird-Output node.description=Lyrebird\n"
        "31\tmodule-remap-source\tsource_name=Lyrebird-Input master=Lyrebird-Output.monitor\n"
        "32\tmodule-something\t\n"
    )
    parsed = parse_pactl_short(text)

    assert parsed[0][0] == "30"
    assert parsed[0][1] == "module-null-sink"
    assert ("sink_name", "Lyrebird-Output") in parsed[0][2]
    assert parsed[1][1] == "module-remap-source"
    assert ("master", "Lyrebird-Output.monitor") in parsed[1][2]
    # Row with no attributes still parses with an empty attribute list.
    assert parsed[2][2] == []


def test_parse_pactl_short_ignores_short_lines():
    assert parse_pactl_short("") == []
    assert parse_pactl_short("garbage line\n") == []
