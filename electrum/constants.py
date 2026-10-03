# -*- coding: utf-8 -*-
#
# Electrum - lightweight Bitcoin client
# Copyright (C) 2018 The Electrum developers
#
# Permission is hereby granted, free of charge, to any person
# obtaining a copy of this software and associated documentation files
# (the "Software"), to deal in the Software without restriction,
# including without limitation the rights to use, copy, modify, merge,
# publish, distribute, sublicense, and/or sell copies of the Software,
# and to permit persons to whom the Software is furnished to do so,
# subject to the following conditions:
#
# The above copyright notice and this permission notice shall be
# included in all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
# EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
# MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
# NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS
# BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN
# ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN
# CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

import copy
import os
import json
from typing import Sequence, Tuple, Mapping, Type, List, Optional

from .lntransport import LNPeerAddr
from .util import inv_dict, all_subclasses, classproperty
from . import bitcoin


def read_json(filename, default=None):
    path = os.path.join(os.path.dirname(__file__), filename)
    try:
        with open(path, 'r') as f:
            r = json.loads(f.read())
    except Exception:
        if default is None:
            # Sometimes it's better to hard-fail: the file might be missing
            # due to a packaging issue, which might otherwise go unnoticed.
            raise
        r = default
    return r


def create_fallback_node_list(fallback_nodes_dict: dict[str, dict]) -> List[LNPeerAddr]:
    """Take a json dict of fallback nodes like: k:node_id, v:{k:'host', k:'port'} and return LNPeerAddr list"""
    fallback_nodes = []
    for node_id, address in fallback_nodes_dict.items():
        fallback_nodes.append(
            LNPeerAddr(host=address['host'], port=int(address['port']), pubkey=bytes.fromhex(node_id)))
    return fallback_nodes


GIT_REPO_URL = "https://github.com/takologi/electrin"
GIT_REPO_ISSUES_URL = "https://github.com/takologi/electrin/issues"
BIP39_WALLET_FORMATS = read_json('bip39_wallet_formats.json')


class AbstractNet:

    NET_NAME: str
    TESTNET: bool
    WIF_PREFIX: int
    ADDRTYPE_P2PKH: int
    ADDRTYPE_P2SH: int
    SEGWIT_HRP: str
    BOLT11_HRP: str
    GENESIS: str
    BLOCK_HEIGHT_FIRST_LIGHTNING_CHANNELS: int = 0
    # Set to False on networks that have no Lightning Network support.
    # When False, wallet.can_have_lightning() returns False unconditionally,
    # hiding all LN UI and preventing channel creation.
    HAS_LIGHTNING: bool = True
    # Whether fiat exchange rates can be shown. The inherited providers quote Bitcoin.
    HAS_FX_RATES: bool = True
    # Each subclass must set BIP44_COIN_TYPE to its SLIP-0044 registered coin
    # type. Rincoin is registered as 9555:
    # https://github.com/satoshilabs/slips/blob/master/slip-0044.md
    BIP44_COIN_TYPE: int
    LN_REALM_BYTE: int
    DEFAULT_PORTS: Mapping[str, str]
    LN_DNS_SEEDS: Sequence[str]
    XPRV_HEADERS: Mapping[str, int]
    XPRV_HEADERS_INV: Mapping[int, str]
    XPUB_HEADERS: Mapping[str, int]
    XPUB_HEADERS_INV: Mapping[int, str]
    # Replay protection of the Rincoin height-840,000 transition. From the activation
    # height every ECDSA signature has to carry SIGHASH_FORKID and the signature hash
    # is the BIP143 digest (also for pre-SegWit inputs) with the fork ID in the upper
    # bytes of the hash type. None on networks without such a rule.
    SIGHASH_FORK_ID: Optional[int] = None
    SIGHASH_FORK_HEIGHT: Optional[int] = None
    # (height, block time) of a block known at release time. Lets a signer without a network
    # connection bound the current height by the clock (see transaction.forkid_height_bounds).
    FORKID_HEIGHT_REFERENCE: Optional[Tuple[int, int]] = None

    @classmethod
    def max_checkpoint(cls) -> int:
        return max(0, len(cls.CHECKPOINTS) * 2016 - 1)

    @classmethod
    def rev_genesis_bytes(cls) -> bytes:
        return bytes.fromhex(cls.GENESIS)[::-1]

    @classmethod
    def set_as_network(cls) -> None:
        global net
        net = cls

    _cached_default_servers = None
    @classproperty
    def DEFAULT_SERVERS(cls) -> Mapping[str, Mapping[str, str]]:
        if cls.__dict__.get('_cached_default_servers') is None:  # per class: subclasses must not inherit the cache
            default_file = {} if cls.TESTNET else None  # for mainnet we hard-fail if the file is missing.
            d = read_json(os.path.join('chains', cls.NET_NAME, 'servers.json'), default_file)
            # sanity check
            for k, v in d.items():
                assert isinstance(v, dict), f'value for {k} not a dict in servers.json'
                assert all(isinstance(v2, str) for v2 in v.values()), f'non-str values for key {k} in servers.json'
            cls._cached_default_servers = d
        return copy.deepcopy(cls._cached_default_servers)

    _cached_fallback_lnnodes = None
    @classproperty
    def FALLBACK_LN_NODES(cls) -> Sequence[LNPeerAddr]:
        if cls.__dict__.get('_cached_fallback_lnnodes') is None:  # per class: subclasses must not inherit the cache
            default_file = {} if cls.TESTNET else None  # for mainnet we hard-fail if the file is missing.
            d = read_json(os.path.join('chains', cls.NET_NAME, 'fallback_lnnodes.json'), default_file)
            cls._cached_fallback_lnnodes = create_fallback_node_list(d)
        return cls._cached_fallback_lnnodes

    _cached_checkpoints = None
    @classproperty
    def CHECKPOINTS(cls) -> Sequence[Tuple[str, int]]:
        if cls.__dict__.get('_cached_checkpoints') is None:  # per class: subclasses must not inherit the cache
            default_file = [] if cls.TESTNET else None  # for mainnet we hard-fail if the file is missing.
            cls._cached_checkpoints = read_json(os.path.join('chains', cls.NET_NAME, 'checkpoints.json'), default_file)
        return cls._cached_checkpoints

    @classmethod
    def datadir_subdir(cls) -> Optional[str]:
        """The name of the folder in the filesystem.
        None means top-level, used by mainnet.
        """
        return cls.NET_NAME

    @classmethod
    def cli_flag(cls) -> str:
        """as used in e.g. `$ run_electrum --testnet4`"""
        return cls.NET_NAME

    @classmethod
    def config_key(cls) -> str:
        """as used for SimpleConfig.get()"""
        return cls.NET_NAME


class BitcoinMainnet(AbstractNet):

    NET_NAME = "mainnet"
    TESTNET = False
    WIF_PREFIX = 0x80
    ADDRTYPE_P2PKH = 0
    ADDRTYPE_P2SH = 5
    SEGWIT_HRP = "bc"
    BOLT11_HRP = SEGWIT_HRP
    GENESIS = "000000000019d6689c085ae165831e934ff763ae46a2a6c172b3f1b60a8ce26f"
    DEFAULT_PORTS = {'t': '50001', 's': '50002'}
    BLOCK_HEIGHT_FIRST_LIGHTNING_CHANNELS = 497000

    XPRV_HEADERS = {
        'standard':    0x0488ade4,  # xprv
        'p2wpkh-p2sh': 0x049d7878,  # yprv
        'p2wsh-p2sh':  0x0295b005,  # Yprv
        'p2wpkh':      0x04b2430c,  # zprv
        'p2wsh':       0x02aa7a99,  # Zprv
    }
    XPRV_HEADERS_INV = inv_dict(XPRV_HEADERS)
    XPUB_HEADERS = {
        'standard':    0x0488b21e,  # xpub
        'p2wpkh-p2sh': 0x049d7cb2,  # ypub
        'p2wsh-p2sh':  0x0295b43f,  # Ypub
        'p2wpkh':      0x04b24746,  # zpub
        'p2wsh':       0x02aa7ed3,  # Zpub
    }
    XPUB_HEADERS_INV = inv_dict(XPUB_HEADERS)
    BIP44_COIN_TYPE = 0
    LN_REALM_BYTE = 0
    LN_DNS_SEEDS = [
        'nodes.lightning.directory.',
        'lseed.bitcoinstats.com.',
        'lseed.darosior.ninja',
    ]

    @classmethod
    def datadir_subdir(cls):
        return None


class BitcoinTestnet(AbstractNet):

    NET_NAME = "testnet"
    TESTNET = True
    WIF_PREFIX = 0xef
    ADDRTYPE_P2PKH = 111
    ADDRTYPE_P2SH = 196
    SEGWIT_HRP = "tb"
    BOLT11_HRP = SEGWIT_HRP
    GENESIS = "000000000933ea01ad0ee984209779baaec3ced90fa3f408719526f8d77f4943"
    DEFAULT_PORTS = {'t': '51001', 's': '51002'}

    XPRV_HEADERS = {
        'standard':    0x04358394,  # tprv
        'p2wpkh-p2sh': 0x044a4e28,  # uprv
        'p2wsh-p2sh':  0x024285b5,  # Uprv
        'p2wpkh':      0x045f18bc,  # vprv
        'p2wsh':       0x02575048,  # Vprv
    }
    XPRV_HEADERS_INV = inv_dict(XPRV_HEADERS)
    XPUB_HEADERS = {
        'standard':    0x043587cf,  # tpub
        'p2wpkh-p2sh': 0x044a5262,  # upub
        'p2wsh-p2sh':  0x024289ef,  # Upub
        'p2wpkh':      0x045f1cf6,  # vpub
        'p2wsh':       0x02575483,  # Vpub
    }
    XPUB_HEADERS_INV = inv_dict(XPUB_HEADERS)
    BIP44_COIN_TYPE = 1
    LN_REALM_BYTE = 1
    LN_DNS_SEEDS = [  # TODO investigate this again
        #'test.nodes.lightning.directory.',  # times out.
        #'lseed.bitcoinstats.com.',  # ignores REALM byte and returns mainnet peers...
    ]


class BitcoinTestnet4(BitcoinTestnet):

    NET_NAME = "testnet4"
    GENESIS = "00000000da84f2bafbbc53dee25a72ae507ff4914b867c565be350b0da8bf043"
    LN_DNS_SEEDS = []


class BitcoinRegtest(BitcoinTestnet):

    NET_NAME = "regtest"
    SEGWIT_HRP = "bcrt"
    BOLT11_HRP = SEGWIT_HRP
    GENESIS = "0f9188f13cb7b2c71f2a335e3a4fc328bf5beb436012afca590b1a11466e2206"
    LN_DNS_SEEDS = []


class BitcoinSimnet(BitcoinTestnet):

    NET_NAME = "simnet"
    WIF_PREFIX = 0x64
    ADDRTYPE_P2PKH = 0x3f
    ADDRTYPE_P2SH = 0x7b
    SEGWIT_HRP = "sb"
    BOLT11_HRP = SEGWIT_HRP
    GENESIS = "683e86bd5c6d110d91b94b97137ba6bfe02dbbdb8e3dff722a669b5d69d77af6"
    LN_DNS_SEEDS = []


class BitcoinSignet(BitcoinTestnet):

    NET_NAME = "signet"
    BOLT11_HRP = "tbs"
    GENESIS = "00000008819873e925422c1ff0f99f7cc9bbb232af63a077a480a3633bee1ef6"
    LN_DNS_SEEDS = []


class BitcoinMutinynet(BitcoinTestnet):

    NET_NAME = "mutinynet"
    BOLT11_HRP = "tbs"
    GENESIS = "00000008819873e925422c1ff0f99f7cc9bbb232af63a077a480a3633bee1ef6"
    LN_DNS_SEEDS = []


# ---------------------------------------------------------------------------
# Rincoin network classes
# Source of truth: /home/tomas_admin/rincoin/src/chainparams.cpp
# Genesis hash confirmed from Fulcrum server.features (2025-07-17).
# ---------------------------------------------------------------------------

class RincoinMainnet(AbstractNet):
    """Rincoin mainnet – P2PKH "R...", bech32 "rin1...", native p2p port 9555."""

    NET_NAME = "rincoin"
    TESTNET = False
    WIF_PREFIX = 0xbc               # 188 – mainnet WIF prefix
    ADDRTYPE_P2PKH = 60             # produces "R..." legacy addresses
    ADDRTYPE_P2SH = 122             # produces "r..." P2SH addresses
    SEGWIT_HRP = "rin"
    BOLT11_HRP = SEGWIT_HRP
    GENESIS = "000096bdd6e4613ca89b074ebd6f609aba6fe3f868b34ee79380aa3bc7a8c9db"
    DEFAULT_PORTS = {'t': '50001', 's': '50002'}
    BLOCK_HEIGHT_FIRST_LIGHTNING_CHANNELS = 0
    # Rincoin has no Lightning Network — disable all LN functionality in the wallet.
    HAS_LIGHTNING = False
    # Rincoin: fiat rates are disabled; the inherited exchange-rate providers quote Bitcoin.
    HAS_FX_RATES = False

    # Rincoin Core reuses standard BTC xpub/xprv serialisation bytes so that
    # hardware wallets derive keys correctly.  The coin type in the BIP-44
    # derivation path (m/44'/COIN_TYPE'/…) is the only distinguishing factor.
    XPRV_HEADERS = {
        'standard':    0x0488ade4,  # xprv
        'p2wpkh-p2sh': 0x049d7878,  # yprv
        'p2wsh-p2sh':  0x0295b005,  # Yprv
        'p2wpkh':      0x04b2430c,  # zprv
        'p2wsh':       0x02aa7a99,  # Zprv
    }
    XPRV_HEADERS_INV = inv_dict(XPRV_HEADERS)
    XPUB_HEADERS = {
        'standard':    0x0488b21e,  # xpub
        'p2wpkh-p2sh': 0x049d7cb2,  # ypub
        'p2wsh-p2sh':  0x0295b43f,  # Ypub
        'p2wpkh':      0x04b24746,  # zpub
        'p2wsh':       0x02aa7ed3,  # Zpub
    }
    XPUB_HEADERS_INV = inv_dict(XPUB_HEADERS)

    # SLIP-0044 registered coin type: https://github.com/satoshilabs/slips/blob/master/slip-0044.md
    # (Note: ticker "RIN" is also used by Ringo at coin type 205 — unrelated, do not confuse.)
    BIP44_COIN_TYPE = 9555

    # Height-840,000 transition: fork ID 840 in every signature from block 840,000.
    SIGHASH_FORK_ID = 840
    SIGHASH_FORK_HEIGHT = 840_000
    # block 750,000 (2026-09-22), the assumevalid block of Rincoin Community Core 1.2.0
    FORKID_HEIGHT_REFERENCE = (750_000, 1_790_048_235)

    # PoW verification parameters (used by electrum/blockchain.py)
    MAX_TARGET = 0x0000ffff00000000000000000000000000000000000000000000000000000000  # compact: 0x1f00ffff
    # SPV wallets cannot independently compute the per-block DA target (DGW v3
    # requires 24 ancestor headers and changes every block from height 30000).
    # Setting this flag tells verify_header to trust the declared `bits` field
    # and only check that RinHash(header) ≤ bits_to_target(bits).  This is the
    # correct SPV security model and is immune to future DA algorithm changes.
    SPV_SKIP_DA_BITS_CHECK = True

    # TODO [SECURITY] — Checkpoints are currently EMPTY. Generate them with:
    #   python3 contrib/generate_checkpoints.py \
    #       --rpc-url http://user:pass@127.0.0.1:9555 \
    #       --output electrum/chains/rincoin/checkpoints.json
    # Without checkpoints, an attacker who controls the Electrum server can
    # serve a fabricated header chain. Checkpoints pin the first N blocks
    # and prevent header-chain replacement within that range.

    LN_REALM_BYTE = 0
    LN_DNS_SEEDS = []


class RincoinTestnet(AbstractNet):
    """Rincoin testnet – P2PKH "T...", bech32 "trin1...", native p2p port 19555."""

    NET_NAME = "rincoin-testnet"
    TESTNET = True
    WIF_PREFIX = 0xc1               # 193 – testnet WIF prefix (Core chain parameters)
    ADDRTYPE_P2PKH = 65             # produces "T..." legacy addresses
    ADDRTYPE_P2SH = 127             # produces "t..." P2SH addresses
    SEGWIT_HRP = "trin"
    BOLT11_HRP = SEGWIT_HRP
    GENESIS = "00009d5fbc8579e8b4292f1bab22437d9468c0cc615cb5b0242d8159b31760ad"
    DEFAULT_PORTS = {'t': '60001', 's': '60002'}

    XPRV_HEADERS = {
        'standard':    0x04358394,  # tprv
        'p2wpkh-p2sh': 0x044a4e28,  # uprv
        'p2wsh-p2sh':  0x024285b5,  # Uprv
        'p2wpkh':      0x045f18bc,  # vprv
        'p2wsh':       0x02575048,  # Vprv
    }
    XPRV_HEADERS_INV = inv_dict(XPRV_HEADERS)
    XPUB_HEADERS = {
        'standard':    0x043587cf,  # tpub
        'p2wpkh-p2sh': 0x044a5262,  # upub
        'p2wsh-p2sh':  0x024289ef,  # Upub
        'p2wpkh':      0x045f1cf6,  # vpub
        'p2wsh':       0x02575483,  # Vpub
    }
    XPUB_HEADERS_INV = inv_dict(XPUB_HEADERS)
    BIP44_COIN_TYPE = 1             # shared testnet coin type (BIP-44 convention)

    # Height-840,000 transition scaled to testnet: fork ID 840 from block 8,400.
    SIGHASH_FORK_ID = 840
    SIGHASH_FORK_HEIGHT = 8_400

    # Rincoin has no Lightning Network.
    HAS_LIGHTNING = False
    # Rincoin: fiat rates are disabled; the inherited exchange-rate providers quote Bitcoin.
    HAS_FX_RATES = False
    # PoW (TESTNET=True already bypasses PoW checks, but set consistently)
    MAX_TARGET = 0x0000ffff00000000000000000000000000000000000000000000000000000000
    SPV_SKIP_DA_BITS_CHECK = True

    LN_REALM_BYTE = 1
    LN_DNS_SEEDS = []


class RincoinRegtest(RincoinTestnet):
    """Rincoin regtest – bech32 "rrin1...", native p2p port 29555."""

    NET_NAME = "rincoin-regtest"
    WIF_PREFIX = 0xef               # 239 – same as BTC regtest (Core chain parameters)
    ADDRTYPE_P2PKH = 111            # same as BTC testnet / regtest
    ADDRTYPE_P2SH = 196
    SEGWIT_HRP = "rrin"
    BOLT11_HRP = SEGWIT_HRP
    GENESIS = "7d2c8c57ce2597f86c9fe41f9865ad664b04d2aad4321fdaab48ed3da1805fe7"
    DEFAULT_PORTS = {'t': '61001', 's': '61002'}
    LN_DNS_SEEDS = []

    # Height-840,000 transition scaled to regtest: fork ID 840 from block 840.
    SIGHASH_FORK_HEIGHT = 840


class RincoinPreview(RincoinTestnet):
    """Rincoin preview – the public rehearsal chain of the height-840,000 transition.

    P2PKH "P...", P2SH "p...", bech32 "prin1...", native p2p port 49555, RPC 49556.
    Extended keys: Core defines one pair, ppub/pprv, used here for the standard (p2pkh)
    script type. Electrin needs one prefix per script type to tell them apart; the
    other types keep the testnet SLIP-132 families (upub/Upub/vpub/Vpub), as regtest does.
    """

    NET_NAME = "rincoin-preview"
    WIF_PREFIX = 0xb8               # 184 (Core chain parameters)
    ADDRTYPE_P2PKH = 56             # produces "P..." legacy addresses
    ADDRTYPE_P2SH = 118             # produces "p..." P2SH addresses
    SEGWIT_HRP = "prin"
    BOLT11_HRP = SEGWIT_HRP
    GENESIS = "00004282aaa888c5b7a1bb210464788510d3c5976a8cec49061a3eb49d04ff33"
    DEFAULT_PORTS = {'t': '62001', 's': '62002'}
    LN_DNS_SEEDS = []

    XPRV_HEADERS = {
        'standard':    0x03e25946,  # pprv (Core chain parameters)
        'p2wpkh-p2sh': 0x044a4e28,  # uprv
        'p2wsh-p2sh':  0x024285b5,  # Uprv
        'p2wpkh':      0x045f18bc,  # vprv
        'p2wsh':       0x02575048,  # Vprv
    }
    XPRV_HEADERS_INV = inv_dict(XPRV_HEADERS)
    XPUB_HEADERS = {
        'standard':    0x03e25d80,  # ppub (Core chain parameters)
        'p2wpkh-p2sh': 0x044a5262,  # upub
        'p2wsh-p2sh':  0x024289ef,  # Upub
        'p2wpkh':      0x045f1cf6,  # vpub
        'p2wsh':       0x02575483,  # Vpub
    }
    XPUB_HEADERS_INV = inv_dict(XPUB_HEADERS)

    # Height-840,000 transition scaled to preview: fork ID 840 from block 840.
    SIGHASH_FORK_HEIGHT = 840

# ---------------------------------------------------------------------------
NETS_LIST = tuple(all_subclasses(AbstractNet))  # type: Sequence[Type[AbstractNet]]
NETS_LIST = tuple(sorted(NETS_LIST, key=lambda x: x.NET_NAME))

assert len(NETS_LIST) == len(set([chain.NET_NAME for chain in NETS_LIST])), "NET_NAME must be unique for each concrete AbstractNet"
assert len(NETS_LIST) == len(set([chain.datadir_subdir() for chain in NETS_LIST])), "datadir must be unique for each concrete AbstractNet"
assert len(NETS_LIST) == len(set([chain.cli_flag() for chain in NETS_LIST])), "cli_flag must be unique for each concrete AbstractNet"
assert len(NETS_LIST) == len(set([chain.config_key() for chain in NETS_LIST])), "config_key must be unique for each concrete AbstractNet"

# don't import net directly, import the module instead (so that net is singleton)
net = BitcoinMainnet  # type: Type[AbstractNet]
