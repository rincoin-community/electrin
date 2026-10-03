# Electrin - lightweight Rincoin client
# Distributed under the MIT software license, see the accompanying
# file LICENCE or http://www.opensource.org/licenses/mit-license.php
"""Announcement of the latest Electrin release, as served at ANNOUNCEMENT_URL:

    {"version": "1.0.0", "openpgp_signature": "-----BEGIN PGP SIGNATURE----- ..."}

The signature is a detached OpenPGP signature over the version string (its UTF-8 bytes, no
trailing newline) by a key in RELEASE_KEYS, made with contrib/sign_version_announcement.sh.
"""

import re
from typing import Optional, Tuple

from .openpgp import PinnedKey, verify_detached_signature, OpenPGPError


ANNOUNCEMENT_URL = "https://electrin.net/version"
DOWNLOAD_URL = "https://github.com/rincoin-community/electrin/releases"

# Rincoin Community Security <security@rincoin.tech>, primary key
# FEE1 ACA5 2C65 FF3E BF31  818C B559 5E17 52BC 2A82; its signing subkey (ed25519, 2026-07-25):
RELEASE_KEYS = (
    PinnedKey(
        fingerprint="ABB2DF8B79E8A4E761394732B3FF4116580342CB",
        packet_body_hex="046a641b2b16092b06010401da470f010107407e97df6f0831f72fc41d24f131250c991cf912116a31bfa26a48e734a636b79f",
    ),
)

_VERSION_RE = re.compile(r'^(\d+)\.(\d+)\.(\d+)(?:-(alpha|beta|rc)\.(\d+))?$')
_PRERELEASE_RANK = {'alpha': 0, 'beta': 1, 'rc': 2, None: 3}


class AnnouncementError(Exception):
    pass


def parse_electrin_version(version_str: str) -> Optional[Tuple[int, int, int, int, int]]:
    """Sortable key of an Electrin version 'X.Y.Z' or 'X.Y.Z-(alpha|beta|rc).N', else None.
    Versions of the earlier scheme (e.g. '4.7.1rc1', inherited from Electrum) are not parsed."""
    m = _VERSION_RE.match(version_str.strip())
    if not m:
        return None
    major, minor, patch, stage, num = m.groups()
    return int(major), int(minor), int(patch), _PRERELEASE_RANK[stage], int(num or 0)


def is_newer(latest_version: str, current_version: str) -> bool:
    latest = parse_electrin_version(latest_version)
    current = parse_electrin_version(current_version)
    if latest is None or current is None:
        return False
    return latest > current


def verify_announcement(announcement: dict, *, keys=RELEASE_KEYS) -> str:
    """Returns the announced version if it is well formed and signed by a release key."""
    if not isinstance(announcement, dict):
        raise AnnouncementError("announcement is not a JSON object")
    version = announcement.get('version')
    signature = announcement.get('openpgp_signature')
    if not isinstance(version, str) or not isinstance(signature, str):
        raise AnnouncementError("announcement lacks a version or a signature")
    if version != version.strip() or parse_electrin_version(version) is None:
        raise AnnouncementError(f"unexpected version {version!r}")
    try:
        verify_detached_signature(version.encode('utf-8'), signature, keys)
    except OpenPGPError as e:
        raise AnnouncementError(f"no valid signature for version announcement: {e}") from e
    return version
