from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .models import WorkUnit


FINAL_STATUSES = {"COMPLETED", "EXHAUSTED"}
STATE_VERSION = 3


class StateStore:
    def __init__(self, state_path: str):
        self.state_path = Path(state_path)

    def load(self, hash_path: str) -> dict[str, object]:
        if not self.state_path.exists():
            state = self._new_state(hash_path)
            self.save(state)
            return state

        with self.state_path.open("r", encoding="utf-8") as handle:
            raw_state = json.load(handle)

        if raw_state.get("version") == STATE_VERSION:
            return raw_state

        migrated = self._migrate_state(raw_state, hash_path)
        self.save(migrated)
        return migrated

    def save(self, state: dict[str, object]) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self.state_path.with_suffix(self.state_path.suffix + ".tmp")
        with tmp_path.open("w", encoding="utf-8") as handle:
            json.dump(state, handle, indent=2, sort_keys=True)
        tmp_path.replace(self.state_path)

    def import_historical_families(self, state: dict[str, object], family_ids: set[str]) -> None:
        historical = set(state.get("historical_families", []))
        historical.update(family_ids)
        state["historical_families"] = sorted(historical)
        self.save(state)

    def upsert_work_unit(self, state: dict[str, object], work_unit: WorkUnit) -> None:
        work_units = state.setdefault("work_units", {})
        existing = work_units.get(work_unit.unit_id)
        payload = work_unit.to_dict()
        if existing:
            payload["status"] = existing.get("status", payload["status"])
            payload["session_name"] = existing.get("session_name", payload["session_name"])
            payload["restore_path"] = existing.get("restore_path", payload["restore_path"])
        work_units[work_unit.unit_id] = payload
        self.save(state)

    def mark_running(
        self,
        state: dict[str, object],
        unit_id: str,
        session_name: str,
        restore_path: str,
    ) -> None:
        work_unit = state["work_units"][unit_id]
        work_unit["status"] = "RUNNING"
        work_unit["session_name"] = session_name
        work_unit["restore_path"] = restore_path
        self.save(state)

    def mark_paused(self, state: dict[str, object], unit_id: str) -> None:
        state["work_units"][unit_id]["status"] = "PAUSED"
        self.save(state)

    def mark_exhausted(self, state: dict[str, object], unit_id: str) -> None:
        work_unit = state["work_units"][unit_id]
        work_unit["status"] = "EXHAUSTED"
        metadata = work_unit.get("metadata", {})
        if metadata.get("sharded"):
            family_id = work_unit["family_id"]
            family_progress = state.setdefault("family_progress", {})
            family_progress[family_id] = {
                "next_shard": int(metadata["shard_index"]) + 1,
            }
        self.save(state)

    def mark_completed(self, state: dict[str, object], unit_id: str, cracked_value: str) -> None:
        state["work_units"][unit_id]["status"] = "COMPLETED"
        state["result"] = {"unit_id": unit_id, "cracked": cracked_value}
        self.save(state)

    def mark_failed(self, state: dict[str, object], unit_id: str, message: str) -> None:
        state["work_units"][unit_id]["status"] = "FAILED"
        state["work_units"][unit_id]["metadata"]["failure"] = message
        self.save(state)

    def _new_state(self, hash_path: str) -> dict[str, object]:
        return {
            "version": STATE_VERSION,
            "target_hash_path": str(Path(hash_path).resolve()),
            "target_hash_fingerprint": self._fingerprint(hash_path),
            "planner_version": 0,
            "seed_fingerprint": "",
            "historical_families": [],
            "family_progress": {},
            "work_units": {},
            "result": None,
        }

    def _migrate_state(self, raw_state: dict[str, object], hash_path: str) -> dict[str, object]:
        if raw_state.get("version") == 2:
            migrated = dict(raw_state)
            migrated["version"] = STATE_VERSION
            migrated.setdefault("planner_version", 0)
            migrated.setdefault("seed_fingerprint", "")
            return migrated

        migrated = self._new_state(hash_path)
        for task_id, task_state in raw_state.get("tasks", {}).items():
            session_name = task_state.get("session")
            status = str(task_state.get("status", "PENDING"))
            mapped_status = "PAUSED" if status == "IN_PROGRESS" else status
            unit = WorkUnit(
                unit_id=f"legacy.{task_id}",
                family_id=f"legacy.{task_id}",
                priority=99999,
                attack_mode="unknown",
                description=f"Migrated legacy task {task_id}",
                status=mapped_status,
                session_name=session_name,
            )
            migrated["work_units"][unit.unit_id] = unit.to_dict()
        return migrated

    def set_planner_context(
        self,
        state: dict[str, object],
        planner_version: int,
        seed_fingerprint: str,
    ) -> None:
        state["planner_version"] = planner_version
        state["seed_fingerprint"] = seed_fingerprint
        self.save(state)

    @staticmethod
    def _fingerprint(hash_path: str) -> str:
        payload = Path(hash_path).read_bytes()
        return hashlib.sha256(payload).hexdigest()
