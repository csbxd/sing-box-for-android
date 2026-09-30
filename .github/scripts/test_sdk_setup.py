import os
from pathlib import Path
import subprocess
import tempfile
import unittest

SCRIPT = Path(__file__).with_name('setup_android_sdk.sh').resolve()


class SDKSetupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.env = {**os.environ, 'ANDROID_HOME': str(self.root), 'GITHUB_ENV': str(self.root / 'github.env')}
        self.manager = self.root / 'cmdline-tools/latest/bin/sdkmanager'
        self.manager.parent.mkdir(parents=True)
        self.manager.write_text('''#!/usr/bin/env bash
set -eu
printf '%s\\n' "$@" > "$ANDROID_HOME/arguments"
[[ "${FAIL_INSTALL:-}" != true ]] || exit 7
mkdir -p "$ANDROID_HOME/platforms/android-37.1" "$ANDROID_HOME/ndk/28.0.13004108" "$ANDROID_HOME/build-tools/37.0.0"
touch "$ANDROID_HOME/platforms/android-37.1/android.jar"
printf 'Pkg.Revision = 28.0.13004108\\n' > "$ANDROID_HOME/ndk/28.0.13004108/source.properties"
for tool in apksigner aapt; do touch "$ANDROID_HOME/build-tools/37.0.0/$tool"; chmod +x "$ANDROID_HOME/build-tools/37.0.0/$tool"; done
''')
        self.manager.chmod(0o755)
        (self.root / 'licenses').mkdir()
        (self.root / 'licenses/android-sdk-license').write_text('unit-test-placeholder')

    def run_setup(self):
        return subprocess.run(['bash', str(SCRIPT)], env=self.env, text=True, capture_output=True)

    def test_exact_packages_installed_and_ndk_exported(self):
        result = self.run_setup()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.root / 'arguments').read_text().splitlines(),
                         ['--install', 'platforms;android-37.1', 'ndk;28.0.13004108', 'build-tools;37.0.0'])
        self.assertIn('ANDROID_NDK_HOME=' + str(self.root / 'ndk/28.0.13004108'), (self.root / 'github.env').read_text())

    def test_missing_license_rejected_without_install(self):
        (self.root / 'licenses/android-sdk-license').unlink()
        result = self.run_setup()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('no accepted Android SDK license', result.stderr)
        self.assertFalse((self.root / 'arguments').exists())

    def test_missing_manager_rejected(self):
        self.manager.unlink()
        result = self.run_setup()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('sdkmanager is missing', result.stderr)

    def test_install_failure_propagates(self):
        self.env['FAIL_INSTALL'] = 'true'
        self.assertEqual(self.run_setup().returncode, 7)
        self.assertFalse((self.root / 'github.env').exists())


if __name__ == '__main__':
    unittest.main()
