import io
import json
import os
import unittest
import urllib.error
from unittest import mock

from plan_android_release import releases


def page(nodes, next_cursor=None):
    return io.BytesIO(json.dumps({'data': {'repository': {'releases': {
        'nodes': nodes, 'pageInfo': {'hasNextPage': next_cursor is not None, 'endCursor': next_cursor}}}}}).encode())


def http_error(code):
    return urllib.error.HTTPError('https://api.github.com/graphql', code, 'test error', {}, None)


@mock.patch.dict(os.environ, {'GH_TOKEN': 'unit-test-placeholder'})
class ReleaseAPITests(unittest.TestCase):
    @mock.patch('plan_android_release.time.sleep')
    @mock.patch('plan_android_release.urllib.request.urlopen')
    def test_small_compact_pages_and_cursor(self, open_url, sleep):
        open_url.side_effect = [page([{'tagName': 'v1.15.0-alpha.9'}], 'next'), page([{'tagName': 'v1.14.2'}])]
        result = releases('SagerNet/sing-box')
        self.assertEqual(len(result), 2)
        payloads = [json.loads(call.args[0].data) for call in open_url.call_args_list]
        self.assertIn('releases(first:10,', payloads[0]['query'])
        self.assertNotIn('assets', payloads[0]['query'])
        self.assertIsNone(payloads[0]['variables']['after'])
        self.assertEqual(payloads[1]['variables']['after'], 'next')
        sleep.assert_not_called()

    @mock.patch('plan_android_release.time.sleep')
    @mock.patch('plan_android_release.urllib.request.urlopen')
    def test_failed_page_retries_without_skipping_cursor(self, open_url, sleep):
        open_url.side_effect = [page([{'tagName': 'first'}], 'next'), http_error(502),
                               TimeoutError(), io.BytesIO(b'{truncated'), page([{'tagName': 'second'}])]
        self.assertEqual([row['tagName'] for row in releases('SagerNet/sing-box')], ['first', 'second'])
        self.assertEqual([call.args[0] for call in sleep.call_args_list], [2, 4, 8])
        afters = [json.loads(call.args[0].data)['variables']['after'] for call in open_url.call_args_list]
        self.assertEqual(afters, [None, 'next', 'next', 'next', 'next'])

    @mock.patch('plan_android_release.time.sleep')
    @mock.patch('plan_android_release.urllib.request.urlopen')
    def test_exactly_four_attempts_then_fail(self, open_url, sleep):
        open_url.side_effect = http_error(503)
        with self.assertRaises(urllib.error.HTTPError): releases('SagerNet/sing-box')
        self.assertEqual(open_url.call_count, 4)
        self.assertEqual([call.args[0] for call in sleep.call_args_list], [2, 4, 8])

    @mock.patch('plan_android_release.time.sleep')
    @mock.patch('plan_android_release.urllib.request.urlopen')
    def test_authorization_and_rate_limits_fail_immediately(self, open_url, sleep):
        for code in (400, 401, 403, 404, 429):
            with self.subTest(code=code):
                open_url.reset_mock(); open_url.side_effect = http_error(code)
                with self.assertRaises(urllib.error.HTTPError): releases('SagerNet/sing-box')
                self.assertEqual(open_url.call_count, 1)
        sleep.assert_not_called()

    @mock.patch('plan_android_release.time.sleep')
    @mock.patch('plan_android_release.urllib.request.urlopen')
    def test_graphql_errors_fail_without_retry(self, open_url, sleep):
        open_url.return_value = io.BytesIO(b'{"errors":[{"message":"query denied"}]}')
        with self.assertRaisesRegex(RuntimeError, 'query denied'): releases('SagerNet/sing-box')
        self.assertEqual(open_url.call_count, 1)
        sleep.assert_not_called()

    @mock.patch('plan_android_release.time.sleep')
    @mock.patch('plan_android_release.urllib.request.urlopen')
    def test_repeated_cursor_fails_closed(self, open_url, sleep):
        open_url.side_effect = [page([], 'same'), page([], 'same')]
        with self.assertRaisesRegex(RuntimeError, 'repeated release cursor'): releases('SagerNet/sing-box')
        self.assertEqual(open_url.call_count, 2)
        sleep.assert_not_called()


if __name__ == '__main__':
    unittest.main()
