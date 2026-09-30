# Real Build Tools 37 regression check

The certificate parser was validated with the actual Google Build Tools 37.0.0 `apksigner` and `aapt`, not only mocked output, on 2026-09-30.

- SDK archive: https://dl.google.com/android/repository/build-tools_r37_linux.zip
- Archive SHA-1 verified against Google's repository metadata: `70954e99f4c3d9d46ee70fa32624672fe7cd6ebe`
- Extracted apksigner.jar SHA-256: `2defad215d7ff52968a409cde528cdaef7918b115e276b8e3378ca7a178e4180`
- Real output uses scheme prefixes such as `V1 Signer:`, `V2 Signer:` and `V3.0 Signer:`. SDK-targeted output uses e.g. `V3.1 Signer: (minSdkVersion=33, maxSdkVersion=2147483647)`.

The complete repository verifier CLI, including real `aapt` package/version/debuggable checks, passed against the [official SFA alpha.9 arm64 APK](https://github.com/SagerNet/sing-box/releases/download/v1.15.0-alpha.9/SFA-1.15.0-alpha.9-arm64-v8a.apk):

- Download SHA-256 matched GitHub's release asset: `23260d607b4fe44f068627bcc9eebd037f8bf3d10f013d06a1b2c30ba7ae9e89`
- Public upstream certificate SHA-256: `32250a4b5f3a6733df57a3b9ec16c38d2c7fc5f2f693a9636f8f7b3be3549641`
- Package `io.nekohasekai.sfa`, version `1.15.0-alpha.9`, versionCode `741`
- The same full CLI command rejected a deliberately incorrect expected certificate fingerprint

Additional real signed [AOSP apksig public test APKs](https://android.googlesource.com/platform/tools/apksig/+/refs/heads/main/src/test/resources/com/android/apksig/) were cryptographically verified with that same SDK:

- `golden-aligned-v1-out.apk`, `golden-aligned-v1v2-out.apk`, and `golden-aligned-v1v2v3-out.apk`: parser accepted the correct public fixture fingerprint `fb5dbd3c669af9fc236c6991e6387b7f11ff0590997f22d0f5c74ff40e04fca8`
- `two-signers.apk`: rejected because it reports two APK signers
- `stamp-1-v31-tgt-33-signer.apk`: rejected because its APK certificate rotation includes different signing certificates; the source-stamp certificate is not treated as an APK signer

These upstream/fixture fingerprints are test expectations only. Production releases must use the owner's separately configured pinned fingerprint. No private signing keys were read, generated or used for these checks, and no test APK was executed or published by this regression check.
