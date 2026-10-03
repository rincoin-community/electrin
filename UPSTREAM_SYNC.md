# Upstream sync ledger

Electrin intentionally does not merge everything from upstream `spesmilo/electrum`. Lightning Network,
the NWC plugin, and LN-adjacent work (submarine swaps, anchor outputs, trampoline routing) are permanently
skipped — Rincoin has no Lightning support (`HAS_LIGHTNING = False`, see `CLAUDE.md`) and that whole
surface is dead code here. Because of that, **GitHub's "N commits behind" counter on this fork will never
trend to zero** — it counts raw commit reachability, not relevance, and upstream keeps adding Lightning
work we'll never take. That's expected, not a sign of neglect. What this file tracks instead is whether the
things that *do* matter are actually landing on a regular cadence.

## Policy

- **Security fixes: land immediately, ad hoc**, whenever noticed upstream — not batched into a sync pass.
  Small, standalone cherry-picks straight onto `master`, patch-released promptly.
- **Everything else relevant (bug fixes, wallet/core, tests, build): batched on a regular cadence.** No
  fixed interval is mandated here — match it to how often you're already touching the repo (monthly or
  quarterly is reasonable). Each pass re-runs the triage below against the *new* commits since the last
  pass, not the whole upstream history again.
- **Lightning core, NWC plugin, and LN-adjacent items are skipped without re-litigating each pass** — the
  policy is decided once (this file), not re-justified per commit.
- Each sync pass gets a dated entry below, appended, never overwritten — this file is the actual record of
  "we checked and here's what we decided," which is worth more than the raw diff-count badge.

### How to run a sync pass

```bash
git fetch upstream
git log --oneline <last-pass-anchor>..upstream/master   # new commits since last pass
```

Triage each new commit into:

1. **Immediately** — security/RPC hardening, or anything touching a file currently mid-refactor on a topic
   branch (land before that branch's work, to avoid rebasing around it later).
2. **Next batch, before the next release** — low-risk, non-urgent wallet/core/test fixes.
3. **Soon, can wait another release** — build/CI/packaging churn, isolated feature additions, no urgency.
4. **Needs its own decision** — Qt/QML styling churn (risks drifting from Electrin's branding, batch-review
   don't cherry-pick one at a time), Android/Qt-toolchain version bumps (conflict-prone against Electrin's
   custom RinHash/argon2/blake3 recipes — evaluate whether the bump is actually needed before touching it).
5. **Skip, not relevant** — Lightning/NWC/LN-adjacent (permanent policy), Bitcoin-specific chain
   data/checkpoints/server lists, upstream's own release-notes/docs.

Land buckets 1–3 as cherry-picks (`git cherry-pick -x <sha>` to keep the upstream SHA traceable in the
message). **Inspect the conflict before resolving one, even for "simple" commits** — `rincoin-bootstrap`
has skipped long runs of intervening upstream commits to the same files, so a 3-way merge can conflict even
when Electrin's side is just an older, otherwise-unmodified version of the file (see the `d34129ef` note in
Sync pass #1 below for a concrete example). Don't force a resolution you can't verify by reading the
result. A conflict can also mean upstream restructured a function across *several* commits, some of which
you don't want (e.g. the `9d9a503a9`/`08622c743` case in Sync pass #2 below, where a raw cherry-pick would
have silently dropped an Electrin-only feature) — when that happens, port the *effective* change by hand
instead of forcing the patch, and say so in the commit message.

**After landing a pass, always check the actual upstream release notes** (`RELEASE-NOTES` at
`upstream/master`) for the versions the pass covers, not just commit subjects — upstream sometimes
deliberately undersells a security-relevant commit in its own message (see Sync pass #2: the 4.8.1 notes
said "important security fixes, details disclosed later" days before this pass, and named the real PRs
under bland headings like "General"). Cross-referencing the release notes surfaces the ones a subject-line
or keyword scan alone would miss.

**End a pass by recording it against GitHub's ahead/behind counter**, once buckets 1–3 are actually landed
(not before — this step is a checkpoint of completed review, not a substitute for it):

```bash
git merge -s ours <upstream-sha-this-pass-covers-up-to> -m "chore: record upstream sync pass #N as reviewed (no content merged)"
```

This makes that upstream commit an ancestor without pulling in any of its file content (verify with
`git diff <before>..<after>` — should be empty). It resets the "N commits behind" badge to reflect only the
genuinely-unreviewed backlog after this point, and doesn't block cherry-picking anything from before it
later if a skipped item turns out to matter after all.

---

## Sync pass #1 — 2026-08-15

**Scope**: `rincoin-bootstrap..upstream/master` at the time of this audit — 351 commits (upstream base
`4.7.0` + 69 commits at fork point; upstream head at `b9be9749`). This pass is a first full audit of that
entire backlog, not an incremental one — future passes should be incremental against this date.

**Already landed**: ~85 of the 351 were already cherry-picked onto `rincoin-bootstrap` prior to this audit
(matched by commit-subject heuristic against `git log upstream/master..rincoin-bootstrap`, not a content
diff — treat as a strong starting point, not a guarantee; a future pass could re-verify with an actual diff
if it matters). This includes **every non-Lightning "mandatory" security item** found in the backlog: BIP70
removal, RPC-server lockdown (GUI-mode minimal RPC, `setconfig` rpcserver lock, restrictive unix-socket
permissions and umask), the CVE-2012-2459 verifier fix, and encrypting the keystore before adding it to the
wallet DB.

### Bucket 1 — land immediately (before the KDF seed-interop work)

Hand-picked, not mechanical — each one touches a file the in-flight KDF seed-interop effort is about to
modify:

- Stale SLIP-44 TODO in `constants.py` — resolved this pass (commit `84a135600`).
- **`d34129ef` "qml: deduplicate wallet name validation"** — **attempted and reverted this pass.** Touches
  `gui/qml/qewizard.py` and `gui/qml/components/wizard/WCWalletName.qml`, exactly the QML wizard files the
  KDF work will extend. The cherry-pick conflicts because it depends on a wallet-rename UI section in
  `WalletDetails.qml` that Electrin's copy doesn't have at all (never received the upstream commit that
  added it) — forcing the merge would have silently duplicated/corrupted that file. Needs a real look at
  why that upstream feature was never ported, not a blind conflict resolution. Left as bucket 4 until
  someone investigates the gap.
- Version-identity work (`ELECTRIN_VERSION`/`ELECTRUM_VERSION` split) — done this pass, not itself an
  upstream commit, but sequenced here because Stage 5 of the KDF plan bumps the wallet-file format version
  and should land on the real scheme, not the old placeholder string.

### Bucket 2 — after KDF, before the next release

Nothing here blocks KDF; land it once that work is merged, to harden the same files while still fresh:

- Re-verify the ~85 "already landed" matches above with an actual diff, not just subject-line matching.
- `a5f1a299` (regex literal-pipe fix), `b3808b79` (`GET_MASTER_FINGERPRINT` for hardware-wallet clients —
  relevant if a hardware wallet ever pairs with a KDF-HD-recovered Electrin wallet).
- Tests supporting the KDF test-oracle work (`toyserver` infra, `wallet_db` upgrader tests) — see the
  KDF plan's Stage 7.

### Bucket 3 — soon, can wait for another release

No interaction with KDF's files, no urgency:

| SHA | Subject | Category | Importance | Action |
|---|---|---|---|---|
| `0e7f7b30` | locale: rm llm_proofreader directory during build | Build / CI / packaging | optional | manual-port |
| `88f9c49a` | ci: add claude code code review | Build / CI / packaging | optional | manual-port |
| `85ea6af5` | ci: llm sec review: tweak trigger types | Build / CI / packaging | optional | manual-port |
| `1ba31448` | ci: bump code review ci claude version 4.6 -> 4.7 | Build / CI / packaging | optional | manual-port |
| `8e49eb80` | appimage: update Dockerfile dependencies | Build / CI / packaging | optional | manual-port |
| `44570bfa` | Bump minimum required version of ledger_bitcoin (build-time and runtime) | Build / CI / packaging | optional | manual-port |
| `1096ebcd` | build: update pinned ledger-bitcoin (partial rerun freeze_packages) | Build / CI / packaging | optional | manual-port |
| `0c52a01a` | ci: code review: pass commit messages into prompt context | Build / CI / packaging | optional | manual-port |
| `8c5af52c` | test_checksum_non_ascii | Tests only | optional | cherry-pick |
| `907ceb9f` | tests: timelock_recovery plugin: add test vector for checksum from bip | Tests only | optional | cherry-pick |
| `37159e47` | qml: 2fa: make it possible to copy 2fa secret | Wallet/core non-LN | optional | manual-port |
| `e71616e6` | update release notes for version 4.7.2 | Wallet/core non-LN | optional | cherry-pick |
| `a5f1a299` | pi: don't match literal \| char in regexes | Wallet/core non-LN | optional | cherry-pick |
| `b3808b79` | Using GET_MASTER_FINGERPRINT for Legacy Client to get the root public key fingerprint | Wallet/core non-LN | optional | cherry-pick |

Also two more from the `timelock_recovery` BIP-128 checksum cluster (`2f3f397a`, `c2f37294`) — real
correctness fix for a real (non-LN) plugin, low urgency; confirm the plugin is actually enabled for Rincoin
before scheduling.

### Bucket 4 — needs its own decision

- **`d34129ef`** (see Bucket 1 note above) — investigate the missing `WalletDetails.qml` rename-UI feature
  before deciding whether to port it.
- **The Android/Qt6.10/NDK28/p4a rebase wave** (`dba6b751`, `4d55b049`, `42472a1e`, `cdb5c0b8`, `32318987`,
  `74f3c042`, `854f95b7`, `c8f5798d`, `9d5b4a7c`, `7b7d7028`, `29b5e167`, `83b67700`, `96a3345a`, and
  related) — conflict-prone against Electrin's custom `blake3`/`argon2-cffi` p4a recipes. Decide whether
  Electrin actually needs Qt6.10 (e.g. Android-8-minimum-API compliance) before touching this; don't adopt
  it reflexively.
- **General Qt/QML styling and UX churn** — button-container refactors, dialog restyling, icon touch-ups,
  roughly 40 commits (see the full 351-commit source triage referenced below for the complete list — not
  reproduced here to keep this section scannable). Batch-review on its own schedule rather than
  cherry-picking individually; risks drifting from Electrin's Rincoin-branded theme one commit at a time.

### Bucket 5 — skip, not relevant

By category, with a few representative examples (not the full list — the point of this bucket is that it
doesn't need re-reading each pass):

- **Lightning core** (64) — e.g. `ddb01f53` lnpeer, `0b2c7a8a` lnsweep, and the rest of `electrum/lnworker.py`
  / `lnpeer.py` / `lnchannel.py` churn. Dead code path, `HAS_LIGHTNING = False`.
- **NWC plugin** (13) — e.g. `4c703ea2`, `0dc08fdf`. Requires Lightning; same reason.
- **LN-adjacent, miscategorized elsewhere** (~10) — submarine swaps (`88c7a731`, `022a1bf0`, `c4dcd85a`),
  LN RPC commands (`46803695` list_channels, `5a5c1e1f` list_channel_htlcs, `3399c20a`
  export_lightning_preimage), LN test suites (`db003257`, `e309f89a`, and the rest of `test_lnpeer.py`/
  `test_onion_message.py`/`test_lnrouter.py`). Same reason, despite upstream's own category labels.
- **Chain data / servers** (3) — Bitcoin checkpoint updates, personal `servers.json` entries. Not
  applicable; Rincoin's server list is Fulcrum-rin-based.
- **Docs / release notes** (7) — Electrum-branded release notes, not Electrin's.
- **All merge commits** (94) — no content of their own.

---

## Sync pass #2 — 2026-08-16

**Scope**: `b9be9749..upstream/master`, i.e. everything since Sync pass #1 — 351 commits, upstream head at
`a94e460b5` (upstream's own release `4.8.1`, dated 2026-08-10). GitHub's counter had reached "702 commits
behind" by the time this pass started; that figure is exactly `351 (pass #1's already-reviewed range,
never checkpointed) + 351 (this range)` — cherry-picks don't move `git merge-base`, so nothing about pass #1
having landed real work was reflected in that number until the pass #1 checkpoint below. **First action of
this pass was checkpointing pass #1** (see below), which is why this pass's own scope is only 351, not 702.

**The 4.8.1 release notes named the real bucket-1 list.** `RELEASE-NOTES` at `upstream/master` opens with
*"Security fixes and disclosures: This release contains important security fixes. Details will be disclosed
later."* — deliberately vague. Cross-referencing the itemized entries under the bland "General" and
"Electrum protocol" headings against their actual commits (not just scanning commit subjects for the word
"security") surfaced several real fixes a keyword scan alone missed entirely — notably the WIF/private-key
screenshot-protection extension and the wallet-DB JSON-patch escaping fix. **Always pull the actual release
notes for a pass's version range, not just the commit log** — see the policy note above.

### Bucket 1 — landed this pass

All 18 landed directly on `master` (17 commits + one, `8e5ea8e12`, confirmed already present under
different history and correctly skipped as a no-op):

| SHA | Subject | Note |
|---|---|---|
| `739cba5d7` | qml/android: protect WIF keys from screenshots in more places | Extends existing screenshot protection (`AddressDetails.qml`) to `ImportAddressesKeysDialog`, `SweepDialog`, `WalletDetails`, and the seed-display wizard screen; fixes a dialog-stacking bug in the original binding. |
| `671c08b6d` | add_tx_fee_from_server: check fee_sat type | Defends against a malformed/malicious fee value from an Electrum-protocol server. |
| `97007d9e0` | json_db: escape '\\' and '~' in json patch pointer | RFC 6901 escaping bug in the wallet-DB JSON-patch mechanism — unescaped input could target the wrong path. |
| `f75f19588` | json_db: set_modified after incomplete data | Wallet-DB recovery-path correctness fix. |
| `c9b2043dc` | jsondb: handle structural characters in data during recovery | Handles `{`/`}` appearing inside user-controlled *values* during truncated-file recovery, which could previously desync the recovery parser. Required manually adding a missing `Dict` import to `typing` that this commit's upstream context assumed was already present (it was, several commits earlier upstream, outside this pass's range) — see the amended commit. |
| `81030cb97` | json_db/config: sanitize logging of unserializable values | Privacy/security hygiene — avoids leaking secrets into logs. |
| `86745a772` + `954c4cf0e` + `99df67cd1` | interface: subscriptions strict checks / resource limits for non-main interfaces | The actual "hardening against resource exhaustion" cluster named in the 4.8.1 notes. Directly applicable — this is the exact layer Electrin uses to talk to Fulcrum-rin. `99df67cd1`'s test-file hunk conflicted (pure append, resolved by taking the addition); both new tests (`test_we_disconnect_on_incoming_request`, `test_we_disconnect_on_incoming_notification_spam`) verified passing after resolution. |
| `d8548dc9a` + `5de8ae887` + `add8e7148`\* | transaction/bitcoin.py: base43 DoS hardening | Closes an algorithmic-complexity (quadratic-time) DoS vector: `convert_raw_tx_to_hex()` no longer attempts an O(n²) base43 decode on inputs over 30,000 chars, and tries the cheap base64 check first. \*`add8e7148` is a **hand-port**, not a raw cherry-pick of `9d9a503a9`/`08622c743` — upstream's current version of this function no longer has the whitespace-stripping logic Electrin carries from an earlier-ported commit (`37db6ea7e`), so applying the patch as-is would have silently deleted that feature. Reconstructed the same net security effect while keeping it. |
| `fba8180c8` | trustedcoin: billing_index: mitigate against CPU DOS from malicious server | Real DoS fix in the 2FA plugin, which Electrin's wizard actively offers as a wallet-kind option. |
| `a4b7c800f` | wallet: check_sighash: handle unknown sighash gracefully | Avoids a crash/exception path on an exotic/malformed sighash. |
| `2c2a40b64` + `d74c9cec9` | docs: Coldcard Mk3 seed-entropy security notice | A real, disclosed hardware-wallet security issue — doc-only, cheap, should be visible to any Rincoin user pairing a Coldcard. |

### Bucket 2 — landed (11 of 15 planned)

- `88c7c6d50`, `ab6308d65` — server-list handling bugfix + sanity check.
- `d7500508f` — coldcard `get_soft_device_id()` missing-return bugfix (independent of the trezor wave below).
- `898a4c270` + `f3af41de4` — hw-wallet dialog reuse (generic `hw_wallet/qt.py`, applies to every hardware wallet, not trezor-specific).
- `b5a0af272` — `qml/2fa: partially reverse #10543`. Electrin's copy of `ShowConfirmOTP.qml` never had the *original* PR #10543 behavior this "reverts" (same class of gap as `d34129ef` in pass #1) — there was nothing to revert against, so the intended end-state (copy-to-clipboard, Android auto-open commented out) was added directly instead of applying the patch mechanically.
- `a266c7635`, `0ee0e390f` — tests covering the bucket-1 `maybe_load_incomplete_data` hardening.
- `c43cf8e46` — hidden-wallet-path privacy fix.
- `72507328f` — QML sign-message whitespace stripping (the smaller, self-contained PR #10787 predecessor to `4c3064f56` below).
- `05d589750` — trustedcoin logging reduction.

**Deferred to bucket 4** (discovered mid-cherry-pick, not from the original plan):
- `1547c5b4c`+`154d79ebb` (trezor Safe 7) and `071b1e24c` (trezor session handling) — both conflict because
  they assume the newer trezorlib API surface (`models`, `PassphraseSetting`, `AppManifest`, `get_client`,
  `trezorlib.thp.pairing`) from upstream's trezorlib 0.20.1 bump (`0f2fa36ec`, itself bucket-4 from pass #1's
  Android/toolchain wave). Cherry-picking the plugin-code commits without that dependency bump would leave
  imports Electrin's pinned trezorlib doesn't provide — this is a dependency-bump decision, not a patch.
- `4c3064f56` (`wallet: sign_message: strip whitespaces in GUIs, do not strip in CLI`) and `92e938f4b`
  (`decrypt_message` nicer error) — both assume `Abstract_Wallet.verify_message()` exists as a wallet method
  and `decrypt_message()`/`encrypt_message()` have keyword-only signatures Electrin doesn't have. This is a
  real, self-contained upstream refactor of the wallet message-crypto API that Electrin never received (predates
  this pass's range) — worth doing as its own scoped effort, not a drive-by pickup of a follow-on commit.

### Bucket 3 — landed (13 of 16 planned)

`a395da4e4`, `271f079dc` (verified safe — read the full diff before assuming "make sanitization optional"
weakens anything: it *moves* the existing whitespace-stripping into `tx_from_any` behind a `sanitize` flag
that user-facing/RPC call sites still default to `True`; only internal reloads of already-validated wallet-DB
data opt out, for performance), `3ae85eeff`, `3638934e2`, `6a89dd303` (a direct follow-up simplification to
the bucket-1 base43 fix — reconciled by hand to keep the security-relevant size cap while dropping the
now-redundant `raw_unstripped` variable, exactly as upstream intended), `920840a8c`, `cc5250821`, `bb1aaf60e`,
`38a2e1ab4`, `6571e479e`, `b199abba3` (turned out to be LN-only content that slipped through the
bucket-3 filter — harmless dead code for Rincoin since `HAS_LIGHTNING=False`, left in rather than unwound),
`74b0993aa`, `d5b7e743f`.

**Deferred to bucket 4:**
- `95317f4b8` (stale-comment fix) depends on a rename (`_paid_invoice_keys` → `_paid_invoice_keys_cache`)
  from an unported paid-invoice-caching feature (`d2d4251c8`/`63ee2f3a6`/`4f8972008`, not yet triaged).
- `7b4759c5b` (skip balance-delta calc for large tx-notification batches) is a follow-up optimization to
  `get_user_notifications_for_new_txns()`, a method Electrin doesn't have at all — its introducing commit
  (`03e95acc`/`2ea8d115`) was deliberately skipped as Qt/QML churn in pass #1. Bundle both together if this
  notification feature is ever adopted.

### Bucket 4 — needs its own decision

- **Upstream has fully migrated off Cirrus CI to GitHub Actions** (`a41c76f3f` removes `.cirrus.yml`
  entirely upstream; `b3986341b`/`ffdd1f42f`/`93acf9013`/`9e809f2b5`/`699603b06` add the GitHub Actions
  replacements). This is the single biggest structural finding of this pass: Electrin's own `.cirrus.yml`
  now tracks a CI system upstream itself has abandoned, so there's nothing more to sync there going
  forward — future upstream CI changes won't touch it. Separately notable: upstream's GitHub Actions setup
  now includes an **LLM-based automated security-review workflow on every PR**
  (`ddde0f09c`/`39cdb23e5`/`a6cfdc5b2`/`de7a8bdb3`/`87ca59e59`/`ed83982fe`/`1334146da`) — genuinely worth
  evaluating for this repo independent of the CI-platform question.
- **trezorlib 0.20.1 dependency bump** (`0f2fa36ec`) plus its three dependent plugin commits above
  (`1547c5b4c`, `154d79ebb`, `071b1e24c`) — bundle as one scoped upgrade.
- **Wallet message-crypto API refactor** (`4c3064f56`, `92e938f4b`, and whatever introduced
  `Abstract_Wallet.verify_message`/`encrypt_message` upstream before this pass's range) — bundle as one
  scoped effort; touches signing/verification/encryption, so worth its own careful review and test pass
  rather than folding into a routine sync.
- **Paid-invoice-key caching feature** (`d2d4251c8`/`63ee2f3a6`/`4f8972008`) and **large-batch tx-notification
  UX** (`03e95acc`/`2ea8d115`/`7b4759c5b`) — both real, self-contained features Electrin never received;
  evaluate as features, not sync-pass fodder.
- PyQt/Qt6.10 version pin (`33e67fdae`) — same open question as the Android/Qt6.10 wave from pass #1.
- General Qt/QML styling and UX churn (~35 commits, not enumerated here — see
  `UPSTREAM_MERGE_TRIAGE_RINCOIN_BOOTSTRAP.md`-style raw listing via `git log b9be9749..upstream/master --
  electrum/gui/qt electrum/gui/qml` if needed). Same guidance as pass #1: batch-review on its own schedule.
- Android build churn (openssl bump, p4a ref bump, target SDK 36) — same conflict-risk caveat against
  Electrin's custom recipes as pass #1.

### Bucket 5 — skip, not relevant

- **Lightning core** (89) and **NWC plugin** (6) — same permanent policy.
- `a10392325` ("wallet: don't remove ln xprv from wallet backup") — categorized as Wallet/core by subject
  matching, but is LN-specific content; no LN xprv exists in a Rincoin wallet.
- `fb9f6c871` ("increase ELECTRUM_VERSION to 4.8.0") — upstream's own version bump; not a cherry-pick
  target, already reflected by this session's own `ELECTRUM_VERSION` tracker update to `4.8.1`.
- `73e1e18fa` ("add builder keys for svanstaa") — upstream's own release-signing key management, not
  applicable (same reasoning as `contrib/add_cosigner` in `CLAUDE.md`).
- Chain data/servers (3), docs/release-notes (4), all merge commits (114).

### Checkpoint

Pass #1's range was checkpointed first, dropping the counter from 702 to 351:

```
git merge -s ours b9be9749   # records 6c1e08593..b9be9749 (pass #1) as reviewed, no content merged
```

Buckets 2 and 3 landed in a follow-up continuation of this same pass (24 of 31 originally-planned items;
7 more discovered mid-cherry-pick to be entangled with unported features and moved to bucket 4 — see the
bucket 2/3 sections above for exactly which and why). With buckets 1–3 now actually landed, pass #2 is
checkpointed the same way:

```
git merge -s ours a94e460b5   # records b9be9749..a94e460b5 (pass #2) as reviewed, no content merged
```

Everything remaining after this point is bucket 4 (needs a dedicated decision, not routine sync work) or
bucket 5 (permanently skipped) — the counter reflects that going forward, not raw upstream activity.

## Single picks outside a sync pass

| Date | Upstream commit | Why |
|---|---|---|
| 2026-10-03 | `fd6879401` contrib: build appimage: fetch ca-certificates from pinned sources | the AppImage build broke because the default Debian 11 sources stopped working (first CI build) |
| 2026-10-03 | `e3c0fa838` contrib: appimage: respect ELECBUILD_NOCACHE during runtime build | prerequisite of the next pick (same patch file) |
| 2026-10-03 | `ca8be6bb2` contrib: appimage: bump type2-runtime build env packages | the pinned Alpine packages of the type2-runtime build were no longer available |

---

## Reference

The complete commit-by-commit triage this pass was built from (all 351 rows, with the original
category/effort/confidence columns) is preserved in git history at
`UPSTREAM_MERGE_TRIAGE_RINCOIN_BOOTSTRAP.md` — recovered from a stray `origin/master` state during this
pass; see `git log --all -- UPSTREAM_MERGE_TRIAGE_RINCOIN_BOOTSTRAP.md` if the original per-commit detail
is needed for a specific SHA not called out above.
