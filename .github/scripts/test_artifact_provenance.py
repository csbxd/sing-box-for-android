import copy
import hashlib
import tempfile
import zipfile
from pathlib import Path
import unittest
from verify_artifact_provenance import validate_artifact, extract_verified_zip


class ArtifactTests(unittest.TestCase):
    info = dict(id=123, name='release-apk-build-output', expired=False, digest='sha256:' + 'a'*64,
                workflow_run=dict(id=456, head_sha='b'*40))

    def test_exact_artifact_passes(self):
        validate_artifact(self.info, '123', 'a'*64, '456', 'b'*40)

    def test_mismatch_or_expiry_rejected(self):
        for key, value in [('id', 999), ('name', 'unreviewed'), ('expired', True), ('digest', 'sha256:'+'c'*64)]:
            data = copy.deepcopy(self.info); data[key] = value
            with self.assertRaises(ValueError): validate_artifact(data, '123', 'a'*64, '456', 'b'*40)
        for key, value in [('id', 789), ('head_sha', 'd'*40)]:
            data = copy.deepcopy(self.info); data['workflow_run'][key] = value
            with self.assertRaises(ValueError): validate_artifact(data, '123', 'a'*64, '456', 'b'*40)

    def test_zip_bytes_checked_before_apk_only_extraction(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); archive = root / 'apks.zip'
            with zipfile.ZipFile(archive, 'w') as package:
                for index in range(10): package.writestr(f'release-{index}.apk', b'public-test-placeholder')
            digest = hashlib.sha256(archive.read_bytes()).hexdigest()
            with self.assertRaisesRegex(ValueError, 'SHA-256 mismatch'):
                extract_verified_zip(archive, '0'*64, root / 'bad')
            self.assertFalse((root / 'bad').exists())
            extract_verified_zip(archive, digest, root / 'good')
            self.assertEqual(len(list((root / 'good').glob('*.apk'))), 10)
            with zipfile.ZipFile(archive, 'a') as package: package.writestr('private.p12', b'not-a-key')
            digest = hashlib.sha256(archive.read_bytes()).hexdigest()
            with self.assertRaisesRegex(ValueError, 'exactly ten flat'):
                extract_verified_zip(archive, digest, root / 'unsafe')

    def test_verify_job_never_receives_signing_secrets(self):
        root = Path(__file__).resolve().parents[2]
        text = (root / '.github/workflows/custom-android-release.yml').read_text()
        verify = text.split('\n  verify:\n', 1)[1].split('\n  publish:\n', 1)[0]
        self.assertNotIn('secrets.', verify)
        self.assertIn('actions/artifacts/$BUILD_ARTIFACT_ID/zip', verify)
        self.assertIn('needs: [plan, verify]', text.split('\n  publish:\n', 1)[1])
        build = text.split('\n  apk:\n', 1)[1].split('\n  verify:\n', 1)[0]
        self.assertIn('path: built-apks/*.apk', build)
        self.assertNotIn('path: .', build)


if __name__ == '__main__':
    unittest.main()
