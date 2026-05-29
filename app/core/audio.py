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


def build_sox_command(scale, preset, buffer_size, input_device="default"):
    """Build the ``sox`` command (as an argument list) for a preset.

    ``scale`` is the pitch slider value, ``preset`` a :class:`Preset`,
    ``buffer_size`` the SoX buffer size (higher = better quality, more latency)
    and ``input_device`` the PulseAudio/PipeWire source to capture from.
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

    # Tremolo (robotic wobble): tremolo <speed Hz> <depth %>.
    if getattr(preset, "tremolo", None) is not None:
        command_effects += ["tremolo", str(preset.tremolo), "80"]

    # Reverb: reverb <reverberance 0-100>.
    if getattr(preset, "reverb", None) is not None:
        command_effects += ["reverb", str(preset.reverb)]

    # Echo: a fixed, pleasant single echo when enabled.
    if getattr(preset, "echo", False):
        command_effects += ["echo", "0.8", "0.9", "200", "0.3"]

    return [
        "sox",
        "--buffer", str(buffer_size),
        "-q",
        "-t", "pulseaudio", input_device,
        "-t", "pulseaudio", OUTPUT_SINK_NAME,
    ] + command_effects


def pick_input_source(configured, default_source, sources):
    """Choose which source SoX should capture from.

    ``configured`` is an explicit override from config (``""``/``"auto"`` means
    auto-detect). Otherwise prefer the system default source, as long as it's a
    real device (not a monitor and not one of Lyrebird's own virtual devices);
    failing that, the first real source; failing that, ``"default"``.
    """
    if configured and configured.lower() != "auto":
        return configured

    def is_real(name):
        return bool(name) and ".monitor" not in name and not name.startswith("Lyrebird")

    if is_real(default_source):
        return default_source
    for name in sources:
        if is_real(name):
            return name
    return default_source or "default"


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

    def run_sox(self, scale, preset, buffer_size=128, input_device=""):
        """Start the SoX effects process for the given preset and pitch.

        ``input_device`` is the configured capture source (``""``/``"auto"``
        auto-detects the system default microphone).
        """
        device = self.resolve_input_device(input_device)
        print(f"[info] Capturing from source: {device}")
        command = build_sox_command(scale, preset, buffer_size, device)
        self.sox_process = subprocess.Popen(command)

    def get_default_source(self):
        """Return the system default source name, or '' if it can't be read."""
        try:
            result = subprocess.run(
                ["pactl", "get-default-source"], capture_output=True, encoding="utf8")
            return result.stdout.strip()
        except OSError:
            return ""

    def get_sources(self):
        """Return the list of source names from ``pactl list short sources``."""
        try:
            result = subprocess.run(
                ["pactl", "list", "short", "sources"],
                capture_output=True, encoding="utf8")
        except OSError:
            return []
        names = []
        for line in result.stdout.split("\n"):
            fields = line.split("\t")
            if len(fields) >= 2 and fields[1]:
                names.append(fields[1])
        return names

    def resolve_input_device(self, configured=""):
        """Resolve the actual capture source, honouring a config override."""
        return pick_input_source(
            configured, self.get_default_source(), self.get_sources())

    def get_sink_name(self, attribute):
        if attribute[0] in ("sink_name", "source_name"):
            return attribute[1]
        return None

    def _is_monitor_loopback(self, module):
        """True if ``module`` is a Lyrebird monitoring loopback."""
        if module[1] != "module-loopback":
            return False
        return any(
            key == "source" and value == f"{OUTPUT_SINK_NAME}.monitor"
            for key, value in module[2]
        )

    def load_monitor(self):
        """Route the Lyrebird output to the default sink so the user can hear
        their own (effected) voice. Safe to call when already monitoring."""
        self.unload_monitor()
        subprocess.run(
            f'pactl load-module module-loopback source={OUTPUT_SINK_NAME}.monitor '
            'latency_msec=50'.split(' '),
            capture_output=True, encoding="utf8", check=True,
        )

    def unload_monitor(self):
        """Unload any Lyrebird monitoring loopback modules."""
        for module in self.get_pactl_modules():
            if len(module) < 3 or len(module[2]) < 1:
                continue
            if self._is_monitor_loopback(module):
                subprocess.run(["pactl", "unload-module", str(module[0])])

    def load_pa_modules(self):
        # capture_output keeps pactl's printed module index off the terminal.
        self.null_sink = subprocess.run(
            f'pactl load-module module-null-sink sink_name={OUTPUT_SINK_NAME} '
            'node.description="Lyrebird Output"'.split(' '),
            capture_output=True, encoding="utf8", check=True,
        ).stdout.strip()
        self.remap_sink = subprocess.run(
            f'pactl load-module module-remap-source source_name={INPUT_SOURCE_NAME} '
            f'master={OUTPUT_SINK_NAME}.monitor '
            'node.description="Lyrebird Virtual Input"'.split(' '),
            capture_output=True, encoding="utf8", check=True,
        ).stdout.strip()

    def get_pactl_modules(self):
        """Return parsed ``pactl list short`` modules (see ``parse_pactl_short``)."""
        pactl_list = subprocess.run(
            ["pactl", "list", "short"], capture_output=True, encoding="utf8"
        )
        return parse_pactl_short(pactl_list.stdout)

    def unload_pa_modules(self):
        """Unload only the Lyrebird-controlled modules (loopback, null sink, remap).

        Uses a single ``pactl list short`` scan to handle all three module types.
        """
        lyrebird_module_ids = []
        for module in self.get_pactl_modules():
            if len(module) < 3 or len(module[2]) < 1:
                continue

            module_type = module[1]
            if module_type == "module-null-sink":
                if self.get_sink_name(module[2][0]) == OUTPUT_SINK_NAME:
                    lyrebird_module_ids.append(module[0])
            elif module_type == "module-remap-source":
                if self.get_sink_name(module[2][0]) == INPUT_SOURCE_NAME:
                    lyrebird_module_ids.append(module[0])
            elif self._is_monitor_loopback(module):
                lyrebird_module_ids.append(module[0])

        for module_id in lyrebird_module_ids:
            subprocess.run(["pactl", "unload-module", str(module_id)])

