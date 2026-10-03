# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Electrin is a Rincoin wallet forked from [Electrum](https://github.com/spesmilo/electrum) (main branch
`master`, which contains the historical `rincoin-bootstrap` branch plus later upstream sync passes; see
`UPSTREAM_SYNC.md`). The repository lives at `rincoin-community/electrin`. It speaks the
Electrum protocol (v1.4–1.6) to [Fulcrum-rin](https://github.com/takologi/Fulcrum-rin) servers — it does not
run a full Rincoin node. See `README.md` for user-facing status, install instructions, and the maintained
`TODO [TAG]` ledger (cross-referenced to source comments).

**Lightning is fully disabled for Rincoin.** `HAS_LIGHTNING = False` on both `RincoinMainnet` and
`RincoinTestnet` (`electrum/constants.py`), `wallet.py`'s `has_lightning()`/`_init_lnworker()` are gated
accordingly. Do not port, fix, or worry about Lightning-core or NWC-plugin upstream changes unless a
specific one turns out to affect a non-LN code path — treat that whole surface as dead code for this fork.

## Repo layout vs. upstream Electrum

This is a `git` fork with `upstream` = `spesmilo/electrum`. Rincoin-specific work lives in `electrum/`
alongside (not instead of) the inherited Electrum code — search `git log upstream/master..HEAD` to see only
this fork's own commits. Key Rincoin-specific additions:

- `electrum/constants.py` — `RincoinMainnet`/`RincoinTestnet` classes: `ADDRTYPE_P2PKH=60`,
  `ADDRTYPE_P2SH=122`, `WIF_PREFIX=188`, `SEGWIT_HRP="rin"`, standard BTC-style xpub/xprv headers,
  `BIP44_COIN_TYPE=9555` (SLIP-44 registered — do not confuse with ticker collision at coin type 205,
  which is Ringo, unrelated). `SPV_SKIP_DA_BITS_CHECK=True` because Rincoin's DGW v3 difficulty adjustment
  can't be independently verified by an SPV client.
- `electrum/rinhash.py` — RinHash PoW (BLAKE3 → Argon2d → SHA3-256) verification.
- Android build (`contrib/android/`) carries substantial custom p4a recipes for `blake3`/`argon2-cffi`
  (RinHash's non-pure-Python dependencies) — do not casually adopt upstream's Android/Qt toolchain bumps
  without checking these still build; they're a common conflict source.

## Source of truth for cross-wallet/cross-protocol compatibility

Electrin must stay wire-compatible with Rincoin's other wallets, all outside this repo:

- **`~/rincoin`** — Rincoin Community Core. Source of truth for consensus rules, address formats, RPC.
- **`~/komodo-coins-rin`** (local clone of `GLEECBTC/coins`) — the authoritative KDF coin registry. Rincoin
  has two entries: `RIN` (`m/44'/9555'`, legacy P2PKH) and `RIN-segwit` (`m/84'/9555'`, native segwit),
  both `pubtype 60`/`p2shtype 122`/`wiftype 188`/`bech32_hrp "rin"`/`segwit: true`. A single key is
  legitimately spendable as both `R…` and `rin1…` addresses.
- **`~/kdf-reloaded-public`** — KDF Reloaded, the reference for Komodo DeFi Framework behavior used here
  (e.g. `mm2src/crypto/src/privkey.rs`'s iguana-legacy vs. BIP39-HD seed handling — they use *different*
  string-normalization rules, which matters for any Electrin code that imports a KDF seed/passphrase).
  Do not read the upstream Komodo DeFi Framework source (`~/kdf-analysis-2022`,
  `GLEECBTC/komodo-defi-framework`) directly; its license does not allow reuse, and questions about its
  behavior go through the process described in `~/kdf-reloaded-public/AGENTS.md`.
- **`~/Fulcrum-rin`** — the Electrum-protocol server Electrin actually talks to. Already supports protocol
  1.6.0, matching `PROTOCOL_VERSION_MAX` here.

## Version identity

`electrum/version.py` defines two separate constants — **read the comment block above them before touching
either**:

- `ELECTRIN_VERSION` — Electrin's own release identity. Used by anything user-facing: About dialog, window
  title, `--version`/`version` RPC, crash reports, the update checker, and release/packaging tooling
  (`setup.py`, `contrib/android/buildozer_qml.spec`, `contrib/android/get_apk_versioncode.py`,
  `contrib/print_electrum_version.py`'s default). Bump on every Electrin release.
- `ELECTRUM_VERSION` — nearest upstream Electrum release actually merged into this fork. Used only for
  `electrum/plugin.py`'s `distutils.StrictVersion`-based plugin min/max version gating and the Electrum-
  protocol P2P user-agent string sent to Fulcrum-rin (`interface.py`) — both need a strict `X.Y.Z` form,
  which `ELECTRIN_VERSION`'s `-beta.N`/`-rc.N` suffixes don't satisfy. Bump only when re-syncing with
  upstream, not on every release. Never wire this into anything user-facing.
- `wallet_db.py`'s stored `first_electrum_version_used` DB field is a deliberate exception, left on
  `ELECTRUM_VERSION` — it's an internal debug/diagnostic field, not user-facing.
- `get_apk_versioncode.py` requires `ELECTRIN_VERSION` to reduce to exactly 3 dot-delimited integer
  components after stripping an optional `-alpha.N`/`-beta.N`/`-rc.N` suffix — keep any future version
  scheme change compatible with that parser.
- `contrib/add_cosigner` and `contrib/make_download` are upstream Electrum's own multi-signer release-
  publishing scripts (SFTP to `electrum-downloads-airlock`, PRs against `electrum-signatures`,
  `electrum-web`'s `publish.sh`) — inherited wholesale, never adapted for Electrin, and out of scope for a
  simple version-constant swap (they also hardcode `Electrum-{version}.tar.gz` filenames throughout). Don't
  partially patch these; either fully adapt them to Electrin's actual (GitHub Releases-based) release
  process or leave them alone.

## Wizard architecture

`electrum/wizard.py` uses the **modern declarative navmap** (`navmap_merge()`, per-view `next`/`accept`/
`last` dict entries) — not the older `base_wizard.py` decorated-method flow. Both Qt (`gui/qt/wizard/`) and
QML (`gui/qml/qewizard.py` + `gui/qml/components/wizard/*.qml`) front ends render the same navmap. New
wizard entry points (e.g. wallet-recovery paths) are cheap to add here; if this ever needs a
`base_wizard.py`-style rewrite, something has gone very wrong.

`electrum/keystore.py`'s `Imported_KeyStore`/`electrum/wallet.py`'s `Imported_Wallet` key the keystore by
**pubkey** but the wallet's address bookkeeping (`_add_imported_addresses`, `wallet.py`) by **address** —
so importing the same private key twice under two txin_type labels (`"p2pkh:{WIF}"` and `"p2wpkh:{WIF}"`,
same WIF body) registers *both* the legacy and native-segwit address for one key through the existing
public `import_private_keys()` API. No new keystore code needed for that case.

## Build / test

No `WITH_*`-style CMake flags here (this is Python) — see `README.md`'s "Getting started" for the
non-pure-Python deps (`libsecp256k1`, `blake3`, `argon2-cffi`, PyQt6). Quick dev install:

```bash
ELECTRUM_ECC_DONT_COMPILE=1 python3 -m pip install --user ".[gui,crypto]"
```

Tests: `pytest tests -v` (see `.cirrus.yml` for the exact CI invocation, incl. coverage). Entry point:
`./run_electrum`.

## Ongoing work / where to pick this up

- **Height-840,000 transition** (Rincoin Community Core 1.2.0): from that height every ECDSA signature
  carries `SIGHASH_FORKID` (fork ID 840, BIP143 digest for every input). Specification:
  `rincoin-community/consensus-840k`, `technology/consensus-transition.md` §5. In this repo:
  `transaction.py` (`sighash_forkid_active()`), `chain_milestones.py` (pre-transition signing prompt),
  `tests/test_rincoin_forkid.py`. Hardware wallets are disabled because no device supports the fork ID.
- **Upstream sync state**: `UPSTREAM_SYNC.md` is the living ledger; `master` also carries
  `UPSTREAM_MERGE_TRIAGE_RINCOIN_BOOTSTRAP.md`, a 351-commit triage of `rincoin-bootstrap..upstream/master`.
  As of that audit, ~83 of those were already cherry-picked onto `rincoin-bootstrap` (including
  every non-LN "mandatory" security fix), matched by commit-subject heuristic, not content diff — treat
  that match as a starting point, not gospel. **Cherry-picking isolated upstream commits here is more
  conflict-prone than it looks even for "simple" fixes**, because the fork has skipped long runs
  of intervening upstream commits to the same files — a 3-way merge can conflict even when "our" side is
  just an older, otherwise-unmodified version of the file. Inspect the actual conflict before resolving;
  don't force it through.
- **KDF seed interoperability**: the live plan for letting Electrin recover a seed/passphrase from Komodo
  Wallet (both its BIP39-HD and legacy-iguana derivation modes) is tracked outside this repo — ask the user
  for the current plan-file/artifact link if picking this up fresh, since it moves between sessions.
- Local Claude Code plan history (if you have access to it): search
  `~/.claude/plans/electrin-upgrade-*.md` for the most recent research pass — it has the wizard/keystore
  findings above written up in full, plus the upstream-commit triage this file summarizes.
