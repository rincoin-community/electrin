# Rincoin height-840,000 transition: how a signer decides the signature rules without a synced
# network (height bounds, PSBT height hint), the confirmation window before the transition
# (chain_milestones), and the refusal to sign with hardware keystores once the rule is in force.
import os
from unittest import mock

from electrum import constants, keystore, chain_milestones
from electrum.address_synchronizer import TX_HEIGHT_UNCONFIRMED
from electrum.fee_policy import FixedFeePolicy
from electrum.keystore import Hardware_KeyStore
from electrum.simple_config import SimpleConfig
from electrum.transaction import (
    PartialTransaction, PartialTxInput, PartialTxOutput, TxOutpoint, Transaction, ForkIdRegimeUnknown,
    FORKID_MIN_BLOCK_SECONDS, forkid_height_bounds, sighash_forkid_regime, sighash_forkid_active_for_signing,
    set_sighash_forkid_tip_height_source, set_sighash_forkid_height_lower_bound_source,
)
from electrum import wallet as wallet_module
from electrum.wallet import (
    Abstract_Wallet, ChainMilestoneConfirmationRequired, HardwareKeystoreCannotSignException,
)

from .test_rincoin_params import RincoinNetworkBase
from .test_wallet_vertical import WalletIntegrityHelper


REF_HEIGHT, REF_TIME = constants.RincoinMainnet.FORKID_HEIGHT_REFERENCE
FORK = 840_000


def time_at(height_upper_bound: int) -> int:
    """Clock time at which the mainnet reference block bounds the tip height at height_upper_bound."""
    return REF_TIME + (height_upper_bound - REF_HEIGHT) * FORKID_MIN_BLOCK_SECONDS


class TestForkIdHeightBounds(RincoinNetworkBase):

    def setUp(self):
        super().setUp()
        set_sighash_forkid_tip_height_source(None)

    def tearDown(self):
        set_sighash_forkid_tip_height_source(None)
        super().tearDown()

    def test_synced_tip_decides(self):
        set_sighash_forkid_tip_height_source(lambda: FORK - 2)
        self.assertIs(False, sighash_forkid_regime(stored_height=FORK + 5))  # the synced tip wins
        set_sighash_forkid_tip_height_source(lambda: FORK - 1)
        self.assertIs(True, sighash_forkid_regime())

    def test_reference_block_and_clock(self):
        self.assertEqual((REF_HEIGHT, REF_HEIGHT), forkid_height_bounds(now=REF_TIME))
        # far before the transition, the clock rules it out
        self.assertIs(False, sighash_forkid_regime(now=time_at(FORK - 2)))
        # once the clock can no longer rule it out, the regime is unknown
        self.assertIsNone(sighash_forkid_regime(now=time_at(FORK - 1)))
        self.assertIsNone(sighash_forkid_regime(now=time_at(FORK + 10_000)))
        with self.assertRaises(ForkIdRegimeUnknown):
            sighash_forkid_active_for_signing(now=time_at(FORK + 10_000))
        # a clock behind the reference block is not trusted for an upper bound
        self.assertEqual((REF_HEIGHT, None), forkid_height_bounds(now=REF_TIME - 1000))

    def test_stored_height_proves_activation(self):
        now = time_at(FORK + 10_000)
        self.assertIs(True, sighash_forkid_regime(stored_height=FORK - 1, now=now))
        self.assertIsNone(sighash_forkid_regime(stored_height=FORK - 2, now=now))

    def test_psbt_hint(self):
        hint_time = time_at(FORK + 10_000)
        # exported 100 blocks before the transition, signed 10 minutes later: still before
        self.assertIs(False, sighash_forkid_regime(psbt_hint=(FORK - 100, hint_time), now=hint_time + 600))
        # signed a day later: cannot tell any more
        self.assertIsNone(sighash_forkid_regime(psbt_hint=(FORK - 100, hint_time), now=hint_time + 86_400))
        # exported after the transition
        self.assertIs(True, sighash_forkid_regime(psbt_hint=(FORK + 3, hint_time), now=hint_time))

    def test_local_headers_as_lower_bound(self):
        # headers still catching up: the verified local height is a lower bound
        set_sighash_forkid_height_lower_bound_source(lambda: FORK + 2)
        try:
            self.assertIs(True, sighash_forkid_regime(now=time_at(FORK + 10_000)))
        finally:
            set_sighash_forkid_height_lower_bound_source(None)

    def test_networks_without_reference(self):
        constants.RincoinRegtest.set_as_network()
        try:
            self.assertIsNone(sighash_forkid_regime(now=10**10))
            self.assertIs(False, sighash_forkid_regime(psbt_hint=(500, 10**9), now=10**9 + 60))
            self.assertIs(True, sighash_forkid_regime(stored_height=839))
        finally:
            constants.RincoinMainnet.set_as_network()

    def test_psbt_hint_round_trip(self):
        txin = PartialTxInput(prevout=TxOutpoint(txid=os.urandom(32), out_idx=0))
        out = PartialTxOutput.from_address_and_value("RMFHsuzARbUB56FFzFYjtLQEWTPWH5fTVy", 1000)
        tx = PartialTransaction.from_io([txin], [out], locktime=0, version=2)
        self.assertIsNone(tx.get_forkid_height_hint())
        # offline: nothing is written
        self.assertIsNone(PartialTransaction.from_raw_psbt(tx.serialize_as_bytes()).get_forkid_height_hint())
        # online and synced: the tip height is written with the time
        set_sighash_forkid_tip_height_source(lambda: FORK - 7)
        with mock.patch('time.time', return_value=1_800_000_000):
            raw = tx.serialize_as_bytes()
        set_sighash_forkid_tip_height_source(None)
        self.assertEqual((FORK - 7, 1_800_000_000), PartialTransaction.from_raw_psbt(raw).get_forkid_height_hint())


class TestChainMilestones(RincoinNetworkBase):

    def tearDown(self):
        set_sighash_forkid_tip_height_source(None)
        super().tearDown()

    def test_window_840k(self):
        # the window covers next-block heights 839,990 .. 839,999
        self.assertEqual([], chain_milestones.signing_notices(tip_height=839_988))
        notices = chain_milestones.signing_notices(tip_height=839_989)
        self.assertEqual(1, len(notices))
        self.assertEqual('sighash-forkid-840', notices[0].milestone.key)
        self.assertEqual(10, notices[0].blocks_left)
        self.assertIn('840,000', notices[0].title())
        self.assertIn('840,000', notices[0].message())
        self.assertEqual(1, chain_milestones.signing_notices(tip_height=839_998)[0].blocks_left)
        self.assertEqual([], chain_milestones.signing_notices(tip_height=839_999))
        self.assertEqual([], chain_milestones.signing_notices(tip_height=900_000))

    def test_scaled_networks(self):
        for net, height in ((constants.RincoinTestnet, 8_400), (constants.RincoinRegtest, 840),
                            (constants.RincoinPreview, 840)):
            net.set_as_network()
            try:
                self.assertEqual([], chain_milestones.signing_notices(tip_height=height - 12))
                self.assertEqual(10, chain_milestones.signing_notices(tip_height=height - 11)[0].blocks_left)
                self.assertEqual([], chain_milestones.signing_notices(tip_height=height - 1))
            finally:
                constants.RincoinMainnet.set_as_network()
        constants.BitcoinMainnet.set_as_network()
        try:
            self.assertEqual([], chain_milestones.signing_notices(tip_height=839_995))
        finally:
            constants.RincoinMainnet.set_as_network()

    def test_reusable_for_another_height(self):
        later = chain_milestones.ChainMilestone(
            key='example',
            height_for_net=lambda net: {'rincoin': 2_000_000}.get(net.NET_NAME),
            warn_blocks_before=3,
            warn_blocks_after=2,
            title=lambda n: 'example',
            message=lambda n: f'{n.blocks_left} left',
        )
        ms = (later,) + chain_milestones.MILESTONES
        self.assertEqual([], chain_milestones.signing_notices(tip_height=1_999_995, milestones=ms))
        self.assertEqual(['example'], [n.milestone.key for n in
                                       chain_milestones.signing_notices(tip_height=1_999_996, milestones=ms)])
        self.assertEqual('0 left', chain_milestones.signing_notices(tip_height=2_000_000, milestones=ms)[0].message())
        self.assertEqual([], chain_milestones.signing_notices(tip_height=2_000_001, milestones=ms))
        constants.RincoinTestnet.set_as_network()
        try:
            self.assertEqual([], chain_milestones.signing_notices(tip_height=1_999_999, milestones=(later,)))
        finally:
            constants.RincoinMainnet.set_as_network()

    def test_bounds_only(self):
        # without a synced tip, a window the bounds do not rule out is reported
        notices = chain_milestones.signing_notices(stored_height=839_995, now=time_at(839_995))
        self.assertEqual(1, len(notices))
        self.assertIsNone(notices[0].blocks_left)
        self.assertIn('840,000', notices[0].message())
        self.assertEqual([], chain_milestones.signing_notices(now=time_at(800_000)))


class _FakeHardwareKeyStore(Hardware_KeyStore):
    """A hardware keystore over the wallet's own xpub, without a device or plugin."""
    hw_type = 'fake'

    def can_sign(self, tx, *, ignore_watching_only=False):
        return True

    def ready_to_sign(self):
        return True

    def sign_transaction(self, tx, password):
        raise AssertionError("a hardware keystore must not be asked to sign")

    def sign_message(self, *args, **kwargs):
        raise NotImplementedError()

    def decrypt_message(self, *args, **kwargs):
        raise NotImplementedError()


class TestWalletSigning840k(RincoinNetworkBase):

    def setUp(self):
        super().setUp()
        self.config = SimpleConfig({'electrum_path': self.electrum_path})

    def tearDown(self):
        set_sighash_forkid_tip_height_source(None)
        super().tearDown()

    def _funded_wallet_and_tx(self):
        ks = keystore.from_seed('bitter grass shiver impose acquire brush forget axis eager alone wine silver',
                                passphrase='', for_multisig=False)
        w = WalletIntegrityHelper.create_standard_wallet(ks, gap_limit=2, config=self.config)
        txin = PartialTxInput(prevout=TxOutpoint(txid=bytes.fromhex('11' * 32), out_idx=0))
        funding = PartialTransaction.from_io(
            [txin], [PartialTxOutput.from_address_and_value(w.get_receiving_address(), 1_000_000)],
            locktime=0, version=2)
        funding_tx = Transaction(funding.serialize_to_network(include_sigs=False))
        w.adb.receive_tx_callback(funding_tx, tx_height=TX_HEIGHT_UNCONFIRMED)
        outputs = [PartialTxOutput.from_address_and_value("RMFHsuzARbUB56FFzFYjtLQEWTPWH5fTVy", 250_000)]
        tx = w.make_unsigned_transaction(outputs=outputs, fee_policy=FixedFeePolicy(5000), rbf=True)
        return w, tx

    @mock.patch.object(Abstract_Wallet, 'save_db')
    async def test_confirmation_window(self, mock_save_db):
        w, tx = self._funded_wallet_and_tx()
        set_sighash_forkid_tip_height_source(lambda: 839_995)
        with self.assertRaises(ChainMilestoneConfirmationRequired) as ctx:
            w.sign_transaction(tx, password=None)
        self.assertIn('840,000', str(ctx.exception))
        self.assertFalse(tx.is_complete())
        # the GUI asked, the user confirmed
        w.sign_transaction(tx, password=None, ignore_warnings=True)
        self.assertTrue(tx.is_complete())
        self.assertEqual([0x01], tx.ecdsa_sighash_bytes())

    @mock.patch.object(Abstract_Wallet, 'save_db')
    async def test_regime_unknown_refuses(self, mock_save_db):
        w, tx = self._funded_wallet_and_tx()
        with mock.patch('time.time', return_value=time_at(FORK + 10_000)):
            with self.assertRaises(ForkIdRegimeUnknown):
                w.sign_transaction(tx, password=None)
            self.assertFalse(tx.is_complete())
            # a wallet that already saw the transition signs the new way
            w.db.put('stored_height', FORK + 5)
            w.sign_transaction(tx, password=None)
        self.assertEqual([0x41], tx.ecdsa_sighash_bytes())

    @mock.patch.object(Abstract_Wallet, 'save_db')
    async def test_hardware_keystore_refused_after_transition(self, mock_save_db):
        w, tx = self._funded_wallet_and_tx()
        fake = _FakeHardwareKeyStore({
            'xpub': w.keystore.xpub,
            'derivation': w.keystore.get_derivation_prefix(),
            'root_fingerprint': w.keystore.get_root_fingerprint(),
        })
        with mock.patch.object(w, 'get_keystores', return_value=[fake]):
            set_sighash_forkid_tip_height_source(lambda: FORK)
            with self.assertRaises(HardwareKeystoreCannotSignException) as ctx:
                w.sign_transaction(tx, password=None)
            self.assertIn('840,000', str(ctx.exception))
            self.assertIn(wallet_module.hardware_wallet_forkid_message(), str(ctx.exception))
            self.assertTrue(w.has_hardware_keystore())
