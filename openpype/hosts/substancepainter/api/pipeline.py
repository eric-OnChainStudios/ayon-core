# -*- coding: utf-8 -*-
"""Pipeline tools for OpenPype Gaffer integration."""
import os
import sys
import logging
from functools import partial

# Substance 3D Painter modules
import substance_painter.ui
import substance_painter.event
import substance_painter.export
import substance_painter.project
import substance_painter.textureset

from openpype.host import HostBase, IWorkfileHost, ILoadHost, IPublishHost

import pyblish.api

from openpype.pipeline import (
    register_creator_plugin_path,
    register_loader_plugin_path,
    AVALON_CONTAINER_ID
)
from openpype.lib import (
    register_event_callback,
    emit_event,
)
from openpype.pipeline.load import any_outdated_containers
from openpype.hosts.substancepainter import SUBSTANCE_HOST_DIR

log = logging.getLogger("openpype.hosts.substance")

PLUGINS_DIR = os.path.join(SUBSTANCE_HOST_DIR, "plugins")
PUBLISH_PATH = os.path.join(PLUGINS_DIR, "publish")
LOAD_PATH = os.path.join(PLUGINS_DIR, "load")
CREATE_PATH = os.path.join(PLUGINS_DIR, "create")
INVENTORY_PATH = os.path.join(PLUGINS_DIR, "inventory")

self = sys.modules[__name__]
self.menu = None
self.callbacks = []


class SubstanceHost(HostBase, IWorkfileHost, ILoadHost, IPublishHost):
    name = "substancepainter"

    def __init__(self):
        super(SubstanceHost, self).__init__()
        self._has_been_setup = False

    def install(self):
        pyblish.api.register_host("substancepainter")

        pyblish.api.register_plugin_path(PUBLISH_PATH)
        register_loader_plugin_path(LOAD_PATH)
        register_creator_plugin_path(CREATE_PATH)

        log.info("Installing callbacks ... ")
        # register_event_callback("init", on_init)
        _register_callbacks()
        # register_event_callback("before.save", before_save)
        # register_event_callback("save", on_save)
        register_event_callback("open", on_open)
        # register_event_callback("new", on_new)

        log.info("Installing menu ... ")
        _install_menu()

        self._has_been_setup = True

    def uninstall(self):
        _uninstall_menu()
        _deregister_callbacks()

    def has_unsaved_changes(self):

        if not substance_painter.project.is_open():
            return False

        return substance_painter.project.needs_saving()

    def get_workfile_extensions(self):
        return [".spp", ".toc"]

    def save_workfile(self, dst_path=None):

        if not substance_painter.project.is_open():
            return False

        if not dst_path:
            dst_path = self.get_current_workfile()

        full_save_mode = substance_painter.project.ProjectSaveMode.Full
        substance_painter.project.save_as(dst_path, full_save_mode)

        return dst_path

    def open_workfile(self, filepath):

        if not os.path.exists(filepath):
            raise RuntimeError("File does not exist: {}".format(filepath))

        # We must first explicitly close current project before opening another
        if substance_painter.project.is_open():
            substance_painter.project.close()

        substance_painter.project.open(filepath)
        return filepath

    def get_current_workfile(self):
        if not substance_painter.project.is_open():
            return None

        filepath = substance_painter.project.file_path()
        if filepath.endswith(".spt"):
            # When currently in a Substance Painter template assume our
            # scene isn't saved. This can be the case directly after doing
            # "New project", the path will then be the template used. This
            # avoids Workfiles tool trying to save as .spt extension if the
            # file hasn't been saved before.
            return

        return filepath

    def get_containers(self):
        return []

    @staticmethod
    def create_context_node():
        pass

    def update_context_data(self, data, changes):
        pass

    def get_context_data(self):
        pass


def _install_menu():
    from PySide2 import QtWidgets
    from openpype.tools.utils import host_tools

    parent = substance_painter.ui.get_main_window()

    menu = QtWidgets.QMenu("OpenPype")

    action = menu.addAction("Load...")
    action.triggered.connect(
        lambda: host_tools.show_loader(parent=parent, use_context=True)
    )

    action = menu.addAction("Publish...")
    action.triggered.connect(
        lambda: host_tools.show_publisher(parent=parent)
    )

    action = menu.addAction("Manage...")
    action.triggered.connect(
        lambda: host_tools.show_scene_inventory(parent=parent)
    )

    action = menu.addAction("Library...")
    action.triggered.connect(
        lambda: host_tools.show_library_loader(parent=parent)
    )

    menu.addSeparator()
    action = menu.addAction("Work Files...")
    action.triggered.connect(
        lambda: host_tools.show_workfiles(parent=parent)
    )

    substance_painter.ui.add_menu(menu)

    def on_menu_destroyed():
        self.menu = None

    menu.destroyed.connect(on_menu_destroyed)

    self.menu = menu


def _uninstall_menu():
    if self.menu:
        self.menu.destroy()
        self.menu = None


def _register_callbacks():
    # Prepare emit event callbacks
    open_callback = partial(emit_event, "open")

    # Connect to the Substance Painter events
    dispatcher = substance_painter.event.DISPATCHER
    for event, callback in [
        (substance_painter.event.ProjectOpened, open_callback)
    ]:
        dispatcher.connect(event, callback)
        # Keep a reference so we can deregister if needed
        self.callbacks.append((event, callback))


def _deregister_callbacks():
    for event, callback in self.callbacks:
        substance_painter.event.DISPATCHER.disconnect(event, callback)


def on_open():
    log.info("Running callback on open..")
    print("Run")

    if any_outdated_containers():
        from openpype.widgets import popup

        log.warning("Scene has outdated content.")

        # Get main window
        parent = substance_painter.ui.get_main_window()
        if parent is None:
            log.info("Skipping outdated content pop-up "
                     "because Substance window can't be found.")
        else:

            # Show outdated pop-up
            def _on_show_inventory():
                from openpype.tools.utils import host_tools
                host_tools.show_scene_inventory(parent=parent)

            dialog = popup.Popup(parent=parent)
            dialog.setWindowTitle("Substance scene has outdated content")
            dialog.setMessage("There are outdated containers in "
                              "your Substance scene.")
            dialog.on_clicked.connect(_on_show_inventory)
            dialog.show()