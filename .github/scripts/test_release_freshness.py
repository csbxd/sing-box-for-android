import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock

from check_release_freshness import check_fresh, REQUEST_PATH
from plan_android_release import source_digest
from publish_android_release import publish


class FreshnessTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.app, self.core = [Path(self.temp.name, name) for name in ('app', 'core')]
        for repo in (self.app, self.core):
            repo.mkdir(); self.git(repo, 'init', '-q')
            self.git(repo, 'config', 'user.name', 'Test')
            self.git(repo, 'config', 'user.email', 'test@example.invalid')
            self.commit(repo, 'source', 'original')
        self.plan = dict(app_commit=self.git(self.app, 'rev-parse', 'HEAD'),
                         core_commit=self.git(self.core, 'rev-parse', 'HEAD'),
                         app_source_digest=source_digest(self.app), core_source_digest=source_digest(self.core))
        self.commit(self.app, REQUEST_PATH, 'original exact source request')
        self.workflow = self.git(self.app, 'rev-parse', 'HEAD')

    def git(self, repo, *args):
        return subprocess.check_output(['git', '-C', str(repo), *args], text=True, stderr=subprocess.DEVNULL).strip()

    def commit(self, repo, name, text):
        file = repo / name; file.parent.mkdir(parents=True, exist_ok=True); file.write_text(text)
        self.git(repo, 'add', '.'); self.git(repo, 'commit', '-qm', text)

    def check(self):
        return check_fresh(self.plan, self.app, self.core, self.workflow, 'HEAD', 'HEAD')

    def test_current_source_allowed(self):
        self.check()

    def test_core_request_only_descendant_allowed(self):
        self.commit(self.core, REQUEST_PATH, 'new core release request')
        self.check()

    def test_new_android_request_rejected(self):
        self.commit(self.app, REQUEST_PATH, 'superseding Android request')
        with self.assertRaisesRegex(RuntimeError, 'newer Android request'): self.check()

    def test_android_source_change_rejected(self):
        self.commit(self.app, 'source', 'new Android code')
        with self.assertRaisesRegex(RuntimeError, 'Android dev source changed'): self.check()

    def test_core_source_change_rejected(self):
        self.commit(self.core, 'source', 'new core code')
        with self.assertRaisesRegex(RuntimeError, 'core custom-dev source changed'): self.check()

    def test_android_forcepush_even_same_tree_rejected(self):
        self.git(self.app, 'checkout', '--orphan', 'rewrite')
        self.git(self.app, 'commit', '-qm', 'unrelated same tree')
        with self.assertRaisesRegex(RuntimeError, 'history was changed'): self.check()

    def test_core_forcepush_even_same_tree_rejected(self):
        self.git(self.core, 'checkout', '--orphan', 'rewrite')
        self.git(self.core, 'commit', '-qm', 'unrelated same tree')
        with self.assertRaisesRegex(RuntimeError, 'history was changed'): self.check()


class PublicationGuardTests(unittest.TestCase):
    plan = dict(tag='v1.15.0-alpha.9.c1', app_commit='a' * 40, version='1.15.0-alpha.9.c1', prerelease=True)

    @mock.patch.dict(os.environ, {'GITHUB_SHA': 'a' * 40})
    def test_rechecks_before_every_transition(self):
        for fail_at in (0, 1, 2):
            with self.subTest(fail_at=fail_at), mock.patch('publish_android_release.gh') as gh, \
                    mock.patch('publish_android_release.refresh_and_check',
                               side_effect=[None] * fail_at + [RuntimeError('stale')]):
                with self.assertRaisesRegex(RuntimeError, 'stale'):
                    publish(self.plan, 'csbxd/sing-box-for-android', [], '/not-used-by-mock')
                self.assertEqual(gh.call_count, fail_at)
                self.assertFalse(any(call.args[:2] == ('release', 'edit') for call in gh.call_args_list))

    @mock.patch.dict(os.environ, {'GITHUB_SHA': 'a' * 40})
    def test_fresh_run_publishes_after_three_checks(self):
        with mock.patch('publish_android_release.gh') as gh, \
                mock.patch('publish_android_release.refresh_and_check') as check:
            publish(self.plan, 'csbxd/sing-box-for-android', [], '/not-used-by-mock')
            self.assertEqual(check.call_count, 3)
            self.assertEqual([call.args[:2] for call in gh.call_args_list],
                             [('api', '--method'), ('release', 'create'), ('release', 'edit'), ('release', 'view')])


if __name__ == '__main__':
    unittest.main()
