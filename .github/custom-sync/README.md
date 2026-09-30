# Reviewed Android branch synchronization

This control branch is the direct-GitHub route for the owner's weekly synchronization. It uses GitHub Actions and the built-in, job-scoped repository `GITHUB_TOKEN`; it does not create credentials, use Work/Codex/cloud tasks, sign APKs, or publish releases.

## Coverage and request

The complete reviewed same-name upstream branch set is `dev`, `main`, `stable`, and `wip`, synchronized from the corresponding branches of `SagerNet/sing-box-for-android`. `dev` preserves the explicitly reviewed custom build/updater and CI commits through **actual `git cherry-pick`**. The other three currently have no custom commits. Control/backup branches are not synchronization targets. A newly discovered matching branch must be reviewed and added to the whitelist/state before it can be requested; never silently reset an unreviewed branch.

The weekly parent process supplies the cadence. This workflow deliberately has no independent cron schedule: it runs only when the authorized process updates `.github/custom-sync/request.json` on `maintenance/custom-sync` through the GitHub connector. First read current fork/upstream heads and `.github/custom-sync/state.json`, then write a unique request:

```json
{
  "schema": 1,
  "request_id": "20261005-reviewed-all-branches",
  "targets": [
    {
      "branch": "dev",
      "expected_head": "FULL_CURRENT_FORK_DEV_COMMIT",
      "upstream_sha": "FULL_CURRENT_UPSTREAM_DEV_COMMIT"
    },
    {
      "branch": "main",
      "expected_head": "FULL_CURRENT_FORK_MAIN_COMMIT",
      "upstream_sha": "FULL_CURRENT_UPSTREAM_MAIN_COMMIT"
    },
    {
      "branch": "stable",
      "expected_head": "FULL_CURRENT_FORK_STABLE_COMMIT",
      "upstream_sha": "FULL_CURRENT_UPSTREAM_STABLE_COMMIT"
    },
    {
      "branch": "wip",
      "expected_head": "FULL_CURRENT_FORK_WIP_COMMIT",
      "upstream_sha": "FULL_CURRENT_UPSTREAM_WIP_COMMIT"
    }
  ]
}
```

All commit values must be full lowercase 40-character SHA-1s. Request IDs allow only alphanumeric characters, hyphen and underscore, maximum 80 characters. One to four unique whitelisted targets are accepted. Each target may additionally specify `expected_tree` to enforce an independently reviewed final tree, including no-op runs. Other fields are rejected.

## Safety and replay state

- The request is restricted to this repository/control branch. Current target heads, upstream heads and the latest control commit must match the request before work and immediately before remote mutation.
- `state.json` stores each branch's reviewed upstream/source commit, source tree, source fingerprint, original replay commit list, and original-to-replayed metadata/patch mapping. New custom code/CI commits require review and a corresponding replay-list/state update; knowing the new tip SHA is not permission to discard them.
- Only `.github/custom-release/request.json` and `.github/custom-validation/request.json` are excluded from source fingerprints. Intervening commits must modify only those request files. Empty commits, merge commits, history rewrites, reverted-but-unreviewed source changes, and other user changes stop the job.
- Unchanged upstream plus unchanged reviewed source is a true no-op: no source rewrite, backup, tag, release, or state commit. Its audit includes `observed_head`, which may be a permitted request-only descendant of the stored source SHA.
- When upstream changes, each branch starts at its exact reviewed upstream SHA in a separate worktree. Each custom commit is applied with actual `git cherry-pick`, preserving author name/email/date and the **full commit message**. Stable patch IDs and exact author/message metadata are compared. Conflicts, empty/absorbed patches, changed patch IDs, or unexpected trees fail closed; no automatic conflict resolution is performed.
- All requested branches are prepared and audited before any source branch changes. Create-only backup refs are pushed first as an atomic batch. They are named `backup/sync-BRANCH-REQUEST_ID` and are never replaced or deleted.
- Source updates and the per-branch state/control commit are then pushed in **one atomic Git transaction**, with explicit expected-head `--force-with-lease` checks for every source branch **and the control branch**. A concurrent user push or newer request rejects the whole source/state batch. Backups may remain when the later transaction fails; inspect them rather than reusing the request ID.
- Upstream is a separate repository, so it cannot participate in that Git transaction. The guarantee is the exact reviewed upstream SHA, observed current at the final check. A later upstream advance is handled by the next fresh request.
- The `android-sync-audit` artifact is a **candidate plan until the workflow succeeds and remote refs/state are verified**. Failure may occur before or after backup creation. Never treat a pre-push `source_sha`/`backup_branch` entry as proof of publication. After success, read current state and verify every changed target equals its stored source SHA. No-op targets instead must match their `observed_head` and reviewed fingerprint.

A successful sync does not launch the APK workflow. GitHub's built-in token does not recursively trigger other push workflows, and the control route never submits a release request. If an APK build is later authorized, use the separate exact-source release flow after confirming signing setup and source freshness.

## Checks

```bash
python3 -m unittest discover -s .github/custom-sync -p 'test_*.py' -v
python3 -m py_compile .github/custom-sync/*.py
```

Tests use temporary local Git repositories and real cherry-picks/push leases. They do not generate keys or access private signing files. Keep custom source changes, CI changes, and this maintenance-control configuration as distinct commits.
