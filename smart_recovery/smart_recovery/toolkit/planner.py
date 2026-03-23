from __future__ import annotations

import math
from pathlib import Path

from .models import WorkUnit
from .report_patterns import COMMON_CHARSET, build_family_registry, write_wordlist
from .seeds import build_seed_catalog


FINAL_STATUSES = {"COMPLETED", "EXHAUSTED"}
PLANNER_VERSION = 2


class RecoveryPlanner:
    def __init__(
        self,
        hash_path: str,
        runtime_dir: str,
        shard_size: int = 1_000_000,
        recovery_root: str | None = None,
        note_seed_file: str | None = None,
        max_band: int | None = None,
        max_candidates_per_family: int | None = None,
    ):
        self.hash_path = str(Path(hash_path).resolve())
        self.runtime_dir = Path(runtime_dir)
        self.wordlist_dir = self.runtime_dir / "wordlists"
        self.sessions_dir = self.runtime_dir / "sessions"
        self.shard_size = shard_size
        self.recovery_root = str(Path(recovery_root).resolve()) if recovery_root else None
        self.note_seed_file = str(Path(note_seed_file).resolve()) if note_seed_file else None
        self.max_band = max_band
        self.max_candidates_per_family = max_candidates_per_family
        self.wordlist_dir.mkdir(parents=True, exist_ok=True)
        self.sessions_dir.mkdir(parents=True, exist_ok=True)

        self.seed_catalog = build_seed_catalog(self.recovery_root, self.note_seed_file)
        self.seed_fingerprint = self.seed_catalog.fingerprint()
        self.family_registry = build_family_registry(self.seed_catalog)

    def plan(self, state: dict[str, object]) -> list[WorkUnit]:
        planned_units = self._targeted_families(state)

        if self.max_band is None or self.max_band >= 8:
            for length in range(8, 17):
                common_unit = self._build_bruteforce_unit(state, charset_kind="common", length=length, priority=1_000 + length)
                if common_unit is not None:
                    planned_units.append(common_unit)

                full_unit = self._build_bruteforce_unit(state, charset_kind="full", length=length, priority=2_000 + length)
                if full_unit is not None:
                    planned_units.append(full_unit)

        return sorted(planned_units, key=lambda unit: (unit.priority, unit.unit_id))

    def materialize_wordlist(self, work_unit: WorkUnit) -> str | None:
        if work_unit.attack_mode != "wordlist" or not work_unit.wordlist_path:
            return None

        family_spec = self.family_registry.get(work_unit.family_id)
        if family_spec is None:
            return None

        wordlist_path = Path(work_unit.wordlist_path)
        if not wordlist_path.exists():
            write_wordlist(
                family_spec,
                self.seed_catalog,
                str(wordlist_path),
                max_candidates=self.max_candidates_per_family,
            )
        return str(wordlist_path)

    def _targeted_families(self, state: dict[str, object]) -> list[WorkUnit]:
        historical = set(state.get("historical_families", []))
        existing_units = state.get("work_units", {})
        units: list[WorkUnit] = []

        for family_id, family_spec in sorted(self.family_registry.items(), key=lambda item: (item[1].priority, item[0])):
            if self.max_band is not None and family_spec.band > self.max_band:
                continue
            if family_id in historical:
                continue
            if not family_spec.candidate_count:
                continue

            existing = existing_units.get(family_id)
            if existing and existing.get("status") in FINAL_STATUSES:
                continue

            units.append(
                self._hydrate_or_create(
                    existing,
                    WorkUnit(
                        unit_id=family_id,
                        family_id=family_id,
                        priority=family_spec.priority,
                        attack_mode="wordlist",
                        description=family_spec.description,
                        wordlist_path=str(self.wordlist_dir / f"{family_id.replace('.', '_')}.txt"),
                        rule_file=family_spec.rule_file,
                        session_name=f"session_{family_id.replace('.', '_')}",
                        restore_path=str(self.sessions_dir / f"{family_id.replace('.', '_')}.restore"),
                        metadata={
                            "band": family_spec.band,
                            "candidate_count": family_spec.candidate_count,
                            "generator_version": PLANNER_VERSION,
                            "seed_sources": list(family_spec.source_tags),
                        },
                    ),
                )
            )

        return units

    def _build_bruteforce_unit(
        self,
        state: dict[str, object],
        charset_kind: str,
        length: int,
        priority: int,
    ) -> WorkUnit | None:
        family_id = f"bruteforce.{charset_kind}.len{length}"
        family_progress = state.get("family_progress", {}).get(family_id, {})
        shard_index = int(family_progress.get("next_shard", 0))
        keyspace = self._keyspace(charset_kind, length)
        skip = shard_index * self.shard_size
        if skip >= keyspace:
            return None

        limit = min(self.shard_size, keyspace - skip)
        unit_id = f"{family_id}.shard{shard_index}"
        existing = state.get("work_units", {}).get(unit_id)
        if existing and existing.get("status") in FINAL_STATUSES:
            return None

        if charset_kind == "common":
            extra_args = ["-1", COMMON_CHARSET, "--skip", str(skip), "--limit", str(limit)]
            mask = "?1" * length
        else:
            extra_args = ["--skip", str(skip), "--limit", str(limit)]
            mask = "?a" * length

        return self._hydrate_or_create(
            existing,
            WorkUnit(
                unit_id=unit_id,
                family_id=family_id,
                priority=priority,
                attack_mode="mask",
                description=f"{charset_kind.capitalize()} charset bruteforce for length {length}, shard {shard_index}",
                mask=mask,
                session_name=f"session_{unit_id.replace('.', '_')}",
                restore_path=str(self.sessions_dir / f"{unit_id.replace('.', '_')}.restore"),
                extra_args=extra_args,
                metadata={
                    "band": 9 if charset_kind == "common" else 10,
                    "candidate_count": limit,
                    "generator_version": PLANNER_VERSION,
                    "seed_sources": list(self.seed_catalog.source_tags),
                    "sharded": True,
                    "shard_index": shard_index,
                    "shard_size": self.shard_size,
                    "keyspace": str(keyspace),
                },
            ),
        )

    @staticmethod
    def _hydrate_or_create(existing: dict[str, object] | None, fallback: WorkUnit) -> WorkUnit:
        if existing:
            return WorkUnit.from_dict(existing)
        return fallback

    @staticmethod
    def _keyspace(charset_kind: str, length: int) -> int:
        charset_size = 26 + 26 + 10 + 8 if charset_kind == "common" else 256
        return math.prod([charset_size] * length)
