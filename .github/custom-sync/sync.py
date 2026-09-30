#!/usr/bin/env python3
"""Reviewed Android branch synchronization using real cherry-picks and leases."""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess

REPO = 'csbxd/sing-box-for-android'
UPSTREAM = 'https://github.com/SagerNet/sing-box-for-android.git'
CONTROL = 'maintenance/custom-sync'
REQUEST_PATHS = {b'.github/custom-release/request.json', b'.github/custom-validation/request.json'}
SHA = re.compile(r'[0-9a-f]{40}\Z')
REPLAYS = {
    'dev': [
        '53dbcb48629f87de56ec3240436ae96f62745c19',
        '42dcd74a65f02b1fb99b5a6fe171067041355bf0',
        '354af9618526fae96314d03bd4edb83da97e76fe',
        'f82d2c96aecbd70c73061d8b8d0a43334e1a4532',
        'c40cc0e6d4bb8fcf44e3515d578910f44bddd355',
        '8ee8b9cbc8446d8c64ff52113d02b3f7e2be0061',
        '7fcc66c3b88fd697482d6d67b1ae7551c513bc89',
        'a7f3056184247f1aabb849a6456d575c7f064b1f',
    ],
    'main': [], 'stable': [], 'wip': [],
}


def raw(*args, cwd=None, data=None):
    return subprocess.check_output(args, cwd=cwd, input=data)


def git(*args, cwd=None):
    return raw('git', *args, cwd=cwd).decode().strip()


def fingerprint(sha, cwd=None):
    entries = raw('git', 'ls-tree', '-r', '-z', sha, cwd=cwd).split(b'\0')
    entries = [entry for entry in entries if entry and entry.split(b'\t', 1)[1] not in REQUEST_PATHS]
    return hashlib.sha256(b'\0'.join(entries)).hexdigest()


def metadata(sha, cwd=None):
    # Preserve exact author name/email/date and full message, including whitespace.
    return raw('git', 'show', '-s', '--format=%an%x00%ae%x00%aI%x00%B', sha, cwd=cwd)


def patch_id(sha, cwd=None):
    patch = raw('git', 'show', '--format=', '--binary', '--no-ext-diff', sha, cwd=cwd)
    result = raw('git', 'patch-id', '--stable', cwd=cwd, data=patch).split()
    if not result:
        raise RuntimeError('Empty replay patch requires explicit review: ' + sha)
    return result[0].decode()


def validate_request(request):
    if set(request) != {'schema', 'request_id', 'targets'} or request['schema'] != 1:
        raise RuntimeError('Unsupported request schema/fields')
    if not isinstance(request['request_id'], str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,80}', request['request_id']):
        raise RuntimeError('Invalid request_id')
    targets = request['targets']
    if not isinstance(targets, list) or not 1 <= len(targets) <= len(REPLAYS):
        raise RuntimeError('Invalid target count')
    seen = set()
    for target in targets:
        if not isinstance(target, dict) or set(target) not in (
                {'branch', 'expected_head', 'upstream_sha'},
                {'branch', 'expected_head', 'upstream_sha', 'expected_tree'}):
            raise RuntimeError('Unexpected target fields')
        branch = target['branch']
        if branch not in REPLAYS or branch in seen:
            raise RuntimeError('Branch is unreviewed or duplicated')
        seen.add(branch)
        for field in ('expected_head', 'upstream_sha', 'expected_tree'):
            if field in target and (not isinstance(target[field], str) or not SHA.fullmatch(target[field])):
                raise RuntimeError('Invalid immutable SHA: ' + field)


def remote_heads(remote, branches):
    refs = ['refs/heads/' + branch for branch in branches]
    output = git('ls-remote', '--exit-code', '--heads', remote, *refs)
    result = {}
    for line in output.splitlines():
        sha, ref = line.split()
        branch = ref.removeprefix('refs/heads/')
        if branch in result or branch not in branches or not SHA.fullmatch(sha):
            raise RuntimeError('Unexpected remote branch response')
        result[branch] = sha
    if set(result) != set(branches):
        raise RuntimeError('A requested branch is missing')
    return result


def ensure_request_current(request, workflow_sha):
    targets = request['targets']
    origin = remote_heads('origin', [CONTROL] + [target['branch'] for target in targets])
    if origin[CONTROL] != workflow_sha:
        raise RuntimeError('A newer control commit superseded this request')
    upstream = remote_heads(UPSTREAM, [target['branch'] for target in targets])
    for target in targets:
        branch = target['branch']
        if origin[branch] != target['expected_head']:
            raise RuntimeError('User branch changed: ' + branch)
        if upstream[branch] != target['upstream_sha']:
            raise RuntimeError('Upstream moved; submit a fresh reviewed request: ' + branch)


def validate_source(expected, state, branch):
    if state['replay_commits'] != REPLAYS[branch]:
        raise RuntimeError('Replay list changed without a reviewed state update: ' + branch)
    if fingerprint(expected) != state['source_fingerprint']:
        raise RuntimeError('Unexpected custom source changes; review before replay: ' + branch)
    subprocess.run(['git', 'merge-base', '--is-ancestor', state['source_sha'], expected], check=True)
    # Only separate release/compile-validation requests may advance between audits.
    for sha in git('rev-list', state['source_sha'] + '..' + expected).splitlines():
        if len(git('rev-list', '--parents', '-n', '1', sha).split()) != 2:
            raise RuntimeError('Unexpected merge/history change after last sync')
        paths = [path for path in raw('git', 'diff-tree', '--no-commit-id', '--name-only', '-r', '-z', sha).split(b'\0') if path]
        if not paths or any(path not in REQUEST_PATHS for path in paths):
            raise RuntimeError('Unexpected intervening user commits; review before replay')


def prepare_target(target, state, work_root):
    branch, expected, upstream = target['branch'], target['expected_head'], target['upstream_sha']
    git('fetch', '--no-tags', 'origin', expected, state['source_sha'], *REPLAYS[branch])
    git('fetch', '--no-tags', UPSTREAM, upstream)
    validate_source(expected, state, branch)
    if state['upstream_sha'] == upstream:
        if target.get('expected_tree') and target['expected_tree'] != git('rev-parse', expected + '^{tree}'):
            raise RuntimeError('No-op tree differs from independently reviewed expectation')
        return {**state, 'branch': branch, 'skip': True, 'observed_head': expected}
    work = work_root / branch
    git('worktree', 'add', '--detach', str(work), upstream)
    git('config', 'user.name', 'github-actions[bot]', cwd=work)
    git('config', 'user.email', '41898282+github-actions[bot]@users.noreply.github.com', cwd=work)
    mapping = []
    for original in REPLAYS[branch]:
        git('-c', 'rerere.enabled=false', 'cherry-pick', original, cwd=work)
        replayed = git('rev-parse', 'HEAD', cwd=work)
        before_metadata, after_metadata = metadata(original, work), metadata(replayed, work)
        if before_metadata != after_metadata:
            raise RuntimeError('Author/date/full commit message changed during cherry-pick')
        before_patch, after_patch = patch_id(original, work), patch_id(replayed, work)
        if before_patch != after_patch:
            raise RuntimeError('Stable patch ID changed; manual review is required')
        mapping.append({'original': original, 'cherry_pick': replayed, 'patch_id': after_patch,
                        'metadata_sha256': hashlib.sha256(after_metadata).hexdigest(), 'metadata_preserved': True})
    if git('status', '--porcelain', cwd=work):
        raise RuntimeError('Replay worktree is dirty')
    source = git('rev-parse', 'HEAD', cwd=work)
    tree = git('rev-parse', 'HEAD^{tree}', cwd=work)
    if target.get('expected_tree') and target['expected_tree'] != tree:
        raise RuntimeError('Final tree differs from independently reviewed expectation')
    return {'branch': branch, 'skip': False, 'upstream_sha': upstream, 'previous_head': expected,
            'source_sha': source, 'source_tree': tree, 'source_fingerprint': fingerprint(source, work),
            'replay_commits': REPLAYS[branch], 'mapping': mapping}


def main():
    if os.environ['GITHUB_REPOSITORY'] != REPO or os.environ['GITHUB_REF'] != 'refs/heads/' + CONTROL:
        raise RuntimeError('Wrong repository/control branch')
    workflow_sha = os.environ['GITHUB_SHA']
    request = json.loads(Path('.github/custom-sync/request.json').read_text())
    validate_request(request)
    state_path = Path('.github/custom-sync/state.json')
    state = json.loads(state_path.read_text())
    if state.get('schema') != 1 or set(state.get('branches', {})) != set(REPLAYS):
        raise RuntimeError('Missing or unreviewed per-branch state')
    ensure_request_current(request, workflow_sha)
    work_root = Path(os.environ['RUNNER_TEMP']) / 'android-reviewed-sync'
    work_root.mkdir(parents=True, exist_ok=False)
    # Prepare and audit every target before changing any remote source branch.
    results = [prepare_target(target, state['branches'][target['branch']], work_root)
               for target in request['targets']]
    changed = [result for result in results if not result['skip']]
    for result in changed:
        result['backup_branch'] = 'backup/sync-' + result['branch'] + '-' + request['request_id']
    audit = {'schema': 1, 'request_id': request['request_id'], 'control_commit': workflow_sha,
             'repository': REPO, 'all_noop': not changed, 'branches': results}
    Path('sync-result.json').write_text(json.dumps(audit, indent=2) + '\n')
    print(json.dumps(audit, indent=2))
    if not changed:
        print('All requested branches unchanged: no rewrite, backup, release or state commit')
        return
    ensure_request_current(request, workflow_sha)
    # Empty-value leases make backup creation create-only, including races.
    git('push', '--atomic', *['--force-with-lease=refs/heads/' + row['backup_branch'] + ':' for row in changed],
        'origin', *[row['previous_head'] + ':refs/heads/' + row['backup_branch'] for row in changed])
    ensure_request_current(request, workflow_sha)
    for row in changed:
        state['branches'][row['branch']] = row
    state_path.write_text(json.dumps(state, indent=2) + '\n')
    git('config', 'user.name', 'github-actions[bot]')
    git('config', 'user.email', '41898282+github-actions[bot]@users.noreply.github.com')
    git('add', str(state_path))
    git('commit', '-m', 'Record verified Android branch synchronization')
    state_commit = git('rev-parse', 'HEAD')
    # The source updates and state/control update form one Git transaction. A new
    # request or user source push causes its lease to reject the entire batch.
    git('push', '--atomic', '--force-with-lease=refs/heads/' + CONTROL + ':' + workflow_sha,
        *['--force-with-lease=refs/heads/' + row['branch'] + ':' + row['previous_head']
          for row in changed], 'origin', 'HEAD:refs/heads/' + CONTROL,
        *[row['source_sha'] + ':refs/heads/' + row['branch'] for row in changed])
    verified = remote_heads('origin', [CONTROL] + [row['branch'] for row in changed])
    if verified[CONTROL] != state_commit:
        raise RuntimeError('Control branch changed after the atomic push; inspect audit/state')
    for row in changed:
        if verified[row['branch']] != row['source_sha']:
            raise RuntimeError('Source branch changed after the atomic push; inspect audit/state')


if __name__ == '__main__':
    main()
