from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .hashcat_runner import HashcatRunner
from .planner import PLANNER_VERSION, RecoveryPlanner
from .report_patterns import DEFAULT_HISTORICAL_FAMILIES
from .state import StateStore

SMART_RECOVERY_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = SMART_RECOVERY_DIR.parent
EXAMPLES_DIR = SMART_RECOVERY_DIR / "examples"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Smart Hashcat recovery orchestrator")
    parser.add_argument("command", nargs="?", default="run", choices=("run", "resume", "status", "plan"))
    parser.add_argument("--hash-file", default=str(EXAMPLES_DIR / "target.example.hash"))
    parser.add_argument("--state-file", default=str(SMART_RECOVERY_DIR / "runtime" / "recovery_state.json"))
    parser.add_argument("--runtime-dir", default=str(SMART_RECOVERY_DIR / "runtime"))
    parser.add_argument("--seed-file", default=str(EXAMPLES_DIR / "note_seeds.example.json"))
    parser.add_argument("--recovery-root", default=str(EXAMPLES_DIR / "recovery"))
    parser.add_argument("--max-band", type=int, default=None)
    parser.add_argument("--max-candidates-per-family", type=int, default=None)
    parser.add_argument("--mode", default="15700")
    parser.add_argument("--shard-size", type=int, default=1_000_000)
    parser.add_argument("--max-work-units", type=int, default=None)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--skip-report-history", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    hash_path = Path(args.hash_file).expanduser().resolve()
    state_store = StateStore(str(Path(args.state_file).expanduser().resolve()))
    state = state_store.load(str(hash_path))
    if not args.skip_report_history:
        state_store.import_historical_families(state, set(DEFAULT_HISTORICAL_FAMILIES))
        state = state_store.load(str(hash_path))

    planner = RecoveryPlanner(
        str(hash_path),
        str(Path(args.runtime_dir).expanduser().resolve()),
        shard_size=args.shard_size,
        recovery_root=str(Path(args.recovery_root).expanduser().resolve()),
        note_seed_file=str(Path(args.seed_file).expanduser().resolve()),
        max_band=args.max_band,
        max_candidates_per_family=args.max_candidates_per_family,
    )
    state_store.set_planner_context(
        state,
        planner_version=PLANNER_VERSION,
        seed_fingerprint=planner.seed_fingerprint,
    )
    _backfill_work_unit_metadata(state, planner, state_store)
    state = state_store.load(str(hash_path))
    runner = HashcatRunner(str(hash_path), mode=args.mode)

    if args.command == "status":
        _print_status(state, planner)
        return 0
    if args.command == "plan":
        _print_plan(state, planner)
        return 0

    processed_units = 0
    while True:
        state = state_store.load(str(hash_path))
        planned_units = planner.plan(state)
        runnable_units = [unit for unit in planned_units if unit.status not in {"COMPLETED", "EXHAUSTED"}]
        if not runnable_units:
            print("[*] No runnable work units remain.")
            return 0

        work_unit = runnable_units[0]
        state_store.upsert_work_unit(state, work_unit)
        planner.materialize_wordlist(work_unit)
        state = state_store.load(str(hash_path))
        hydrated = planner.plan(state)[0]
        outcome, payload = runner.execute(hydrated, state, state_store, dry_run=args.dry_run)
        processed_units += 1

        if args.dry_run:
            print(" ".join(payload))
            if args.max_work_units is not None and processed_units >= args.max_work_units:
                return 0
            if args.max_work_units is None:
                return 0
            continue

        if outcome == "cracked":
            print(payload)
            return 0
        if outcome == "failed":
            print(payload)
            return 1
        if args.max_work_units is not None and processed_units >= args.max_work_units:
            return 0


def _print_status(state: dict[str, object], planner: RecoveryPlanner) -> None:
    work_units = state.get("work_units", {})
    counts = {}
    band_counts = {}
    for payload in work_units.values():
        counts[payload["status"]] = counts.get(payload["status"], 0) + 1
        band = payload.get("metadata", {}).get("band")
        if band is not None:
            band_counts[band] = band_counts.get(band, 0) + 1
    print("=== Smart Recovery Status ===")
    for status in sorted(counts):
        print(f"{status}: {counts[status]}")
    for band in sorted(band_counts):
        print(f"Band {band}: {band_counts[band]}")
    if state.get("result"):
        print(f"Result: {state['result']['cracked']}")
    print(f"Planner Version: {state.get('planner_version', 0)}")
    if state.get("seed_fingerprint"):
        print(f"Seed Fingerprint: {state['seed_fingerprint'][:12]}")
    print(f"Queued: {len(planner.plan(state))}")


def _print_plan(state: dict[str, object], planner: RecoveryPlanner) -> None:
    print("=== Planned Work Units ===")
    for work_unit in planner.plan(state):
        band = work_unit.metadata.get("band", "?")
        count = work_unit.metadata.get("candidate_count")
        suffix = f" count={count}" if count is not None else ""
        print(f"{work_unit.priority:04d} band={band} {work_unit.unit_id} [{work_unit.status}] {work_unit.description}{suffix}")


def _backfill_work_unit_metadata(
    state: dict[str, object],
    planner: RecoveryPlanner,
    store: StateStore,
) -> None:
    family_registry = getattr(planner, "family_registry", {})
    if not isinstance(family_registry, dict):
        family_registry = {}
    raw_seed_sources = getattr(getattr(planner, "seed_catalog", None), "source_tags", ())
    seed_sources = list(raw_seed_sources) if isinstance(raw_seed_sources, (list, tuple)) else []
    changed = False
    for payload in state.get("work_units", {}).values():
        metadata = payload.setdefault("metadata", {})
        family_id = payload.get("family_id")
        if family_id in family_registry:
            family = family_registry[family_id]
            if metadata.get("band") != family.band:
                metadata["band"] = family.band
                changed = True
            if metadata.get("candidate_count") != family.candidate_count:
                metadata["candidate_count"] = family.candidate_count
                changed = True
            if metadata.get("generator_version") != PLANNER_VERSION:
                metadata["generator_version"] = PLANNER_VERSION
                changed = True
            if metadata.get("seed_sources") != list(family.source_tags):
                metadata["seed_sources"] = list(family.source_tags)
                changed = True
        elif isinstance(family_id, str) and family_id.startswith("bruteforce."):
            band = 9 if ".common." in family_id else 10
            if metadata.get("band") != band:
                metadata["band"] = band
                changed = True
            if metadata.get("generator_version") != PLANNER_VERSION:
                metadata["generator_version"] = PLANNER_VERSION
                changed = True
            if metadata.get("seed_sources") != seed_sources:
                metadata["seed_sources"] = seed_sources
                changed = True
    if changed:
        store.save(state)


if __name__ == "__main__":
    sys.exit(main())
