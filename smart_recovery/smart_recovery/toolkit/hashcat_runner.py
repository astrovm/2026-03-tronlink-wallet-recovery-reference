from __future__ import annotations

import subprocess
from pathlib import Path

from .models import WorkUnit
from .state import StateStore


class HashcatRunner:
    def __init__(self, hash_path: str, mode: str = "15700", hashcat_binary: str = "hashcat"):
        self.hash_path = str(Path(hash_path).resolve())
        self.mode = mode
        self.hashcat_binary = hashcat_binary

    def build_run_command(self, work_unit: WorkUnit) -> list[str]:
        base = [
            self.hashcat_binary,
            "-m",
            self.mode,
            "--self-test-disable",
            "--session",
            self._require(work_unit.session_name, "session_name"),
            "--restore-file-path",
            self._require(work_unit.restore_path, "restore_path"),
            "--status",
            "--status-timer",
            "30",
            "-w",
            "3",
        ]
        if work_unit.attack_mode == "wordlist":
            cmd = base + ["-a", "0", self.hash_path, self._require(work_unit.wordlist_path, "wordlist_path")]
            if work_unit.rule_file:
                cmd += ["-r", work_unit.rule_file]
            return cmd
        if work_unit.attack_mode == "mask":
            return base + work_unit.extra_args + ["-a", "3", self.hash_path, self._require(work_unit.mask, "mask")]
        raise ValueError(f"Unsupported attack mode: {work_unit.attack_mode}")

    def build_restore_command(self, work_unit: WorkUnit) -> list[str]:
        return [
            self.hashcat_binary,
            "--restore",
            "--session",
            self._require(work_unit.session_name, "session_name"),
            "--restore-file-path",
            self._require(work_unit.restore_path, "restore_path"),
        ]

    def check_cracked(self) -> str | None:
        command = [self.hashcat_binary, "-m", self.mode, "--show", self.hash_path]
        result = subprocess.run(command, capture_output=True, text=True, check=False)
        output = result.stdout.strip()
        return output or None

    def execute(
        self,
        work_unit: WorkUnit,
        state: dict[str, object],
        store: StateStore,
        dry_run: bool = False,
    ) -> tuple[str, list[str] | str]:
        restore_path = Path(self._require(work_unit.restore_path, "restore_path"))
        current_status = state["work_units"][work_unit.unit_id]["status"]
        if current_status in {"PAUSED", "RUNNING"} and restore_path.exists():
            command = self.build_restore_command(work_unit)
        else:
            command = self.build_run_command(work_unit)

        if dry_run:
            return "dry-run", command

        cracked = self.check_cracked()
        if cracked:
            store.mark_completed(state, work_unit.unit_id, cracked)
            return "cracked", cracked

        if current_status in {"PAUSED", "RUNNING"}:
            if not restore_path.exists():
                store.mark_failed(state, work_unit.unit_id, f"Missing restore file: {restore_path}")
                return "failed", f"Missing restore file: {restore_path}"

        store.mark_running(
            state,
            work_unit.unit_id,
            session_name=self._require(work_unit.session_name, "session_name"),
            restore_path=str(restore_path),
        )

        try:
            process = subprocess.Popen(command)
            process.wait()
        except KeyboardInterrupt:
            store.mark_paused(state, work_unit.unit_id)
            return "paused", command

        if process.returncode == 0:
            cracked = self.check_cracked() or "CRACKED"
            store.mark_completed(state, work_unit.unit_id, cracked)
            return "cracked", cracked
        if process.returncode == 1:
            store.mark_exhausted(state, work_unit.unit_id)
            return "exhausted", command
        if process.returncode == 2:
            store.mark_paused(state, work_unit.unit_id)
            return "paused", command

        store.mark_failed(state, work_unit.unit_id, f"Hashcat exit code {process.returncode}")
        return "failed", f"Hashcat exit code {process.returncode}"

    @staticmethod
    def _require(value: str | None, field_name: str) -> str:
        if not value:
            raise ValueError(f"{field_name} is required")
        return value
