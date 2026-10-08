import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import read_release_request
import read_compile_request

class DeletedRequestTests(unittest.TestCase):
    def check_request(self, module, path, content, error=None):
        original = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                if content is not None:
                    p = Path(path)
                    p.parent.mkdir(parents=True)
                    p.write_text(content)
                with patch.dict(os.environ, {'GITHUB_EVENT_NAME': 'push',
                       'GITHUB_REPOSITORY':'csbxd/sing-box-for-android',
                       'GITHUB_REF':'refs/heads/dev', 'GITHUB_SHA':'a'*40,
                       'GITHUB_OUTPUT':'output'}), \
                     patch.object(module.subprocess, 'run') as git_call:
                    if error:
                        with self.assertRaises(error): module.main()
                        self.assertFalse(Path('output').exists())
                    else:
                        module.main()
                        self.assertEqual(Path('output').read_text(), 'skip=true\n')
                    git_call.assert_not_called()
            finally:
                os.chdir(original)

    def test_release_missing_skips(self):
        self.check_request(read_release_request, '.github/custom-release/request.json', None)

    def test_compile_missing_skips(self):
        self.check_request(read_compile_request, '.github/custom-validation/request.json', None)

    def test_invalid_existing_release_fails(self):
        for content in ('bad json', '{}', '{"schema":1,"source_sha":"bad","core_sha":"bad"}'):
            self.check_request(read_release_request, '.github/custom-release/request.json',
                               content, (ValueError, json.JSONDecodeError))

    def test_invalid_existing_compile_fails(self):
        for content in ('bad json', '{}', '{"schema":1}'):
            self.check_request(read_compile_request, '.github/custom-validation/request.json',
                               content, (ValueError, json.JSONDecodeError))
