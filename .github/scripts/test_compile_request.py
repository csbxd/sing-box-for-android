import unittest
from read_compile_request import resolve

class CompileRequestTests(unittest.TestCase):
    def request(self):
        return dict(schema=1, source_sha="a" * 40, core_sha="b" * 40,
                    core_version="1.15.0-alpha.9.c1")

    def test_exact_sources(self):
        self.assertEqual(resolve(self.request()), ("a" * 40, "b" * 40, "1.15.0-alpha.9.c1"))

    def test_reject_non_sha_and_injection(self):
        for value in ("dev", "a" * 7, "A" * 40, "$(exit 0)", "a" * 40 + "\nx=y"):
            for key in ("source_sha", "core_sha"):
                row = self.request(); row[key] = value
                with self.assertRaises(ValueError): resolve(row)

    def test_reject_extra_fields_and_version_injection(self):
        row = self.request(); row["extra"] = True
        with self.assertRaises(ValueError): resolve(row)
        for value in ("latest", "1.2.3\nx=y", "$(exit 0)", None):
            row = self.request(); row["core_version"] = value
            with self.assertRaises(ValueError): resolve(row)
        row = self.request(); row["schema"] = True
        with self.assertRaises(ValueError): resolve(row)
