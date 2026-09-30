import unittest
from verify_apk import validate


class APKValidationTests(unittest.TestCase):
    cert = 'a' * 64
    signature = 'Number of signers: 1\nSigner #1 certificate SHA-256 digest: ' + cert + '\n'
    badging = "package: name='io.nekohasekai.sfa' versionCode='742' versionName='1.15.0-alpha.9.c1'\n"

    def check(self, signature=None, badging=None):
        validate(self.signature if signature is None else signature,
                 self.badging if badging is None else badging, self.cert, '1.15.0-alpha.9.c1', 742)

    def test_signed_release(self):
        self.check()

    def test_debuggable_rejected(self):
        for flag in ('application-debuggable', 'application-debuggable:', 'application-debuggable: true'):
            with self.assertRaisesRegex(ValueError, 'debuggable'):
                self.check(badging=self.badging + flag + '\n')

    def test_unsigned_wrong_and_multiple_signers_rejected(self):
        for signature in ('', self.signature.replace('a' * 64, 'b' * 64),
                          self.signature + self.signature.replace('#1', '#2')):
            with self.assertRaises(ValueError): self.check(signature=signature)

    def test_observed_build_tools_37_scheme_labels(self):
        for scheme in ('V1', 'V2', 'V3.0'):
            self.check(signature=self.signature.replace('Signer #1', scheme + ' Signer:'))
        self.check(signature=('Number of signers: 1\n'
                             + f'V3.1 Signer: (minSdkVersion=33, maxSdkVersion=2147483647) certificate SHA-256 digest: {self.cert}\n'
                             + f'V3.0 Signer: (minSdkVersion=28, maxSdkVersion=32) certificate SHA-256 digest: {self.cert}'))
        with self.assertRaises(ValueError):
            self.check(signature=self.signature.replace('Signer #1', 'V2 Signer #2:'))

    def test_v31_sdk_range_labels_and_repeated_same_identity(self):
        signature = 'Number of signers: 1\n' + '\n'.join(
            f'Signer (minSdkVersion={lo}, maxSdkVersion={hi}) certificate SHA-256 digest: {self.cert}'
            for lo, hi in [(33, 2147483647), (28, 32)])
        self.check(signature=signature)
        self.check(signature=signature.replace('minSdkVersion=33,', 'minSdkVersion=33 (dev release=true),'))
        self.check(signature=signature.replace('\n', '\r\n'))

    def test_v31_different_rotation_certificate_rejected(self):
        signature = ('Number of signers: 1\n'
                     + f'Signer (minSdkVersion=33, maxSdkVersion=2147483647) certificate SHA-256 digest: {self.cert}\n'
                     + 'Signer (minSdkVersion=28, maxSdkVersion=32) certificate SHA-256 digest: ' + 'b' * 64)
        with self.assertRaisesRegex(ValueError, 'differs from pinned'): self.check(signature=signature)

    def test_source_stamp_does_not_replace_apk_signer(self):
        stamp = 'Source Stamp Signer certificate SHA-256 digest: ' + 'b' * 64 + '\n'
        self.check(signature=self.signature + stamp)
        with self.assertRaises(ValueError): self.check(signature='Number of signers: 1\n' + stamp)

    def test_signer_count_and_unknown_mixed_formats_rejected(self):
        for signature in (self.signature.replace('signers: 1', 'signers: 2'),
                          self.signature.replace('Number of signers: 1\n', ''),
                          self.signature.replace('#1', '#2'), self.signature.replace('#1', 'unknown-label'),
                          self.signature + f'Signer (minSdkVersion=28, maxSdkVersion=32) certificate SHA-256 digest: {self.cert}'):
            with self.assertRaises(ValueError): self.check(signature=signature)

    def test_wrong_code_version_or_package_rejected(self):
        for old, new in [('742', '741'), ('alpha.9.c1', 'alpha.9'), ('io.nekohasekai.sfa', 'unexpected.app')]:
            with self.assertRaises(ValueError): self.check(badging=self.badging.replace(old, new))


if __name__ == '__main__':
    unittest.main()
