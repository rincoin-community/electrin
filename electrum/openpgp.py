# Electrin - lightweight Rincoin client
# Distributed under the MIT software license, see the accompanying
# file LICENCE or http://www.opensource.org/licenses/mit-license.php
"""Minimal verifier of detached OpenPGP signatures made with a pinned Ed25519 key.

Electrin's release announcements are signed with the OpenPGP release key of Rincoin Community
Forge (the same key that signs the release checksums), e.g.

    printf '%s' "$VERSION" | gpg --local-user '<subkey fingerprint>!' --detach-sign --armor

This module verifies exactly that kind of signature and nothing else (RFC 4880 / RFC 9580):
one version-4 signature packet of type 0x00 (binary document), made by a pinned version-4
EdDSA key over Ed25519 (public-key algorithm 22) with SHA-256, SHA-384 or SHA-512, with the
issuer fingerprint in the hashed subpackets. The key is pinned by its public-key packet,
whose fingerprint is checked, so no key ring, no trust model and no key server is involved.
"""

import base64
import hashlib
from typing import Iterable, List, NamedTuple, Optional, Tuple


class OpenPGPError(Exception):
    pass


class PinnedKey(NamedTuple):
    fingerprint: str      # upper-case hex, 40 characters (version-4 fingerprint)
    packet_body_hex: str  # body of the version-4 public-(sub)key packet


_ED25519_OID = bytes.fromhex("2b06010401da470f01")  # 1.3.6.1.4.1.11591.15.1
_PK_ALGO_EDDSA_LEGACY = 22
_SIG_TYPE_BINARY = 0x00
_HASHES = {8: hashlib.sha256, 9: hashlib.sha384, 10: hashlib.sha512}
_SUBPACKET_SIG_CREATION_TIME = 2
_SUBPACKET_ISSUER_KEY_ID = 16
_SUBPACKET_ISSUER_FINGERPRINT = 33


def key_fingerprint(packet_body: bytes) -> str:
    """Version-4 fingerprint of a public-key packet body."""
    if not packet_body or packet_body[0] != 4:
        raise OpenPGPError("only version-4 keys are supported")
    return hashlib.sha1(b"\x99" + len(packet_body).to_bytes(2, "big") + packet_body).hexdigest().upper()


def ed25519_public_key(pinned: PinnedKey) -> bytes:
    """The 32-byte Ed25519 public key of a pinned key, after checking its fingerprint."""
    body = bytes.fromhex(pinned.packet_body_hex)
    if key_fingerprint(body) != pinned.fingerprint.upper():
        raise OpenPGPError("pinned key does not match its fingerprint")
    # version (1), creation time (4), algorithm (1), OID length (1), OID, MPI
    if body[5] != _PK_ALGO_EDDSA_LEGACY:
        raise OpenPGPError("pinned key is not an EdDSA key")
    oid_len = body[6]
    if body[7:7 + oid_len] != _ED25519_OID:
        raise OpenPGPError("pinned key is not an Ed25519 key")
    mpi = body[7 + oid_len:]
    bits = int.from_bytes(mpi[:2], "big")
    point = mpi[2:]
    if bits != 263 or len(point) != 33 or point[0] != 0x40:
        raise OpenPGPError("unexpected Ed25519 public key encoding")
    return point[1:]


def _crc24(data: bytes) -> int:
    crc = 0xB704CE
    for byte in data:
        crc ^= byte << 16
        for _ in range(8):
            crc <<= 1
            if crc & 0x1000000:
                crc ^= 0x1864CFB
    return crc & 0xFFFFFF


def dearmor(armored: str) -> bytes:
    lines = [line.strip() for line in armored.strip().splitlines()]
    try:
        start = lines.index("-----BEGIN PGP SIGNATURE-----")
        end = lines.index("-----END PGP SIGNATURE-----")
    except ValueError:
        raise OpenPGPError("not an armored OpenPGP signature") from None
    body = lines[start + 1:end]
    # armor headers end with the first empty line
    if "" in body:
        body = body[body.index("") + 1:]
    checksum = None
    if body and body[-1].startswith("="):
        checksum = body.pop()
    try:
        data = base64.b64decode("".join(body), validate=True)
    except Exception:
        raise OpenPGPError("invalid armor") from None
    if checksum is not None:
        try:
            expected = int.from_bytes(base64.b64decode(checksum[1:], validate=True), "big")
        except Exception:
            raise OpenPGPError("invalid armor checksum") from None
        if _crc24(data) != expected:
            raise OpenPGPError("armor checksum mismatch")
    return data


def _packets(data: bytes) -> List[Tuple[int, bytes]]:
    packets = []
    i = 0
    while i < len(data):
        header = data[i]
        i += 1
        if not header & 0x80:
            raise OpenPGPError("invalid packet header")
        if header & 0x40:  # new format
            tag = header & 0x3F
            if i >= len(data):
                raise OpenPGPError("truncated packet")
            first = data[i]
            i += 1
            if first < 192:
                length = first
            elif first < 224:
                length = ((first - 192) << 8) + data[i] + 192
                i += 1
            elif first == 255:
                length = int.from_bytes(data[i:i + 4], "big")
                i += 4
            else:
                raise OpenPGPError("partial body lengths are not supported")
        else:  # old format
            tag = (header >> 2) & 0x0F
            length_type = header & 0x03
            if length_type == 3:
                raise OpenPGPError("indeterminate packet length is not supported")
            n = (1, 2, 4)[length_type]
            length = int.from_bytes(data[i:i + n], "big")
            i += n
        if i + length > len(data):
            raise OpenPGPError("truncated packet")
        packets.append((tag, data[i:i + length]))
        i += length
    return packets


def _subpackets(area: bytes) -> List[Tuple[int, bool, bytes]]:
    result = []
    i = 0
    while i < len(area):
        first = area[i]
        i += 1
        if first < 192:
            length = first
        elif first < 255:
            length = ((first - 192) << 8) + area[i] + 192
            i += 1
        else:
            length = int.from_bytes(area[i:i + 4], "big")
            i += 4
        if length < 1 or i + length > len(area):
            raise OpenPGPError("invalid signature subpacket")
        stype = area[i]
        result.append((stype & 0x7F, bool(stype & 0x80), area[i + 1:i + length]))
        i += length
    return result


def _read_mpi(data: bytes, i: int) -> Tuple[bytes, int]:
    if i + 2 > len(data):
        raise OpenPGPError("truncated MPI")
    bits = int.from_bytes(data[i:i + 2], "big")
    n = (bits + 7) // 8
    if i + 2 + n > len(data):
        raise OpenPGPError("truncated MPI")
    return data[i + 2:i + 2 + n], i + 2 + n


def verify_detached_signature(data: bytes, armored_signature: str, keys: Iterable[PinnedKey]) -> str:
    """Verifies a detached signature over data by one of the pinned keys.
    Returns the fingerprint of the key that made it; raises OpenPGPError otherwise."""
    keys = {k.fingerprint.upper(): k for k in keys}
    packets = _packets(dearmor(armored_signature))
    if len(packets) != 1 or packets[0][0] != 2:
        raise OpenPGPError("expected exactly one signature packet")
    sig = packets[0][1]
    if len(sig) < 6 or sig[0] != 4:
        raise OpenPGPError("only version-4 signatures are supported")
    sig_type, pk_algo, hash_algo = sig[1], sig[2], sig[3]
    if sig_type != _SIG_TYPE_BINARY:
        raise OpenPGPError("not a signature of a binary document")
    if pk_algo != _PK_ALGO_EDDSA_LEGACY:
        raise OpenPGPError("not an EdDSA signature")
    if hash_algo not in _HASHES:
        raise OpenPGPError("unsupported hash algorithm")
    hashed_len = int.from_bytes(sig[4:6], "big")
    hashed_end = 6 + hashed_len
    if hashed_end + 2 > len(sig):
        raise OpenPGPError("truncated signature packet")
    hashed_area = sig[6:hashed_end]
    unhashed_len = int.from_bytes(sig[hashed_end:hashed_end + 2], "big")
    i = hashed_end + 2 + unhashed_len
    if i + 2 > len(sig):
        raise OpenPGPError("truncated signature packet")
    left16 = sig[i:i + 2]
    r, i = _read_mpi(sig, i + 2)
    s, i = _read_mpi(sig, i)
    if i != len(sig) or len(r) > 32 or len(s) > 32:
        raise OpenPGPError("unexpected EdDSA signature encoding")

    issuer = None  # type: Optional[str]
    has_creation_time = False
    for stype, critical, value in _subpackets(hashed_area):
        if stype == _SUBPACKET_ISSUER_FINGERPRINT:
            if len(value) != 21 or value[0] != 4:
                raise OpenPGPError("unexpected issuer fingerprint")
            issuer = value[1:].hex().upper()
        elif stype == _SUBPACKET_SIG_CREATION_TIME:
            has_creation_time = True
        elif critical and stype != _SUBPACKET_ISSUER_KEY_ID:
            raise OpenPGPError(f"unsupported critical subpacket {stype}")
    if issuer is None or not has_creation_time:
        raise OpenPGPError("signature lacks a hashed issuer fingerprint or creation time")
    key = keys.get(issuer)
    if key is None:
        raise OpenPGPError(f"signature made by an unknown key {issuer}")

    h = _HASHES[hash_algo]()
    h.update(data)
    h.update(sig[:hashed_end])
    h.update(b"\x04\xff" + hashed_end.to_bytes(4, "big"))
    digest = h.digest()
    if digest[:2] != left16:
        raise OpenPGPError("signature does not match the data")

    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
        from cryptography.exceptions import InvalidSignature
    except ImportError:
        raise OpenPGPError("the cryptography package is needed to verify Ed25519 signatures") from None
    public_key = Ed25519PublicKey.from_public_bytes(ed25519_public_key(key))
    try:
        public_key.verify(r.rjust(32, b"\x00") + s.rjust(32, b"\x00"), digest)
    except InvalidSignature:
        raise OpenPGPError("invalid signature") from None
    return issuer
