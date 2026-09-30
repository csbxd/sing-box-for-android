#!/usr/bin/env python3
"""Fail closed unless APK signature, release flags and versions match the plan."""
import argparse
from pathlib import Path
import re
import subprocess


def signing_digests(signature):
    lines = [line.strip() for line in signature.splitlines()]
    counts = [line.removeprefix('Number of signers: ') for line in lines
              if line.startswith('Number of signers: ')]
    if counts != ['1']:
        raise ValueError('APK must have exactly one signer; reported counts: ' + repr(counts))
    # Official apksigner uses SDK-range labels for APK Signature Scheme v3.1,
    # potentially printing the same certificate once for each supported range.
    # Source Stamp Signer is intentionally not an APK signing identity.
    label = r'(#[1-9]\d*|\(minSdkVersion=\d+(?: \(dev release=true\))?, maxSdkVersion=\d+\))'
    pattern = re.compile(r'^Signer ' + label + r' certificate SHA-256 digest: ([0-9a-fA-F]{64})$')
    identities, digests = [], []
    for line in lines:
        if not line.startswith('Signer ') or ' certificate SHA-256 digest:' not in line:
            continue
        match = pattern.fullmatch(line)
        if not match:
            raise ValueError('Unrecognized APK signer certificate output; refusing to guess')
        identities.append(match[1])
        digests.append(match[2].lower())
    if not digests:
        raise ValueError('No APK signer certificate found in apksigner output')
    indexed = [identity for identity in identities if identity.startswith('#')]
    if indexed and (indexed != ['#1'] or len(identities) != 1):
        raise ValueError('Unexpected additional or mixed APK signer identities')
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
    signature = subprocess.check_output([str(args.build_tools / 'apksigner'), 'verify', '--verbose',
                                         '--print-certs', args.apk], text=True)
    for line in signature.splitlines():
        if line.startswith('Number of signers: ') or (line.startswith('Signer ') and ' certificate SHA-256 digest:' in line):
            print(line, flush=True)  # Public certificate metadata only; never key/password data.
    print('Expected signing certificate SHA-256: ' + args.certificate, flush=True)
    badging = subprocess.check_output([str(args.build_tools / 'aapt'), 'dump', 'badging', args.apk], text=True)
    validate(signature, badging, args.certificate, args.version, args.code)
    print('Verified signed release APK: ' + args.apk)


if __name__ == '__main__':
    main()
