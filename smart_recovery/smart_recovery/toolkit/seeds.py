from __future__ import annotations

import hashlib
import html
import json
import re
from dataclasses import dataclass
from pathlib import Path


WORD_RE = re.compile(r"[a-z]+", re.IGNORECASE)
NUMBER_RE = re.compile(r"\d+")
SYMBOL_RE = re.compile(r"[^A-Za-z0-9\s]")
STRING_TAG_RE = re.compile(r'<string name="([^"]+)">(.*?)</string>', re.DOTALL)
STOPWORDS = {"usuario", "clave", "wallet", "sample", "example"}
NAME_CANDIDATES: set[str] = set()
EXTENSION_CANDIDATES: set[str] = set()
DEFAULT_NUMBER_CANDIDATES: set[str] = set()
DEFAULT_SYMBOLS = ("!", "#", "$", "@", ",", ".", "*")


@dataclass(frozen=True)
class SeedCatalog:
    names: tuple[str, ...]
    extensions: tuple[str, ...]
    labels: tuple[str, ...]
    numbers: tuple[str, ...]
    symbols: tuple[str, ...]
    source_tags: tuple[str, ...]

    def fingerprint(self) -> str:
        payload = json.dumps(
            {
                "extensions": self.extensions,
                "labels": self.labels,
                "names": self.names,
                "numbers": self.numbers,
                "source_tags": self.source_tags,
                "symbols": self.symbols,
            },
            sort_keys=True,
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def load_note_seed_payload(note_seed_file: str | None) -> dict[str, object]:
    if not note_seed_file:
        return {}

    path = Path(note_seed_file)
    if not path.exists():
        return {}

    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)

    return payload if isinstance(payload, dict) else {}


def build_seed_catalog(recovery_root: str | None, note_seed_file: str | None = None) -> SeedCatalog:
    names = set(NAME_CANDIDATES)
    extensions = set(EXTENSION_CANDIDATES)
    labels: set[str] = set()
    numbers = set(DEFAULT_NUMBER_CANDIDATES)
    symbols = set(DEFAULT_SYMBOLS)
    source_tags = {"defaults"}

    for label in _extract_artifact_labels(recovery_root):
        labels.add(label)
        source_tags.add("artifact:label")

    note_payload = load_note_seed_payload(note_seed_file)
    for key, values in note_payload.items():
        if not isinstance(values, list):
            continue
        cleaned_values = [str(value).strip() for value in values if str(value).strip()]
        if key == "labels":
            labels.update(_normalize_label(value) for value in cleaned_values)
            source_tags.add("note:labels")
        elif key == "names":
            names.update(_normalize_word(value) for value in cleaned_values)
            source_tags.add("note:names")
        elif key == "extensions":
            extensions.update(_normalize_word(value) for value in cleaned_values)
            source_tags.add("note:extensions")
        elif key == "numbers":
            numbers.update(value.strip() for value in cleaned_values if value.strip())
            source_tags.add("note:numbers")
        elif key == "symbols":
            symbols.update(value for value in cleaned_values if value)
            source_tags.add("note:symbols")

    for label in list(labels):
        words = [_normalize_word(word) for word in WORD_RE.findall(label)]
        filtered_words = [word for word in words if word not in STOPWORDS]
        for index, normalized in enumerate(filtered_words):
            names.add(normalized)
            if index > 0:
                extensions.add(normalized)

        for word in WORD_RE.findall(label):
            normalized = _normalize_word(word)
            if normalized in STOPWORDS:
                continue
        for number in NUMBER_RE.findall(label):
            numbers.add(number)

        for symbol in SYMBOL_RE.findall(label):
            symbols.add(symbol)

    names = {name for name in names if name and name not in STOPWORDS}
    extensions = {extension for extension in extensions if extension and extension not in STOPWORDS}
    labels = {label for label in labels if label}
    numbers = {number for number in numbers if number}
    symbols = {symbol for symbol in symbols if symbol}

    return SeedCatalog(
        names=tuple(sorted(names)),
        extensions=tuple(sorted(extensions)),
        labels=tuple(sorted(labels)),
        numbers=tuple(sorted(numbers, key=_number_sort_key)),
        symbols=tuple(sorted(symbols)),
        source_tags=tuple(sorted(source_tags)),
    )


def _extract_artifact_labels(recovery_root: str | None) -> set[str]:
    if not recovery_root:
        return set()

    shared_prefs_dir = Path(recovery_root) / "shared_prefs"
    if not shared_prefs_dir.exists():
        return set()

    labels: set[str] = set()
    for file_path in shared_prefs_dir.glob("*.xml"):
        try:
            payload = file_path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue

        for name, value in STRING_TAG_RE.findall(payload):
            decoded = html.unescape(value).strip()
            if not decoded:
                continue
            if name == "wallet_name_key":
                labels.add(_normalize_label(decoded))
            elif name == "key_recently_wallet":
                for item in _parse_recent_wallets(decoded):
                    labels.add(_normalize_label(item))

    return labels


def _parse_recent_wallets(value: str) -> list[str]:
    try:
        payload = json.loads(value)
    except json.JSONDecodeError:
        return []

    if not isinstance(payload, list):
        return []

    return [str(item) for item in payload if str(item).strip()]


def _normalize_label(value: str) -> str:
    normalized = " ".join(value.strip().split()).lower()
    return normalized


def _normalize_word(value: str) -> str:
    return value.strip().lower()


def _number_sort_key(value: str) -> tuple[int, str]:
    try:
        return (int(value), value)
    except ValueError:
        return (10**9, value)
