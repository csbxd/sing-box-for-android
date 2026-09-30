#!/usr/bin/env bash
set -euo pipefail
[[ "${CUSTOM_ANDROID_RELEASE:-}" == "true" ]] || { echo "Custom release mode is required"; exit 1; }
# Signing material is supplied by the owner through GitHub Secrets, never committed.
for setting in ANDROID_KEYSTORE_BASE64 ANDROID_KEYSTORE_PASSWORD ANDROID_KEY_ALIAS ANDROID_KEY_PASSWORD ANDROID_KEYSTORE_PATH ANDROID_SIGNING_CERT_SHA256 CUSTOM_VERSION_NAME CUSTOM_VERSION_CODE; do
  [[ -n "${!setting:-}" ]] || { echo "Missing required signing/build setting: $setting" >&2; exit 1; }
done
[[ "$CUSTOM_VERSION_CODE" =~ ^[0-9]+$ ]] || exit 1
expected_cert=$(printf '%s' "$ANDROID_SIGNING_CERT_SHA256" | tr -d ':' | tr '[:upper:]' '[:lower:]')
[[ "$expected_cert" =~ ^[0-9a-f]{64}$ ]] || { echo 'Invalid expected certificate SHA-256'; exit 1; }
umask 077
trap 'rm -f "$ANDROID_KEYSTORE_PATH"' EXIT
printf '%s' "$ANDROID_KEYSTORE_BASE64" | base64 --decode > "$ANDROID_KEYSTORE_PATH"
unset ANDROID_KEYSTORE_BASE64
actual_cert=$(keytool -exportcert -keystore "$ANDROID_KEYSTORE_PATH" -storetype PKCS12 \
  -alias "$ANDROID_KEY_ALIAS" -storepass:env ANDROID_KEYSTORE_PASSWORD | sha256sum | cut -d' ' -f1)
[[ "$actual_cert" == "$expected_cert" ]] || { echo 'Keystore certificate does not match the pinned public fingerprint'; exit 1; }
# Never use a debug task or the upstream checked-in keystore for custom publication.
./gradlew --no-daemon :app:assembleOtherRelease :app:assembleOtherLegacyRelease
# Preserve APK-only build output before the independent verification job.
# This directory must never contain a keystore, properties, passwords or other files.
mkdir -p built-apks
shopt -s nullglob
apks=(app/build/outputs/apk/other/release/*.apk app/build/outputs/apk/otherLegacy/release/*.apk)
[[ ${#apks[@]} -eq 10 ]] || { echo 'Expected ten release APK build outputs'; exit 1; }
for apk in "${apks[@]}"; do
  [[ "$apk" != *unsigned* && "$apk" != *debug* ]]
  cp "$apk" built-apks/
done
printf 'certificate_sha256=%s\n' "$expected_cert" >> "$GITHUB_OUTPUT"
