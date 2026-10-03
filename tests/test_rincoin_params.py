# -*- coding: utf-8 -*-
#
# Electrum-RIN – Rincoin-specific parameter and encoding tests
# Phase 2 test gate.
#
# Test vectors computed from Rincoin Core chainparams.cpp and
# cross-checked against the running Fulcrum-RIN server.
#
# Private keys used are deterministic test-only values; they should NEVER
# hold real funds.

import hashlib
import unittest

import electrum_ecc as ecc

from electrum import bitcoin, constants, segwit_addr
from electrum.bitcoin import (
    address_to_script,
    address_to_scripthash,
    hash160_to_p2pkh,
    hash160_to_p2sh,
    is_address,
    is_b58_address,
    is_segwit_address,
    pubkey_to_address,
    serialize_privkey,
    deserialize_privkey,
)

from . import ElectrumTestCase


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _h160_from_privkey(priv_hex: str) -> bytes:
    """Return HASH160 = RIPEMD160(SHA256(compressed_pubkey)) for a raw priv key."""
    priv_bytes = bytes.fromhex(priv_hex)
    pub = ecc.ECPrivkey(priv_bytes).get_public_key_bytes(compressed=True)
    sha = hashlib.sha256(pub).digest()
    return hashlib.new('ripemd160', sha).digest()


# ---------------------------------------------------------------------------
# Test vectors (computed with RincoinMainnet active)
#
# Key 1: privkey = 0x01 * 32  (canonical "all-ones" BIP-32 test key)
# Key 2: privkey = 0x0c28fca386c7a227600b2fe50b7cae11ec86d3bf1fbe471be89827e19d72aa1d
# ---------------------------------------------------------------------------

_PRIV1 = '01' * 32
_PRIV2 = '0c28fca386c7a227600b2fe50b7cae11ec86d3bf1fbe471be89827e19d72aa1d'

VECTORS = [
    {
        'privkey': _PRIV1,
        'pubkey':  '031b84c5567b126440995d3ed5aaba0565d71e1834604819ff9c17f5e9d5dd078f',
        'p2pkh':   'RLNcgZpJgK6Uh3zXgkm2z7As5nJJVt6HXr',
        'p2sh':    'r9svCrtrPFHfuRiGiP8ByLLbqLp2mkLf1y',
        'p2wpkh':  'rin1q0xcqpzrky6eff2g52qdye53xkk9jxkvrfmv3j4',
        'wif':     'p2pkh:Up3VgAKQio8guDjySfZTAnh8RbBZmdLt42AbuvVMB7SRabip7y9r',
        # scripthash = SHA256(scriptPubKey), reversed — Electrum/Fulcrum convention
        'sh_p2pkh':  '3f3a51af7593482038529b8f4338f0ab068b9e52489971ad4052ed7f9d341b6f',
        'sh_p2wpkh': '034d384e7bb98692522016f8d99b0c07cd4b50ef149dcfa1ba399156b089439f',
    },
    {
        'privkey': _PRIV2,
        'pubkey':  '02d0de0aaeaefad02b8bdc8a01a1b8b11c696bd3d66a2c5f10780d95b7df42645c',
        'p2pkh':   'RV5gLjZiTyW2jTjVr5WSYMK9Ns6XcH2eyq',
        'p2sh':    'rHhJAxAR5g5f1XJ7eZe94nstuiT2fEidMy',
        'p2wpkh':  'rin1qmy63mjadtw8nhzl69ukdepwzsyvv4yex2phaqk',
        'wif':     'p2pkh:UpRBUQtkA5WqFnSztd7sCYyyhtd4aq6AggQ9sXFh2fXeSnLHtd3Z',
        'sh_p2pkh':  'e4f6742ca0c2dceef3d055333c7d318aa6d56b4016e5bfaf12a683bc0eee07a3',
        'sh_p2wpkh': '816948db53f7be553b73e8b98673a369f89a0dfaad64d2c586bbcc3a53f8cd1e',
    },
]

# Zero hash160 edge-case addresses (prefix bytes dominate)
ZERO_H160_P2PKH  = 'R9HC5WtHbpoa51NCUAz86XLCmGTbkf45NT'
ZERO_H160_P2SH   = 'r6Eb8FN9d1Xtmt1ZzBdtAJCynYS5jpWCRq'
ZERO_H160_P2WPKH = 'rin1qqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqmckj4t'


class RincoinNetworkBase(ElectrumTestCase):
    """Base that activates RincoinMainnet for the duration of each test."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Override whatever bitcoin net the base class set
        constants.RincoinMainnet.set_as_network()

    @classmethod
    def tearDownClass(cls):
        # Restore upstream default so subsequent test classes are unaffected
        constants.BitcoinMainnet.set_as_network()
        super().tearDownClass()


# ===========================================================================
# 1. Network constant correctness
# ===========================================================================

class TestRincoinNetworkConstants(RincoinNetworkBase):

    def test_addrtype_p2pkh(self):
        self.assertEqual(constants.net.ADDRTYPE_P2PKH, 60)

    def test_addrtype_p2sh(self):
        self.assertEqual(constants.net.ADDRTYPE_P2SH, 122)

    def test_wif_prefix(self):
        self.assertEqual(constants.net.WIF_PREFIX, 0xbc)  # 188

    def test_segwit_hrp(self):
        self.assertEqual(constants.net.SEGWIT_HRP, 'rin')

    def test_bolt11_hrp_matches_segwit(self):
        self.assertEqual(constants.net.BOLT11_HRP, constants.net.SEGWIT_HRP)

    def test_genesis(self):
        self.assertEqual(
            constants.net.GENESIS,
            '000096bdd6e4613ca89b074ebd6f609aba6fe3f868b34ee79380aa3bc7a8c9db',
        )

    def test_bip44_coin_type_sentinel(self):
        # 9555 is a placeholder — MUST be replaced with SLIP-0044 registered
        # value before public release.  If this test breaks, confirm the PR
        # merged and update constants.py + this assertion.
        self.assertEqual(constants.net.BIP44_COIN_TYPE, 9555)

    def test_testnet_constants(self):
        self.assertEqual(constants.RincoinTestnet.ADDRTYPE_P2PKH, 65)
        self.assertEqual(constants.RincoinTestnet.ADDRTYPE_P2SH, 127)
        self.assertEqual(constants.RincoinTestnet.WIF_PREFIX, 0xc1)  # 193, Core chain parameters
        self.assertEqual(constants.RincoinTestnet.SEGWIT_HRP, 'trin')
        self.assertEqual(
            constants.RincoinTestnet.GENESIS,
            '00009d5fbc8579e8b4292f1bab22437d9468c0cc615cb5b0242d8159b31760ad',
        )

    def test_regtest_constants(self):
        self.assertEqual(constants.RincoinRegtest.ADDRTYPE_P2PKH, 111)
        self.assertEqual(constants.RincoinRegtest.ADDRTYPE_P2SH, 196)
        self.assertEqual(constants.RincoinRegtest.SEGWIT_HRP, 'rrin')
        self.assertEqual(
            constants.RincoinRegtest.GENESIS,
            '7d2c8c57ce2597f86c9fe41f9865ad664b04d2aad4321fdaab48ed3da1805fe7',
        )

    def test_xpub_headers_same_as_bitcoin(self):
        """Rincoin Core reuses BTC xpub/xprv bytes — hardware-wallet compatibility."""
        self.assertEqual(
            constants.RincoinMainnet.XPUB_HEADERS['standard'],
            constants.BitcoinMainnet.XPUB_HEADERS['standard'],
        )
        self.assertEqual(
            constants.RincoinMainnet.XPRV_HEADERS['standard'],
            constants.BitcoinMainnet.XPRV_HEADERS['standard'],
        )


# ===========================================================================
# 2. P2PKH address encoding / recognition
# ===========================================================================

class TestRincoinP2PKHAddresses(RincoinNetworkBase):

    def test_p2pkh_address_starts_with_R(self):
        for v in VECTORS:
            with self.subTest(v['privkey'][:8]):
                self.assertTrue(
                    v['p2pkh'].startswith('R'),
                    f"P2PKH address should start with 'R', got: {v['p2pkh']}",
                )

    def test_p2pkh_address_from_hash160(self):
        for v in VECTORS:
            with self.subTest(v['privkey'][:8]):
                h160 = _h160_from_privkey(v['privkey'])
                addr = hash160_to_p2pkh(h160)
                self.assertEqual(addr, v['p2pkh'])

    def test_zero_h160_p2pkh(self):
        self.assertEqual(hash160_to_p2pkh(bytes(20)), ZERO_H160_P2PKH)
        self.assertTrue(ZERO_H160_P2PKH.startswith('R'))

    def test_is_address_accepts_p2pkh(self):
        for v in VECTORS:
            with self.subTest(v['p2pkh']):
                self.assertTrue(is_address(v['p2pkh']))
                self.assertTrue(is_b58_address(v['p2pkh']))

    def test_is_address_rejects_bitcoin_mainnet_p2pkh(self):
        # BTC mainnet P2PKH starts with '1' — should not be valid on Rincoin
        self.assertFalse(is_address('1A1zP1eP5QGefi2DMPTfTL5SLmv7Divf'
                                    'Na'))  # Genesis coinbase addr


# ===========================================================================
# 3. P2SH address encoding
# ===========================================================================

class TestRincoinP2SHAddresses(RincoinNetworkBase):

    def test_p2sh_address_starts_with_r(self):
        for v in VECTORS:
            with self.subTest(v['privkey'][:8]):
                self.assertTrue(
                    v['p2sh'].startswith('r'),
                    f"P2SH address should start with 'r', got: {v['p2sh']}",
                )

    def test_p2sh_address_from_hash160(self):
        for v in VECTORS:
            with self.subTest(v['privkey'][:8]):
                h160 = _h160_from_privkey(v['privkey'])
                redeem = bytes.fromhex('0014') + h160  # P2WPKH-in-P2SH witness program
                h160_2 = hashlib.new('ripemd160', hashlib.sha256(redeem).digest()).digest()
                addr = hash160_to_p2sh(h160_2)
                self.assertEqual(addr, v['p2sh'])

    def test_zero_h160_p2sh(self):
        self.assertEqual(hash160_to_p2sh(bytes(20)), ZERO_H160_P2SH)
        self.assertTrue(ZERO_H160_P2SH.startswith('r'))

    def test_is_address_accepts_p2sh(self):
        for v in VECTORS:
            with self.subTest(v['p2sh']):
                self.assertTrue(is_address(v['p2sh']))


# ===========================================================================
# 4. Bech32 (P2WPKH) address encoding
# ===========================================================================

class TestRincoinBech32Addresses(RincoinNetworkBase):

    def test_p2wpkh_starts_with_rin1(self):
        for v in VECTORS:
            with self.subTest(v['privkey'][:8]):
                self.assertTrue(
                    v['p2wpkh'].startswith('rin1'),
                    f"P2WPKH address should start with 'rin1', got: {v['p2wpkh']}",
                )

    def test_p2wpkh_from_pubkey(self):
        for v in VECTORS:
            with self.subTest(v['privkey'][:8]):
                addr = pubkey_to_address('p2wpkh', v['pubkey'])
                self.assertEqual(addr, v['p2wpkh'])

    def test_zero_h160_p2wpkh(self):
        zero_bech32 = segwit_addr.encode_segwit_address(
            constants.net.SEGWIT_HRP, 0, bytes(20))
        self.assertEqual(zero_bech32, ZERO_H160_P2WPKH)
        self.assertTrue(zero_bech32.startswith('rin1q'))

    def test_is_address_accepts_p2wpkh(self):
        for v in VECTORS:
            with self.subTest(v['p2wpkh']):
                self.assertTrue(is_address(v['p2wpkh']))
                self.assertTrue(is_segwit_address(v['p2wpkh']))

    def test_address_to_script_p2wpkh(self):
        """P2WPKH scriptPubKey must be OP_0 <20-byte-hash>."""
        for v in VECTORS:
            with self.subTest(v['p2wpkh']):
                script = address_to_script(v['p2wpkh'])
                self.assertTrue(script.startswith(b'\x00\x14'), script.hex())
                self.assertEqual(len(script), 22)

    def test_bech32_is_case_insensitive(self):
        addr = VECTORS[0]['p2wpkh']
        self.assertTrue(is_address(addr.upper()))


# ===========================================================================
# 5. WIF encoding / decoding
# ===========================================================================

class TestRincoinWIF(RincoinNetworkBase):

    def test_wif_decode_round_trip(self):
        for v in VECTORS:
            with self.subTest(v['privkey'][:8]):
                priv_bytes = bytes.fromhex(v['privkey'])
                wif = serialize_privkey(priv_bytes, compressed=True, txin_type='p2pkh')
                self.assertEqual(wif, v['wif'])
                # Decode and compare
                txin_type, decoded, compressed = deserialize_privkey(wif)
                self.assertEqual(decoded, priv_bytes)
                self.assertTrue(compressed)
                self.assertEqual(txin_type, 'p2pkh')

    def test_wif_prefix_byte_is_0xbc(self):
        """Rincoin compressed WIF must start with the prefix derived from 0xbc."""
        for v in VECTORS:
            with self.subTest(v['privkey'][:8]):
                # 0xbc + 32B key + 0x01 → base58check → starts with 'U' in Rincoin
                self.assertTrue(
                    v['wif'].startswith('p2pkh:U'),
                    f"WIF should start with 'p2pkh:U', got: {v['wif'][:10]}",
                )


# ===========================================================================
# 6. Scripthash derivation (Electrum / Fulcrum convention)
# ===========================================================================

class TestRincoinScripthash(RincoinNetworkBase):
    """
    Electrum scripthash = SHA256(scriptPubKey) with the 32 bytes reversed.
    This is what Fulcrum indexes and what blockchain.scripthash.* methods use.
    """

    def test_p2pkh_scripthash(self):
        for v in VECTORS:
            with self.subTest(v['privkey'][:8]):
                sh = address_to_scripthash(v['p2pkh'])
                self.assertEqual(sh, v['sh_p2pkh'])

    def test_p2wpkh_scripthash(self):
        for v in VECTORS:
            with self.subTest(v['privkey'][:8]):
                sh = address_to_scripthash(v['p2wpkh'])
                self.assertEqual(sh, v['sh_p2wpkh'])

    def test_scripthash_is_64_hex_chars(self):
        for v in VECTORS:
            with self.subTest(v['p2pkh']):
                sh = address_to_scripthash(v['p2pkh'])
                self.assertEqual(len(sh), 64)
                # must be valid hex
                int(sh, 16)


# ===========================================================================
# 7. address_to_script correctness
# ===========================================================================

class TestRincoinAddressToScript(RincoinNetworkBase):

    def test_p2pkh_script_structure(self):
        """OP_DUP OP_HASH160 <20B> OP_EQUALVERIFY OP_CHECKSIG — 25 bytes total."""
        for v in VECTORS:
            with self.subTest(v['p2pkh']):
                script = address_to_script(v['p2pkh'])
                self.assertEqual(len(script), 25, script.hex())
                self.assertEqual(script[0], 0x76)   # OP_DUP
                self.assertEqual(script[1], 0xa9)   # OP_HASH160
                self.assertEqual(script[2], 0x14)   # PUSH 20
                self.assertEqual(script[23], 0x88)  # OP_EQUALVERIFY
                self.assertEqual(script[24], 0xac)  # OP_CHECKSIG

    def test_p2sh_script_structure(self):
        """OP_HASH160 <20B> OP_EQUAL — 23 bytes total."""
        for v in VECTORS:
            with self.subTest(v['p2sh']):
                script = address_to_script(v['p2sh'])
                self.assertEqual(len(script), 23, script.hex())
                self.assertEqual(script[0], 0xa9)   # OP_HASH160
                self.assertEqual(script[1], 0x14)   # PUSH 20
                self.assertEqual(script[22], 0x87)  # OP_EQUAL

    def test_p2wpkh_script_structure(self):
        """OP_0 <20B> — 22 bytes."""
        for v in VECTORS:
            with self.subTest(v['p2wpkh']):
                script = address_to_script(v['p2wpkh'])
                self.assertEqual(len(script), 22, script.hex())
                self.assertEqual(script[0], 0x00)   # OP_0
                self.assertEqual(script[1], 0x14)   # PUSH 20


# ===========================================================================
# 8. Cross-network isolation
# ===========================================================================

class TestRincoinCrossNetworkIsolation(RincoinNetworkBase):
    """Rincoin addresses must not be accepted on Bitcoin mainnet and vice-versa."""

    _BTC_P2PKH    = '1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa'   # BTC genesis coinbase
    _BTC_P2SH     = '3J98t1WpEZ73CNmQviecrnyiWrnqRhWNLy'
    _BTC_P2WPKH   = 'bc1qar0srrr7xfkvy5l643lydnw9re59gtzzwf5mdq'

    def test_bitcoin_addresses_invalid_on_rincoin(self):
        # Already on RincoinMainnet via setUpClass
        for addr in [self._BTC_P2PKH, self._BTC_P2SH, self._BTC_P2WPKH]:
            with self.subTest(addr):
                self.assertFalse(
                    is_address(addr),
                    f"BTC address {addr!r} should not be valid on Rincoin",
                )

    def test_rincoin_addresses_invalid_on_bitcoin(self):
        constants.BitcoinMainnet.set_as_network()
        try:
            for v in VECTORS:
                for addr in [v['p2pkh'], v['p2sh'], v['p2wpkh']]:
                    with self.subTest(addr):
                        self.assertFalse(
                            is_address(addr),
                            f"Rincoin address {addr!r} should not be valid on BTC mainnet",
                        )
        finally:
            constants.RincoinMainnet.set_as_network()


if __name__ == '__main__':
    unittest.main()
