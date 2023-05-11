import json

from maya import cmds

from openpype.pipeline import registered_host, get_current_asset_name
from openpype.pipeline.workfile.workfile_template_builder import (
    TemplateAlreadyImported,
    AbstractTemplateBuilder,
    PlaceholderPlugin,
    LoadPlaceholderItem,
    PlaceholderLoadMixin,
    TemplateLoadFailed,
    TemplateNotFound,
    TemplateProfileNotFound,
)
from openpype.tools.workfile_template_build import (
    WorkfileBuildPlaceholderDialog,
)

from .lib import read, imprint

PLACEHOLDER_SET = "PLACEHOLDERS_SET"


class MayaTemplateBuilder(AbstractTemplateBuilder):
    """Concrete implementation of AbstractTemplateBuilder for maya"""

    use_legacy_creators = True

    def open_template(self):
        """Open template in current scene.
        """

        try:
            template_preset = self.get_template_preset()
            template_path = template_preset["path"]

        except (
                    TemplateNotFound,
                    TemplateProfileNotFound,
                    TemplateLoadFailed
                ) as e:
            cmds.confirmDialog(
                title="Error",
                message="An error has occurred:\n{}".format(e),
                button=["OK"],
                defaultButton="OK",
            )
            return

        result = cmds.confirmDialog(
            title="Warning",
            message="Opening a template will clear the current scene.",
            button=["OK", "Cancel"],
            defaultButton="OK",
            cancelButton="Cancel",
            dismissString="Cancel",
        )

        if result != "OK":
            return

        print("opening template {}".format(template_path))
        cmds.file(template_path, open=True, force=True)

    def import_template(self, path):
        """Import template into current scene.
        Block if a template is already loaded.

        Args:
            path (str): A path to current template (usually given by
            get_template_preset implementation)

        Returns:
            bool: Whether the template was successfully imported or not
        """

        if cmds.objExists(PLACEHOLDER_SET):
            raise TemplateAlreadyImported((
                "Build template already loaded\n"
                "Clean scene if needed (File > New Scene)"
            ))

        cmds.sets(name=PLACEHOLDER_SET, empty=True)
        new_nodes = cmds.file(path, i=True, returnNewNodes=True)

        cmds.setAttr(PLACEHOLDER_SET + ".hiddenInOutliner", True)

        imported_sets = cmds.ls(new_nodes, set=True)
        if not imported_sets:
            return True

        # update imported sets information
        asset_name = get_current_asset_name()
        for node in imported_sets:
            if not cmds.attributeQuery("id", node=node, exists=True):
                continue
            if cmds.getAttr("{}.id".format(node)) != "pyblish.avalon.instance":
                continue
            if not cmds.attributeQuery("asset", node=node, exists=True):
                continue

            cmds.setAttr(
                "{}.asset".format(node), asset_name, type="string")

        return True


class MayaPlaceholderLoadPlugin(PlaceholderPlugin, PlaceholderLoadMixin):
    identifier = "maya.load"
    label = "Maya load"

    def _collect_scene_placeholders(self):
        # Cache placeholder data to shared data
        placeholder_nodes = self.builder.get_shared_populate_data(
            "placeholder_nodes"
        )
        if placeholder_nodes is None:
            attributes = cmds.ls("*.plugin_identifier", long=True)
            placeholder_nodes = {}
            for attribute in attributes:
                node_name = attribute.rpartition(".")[0]
                placeholder_nodes[node_name] = (
                    self._parse_placeholder_node_data(node_name)
                )

            self.builder.set_shared_populate_data(
                "placeholder_nodes", placeholder_nodes
            )
        return placeholder_nodes

    def _parse_placeholder_node_data(self, node_name):
        placeholder_data = read(node_name)
        parent_name = (
            cmds.getAttr(node_name + ".parent", asString=True)
            or node_name.rpartition("|")[0]
            or ""
        )
        if parent_name:
            siblings = cmds.listRelatives(parent_name, children=True)
        else:
            siblings = cmds.ls(assemblies=True)
        node_shortname = node_name.rpartition("|")[2]
        current_index = cmds.getAttr(node_name + ".index", asString=True)
        if current_index < 0:
            current_index = siblings.index(node_shortname)

        placeholder_data.update({
            "parent": parent_name,
            "index": current_index
        })
        return placeholder_data

    def _create_placeholder_name(self, placeholder_data):
        placeholder_name_parts = placeholder_data["builder_type"].split("_")

        pos = 1
        # add family in any
        placeholder_family = placeholder_data["family"]
        if placeholder_family:
            placeholder_name_parts.insert(pos, placeholder_family)
            pos += 1

        # add loader arguments if any
        loader_args = placeholder_data["loader_args"]
        if loader_args:
            loader_args = json.loads(loader_args.replace('\'', '\"'))
            values = [v for v in loader_args.values()]
            for value in values:
                placeholder_name_parts.insert(pos, value)
                pos += 1

        placeholder_name = "_".join(placeholder_name_parts)

        return placeholder_name.capitalize()

    def _get_loaded_repre_ids(self):
        loaded_representation_ids = self.builder.get_shared_populate_data(
            "loaded_representation_ids"
        )
        if loaded_representation_ids is None:
            try:
                containers = cmds.sets("AVALON_CONTAINERS", q=True)
            except ValueError:
                containers = []

            loaded_representation_ids = {
                cmds.getAttr(container + ".representation")
                for container in containers
            }
            self.builder.set_shared_populate_data(
                "loaded_representation_ids", loaded_representation_ids
            )
        return loaded_representation_ids

    def create_placeholder(self, placeholder_data):
        selection = cmds.ls(selection=True)
        if not selection:
            raise ValueError("Nothing is selected")
        if len(selection) > 1:
            raise ValueError("More then one item are selected")

        placeholder_data["plugin_identifier"] = self.identifier

        placeholder_name = self._create_placeholder_name(placeholder_data)

        placeholder = cmds.spaceLocator(name=placeholder_name)[0]
        # TODO: this can crash if selection can't be used
        cmds.parent(placeholder, selection[0])

        # get the long name of the placeholder (with the groups)
        placeholder_full_name = (
            cmds.ls(selection[0], long=True)[0]
            + "|"
            + placeholder.replace("|", "")
        )

        imprint(placeholder_full_name, placeholder_data)

        # Add helper attributes to keep placeholder info
        cmds.addAttr(
            placeholder_full_name,
            longName="parent",
            hidden=True,
            dataType="string"
        )
        cmds.addAttr(
            placeholder_full_name,
            longName="index",
            hidden=True,
            attributeType="short",
            defaultValue=-1
        )

        cmds.setAttr(placeholder_full_name + ".parent", "", type="string")

    def update_placeholder(self, placeholder_item, placeholder_data):
        node_name = placeholder_item.scene_identifier
        new_values = {}
        for key, value in placeholder_data.items():
            placeholder_value = placeholder_item.data.get(key)
            if value != placeholder_value:
                new_values[key] = value
                placeholder_item.data[key] = value

        for key in new_values.keys():
            cmds.deleteAttr(node_name + "." + key)

        imprint(node_name, new_values)

    def collect_placeholders(self):
        output = []
        scene_placeholders = self._collect_scene_placeholders()
        for node_name, placeholder_data in scene_placeholders.items():
            if placeholder_data.get("plugin_identifier") != self.identifier:
                continue

            # TODO do data validations and maybe updgrades if are invalid
            output.append(
                LoadPlaceholderItem(node_name, placeholder_data, self)
            )

        return output

    def populate_placeholder(self, placeholder):
        self.populate_load_placeholder(placeholder)

    def repopulate_placeholder(self, placeholder):
        repre_ids = self._get_loaded_repre_ids()
        self.populate_load_placeholder(placeholder, repre_ids)

    def get_placeholder_options(self, options=None):
        return self.get_load_plugin_options(options)

    def cleanup_placeholder(self, placeholder, failed):
        """Hide placeholder, add them to placeholder set
        """
        node = placeholder._scene_identifier

        cmds.sets(node, addElement=PLACEHOLDER_SET)
        cmds.hide(node)
        cmds.setAttr(node + ".hiddenInOutliner", True)

    def load_succeed(self, placeholder, container):
        self._parent_in_hierarchy(placeholder, container)

    def _parent_in_hierarchy(self, placeholder, container):
        """Parent loaded container to placeholder's parent.

        ie : Set loaded content as placeholder's sibling

        Args:
            container (str): Placeholder loaded containers
        """

        if not container:
            return

        roots = cmds.sets(container, q=True)
        nodes_to_parent = []
        for root in roots:
            if root.endswith("_RN"):
                refRoot = cmds.referenceQuery(root, n=True)[0]
                refRoot = cmds.listRelatives(refRoot, parent=True) or [refRoot]
                nodes_to_parent.extend(refRoot)
            elif root not in cmds.listSets(allSets=True):
                nodes_to_parent.append(root)

            elif not cmds.sets(root, q=True):
                return

        # Move loaded nodes to correct index in outliner hierarchy
        placeholder_form = cmds.xform(
            placeholder.scene_identifier,
            q=True,
            matrix=True,
            worldSpace=True
        )
        for node in set(nodes_to_parent):
            cmds.reorder(node, front=True)
            cmds.reorder(node, relative=placeholder.data["index"])
            cmds.xform(node, matrix=placeholder_form, ws=True)

        holding_sets = cmds.listSets(object=placeholder.scene_identifier)
        if not holding_sets:
            return
        for holding_set in holding_sets:
            cmds.sets(roots, forceElement=holding_set)


def build_workfile_template(*args):
    builder = MayaTemplateBuilder(registered_host())
    builder.build_template()


def update_workfile_template(*args):
    builder = MayaTemplateBuilder(registered_host())
    builder.rebuild_template()


def open_template(*args):
    builder = MayaTemplateBuilder(registered_host())
    builder.open_template()


def create_placeholder(*args):
    host = registered_host()
    builder = MayaTemplateBuilder(host)
    window = WorkfileBuildPlaceholderDialog(host, builder)
    window.exec_()


def update_placeholder(*args):
    host = registered_host()
    builder = MayaTemplateBuilder(host)
    placeholder_items_by_id = {
        placeholder_item.scene_identifier: placeholder_item
        for placeholder_item in builder.get_placeholders()
    }
    placeholder_items = []
    for node_name in cmds.ls(selection=True, long=True):
        if node_name in placeholder_items_by_id:
            placeholder_items.append(placeholder_items_by_id[node_name])

    # TODO show UI at least
    if len(placeholder_items) == 0:
        raise ValueError("No node selected")

    if len(placeholder_items) > 1:
        raise ValueError("Too many selected nodes")

    placeholder_item = placeholder_items[0]
    window = WorkfileBuildPlaceholderDialog(host, builder)
    window.set_update_mode(placeholder_item)
    window.exec_()
