#!/usr/bin/env python3
"""Fail closed unless APK signature, release flags and versions match the plan."""
import argparse
from pathlib import Path
import re
import subprocess


def validate(signature, badging, certificate, version, code):
    digests = re.findall(r'^Signer #\d+ certificate SHA-256 digest: ([0-9a-fA-F]+)$', signature, re.M)
    if [digest.lower() for digest in digests] != [certificate.lower()]:
        raise ValueError('APK must have exactly the pinned signing certificate')
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
    badging = subprocess.check_output([str(args.build_tools / 'aapt'), 'dump', 'badging', args.apk], text=True)
    validate(signature, badging, args.certificate, args.version, args.code)
    print('Verified signed release APK: ' + args.apk)


if __name__ == '__main__':
    main()
