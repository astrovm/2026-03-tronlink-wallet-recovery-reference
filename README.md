# TronLink Wallet Recovery Reference

Reference material for a TronLink wallet recovery workflow on Android.

The workflow covers two connected problems:

1. Acquiring a target app's private data from a non-rooted but vulnerable Android device
2. Recovering the password and reconstructing the mnemonic offline from encrypted wallet material

> [!IMPORTANT]
> The repository includes a safe, publishable lab example under [`recovery/`](recovery/), plus [`target.hash`](target.hash) and [`note_seeds.json`](note_seeds.json). These files are intentionally synthetic and are not a private dump from a third-party device.

## Documentation

| File | Purpose |
| --- | --- |
| [`tronlink_wallet_recovery_case.md`](tronlink_wallet_recovery_case.md) | Full narrative write-up with decisions, commands, and outputs |
| [`step_by_step.md`](step_by_step.md) | Minimal command-by-command replication guide |
| [`smart_recovery/README.md`](smart_recovery/README.md) | Offline password recovery orchestration |
| [`zygote-injection-toolkit/README.md`](zygote-injection-toolkit/README.md) | Lower-level Zygote injection details |

## Repository layout

```text
.
├── tronlink_wallet_recovery_case.md   # main case write-up
├── step_by_step.md                    # compact replication guide
├── repro.py                           # app-targeted Zygote acquisition helper
├── target.hash                        # Hashcat-ready keystore hash (safe example)
├── note_seeds.json                    # seed material for password families
├── recovery/                          # safe lab dump used throughout the docs
├── tools/
│   ├── extract_hash.py                # keystore → Hashcat format
│   └── decrypt_mnemonic.py            # password + keystore → seed phrase
├── smart_recovery/                    # Hashcat orchestration layer
└── zygote-injection-toolkit/          # lower-level Android acquisition toolkit
```

## How it works

On the Android side, the hard part is not getting a shell — it's getting a process that Android treats as the target app, with access to its private storage. A higher-privilege shell alone is often not enough because SELinux and mount namespaces block access to `/data/data/<package>`.

On the offline side, the hard part is not running Hashcat forever. The useful path is to extract encrypted material into a verifiable offline format, spend the first search budget on human-generated password families, and widen into brute force only after those are exhausted.

## End-to-end workflow

1. Identify the target app UID on a vulnerable device
2. Launch a listener in the target app's context using the Zygote injection path
3. Stream the app's private data to the host
4. Extract the TronLink keystore into a Hashcat-verifiable hash
5. Generate ranked candidate families from notes and recovered labels
6. Crack the password offline
7. Decrypt the mnemonic blob with the recovered password

## Quick start

```bash
uv sync
```

> [!WARNING]
> The Android acquisition phase modifies system settings that persist across reboots. If the exploit fails under certain conditions, the device may enter a **boot loop**. The exploit code includes cleanup logic, but see the troubleshooting section in [`step_by_step.md`](step_by_step.md) if this occurs.

The offline phase can be reproduced directly with the bundled files, no Android device needed:

```bash
# Extract keystore hash
uv run tools/extract_hash.py recovery/shared_prefs/carlitosmenem991.xml > target.hash

# Run targeted password recovery
uv run -m smart_recovery run \
  --hash-file target.hash \
  --seed-file note_seeds.json \
  --recovery-root recovery

# Decrypt the mnemonic with the recovered password
uv run tools/decrypt_mnemonic.py \
  recovery/shared_prefs/carlitosmenem991.xml \
  Turcosaul7
```

## Disclaimers

- This is not a universal Android exploitation framework
- This is not a turnkey extractor for every device or app version
- This is not a replacement for proper forensic handling
- Password recovery is not feasible without a defensible hypothesis about the target password pattern

This repository is published for research, lab validation, and authorized recovery work. It is not intended for unauthorized access to third-party devices, accounts, or data.

## References

- [Android Security Bulletin, June 2024](https://source.android.com/docs/security/bulletin/2024-06-01)
- [CVE-2024-31317](https://nvd.nist.gov/vuln/detail/CVE-2024-31317)
- [AOSP patch](https://android.googlesource.com/platform/frameworks/base/+/e25a0e394bbfd6143a557e1019bb7ad992d11985)
