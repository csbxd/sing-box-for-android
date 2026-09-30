#!/usr/bin/env python3
"""Fail closed unless APK signature, release flags and versions match the plan."""
import argparse
from pathlib import Path
import re
import subprocess
import sys


def signing_digests(signature):
    lines = [line.strip() for line in signature.splitlines()]
    counts = [line.removeprefix('Number of signers: ') for line in lines
              if line.startswith('Number of signers: ')]
    if counts != ['1']:
        raise ValueError('APK must have exactly one signer; reported counts: ' + repr(counts))
    # Build Tools 37 was reproduced with Google's exact SDK binary and public
    # signed APKs: it emits "V2 Signer:" / "V3.0 Signer:" / SDK-ranged labels.
    sdk_range = r'\(minSdkVersion=\d+(?: \(dev release=true\))?, maxSdkVersion=\d+\)'
    legacy = re.compile(r'^Signer (#[1-9]\d*|' + sdk_range + r') certificate SHA-256 digest: ([0-9a-fA-F]{64})$')
    current = re.compile(r'^(V(?:1|2|3\.[012]) Signer(?: #[1-9]\d*)?:)(?: ' + sdk_range + r')? certificate SHA-256 digest: ([0-9a-fA-F]{64})$')
    identities, digests = [], []
    for line in lines:
        if ' certificate SHA-256 digest:' not in line:
            continue
        # Source-stamp certificates are not APK signing identities.
        if line.startswith(('Source Stamp Signer certificate ', 'Source Stamp Signer: certificate ')):
            continue
        match = legacy.fullmatch(line) or current.fullmatch(line)
        if not match:
            raise ValueError('Unrecognized APK signer certificate output; refusing to guess')
        identities.append(match[1])
        digests.append(match[2].lower())
    if not digests:
        raise ValueError('No APK signer certificate found in apksigner output')
    indexed = [identity for identity in identities if identity.startswith('#')]
    if indexed and (indexed != ['#1'] or len(identities) != 1):
        raise ValueError('Unexpected additional or mixed APK signer identities')
    if any(re.search(r'#(?!1(?:$|:))', identity) for identity in identities):
        raise ValueError('Unexpected additional indexed APK signer')
    return digests


def validate(signature, badging, certificate, version, code):
    if not re.fullmatch(r'[0-9a-fA-F]{64}', certificate):
        raise ValueError('Invalid expected signing certificate SHA-256')
    digests = signing_digests(signature)
    if set(digests) != {certificate.lower()}:
        raise ValueError('APK signing certificate differs from pinned SHA-256: ' + repr(digests))
    if re.search(r'^application-debuggable(?:\s|$|:)', badging, re.M):
        raise ValueError('Refusing debuggable APK')
    package = re.search(r'^package: (.+)$', badging, re.M)
    if not package:
        raise ValueError('APK package metadata missing')
    values = dict(re.findall(r"(\w+)='([^']*)'", package[1]))
    if values.get('versionCode') != str(code) or values.get('versionName') != version:
        raise ValueError('APK version differs from planned release')
    if values.get('name') != 'io.nekohasekai.sfa':
        raise ValueError('Unexpected APK application ID')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--apk', required=True)
    parser.add_argument('--build-tools', type=Path, required=True)
    parser.add_argument('--certificate', required=True)
    parser.add_argument('--version', required=True)
    parser.add_argument('--code', type=int, required=True)
    args = parser.parse_args()
    result = subprocess.run([str(args.build_tools / 'apksigner'), 'verify', '--verbose',
                             '--print-certs', args.apk], capture_output=True, text=True)
    # This command reads only the APK: its complete stdout/stderr contain public
    # certificate/verification information, never keystore or password material.
    print(result.stdout, end="", flush=True)
    print(result.stderr, end="", file=sys.stderr, flush=True)
    result.check_returncode()
    signature = result.stdout
    print('Expected signing certificate SHA-256: ' + args.certificate, flush=True)
    badging = subprocess.check_output([str(args.build_tools / 'aapt'), 'dump', 'badging', args.apk], text=True)
    validate(signature, badging, args.certificate, args.version, args.code)
    print('Verified signed release APK: ' + args.apk)


if __name__ == '__main__':
    main()
