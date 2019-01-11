import unittest

from conans.client.conf import default_settings_yml
from conans.client.generators.compiler_args import CompilerArgsGenerator
from conans.client.generators.gcc import GCCGenerator
from conans.model.settings import Settings
from conans.test.utils.conanfile import ConanFileMock


class CompilerArgsTest(unittest.TestCase):

    def visual_studio_extensions_test(self):
        settings = Settings.loads(default_settings_yml)
        settings.os = "Windows"
        settings.compiler = "Visual Studio"
        settings.compiler.version = "15"
        settings.arch = "x86"
        settings.build_type = "Release"

        conan_file = ConanFileMock()
        conan_file.settings = settings
        cpp_info = conan_file.deps_cpp_info
        cpp_info.libs.append("mylib")
        cpp_info.libs.append("other.lib")

        gen = CompilerArgsGenerator(conan_file)
        self.assertEqual('-O2 -Ob2 -DNDEBUG -link mylib.lib other.lib', gen.content)

    def _get_conanfile(self, settings):
        conan_file = ConanFileMock()
        conan_file.settings = settings
        conan_file.source_folder = "my_cache_source_folder"
        conan_file.build_folder = "my_cache_build_folder"

        cpp_info = conan_file.deps_cpp_info  # CppInfo("/root")
        cpp_info.include_paths.append("path/to/include1")
        cpp_info.lib_paths.append("path/to/lib1")
        cpp_info.libs.append("mylib")
        cpp_info.bindirs = "path/to/bin1"
        cpp_info.cflags.append("c_flag1")
        cpp_info.cppflags.append("cxx_flag1")
        cpp_info.defines.append("mydefine1")

        return conan_file

    def gcc_test(self):
        settings = Settings.loads(default_settings_yml)
        settings.os = "Linux"
        settings.compiler = "gcc"
        settings.compiler.version = "6.3"
        settings.arch = "x86"
        settings.build_type = "Release"
        settings.cppstd = "gnu17"

        conan_file = self._get_conanfile(settings)
        gcc = GCCGenerator(conan_file)
        self.assertEqual('-Dmydefine1 -Ipath/to/include1 cxx_flag1 c_flag1 -m32 -O3 -s -DNDEBUG '
                          '-Wl,-rpath="path/to/lib1" '
                          '-Lpath/to/lib1 -lmylib -std=gnu++17', gcc.content)

        settings.arch = "x86_64"
        settings.build_type = "Debug"
        settings.compiler.libcxx = "libstdc++11"

        gcc = GCCGenerator(conan_file)
        self.assertEqual('-Dmydefine1 -Ipath/to/include1 cxx_flag1 c_flag1 -m64 -g '
                          '-Wl,-rpath="path/to/lib1" -Lpath/to/lib1 -lmylib '
                          '-D_GLIBCXX_USE_CXX11_ABI=1 -std=gnu++17',
                          gcc.content)

        settings.compiler.libcxx = "libstdc++"
        gcc = GCCGenerator(conan_file)
        self.assertEqual('-Dmydefine1 -Ipath/to/include1 cxx_flag1 c_flag1 -m64 -g '
                          '-Wl,-rpath="path/to/lib1" -Lpath/to/lib1 -lmylib '
                          '-D_GLIBCXX_USE_CXX11_ABI=0 -std=gnu++17',
                          gcc.content)

        settings.os = "Windows"
        settings.compiler = "Visual Studio"
        settings.compiler.version = "15"
        settings.arch = "x86"
        settings.build_type = "Release"
        gcc = GCCGenerator(conan_file)
        # GCC generator ignores the compiler setting, it is always gcc
        self.assertEqual('-Dmydefine1 -Ipath/to/include1 cxx_flag1 c_flag1 -m32 -O3 -s '
                          '-DNDEBUG -Wl,-rpath="path/to/lib1" -Lpath/to/lib1 -lmylib',
                          gcc.content)

    def compiler_args_test(self):
        settings = Settings.loads(default_settings_yml)
        settings.os = "Windows"
        settings.compiler = "Visual Studio"
        settings.compiler.version = "15"
        settings.arch = "x86"
        settings.build_type = "Release"

        conan_file = self._get_conanfile(settings)
        gen = CompilerArgsGenerator(conan_file)
        self.assertEqual('-Dmydefine1 -Ipath\\to\\include1 cxx_flag1 c_flag1 -O2 -Ob2 -DNDEBUG '
                          '-link -LIBPATH:path\\to\\lib1 mylib.lib', gen.content)

        settings = Settings.loads(default_settings_yml)
        settings.os = "Macos"
        settings.compiler = "apple-clang"
        settings.compiler.version = "9.0"
        settings.arch = "x86"
        settings.build_type = "Release"
        conan_file = self._get_conanfile(settings)
        gen = CompilerArgsGenerator(conan_file)
        self.assertEqual('-Dmydefine1 -Ipath/to/include1 cxx_flag1 c_flag1 -m32 -O3 -DNDEBUG '
                          '-Wl,-rpath,"path/to/lib1" -Lpath/to/lib1 -lmylib', gen.content)

        settings = Settings.loads(default_settings_yml)
        settings.os = "Linux"
        settings.os_build = "Macos"
        settings.compiler = "apple-clang"
        settings.compiler.version = "9.0"
        settings.arch = "x86"
        settings.build_type = "Release"

        conan_file = self._get_conanfile(settings)
        args = CompilerArgsGenerator(conan_file)
        self.assertEqual('-Dmydefine1 -Ipath/to/include1 cxx_flag1 c_flag1 -m32 -O3 -DNDEBUG '
                          '-Wl,-rpath,"path/to/lib1" '
                          '-Lpath/to/lib1 -lmylib', args.content)
