# Compile-only Android validation

The `Custom Android compile validation` workflow builds the exact custom core into four ABI AARs, merges the AARs, and assembles/tests both `otherRelease` and `otherLegacyRelease` using the official SDK/NDK and pinned JDK/Go versions.

It receives no signing secrets and does not generate a keystore. A CI-only Gradle init script removes signing configurations and rejects debug, signing, publication and upload tasks. Ten unsigned, non-debuggable APKs are checked only on the ephemeral runner. **No APK is uploaded or published.** Only intermediate AARs are shared within the run, with one-day retention. This is compile validation, not a signed-release substitute or runtime/device test.

Use the direct GitHub connector to commit `.github/custom-validation/request.json` on `dev` with exactly:

```json
{
  "schema": 1,
  "source_sha": "FULL_LOWERCASE_40_CHARACTER_ANDROID_SHA",
  "core_sha": "FULL_LOWERCASE_40_CHARACTER_CORE_SHA",
  "core_version": "1.15.0-alpha.9.c1"
}
```

The source commit must contain the validation scripts and be an ancestor of the trigger and `dev`. The core must be reachable from `csbxd/sing-box/custom-dev`, and `v<core_version>` must resolve to that exact commit. The workflow has read-only repository permissions and cannot create tags or Releases. A successful run validates compilation and packaging only; owner-provided signing settings and the separate signed-release workflow remain required for distributable APKs.

Validation request-only changes are excluded from release source fingerprints, like release requests. CI fixes are separate normal commits, preserving original custom application commits.
