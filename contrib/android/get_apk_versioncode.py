#!/usr/bin/python3

import importlib.util
import os
import sys

ARCH_DICT = {
    "x86_64": "4",
    "arm64-v8a": "3",
    "armeabi-v7a": "2",
    "x86": "1",
    "null": "0",
}


def get_electrin_version() -> str:
    project_root = os.path.abspath(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
    version_file_path = os.path.join(project_root, "electrum", "version.py")
    # load version.py; needlessly complicated alternative to "imp.load_source":
    version_spec = importlib.util.spec_from_file_location('version', version_file_path)
    version_module = version = importlib.util.module_from_spec(version_spec)
    version_spec.loader.exec_module(version_module)
    return version.ELECTRIN_VERSION


def get_android_versioncode(*, arch_name: str) -> int:
    version_code = 0
    # add ELECTRIN_VERSION
    app_version = get_electrin_version()
    # if alpha/beta/rc, and not stable: strip out the "-alpha.N"/"-beta.N"/"-rc.N"
    # pre-release suffix from the last component (e.g. '1.0.0-beta.1' -> '1.0.0').
    # NOTE: we REUSE the version_code int between alphas/betas/rcs and the final stable.
    #       This is not allowed on Google Play or F-Droid.
    #       This means we MUST NOT upload alphas/betas/rcs there.
    import re
    m = re.search(r'-(alpha|beta|rc)\.?\d*$', app_version)
    if m:
        app_version = app_version[:m.start()]
    # now the app_version str must contain exactly three dot-delimited components
    app_version_components = app_version.split('.')
    assert len(app_version_components) == 3, f"version str expected to have 3 components, but got {app_version!r}"
    # convert to int
    for i in app_version_components:
        version_code *= 100
        version_code += int(i)
    # add arch
    arch_code = ARCH_DICT[arch_name]
    assert len(arch_code) == 1
    version_code *= 10
    version_code += int(arch_code)
    # compensate for legacy scheme
    # note: up until version 4.5.5, we used a different scheme for version_code.
    #       4_______________4_05_05_00
    #       ^ android arch, ^ app_version (4.5.5.0)
    # This offset ensures that all new-scheme version codes are larger than the old-scheme version codes.
    offset_due_to_legacy_scheme = 45_000_000
    version_code += offset_due_to_legacy_scheme
    # Electrin: until 4.7.1rc1, Electrin APKs carried the inherited Electrum version number
    # (version code 45_407_013 for 4.7.1 on arm64-v8a). Electrin's own numbering restarts at 1.0.0,
    # whose plain code (45_100_003) would be lower, and Android refuses to install a lower version
    # code over an installed app. This offset keeps every Electrin version above the 4.x codes.
    offset_due_to_electrin_version_restart = 1_000_000
    version_code += offset_due_to_electrin_version_restart
    return version_code


if __name__ == '__main__':
    try:
        android_arch = sys.argv[1]
    except Exception:
        print(f"usage: {os.path.basename(__file__)} <android_arch>", file=sys.stderr)
        sys.exit(1)
    if android_arch not in ARCH_DICT:
        print(f"usage: {os.path.basename(__file__)} <android_arch>", file=sys.stderr)
        print(f"error: unknown {android_arch=}", file=sys.stderr)
        print(f"       should be one of: {list(ARCH_DICT.keys())}", file=sys.stderr)
        sys.exit(1)
    version_code = get_android_versioncode(arch_name=android_arch)
    assert isinstance(version_code, int), f"{version_code=!r} must be an int."
    print(version_code, file=sys.stdout)
