#!/usr/bin/env python3
"""Plan immutable Android releases from GitHub Releases and exact source trees."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import urllib.request

BASE_RE = re.compile(r"^v?(\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?)$")
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
MARKER_RE = re.compile(r"<!-- custom-android-release: (.*?) -->")
MAX_VERSION_CODE = 2_100_000_000


def git(repo, *args):
    return subprocess.check_output(["git", "-C", str(repo), *args], text=True).strip()


def releases(repository):
    """GraphQL avoids downloading every large release's complete asset list."""
    owner, name = repository.split("/")
    query = """query($owner:String!,$name:String!,$after:String) {
      repository(owner:$owner,name:$name) {
        releases(first:100,after:$after,orderBy:{field:CREATED_AT,direction:DESC}) {
          nodes { tagName isPrerelease isDraft publishedAt description tagCommit { oid } }
          pageInfo { hasNextPage endCursor }
        }
      }
    }"""
    result, after = [], None
    while True:
        request = urllib.request.Request(
            "https://api.github.com/graphql",
            data=json.dumps({"query": query, "variables": {
                "owner": owner, "name": name, "after": after}}).encode(),
            headers={"Authorization": "Bearer " + os.environ["GH_TOKEN"],
                     "Content-Type": "application/json", "User-Agent": "custom-android-release"})
        with urllib.request.urlopen(request, timeout=120) as response:
            payload = json.load(response)
        if payload.get("errors"):
            raise RuntimeError(str(payload["errors"]))
        page = payload["data"]["repository"]["releases"]
        result.extend(page["nodes"])
        if not page["pageInfo"]["hasNextPage"]:
            return result
        after = page["pageInfo"]["endCursor"]


def version_key(tag):
    match = BASE_RE.fullmatch(tag)
    if not match:
        raise ValueError("Invalid source/release version: " + tag)
    version = match[1]
    numeric, separator, prerelease = version.partition("-")
    numbers = tuple(int(part) for part in numeric.split("."))
    if separator:
        identifiers = prerelease.split(".")
        if any(not item or (item.isdigit() and len(item) > 1 and item[0] == "0") for item in identifiers):
            raise ValueError("Invalid SemVer prerelease: " + tag)
        order = tuple((0, int(item)) if item.isdigit() else (1, item) for item in identifiers)
        return (*numbers, 0, order)
    return (*numbers, 1, ())


def source_version(changelog):
    for heading in re.finditer(r"(?m)^#{1,6}\s+(v?[0-9A-Za-z.-]+)(?:\s|$)", changelog):
        if BASE_RE.fullmatch(heading[1]):
            version_key(heading[1])
            return heading[1].removeprefix("v")
    raise ValueError("No source version heading found in exact core docs/changelog.md")


def source_digest(repo, ref="HEAD"):
    # Both repositories accept the same connector-only trigger path.
    entries = "\n".join(line for line in git(repo, "ls-tree", "-r", ref).splitlines()
                        if line.split("\t", 1)[1] != ".github/custom-release/request.json")
    return hashlib.sha256(entries.encode()).hexdigest()


def choose_base(upstream, source):
    series = version_key(source)[:3]
    candidates = [r for r in upstream if not r["isDraft"]
                  and BASE_RE.fullmatch(r["tagName"])
                  and version_key(r["tagName"])[:3] == series
                  and r.get("tagCommit")]
    if not candidates:
        raise ValueError("No published upstream Release matches source series " + ".".join(map(str, series)))
    # SemVer order, not commit ancestry or publication recency. The upstream
    # testing branch can rewrite history while keeping an existing Release.
    return max(candidates, key=lambda r: (version_key(r["tagName"]), r.get("publishedAt") or "", r["tagName"]))


def markers(existing):
    result = []
    for release in existing:
        body = release.get("description") or ""
        if "<!-- custom-android-release:" not in body:
            if re.fullmatch(r"v?\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+\.c|-c)\d+", release["tagName"]):
                raise ValueError("Custom release is missing its versionCode/source marker: " + release["tagName"])
            continue
        found = MARKER_RE.findall(body)
        if len(found) != 1:
            raise ValueError("Malformed release metadata: " + release["tagName"])
        info = json.loads(found[0])
        if (info.get("schema") != 1 or type(info.get("version_code")) is not int
                or not 0 < info["version_code"] <= MAX_VERSION_CODE
                or not re.fullmatch(r"[0-9a-f]{64}", info.get("source_id", ""))
                or info.get("tag") != release["tagName"]):
            raise ValueError("Invalid release metadata: " + release["tagName"])
        result.append((release, info))
    return result


def plan(base, existing, tags, source, initial_code):
    records = markers(existing)
    for release, info in records:
        if info["source_id"] == source["source_id"]:
            if release["isDraft"]:
                raise ValueError("A draft already reserves this source: " + release["tagName"]
                                 + ". Inspect/finish that draft; do not overwrite its tag or assets.")
            return {"skip": True, "reason": "source already published", "tag": release["tagName"]}
    version = BASE_RE.fullmatch(base["tagName"])[1]
    prefix = version + (".c" if "-" in version else "-c")
    used = set(tags) | {r["tagName"] for r in existing}
    revisions = [int(m[1]) for tag in used
                 if (m := re.fullmatch(r"v?" + re.escape(prefix) + r"(\d+)", tag))]
    revision = max(revisions, default=0) + 1
    code = max([initial_code] + [info["version_code"] for _, info in records]) + 1
    if code > MAX_VERSION_CODE:
        raise ValueError("Android versionCode range exhausted")
    return {**source, "schema": 1, "skip": False, "base_tag": base["tagName"],
            "base_commit": base["tagCommit"]["oid"], "version": prefix + str(revision),
            "tag": "v" + prefix + str(revision), "version_code": code,
            "prerelease": bool(base["isPrerelease"] or "-" in version)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--core", required=True, type=Path)
    parser.add_argument("--core-sha", required=True)
    parser.add_argument("--app", default=".", type=Path)
    parser.add_argument("--repository", default="csbxd/sing-box-for-android")
    parser.add_argument("--output", default="release-plan.json", type=Path)
    args = parser.parse_args()
    if args.repository != "csbxd/sing-box-for-android" or not SHA_RE.fullmatch(args.core_sha):
        raise ValueError("Use the expected repository and a full lowercase 40-character core commit")
    if git(args.core, "rev-parse", "HEAD") != args.core_sha:
        raise ValueError("Core checkout is not the requested exact commit")
    subprocess.run(["git", "-C", str(args.core), "merge-base", "--is-ancestor",
                    args.core_sha, "refs/remotes/origin/custom-dev"], check=True)
    app_sha = git(args.app, "rev-parse", "HEAD")
    subprocess.run(["git", "-C", str(args.app), "merge-base", "--is-ancestor", app_sha,
                    "refs/remotes/origin/dev"], check=True)
    app_tree = git(args.app, "rev-parse", "HEAD^{tree}")
    core_tree = git(args.core, "rev-parse", "HEAD^{tree}")
    # Connector-only request changes in either repository are not new source.
    app_source_digest = source_digest(args.app)
    core_source_digest = source_digest(args.core)
    source_id = hashlib.sha256((app_source_digest + "\n" + core_source_digest).encode()).hexdigest()
    source = {"app_commit": app_sha, "app_tree": app_tree, "core_commit": args.core_sha,
              "core_tree": core_tree, "source_id": source_id, "app_source_digest": app_source_digest, "core_source_digest": core_source_digest}
    props = dict(line.split("=", 1) for line in (args.app / "version.properties").read_text().splitlines()
                 if line and not line.startswith("#"))
    upstream = releases("SagerNet/sing-box")
    version = source_version((args.core / "docs/changelog.md").read_text())
    source.update(source_version=version, version_policy="source-series-latest")
    base = choose_base(upstream, version)
    result = plan(base, releases(args.repository), git(args.app, "tag", "--list").splitlines(),
                  source, int(props["VERSION_CODE"]))
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a") as output:
            for key in ("skip", "tag", "version", "version_code", "prerelease", "core_commit", "app_commit"):
                if key in result:
                    value = str(result[key]).lower() if isinstance(result[key], bool) else result[key]
                    output.write(f"{key}={value}\n")
            output.write(f"go_version={props['GO_VERSION'].removeprefix('go')}\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
