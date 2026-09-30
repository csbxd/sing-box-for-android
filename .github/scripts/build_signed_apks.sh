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
build_tools=$(find "$ANDROID_HOME/build-tools" -mindepth 1 -maxdepth 1 -type d | sort -V | tail -1)
[[ -x "$build_tools/apksigner" && -x "$build_tools/aapt" ]]
mkdir -p dist
shopt -s nullglob
apks=(app/build/outputs/apk/other/release/*.apk app/build/outputs/apk/otherLegacy/release/*.apk)
[[ ${#apks[@]} -eq 10 ]] || { echo 'Expected four ABI APKs plus universal APK for both release flavors'; exit 1; }
for apk in "${apks[@]}"; do
  [[ "$apk" != *unsigned* && "$apk" != *debug* ]]
  python3 .github/scripts/verify_apk.py --apk "$apk" --build-tools "$build_tools" \
    --certificate "$expected_cert" --version "$CUSTOM_VERSION_NAME" --code "$CUSTOM_VERSION_CODE"
  cp "$apk" dist/
done
export VERIFIED_CERT_SHA256="$expected_cert"
python3 - <<'PY'
import json, os
from pathlib import Path
plan = json.loads(Path('release-plan.json').read_text())
assert plan['version'] == os.environ['CUSTOM_VERSION_NAME']
assert plan['version_code'] == int(os.environ['CUSTOM_VERSION_CODE'])
plan['signing_certificate_sha256'] = os.environ['VERIFIED_CERT_SHA256']
Path('dist/release-plan.json').write_text(json.dumps(plan, indent=2) + '\n')
Path('dist/SFA-version-metadata.json').write_text(json.dumps({
    'version_name': plan['version'], 'version_code': plan['version_code']}, indent=2) + '\n')
PY
(cd dist && sha256sum -- *.apk *.json > SHA256SUMS)
