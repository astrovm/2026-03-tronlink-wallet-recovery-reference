# Smart Recovery

Hashcat orchestration layer for recovery cases where the useful search space is not "all possible passwords" but a ranked set of human-generated candidates plus resumable brute-force shards.

## When to use this

Use `smart_recovery` when you have:

- a hash that can be verified offline
- notes, labels, names, numbers, or other human clues about the password
- a need to pause and resume work without losing state

If you just want to throw a static wordlist or a single mask at Hashcat, you don't need this wrapper.

## How it works

The CLI combines three pieces:

- a **seed catalog** built from operator notes and recovered app artifacts
- a **planner** that ranks candidate families and brute-force shards by priority
- a **Hashcat runner** that keeps session state so work can be paused and resumed

Instead of generating one giant wordlist up front, the planner breaks work into units and materializes each wordlist only when that unit is about to run.

## Seed sources

From the note seed file (`note_seeds.json`):

- `names`, `extensions`, `numbers`, `symbols`, optional `labels`

From the recovered artifact tree:

- wallet labels from `shared_prefs/*.xml`
- `wallet_name_key`, `key_recently_wallet`

All inputs are normalized, fingerprinted, and passed into the family registry.

## Candidate families

Targeted families are tried first, ordered by priority band:

| Family | Example |
| --- | --- |
| `seed.exact-labels` | `carlitosmenem991` |
| `normalize.compact-labels` | `carlitosmenem` |
| `normalize.filtered-labels` | `carlitos`, `menem` |
| `compose.bare-stems` | `Turcosaul`, `MenemCarlos` |
| `compose.name-number` | `Turco7`, `Saul91` |
| `compose.name-number-symbol` | `Turco7!`, `Saul#91` |
| `compose.name-extension-number` | `Turcosaul7` |
| `compose.extension-name-number` | `SaulTurco7` |
| `mutate.toggle-case-stems` | `tURCOSAUL`, `MENEMCARLOS` |
| `mutate.toggle-case-name-ext-number` | `tURCOSAUL7`, `tuRcosaul7` |

The `mutate.*` families use hashcat rule files (`-r`) to try case toggle variations directly on the GPU instead of generating every variant in the wordlist.

If targeted families are exhausted, the planner appends brute-force shards:

- `bruteforce.common.len8` through `bruteforce.common.len16` (charset: `?l?u?d!#$@,.*`)
- `bruteforce.full.len8` through `bruteforce.full.len16`

## Runtime state

State lives under `runtime/`:

- `recovery_state.json` — work-unit metadata, status transitions, cracked result
- `wordlists/` — materialized candidate lists
- `sessions/` — Hashcat session files for pause/resume

## Bundled examples

The CLI defaults point to synthetic examples under [`examples/`](examples/). The repo root has a safe lab bundle (`target.hash`, `note_seeds.json`, `recovery/`) that matches the case write-up.

## Usage

```bash
uv run -m smart_recovery <command> [flags]
```

Commands: `plan`, `status`, `run`, `resume`

Key flags:

| Flag | Purpose |
| --- | --- |
| `--hash-file` | Hashcat-format hash file |
| `--seed-file` | JSON with seed material |
| `--recovery-root` | Path to recovered app data |
| `--max-band` | Stop after this priority band |
| `--dry-run` | Print Hashcat command without executing |
| `--max-work-units` | Limit number of units per run |

### Using the built-in defaults

```bash
uv run -m smart_recovery plan
uv run -m smart_recovery run --dry-run
```

### Using the safe lab bundle

```bash
uv run -m smart_recovery run \
  --hash-file target.hash \
  --seed-file note_seeds.json \
  --recovery-root recovery
```

### Using your own inputs

```bash
uv run -m smart_recovery run \
  --hash-file /path/to/target.hash \
  --seed-file /path/to/note_seeds.json \
  --recovery-root /path/to/recovery_dump
```

## How Hashcat is invoked

- Wordlist attacks: mode `0`, optionally with `-r <rule_file>` for case mutations
- Brute-force shards: mode `3`
- Always sets: `--self-test-disable`, `--session`, `--status`, `--status-timer 30`, `-w 3`
- Checks `hashcat --show` before and after execution to detect already-cracked hashes

Execution stops when a password is cracked, no runnable units remain, or the `--max-work-units` limit is reached.

## Requirements

- `uv` for Python environment management
- `hashcat` in PATH (only needed for `run`/`resume`; `plan` and `status` work without it)
