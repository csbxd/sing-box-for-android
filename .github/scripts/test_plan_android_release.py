import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from plan_android_release import choose_base, plan, source_digest, source_version, version_key, MAX_VERSION_CODE
from read_release_request import resolve


def release(tag, sha='a', prerelease=True, draft=False, body='', published='2026-01-01'):
    return dict(tagName=tag, tagCommit={'oid': sha}, isPrerelease=prerelease,
                isDraft=draft, description=body, publishedAt=published)


def prior(tag, source='1' * 64, code=750, draft=False):
    info = dict(schema=1, source_id=source, version_code=code, tag=tag)
    return release(tag, draft=draft, body='<!-- custom-android-release: ' + json.dumps(info) + ' -->')


class PlannerTests(unittest.TestCase):
    source = {'source_id': '2' * 64}

    def test_latest_release_in_exact_source_series(self):
        rows = [release('v1.15.0-alpha.9', 'unreachable'), release('v1.14.2', 'reachable', False),
                release('v1.15.0-alpha.8', 'reachable'), release('v1.16.0-alpha.1', 'other'),
                release('v1.15.0-alpha.10', 'draft', draft=True)]
        self.assertEqual(choose_base(rows, '1.15.0-alpha.9')['tagName'], 'v1.15.0-alpha.9')

    def test_semver_numeric_order_and_stable_precedence(self):
        versions = ['1.15.0-alpha.9', '1.15.0-alpha.10', '1.15.0-beta.1', '1.15.0-rc.1', '1.15.0']
        self.assertEqual(sorted(reversed(versions), key=version_key), versions)
        self.assertEqual(choose_base([release(v) for v in versions], versions[0])['tagName'], '1.15.0')

    def test_no_matching_series_fails(self):
        with self.assertRaises(ValueError): choose_base([release('v1.14.2')], '1.15.0-alpha.9')

    def test_source_version_first_semver_heading(self):
        self.assertEqual(source_version('# Changelog\n#### 1.15.0-alpha.9\nold\n#### 1.14.2'), '1.15.0-alpha.9')
        with self.assertRaises(ValueError): source_version('# No version here')

    def test_prerelease_revision_and_global_code(self):
        result = plan(release('v1.15.0-alpha.9'), [prior('v1.14.0-c3', code=900)],
                      ['v1.15.0-alpha.9.c1', 'v1.15.0-alpha.9.c9'], self.source, 741)
        self.assertEqual((result['version'], result['version_code']), ('1.15.0-alpha.9.c10', 901))
        self.assertTrue(result['prerelease'])

    def test_stable_revision(self):
        result = plan(release('v1.15.0', prerelease=False), [], [], self.source, 741)
        self.assertEqual(result['version'], '1.15.0-c1')
        self.assertFalse(result['prerelease'])
        self.assertEqual(result['version_code'], 742)

    def test_unchanged_source_skips_even_after_base_changes(self):
        result = plan(release('v2.0.0'), [prior('v1.0.0-c1', source=self.source['source_id'])], [], self.source, 741)
        self.assertTrue(result['skip'])

    def test_draft_source_reservation_fails_closed(self):
        with self.assertRaises(ValueError):
            plan(release('v2.0.0'), [prior('v1.0.0-c1', source=self.source['source_id'], draft=True)], [], self.source, 741)

    def test_draft_counter_and_code_are_reserved(self):
        result = plan(release('v1.15.0', prerelease=False), [prior('v1.15.0-c4', code=1000, draft=True)], [], self.source, 741)
        self.assertEqual((result['tag'], result['version_code']), ('v1.15.0-c5', 1001))

    def test_version_code_limit(self):
        with self.assertRaises(ValueError):
            plan(release('v1.15.0'), [], [], self.source, MAX_VERSION_CODE)

    def test_malformed_metadata_fails_closed(self):
        bad = release('v1.0.0-c1', body='<!-- custom-android-release: broken -->')
        with self.assertRaises(ValueError): plan(release('v1.15.0'), [bad], [], self.source, 741)

    def test_custom_release_without_marker_fails_closed(self):
        with self.assertRaisesRegex(ValueError, 'missing'):
            plan(release('v1.15.0'), [release('v1.15.0-c1')], [], self.source, 741)

    def test_request_only_changes_do_not_change_source_digest(self):
        with tempfile.TemporaryDirectory() as root:
            def git(*args):
                return subprocess.check_output(['git', '-C', root, *args], text=True).strip()
            git('init', '-q'); git('config', 'user.name', 'Test'); git('config', 'user.email', 'test@example.invalid')
            Path(root, 'source').write_text('real source'); git('add', '.'); git('commit', '-qm', 'source')
            original = source_digest(root)
            request = Path(root, '.github/custom-release/request.json')
            request.parent.mkdir(parents=True); request.write_text('{}')
            git('add', '.'); git('commit', '-qm', 'request')
            self.assertEqual(source_digest(root), original)
            Path(root, 'source').write_text('changed source'); git('commit', '-qam', 'real change')
            self.assertNotEqual(source_digest(root), original)

    def test_dispatch_and_connector_requests(self):
        a, b = 'a' * 40, 'b' * 40
        self.assertEqual(resolve('workflow_dispatch', a, b), (a, b))
        self.assertEqual(resolve('push', a, '', {'schema': 1, 'source_sha': a, 'core_sha': b}), (a, b))
        for bad in ('main', 'a' * 7, '$(touch bad)', 'A' * 40):
            with self.assertRaises(ValueError): resolve('workflow_dispatch', a, bad)
        with self.assertRaises(ValueError): resolve('push', a, '', {'schema': 1, 'source_sha': a, 'core_sha': b, 'extra': True})


if __name__ == '__main__':
    unittest.main()
