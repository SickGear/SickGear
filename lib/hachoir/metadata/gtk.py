import sys
import os

from gi.repository import Gtk

from hachoir.parser import createParser
from hachoir.metadata import extractMetadata


class MetadataGtk:

    def __init__(self):
        self.main_window = Gtk.Window()
        self.main_window.set_border_width(5)
        self.main_window.connect("destroy", self._destroy)

        self.main_vbox = Gtk.VBox()

        self.select_hbox = Gtk.HBox()
        self.select_button = Gtk.Button("Select")
        self.select_button.connect("clicked", self._select_clicked)
        self.select_hbox.pack_start(self.select_button, False, True, 0)
        self.file_combo = Gtk.ComboBoxText()
        self.file_combo.connect("changed", self._file_combo_changed)
        self.select_hbox.pack_start(self.file_combo, True, True, 0)
        self.main_vbox.pack_start(self.select_hbox, False, True, 0)

        self.metadata_table = Gtk.Table(1, 1)
        self.metadata_table.attach(
            Gtk.Label("Select a file to view metadata information..."), 0, 1, 0, 1)
        self.main_vbox.pack_start(self.metadata_table, True, True, 0)

        self.main_window.add(self.main_vbox)
        self.main_window.show_all()

    def add_file(self, filename):
        self.file_combo.append_text(filename)

    def _select_clicked(self, widget):
        file_chooser = Gtk.FileChooserDialog("Ouvrir..", None,
                                             Gtk.FILE_CHOOSER_ACTION_OPEN,
                                             (Gtk.STOCK_CANCEL, Gtk.RESPONSE_CANCEL,
                                              Gtk.STOCK_OPEN, Gtk.RESPONSE_OK))
        file_chooser.set_default_response(Gtk.RESPONSE_OK)
        file_chooser.show()

        reponse = file_chooser.run()
        if reponse == Gtk.RESPONSE_OK:
            selected_file = file_chooser.get_filename()
            self.add_file(selected_file)
        file_chooser.destroy()

    def _file_combo_changed(self, widget):
        self.main_vbox.remove(self.metadata_table)

        filename = self.file_combo.get_active_text()
        parser = createParser(filename)
        metadata = extractMetadata(parser)

        self.metadata_table = Gtk.Table(1, 2)
        self.main_vbox.pack_start(self.metadata_table, True, True, 0)

        if metadata is None:
            self.metadata_table.attach(
                Gtk.Label("Unknown file format"), 0, 1, 0, 1)
        else:
            total = 1
            for data in sorted(metadata):
                if not data.values:
                    continue
                title = data.description
                for item in data.values:
                    self.metadata_table.resize(total, 2)
                    value = item.text
                    self.metadata_table.attach(
                        Gtk.Label(title + ":"), 0, 1, total - 1, total)
                    self.metadata_table.attach(
                        Gtk.Label(value), 1, 2, total - 1, total)
                    total += 1
        self.metadata_table.show_all()

    def _destroy(self, widget, data=None):
        Gtk.main_quit()

    def main(self):
        has_file = False
        for arg in sys.argv[1:]:
            if os.path.isdir(arg):
                for file in os.listdir(arg):
                    path = os.path.join(arg, file)
                    if os.path.isfile(path):
                        self.add_file(path)
                        has_file = True
            elif os.path.isfile(arg):
                self.add_file(arg)
                has_file = True
        if has_file:
            self.file_combo.set_active(0)
        Gtk.main()
