# Optional owner-run signing setup helper

This is an optional handoff for **you to review and run yourself on your trusted
computer**. It has not been executed by the assistant or CI. It generates a brand
new key locally; it does not reuse or retrieve a cloud-generated key. Do not use it
if a release key already exists or an app has already shipped with another key.
Never send the key directory, backups or passwords in chat or commit them.

The script is `.github/scripts/owner_setup_android_signing.sh`. Read it and the
existing `.github/scripts/setup_android_signing.sh` before running. Requirements:
Bash, JDK/keytool, OpenSSL, base64 and the official GitHub CLI already authenticated
as `csbxd`. You must handle login or missing permissions yourself; the script does
not log in, mint a token, expand permissions or trigger any workflow.

From your local repository checkout, choose two new private directories outside it.
Their parent directories must already exist. For example, after reviewing the code:

```bash
bash .github/scripts/owner_setup_android_signing.sh \
  "$HOME/android-signing" "$HOME/android-signing-backup"
```

It verifies the account and exact target repository, refuses existing signing
Secrets/certificate settings, and displays what will happen. Type `YES` only if you
want this new permanent key. It generates a PKCS12 bundle, retains a byte-verified
private backup with restricted filesystem permissions, then waits again.

Type `UPLOAD` only if you personally authorize transmitting the keystore and signing
values to `csbxd/sing-box-for-android` GitHub Actions Secrets. Four values travel from
local files via standard input; no passwords/private keys are placed in command
arguments or printed. The public certificate fingerprint goes into the repository
Actions variable. Repository and account checks are repeated before upload.

The helper stops on errors. Uploading multiple values is not atomic: if it fails
partway, retain **the same key and backup**, inspect repository settings yourself,
and complete the remaining values using the manual instructions in
[custom Android release setup](custom-android-release.md). It refuses to rerun over
existing directories/settings rather than accidentally generating a second signer.

The retained local backup is not protection against loss of your computer. Secure
an encrypted/offline copy yourself before depending on the key for released apps.
No APK is built or published by this helper. New signing keys cannot update an
existing installation signed by someone else; back up app profiles before any
uninstall. Future custom APK updates must reuse the same key.

CLI behavior references: [gh secret set](https://cli.github.com/manual/gh_secret_set)
and [gh variable set](https://cli.github.com/manual/gh_variable_set) both support
reading values from standard input when no --body argument is supplied.
