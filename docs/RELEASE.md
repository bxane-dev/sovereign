# Release process

The `v8.*` tag workflow builds Windows NSIS, macOS DMG/ZIP, and Linux AppImage/DEB packages from `uv.lock` and `pnpm-lock.yaml`. It runs tests and a packaged-core startup check on each operating system. The final job uploads installers, update metadata, and SHA-256 checksums to a **draft** GitHub Release. Publish the draft only after installing and testing each package on a target machine.

## Signing secrets

Configure these GitHub Actions repository secrets before pushing a release tag:

| Platform | Secrets |
| --- | --- |
| Windows | `WIN_CSC_LINK` (base64 PFX or certificate URL), `WIN_CSC_KEY_PASSWORD` |
| macOS | `MAC_CSC_LINK` (Developer ID Application P12), `MAC_CSC_KEY_PASSWORD`, `APPLE_ID`, `APPLE_APP_SPECIFIC_PASSWORD`, `APPLE_TEAM_ID` |

The release workflow fails if signing credentials are absent. macOS builds enable hardened runtime and notarization. Never commit certificates, passwords, or API keys. The Linux AppImage and DEB are distributed with checksums; the workflow does not apply a separate Linux package signature.

## Release checklist

1. Confirm `python scripts/verify_version.py v8.0.0` and all CI jobs pass on the release commit.
2. Configure signing secrets, then push the reviewed `v8.0.0` tag. This starts the signed build and creates a draft release.
3. Download the draft artifacts. Verify Windows Authenticode, macOS `codesign` and notarization, package installation, core startup, provider configuration, session resume, permission gates, and a live visual task on each desktop platform.
4. Publish the draft GitHub Release. The app checks that release for updates and asks the user before installation.

Windows NSIS, macOS ZIP, and Linux AppImage are the auto-update targets. The DEB is provided for package-manager installs and is updated through the package manager. Development and preview builds may be unsigned; do not publish them as production releases.

## Local preview build

Use `python scripts/build_core.py`, `python scripts/smoke_core.py`, `python scripts/build_terminal.py`, and `pnpm --filter @sovereign/desktop run dist`. Preview artifacts appear in `apps/desktop/dist/`. They do not satisfy the production signing gate.
