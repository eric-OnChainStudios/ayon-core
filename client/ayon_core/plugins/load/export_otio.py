from collections import defaultdict

from qtpy import QtWidgets, QtCore, QtGui

from ayon_core.client import (
    get_representations,
    get_asset_name_identifier
)
from ayon_core.pipeline import load, Anatomy
from ayon_core import resources, style
from ayon_core.pipeline.load import get_representation_path_with_anatomy
from ayon_core.lib import run_subprocess


class ExportOTIO(load.SubsetLoaderPlugin):
    """Export selected versions to OpenTimelineIO."""

    is_multiple_contexts_compatible = True
    sequence_splitter = "__sequence_splitter__"

    representations = ["*"]
    families = ["*"]
    tool_names = ["library_loader"]

    label = "Export OTIO"
    order = 35
    icon = "save"
    color = "#d8d8d8"

    def load(self, contexts, name=None, namespace=None, options=None):
        try:
            dialog = ExportOTIOOptionsDialog(contexts, self.log)
            dialog.exec_()
        except Exception:
            self.log.error("Failed to export OTIO.", exc_info=True)


class ExportOTIOOptionsDialog(QtWidgets.QDialog):
    """Dialog to select template where to deliver selected representations."""

    def __init__(self, contexts, log=None, parent=None):
        # Not all hosts have OpenTimelineIO available.
        import opentimelineio as otio
        self.otio = otio

        super(ExportOTIOOptionsDialog, self).__init__(parent=parent)

        self.setWindowTitle("AYON - Export OTIO")
        icon = QtGui.QIcon(resources.get_ayon_icon_filepath())
        self.setWindowIcon(icon)

        self.setWindowFlags(
            QtCore.Qt.WindowStaysOnTopHint
            | QtCore.Qt.WindowCloseButtonHint
            | QtCore.Qt.WindowMinimizeButtonHint
        )

        self.setStyleSheet(style.load_stylesheet())

        input_widget = QtWidgets.QWidget(self)
        input_layout = QtWidgets.QGridLayout(input_widget)

        self._project_name = contexts[0]["project"]["name"]

        self._version_by_representation_id = {}
        all_representation_names = set()
        self._version_path_by_id = {}
        version_docs_by_id = {
            context["version"]["_id"]: context["version"]
            for context in contexts
        }
        repre_docs = list(get_representations(
            self._project_name, version_ids=set(version_docs_by_id)
        ))
        self._version_by_representation_id = {
            repre_doc["_id"]: version_docs_by_id[repre_doc["parent"]]
            for repre_doc in repre_docs
        }
        self._version_path_by_id = {}
        for context in contexts:
            version_doc = context["version"]
            version_id = version_doc["_id"]
            if version_id in self._version_path_by_id:
                continue
            asset_doc = context["asset"]
            folder_path = get_asset_name_identifier(asset_doc)
            subset_name = context["subset"]["name"]
            self._version_path_by_id[version_id] = "{}/{}/v{:03d}".format(
                folder_path, subset_name, version_doc["name"]
            )

        representations_by_version_id = defaultdict(list)
        for repre_doc in repre_docs:
            representations_by_version_id[repre_doc["parent"]].append(
                repre_doc
            )

        all_representation_names = sorted(set(x["name"] for x in repre_docs))

        input_layout.addWidget(QtWidgets.QLabel("Representations:"), 0, 0)
        for count, name in enumerate(all_representation_names):
            widget = QtWidgets.QPushButton(name)
            input_layout.addWidget(
                widget,
                0,
                count + 1,
                alignment=QtCore.Qt.AlignCenter
            )
            widget.clicked.connect(self.toggle_all)

        self._representation_widgets = defaultdict(list)
        row = 1
        items = representations_by_version_id.items()
        for version_id, representations in items:
            version_path = self._version_path_by_id[version_id]
            input_layout.addWidget(QtWidgets.QLabel(version_path), row, 0)

            representations_by_name = {x["name"]: x for x in representations}
            group_box = QtWidgets.QGroupBox()
            layout = QtWidgets.QHBoxLayout()
            group_box.setLayout(layout)
            for count, name in enumerate(all_representation_names):
                if name in representations_by_name.keys():
                    widget = QtWidgets.QRadioButton()
                    self._representation_widgets[name].append(
                        {
                            "widget": widget,
                            "representation": representations_by_name[name]
                        }
                    )
                else:
                    widget = QtWidgets.QLabel("x")

                layout.addWidget(widget)

            input_layout.addWidget(
                group_box, row, 1, 1, len(all_representation_names)
            )

            row += 1

        export_widget = QtWidgets.QWidget()
        export_layout = QtWidgets.QVBoxLayout(export_widget)

        widget = QtWidgets.QWidget()
        layout = QtWidgets.QHBoxLayout(widget)
        layout.addWidget(QtWidgets.QLabel("Output Path:"))
        self.lineedit_output_path = QtWidgets.QLineEdit()
        layout.addWidget(self.lineedit_output_path)
        export_layout.addWidget(widget)

        self.checkbox_inspect_otio_view = QtWidgets.QCheckBox(
            "Inspect with OTIO view"
        )
        export_layout.addWidget(self.checkbox_inspect_otio_view)

        self.btn_export = QtWidgets.QPushButton("Export")
        export_layout.addWidget(self.btn_export)

        layout = QtWidgets.QVBoxLayout(self)
        layout.addWidget(input_widget)
        layout.addWidget(export_widget)

        self.btn_export.clicked.connect(self.export)

    def toggle_all(self):
        representation_name = self.sender().text()
        for item in self._representation_widgets[representation_name]:
            item["widget"].setChecked(True)

    def export(self):
        representations = []
        for name, items in self._representation_widgets.items():
            for item in items:
                if item["widget"].isChecked():
                    representations.append(item["representation"])

        anatomy = Anatomy(self._project_name)
        clips_data = {}
        for representation in representations:
            version = self._version_by_representation_id[representation["_id"]]
            name = "{}/{}".format(
                self._version_path_by_id[version["_id"]],
                representation["name"]
            )
            clips_data[name] = {
                "path": get_representation_path_with_anatomy(
                    representation, anatomy
                ),
                "frames": (
                    version["data"]["frameEnd"] -
                    version["data"]["frameStart"]
                ),
                "framerate": version["data"]["fps"]
            }

        output_path = self.lineedit_output_path.text()
        self.export_otio(clips_data, output_path)

        check_state = self.checkbox_inspect_otio_view.checkState()
        if check_state == QtCore.Qt.CheckState.Checked:
            run_subprocess(["otioview", output_path])

    def create_clip(self, path, name, frames, framerate):
        range = self.otio.opentime.TimeRange(
            start_time=self.otio.opentime.RationalTime(0, framerate),
            duration=self.otio.opentime.RationalTime(frames, framerate)
        )

        media_reference = self.otio.schema.ExternalReference(
            available_range=range,
            target_url=f"file://{path}"
        )

        return self.otio.schema.Clip(
            name=name,
            media_reference=media_reference,
            source_range=range
        )

    def export_otio(self, clips_data, output_path):
        clips = []
        for name, data in clips_data.items():
            clips.append(
                self.create_clip(
                    data["path"], name, data["frames"], data["framerate"]
                )
            )

        timeline = self.otio.schema.timeline_from_clips(clips)
        self.otio.adapters.write_to_file(timeline, output_path)