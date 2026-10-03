# Rincoin height-840,000 transition: replay-protected signatures (SIGHASH_FORKID, fork ID 840).
#
# Vectors: tests/rincoin_s6b_sighash.json is the signature-hash vector file of Rincoin
# Community Core (src/test/data/s6b_sighash.json): 144 vectors over one transaction for
# every hash type, both script versions and both activation states, plus two Bitcoin Gold
# mainnet transactions (fork ID 79). The rincoin-tx vector is test/util/data/
# txsignheight840000.json of the same source.
import copy
import json
import os

import electrum_ecc as ecc

from electrum import constants, bitcoin, descriptor, transaction
from electrum.transaction import (
    Transaction, PartialTransaction, PartialTxInput, PartialTxOutput, TxOutpoint, TxOutput, Sighash,
    sighash_forkid_active, set_sighash_forkid_tip_height_source,
)
from electrum.crypto import sha256d
from electrum.util import bfh

from . import ElectrumTestCase
from .test_rincoin_params import RincoinNetworkBase


VECTORS = os.path.join(os.path.dirname(os.path.realpath(__file__)), "rincoin_s6b_sighash.json")

# rincoin-tx -signheight=840000 ... sign=ALL (txsignheight840000.hex / .json)
RINCOIN_TX_WIF = "Utsv1mH55bbWfpseVqtcupbpeXdQyvaJjS3tPoGWVEVPkbATC9KD"
RINCOIN_TX_PREV_TXID = "6c2789243608b46f750f49ff24f6f79a78c3010f7e56951e045e5b7ea5d07bf7"
RINCOIN_TX_PREV_AMOUNT = 150_000_000
RINCOIN_TX_DEST = "RMFHsuzARbUB56FFzFYjtLQEWTPWH5fTVy"
RINCOIN_TX_HEX = (
    "0200000001f77bd0a57e5b5e041e95567e0f01c3789af7f624ff490f756fb408362489276c000000006a47304402206d98"
    "0302f492844f15ad99b9d998f8c88d392259ac9c6207113364d4c2fa21ea022065614adead6c5b7db3e26884e268ed801f"
    "591f0c20b8d4a8b53ca853a494d81a4121035d7fd5626462ae8ea61f621d76bfc359befaf851fedeba491b06a9aef04a13"
    "45ffffffff01a0860100000000001976a914834584e0afbd77db57fcf4a3a076b8d3e02aa6fb88ac00000000")
RINCOIN_TX_TXID = "224757cfe9e085eb7c2b566611f0c1a38fd8cd211b4c435bb8b77dd8ed9e7316"


def _preimage_for_vector(v: dict, fork_active: bool) -> bytes:
    tx = Transaction(v["tx"])
    tx.deserialize()
    ptx = PartialTransaction.from_tx(tx)
    txin = ptx.inputs()[v["input_index"]]
    script_code = bfh(v["script_code"])
    if v["sigversion"] == "witness_v0":
        spk = bfh(v["script_pubkey"]) if v.get("script_pubkey") else b"\x00\x14" + script_code[3:23]
        txin.witness_utxo = TxOutput(scriptpubkey=spk, value=v["amount"])
    else:
        txin._trusted_value_sats = v["amount"]
    txin.get_scriptcode_for_sighash = lambda: script_code
    txin.is_segwit = lambda guess_for_address=False: v["sigversion"] == "witness_v0"
    txin.is_taproot = lambda: False
    return ptx.serialize_preimage(v["input_index"], sighash=v["hash_type"], forkid_active=fork_active)


class TestRincoinForkIdVectors(RincoinNetworkBase):

    def setUp(self):
        super().setUp()
        with open(VECTORS) as f:
            self.vectors = json.load(f)

    def test_vector_file(self):
        self.assertEqual(146, len(self.vectors))

    def test_core_sighash_vectors(self):
        """Every vector Electrin can compute gives the digest of Core. The legacy (pre-SegWit)
        digest is only implemented for SIGHASH_ALL in Electrum, so legacy NONE/SINGLE/
        ANYONECANPAY vectors that are hashed the historical way are skipped; every vector
        with SIGHASH_FORKID in force is checked."""
        checked = skipped = 0
        for v in self.vectors:
            if v["kind"] != "vector":
                continue
            self.assertEqual(840, v["fork_id"])
            forkid = bool(v["hash_type"] & Sighash.FORKID)
            legacy_path = v["sigversion"] == "base" and not (forkid and v["fork_active"])
            if legacy_path and Sighash.base(v["hash_type"]) != Sighash.ALL:
                skipped += 1
                continue
            pre = _preimage_for_vector(v, v["fork_active"])
            self.assertEqual(v["sighash"], sha256d(pre).hex(), msg=str({k: v[k] for k in ("sigversion", "fork_active", "hash_type")}))
            if forkid and v["fork_active"]:
                # the preimage ends with the hash type carrying the fork ID, e.g. 41 48 03 00 for ALL
                self.assertEqual(v["hash_type"] | (840 << 8), int.from_bytes(pre[-4:], "little"))
            checked += 1
        self.assertEqual(45, skipped)
        self.assertEqual(99, checked)

    def test_bitcoin_gold_vectors(self):
        """Two Bitcoin Gold mainnet signatures (fork ID 79) verify with the same code."""
        for v in self.vectors:
            if v["kind"] != "bitcoin_gold":
                continue
            saved = constants.net.SIGHASH_FORK_ID
            constants.net.SIGHASH_FORK_ID = v["fork_id"]
            try:
                pre = _preimage_for_vector(v, True)
                self.assertEqual(v["sighash"], sha256d(pre).hex())
                pubkey = ecc.ECPubkey(bfh(v["pubkey"]))
                sig64 = ecc.ecdsa_sig64_from_der_sig(bfh(v["signature"])[:-1])
                self.assertTrue(pubkey.ecdsa_verify(sig64, sha256d(pre)))
            finally:
                constants.net.SIGHASH_FORK_ID = saved

    def test_rincoin_tx_vector(self):
        """Signing at the transition height gives the transaction rincoin-tx produces, byte for byte."""
        txin_type, privkey, compressed = bitcoin.deserialize_privkey(RINCOIN_TX_WIF)
        pub = ecc.ECPrivkey(privkey).get_public_key_bytes(compressed=compressed)
        txin = PartialTxInput(prevout=TxOutpoint(txid=bfh(RINCOIN_TX_PREV_TXID), out_idx=0))
        txin.script_descriptor = descriptor.PKHDescriptor(descriptor.PubkeyProvider.parse(pub.hex()))
        txin._trusted_value_sats = RINCOIN_TX_PREV_AMOUNT
        txin.nsequence = 0xffffffff
        out = PartialTxOutput.from_address_and_value(RINCOIN_TX_DEST, 100_000)
        tx = PartialTransaction.from_io([txin], [out], locktime=0, version=2)
        tx.sign({pub: privkey}, forkid_active=True)
        self.assertEqual(RINCOIN_TX_HEX, tx.serialize())
        self.assertEqual(RINCOIN_TX_TXID, tx.txid())
        self.assertEqual([0x41], tx.ecdsa_sighash_bytes())
        # Core's signature verifies only with the rule in force
        sig = bfh(RINCOIN_TX_HEX)[43:43 + 0x47]  # after version, count, prevout, script length, push
        self.assertEqual(0x30, sig[0])
        self.assertTrue(tx.verify_sig_for_txin(txin_index=0, pubkey_bytes=pub, sig=sig, forkid_active=True))
        self.assertFalse(tx.verify_sig_for_txin(txin_index=0, pubkey_bytes=pub, sig=sig, forkid_active=False))


class TestRincoinForkIdActivation(RincoinNetworkBase):

    def tearDown(self):
        set_sighash_forkid_tip_height_source(None)
        super().tearDown()

    def test_network_parameters(self):
        for net, height in ((constants.RincoinMainnet, 840_000), (constants.RincoinTestnet, 8_400),
                            (constants.RincoinRegtest, 840), (constants.RincoinPreview, 840)):
            self.assertEqual(840, net.SIGHASH_FORK_ID)
            self.assertEqual(height, net.SIGHASH_FORK_HEIGHT)
        for net in (constants.BitcoinMainnet, constants.BitcoinTestnet, constants.BitcoinRegtest):
            self.assertIsNone(net.SIGHASH_FORK_ID)
            self.assertIsNone(net.SIGHASH_FORK_HEIGHT)

    def test_activation_by_tip_height(self):
        # a signature made now can confirm in block tip + 1 at the earliest
        self.assertFalse(sighash_forkid_active(tip_height=839_998))
        self.assertTrue(sighash_forkid_active(tip_height=839_999))
        self.assertTrue(sighash_forkid_active(tip_height=840_000))
        set_sighash_forkid_tip_height_source(lambda: 839_998)
        self.assertFalse(sighash_forkid_active())
        set_sighash_forkid_tip_height_source(lambda: 839_999)
        self.assertTrue(sighash_forkid_active())
        set_sighash_forkid_tip_height_source(lambda: None)
        self.assertFalse(sighash_forkid_active())  # unknown height: historical signing, warning logged

    def test_sighash_validity(self):
        self.assertTrue(Sighash.is_valid(0x41))
        self.assertTrue(Sighash.is_valid(0xc3))
        self.assertFalse(Sighash.is_valid(0x40))
        self.assertFalse(Sighash.is_valid(0x41, is_taproot=True))
        self.assertEqual(Sighash.ALL, Sighash.base(0x41))
        constants.BitcoinMainnet.set_as_network()
        try:
            self.assertFalse(Sighash.is_valid(0x41))
        finally:
            constants.RincoinMainnet.set_as_network()


class TestRincoinForkIdRegimes(RincoinNetworkBase):
    """Signing, verification and re-signing on both sides of the transition."""

    def tearDown(self):
        set_sighash_forkid_tip_height_source(None)
        super().tearDown()

    def _p2wpkh_tx(self):
        priv = ecc.ECPrivkey.generate_random_key()
        pub = priv.get_public_key_bytes(compressed=True)
        desc = descriptor.WPKHDescriptor(descriptor.PubkeyProvider.parse(pub.hex()))
        txin = PartialTxInput(prevout=TxOutpoint(txid=os.urandom(32), out_idx=1))
        txin.script_descriptor = desc
        txin.witness_utxo = TxOutput(scriptpubkey=desc.expand().output_script, value=100_000_000)
        out = PartialTxOutput.from_address_and_value(RINCOIN_TX_DEST, 90_000_000)
        return PartialTransaction.from_io([txin], [out], locktime=0, version=2), pub, priv.get_secret_bytes()

    def test_sign_follows_tip_height(self):
        tx, pub, sec = self._p2wpkh_tx()
        set_sighash_forkid_tip_height_source(lambda: 839_998)
        old = copy.deepcopy(tx)
        old.sign({pub: sec})
        self.assertEqual([0x01], [old.inputs()[0].sigs_ecdsa[pub][-1]])
        set_sighash_forkid_tip_height_source(lambda: 839_999)
        new = copy.deepcopy(tx)
        new.sign({pub: sec})
        self.assertEqual([0x41], [new.inputs()[0].sigs_ecdsa[pub][-1]])
        # verification matrix
        sig_old, sig_new = old.inputs()[0].sigs_ecdsa[pub], new.inputs()[0].sigs_ecdsa[pub]
        self.assertTrue(tx.verify_sig_for_txin(txin_index=0, pubkey_bytes=pub, sig=sig_old, forkid_active=False))
        self.assertFalse(tx.verify_sig_for_txin(txin_index=0, pubkey_bytes=pub, sig=sig_old, forkid_active=True))
        self.assertFalse(tx.verify_sig_for_txin(txin_index=0, pubkey_bytes=pub, sig=sig_new, forkid_active=False))
        self.assertTrue(tx.verify_sig_for_txin(txin_index=0, pubkey_bytes=pub, sig=sig_new, forkid_active=True))

    def test_stale_signatures_are_dropped_and_resigned(self):
        tx, pub, sec = self._p2wpkh_tx()
        tx.sign({pub: sec}, forkid_active=False)
        self.assertTrue(tx.is_complete())
        self.assertEqual({}, tx.signatures_of_other_forkid_regime(forkid_active=False))
        self.assertEqual({0: [pub]}, tx.signatures_of_other_forkid_regime(forkid_active=True))
        self.assertEqual(1, tx.remove_signatures_of_other_forkid_regime(forkid_active=True))
        self.assertFalse(tx.is_complete())
        tx.sign({pub: sec}, forkid_active=True)
        self.assertTrue(tx.is_complete())
        self.assertEqual({}, tx.signatures_of_other_forkid_regime(forkid_active=True))
        # the same on a finalized (network-serialized) transaction
        raw = tx.serialize()
        self.assertEqual([0x41], Transaction(raw).ecdsa_sighash_bytes())
        self.assertEqual({0: [None]}, tx.signatures_of_other_forkid_regime(forkid_active=False))
        self.assertEqual(1, tx.remove_signatures_of_other_forkid_regime(forkid_active=False))
        self.assertFalse(tx.is_complete())
        tx.sign({pub: sec}, forkid_active=False)
        self.assertEqual([0x01], Transaction(tx.serialize()).ecdsa_sighash_bytes())

    def test_psbt_round_trip_keeps_forkid_sighash(self):
        tx, pub, sec = self._p2wpkh_tx()
        tx.inputs()[0].sighash = Sighash.ALL | Sighash.FORKID
        psbt = PartialTransaction.from_raw_psbt(tx.serialize_as_bytes(force_psbt=True))
        self.assertEqual(0x41, psbt.inputs()[0].sighash)
        psbt.inputs()[0].script_descriptor = tx.inputs()[0].script_descriptor
        psbt.sign({pub: sec}, forkid_active=True)
        self.assertEqual([0x41], Transaction(psbt.serialize()).ecdsa_sighash_bytes())


class TestSupplyLimit(ElectrumTestCase):

    def test_total_supply(self):
        self.assertEqual(168_000_000, bitcoin.TOTAL_COIN_SUPPLY_LIMIT_IN_BTC)


class TestRincoinPreviewKeys(ElectrumTestCase):

    def test_preview_extended_key_prefixes(self):
        from electrum.bip32 import BIP32Node
        constants.RincoinPreview.set_as_network()
        try:
            node = BIP32Node.from_rootseed(bytes(32), xtype='standard')
            self.assertTrue(node.to_xpub().startswith('ppub'))
            self.assertTrue(node.to_xprv().startswith('pprv'))
            self.assertEqual('standard', BIP32Node.from_xkey(node.to_xpub()).xtype)
            self.assertEqual(0x03e25d80, constants.net.XPUB_HEADERS['standard'])
            self.assertEqual(0x03e25946, constants.net.XPRV_HEADERS['standard'])
        finally:
            constants.BitcoinMainnet.set_as_network()
