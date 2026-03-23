from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class WorkUnit:
    unit_id: str
    family_id: str
    priority: int
    attack_mode: str
    description: str
    status: str = "READY"
    wordlist_path: str | None = None
    mask: str | None = None
    rule_file: str | None = None
    session_name: str | None = None
    restore_path: str | None = None
    extra_args: list[str] = field(default_factory=list)
    metadata: dict[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {
            "unit_id": self.unit_id,
            "family_id": self.family_id,
            "priority": self.priority,
            "attack_mode": self.attack_mode,
            "description": self.description,
            "status": self.status,
            "wordlist_path": self.wordlist_path,
            "mask": self.mask,
            "rule_file": self.rule_file,
            "session_name": self.session_name,
            "restore_path": self.restore_path,
            "extra_args": list(self.extra_args),
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, object]) -> "WorkUnit":
        return cls(
            unit_id=str(payload["unit_id"]),
            family_id=str(payload["family_id"]),
            priority=int(payload["priority"]),
            attack_mode=str(payload["attack_mode"]),
            description=str(payload["description"]),
            status=str(payload.get("status", "READY")),
            wordlist_path=payload.get("wordlist_path") or None,
            mask=payload.get("mask") or None,
            rule_file=payload.get("rule_file") or None,
            session_name=payload.get("session_name") or None,
            restore_path=payload.get("restore_path") or None,
            extra_args=list(payload.get("extra_args", [])),
            metadata=dict(payload.get("metadata", {})),
        )
