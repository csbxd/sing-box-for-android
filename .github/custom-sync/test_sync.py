import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock

import sync


class RequestTests(unittest.TestCase):
    def request(self):
        return {'schema': 1, 'request_id': '20260930-reviewed', 'targets': [
            {'branch': 'dev', 'expected_head': 'a' * 40, 'upstream_sha': 'b' * 40}]}

    def test_valid_all_whitelisted_branches(self):
        request = self.request()
        request['targets'] = [{'branch': branch, 'expected_head': 'a' * 40, 'upstream_sha': 'b' * 40}
                              for branch in sync.REPLAYS]
        sync.validate_request(request)

    def test_unknown_or_duplicate_branch_rejected(self):
        for branch in ('../dev', 'maintenance/custom-sync', 'new-branch'):
            request = self.request(); request['targets'][0]['branch'] = branch
            with self.assertRaises(RuntimeError): sync.validate_request(request)
        request = self.request(); request['targets'] *= 2
        with self.assertRaises(RuntimeError): sync.validate_request(request)

    def test_mutable_or_injected_shas_rejected(self):
        for value in ('main', 'a' * 7, '--force', 'A' * 40, None):
            request = self.request(); request['targets'][0]['upstream_sha'] = value
            with self.assertRaises(RuntimeError): sync.validate_request(request)

    def test_unknown_fields_rejected(self):
        request = self.request(); request['force'] = True
        with self.assertRaises(RuntimeError): sync.validate_request(request)
        request = self.request(); request['targets'][0]['remote'] = 'attacker/repo'
        with self.assertRaises(RuntimeError): sync.validate_request(request)

    def test_invalid_id_empty_targets_and_tree_rejected(self):
        for key, value in [('request_id', '../unsafe'), ('targets', []), ('schema', 2)]:
            request = self.request(); request[key] = value
            with self.assertRaises(RuntimeError): sync.validate_request(request)
        request = self.request(); request['targets'][0]['expected_tree'] = 'HEAD'
        with self.assertRaises(RuntimeError): sync.validate_request(request)


class LocalGitIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.upstream, self.origin = self.root / 'upstream.git', self.root / 'origin.git'
        self.upwork, self.work = self.root / 'upstream-work', self.root / 'work'
        self.command('git', 'init', '--bare', '-q', str(self.upstream))
        self.command('git', 'init', '--bare', '-q', str(self.origin))
        self.command('git', 'init', '-q', str(self.upwork))
        self.identify(self.upwork)
        self.commit(self.upwork, 'source.txt', 'base\n', 'Upstream base')
        self.base = self.git(self.upwork, 'rev-parse', 'HEAD')
        self.git(self.upwork, 'remote', 'add', 'origin', str(self.upstream))
        self.git(self.upwork, 'push', '-q', 'origin', 'HEAD:refs/heads/dev')
        self.command('git', 'clone', '-q', '--branch', 'dev', str(self.upstream), str(self.work))
        self.identify(self.work)
        self.git(self.work, 'remote', 'set-url', 'origin', str(self.origin))
        self.commit(self.work, 'custom.txt', 'original custom patch\n', 'Custom feature\n\nPreserve full message.\n')
        self.custom = self.git(self.work, 'rev-parse', 'HEAD')
        self.git(self.work, 'push', '-q', 'origin', 'HEAD:refs/heads/dev')
        self.git(self.work, 'checkout', '-qb', sync.CONTROL)
        self.state = {'schema': 1, 'branches': {'dev': {
            'upstream_sha': self.base, 'source_sha': self.custom,
            'source_tree': self.git(self.work, 'rev-parse', 'HEAD^{tree}'),
            'source_fingerprint': sync.fingerprint(self.custom, self.work),
            'replay_commits': [self.custom], 'mapping': []}}}
        self.request = {'schema': 1, 'request_id': 'integration-test', 'targets': [
            {'branch': 'dev', 'expected_head': self.custom, 'upstream_sha': self.base}]}
        control_dir = self.work / '.github/custom-sync'; control_dir.mkdir(parents=True)
        (control_dir / 'state.json').write_text(json.dumps(self.state))
        self.write_request()
        self.previous_cwd = Path.cwd(); os.chdir(self.work)
        self.addCleanup(os.chdir, self.previous_cwd)
        self.environ = mock.patch.dict(os.environ, {'GITHUB_REPOSITORY': sync.REPO,
            'GITHUB_REF': 'refs/heads/' + sync.CONTROL, 'GITHUB_SHA': self.control,
            'RUNNER_TEMP': str(self.root / 'runner')})
        self.environ.start(); self.addCleanup(self.environ.stop)
        (self.root / 'runner').mkdir()
        patch = mock.patch.multiple(sync, UPSTREAM=str(self.upstream), REPLAYS={'dev': [self.custom]})
        patch.start(); self.addCleanup(patch.stop)

    def command(self, *args):
        return subprocess.check_output(args, text=True, stderr=subprocess.DEVNULL).strip()

    def git(self, repo, *args):
        return self.command('git', '-C', str(repo), *args)

    def identify(self, repo):
        self.git(repo, 'config', 'user.name', 'Original Author')
        self.git(repo, 'config', 'user.email', 'original@example.invalid')

    def commit(self, repo, filename, content, message):
        (repo / filename).write_text(content)
        self.git(repo, 'add', filename); self.git(repo, 'commit', '-qm', message)

    def write_request(self):
        path = self.work / '.github/custom-sync/request.json'
        path.write_text(json.dumps(self.request))
        self.git(self.work, 'add', '.github/custom-sync')
        self.git(self.work, 'commit', '-qm', 'Reviewed sync request')
        self.control = self.git(self.work, 'rev-parse', 'HEAD')
        self.git(self.work, 'push', '-q', 'origin', 'HEAD:refs/heads/' + sync.CONTROL)
        os.environ['GITHUB_SHA'] = self.control

    def advance_upstream(self, conflict=False):
        self.commit(self.upwork, 'custom.txt' if conflict else 'upstream.txt',
                    'upstream update\n', 'Upstream update')
        sha = self.git(self.upwork, 'rev-parse', 'HEAD')
        self.git(self.upwork, 'push', '-q', 'origin', 'HEAD:refs/heads/dev')
        self.request['targets'][0]['upstream_sha'] = sha
        self.write_request()
        return sha

    def test_unchanged_source_is_true_noop(self):
        sync.main()
        self.assertEqual(sync.remote_heads('origin', ['dev'])['dev'], self.custom)
        self.assertEqual(sync.remote_heads('origin', [sync.CONTROL])[sync.CONTROL], self.control)
        self.assertFalse(self.git(self.work, 'ls-remote', '--heads', 'origin', 'refs/heads/backup/*'))
        self.assertTrue(json.loads(Path('sync-result.json').read_text())['all_noop'])

    def test_actual_cherry_pick_metadata_patch_backup_and_state(self):
        upstream = self.advance_upstream()
        sync.main()
        new = sync.remote_heads('origin', ['dev'])['dev']
        self.assertNotEqual(new, self.custom)
        self.assertEqual(self.git(self.work, 'rev-parse', new + '^'), upstream)
        self.assertEqual(sync.metadata(new), sync.metadata(self.custom))
        self.assertEqual(sync.patch_id(new), sync.patch_id(self.custom))
        backup = 'backup/sync-dev-integration-test'
        self.assertEqual(sync.remote_heads('origin', [backup])[backup], self.custom)
        saved = json.loads(Path('.github/custom-sync/state.json').read_text())['branches']['dev']
        self.assertEqual(saved['source_sha'], new)
        self.assertTrue(saved['mapping'][0]['metadata_preserved'])

    def advance_source_without_code(self, empty=False):
        source_work = self.root / 'source-work'
        self.git(self.work, 'worktree', 'add', '--detach', str(source_work), self.custom)
        if empty:
            self.git(source_work, 'commit', '--allow-empty', '-qm', 'Keep my user note')
        else:
            request_path = source_work / '.github/custom-validation/request.json'
            request_path.parent.mkdir(parents=True); request_path.write_text('{"validation":true}')
            self.git(source_work, 'add', '.github/custom-validation/request.json')
            self.git(source_work, 'commit', '-qm', 'Compile-only request')
        head = self.git(source_work, 'rev-parse', 'HEAD')
        self.git(source_work, 'push', '-q', 'origin', 'HEAD:refs/heads/dev')
        self.request['targets'][0]['expected_head'] = head
        self.write_request()
        return head

    def test_validation_request_only_descendant_allowed_without_rewrite(self):
        head = self.advance_source_without_code()
        sync.main()
        self.assertEqual(sync.remote_heads('origin', ['dev'])['dev'], head)
        self.assertTrue(json.loads(Path('sync-result.json').read_text())['all_noop'])

    def test_empty_user_commit_is_not_silently_discarded(self):
        self.advance_source_without_code(empty=True)
        with self.assertRaisesRegex(RuntimeError, 'Unexpected intervening user commits'): sync.main()

    def test_superseding_control_push_rejects_atomic_source_and_state(self):
        self.advance_upstream()
        real_git = sync.git
        superseding = None
        def race(*args, **kwargs):
            nonlocal superseding
            if args[:2] == ('push', '--atomic') and 'HEAD:refs/heads/' + sync.CONTROL in args:
                tree = self.git(self.work, 'rev-parse', self.control + '^{tree}')
                superseding = self.git(self.work, 'commit-tree', tree, '-p', self.control, '-m', 'Newer reviewed request')
                self.git(self.work, 'push', '-q', 'origin', superseding + ':refs/heads/' + sync.CONTROL)
            return real_git(*args, **kwargs)
        with mock.patch('sync.git', side_effect=race):
            with self.assertRaises(subprocess.CalledProcessError): sync.main()
        self.assertEqual(sync.remote_heads('origin', ['dev'])['dev'], self.custom)
        self.assertEqual(sync.remote_heads('origin', [sync.CONTROL])[sync.CONTROL], superseding)

    def test_conflict_does_not_mutate_source_or_create_backup(self):
        self.advance_upstream(conflict=True)
        with self.assertRaises(subprocess.CalledProcessError): sync.main()
        self.assertEqual(sync.remote_heads('origin', ['dev'])['dev'], self.custom)
        self.assertFalse(self.git(self.work, 'ls-remote', '--heads', 'origin', 'refs/heads/backup/*'))

    def test_upstream_move_after_request_rejected(self):
        self.commit(self.upwork, 'unreviewed.txt', 'new\n', 'Unreviewed change')
        self.git(self.upwork, 'push', '-q', 'origin', 'HEAD:refs/heads/dev')
        with self.assertRaisesRegex(RuntimeError, 'Upstream moved'): sync.main()

    def test_wrong_expected_head_rejected(self):
        self.request['targets'][0]['expected_head'] = self.base; self.write_request()
        with self.assertRaisesRegex(RuntimeError, 'User branch changed'): sync.main()

    def test_noop_expected_tree_enforced(self):
        self.request['targets'][0]['expected_tree'] = 'a' * 40; self.write_request()
        with self.assertRaisesRegex(RuntimeError, 'No-op tree differs'): sync.main()

    def test_unexpected_source_rejected_even_with_current_sha(self):
        self.commit(self.work, 'unreviewed.txt', 'user code\n', 'Unreviewed user change')
        user_head = self.git(self.work, 'rev-parse', 'HEAD')
        self.git(self.work, 'push', '-q', 'origin', user_head + ':refs/heads/dev')
        self.request['targets'][0]['expected_head'] = user_head; self.write_request()
        with self.assertRaisesRegex(RuntimeError, 'Unexpected custom source'): sync.main()


if __name__ == '__main__':
    unittest.main()
