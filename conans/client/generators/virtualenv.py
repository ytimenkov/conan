import os
from abc import ABCMeta, abstractmethod, abstractproperty
from itertools import chain
from textwrap import dedent

from conans.client.tools.oss import OSInfo
from conans.model import Generator


class BasicScriptGenerator(object):
    __metaclass__ = ABCMeta

    append_with_spaces = [
        "CPPFLAGS", "CFLAGS", "CXXFLAGS", "LIBS", "LDFLAGS", "CL"
    ]

    def __init__(self, name, env):
        self.name = name
        self.env = env

    def activate_lines(self):
        yield self.activate_prefix

        for name, value in self.env.items():
            if isinstance(value, list):
                placeholder = self.placeholder_format.format(name)
                if name in self.append_with_spaces:
                    # Variables joined with spaces look like: CPPFLAGS="one two three"
                    formatted_value = self.single_value_format.format(" ".join(
                        chain(value, [placeholder])))
                else:
                    # Quoted variables joined with pathset may look like:
                    # PATH="one path":"two paths"
                    # Unquoted variables joined with pathset may look like: PATH=one path;two paths
                    formatted_value = self.path_separator.join(
                        chain(self.path_transform(value), [placeholder]))
            else:
                formatted_value = self.single_value_format.format(value)

            yield self.activate_value_format.format(
                name=name, value=formatted_value)

        yield self.activate_suffix

    def deactivate_lines(self):
        yield self.deactivate_prefix

        for name in self.env:
            yield self.deactivate_value_format.format(name=name)

        yield self.deactivate_suffix

    @abstractproperty
    def activate_prefix(self):
        raise NotImplementedError()

    @abstractproperty
    def activate_suffix(self):
        raise NotImplementedError()

    @abstractproperty
    def activate_value_format(self):
        raise NotImplementedError()

    @abstractproperty
    def single_value_format(self):
        raise NotImplementedError()

    @abstractproperty
    def placeholder_format(self):
        raise NotImplementedError()

    @abstractmethod
    def path_transform(self, values):
        raise NotImplementedError()

    @abstractproperty
    def path_separator(self):
        raise NotImplementedError()

    @abstractproperty
    def deactivate_prefix(self):
        raise NotImplementedError()

    @abstractproperty
    def deactivate_value_format(self):
        raise NotImplementedError()

    @abstractproperty
    def deactivate_suffix(self):
        raise NotImplementedError()


class PosixValueFormats(object):
    # NTOE: Maybe this should be a function which escapes internal quotes,
    # e.g. if some CXXFLAGS contain spaces and are quoted themselves.
    single_value_format = '"{}"'
    placeholder_format = "${}"
    path_separator = ":"

    def path_transform(self, values):
        return ('"%s"' % v for v in values)


class FishScriptGenerator(PosixValueFormats, BasicScriptGenerator):
    def __init__(self, name, env):
        # Path is handled separately in fish.
        self.path = env.get("PATH", None)
        if "PATH" in env:
            env = env.copy()
            del env["PATH"]

        super(FishScriptGenerator, self).__init__(name, env)

    @property
    def activate_prefix(self):
        paths_prefix = dedent("""\
            if set -q fish_user_paths
                set -g _venv_old_fish_user_paths fish_user_paths
            end
            set -g fish_user_paths %s $fish_user_paths
            """) % " ".join(self.path_transform(
            self.path)) if self.path else ""

        return dedent("""\
            if set -q venv_name
                deactivate
            end
            set -g venv_name "%s"

            %s""") % (self.name, paths_prefix)

    activate_suffix = ""

    activate_value_format = dedent("""\
        if set -q {name}
            set -g _venv_old_{name} ${name}
        end
        set -gx {name} {value}""")

    @property
    def deactivate_prefix(self):
        paths_prefix = dedent("""\
            if set -q _venv_old_fish_user_paths
                set -g fish_user_paths $_venv_old_fish_user_paths
                set -e _venv_old_fish_user_paths
            else
                set -e fish_user_paths
            end""") if self.path else ""

        return dedent("""\
            function deactivate --description "Deactivate current virtualenv"

            %s
            """) % paths_prefix

    deactivate_suffix = dedent("""\
        set -e venv_name
        functions -e deactivate

        end
        """)

    deactivate_value_format = dedent("""\
        if set -q _venv_old_{name}
            set -gx {name} $_venv_old_{name}
            set -e _venv_old_{name}
        else
            set -ex {name}
        end
        """)


class ShScriptGenerator(PosixValueFormats, BasicScriptGenerator):
    def __init__(self, name, env):
        env = env.copy()
        env["PS1"] = "(%s) $PS1" % name
        super(ShScriptGenerator, self).__init__(name, env)

    @property
    def activate_prefix(self):
        return dedent("""\
            if [ -n "${VENV_NAME:-}" ] ; then
                deactivate
            fi
            VENV_NAME="%s"
            export VENV_NAME
            """) % self.name

    activate_value_format = dedent("""\
        if [ -n "${{{name}:-}}" ] ; then
            _venv_old_{name}="${{{name}}}"
        fi
        {name}={value}
        export {name}
        """)

    activate_suffix = ""

    deactivate_prefix = dedent("""\
        deactivate () {
        """)

    deactivate_suffix = dedent("""\
        unset VENV_NAME
        unset -f deactivate

        }
        """)

    deactivate_value_format = dedent("""\
        if [ -n "${{_venv_old_{name}:-}}" ] ; then
            {name}="${{_venv_old_{name}:-}}"
            export {name}
            unset _venv_old_{name}
        else
            unset {name}
        fi
        """)


class VirtualEnvGenerator(Generator):

    append_with_spaces = ["CPPFLAGS", "CFLAGS", "CXXFLAGS", "LIBS", "LDFLAGS", "CL"]

    def __init__(self, conanfile):
        super(VirtualEnvGenerator, self).__init__(conanfile)
        self.env = conanfile.env
        self.venv_name = "conanenv"

    @property
    def filename(self):
        return

    def _variable_placeholder(self, flavor, name):
        """
        :param flavor: flavor of the execution environment
        :param name: variable name
        :return: placeholder for the variable name formatted for a certain execution environment.
        (e.g., cmd, ps1, sh).
        """
        if flavor == "cmd":
            return "%%%s%%" % name
        if flavor == "ps1":
            return "$env:%s" % name
        return "$%s" % name  # flavor == sh

    def format_values(self, flavor, variables):
        """
        Formats the values for the different supported script language flavors.
        :param flavor: flavor of the execution environment
        :param variables: variables to be formatted
        :return:
        """
        variables = variables or self.env.items()
        if flavor == "cmd":
            path_sep, quote_elements, quote_full_value = ";", False, False
        elif flavor == "ps1":
            path_sep, quote_elements, quote_full_value = ";", False, True
        elif flavor == "sh":
            path_sep, quote_elements, quote_full_value = ":", True, False

        ret = []
        for name, value in variables:
            # activate values
            if isinstance(value, list):
                placeholder = self._variable_placeholder(flavor, name)
                if name in self.append_with_spaces:
                    # Variables joined with spaces look like: CPPFLAGS="one two three"
                    value = " ".join(value+[placeholder])
                    value = "\"%s\"" % value if quote_elements else value
                else:
                    # Quoted variables joined with pathset may look like:
                    # PATH="one path":"two paths"
                    # Unquoted variables joined with pathset may look like: PATH=one path;two paths
                    value = ["\"%s\"" % v for v in value] if quote_elements else value
                    value = path_sep.join(value+[placeholder])
            else:
                # single value
                value = "\"%s\"" % value if quote_elements else value
            activate_value = "\"%s\"" % value if quote_full_value else value

            # deactivate values
            value = os.environ.get(name, "")
            deactivate_value = "\"%s\"" % value if quote_full_value or quote_elements else value
            ret.append((name, activate_value, deactivate_value))
        return ret

    def _sh_lines(self):
        variables = [("OLD_PS1", "$PS1"),
                     ("PS1", "(%s) $PS1" % self.venv_name)]
        variables.extend(self.env.items())

        activate_lines = []
        deactivate_lines = ["%s=%s" % ("PS1", "$OLD_PS1"), "export PS1"]

        for name, activate, deactivate in self.format_values("sh", variables):
            activate_lines.append("%s=%s" % (name, activate))
            activate_lines.append("export %s" % name)
            if name != "PS1":
                if deactivate == '""':
                    deactivate_lines.append("unset %s" % name)
                else:
                    deactivate_lines.append("%s=%s" % (name, deactivate))
                    deactivate_lines.append("export %s" % name)
        activate_lines.append('')
        deactivate_lines.append('')
        return activate_lines, deactivate_lines

    def _cmd_lines(self):
        variables = [("PROMPT", "(%s) %%PROMPT%%" % self.venv_name)]
        variables.extend(self.env.items())

        activate_lines = ["@echo off"]
        deactivate_lines = ["@echo off"]
        for name, activate, deactivate in self.format_values("cmd", variables):
            activate_lines.append("SET %s=%s" % (name, activate))
            deactivate_lines.append("SET %s=%s" % (name, deactivate))
        activate_lines.append('')
        deactivate_lines.append('')
        return activate_lines, deactivate_lines

    def _ps1_lines(self):
        activate_lines = ['function global:_old_conan_prompt {""}']
        activate_lines.append('$function:_old_conan_prompt = $function:prompt')
        activate_lines.append('function global:prompt { write-host "(%s) " -nonewline; '
                              '& $function:_old_conan_prompt }' % self.venv_name)
        deactivate_lines = ['$function:prompt = $function:_old_conan_prompt']
        deactivate_lines.append('remove-item function:_old_conan_prompt')
        for name, activate, deactivate in self.format_values("ps1", self.env.items()):
            activate_lines.append('$env:%s = %s' % (name, activate))
            deactivate_lines.append('$env:%s = %s' % (name, deactivate))
        activate_lines.append('')
        return activate_lines, deactivate_lines

    @property
    def content(self):
        os_info = OSInfo()
        result = {}
        if os_info.is_windows and not os_info.is_posix:
            activate, deactivate = self._cmd_lines()
            result["activate.bat"] = os.linesep.join(activate)
            result["deactivate.bat"] = os.linesep.join(deactivate)

            activate, deactivate = self._ps1_lines()
            result["activate.ps1"] = os.linesep.join(activate)
            result["deactivate.ps1"] = os.linesep.join(deactivate)

        if os_info.is_posix:
            fish_script = FishScriptGenerator(self.venv_name, self.env)
            result["activate.fish"] = os.linesep.join(
                chain(fish_script.activate_lines(),
                      fish_script.deactivate_lines()))

        sh_script = ShScriptGenerator(self.venv_name, self.env)
        result["activate.sh"] = os.linesep.join(
            chain(sh_script.activate_lines(), sh_script.deactivate_lines()))

        return result
