# Zygote Injection Toolkit

Experimental Python CLI for running a Zygote injection on vulnerable Android devices and exposing a shell for controlled data acquisition.

Within this repository, the repo-specific helper is [`../repro.py`](../repro.py), which wraps the app-targeted flow used in the documented recovery path. Use this toolkit directly when you need lower-level control over the injection.

## Why app-targeted injection matters

A plain `system` shell may still be blocked from another app's private data due to SELinux and mount namespaces. An app-targeted launch inherits the UID, data directory, and runtime context needed to access that app's storage.

That's why the toolkit supports both generic system-targeted runs and app-targeted runs.

## What it does

1. Checks device compatibility
2. Delivers the payload via `hidden_api_blacklist_exemptions`
3. Waits for a netcat listener on port `1234`
4. Forwards `tcp:1234` from device to host
5. Reports success and leaves a shell ready for acquisition commands

Diagnostics printed during execution: delivery mode (`old`/`new`), netcat path, security patch level, build fingerprint, listener status.

## Requirements

- `uv` for Python environment management
- `adb` installed and in PATH
- USB debugging enabled on the target device
- Device with security patch before June 1, 2024 (Android 9–14)

## Setup

```bash
uv sync
```

## Usage

### System-targeted (default)

```bash
uv run -m zygote_injection_toolkit
```

Defaults: `--uid 1000`, `--gid 1000`, `--groups 3003`

### App-targeted

First, find the app UID:

```bash
adb shell pm dump com.package.name | grep userId
```

Then run with app-specific context:

```bash
uv run -m zygote_injection_toolkit \
  --uid 10145 \
  --gid 10145 \
  --package-name com.package.name \
  --app-data-dir /data/user/0/com.package.name \
  --target-sdk-version 30 \
  --is-top-app
```

## CLI flags

| Flag | Default | Purpose |
| --- | --- | --- |
| `--serial` | auto | Device serial |
| `--uid` | `1000` | Target UID |
| `--gid` | `1000` | Target GID |
| `--groups` | `3003` | Supplementary groups |
| `--seinfo` | `platform:isSystemServer:system_app:targetSdkVersion=29:complete` | SELinux label |
| `--app-data-dir` | — | Target app data directory |
| `--package-name` | — | Target package name |
| `--nice-name` | `runmenetcat` | Process name |
| `--target-sdk-version` | — | Target SDK version |
| `--is-top-app` | off | Mark as foreground app |

> [!WARNING]
> Do not pass comma-delimited values to `--groups` (e.g. `3003,1015`). The delivery path can split them incorrectly before they reach Zygote. Pass a single value.

## What success looks like

```text
Stage 1 success!
```

At that point you have a forwarded listener on `127.0.0.1:1234` with a shell running under the target identity.

## What this is not

- Not a general-purpose root tool or Magisk replacement
- Does not guarantee access on patched devices
- Does not bypass every storage boundary on every Android version
- Not needed if the device is already rooted

## Related docs

- Full write-up: [`../tronlink_wallet_recovery_case.md`](../tronlink_wallet_recovery_case.md)
- Step-by-step guide: [`../step_by_step.md`](../step_by_step.md)
- Repo-specific wrapper: [`../repro.py`](../repro.py)
