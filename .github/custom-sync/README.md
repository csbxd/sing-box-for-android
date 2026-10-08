# Reviewed Android branch synchronization

This control branch is the direct-GitHub route for the owner's weekly synchronization. It uses GitHub Actions with read-only, job-scoped `GITHUB_TOKEN` permissions for checkout/tests and the owner-managed repository Actions secret `CUSTOM_SYNC_TOKEN` only for the final atomic push. It does not create credentials, use Work/Codex/cloud tasks, sign APKs, or submit release requests.

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
- `state.json` stores each branch's reviewed upstream/source commit, source tree, source fingerprint, original replay commit list, and original-to-replayed metadata/patch mapping. New custom code/CI commits require review and append-only additions to the replay list; the recorded list must remain its exact prefix, and appended commits force replay even when upstream is unchanged. State is updated only by the successful transaction; knowing the new tip SHA is not permission to discard them.
- Only `.github/custom-release/request.json` and `.github/custom-validation/request.json` are excluded from source fingerprints. Intervening commits must modify only those request files. Empty commits, merge commits, history rewrites, reverted-but-unreviewed source changes, and other user changes stop the job.
- Unchanged upstream plus unchanged reviewed source is a true no-op: no source rewrite, backup, tag, release, or state commit. Its audit includes `observed_head`, which may be a permitted request-only descendant of the stored source SHA.
- When upstream changes, each branch starts at its exact reviewed upstream SHA in a separate worktree. Each custom commit is applied with actual `git cherry-pick`, preserving author name/email/date and the **full commit message**. Stable patch IDs and exact author/message metadata are compared. Conflicts, empty/absorbed patches, changed patch IDs, or unexpected trees fail closed; no automatic conflict resolution is performed.
- All requested branches are prepared and audited before any source branch changes. Create-only backup refs join the source/state atomic transaction. They are named `backup/sync-BRANCH-REQUEST_ID` and are never replaced or deleted.
- Backup refs, source updates and the per-branch state/control commit are pushed in **one atomic Git transaction**, with explicit expected-head `--force-with-lease` checks for every source branch **and the control branch**. A concurrent user push or newer request rejects the entire backup/source/state batch. Every backup uses an empty-value create-only lease; an existing backup or concurrent creation rejects the whole batch. The local control HEAD must equal the exact request SHA, and the state commit must have that SHA as its only parent.
- Upstream is a separate repository, so it cannot participate in that Git transaction. The guarantee is the exact reviewed upstream SHA, observed current at the final check. A later upstream advance is handled by the next fresh request.
- The `android-sync-audit` artifact is a **candidate plan until the workflow succeeds and remote refs/state are verified**. Its status is `prepared` until verification completes, then `verified-pushed` or `verified-noop`. Never treat a pre-push `source_sha`/`backup_branch` entry as proof of publication. After success, read current state and verify every changed target equals its stored source SHA and every backup equals its previous head. No-op targets instead must match their `observed_head` and reviewed fingerprint.

CUSTOM_SYNC_TOKEN pushes can trigger downstream workflows. Review each candidate's workflow changes before a live request. Current dev release/validation workflows use request-file triggers and safely skip missing requests, while main/stable/wip have no workflows in the recorded source. The control route never submits a release request. If an APK build is later authorized, use the separate exact-source release flow after confirming signing setup and source freshness.

## Checks

```bash
python3 .github/custom-sync/sync.py --prepare-only  # identical preparation/audit, no state commit or push
python3 -m unittest discover -s .github/custom-sync -p 'test_*.py' -v
python3 -m py_compile .github/custom-sync/*.py
```

Tests use temporary local Git repositories and real cherry-picks/push leases. They do not generate keys or access private signing files. Keep custom source changes, CI changes, and this maintenance-control configuration as distinct commits.

## Authorized local execution on 2026-10-08

The owner authorized the asa local task for synchronization and release. The
committed validation-request.json is an alternate audited input for local
prepare-only and live execution via --request-path. It does not trigger the
Actions synchronization request workflow, preventing duplicate concurrent
execution. Source, backup and control updates retain all exact leases.

## Owner-managed synchronization secret

The owner saves CUSTOM_SYNC_TOKEN in each repository's Actions secrets. The
connector never reads or writes its value. It needs permission to push this
repository, including workflow files; no credentials are generated by this route.

Both checkouts disable persisted credentials. Unit tests and preparation run
without the PAT in child-process environments. The trusted control script removes
the secret from its environment immediately and fails closed when the required
secret is empty. Only the final atomic Git push receives it through an ephemeral,
exact-destination askpass helper, never through a URL, command argument, request,
Git config, audit artifact or persisted credential file. The helper is deleted
after the push. Existing exact leases and all source/metadata/patch/tree checks
remain mandatory. Only audited control code runs in the credentialed step; never
build or execute candidate source there.

A fresh all-target no-op request verifies secret presence and synchronization
guards without changing source/state/backups or publishing a release. It does
not exercise authenticated push permissions, prove token scopes/expiry, or prove
revocation of any previously exposed token. Missing or invalid credentials must
never cause fallback to GITHUB_TOKEN or removal of atomic/lease safeguards.
