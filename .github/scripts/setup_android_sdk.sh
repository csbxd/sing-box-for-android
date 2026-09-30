#!/usr/bin/env bash
set -euo pipefail
# Coordinates verified in Google's official repository2-3.xml and app Gradle config.
: "${ANDROID_HOME:?GitHub runner must provide ANDROID_HOME}"
sdkmanager="$ANDROID_HOME/cmdline-tools/latest/bin/sdkmanager"
[[ -x "$sdkmanager" ]] || { echo 'Official Android sdkmanager is missing from this runner' >&2; exit 1; }
[[ -f "$ANDROID_HOME/licenses/android-sdk-license" ]] || {
  echo 'The runner has no accepted Android SDK license; the repository owner must resolve this before building' >&2
  exit 1
}
# Do not auto-accept new license agreements. The GitHub-hosted image supplies its
# accepted SDK license; a changed/missing license fails closed without prompting.
"$sdkmanager" --install 'platforms;android-37.1' 'ndk;28.0.13004108' 'build-tools;37.0.0' < /dev/null
[[ -f "$ANDROID_HOME/platforms/android-37.1/android.jar" ]] || { echo 'SDK platform 37.1 was not installed'; exit 1; }
ndk="$ANDROID_HOME/ndk/28.0.13004108"
[[ -f "$ndk/source.properties" ]] || { echo 'Required NDK was not installed'; exit 1; }
grep -Eq '^Pkg.Revision[[:space:]]*=[[:space:]]*28[.]0[.]13004108[[:space:]]*$' "$ndk/source.properties"
for tool in apksigner aapt; do
  [[ -x "$ANDROID_HOME/build-tools/37.0.0/$tool" ]] || { echo "Android build tool $tool is missing"; exit 1; }
done
if [[ -n "${GITHUB_ENV:-}" ]]; then
  printf 'ANDROID_NDK_HOME=%s\n' "$ndk" >> "$GITHUB_ENV"
fi
printf 'Verified Android SDK 37.1, NDK 28.0.13004108 and build-tools 37.0.0\n'
