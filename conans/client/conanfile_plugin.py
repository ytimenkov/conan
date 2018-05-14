"""Pylint plugin for ConanFile"""

import astroid
from astroid import MANAGER, scoped_nodes


def register(linter):
    # Needed for registering the plugin.
    pass


def _is_conanfile(node):
    return node.qname() == "conans.model.conan_file.ConanFile"


def transform_conanfile(node):
    str_class = scoped_nodes.builtin_lookup("str")
    info_class = MANAGER.ast_from_module_name("conans.model.info").lookup(
        "ConanInfo")
    list_class = scoped_nodes.builtin_lookup("list")

    dynamic_fields = {
        "source_folder": str_class,
        "build_folder": str_class,
        "package_folder": str_class,
        "build_requires": list_class,
        "info_build": info_class,
        "info": info_class,
    }

    for f, t in dynamic_fields.items():
        node.locals[f] = [t]


MANAGER.register_transform(scoped_nodes.Class, transform_conanfile,
                           _is_conanfile)
