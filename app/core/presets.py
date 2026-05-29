import toml

import app.core.config as config


def key_or_default(key, dict, default):
    return dict[key] if key in dict else default


class Preset:
    def __init__(self,
                name,
                pitch_value=None,
                downsample_amount=None,
                volume_boost=None,
                reverb=None,
                echo=False,
                tremolo=None):
        self.name = name
        self.pitch_value = pitch_value
        self.downsample_amount = downsample_amount
        self.volume_boost = volume_boost
        # Reverberance 0-100 (SoX `reverb`). None disables.
        self.reverb = reverb
        # Simple echo effect (SoX `echo`). Boolean toggle.
        self.echo = echo
        # Tremolo speed in Hz (SoX `tremolo`), gives a robotic/wobble effect.
        self.tremolo = tremolo

    def matches(self, y):
        return (self.name == y.name
                and self.pitch_value == y.pitch_value
                and self.downsample_amount == y.downsample_amount
                and self.volume_boost == y.volume_boost
                and self.reverb == y.reverb
                and bool(self.echo) == bool(y.echo)
                and self.tremolo == y.tremolo)

    def dictionary(self):
        dictionary = { "name": self.name }
        if self.pitch_value is not None:
            dictionary["pitch_value"] = self.pitch_value
        if self.downsample_amount is not None:
            dictionary["downsample_amount"] = self.downsample_amount
        if self.volume_boost is not None:
            dictionary["volume_boost"] = self.volume_boost
        if self.reverb is not None:
            dictionary["reverb"] = self.reverb
        if self.echo:
            dictionary["echo"] = True
        if self.tremolo is not None:
            dictionary["tremolo"] = self.tremolo
        return dictionary

DEFAULT_PRESETS = [
    Preset("Man", -1.5, None, None),
    Preset("Woman", 2.5, None, None),
    Preset("Boy", 1.25, None, None),
    Preset("Girl", 2.8, None, None),
    Preset("Darth Vader", -6.0, None, None),
    Preset("Chipmunk", 10.0, None, None),
    Preset("Bad Mic", None, 8, 0),
    Preset("Radio", None, 6, 0),
    Preset("Megaphone", None, 2, 0),
    Preset("Robot", 0.0, tremolo=30.0),
    Preset("Cathedral", -1.0, reverb=90),
    Preset("Echo", 0.0, echo=True),
    Preset("Off", 0.0, None, None)
]

LEGACY_PRESETS = [
    Preset("Man", -1.5, None, None),
    Preset("Woman", 2.5, None, None),
    Preset("Boy", 1.25, None, None),
    Preset("Girl", 2.8, None, None),
    Preset("Darth Vader", -6.0, None, None),
    Preset("Chipmunk", 10.0, None, None),
    Preset("Russian Mic", None, 8, 8),
    Preset("Radio", None, 6, 5),
    Preset("Megaphone", None, 2, 8),
    Preset("Custom", None, None, None)
]

PRESETS_TOML_HEADER='''# Effect presets are defined in presets.toml
# The following parameters are available for presets

# name: Preset name, will be displayed in the GUI
# pitch_value: The pitch value of the preset, float value between -10.0 to 10.0. Omit if pitch value should not be affected from slider value.
# downsample_amount Downsample by an integer factor.
# volume_boost: Amount in dB to boost the audio. Can be negative to make the audio quieter.
# reverb: Reverberance amount, integer between 0 and 100.
# echo: Add a simple echo effect, true or false.
# tremolo: Tremolo/wobble speed in Hz (float), gives a robotic effect.

# e.g.
# [[presets]]
# name = "Bad Mic"
# pitch_value = -1.5
# downsample_amount = 8
# volume_boost = 8
# reverb = 60
# echo = true
# tremolo = 20.0
'''

# Names reserved by the built-in presets. Used by the GUI editor so it only
# manages user-created presets.
DEFAULT_PRESET_NAMES = {preset.name for preset in DEFAULT_PRESETS}

def load_presets():
    '''
    Loads presets from ~/.config/lyrebird/presets.toml and returns
    a list of `Preset` objects from the file
    '''

    # create_presets()
    presets = []
    failed = []

    path = config.presets_path

    if not config.presets_path.exists():
        create_presets()
        return { "presets": [], "failed": [] }

    with open(path, 'r') as f:
        presets_data = toml.loads(f.read())['presets']
        for item in presets_data:
            # name
            if "name" not in item:
                print("[error] Preset missing name, skipping")
                continue
            name = item["name"]
            # pitch value
            pitch_value = None
            if "pitch_value" in item and item["pitch_value"] != "scale":
                try:
                    pitch_value = float(item["pitch_value"])
                    pitch_value = min(max(pitch_value, -10), 10)
                except ValueError:
                    failed.append(name)
                    print(f"[error] Preset '{name}' failed to load: invalid pitch value '{item['pitch_value']}'")
                    continue
            # downsample
            downsample_amount = None
            if "downsample_amount" in item and item["downsample_amount"] != "none":
                try:
                    downsample_amount = int(item["downsample_amount"])
                except ValueError:
                    failed.append(name)
                    print(f"[error] Preset '{name}' failed to load: invalid downsample value '{item['downsample_amount']}'")
                    continue
            # volume boost
            volume_boost = None
            if "volume_boost" in item:
                if item["volume_boost"] != "none":
                    try:
                        volume_boost = int(item["volume_boost"])
                    except ValueError:
                        failed.append(name)
                        print(f"[error] Preset '{name}' failed to load: invalid volume boost value '{item['volume_boost']}'")
                        continue
            # reverb (0-100)
            reverb = None
            if "reverb" in item and item["reverb"] != "none":
                try:
                    reverb = min(max(int(item["reverb"]), 0), 100)
                except ValueError:
                    failed.append(name)
                    print(f"[error] Preset '{name}' failed to load: invalid reverb value '{item['reverb']}'")
                    continue
            # echo (boolean)
            echo = bool(item.get("echo", False))
            # tremolo (speed in Hz)
            tremolo = None
            if "tremolo" in item and item["tremolo"] != "none":
                try:
                    tremolo = float(item["tremolo"])
                except ValueError:
                    failed.append(name)
                    print(f"[error] Preset '{name}' failed to load: invalid tremolo value '{item['tremolo']}'")
                    continue
            preset = Preset(name=name,
                pitch_value=pitch_value,
                downsample_amount=downsample_amount,
                volume_boost=volume_boost,
                reverb=reverb,
                echo=echo,
                tremolo=tremolo)
            presets.append(preset)

    custom_presets = []
    contains_legacy = False
    for preset in presets:
        legacy_match = False
        for legacy_preset in LEGACY_PRESETS:
            legacy_match = legacy_preset.matches(preset)
            if legacy_match:
                break
        if not legacy_match:
            custom_presets.append(preset)
        else:
            contains_legacy = True

    if contains_legacy:
        print(f"[info] Config file ({path}) contains legacy presets, writing new file with {len(custom_presets)} custom preset(s)")
        create_presets(custom_presets)

    return { "presets": custom_presets, "failed": failed }

def create_presets(presets=[]):
    config.create_config_dir()

    if config.presets_path.exists():
        old_file_data = None
        with open(config.presets_path, "r") as f:
            old_file_data = f.read()
        with open(config.presets_old_path, "w") as f:
            f.write(old_file_data)

    with open(config.presets_path, "w") as f:
        f.write(PRESETS_TOML_HEADER + "\n")

        presets = map(lambda x: x.dictionary(), presets)
        presets = list(presets)
        toml_data = toml.dumps({ "presets": presets })
        f.write(toml_data)


def load_custom_presets():
    '''Return only the user's custom presets currently saved on disk.'''
    return load_presets()["presets"]


def validate_preset_fields(name, pitch_value, downsample_amount, volume_boost,
                           reverb=None, echo=False, tremolo=None):
    '''
    Validate raw preset field values (as provided by the GUI editor).

    Returns ``(preset, error)`` where exactly one is ``None``. Numeric effect
    fields may be ``None``/blank to leave the corresponding effect unset.
    '''
    name = (name or "").strip()
    if not name:
        return None, "Preset name cannot be empty."
    if name in DEFAULT_PRESET_NAMES:
        return None, f"'{name}' is a reserved built-in preset name."

    parsed_pitch = None
    if pitch_value is not None and pitch_value != "":
        try:
            parsed_pitch = min(max(float(pitch_value), -10.0), 10.0)
        except (TypeError, ValueError):
            return None, "Pitch must be a number between -10 and 10."

    parsed_downsample = None
    if downsample_amount is not None and downsample_amount != "":
        try:
            parsed_downsample = int(downsample_amount)
        except (TypeError, ValueError):
            return None, "Downsample must be a whole number."
        if parsed_downsample < 1:
            return None, "Downsample must be 1 or greater."

    parsed_volume = None
    if volume_boost is not None and volume_boost != "":
        try:
            parsed_volume = int(volume_boost)
        except (TypeError, ValueError):
            return None, "Volume boost must be a whole number (dB)."

    parsed_reverb = None
    if reverb is not None and reverb != "":
        try:
            parsed_reverb = int(reverb)
        except (TypeError, ValueError):
            return None, "Reverb must be a whole number between 0 and 100."
        if not 0 <= parsed_reverb <= 100:
            return None, "Reverb must be between 0 and 100."

    parsed_tremolo = None
    if tremolo is not None and tremolo != "":
        try:
            parsed_tremolo = float(tremolo)
        except (TypeError, ValueError):
            return None, "Tremolo speed must be a number (Hz)."
        if parsed_tremolo <= 0:
            return None, "Tremolo speed must be greater than 0."

    preset = Preset(name, parsed_pitch, parsed_downsample, parsed_volume,
                    reverb=parsed_reverb, echo=bool(echo), tremolo=parsed_tremolo)
    return preset, None


def add_custom_preset(preset):
    '''Append a custom preset and persist all custom presets to disk.'''
    custom = load_custom_presets()
    custom = [p for p in custom if p.name != preset.name]
    custom.append(preset)
    create_presets(custom)
    return custom


def delete_custom_preset(name):
    '''Remove a custom preset by name and persist the remainder.'''
    custom = [p for p in load_custom_presets() if p.name != name]
    create_presets(custom)
    return custom
