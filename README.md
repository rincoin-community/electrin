<p align="center">
  <img src="electrum/gui/icons/electrum_text.png" alt="Electrin" height="60">
  <br>
  <img src="electrum/gui/icons/Electrum_512.png" alt="Electrin logo" width="128">
</p>

<h1 align="center">Electrin — Lightweight Rincoin Wallet</h1>

```
Licence: MIT Licence
Author: Takologi
Language: Python (>= 3.10)
Homepage: https://electrin.net
Based on: Electrum by Thomas Voegtlin (https://electrum.org)
```

**Electrin** is a lightweight Rincoin wallet forked from
[Electrum](https://github.com/spesmilo/electrum), the widely trusted
Bitcoin wallet created by Thomas Voegtlin and the Electrum developers.
Electrin connects to [Fulcrum-rin](https://github.com/takologi/Fulcrum-rin)
servers and does not require running a full Rincoin node.

---

## Status

| Target | Status |
|--------|--------|
| Rincoin adaptation | done |
| Name & icon rebrand | done |
| Dark / light theme switching (no restart) | done |
| Windows | done |
| Linux (AppImage) | done |
| Android (APK) | done |
| iOS | planned |
| Preliminary alpha testing | done |
| Functional beta testing | done |
| Thorough release-grade testing | planned |

Rincoin adaptation details:

- [x] Currency units, blockchain parameters, consensus rules
- [x] Wallet address formats (P2PKH, P2SH, bech32 with `rin` HRP)
- [x] Fulcrum-rin server connection
- [x] Lightning support hidden (not applicable to Rincoin)
- [x] Block explorers updated
- [x] Height-840,000 transition of Rincoin Community Core 1.2.0: replay-protected signatures
      (`SIGHASH_FORKID`, fork ID 840) from block 840,000, confirmation prompt in the 10 blocks before it
- [x] Hardware wallets disabled (no device supports the replay-protected signatures)
- [x] Fiat exchange rates disabled (the inherited providers quote Bitcoin)

---

## Getting started

_(If you just want to run Electrin,
[download the latest release](https://github.com/takologi/electrin/releases).)_

Electrin itself is pure Python, and so are most of the required dependencies,
but not everything. The following sections describe how to run from source, but here
is a TL;DR:

```
$ sudo apt-get install libsecp256k1-dev
$ ELECTRUM_ECC_DONT_COMPILE=1 python3 -m pip install --user ".[gui,crypto]"
```

### Not pure-python dependencies

#### RinHash (Rincoin proof-of-work)

Rincoin uses RinHash (BLAKE3 → Argon2d → SHA3-256) for block hashing.
Two additional Python packages are required:

```
$ pip install blake3 argon2-cffi
```

`blake3` contains a compiled C extension; on most platforms a binary wheel is
available. If not, you will need a C compiler and Rust toolchain.
`argon2-cffi` also ships binary wheels; building from source requires
`libffi-dev`:

```
$ sudo apt-get install libffi-dev   # only needed if building argon2-cffi from source
```

Both packages are listed in `contrib/requirements/requirements.txt` and will
be installed automatically by `pip install .`.

#### Qt GUI

If you want to use the Qt interface, install the Qt dependencies:
```
$ sudo apt-get install python3-pyqt6
```

#### libsecp256k1

For elliptic curve operations,
[libsecp256k1](https://github.com/bitcoin-core/secp256k1)
is a required dependency.

If you "pip install" Electrin, by default libsecp will get compiled locally,
as part of the `electrum-ecc` dependency. This can be opted-out of,
by setting the `ELECTRUM_ECC_DONT_COMPILE=1` environment variable.
For the compilation to work, besides a C compiler, you need at least:
```
$ sudo apt-get install automake libtool
```
If you opt out of the compilation, you need to provide libsecp in another way, e.g.:
```
$ sudo apt-get install libsecp256k1-dev
```

#### cryptography

Due to the need for fast symmetric ciphers,
[cryptography](https://github.com/pyca/cryptography) is required.
Install from your package manager (or from pip):
```
$ sudo apt-get install python3-cryptography
```


### Running from tar.gz

If you downloaded the official package (tar.gz), you can run
Electrin from its root directory without installing it on your
system; all the pure python dependencies are included in the 'packages'
directory. To run Electrin from its root directory, just do:
```
$ ./run_electrin
```

You can also install Electrin on your system, by running this command:
```
$ sudo apt-get install python3-setuptools python3-pip
$ python3 -m pip install --user .
```

This will download and install the Python dependencies used by
Electrin instead of using the 'packages' directory.
It will also place an executable named `electrin` in `~/.local/bin`,
so make sure that is on your `PATH` variable.


### Development version (git clone)

_(For OS-specific instructions, see [here for Windows](contrib/build-wine/README_windows.md),
and [for macOS](contrib/osx/README_macos.md))_

Check out the code from GitHub:
```
$ git clone https://github.com/takologi/electrin.git
$ cd electrin
$ git submodule update --init
```

Run install (this should install dependencies):
```
$ python3 -m pip install --user -e .
```

Create translations (optional):
```
$ sudo apt-get install gettext
$ ./contrib/locale/build_locale.sh electrum/locale/locale electrum/locale/locale
```

Finally, to start Electrin:
```
$ ./run_electrin
```

### Run tests

Run unit tests with `pytest`:
```
$ pytest tests -v
```
(can be parallelized with `-n auto` option, using [`pytest-xdist`](https://github.com/pytest-dev/pytest-xdist) plugin)

To run a single file, specify it directly like this:
```
$ pytest tests/test_bitcoin.py -v
```

## Creating Binaries

- [Linux (tarball)](contrib/build-linux/sdist/README.md)
- [Linux (AppImage)](contrib/build-linux/appimage/README.md)
- [macOS](contrib/osx/README.md)
- [Windows](contrib/build-wine/README.md)
- [Android](contrib/android/Readme.md)

All release targets except macOS are built locally with `contrib/release_build.sh`, or on GitHub
with the manually started workflow **Build** (`.github/workflows/build.yml`), which also writes
`SHA256SUMS.txt`, signs it and the update announcement when the signing secrets are set (see the
header of the workflow), and can create a draft release.


## Upstream Credit

Electrin is a fork of [Electrum](https://github.com/spesmilo/electrum),
created by **Thomas Voegtlin** and maintained by the
[Electrum developers](https://github.com/spesmilo/electrum/blob/master/AUTHORS).
We are deeply grateful for their work in building the premier lightweight
Bitcoin wallet — without it, Electrin would not exist.

See the [LICENCE](LICENCE) file for the full MIT licence text, which
covers both the original Electrum code and the Electrin modifications.


## Contributing

Any help testing the software, reporting or fixing bugs, reviewing pull requests
and recent changes, writing tests, or helping with outstanding issues is very welcome.
Implementing new features, or improving/refactoring the codebase, is of course
also welcome, but to avoid wasted effort, especially for larger changes,
we encourage discussing these on the issue tracker first.

Development discussion: [GitHub Issues](https://github.com/takologi/electrin/issues)


---

## TODO

Consolidated list of open items tracked in code comments (`TODO [TAG]`).
Each item references the source file(s) where the matching code comment lives.

### Security & Infrastructure

| Tag | Summary | Files |
|-----|---------|-------|
| `UPDATE-CHECK` | The checker queries `https://electrin.net/version` and verifies the OpenPGP signature of the announcement against the pinned release key (`electrum/version_announcement.py`); it stays disabled until electrin.net serves an announcement signed with `contrib/sign_version_announcement.sh`. | `electrum/gui/qt/update_checker.py`, `electrum/gui/qt/main_window.py` |
| `SECURITY` | The contact key listed in SECURITY.md (`pubkeys/takologi.asc`) differs from the release signing key (`pubkeys/rincoin-community-security.asc`); decide which one is the contact key. | `SECURITY.md` |
| `CRASH-REPORTER` | Deploy crash-report endpoint on electrin.net, set `report_server`, test end-to-end. | `electrum/base_crash_reporter.py` |
| `LABELS-SYNC` | Deploy an Electrin-owned labels-sync server, update `target_host`, remove disable guard. | `electrum/plugins/labels/labels.py` |

### Chain & Wallet

| Tag | Summary | Files |
|-----|---------|-------|
| `CHECKPOINTS` | Generate checkpoints.json from Rincoin Core RPC (`python3 contrib/generate_checkpoints.py`). Without checkpoints, a malicious server can serve a fabricated header chain. | `electrum/constants.py`, `contrib/generate_checkpoints.py` |
| `SEED-PREFIX` | Decide whether to adopt unique seed prefixes before stable release to prevent cross-chain seed confusion with Electrum. | `electrum/version.py` |

### Branding

| Tag | Summary | Files |
|-----|---------|-------|
| `BRANDING` | Remaining "Electrum" references in internal class names (`ElectrumWindow`, `ElectrumGui`, `QElectrumApplication`, `ElectrumItemDelegate`, `BaseElectrumGui`, `ElectrumTranslator`). Renaming these is RISKY — requires updating 100+ import sites, config keys, and plugin interfaces. Defer until a dedicated refactor. | `electrum/gui/qt/__init__.py`, `electrum/gui/qt/main_window.py`, `electrum/gui/qt/my_treeview.py` |
| `BRANDING` | Consider adding a "Rincoin Whitepaper" link in Help menu (replaced Bitcoin Paper). | `electrum/gui/qt/main_window.py` |
| `BRANDING` | `electrum/` package directory still named `electrum`. Renaming it would break every import in the codebase. Keep as-is; the `setup.py` `name="Electrin"` and entry script `electrin` handle user-facing naming. | `setup.py`, `electrum/` |

### Build & CI

| Tag | Summary | Files |
|-----|---------|-------|
| `CI` | Regtest tests need rincoind + Fulcrum-rin (currently use bitcoind + electrumx). | `.cirrus.yml` |
| `CI` | Crowdin locale task references upstream project and `master` branch. | `.cirrus.yml` |
| `CI` | Windows build `CIRRUS_WORKING_DIR` path matches upstream Dockerfile; rename together. | `.cirrus.yml`, `contrib/build-wine/Dockerfile` |
| `CI` | Build tasks (Windows, AppImage, Android) need testing with Electrin branding. | `.cirrus.yml`, `contrib/` |

### Exchange Rates

Fiat exchange rates are disabled on all Rincoin networks (`HAS_FX_RATES = False` in
`electrum/constants.py`): the inherited providers quote Bitcoin, not Rincoin.

| Tag | Summary | Files |
|-----|---------|-------|
| `EXCHANGE` | Re-enable fiat rates with Rincoin-quoting providers only, after checking their data quality. | `electrum/constants.py`, `electrum/exchange_rate.py` |
| `EXCHANGE` | CoinPaprika integration added (free API, no key). Verify `rin-rincoin` coin ID once Rincoin is listed. | `electrum/exchange_rate.py` |
| `EXCHANGE` | LiveCoinWatch integration added (requires `LIVECOINWATCH_API_KEY` env var). Verify `RIN` code once listed. | `electrum/exchange_rate.py` |

### Server Diversity

| Tag | Summary | Files |
|-----|---------|-------|
| `SERVERS` | Three Fulcrum-rin servers (`peer1`–`peer3.rincoin.tech`), all run by one operator. Goal: a wider network of independent operators. The servers must run Rincoin Community Core 1.2.0 before block 840,000, since Electrin follows the chain of the server it is connected to. | `electrum/chains/rincoin/servers.json` |


## Licence

MIT — see [LICENCE](LICENCE) for details.
