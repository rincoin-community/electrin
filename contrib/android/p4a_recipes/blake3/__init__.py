import glob
import os

from pythonforandroid.logger import shprint
from pythonforandroid.recipe import PythonRecipe
from pythonforandroid.util import current_directory
import sh


class Blake3Recipe(PythonRecipe):
    # 0.4.1 is the last CFFI-based release (no Rust toolchain required).
    # Later releases (>= 1.0.0) require Rust and cannot currently be
    # cross-compiled for Android in the p4a environment.
    #
    # NOTE: blake3 0.4.1's top-level is a Rust/maturin package; the only
    # usable C extension is in the c_impl/ subdirectory which has its own
    # setup.py.  That setup.py also enforces cwd == its own directory.
    version = "0.4.1"
    sha512sum = "3c08e6bec2d69d6e7ce57dde3f8428f0d1b40f596b38a979f4a2f930061f14067f5675b4f74207d4bcccc4dda6b49f79cf48093d50a6b625e9bbebacecdf77ce"
    url = "https://files.pythonhosted.org/packages/b0/8d/43eafa8a785547c33b611068ffd6d914f5c5f96637d5b453abc556f095a0/blake3-{version}.tar.gz"
    depends = ["setuptools", "cffi"]

    def get_recipe_env(self, arch=None, with_flags_in_cc=True):
        env = super().get_recipe_env(arch, with_flags_in_cc)
        # p4a sets PYTHONHOME during builds to point at the target Python,
        # which hides hostpython3's own Lib/site-packages (including
        # setuptools).  Prepend hostpython3's site-packages to PYTHONPATH
        # so that setup.py can 'import setuptools' regardless.
        hp_dir = os.path.dirname(str(self.ctx.hostpython))
        hp_sp = os.path.join(hp_dir, 'Lib', 'site-packages')
        if not os.path.isdir(hp_sp):
            matches = glob.glob(os.path.join(self.ctx.build_dir, 'other_builds',
                'hostpython3', '*', 'hostpython3', 'native-build', 'Lib', 'site-packages'))
            if matches:
                hp_sp = matches[0]
        if os.path.isdir(hp_sp):
            existing = env.get('PYTHONPATH', '')
            env['PYTHONPATH'] = hp_sp + (os.pathsep + existing if existing else '')

        # On Android the linker does not resolve Python C-API symbols unless
        # the extension is explicitly linked against libpython.  PythonRecipe
        # only adds -lpython when call_hostpython_via_targetpython is False,
        # but blake3 uses a custom build_arch so we add it here explicitly.
        python_recipe = self.ctx.python_recipe
        # blake3 0.4.1's C module declares its METH_VARARGS|METH_KEYWORDS functions with three
        # parameters in PyMethodDef (the usual CPython idiom, without a cast); the clang of
        # NDK r28 treats that as an error (default since clang 16). Keep it a warning.
        env['CFLAGS'] = env.get('CFLAGS', '') + ' -Wno-error=incompatible-function-pointer-types'
        env['LDFLAGS'] += ' -L{} -lpython{}'.format(
            python_recipe.link_root(arch.arch),
            python_recipe.link_version,
        )

        return env

    def build_arch(self, arch):
        env = self.get_recipe_env(arch)
        build_dir = self.get_build_dir(arch.arch)
        c_impl_dir = os.path.join(build_dir, 'c_impl')

        # Patch c_impl/setup.py to fix platform detection for cross-compilation.
        # platform.machine() on the build host is "x86_64", so without patching
        # the script picks x86-64 ASM files which aarch64 clang cannot assemble.
        # We override the three detection functions so the ARM64 NEON path is
        # selected instead (targeting_x86_64/32 -> False, is_aarch64 -> True).
        setup_py = os.path.join(c_impl_dir, 'setup.py')
        with open(setup_py, 'r') as fh:
            src = fh.read()

        patch_marker = '# CROSS_COMPILE_PATCHED_FOR_AARCH64'
        if patch_marker not in src:
            arch_patch = (
                patch_marker + '\n'
                'def targeting_x86_64():\n'
                '    return False\n'
                'def targeting_x86_32():\n'
                '    return False\n'
                'def is_aarch64():\n'
                '    return True\n'
            )
            # Insert the overrides just before prepare_extension() which uses them.
            src = src.replace(
                '\ndef prepare_extension():',
                '\n' + arch_patch + '\ndef prepare_extension():'
            )
            with open(setup_py, 'w') as fh:
                fh.write(src)

        # c_impl/setup.py explicitly checks that cwd == its own directory.
        install_dir = self.ctx.get_python_install_dir(arch.arch)
        with current_directory(c_impl_dir):
            hostpython = sh.Command(self.ctx.hostpython)
            shprint(hostpython, 'setup.py', 'install', '-O2',
                    '--root={}'.format(install_dir),
                    '--install-lib=.',
                    _env=env)


recipe = Blake3Recipe()
