# Release announcements: the minimal OpenPGP verifier (electrum/openpgp.py) and the
# announcement format (electrum/version_announcement.py).
#
# The fixtures are real detached signatures by the release signing subkey over version
# strings that are never newer than any release ('0.0.0-alpha.1', '0.0.0-alpha.2'), made with
#   printf '%s' 0.0.0-alpha.1 | gpg --local-user 'B3FF4116580342CB!' --digest-algo SHA256 --detach-sign --armor
import base64

from electrum import openpgp, version_announcement
from electrum.openpgp import OpenPGPError, PinnedKey, verify_detached_signature
from electrum.version_announcement import AnnouncementError, RELEASE_KEYS, verify_announcement

from . import ElectrumTestCase


SIG_SHA256 = """-----BEGIN PGP SIGNATURE-----

iHUEABYIAB0WIQSrst+Leeik52E5RzKz/0EWWANCywUCasFsJwAKCRCz/0EWWANC
y9vKAQD24fu94JS2ooRfov7SuzaQnnJgimlsCPTckcP52KANMwD9F4vwOFhBAKau
4XyQkFNB+OFTmm+yqFZOfhVlj1E2Eww=
=DnES
-----END PGP SIGNATURE-----"""  # over b"0.0.0-alpha.1"

SIG_SHA512 = """-----BEGIN PGP SIGNATURE-----

iHUEABYKAB0WIQSrst+Leeik52E5RzKz/0EWWANCywUCasFsJwAKCRCz/0EWWANC
y5EKAQCjt6sxNs8aT5MHbgeTCrAlISZEslzPVdEaJ5cC24IqKgD+PCFSTgOT74sA
aK/+a4lU3ScXaiZCsUyrA/BMb5mgkAc=
=EhK7
-----END PGP SIGNATURE-----"""  # over b"0.0.0-alpha.2"

FINGERPRINT = "ABB2DF8B79E8A4E761394732B3FF4116580342CB"


def _rearmor(data: bytes) -> str:
    body = base64.b64encode(data).decode()
    crc = openpgp._crc24(data).to_bytes(3, "big")
    return "\n".join(["-----BEGIN PGP SIGNATURE-----", "", body, "=" + base64.b64encode(crc).decode(),
                      "-----END PGP SIGNATURE-----"])


class TestOpenPGP(ElectrumTestCase):

    def test_pinned_key(self):
        self.assertEqual(1, len(RELEASE_KEYS))
        self.assertEqual(FINGERPRINT, RELEASE_KEYS[0].fingerprint)
        self.assertEqual(FINGERPRINT, openpgp.key_fingerprint(bytes.fromhex(RELEASE_KEYS[0].packet_body_hex)))
        self.assertEqual(32, len(openpgp.ed25519_public_key(RELEASE_KEYS[0])))
        bad = PinnedKey(fingerprint="00" * 20, packet_body_hex=RELEASE_KEYS[0].packet_body_hex)
        with self.assertRaises(OpenPGPError):
            openpgp.ed25519_public_key(bad)

    def test_valid_signatures(self):
        self.assertEqual(FINGERPRINT, verify_detached_signature(b"0.0.0-alpha.1", SIG_SHA256, RELEASE_KEYS))
        self.assertEqual(FINGERPRINT, verify_detached_signature(b"0.0.0-alpha.2", SIG_SHA512, RELEASE_KEYS))

    def test_wrong_data(self):
        for data in (b"0.0.0-alpha.2", b"0.0.0-alpha.1\n", b"", b"1.0.0"):
            with self.assertRaises(OpenPGPError):
                verify_detached_signature(data, SIG_SHA256, RELEASE_KEYS)

    def test_unknown_key(self):
        with self.assertRaises(OpenPGPError):
            verify_detached_signature(b"0.0.0-alpha.1", SIG_SHA256, ())

    def test_tampered_signature(self):
        raw = bytearray(openpgp.dearmor(SIG_SHA256))
        raw[-5] ^= 0x01  # inside the S value
        with self.assertRaises(OpenPGPError):
            verify_detached_signature(b"0.0.0-alpha.1", _rearmor(bytes(raw)), RELEASE_KEYS)
        # the same bytes re-armored unchanged still verify (the re-armoring itself is sound)
        self.assertEqual(FINGERPRINT, verify_detached_signature(
            b"0.0.0-alpha.1", _rearmor(openpgp.dearmor(SIG_SHA256)), RELEASE_KEYS))

    def test_armor_checksum(self):
        lines = SIG_SHA256.splitlines()
        crc_line = next(i for i, line in enumerate(lines) if line.startswith("="))
        lines[crc_line] = "=AAAA"
        with self.assertRaises(OpenPGPError):
            verify_detached_signature(b"0.0.0-alpha.1", "\n".join(lines), RELEASE_KEYS)
        with self.assertRaises(OpenPGPError):
            verify_detached_signature(b"0.0.0-alpha.1", "not a signature", RELEASE_KEYS)


class TestVersionAnnouncement(ElectrumTestCase):

    def test_verify(self):
        self.assertEqual("0.0.0-alpha.1", verify_announcement(
            {"version": "0.0.0-alpha.1", "openpgp_signature": SIG_SHA256}))
        for bad in (
            {"version": "0.0.0-alpha.2", "openpgp_signature": SIG_SHA256},  # signature of another version
            {"version": "0.0.0-alpha.1"},
            {"version": " 0.0.0-alpha.1", "openpgp_signature": SIG_SHA256},
            {"version": "4.7.1rc1", "signatures": {}},  # the earlier unsigned format
            "0.0.0-alpha.1",
        ):
            with self.assertRaises(AnnouncementError):
                verify_announcement(bad)

    def test_versions(self):
        p = version_announcement.parse_electrin_version
        self.assertTrue(p("1.0.0-alpha.1") < p("1.0.0-beta.1") < p("1.0.0-beta.2") < p("1.0.0-rc.1")
                        < p("1.0.0") < p("1.0.1") < p("1.1.0") < p("2.0.0"))
        self.assertIsNone(p("4.7.1rc1"))
        self.assertIsNone(p("1.0"))
        self.assertTrue(version_announcement.is_newer("1.0.0", "1.0.0-beta.1"))
        self.assertFalse(version_announcement.is_newer("1.0.0-beta.1", "1.0.0-beta.1"))
        self.assertFalse(version_announcement.is_newer("4.7.1rc1", "1.0.0-beta.1"))
        self.assertFalse(version_announcement.is_newer("0.0.0-alpha.1", "1.0.0-beta.1"))
