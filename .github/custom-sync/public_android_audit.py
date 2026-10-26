#!/usr/bin/env python3
"""Read-only public Android release byte verification. Never executes APKs."""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import urllib.request

REPO = "csbxd/sing-box-for-android"

def require(condition, message):
    if not condition:
        raise RuntimeError(message)

def api(path):
    return json.loads(subprocess.check_output(
        ["gh", "api", f"repos/{REPO}/{path}"], text=True))

def snapshot(release):
    return {
        "id": release["id"],
        "tag_name": release["tag_name"],
        "draft": release["draft"],
        "prerelease": release["prerelease"],
        "body": release["body"],
        "assets": sorted(
            [(a["id"], a["name"], a["size"], a.get("digest"),
              a["browser_download_url"], a["updated_at"])
             for a in release["assets"]])
    }

def main():
    require(os.environ["GITHUB_REPOSITORY"] == REPO, "Wrong repository")
    request = json.loads(Path(
        ".github/custom-sync/public-android-audit-request.json").read_text())
    require(set(request) == {
        "schema", "request_id", "tag", "source_sha",
        "source_tree", "core_sha", "version_code", "certificate_sha256"}, "Unexpected request fields")
    require(request["schema"] == 1, "Wrong schema")
    require(re.fullmatch(r"[A-Za-z0-9._-]{1,100}", request["request_id"]),
            "Invalid request ID")
    tag = request["tag"]
    require(re.fullmatch(r"v\d+\.\d+\.\d+(?:-[a-z]+\.\d+\.c\d+|-c\d+)", tag),
            "Invalid tag")
    for field in ("source_sha", "source_tree", "core_sha"):
        require(re.fullmatch(r"[0-9a-f]{40}", request[field]), field)
    require(re.fullmatch(r"[0-9a-f]{64}", request["certificate_sha256"]),
            "Invalid certificate fingerprint")
    require(type(request["version_code"]) is int and 0 < request["version_code"] <= 2100000000,
            "Invalid version code")

    release = api(f"releases/tags/{tag}")
    require(not release["draft"] and release["tag_name"] == tag,
            "Release is not public")
    ref = api(f"git/ref/tags/{tag}")["object"]
    require(ref["type"] == "commit" and ref["sha"] == request["source_sha"],
            "Tag does not identify exact source")
    commit = api(f"git/commits/{request['source_sha']}")
    require(commit["tree"]["sha"] == request["source_tree"], "Wrong source tree")

    version = tag[1:]
    apks = {
        f"SFA-{version}-{flavor}{arch}.apk"
        for flavor in ("", "legacy-android-5-")
        for arch in ("arm64-v8a", "armeabi-v7a", "x86", "x86_64", "universal")
    }
    manifests = {"SFA-version-metadata.json", "release-plan.json"}
    expected = apks | manifests | {"SHA256SUMS"}
    assets = release["assets"]
    require(len(assets) == 13 and {a["name"] for a in assets} == expected,
            "Unexpected or duplicate asset set")
    digests = {}
    texts = {}
    for asset in assets:
        name = asset["name"]
        url = f"https://github.com/{REPO}/releases/download/{tag}/{name}"
        require(asset["browser_download_url"] == url, "Unexpected asset URL")
        require(asset["state"] == "uploaded", "Asset incomplete")
        limit = 256 * 1024 * 1024 if name in apks else 1024 * 1024
        require(0 < asset["size"] <= limit, "Asset size outside bound")
        digest = hashlib.sha256()
        size = 0
        data = bytearray()
        # No Authorization header is sent to download URLs or redirect targets.
        with urllib.request.urlopen(url, timeout=60) as response:
            require(response.status == 200, "Download failed")
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                size += len(chunk)
                require(size <= limit, "Download exceeded bound")
                digest.update(chunk)
                if name not in apks:
                    data.extend(chunk)
        value = digest.hexdigest()
        require(size == asset["size"], "Downloaded size mismatch")
        require(asset.get("digest") == "sha256:" + value,
                "Public bytes disagree with GitHub digest")
        digests[name] = value
        if name not in apks:
            texts[name] = data.decode("utf-8")

    sums = {}
    for line in texts["SHA256SUMS"].splitlines():
        match = re.fullmatch(r"([0-9a-f]{64})  ([A-Za-z0-9._-]+)", line)
        require(match is not None, "Invalid checksum line")
        value, name = match.groups()
        require(name not in sums, "Duplicate checksum")
        sums[name] = value
    require(set(sums) == apks | manifests, "Checksum manifest asset set differs")
    require(all(sums[name] == digests[name] for name in apks | manifests),
            "Checksum manifest does not match public bytes")

    metadata = json.loads(texts["release-plan.json"])
    version_metadata = json.loads(texts["SFA-version-metadata.json"])
    markers = re.findall(
        r"<!-- custom-android-release: (\{[^\n]+\}) -->", release["body"])
    require(len(markers) == 1, "Missing or ambiguous metadata marker")
    require(metadata == json.loads(markers[0]), "Metadata file/marker mismatch")
    for key, field in (("app_commit", "source_sha"), ("app_tree", "source_tree"),
                       ("core_commit", "core_sha"), ("tag", "tag"),
                       ("version_code", "version_code"),
                       ("signing_certificate_sha256", "certificate_sha256")):
        require(metadata[key] == request[field], "Metadata mismatch: " + key)
    require(metadata["schema"] == 1 and metadata["version"] == version and metadata["skip"] is False,
            "Invalid version metadata")
    require(version_metadata == {"version_name": version, "version_code": request["version_code"]},
            "Updater version metadata differs")
    require(metadata["prerelease"] == release["prerelease"],
            "Prerelease metadata mismatch")
    require(metadata["verification_commit"] == request["source_sha"],
            "Verification source mismatch")
    require(type(metadata["build_run_id"]) is int and type(metadata["build_artifact_id"]) is int,
            "Invalid build provenance")
    run = api(f"actions/runs/{metadata['build_run_id']}")
    require(run["status"] == "completed" and run["conclusion"] == "success",
            "Signed build did not finish successfully")
    require(run["head_sha"] == metadata["build_workflow_commit"]
            and run["path"] == ".github/workflows/custom-android-release.yml",
            "Build workflow provenance mismatch")

    require(snapshot(api(f"releases/tags/{tag}")) == snapshot(release),
            "Release changed during verification")
    require(api(f"git/ref/tags/{tag}")["object"] == ref,
            "Tag changed during verification")
    result = {
        "schema": 1,
        "request_id": request["request_id"],
        "control_commit": os.environ["GITHUB_SHA"],
        "release_url": release["html_url"],
        "source_sha": request["source_sha"],
        "source_tree": request["source_tree"],
        "core_sha": request["core_sha"],
        "version_code": request["version_code"],
        "certificate_sha256": request["certificate_sha256"],
        "asset_sha256": digests,
        "status": "verified-public-bytes"
    }
    output = json.dumps(result, indent=2) + "\n"
    Path("public-android-audit-result.json").write_text(output)
    print(output)

if __name__ == "__main__":
    main()
