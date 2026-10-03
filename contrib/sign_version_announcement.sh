#!/usr/bin/env bash
# Writes the signed announcement of an Electrin release, the JSON document served at
# https://electrin.net/version (src/content/version.json of the electrin-web repository):
#
#   {"version": "1.0.0", "openpgp_signature": "-----BEGIN PGP SIGNATURE----- ..."}
#
# The signature is a detached OpenPGP signature over the version string without a trailing
# newline, by the release signing key pinned in electrum/version_announcement.py.
#
# usage: contrib/sign_version_announcement.sh [VERSION] > version.json
#   VERSION defaults to ELECTRIN_VERSION of this tree.
#   ELECTRIN_RELEASE_KEY selects the signing key (default: the pinned release signing subkey).
#   GPG_PASSPHRASE, if set, is passed to gpg for non-interactive signing (CI).
set -euo pipefail

here="$(cd "$(dirname "$0")" && pwd)"
root="$(dirname "$here")"
key="${ELECTRIN_RELEASE_KEY:-ABB2DF8B79E8A4E761394732B3FF4116580342CB}"
version="${1:-$(python3 "$here/print_electrum_version.py")}"

gpg_args=(--batch --yes --local-user "${key}!" --digest-algo SHA256 --detach-sign --armor)
if [ -n "${GPG_PASSPHRASE:-}" ]; then
    gpg_args=(--pinentry-mode loopback --passphrase-fd 3 "${gpg_args[@]}")
    signature="$(printf '%s' "$version" | gpg "${gpg_args[@]}" 3<<<"$GPG_PASSPHRASE")"
else
    signature="$(printf '%s' "$version" | gpg "${gpg_args[@]}")"
fi

# write the document, then check it with Electrin's own verifier (needs only the cryptography
# package: the two modules are loaded without running electrum/__init__.py)
ELECTRIN_ROOT="$root" python3 - "$version" "$signature" <<'PY'
import json, os, sys, types
package = types.ModuleType("electrum")
package.__path__ = [os.path.join(os.environ["ELECTRIN_ROOT"], "electrum")]
sys.modules["electrum"] = package
from electrum.version_announcement import verify_announcement
announcement = {"version": sys.argv[1], "openpgp_signature": sys.argv[2]}
verify_announcement(announcement)
print(json.dumps(announcement, indent=2))
PY
