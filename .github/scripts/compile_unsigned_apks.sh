#!/usr/bin/env bash
set -euo pipefail
[[ "${CUSTOM_ANDROID_COMPILE_CHECK:-}" == true && "${CUSTOM_ANDROID_RELEASE:-}" != true ]] || exit 1
for setting in ANDROID_KEYSTORE_BASE64 ANDROID_KEYSTORE_PASSWORD ANDROID_KEY_ALIAS ANDROID_KEY_PASSWORD LOCAL_PROPERTIES; do
  [[ -z "${!setting:-}" ]] || { echo "Compile validation must not receive $setting"; exit 1; }
done
[[ "${CUSTOM_COMPILE_VERSION_NAME:-}" =~ ^[0-9]+\.[0-9]+\.[0-9]+(-[0-9A-Za-z.-]+)?$ ]] || exit 1
[[ "${CUSTOM_COMPILE_VERSION_CODE:-}" =~ ^[0-9]+$ ]] || exit 1
[[ ! -e local.properties && ! -e service-account-credentials.json ]] || {
  echo 'Compile validation must use a clean checkout without local credentials'; exit 1;
}
# No keystore is generated or read; the init script removes every signing config.
./gradlew --no-daemon --max-workers=2 -Dorg.gradle.jvmargs="-Xmx5g -Dfile.encoding=UTF-8" \
  --init-script .github/scripts/compile_unsigned.init.gradle \
  :app:assembleOtherRelease :app:assembleOtherLegacyRelease \
  :app:testOtherReleaseUnitTest :app:testOtherLegacyReleaseUnitTest
python3 - <<'PY'
import os
from pathlib import Path
import re
import subprocess
import zipfile

apks = list(Path("app/build/outputs/apk/other/release").glob("*.apk"))
apks += list(Path("app/build/outputs/apk/otherLegacy/release").glob("*.apk"))
assert len(apks) == 10, f"Expected ten release APKs, found {len(apks)}"
tools = Path(os.environ["ANDROID_HOME"]) / "build-tools/37.0.0"
expected_abis = {"armeabi-v7a", "arm64-v8a", "x86", "x86_64"}
seen = {"other": [], "otherLegacy": []}
for flavor in seen:
    assert (Path("app/build/outputs/mapping") / (flavor + "Release") / "mapping.txt").is_file()
for apk in apks:
    assert "unsigned" in apk.name and "debug" not in apk.name, apk
    verified = subprocess.run([str(tools / "apksigner"), "verify", str(apk)], capture_output=True)
    assert verified.returncode != 0, f"Unexpected signed APK: {apk}"
    badging = subprocess.check_output([str(tools / "aapt"), "dump", "badging", str(apk)], text=True)
    assert "application-debuggable" not in badging, apk
    package = re.search(r"package: name='([^']+)' versionCode='([^']+)' versionName='([^']+)'", badging)
    assert package and package.groups() == ("io.nekohasekai.sfa",
        os.environ["CUSTOM_COMPILE_VERSION_CODE"], os.environ["CUSTOM_COMPILE_VERSION_NAME"]), apk
    native = re.search(r"(?m)^native-code:(.+)$", badging)
    abis = set(re.findall(r"'([^']+)'", native[1])) if native else set()
    assert abis and abis <= expected_abis, (apk, abis)
    seen[apk.parent.parent.name].append(abis)
    with zipfile.ZipFile(apk) as archive:
        assert "classes.dex" in archive.namelist(), apk
        assert any(p.startswith("lib/") and p.endswith("/libbox.so") for p in archive.namelist()), apk
    print(f"Verified internal-only unsigned release build: {apk.name}")
for flavor, variants in seen.items():
    assert len(variants) == 5 and variants.count(expected_abis) == 1, (flavor, variants)
    assert all(variants.count({abi}) == 1 for abi in expected_abis), (flavor, variants)
with open(os.environ["GITHUB_STEP_SUMMARY"], "a") as summary:
    summary.write("\nBoth minified release variants compiled with exact custom core. "
                  "Ten unsigned, non-debuggable APKs verified locally on runner; no APKs uploaded.\n")
PY
