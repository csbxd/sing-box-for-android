# Custom signed Android releases

This fork builds APKs from **an exact commit of `csbxd/sing-box/custom-dev`** and an exact Android source commit. It does not use the core repository's upstream Android submodule or download a prebuilt upstream core. The release workflow only builds `otherRelease` and `otherLegacyRelease`, verifies every APK's signer/version and debuggable flag, and publishes all four ABIs plus a universal APK for each flavor.

## One-time owner setup: new signing key

**Run these steps yourself on a trusted computer. Do not send the key or passwords to an assistant, paste them in chat, or commit them.** The setup script is supplied for owner execution only; it has not been run as part of configuring this repository.

1. Install a JDK with `keytool` and OpenSSL if they are not already available.
2. Clone this repository and inspect `.github/scripts/setup_android_signing.sh`.
3. Choose a private directory **outside the checkout**, then run:

   ```bash
   bash .github/scripts/setup_android_signing.sh "$HOME/private-android-signing"
   ```

   The directory must not already exist. The script creates a new RSA-4096 PKCS12 key with a random password. No secret values are printed. Keep an encrypted/offline backup of the directory and password. Losing this key prevents updates to previously signed installs.
4. Open [repository Actions secrets](https://github.com/csbxd/sing-box-for-android/settings/secrets/actions). Add these **repository secrets** yourself, using the entire corresponding file content:

   | GitHub secret | Local file |
   | --- | --- |
   | `ANDROID_KEYSTORE_BASE64` | `keystore-base64.txt` |
   | `ANDROID_KEYSTORE_PASSWORD` | `keystore-password.txt` |
   | `ANDROID_KEY_ALIAS` | `key-alias.txt` |
   | `ANDROID_KEY_PASSWORD` | `key-password.txt` |

5. Open [repository Actions variables](https://github.com/csbxd/sing-box-for-android/settings/variables/actions). Add the non-secret variable `ANDROID_SIGNING_CERT_SHA256` from `certificate-sha256.txt`. This pins the expected signer. The workflow refuses a different key even if Secrets are misconfigured. Later releases also reject a signer change from existing release metadata.
6. If this fork's Actions are disabled, enable them on its [Actions page](https://github.com/csbxd/sing-box-for-android/actions). Repository policy must permit the workflow's `contents: write` publish job. Other jobs have read-only permissions and checkouts do not retain credentials.

The checked-in upstream `app/release.keystore` is never used by this workflow. There is no unsigned/debug fallback. The plan fails before expensive builds if signing settings are missing. No key is generated in Actions and no private signing material is uploaded as an artifact.

The package ID is unchanged (`io.nekohasekai.sfa`). A new key cannot update an existing official/other-signer install in place. Export/back up profiles first; uninstalling a differently signed build can erase application data. All subsequent custom releases must reuse this new key.

## Run a release manually

Open [Custom signed Android release](https://github.com/csbxd/sing-box-for-android/actions/workflows/custom-android-release.yml), choose branch `dev`, and supply the full lowercase 40-character core commit. The commit must be reachable from `csbxd/sing-box` branch `custom-dev` and contain the `SING_BOX_BUILD_VERSION` build override. The selected `dev` commit is the Android source. The workflow reports the exact source commits in its plan, release notes, and `release-plan.json` asset.

Equivalent owner-run GitHub CLI command:

```bash
gh workflow run custom-android-release.yml --repo csbxd/sing-box-for-android --ref dev \
  -f core_commit=FULL_40_CHARACTER_CORE_COMMIT
```

## Direct GitHub connector trigger

For an authorized scheduled/direct GitHub process that cannot call workflow dispatch, create or update `.github/custom-release/request.json` on `dev` using the GitHub connector in a normal fast-forward commit:

```json
{
  "schema": 1,
  "source_sha": "FULL_40_CHARACTER_ANDROID_COMMIT",
  "core_sha": "FULL_40_CHARACTER_CORE_COMMIT"
}
```

Both values must be real lowercase SHA-1 commit IDs. The Android source must be an ancestor of the trigger commit and of `dev`; the core commit must be an ancestor of `custom-dev`. Requests execute through the GitHub connector and GitHub Actions only; no Work/Codex executor or cloud task is required. A request-file-only commit is excluded from the Android source fingerprint. This file is intentionally not created during setup, so configuration does not launch an unconfigured signed release. Existing identical JSON must not be rewritten just to create a build; re-run a failed workflow when appropriate. Never place secrets in the request.

## Versioning and immutability

- Enumerate actual published upstream **GitHub Releases**, including prereleases, from `SagerNet/sing-box`. Drafts and unrecognized version tags are excluded.
- Read the first SemVer heading in the exact core commit's `docs/changelog.md` as its source version. Select the highest SemVer published upstream Release with the **same numeric X.Y.Z series**. Numeric prerelease components sort numerically; stable sorts above prerelease. This matches the core release planner and deliberately does not require Release-tag ancestry, because upstream testing history may be rewritten. Fail closed if the series has no matching Release.
- An upstream `v1.15.0-alpha.9` base yields `1.15.0-alpha.9.c1`, `.c2`, etc. A stable `v1.15.0` base yields `1.15.0-c1`, `-c2`, etc. Stable custom builds are GitHub stable Releases despite the custom suffix. Git tags have a `v` prefix.
- The suffix increments over all existing matching tags/releases, including drafts. An unchanged Android+core source fingerprint produces a successful no-op, even if the upstream Release list changes. Build configuration is part of the source fingerprint; request-file contents in either repository are not.
- Android `versionCode` is one greater than the maximum of checked-in `VERSION_CODE` and every prior custom release/draft's recorded code. It never resets when the upstream base changes. The Android maximum is enforced.
- Custom APKs check this fork's releases, compare numeric `versionCode`, and select the appropriate universal APK. Noncustom builds keep their upstream update behavior. Android itself enforces installed-package signing-certificate compatibility.
- Runs are serialized without cancelling an in-progress release. Publication creates a new tag, creates a draft with verified artifacts, then publishes it. No force-push, tag replacement, release replacement, or asset clobbering is used.
- Failed uploads leave a draft/reserved version. Inspect and complete it deliberately; a repeat request for the same reserved source fails closed. Do not edit/remove the machine-readable `custom-android-release` marker in release notes. Its source/version/signing metadata is required for safe future releases.

Artifacts include ten signed APKs, `SFA-version-metadata.json`, exact-source/signing metadata in `release-plan.json`, and `SHA256SUMS`. Build logs/metadata and public certificate fingerprints are not signing secrets.

## Checks and limitations

Run the source-level checks without a signing key:

```bash
python3 -m unittest discover -s .github/scripts -p 'test_*.py' -v
python3 -m py_compile .github/scripts/*.py
bash -n .github/scripts/build_signed_apks.sh
bash -n .github/scripts/setup_android_signing.sh
```

A real signed build needs the owner-configured secrets, Android SDK/NDK, Go version from `version.properties`, JDK 17, and network access to the repository's existing dependencies. A planner/static test pass is not an APK build pass. All APK signature/version checks run again before upload. Dependencies and SDK coordinates are inherited from the existing Android/core repositories; incompatibilities fail without publishing unsigned output.
