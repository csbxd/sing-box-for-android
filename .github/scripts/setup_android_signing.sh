#!/usr/bin/env bash
# OWNER-RUN ONLY. Do not run this through an assistant or paste generated secrets into chat.
set -euo pipefail
umask 077
if [[ $# -ne 1 || -e "$1" ]]; then
  echo "Usage: bash $0 /private/backed-up/new-directory (must not exist)" >&2
  exit 1
fi
for tool in keytool openssl base64; do command -v "$tool" >/dev/null; done
mkdir -m 700 -- "$1"
output=$(cd "$1" && pwd)
# Password and key never appear on the terminal or in process arguments.
openssl rand -base64 36 > "$output/keystore-password.txt"
printf '%s' 'custom-android' > "$output/key-alias.txt"
keytool -genkeypair -keystore "$output/release.p12" -storetype PKCS12 \
  -alias custom-android -keyalg RSA -keysize 4096 -validity 10000 \
  -dname 'CN=Custom Android Release' \
  -storepass:file "$output/keystore-password.txt" -keypass:file "$output/keystore-password.txt"
cp "$output/keystore-password.txt" "$output/key-password.txt"
base64 < "$output/release.p12" | tr -d '\n' > "$output/keystore-base64.txt"
keytool -exportcert -keystore "$output/release.p12" -storetype PKCS12 \
  -alias custom-android -storepass:file "$output/keystore-password.txt" > "$output/certificate.der"
openssl dgst -sha256 "$output/certificate.der" | awk '{print $NF}' > "$output/certificate-sha256.txt"
chmod 600 "$output"/*
printf 'Created a new private signing key in %s\nBack up this directory securely. Follow docs/custom-android-release.md to add GitHub Secrets yourself.\n' "$output"
