#!/usr/bin/env python3
"""Bind verification to an immutable APK-only artifact from this exact source run."""
import hashlib
import json
import os
from pathlib import Path
import re
import zipfile


def validate_artifact(info, artifact_id, digest, run_id, workflow_commit):
    if not re.fullmatch('[0-9a-f]{64}', digest):
        raise ValueError('Invalid build artifact SHA-256')
    if (info.get('id') != int(artifact_id) or info.get('name') != 'release-apk-build-output'
            or info.get('expired') is not False or info.get('digest') != 'sha256:' + digest):
        raise ValueError('Artifact identity/digest differs from successful build output')
    run = info.get('workflow_run', {})
    if run.get('id') != int(run_id) or run.get('head_sha') != workflow_commit:
        raise ValueError('Artifact belongs to a different workflow run/source')


def extract_verified_zip(archive, expected_digest, destination):
    with open(archive, 'rb') as source:
        actual = hashlib.file_digest(source, 'sha256').hexdigest()
    if actual != expected_digest:
        raise ValueError('Downloaded artifact ZIP SHA-256 mismatch')
    with zipfile.ZipFile(archive) as package:
        entries = package.infolist()
        names = [entry.filename for entry in entries]
        if len(entries) != 10 or len(set(names)) != 10 or any(
                entry.is_dir() or Path(entry.filename).name != entry.filename
                or not entry.filename.endswith('.apk') or 'unsigned' in entry.filename
                or 'debug' in entry.filename for entry in entries):
            raise ValueError('Build artifact must contain exactly ten flat release APK files')
        destination = Path(destination)
        destination.mkdir(parents=True, exist_ok=False)
        for entry in entries:
            (destination / entry.filename).write_bytes(package.read(entry))


def main():
    validate_artifact(json.loads(Path('artifact-provenance.json').read_text()),
                      os.environ['BUILD_ARTIFACT_ID'], os.environ['BUILD_ARTIFACT_SHA256'],
                      os.environ['GITHUB_RUN_ID'], os.environ['GITHUB_SHA'])
    extract_verified_zip('apk-build-output.zip', os.environ['BUILD_ARTIFACT_SHA256'], 'built-apks')
    print('Verified artifact identity, source run and actual ZIP SHA-256 before APK-only extraction')


if __name__ == '__main__':
    main()
