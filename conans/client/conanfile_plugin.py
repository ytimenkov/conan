"""Pylint plugin for ConanFile"""

import astroid
from astroid import MANAGER, scoped_nodes


def register(linter):
    # Needed for registering the plugin.
    pass


def transform_conanfile(node):
    """Transform definition of ConanFile class so dynamic fields are visible to pylint"""

    str_class = scoped_nodes.builtin_lookup("str")
    info_class = MANAGER.ast_from_module_name("conans.model.info").lookup(
        "ConanInfo")
    build_requires_class = MANAGER.ast_from_module_name(
        "conans.client.graph.build_requires").lookup("_RecipeBuildRequires")

    dynamic_fields = {
        "source_folder": str_class,
        "build_folder": str_class,
        "package_folder": str_class,
        "build_requires": build_requires_class,
        "info_build": info_class,
        "info": info_class,
    }

    for f, t in dynamic_fields.items():
        node.locals[f] = [t]


def infer_copy(node, context=None):
    """Transform access to self.copy so it returns callable FileCopier instance
    
    NOTE: For some reason pylint doesn't like when copy is declared in locals
          and complains that self.copy() is not callable.
    """

    _module, nodes = MANAGER.ast_from_module_name(
        "conans.client.file_copier").lookup("FileCopier")
    file_copier_node = nodes[0]
    return file_copier_node.infer_call_result(node, context=context)


MANAGER.register_transform(
    scoped_nodes.Class, transform_conanfile,
    lambda node: node.qname() == "conans.model.conan_file.ConanFile")

MANAGER.register_transform(astroid.Attribute,
                           astroid.inference_tip(infer_copy),
                           lambda node: node.attrname == "copy")
