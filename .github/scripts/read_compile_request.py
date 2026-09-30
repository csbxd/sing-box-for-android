#!/usr/bin/env python3
"""Validate exact sources for compile-only CI; no release planning or publication."""
import json
import os
from pathlib import Path
import re
import subprocess

SHA = re.compile(r"[0-9a-f]{40}")
VERSION = re.compile(r"[0-9]+\.[0-9]+\.[0-9]+(?:-[0-9A-Za-z.-]+)?")

def resolve(request):
    if (not isinstance(request, dict) or type(request.get("schema")) is not int
            or request["schema"] != 1
            or set(request) != {"schema", "source_sha", "core_sha", "core_version"}):
        raise ValueError("Require schema:1, source_sha, core_sha and core_version only")
    app, core, version = (request[key] for key in ("source_sha", "core_sha", "core_version"))
    if not all(isinstance(value, str) and SHA.fullmatch(value) for value in (app, core)):
        raise ValueError("Require full lowercase source commit SHAs")
    if not isinstance(version, str) or not VERSION.fullmatch(version):
        raise ValueError("Require a single-line core version")
    return app, core, version

def git(repo, *args):
    return subprocess.check_output(["git", "-C", repo, *args], text=True).strip()

def main():
    if (os.environ["GITHUB_EVENT_NAME"] != "push"
            or os.environ["GITHUB_REPOSITORY"] != "csbxd/sing-box-for-android"
            or os.environ["GITHUB_REF"] != "refs/heads/dev"):
        raise ValueError("Compile checks run only from the expected dev push")
    app, core, version = resolve(json.loads(Path(".github/custom-validation/request.json").read_text()))
    for repo, source, ancestor in ((".", app, os.environ["GITHUB_SHA"]),
                                   (".", app, "origin/dev"),
                                   ("core", core, "origin/custom-dev")):
        subprocess.run(["git", "-C", repo, "merge-base", "--is-ancestor", source, ancestor], check=True)
    # A core tag is immutable input too; refuse a version/source mismatch.
    if git("core", "rev-parse", "refs/tags/v" + version + "^{commit}") != core:
        raise ValueError("Requested core version tag does not identify the exact core SHA")
    props = dict(line.split("=", 1) for line in git(".", "show", app + ":version.properties").splitlines()
                 if line and not line.startswith("#"))
    go = props["GO_VERSION"].removeprefix("go")
    if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", go):
        raise ValueError("Invalid exact Go version")
    code = int(props["VERSION_CODE"]) + 1
    if not 1 <= code <= 2100000000:
        raise ValueError("Invalid compile-check Android version code")
    with open(os.environ["GITHUB_OUTPUT"], "a") as output:
        output.write(f"app_commit={app}\ncore_commit={core}\ncore_version={version}\ngo_version={go}\nversion_code={code}\n")
    with open(os.environ["GITHUB_STEP_SUMMARY"], "a") as summary:
        summary.write(f"Compile-only validation\n\nAndroid: {app}\n\nCore: {core} ({version})\n\n"
                      "No signing secrets, APK upload, tag, or Release publication.\n")

if __name__ == "__main__":
    main()
