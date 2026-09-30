#!/usr/bin/env python3
"""Resolve direct GitHub connector requests without accepting shell expressions."""
import json
import os
from pathlib import Path
import re
import subprocess


def resolve(event, workflow_sha, manual_core, request=None):
    if event == 'workflow_dispatch':
        app, core = workflow_sha, manual_core
    elif event == 'push':
        if request is None or request.get('schema') != 1 or set(request) != {'schema', 'source_sha', 'core_sha'}:
            raise ValueError('Request requires exactly schema:1, source_sha and core_sha')
        app, core = request['source_sha'], request['core_sha']
    else:
        raise ValueError('Unsupported trigger')
    if not all(isinstance(s, str) and re.fullmatch('[0-9a-f]{40}', s) for s in (app, core)):
        raise ValueError('Exact full lowercase 40-character commit SHAs are required')
    return app, core


def main():
    event = os.environ['GITHUB_EVENT_NAME']
    request = json.loads(Path('.github/custom-release/request.json').read_text()) if event == 'push' else None
    app, core = resolve(event, os.environ['GITHUB_SHA'], os.environ.get('CORE_COMMIT', ''), request)
    subprocess.run(['git', 'merge-base', '--is-ancestor', app, os.environ['GITHUB_SHA']], check=True)
    with open(os.environ['GITHUB_OUTPUT'], 'a') as output:
        output.write(f'app_commit={app}\ncore_commit={core}\n')


if __name__ == '__main__':
    main()
