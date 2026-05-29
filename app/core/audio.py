"""Audio backend for Lyrebird.

Wraps the ``sox`` effects pipeline and the ``pactl`` virtual device
management. The command-building and parsing helpers are kept as pure
functions so they can be unit tested without a running audio server.
"""

import subprocess

# Names of the virtual devices Lyrebird creates. Kept as constants so the
# parsing/unloading logic and the device creation stay in sync.
OUTPUT_SINK_NAME = "Lyrebird-Output"
INPUT_SOURCE_NAME = "Lyrebird-Input"

# SoX scales the "pitch" effect in cents (100 cents per semitone). The slider
# uses a -10..10 range which is multiplied to reach a useful pitch range.
PITCH_MULTIPLIER = 100


def build_sox_command(scale, preset, buffer_size):
    """Build the ``sox`` command (as an argument list) for a preset.

    ``scale`` is the pitch slider value, ``preset`` a :class:`Preset` and
    ``buffer_size`` the SoX buffer size (higher = better quality, more latency).
    """
    command_effects = ["pitch", str(scale * PITCH_MULTIPLIER)]

    # Volume boosting. SoX remembers the last given volume between invocations,
    # so an explicit "0" is appended when no boost is requested to reset it.
    if preset.volume_boost is not None:
        command_effects += ["vol", str(preset.volume_boost) + "dB"]
    else:
        command_effects += ["vol", "0"]

    # Downsampling. A downsample of "1" (no-op) is appended for the same
    # reset reason as the volume above.
    if preset.downsample_amount is not None:
        command_effects += ["downsample", str(preset.downsample_amount)]
    else:
        command_effects += ["downsample", "1"]

    return [
        "sox",
        "--buffer", str(buffer_size),
        "-q",
        "-t", "pulseaudio", "default",
        "-t", "pulseaudio", OUTPUT_SINK_NAME,
    ] + command_effects


def parse_pactl_short(text):
    """Parse the output of ``pactl list short`` into structured tuples.

    Returns a list of ``(module_id, module_type, attributes)`` tuples where
    ``attributes`` is a list of ``(key, value)`` pairs. Designed for named
    modules; unrelated rows may be included.
    """
    data = []
    for line in text.split("\n"):
        info = line.split("\t")
        if len(info) <= 2:
            continue

        if info[2] and len(info[2]) > 0:
            key_values = [tuple(kv.split("=", 1)) for kv in info[2].split(" ")]
            data.append((info[0], info[1], key_values))
        else:
            data.append((info[0], info[1], []))
    return data


class Audio:
    def __init__(self):
        self.sox_process = None

    def kill_sox(self, timeout=1):
        if self.sox_process is not None:
            self.sox_process.terminate()
            try:
                self.sox_process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                self.sox_process.kill()
                self.sox_process.wait(timeout=timeout)
            self.sox_process = None

    def run_sox(self, scale, preset, buffer_size=128):
        """Start the SoX effects process for the given preset and pitch."""
        command = build_sox_command(scale, preset, buffer_size)
        self.sox_process = subprocess.Popen(command)

    def get_sink_name(self, attribute):
        if attribute[0] in ("sink_name", "source_name"):
            return attribute[1]
        return None

    def load_monitor(self):
        """Route the Lyrebird output to the default sink so the user can hear
        their own (effected) voice. Safe to call when already monitoring."""
        self.unload_monitor()
        subprocess.check_call(
            f'pactl load-module module-loopback source={OUTPUT_SINK_NAME}.monitor '
            'latency_msec=50'.split(' ')
        )

    def unload_monitor(self):
        """Unload any Lyrebird monitoring loopback modules."""
        for module in self.get_pactl_modules():
            if len(module) < 3 or len(module[2]) < 1:
                continue
            if module[1] != "module-loopback":
                continue
            for key, value in module[2]:
                if key == "source" and value == f"{OUTPUT_SINK_NAME}.monitor":
                    subprocess.run(["pactl", "unload-module", str(module[0])])
                    break

    def load_pa_modules(self):
        self.null_sink = subprocess.check_call(
            f'pactl load-module module-null-sink sink_name={OUTPUT_SINK_NAME} '
            'node.description="Lyrebird Output"'.split(' ')
        )
        self.remap_sink = subprocess.check_call(
            f'pactl load-module module-remap-source source_name={INPUT_SOURCE_NAME} '
            f'master={OUTPUT_SINK_NAME}.monitor '
            'node.description="Lyrebird Virtual Input"'.split(' ')
        )

    def get_pactl_modules(self):
        """Return parsed ``pactl list short`` modules (see ``parse_pactl_short``)."""
        pactl_list = subprocess.run(
            ["pactl", "list", "short"], capture_output=True, encoding="utf8"
        )
        return parse_pactl_short(pactl_list.stdout)

    def unload_pa_modules(self):
        """Unload only the Lyrebird-controlled modules (loopback, null sink, remap)."""
        self.unload_monitor()
        modules = self.get_pactl_modules()
        lyrebird_module_ids = []
        for module in modules:
            if len(module) < 3:
                continue
            if len(module[2]) < 1:
                continue

            if module[1] == "module-null-sink":
                sink_name = self.get_sink_name(module[2][0])
                if sink_name == OUTPUT_SINK_NAME:
                    lyrebird_module_ids.append(module[0])
            elif module[1] == "module-remap-source":
                sink_name = self.get_sink_name(module[2][0])
                if sink_name == INPUT_SOURCE_NAME:
                    lyrebird_module_ids.append(module[0])

        for module_id in lyrebird_module_ids:
            subprocess.run(["pactl", "unload-module", str(module_id)])
