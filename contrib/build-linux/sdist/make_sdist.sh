#!/bin/bash

set -e

PROJECT_ROOT="$(dirname "$(readlink -e "$0")")/../../.."
CONTRIB="$PROJECT_ROOT/contrib"
CONTRIB_SDIST="$CONTRIB/build-linux/sdist"
DISTDIR="$PROJECT_ROOT/dist"
BUILDDIR="$CONTRIB_SDIST/build"

. "$CONTRIB"/build_tools_util.sh

git -C "$PROJECT_ROOT" rev-parse 2>/dev/null || fail "Building outside a git clone is not supported."

rm -rf "$BUILDDIR"
mkdir -p "$BUILDDIR" "$DISTDIR"

python3 --version || fail "python interpreter not found"

break_legacy_easy_install

rm -rf "$PROJECT_ROOT/packages/"
if ([ "$OMIT_UNCLEAN_FILES" != 1 ]); then
    "$CONTRIB"/make_packages.sh || fail "make_packages failed"
fi

info "preparing electrin-locale."
(
    "$CONTRIB/locale/build_cleanlocale.sh"
    # By default, include both source (.po) and compiled (.mo) locale files in the source dist.
    # Set option OMIT_UNCLEAN_FILES=1 to exclude the compiled locale files
    # see https://askubuntu.com/a/144139 (also see MANIFEST.in)
    if ([ "$OMIT_UNCLEAN_FILES" = 1 ]); then
        rm -r "$PROJECT_ROOT/electrum/locale/locale"/*/LC_MESSAGES/electrum.mo
    fi
)

(
    cd "$PROJECT_ROOT"

    find -exec touch -h -d '2000-11-11T11:11:11+00:00' {} +

    # note: .zip sdists would not be reproducible due to https://bugs.python.org/issue40963
    if ([ "$OMIT_UNCLEAN_FILES" = 1 ]); then
        PY_DISTDIR="$BUILDDIR/dist1/_sourceonly" # The DISTDIR variable of this script is only used to find where the output is *finally* placed.
    else
        PY_DISTDIR="$BUILDDIR/dist1"
    fi
    # build initial tar.gz
    python3 setup.py --quiet sdist --format=gztar --dist-dir="$PY_DISTDIR"

    VERSION=$("$CONTRIB"/print_electrum_version.py)
    if ([ "$OMIT_UNCLEAN_FILES" = 1 ]); then
        FINAL_DISTNAME="Electrin-sourceonly-$VERSION.tar.gz"
    else
        FINAL_DISTNAME="Electrin-$VERSION.tar.gz"
    fi
    # setuptools names the tarball after the normalized version (1.0.0-beta.1 -> 1.0.0b1);
    # the published name keeps ELECTRIN_VERSION
    PY_TARBALL="$(ls "$PY_DISTDIR"/Electrin-*.tar.gz)"
    PY_NAME="$(basename "$PY_TARBALL" .tar.gz)"

    # the initial tar.gz is not reproducible, see https://github.com/pypa/setuptools/issues/2133
    # so we untar, fix timestamps, and then re-tar
    mkdir -p "$BUILDDIR/dist2"
    cd "$BUILDDIR/dist2"
    tar -xzf "$PY_TARBALL"
    if [ "$PY_NAME" != "Electrin-$VERSION" ]; then
        mv "$PY_NAME" "Electrin-$VERSION"
    fi
    rm -f "$PY_TARBALL"
    if ([ "$OMIT_UNCLEAN_FILES" = 1 ]); then
        rmdir "$PY_DISTDIR"
    fi
    find -exec touch -h -d '2000-11-11T11:11:11+00:00' {} +
    GZIP=-n tar --sort=name -czf "$FINAL_DISTNAME" "Electrin-$VERSION/"
    mv "$FINAL_DISTNAME" "$DISTDIR/$FINAL_DISTNAME"
)


info "done."
ls -la "$DISTDIR"
sha256sum "$DISTDIR"/*
