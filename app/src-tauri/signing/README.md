# Android signing keys

## debug.keystore

The **stable debug signing key** for the CI-built sideload APKs.

- PKCS12 keystore, alias `androiddebugkey`, store/key password `android`
  (the exact contract Android Gradle Plugin's debug signing config expects
  at `$HOME/.android/debug.keystore`), RSA-2048, self-signed, 30-year
  validity. Cert SHA-256 fingerprint:
  `3e7ea3b0d3866e6625c35e49cbd6951e677787bfb0f2e9b2f8fc8db2706cd568`.

### Why it is committed

GitHub runners are ephemeral: without this file, every CI run would
generate a *fresh* `~/.android/debug.keystore`, so each APK would be
signed by a different key. Android refuses to update an installed app
whose signature changed — the installer just says "App not installed".
With the keystore in-repo, the android leg copies it to
`$HOME/.android/debug.keystore` before the build, and every APK (local or
CI) carries the same signature, so new builds install over old ones.

### What it is NOT

- **Not** a Play Store upload key (this repo ships sideload-only debug
  APKs for testing).
- **Not** a secret worth protecting in a private repo: it is a
  debug-grade key by definition — anyone who could clone the repo could
  already build their own debug APK with their own key under a different
  package name. If admincraft ever ships Play Store releases, generate a
  real upload key and store it in repo secrets instead.

### Rotating the key

`keytool -genkeypair -keystore debug.keystore -storetype PKCS12
-alias androiddebugkey -keyalg RSA -keysize 2048 -validity 10950
-storepass android -keypass android -dname "CN=Android Debug,O=Android,C=US"`
— then note in the release notes that every user must uninstall the old
build once (signature change) before installing the new one.
