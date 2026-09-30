#!/usr/bin/env python3
"""Reject publication after source rewrites, new code or superseding requests."""
from pathlib import Path
import subprocess

from plan_android_release import git, source_digest

REQUEST_PATH = '.github/custom-release/request.json'


def request_blob(repo, ref):
    entry = git(repo, 'ls-tree', ref, '--', REQUEST_PATH)
    return entry.split()[2] if entry else None


def require_ancestor(repo, ancestor, descendant, label):
    result = subprocess.run(['git', '-C', str(repo), 'merge-base', '--is-ancestor', ancestor, descendant],
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False)
    if result.returncode:
        raise RuntimeError(f'Stale release: {label} history was changed or original source is unavailable')


def check_fresh(plan, app_repo, core_repo, workflow_commit,
                app_ref='refs/remotes/origin/dev', core_ref='refs/remotes/origin/custom-dev'):
    app_head = git(app_repo, 'rev-parse', app_ref + '^{commit}')
    core_head = git(core_repo, 'rev-parse', core_ref + '^{commit}')
    require_ancestor(app_repo, workflow_commit, app_head, 'Android workflow')
    require_ancestor(app_repo, plan['app_commit'], app_head, 'Android source')
    require_ancestor(core_repo, plan['core_commit'], core_head, 'core source')
    if source_digest(app_repo, app_head) != plan['app_source_digest']:
        raise RuntimeError('Stale release: Android dev source changed during the build')
    if source_digest(core_repo, core_head) != plan['core_source_digest']:
        raise RuntimeError('Stale release: core custom-dev source changed during the build')
    if request_blob(app_repo, workflow_commit) != request_blob(app_repo, app_head):
        raise RuntimeError('Stale release: a newer Android request superseded this run')
    return app_head, core_head


def refresh_and_check(plan, app_repo, core_repo, workflow_commit):
    core_repo = Path(core_repo)
    if not (core_repo / 'HEAD').exists():
        subprocess.run(['git', 'init', '--bare', '--quiet', str(core_repo)], check=True)
        subprocess.run(['git', '-C', str(core_repo), 'remote', 'add', 'origin',
                        'https://github.com/csbxd/sing-box.git'], check=True)
    # Updating local tracking refs is read-only with respect to GitHub, including
    # force-push detection. No push, ref replacement, or credential persistence.
    subprocess.run(['git', '-C', str(app_repo), 'fetch', '--no-tags', 'origin',
                    '+refs/heads/dev:refs/remotes/origin/dev'], check=True)
    subprocess.run(['git', '-C', str(core_repo), 'fetch', '--filter=blob:none', '--no-tags', 'origin',
                    '+refs/heads/custom-dev:refs/remotes/origin/custom-dev'], check=True)
    return check_fresh(plan, app_repo, core_repo, workflow_commit)
