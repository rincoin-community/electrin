# Security Policy

> **⚠ TESTING PHASE** — Electrin is currently in a testing phase.
> We **strongly recommend NOT using this wallet** for anything other than
> testing with **small amounts** of Rincoin.  There may be undiscovered
> bugs that could lead to loss of funds.

## Reporting a Vulnerability

To report security issues, send an email to the address listed below.
(Not for support. Support requests will be *ignored*.)

<!-- TODO [SECURITY] — Before leaving the testing phase:
     1. Generate a dedicated GPG key pair for the Electrin project
        (see "How to generate project GPG keys" below).
     2. Add additional maintainer keys as the team grows.
     3. Publish the public keys in the `pubkeys/` directory of this repo
        and on public keyservers.
-->

| Name      | Email                          | GPG fingerprint                                   |
|-----------|--------------------------------|---------------------------------------------------|
| Takologi  | takologi [AT] proton [DOT] me  | 588F 056A 90C0 D941 274F 6662 24DC 647F 06EE F1D9 |

### Release signing key

Releases and the in-app version announcement are signed with the OpenPGP key of
Rincoin Community Forge (the same key that signs Rincoin Community Core releases):

| Key | Fingerprint |
|-----|-------------|
| Rincoin Community Security <security@rincoin.tech> (primary) | FEE1 ACA5 2C65 FF3E BF31  818C B559 5E17 52BC 2A82 |
| signing subkey (ed25519) | ABB2 DF8B 79E8 A4E7 6139  4732 B3FF 4116 5803 42CB |

The public key is in `pubkeys/rincoin-community-security.asc`. Verify a download with
`gpg --verify SHA256SUMS.txt.asc SHA256SUMS.txt` and `sha256sum --check --ignore-missing SHA256SUMS.txt`.

### Upstream Electrum contacts (original project)

Electrin is forked from [Electrum](https://github.com/spesmilo/electrum).
If you believe a vulnerability also affects upstream Electrum, please
**also** report it to the original maintainers:

| Name        | Email                                  | GPG fingerprint                                   |
|-------------|----------------------------------------|---------------------------------------------------|
| ThomasV     | thomasv [AT] electrum [DOT] org        | 6694 D8DE 7BE8 EE56 31BE D950 2BD5 824B 7F94 70E6 |
| SomberNight | somber.night [AT] protonmail [DOT] com | 4AD6 4339 DFA0 5E20 B3F6 AD51 E7B7 48CD AF5E 5ED9 |

#### Where to find GPG keys

You can import a key by running the following command with that
individual's fingerprint: `gpg --recv-keys "<fingerprint>"`

Upstream Electrum public keys can also be found in the
[Electrum git repository](https://github.com/spesmilo/electrum),
in the top-level `pubkeys` folder.


-------------------
| DEVELOPER MEMOS |
-------------------

## How to generate project GPG keys

This section documents the procedure for creating the Electrin project
signing keys. These keys are used for:

- Signing release tarballs / binaries
- Signing version-announcement messages (for the update checker)
- Encrypted communication for security reports

### Step 1 — Generate a new GPG key pair

```bash
gpg --full-generate-key
```

Recommended settings:
- **Key type**: RSA and RSA (option 1)
- **Key size**: 4096 bits
- **Expiry**: 2 years (can be extended later)
- **Real name**: `Electrin Release Signing Key` (or your maintainer name)
- **Email**: the project email listed above

### Step 2 — Export the public key

```bash
# ASCII-armored export
gpg --armor --export "takologi@proton.me" > pubkeys/takologi.asc
```

### Step 3 — Publish the key

1. Commit `pubkeys/takologi.asc` to this repository.
2. Upload to public keyservers:
   ```bash
   gpg --keyserver hkps://keys.openpgp.org --send-keys "<YOUR_FINGERPRINT>"
   gpg --keyserver hkps://keyserver.ubuntu.com --send-keys "<YOUR_FINGERPRINT>"
   ```
3. Update the table at the top of this file with the full fingerprint.

### Step 4 — Back up the private key securely

```bash
# Export private key to an encrypted backup (store OFFLINE only)
gpg --armor --export-secret-keys "takologi@proton.me" > electrin-signing-key.private.asc
```

Store the backup on an encrypted USB drive or hardware security module.
**Never** commit private keys to the repository.

### Step 5 — Sign the version announcement (for the in-app update checker)

The in-app update checker fetches a JSON document from `https://electrin.net/version`:

```json
{
    "version": "1.0.0",
    "openpgp_signature": "-----BEGIN PGP SIGNATURE----- ..."
}
```

The signature is a detached OpenPGP signature over the version string (no trailing newline) by
the release signing subkey. Electrin pins that key in `electrum/version_announcement.py`
(`RELEASE_KEYS`, the public-key packet and its fingerprint) and verifies the signature itself
(`electrum/openpgp.py`), without a key ring or key server. When releasing a new version:

```bash
contrib/sign_version_announcement.sh 1.0.0 > version.json
```

and publish `version.json` as `src/content/version.json` of the electrin-web repository. A new
signing key must be added to `RELEASE_KEYS` in a release before announcements are signed with it.
