import unittest
from verify_apk import validate


class APKValidationTests(unittest.TestCase):
    cert = 'a' * 64
    signature = 'Signer #1 certificate SHA-256 digest: ' + cert + '\n'
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

    def test_wrong_code_version_or_package_rejected(self):
        for old, new in [('742', '741'), ('alpha.9.c1', 'alpha.9'), ('io.nekohasekai.sfa', 'unexpected.app')]:
            with self.assertRaises(ValueError): self.check(badging=self.badging.replace(old, new))


if __name__ == '__main__':
    unittest.main()
