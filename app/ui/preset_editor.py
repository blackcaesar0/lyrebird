"""GUI dialog for managing custom Lyrebird presets.

Lets the user add and remove their own presets, which are persisted to
``~/.config/lyrebird/presets.toml``. Built-in presets are listed for reference
but cannot be edited or removed.
"""

from gi.repository import Gtk

import app.core.presets as presets


class PresetEditor(Gtk.Dialog):
    def __init__(self, parent):
        super().__init__(title="Manage Presets", transient_for=parent)
        self.set_default_size(420, 460)
        self.add_button("Close", Gtk.ResponseType.CLOSE)

        box = self.get_content_area()
        box.set_spacing(8)
        box.set_border_width(10)

        # --- Existing custom presets list ---
        heading = Gtk.Label()
        heading.set_markup("<b>Your custom presets</b>")
        heading.set_halign(Gtk.Align.START)
        box.pack_start(heading, False, False, 0)

        self.list_box = Gtk.ListBox()
        self.list_box.set_selection_mode(Gtk.SelectionMode.NONE)
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scrolled.set_min_content_height(160)
        scrolled.add(self.list_box)
        box.pack_start(scrolled, True, True, 0)

        # --- New preset form ---
        form_heading = Gtk.Label()
        form_heading.set_markup("<b>Add a preset</b>")
        form_heading.set_halign(Gtk.Align.START)
        box.pack_start(form_heading, False, False, 0)

        grid = Gtk.Grid(column_spacing=8, row_spacing=6)

        self.name_entry = Gtk.Entry()
        self.name_entry.set_hexpand(True)
        self.pitch_entry = Gtk.Entry()
        self.pitch_entry.set_placeholder_text("optional, -10 to 10")
        self.downsample_entry = Gtk.Entry()
        self.downsample_entry.set_placeholder_text("optional, integer >= 1")
        self.volume_entry = Gtk.Entry()
        self.volume_entry.set_placeholder_text("optional, dB")

        rows = [
            ("Name", self.name_entry),
            ("Pitch", self.pitch_entry),
            ("Downsample", self.downsample_entry),
            ("Volume boost", self.volume_entry),
        ]
        for i, (label_text, widget) in enumerate(rows):
            label = Gtk.Label(label=label_text)
            label.set_halign(Gtk.Align.START)
            grid.attach(label, 0, i, 1, 1)
            grid.attach(widget, 1, i, 1, 1)
        box.pack_start(grid, False, False, 0)

        add_btn = Gtk.Button(label="Add Preset")
        add_btn.connect("clicked", self.on_add_clicked)
        box.pack_start(add_btn, False, False, 0)

        self.refresh_list()
        self.show_all()

    def refresh_list(self):
        for child in self.list_box.get_children():
            self.list_box.remove(child)

        try:
            custom = presets.load_custom_presets()
        except Exception as e:
            print(f"[error] Failed to load custom presets for editor: {e}")
            custom = []

        if not custom:
            empty = Gtk.Label(label="No custom presets yet.")
            empty.set_halign(Gtk.Align.START)
            empty.set_margin_top(6)
            empty.set_margin_bottom(6)
            self.list_box.add(empty)
        else:
            for preset in custom:
                self.list_box.add(self._build_row(preset))

        self.list_box.show_all()

    def _build_row(self, preset):
        row = Gtk.ListBoxRow()
        hbox = Gtk.HBox(spacing=6)
        hbox.set_margin_top(4)
        hbox.set_margin_bottom(4)

        label = Gtk.Label(label=self._describe(preset))
        label.set_halign(Gtk.Align.START)
        hbox.pack_start(label, True, True, 0)

        delete_btn = Gtk.Button.new_from_icon_name("user-trash-symbolic", Gtk.IconSize.BUTTON)
        delete_btn.set_tooltip_text("Delete preset")
        delete_btn.connect("clicked", self.on_delete_clicked, preset.name)
        hbox.pack_end(delete_btn, False, False, 0)

        row.add(hbox)
        return row

    @staticmethod
    def _describe(preset):
        parts = []
        if preset.pitch_value is not None:
            parts.append(f"pitch {preset.pitch_value}")
        if preset.downsample_amount is not None:
            parts.append(f"downsample {preset.downsample_amount}")
        if preset.volume_boost is not None:
            parts.append(f"vol {preset.volume_boost}dB")
        detail = ", ".join(parts) if parts else "no effects"
        return f"{preset.name}  —  {detail}"

    def on_add_clicked(self, button):
        preset, error = presets.validate_preset_fields(
            self.name_entry.get_text(),
            self.pitch_entry.get_text() or None,
            self.downsample_entry.get_text() or None,
            self.volume_entry.get_text() or None,
        )
        if error is not None:
            self._error_dialog(error)
            return

        try:
            presets.add_custom_preset(preset)
        except Exception as e:
            self._error_dialog(f"Failed to save preset: {e}")
            return

        # Clear the form and refresh.
        for entry in (self.name_entry, self.pitch_entry,
                      self.downsample_entry, self.volume_entry):
            entry.set_text("")
        self.refresh_list()

    def on_delete_clicked(self, button, name):
        try:
            presets.delete_custom_preset(name)
        except Exception as e:
            self._error_dialog(f"Failed to delete preset: {e}")
            return
        self.refresh_list()

    def _error_dialog(self, message):
        dialog = Gtk.MessageDialog(
            transient_for=self,
            message_type=Gtk.MessageType.ERROR,
            buttons=Gtk.ButtonsType.OK,
            text=message)
        dialog.run()
        dialog.destroy()
