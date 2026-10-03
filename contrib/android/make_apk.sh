#!/bin/bash

set -e

CONTRIB_ANDROID="$(dirname "$(readlink -e "$0")")"
CONTRIB="$CONTRIB_ANDROID"/..
PROJECT_ROOT="$CONTRIB"/..
PACKAGES="$PROJECT_ROOT"/packages/

. "$CONTRIB"/build_tools_util.sh

git -C "$PROJECT_ROOT" rev-parse 2>/dev/null || fail "Building outside a git clone is not supported."


# arguments have been checked in build.sh
export ELEC_APK_GUI=$1

if [ ! -d "$PACKAGES" ]; then
    "$CONTRIB"/make_packages.sh || fail "make_packages failed"
fi

# update locale
info "preparing electrum-locale."
(
    "$CONTRIB/locale/build_cleanlocale.sh"
)

pushd "$CONTRIB_ANDROID"

info "apk building phase starts."

# Fix p4a distribute_javaclasses bug: it copies the dist-name directory itself
# into src/main/java/ instead of its contents, causing wrong paths like
# src/main/java/electrin/org/... instead of src/main/java/org/...
# See: pythonforandroid/bootstrap.py distribute_javaclasses()
P4A_BOOTSTRAP_PY="$(python3 -c 'import pythonforandroid.bootstrap; print(pythonforandroid.bootstrap.__file__)')" 2>/dev/null || true
if [ -n "$P4A_BOOTSTRAP_PY" ] && grep -q 'glob.glob(javaclass_dir)' "$P4A_BOOTSTRAP_PY"; then
    info "Patching p4a distribute_javaclasses to copy contents instead of directory..."
    sed -i "s|filenames = glob.glob(javaclass_dir)|filenames = glob.glob(javaclass_dir + '/*')|" "$P4A_BOOTSTRAP_PY"
fi

# Uncomment and change below to set a custom android package id,
# e.g. to allow simultaneous mainnet and testnet installs of the apk.
# defaults:
#   export APP_PACKAGE_NAME=Electrin
#   export APP_PACKAGE_DOMAIN=org.electrin
#
# FIXME: changing "APP_PACKAGE_NAME" seems to require a clean rebuild of ".buildozer/".
#        However, even with a clean build, the build appears to break in the final stages (~4.7.0).
#        To avoid these issues; only change "APP_PACKAGE_DOMAIN" instead.
#
# So, in particular, to build a testnet APK, simply uncomment:
#export APP_PACKAGE_DOMAIN=org.electrin.testnet

if [ $CI ]; then
    # override log level specified in buildozer.spec to "debug":
    export BUILDOZER_LOG_LEVEL=2
fi

if [[ "$3" == "release" ]] ; then
    # do release build, and sign the APKs.
    # Note: keystore validation is done earlier in build.sh (on the host).
    TARGET="release"
    export P4A_RELEASE_KEYSTORE_PASSWD="$4"
    export P4A_RELEASE_KEYALIAS_PASSWD="$4"
    export P4A_RELEASE_KEYSTORE=~/.keystore
    export P4A_RELEASE_KEYALIAS=electrin
elif [[ "$3" == "release-unsigned" ]] ; then
    # do release build, but do not sign the APKs.
    TARGET="release"
elif [[ "$3" == "debug" ]] ; then
    # do debug build.
    TARGET="apk"
    export P4A_DEBUG_KEYSTORE="$CONTRIB_ANDROID"/android_debug.keystore
    export P4A_DEBUG_KEYSTORE_PASSWD=unsafepassword
    export P4A_DEBUG_KEYALIAS_PASSWD=unsafepassword
    export P4A_DEBUG_KEYALIAS=electrum
    # create keystore if needed
    if [ ! -f "$P4A_DEBUG_KEYSTORE" ]; then
        keytool -genkey -v -keystore "$CONTRIB_ANDROID"/android_debug.keystore \
            -alias "$P4A_DEBUG_KEYALIAS" -keyalg RSA -keysize 2048 -validity 10000 \
            -dname "CN=mqttserver.ibm.com, OU=ID, O=IBM, L=Hursley, S=Hants, C=GB" \
            -storepass "$P4A_DEBUG_KEYSTORE_PASSWD" \
            -keypass "$P4A_DEBUG_KEYALIAS_PASSWD"
    fi
    export ELEC_APK_USE_CURRENT_TIME=1
else
    fail "unknown build type"
fi


if [[ "$2" == "all" ]] ; then
    # build all apks
    # FIXME failures are not propagated out: we should fail the script if any arch build fails
    export APP_ANDROID_ARCHS=armeabi-v7a
    export APP_ANDROID_NUMERIC_VERSION=$("$CONTRIB_ANDROID"/get_apk_versioncode.py "$APP_ANDROID_ARCHS")
    "$CONTRIB_ANDROID"/make_barcode_scanner.sh "$APP_ANDROID_ARCHS" || fail "make_barcode_scanner.sh failed"
    make $TARGET

    export APP_ANDROID_ARCHS=arm64-v8a
    export APP_ANDROID_NUMERIC_VERSION=$("$CONTRIB_ANDROID"/get_apk_versioncode.py "$APP_ANDROID_ARCHS")
    "$CONTRIB_ANDROID"/make_barcode_scanner.sh "$APP_ANDROID_ARCHS" || fail "make_barcode_scanner.sh failed"
    make $TARGET

    export APP_ANDROID_ARCHS=x86_64
    export APP_ANDROID_NUMERIC_VERSION=$("$CONTRIB_ANDROID"/get_apk_versioncode.py "$APP_ANDROID_ARCHS")
    "$CONTRIB_ANDROID"/make_barcode_scanner.sh "$APP_ANDROID_ARCHS" || fail "make_barcode_scanner.sh failed"
    make $TARGET
else
    export APP_ANDROID_ARCHS=$2
    export APP_ANDROID_NUMERIC_VERSION=$("$CONTRIB_ANDROID"/get_apk_versioncode.py "$APP_ANDROID_ARCHS")
    "$CONTRIB_ANDROID"/make_barcode_scanner.sh "$APP_ANDROID_ARCHS" || fail "make_barcode_scanner.sh failed"
    make $TARGET
fi

popd


info "done."
ls -la "$PROJECT_ROOT/dist"
sha256sum "$PROJECT_ROOT/dist"/*
