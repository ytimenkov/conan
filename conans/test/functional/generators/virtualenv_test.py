import os
import subprocess
import unittest
from textwrap import dedent

from conans.client.tools import which
from conans.client.tools.oss import OSInfo
from conans.test.utils.tools import TestClient
from conans.util.files import decode_text, load, to_file_bytes

os_info = OSInfo()


class VirtualEnvIntegrationTest(unittest.TestCase):
    def setUp(self):
        self.client = TestClient()
        package_conanfile = r"""
import os
from conans import ConanFile, tools

class DummyConan(ConanFile):
    name = "dummy"
    version = "0.1"

    def package(self):
        # Create a program in bin folder (added to PATH) so we can check that it can be ran later.
        posix_prog_path = os.path.join(self.package_folder, "bin", "conan_venv_test_prog")
        tools.save(posix_prog_path + ".cmd", "")
        tools.save(posix_prog_path, "")
        os.chmod(posix_prog_path, 0o755)

    def package_info(self):
        self.env_info.PATH.append(os.path.join(self.package_folder, "bin"))
        self.env_info.CFLAGS.append("-O2")
        self.env_info.USER_VALUE = r"some value with space and \ (backslash)"
"""
        consumer_conanfile = """
[requires]
dummy/0.1@lasote/testing
[generators]
virtualenv
    """
        self.client.save({"conanfile.py": package_conanfile})
        self.client.run("export . lasote/testing")
        self.client.save(
            {
                "conanfile.txt": consumer_conanfile,
                "original path/conan_original_test_prog": "",
                "original path/conan_original_test_prog.cmd": ""
            },
            clean_first=True)
        os.chmod(
            os.path.join(self.client.current_folder, "original path",
                         "conan_original_test_prog"), 0o755)
        self.client.run("install . --build")

    @property
    def subprocess_env(self):
        env = os.environ.copy()
        env["PATH"] = "%s%s%s" % (os.path.join(self.client.current_folder,
                                               "original path"), os.pathsep,
                                  env.get("PATH", ""))
        env["CFLAGS"] = "-g"
        env["USER_VALUE"] = "original value"
        return env

    @staticmethod
    def load_env(path):
        text = load(path)
        return dict(l.split("=", 1) for l in text.splitlines())

    def do_verification(self, stdout, stderr):
        self.assertFalse(stderr, "Running shell resulted in error")
        stdout = decode_text(stdout)
        self.assertRegex(
            stdout,
            r"(?m)^__conan_venv_test_prog_path__=%s.*bin/conan_venv_test_prog"
            % self.client.base_folder, "Packaged binary was not found in PATH")
        self.assertRegex(
            stdout,
            r"(?m)^__original_prog_path__=%s/original path/conan_original_test_prog"
            % self.client.current_folder,
            "Activated environment incorrectly preserved PATH")
        activated_env = VirtualEnvIntegrationTest.load_env(
            os.path.join(self.client.current_folder, "env_activated.txt"))
        self.assertEqual(
            activated_env["CFLAGS"], "-O2 -g",
            "Environment variable with spaces is set incorrectly")
        self.assertEqual(activated_env["USER_VALUE"],
                         r"some value with space and \ (backslash)",
                         "Custom variable is set incorrectly")
        before_env = VirtualEnvIntegrationTest.load_env(
            os.path.join(self.client.current_folder, "env_before.txt"))
        after_env = VirtualEnvIntegrationTest.load_env(
            os.path.join(self.client.current_folder, "env_after.txt"))
        self.assertDictEqual(before_env, after_env,
                             "Environment restored incorrectly")

    def execute_intereactive_shell(self, args, commands):
        shell = subprocess.Popen(
            args,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=self.client.current_folder,
            env=self.subprocess_env)
        (stdout, stderr) = shell.communicate(to_file_bytes(dedent(commands)))
        self.do_verification(stdout, stderr)

    @unittest.skipUnless(os_info.is_posix, "needs POSIX")
    def posix_shell_test(self):
        self.execute_intereactive_shell(
            "sh", """\
                env > env_before.txt
                . ./activate.sh
                env > env_activated.txt
                echo __conan_venv_test_prog_path__=$(which conan_venv_test_prog)
                echo __original_prog_path__=$(which conan_original_test_prog)
                deactivate
                env > env_after.txt
                """)

    @unittest.skipUnless(
        os_info.is_posix and which("fish"), "fish shell is not found")
    def fish_shell_test(self):
        self.execute_intereactive_shell(
            "fish", """\
                env > env_before.txt
                . activate.fish
                env > env_activated.txt
                echo __conan_venv_test_prog_path__=(which conan_venv_test_prog)
                echo __original_prog_path__=(which conan_original_test_prog)
                deactivate
                env > env_after.txt
                """)

    @unittest.skipUnless(
        os_info.is_windows or which("pwsh"), "Requires PowerShell (Core)")
    def powershell_test(self):
        powershell_cmd = "powershell.exe" if os_info.is_windows else "pwsh"
        self.execute_intereactive_shell(
            [powershell_cmd, "-ExecutionPolicy", "RemoteSigned"], """\
                Get-ChildItem Env: | ForEach-Object {"$($_.Name)=$($_.Value)"} > env_before.txt
                . ./activate.ps1
                Get-ChildItem Env: | ForEach-Object {"$($_.Name)=$($_.Value)"} > env_activated.txt
                Write-Host "__conan_venv_test_prog_path__=$((Get-Command conan_venv_test_prog).Source)"
                Write-Host "__original_prog_path__=$((Get-Command conan_original_test_prog).Source)"
                deactivate
                Get-ChildItem Env: | ForEach-Object {"$($_.Name)=$($_.Value)"} > env_after.txt
                """)

    @unittest.skipUnless(os_info.is_windows and not os_info.is_posix,
                         "Available on Windows only")
    def windows_cmd_test(self):
        self.execute_intereactive_shell(
            "cmd", """\
                set > env_before.txt
                activate.bat
                set > env_activated.txt
                for /f "usebackq tokens=*" %testprog in (`where conan_venv_test_prog`) do echo __conan_venv_test_prog_path__=%testprog
                for /f "usebackq tokens=*" %testprog in (`where conan_original_test_prog`) do echo __original_prog_path__=%testprog
                deactivate.bat
                set > env_after.txt
                """)
