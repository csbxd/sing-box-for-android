#!/usr/bin/env python3
"""Publish verified signed artifacts. Never overwrite tags, releases, or assets."""
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
from plan_android_release import releases, markers
from check_release_freshness import refresh_and_check


def gh(*args, **kwargs):
    return subprocess.run(["gh", *args], check=True, text=True, **kwargs)


def main():
    repo = os.environ["GITHUB_REPOSITORY"]
    assert repo == "csbxd/sing-box-for-android"
    plan = json.loads(Path("dist/release-plan.json").read_text())
    assert plan["app_commit"] == os.environ["EXPECTED_APP_COMMIT"]
    assert re.fullmatch(r"v\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+\.c|-c)[1-9]\d*", plan["tag"])
    assert re.fullmatch(r"[0-9a-f]{64}", plan["signing_certificate_sha256"])
    apks = sorted(Path("dist").glob("*.apk"))
    assert len(apks) == 10 and all("unsigned" not in p.name and "debug" not in p.name for p in apks)
    subprocess.run(["sha256sum", "--check", "SHA256SUMS"], cwd="dist", check=True)
    # Recheck source and global versionCode watermark immediately before publication.
    current = releases(repo)
    for release, info in markers(current):
        if info["source_id"] == plan["source_id"]:
            raise RuntimeError("Source was already published/reserved: " + release["tagName"])
        if info.get("signing_certificate_sha256") != plan["signing_certificate_sha256"]:
            raise RuntimeError("Signing certificate differs from a prior custom release; refusing key rotation")
        if info["version_code"] >= plan["version_code"]:
            raise RuntimeError("versionCode was overtaken; rerun planning")
    if any(r["tagName"] == plan["tag"] for r in current):
        raise RuntimeError("Release already exists; refusing to overwrite")
    marker = "<!-- custom-android-release: " + json.dumps(plan, separators=(",", ":")) + " -->"
    body = f"""Custom signed Android build {plan['version']}

- Version policy: latest upstream Release in exact source series ({plan["source_version"]})
- Upstream base Release: https://github.com/SagerNet/sing-box/releases/tag/{plan['base_tag']}
- Exact core source: https://github.com/csbxd/sing-box/commit/{plan['core_commit']}
- Exact Android source: https://github.com/{repo}/commit/{plan['app_commit']}
- Android versionCode: {plan['version_code']}
- Signing certificate SHA-256: {plan['signing_certificate_sha256']}
- Install the universal APK for your Android version, or choose the matching ABI
- Legacy APKs support Android 5+; other APKs require Android 7+

This fork is signed with its owner's key. Back up profiles before replacing an app signed with another key; Android cannot update it in place. Exact source links, build workflow, metadata and SHA256SUMS accompany this release.

{marker}
"""
    Path("release-notes.md").write_text(body)
    core_dir = tempfile.TemporaryDirectory(prefix="android-release-core-")
    try:
        publish(plan, repo, apks, core_dir.name)
    finally:
        core_dir.cleanup()


def publish(plan, repo, apks, core_dir):
    # Refresh immediately before each external publication transition. A stale
    # run may leave its existing draft/tag for inspection, but never overwrites it.
    refresh_and_check(plan, Path.cwd(), core_dir, os.environ["GITHUB_SHA"])
    # POST is create-only. A collision fails even if another actor just created the tag.
    gh("api", "--method", "POST", f"repos/{repo}/git/refs", "-f", "ref=refs/tags/" + plan["tag"],
       "-f", "sha=" + plan["app_commit"])
    args = ["release", "create", plan["tag"], "--repo", repo, "--verify-tag", "--draft",
            "--title", plan["version"], "--notes-file", "release-notes.md"]
    if plan["prerelease"]:
        args.append("--prerelease")
    args += [str(p) for p in apks] + ["dist/SFA-version-metadata.json", "dist/release-plan.json", "dist/SHA256SUMS"]
    refresh_and_check(plan, Path.cwd(), core_dir, os.environ["GITHUB_SHA"])
    gh(*args)
    # Failed uploads leave a draft and reserved metadata for inspection, never replacement.
    refresh_and_check(plan, Path.cwd(), core_dir, os.environ["GITHUB_SHA"])
    gh("release", "edit", plan["tag"], "--repo", repo, "--draft=false",
       "--latest=" + ("false" if plan["prerelease"] else "true"))
    gh("release", "view", plan["tag"], "--repo", repo, "--json", "url,isDraft,tagName")


if __name__ == "__main__":
    main()
