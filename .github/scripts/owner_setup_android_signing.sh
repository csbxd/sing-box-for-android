#!/usr/bin/env bash
# OWNER-RUN ONLY: review, then run yourself on a trusted local computer.
# Assistants/CI must never execute this generation/upload helper.
set +x
set -euo pipefail
umask 077
unset GH_DEBUG GH_FORCE_TTY
export GH_HOST=github.com
readonly repo='github.com/csbxd/sing-box-for-android'
readonly owner='csbxd'
script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
repo_dir=$(cd -- "$script_dir/../.." && pwd -P)
fail() { printf '%s\n' "$*" >&2; exit 1; }
[[ $# -eq 2 ]] || fail "Usage: bash $0 NEW_PRIVATE_KEY_DIRECTORY NEW_PRIVATE_BACKUP_DIRECTORY"
[[ -t 0 && -t 1 ]] || fail 'Run interactively yourself in a local terminal; no automation or redirected input.'
[[ -z "${CI:-}" && -z "${GITHUB_ACTIONS:-}" ]] || fail 'Refusing to run in CI.'
for command in gh keytool openssl base64 git cmp; do
  command -v "$command" >/dev/null || fail "Missing required command: $command"
done
[[ -f "$script_dir/setup_android_signing.sh" ]] || fail 'Missing reviewed key-generation script.'
# Parents must already exist. Resolve them physically; do not create keys in checkout.
key_parent=$(cd -- "$(dirname -- "$1")" && pwd -P)
backup_parent=$(cd -- "$(dirname -- "$2")" && pwd -P)
key_dir="$key_parent/$(basename -- "$1")"
backup_dir="$backup_parent/$(basename -- "$2")"
for directory in "$key_dir" "$backup_dir"; do
  [[ ! -e "$directory" && ! -L "$directory" ]] || fail 'Both destination directories must be new; nothing will be overwritten.'
  case "$directory/" in "$repo_dir/"*) fail 'Keep keys and backups outside the repository checkout.' ;; esac
done
[[ "$key_dir" != "$backup_dir" ]] || fail 'Use different key and backup directories.'
login=$(gh api --hostname github.com user --jq '.login')
[[ "$login" == "$owner" ]] || fail "Existing gh login must be $owner. Sign in/select it yourself, then retry; this script never changes authentication."
identity=$(gh repo view "$repo" --json nameWithOwner,viewerPermission --jq '.nameWithOwner + " " + .viewerPermission')
[[ "$identity" == 'csbxd/sing-box-for-android ADMIN' ]] || fail 'Repository identity/admin permission check failed.'
# Refuse accidental replacement of any existing signing setup.
check_empty_remote_signing() {
  secrets=$(gh secret list --repo "$repo" --app actions --json name --jq '.[].name')
  variables=$(gh variable list --repo "$repo" --json name --jq '.[].name')
  for name in ANDROID_KEYSTORE_BASE64 ANDROID_KEYSTORE_PASSWORD ANDROID_KEY_ALIAS ANDROID_KEY_PASSWORD; do
    if grep -Fxq "$name" <<< "$secrets"; then fail "Signing secret $name already exists; inspect existing setup yourself instead of replacing it."; fi
  done
  if grep -Fxq ANDROID_SIGNING_CERT_SHA256 <<< "$variables"; then fail 'A signer certificate is already configured; do not replace it with a new key.'; fi
}
check_empty_remote_signing
printf '\nGitHub account: %s\nRepository: %s\n' "$login" "$repo"
printf 'This creates a NEW permanent signing key locally and a private backup.\nKey directory: %s\nBackup directory: %s\n' "$key_dir" "$backup_dir"
printf 'It will send the encrypted keystore and three signing values to GitHub Actions Secrets, plus the public certificate fingerprint to an Actions variable.\n'
printf 'No APK will be published or workflow started. No token will be created or permissions expanded.\n'
printf 'Type YES to generate this new key and prepare its backup: '
IFS= read -r answer
[[ "$answer" == YES ]] || fail 'Cancelled; no key or remote setting changed.'
bash "$script_dir/setup_android_signing.sh" "$key_dir"
mkdir -m 700 -- "$backup_dir"
cp -p -- "$key_dir"/* "$backup_dir/"
chmod 600 -- "$backup_dir"/*
for file in release.p12 keystore-base64.txt keystore-password.txt key-alias.txt key-password.txt certificate.der certificate-sha256.txt; do
  [[ -s "$key_dir/$file" ]] || fail 'Generated key bundle is incomplete; keep the private directory and inspect locally.'
  cmp -s -- "$key_dir/$file" "$backup_dir/$file" || fail 'Backup verification failed; nothing uploaded.'
done
printf '\nPrivate key and backup retained locally. Protect the backup; losing this key prevents updates.\n'
printf 'Type UPLOAD to personally authorize uploading these four Secrets and the certificate variable to %s: ' "$repo"
IFS= read -r answer
[[ "$answer" == UPLOAD ]] || fail 'Upload cancelled. Your private key and backup remain locally; nothing uploaded.'
[[ $(gh api --hostname github.com user --jq '.login') == "$owner" ]] || fail 'GitHub account changed; nothing uploaded.'
check_empty_remote_signing
# Values travel via stdin, never shell arguments, variables, stdout, or command logs.
# Upload is not atomic: on error, keep this same key and finish setup manually.
trap 'printf "Setup stopped. Keep the SAME local key and backup; some values may already be uploaded. Finish/review them manually, do not generate a replacement.\n" >&2' ERR
gh secret set ANDROID_KEYSTORE_BASE64 --app actions --repo "$repo" < "$key_dir/keystore-base64.txt" >/dev/null
gh secret set ANDROID_KEYSTORE_PASSWORD --app actions --repo "$repo" < "$key_dir/keystore-password.txt" >/dev/null
gh secret set ANDROID_KEY_ALIAS --app actions --repo "$repo" < "$key_dir/key-alias.txt" >/dev/null
gh secret set ANDROID_KEY_PASSWORD --app actions --repo "$repo" < "$key_dir/key-password.txt" >/dev/null
gh variable set ANDROID_SIGNING_CERT_SHA256 --repo "$repo" < "$key_dir/certificate-sha256.txt" >/dev/null
trap - ERR
printf 'Owner signing setup uploaded. Local key and backup retained. No build or release was triggered.\n'
