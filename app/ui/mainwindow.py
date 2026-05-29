#!/bin/python

from gi.repository import Gtk, GdkPixbuf, GLib

# Core imports
import app.core.presets as presets
import app.core.state as state
import app.core.config as config
import app.core.lock as lock
from app.core.version import VERSION_STRING
from app.core.resources import icon_path
from app.core.audio import Audio

from app.ui.alert import Alert
from app.ui.preset_editor import PresetEditor

OFF_PRESET_NAME = "Off"

# Debounce window (ms) for restarting SoX while the pitch slider is dragged.
# Without this, GTK's value-changed fires per pixel and spawns a new sox
# process for each tick, causing audio glitches and CPU churn.
RESTART_DEBOUNCE_MS = 150


class MainWindow(Gtk.Window):
    '''
    Main window for Lyrebird
    '''

    def __init__(self):
        Gtk.Window.__init__(self, title='Lyrebird')
        self.set_border_width(10)

        self.set_size_request(600, 500)
        self.set_default_size(600, 500)

        self.alert = Alert(self)

        # Pending debounced sox restart (GLib source id), see schedule_restart.
        self._restart_timeout_id = None

        headerbar = Gtk.HeaderBar()
        headerbar.set_show_close_button(True)
        headerbar.props.title = 'Lyrebird'

        about_btn = Gtk.Button.new_from_icon_name('help-about-symbolic', Gtk.IconSize.BUTTON)
        about_btn.connect('clicked', self.about_clicked)
        headerbar.pack_start(about_btn)

        self.edit_btn = Gtk.Button.new_from_icon_name('list-add-symbolic', Gtk.IconSize.BUTTON)
        self.edit_btn.set_tooltip_text('Manage custom presets')
        self.edit_btn.connect('clicked', self.manage_presets_clicked)
        headerbar.pack_end(self.edit_btn)

        self.set_wmclass('Lyrebird', 'Lyrebird')
        self.set_title('Lyrebird')
        self.set_titlebar(headerbar)

        # Set the icon (resolved relative to the package, not the cwd)
        try:
            self.set_icon_from_file(icon_path())
        except Exception as e:
            print(f"[warning] Failed to load window icon: {e}")

        # Create the lock file to ensure only one instance of Lyrebird is running at once
        lock_file = lock.place_lock()
        if lock_file is None:
            self.alert.show_error_markup(
                "Lyrebird Already Running",
                "Only one instance of Lyrebird can be ran at a time.")
            exit(1)
        else:
            self.lock_file = lock_file

        # Load the configuration file
        try:
            state.config = config.load_config()
        except BaseException as e:
            print(f"[error] Failed to load config file: {str(e)}")
            self.alert.show_warning(
                "Failed to Load Config File",
                "Lyrebird failed to load config, your config.toml file is most "
                "likely malformed. See the console for further details.\n\n"
                f"Config file location: {config.config_path}")
            # load with default options
            state.config = config.Configuration()

        # Load the persisted session (last used preset / pitch)
        try:
            state.session = config.load_session()
        except BaseException as e:
            print(f"[warning] Failed to load session: {str(e)}")
            state.session = config.Session()

        state.audio = Audio()

        # Unload the null sink module if there is one from last time.
        # The only reason there would be one already, is if the application was closed without
        # toggling the switch to off (aka a crash was experienced).
        state.audio.unload_pa_modules()

        self.reload_presets(initial=True)

        # Build the UI
        self.build_ui()

        # Restore the last used preset/pitch if enabled
        self.restore_session()

    def reload_presets(self, initial=False):
        '''Load built-in + custom presets into ``state.loaded_presets``.'''
        state.loaded_presets = list(presets.DEFAULT_PRESETS)
        try:
            load_presets_state = presets.load_presets()
            loaded_presets = load_presets_state["presets"]
            failed_presets = load_presets_state["failed"]

            state.loaded_presets += loaded_presets
            if initial and len(failed_presets) > 0:
                msg = ("The following presets failed to import: "
                       f"{', '.join(failed_presets)}. See the console for more details.")
                self.alert.show_warning("Failed to Import Presets", msg)
        except BaseException as e:
            print(f"[error] Failed to load custom presets: {str(e)}")
            if initial:
                self.alert.show_warning(
                    "Failed to Load Presets",
                    "Lyrebird failed to load custom presets, your presets.toml file "
                    "is most likely malformed. See the console for further details.\n\n"
                    f"Presets file location: {config.presets_path}")

    def build_ui(self):
        self.vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)

        # Toggle switch for Lyrebird
        self.hbox_toggle = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        self.toggle_label = Gtk.Label('Toggle Lyrebird')
        self.toggle_label.set_halign(Gtk.Align.START)

        self.toggle_switch = Gtk.Switch()
        self.toggle_switch.set_size_request(10, 25)
        self.toggle_switch.connect('notify::active', self.toggle_activated)
        self.hbox_toggle.pack_start(self.toggle_label, False, False, 0)
        self.hbox_toggle.pack_end(self.toggle_switch, False, False, 0)

        # Monitor (hear yourself) switch
        self.hbox_monitor = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        self.monitor_label = Gtk.Label('Monitor (hear yourself)')
        self.monitor_label.set_halign(Gtk.Align.START)

        self.monitor_switch = Gtk.Switch()
        self.monitor_switch.set_size_request(10, 25)
        self.monitor_switch.connect('notify::active', self.monitor_activated)
        self.hbox_monitor.pack_start(self.monitor_label, False, False, 0)
        self.hbox_monitor.pack_end(self.monitor_switch, False, False, 0)

        # Pitch shift scale
        self.hbox_pitch = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        self.pitch_label = Gtk.Label('Pitch Shift ')
        self.pitch_label.set_halign(Gtk.Align.START)

        self.pitch_adj = Gtk.Adjustment(0, -10, 10, 5, 10, 0)
        self.pitch_scale = Gtk.Scale(orientation=Gtk.Orientation.HORIZONTAL, adjustment=self.pitch_adj)
        self.pitch_scale.set_valign(Gtk.Align.CENTER)
        self.pitch_scale.connect('value-changed', self.pitch_scale_moved)

        self.hbox_pitch.pack_start(self.pitch_label, False, False, 0)
        self.hbox_pitch.pack_end(self.pitch_scale, True, True, 0)

        # Flow box containing the presets
        self.effects_label = Gtk.Label()
        self.effects_label.set_markup('<b>Presets</b>')
        self.effects_label.set_halign(Gtk.Align.START)

        self.flowbox = Gtk.FlowBox()
        self.flowbox.set_valign(Gtk.Align.START)
        self.flowbox.set_max_children_per_line(5)
        self.flowbox.set_selection_mode(Gtk.SelectionMode.NONE)

        # Create the flow box items
        self.preset_buttons = self.create_flowbox_items(self.flowbox)
        self.select_default_preset()

        self.vbox.pack_start(self.hbox_toggle, False, False, 5)
        self.vbox.pack_start(self.hbox_monitor, False, False, 5)
        self.vbox.pack_start(self.hbox_pitch, False, False, 5)
        self.vbox.pack_start(self.effects_label, False, False, 5)
        self.vbox.pack_end(self.flowbox, True, True, 0)

        self.add(self.vbox)

    def rebuild_flowbox(self):
        '''Recreate the preset buttons (after presets are added/removed).'''
        for child in self.flowbox.get_children():
            self.flowbox.remove(child)
        self.preset_buttons = self.create_flowbox_items(self.flowbox)
        self.select_default_preset()
        self.flowbox.show_all()

    def create_flowbox_items(self, flowbox):
        buttons = []
        for preset in state.loaded_presets:
            button = Gtk.Button()
            button.set_size_request(80, 80)
            buttons.append(button)

            button.set_label(preset.name)
            button.connect('clicked', self.preset_clicked)
            flowbox.add(button)
        return buttons

    def find_button(self, name):
        for button in self.preset_buttons:
            if button.props.label == name:
                return button
        return None

    def select_default_preset(self):
        '''Highlight the "Off" preset (or the first available) by default.'''
        button = self.find_button(OFF_PRESET_NAME)
        if button is None and self.preset_buttons:
            button = self.preset_buttons[-1]
        if button is not None:
            for preset_button in self.preset_buttons:
                preset_button.set_sensitive(True)
            button.set_sensitive(False)

    def restore_session(self):
        if not getattr(state.config, "remember_last_preset", True):
            return
        session = getattr(state, "session", None)
        if session is None:
            return

        if session.last_pitch is not None:
            self.pitch_scale.set_value(float(session.last_pitch))

        if session.last_preset:
            button = self.find_button(session.last_preset)
            if button is not None:
                self.activate_preset(session.last_preset, move_slider=False)

    # Event handlers
    def about_clicked(self, button):
        about = Gtk.AboutDialog()
        about.set_program_name('Lyrebird Voice Changer')
        about.set_version(VERSION_STRING)
        about.set_copyright('Copyright (c) 2020-2026 megabytesofrem, Harry Stanton & contributors')
        about.set_comments('Simple and powerful voice changer for Linux, written in Python & GTK.')
        try:
            about.set_logo(GdkPixbuf.Pixbuf.new_from_file(icon_path()))
        except Exception as e:
            print(f"[warning] Failed to load about logo: {e}")

        about.run()
        about.destroy()

    def manage_presets_clicked(self, button):
        editor = PresetEditor(self)
        editor.run()
        editor.destroy()
        # Presets may have changed; reload and rebuild the UI.
        self.reload_presets()
        self.rebuild_flowbox()

    def get_current_present(self):
        default_preset = self.get_preset_by_name(OFF_PRESET_NAME)
        return state.current_preset or default_preset

    def get_preset_by_name(self, name):
        for preset in state.loaded_presets:
            if preset.name == name:
                return preset
        return state.loaded_presets[-1] if state.loaded_presets else None

    def start_voice_changer(self):
        preset = self.get_current_present()
        pitch = self.pitch_scale.get_value()
        state.audio.run_sox(pitch, preset, state.config.buffer_size)

    def stop_voice_changer(self):
        state.audio.kill_sox()
        state.audio.unload_pa_modules()
        # Monitoring depends on the null sink existing, so reflect that it's off.
        if self.monitor_switch.get_active():
            self.monitor_switch.set_active(False)

    def toggle_activated(self, switch, gparam):
        if switch.get_active():
            # Load module-null-sink
            state.audio.load_pa_modules()

            # Kill the sox process
            state.audio.kill_sox()

            self.start_voice_changer()
        else:
            self.stop_voice_changer()

    def monitor_activated(self, switch, gparam):
        if switch.get_active():
            if not self.toggle_switch.get_active():
                # Monitoring needs Lyrebird's output device to exist first.
                self.alert.show_warning(
                    "Enable Lyrebird First",
                    "Turn Lyrebird on before enabling monitoring.")
                switch.set_active(False)
                return
            try:
                state.audio.load_monitor()
            except Exception as e:
                print(f"[error] Failed to enable monitoring: {e}")
                switch.set_active(False)
        else:
            state.audio.unload_monitor()

    def schedule_restart(self):
        """Restart SoX after a short quiet period.

        Coalesces the rapid ``value-changed`` events emitted while dragging the
        pitch slider (and a preset click that also moves the slider) into a
        single sox restart instead of one per event.
        """
        if not self.toggle_switch.get_active():
            return
        if self._restart_timeout_id is not None:
            GLib.source_remove(self._restart_timeout_id)
        self._restart_timeout_id = GLib.timeout_add(
            RESTART_DEBOUNCE_MS, self._restart_voice_changer)

    def _restart_voice_changer(self):
        self._restart_timeout_id = None
        state.audio.kill_sox()
        self.start_voice_changer()
        return False  # one-shot

    def pitch_scale_moved(self, event):
        self.schedule_restart()

    def preset_clicked(self, button):
        self.activate_preset(button.props.label)

    def activate_preset(self, name, move_slider=True):
        current_preset = self.get_preset_by_name(name)
        if current_preset is None:
            return
        state.current_preset = current_preset

        for preset_button in self.preset_buttons:
            preset_button.set_sensitive(True)
        button = self.find_button(name)
        if button is not None:
            button.set_sensitive(False)

        if move_slider and current_preset.pitch_value is not None:
            # Set the pitch of the slider (also triggers a debounced restart).
            self.pitch_scale.set_value(float(current_preset.pitch_value))

        self.schedule_restart()

    def save_session(self):
        try:
            current = state.current_preset.name if state.current_preset else None
            session = config.Session(
                last_preset=current,
                last_pitch=self.pitch_scale.get_value())
            config.save_session(session)
        except Exception as e:
            print(f"[warning] Failed to save session: {e}")

    def close(self, *args):
        self.save_session()

        # Cancel any pending debounced restart so it can't fire after teardown.
        if self._restart_timeout_id is not None:
            GLib.source_remove(self._restart_timeout_id)
            self._restart_timeout_id = None

        state.audio.kill_sox()
        state.audio.unload_pa_modules()

        self.lock_file.close()
        lock.destroy_lock()

        Gtk.main_quit()
