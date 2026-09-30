#!/usr/bin/env bash
set -euo pipefail
# No keystore or signing-password inputs are required by this verification job.
for setting in ANDROID_SIGNING_CERT_SHA256 CUSTOM_VERSION_NAME CUSTOM_VERSION_CODE BUILD_ARTIFACT_ID BUILD_ARTIFACT_SHA256; do
  [[ -n "${!setting:-}" ]] || { echo "Missing verification setting: $setting" >&2; exit 1; }
done
[[ "$ANDROID_SIGNING_CERT_SHA256" =~ ^[0-9a-f]{64}$ ]]
build_tools="$ANDROID_HOME/build-tools/37.0.0"
mkdir -p dist
shopt -s nullglob
apks=(built-apks/*.apk)
[[ ${#apks[@]} -eq 10 ]] || { echo 'Expected exactly ten APK build artifacts'; exit 1; }
for apk in "${apks[@]}"; do
  [[ "$apk" != *unsigned* && "$apk" != *debug* ]]
  python3 .github/scripts/verify_apk.py --apk "$apk" --build-tools "$build_tools" \
    --certificate "$ANDROID_SIGNING_CERT_SHA256" --version "$CUSTOM_VERSION_NAME" --code "$CUSTOM_VERSION_CODE"
  cp "$apk" dist/
done
python3 - <<'PY'
import json, os, subprocess
from pathlib import Path
plan = json.loads(Path('release-plan.json').read_text())
assert plan['version'] == os.environ['CUSTOM_VERSION_NAME']
assert plan['version_code'] == int(os.environ['CUSTOM_VERSION_CODE'])
assert plan['app_commit'] == subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip()
plan.update(signing_certificate_sha256=os.environ['ANDROID_SIGNING_CERT_SHA256'],
            build_artifact_id=int(os.environ['BUILD_ARTIFACT_ID']),
            build_artifact_sha256=os.environ['BUILD_ARTIFACT_SHA256'],
            build_run_id=int(os.environ['GITHUB_RUN_ID']),
            build_workflow_commit=os.environ['GITHUB_SHA'],
            verification_commit=plan['app_commit'],
            verification_run_attempt=int(os.environ['GITHUB_RUN_ATTEMPT']))
Path('dist/release-plan.json').write_text(json.dumps(plan, indent=2) + '\n')
Path('dist/SFA-version-metadata.json').write_text(json.dumps({
    'version_name': plan['version'], 'version_code': plan['version_code']}, indent=2) + '\n')
PY
(cd dist && sha256sum -- *.apk *.json > SHA256SUMS)
