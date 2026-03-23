from __future__ import annotations

from dataclasses import dataclass, field
from itertools import product
from pathlib import Path
import re

from .seeds import SeedCatalog


COMMON_CHARSET = "?l?u?d!#$@,.*"
RULES_DIR = Path(__file__).resolve().parents[1] / "runtime" / "rules"
DEFAULT_HISTORICAL_FAMILIES = {
    "report.legacy-seeded-families",
    "report.legacy-structured-ranges",
    "report.legacy-permuted-labels",
    "report.legacy-word-pair-number-symbol",
}
TOP_SYMBOLS = ("!", "#", ".", "@", "*")
WORD_RE = re.compile(r"[a-z]+", re.IGNORECASE)


@dataclass
class FamilySpec:
    family_id: str
    priority: int
    band: int
    description: str
    generator: callable
    candidate_count: int | None = None
    source_tags: tuple[str, ...] = field(default_factory=tuple)
    rule_file: str | None = None


def build_family_registry(catalog: SeedCatalog) -> dict[str, FamilySpec]:
    registry = {
        "seed.exact-labels": FamilySpec(
            family_id="seed.exact-labels",
            priority=10,
            band=1,
            description="Exact labels and note-derived literals",
            generator=_iter_exact_labels,
        ),
        "normalize.compact-labels": FamilySpec(
            family_id="normalize.compact-labels",
            priority=20,
            band=2,
            description="Compact labels with spaces removed",
            generator=_iter_compact_labels,
        ),
        "normalize.filtered-labels": FamilySpec(
            family_id="normalize.filtered-labels",
            priority=25,
            band=2,
            description="Compact labels with boilerplate words removed",
            generator=_iter_filtered_labels,
        ),
        "compose.bare-stems": FamilySpec(
            family_id="compose.bare-stems",
            priority=30,
            band=3,
            description="Bare stems from names, extensions, and labels",
            generator=_iter_bare_stems,
        ),
        "report.wallet-identities": FamilySpec(
            family_id="report.wallet-identities",
            priority=40,
            band=3,
            description="Wallet identity variations",
            generator=_iter_wallet_identity_candidates,
        ),
        "compose.name-number": FamilySpec(
            family_id="compose.name-number",
            priority=50,
            band=4,
            description="Observed names paired with observed numbers",
            generator=_iter_name_number_candidates,
        ),
        "compose.name-extension-number": FamilySpec(
            family_id="compose.name-extension-number",
            priority=55,
            band=4,
            description="Name + extension + observed number families",
            generator=_iter_name_extension_number_candidates,
        ),
        "compose.name-number-symbol": FamilySpec(
            family_id="compose.name-number-symbol",
            priority=60,
            band=5,
            description="Observed names paired with observed numbers and symbols",
            generator=_iter_name_number_symbol_candidates,
        ),
        "compose.extension-name-number": FamilySpec(
            family_id="compose.extension-name-number",
            priority=65,
            band=5,
            description="Extension + name + observed number families",
            generator=_iter_extension_name_number_candidates,
        ),
        "compose.name-number-extension": FamilySpec(
            family_id="compose.name-number-extension",
            priority=70,
            band=5,
            description="Name + observed number + extension families",
            generator=_iter_name_number_extension_candidates,
        ),
        "report.extension-first": FamilySpec(
            family_id="report.extension-first",
            priority=80,
            band=5,
            description="Extension-first patterns",
            generator=_iter_extension_first_candidates,
        ),
        "report.split-number-patterns": FamilySpec(
            family_id="report.split-number-patterns",
            priority=90,
            band=6,
            description="Split-number patterns",
            generator=_iter_split_number_candidates,
        ),
        "symbols.double-around-stems": FamilySpec(
            family_id="symbols.double-around-stems",
            priority=100,
            band=6,
            description="Two-symbol variants around high-confidence stems",
            generator=_iter_double_symbol_stems,
        ),
        "report.two-symbol-variants": FamilySpec(
            family_id="report.two-symbol-variants",
            priority=110,
            band=6,
            description="Legacy two-symbol targeted variants",
            generator=_iter_two_symbol_candidates,
        ),
        "normalize.spaced-labels": FamilySpec(
            family_id="normalize.spaced-labels",
            priority=120,
            band=7,
            description="Late spaced label variants",
            generator=_iter_spaced_labels,
        ),
        "report.high-range-name-number-symbol": FamilySpec(
            family_id="report.high-range-name-number-symbol",
            priority=200,
            band=8,
            description="High-range name-number-symbol candidates",
            generator=_iter_high_range_name_number_symbol_candidates,
        ),
        "mutate.toggle-case-stems": FamilySpec(
            family_id="mutate.toggle-case-stems",
            priority=300,
            band=8,
            description="Stems with hashcat toggle-case rules",
            generator=_iter_bare_stems_for_rules,
            rule_file=str(RULES_DIR / "toggle_case.rule"),
        ),
        "mutate.toggle-case-name-ext-number": FamilySpec(
            family_id="mutate.toggle-case-name-ext-number",
            priority=310,
            band=8,
            description="Name+extension+number with hashcat toggle-case rules",
            generator=_iter_name_extension_number_base,
            rule_file=str(RULES_DIR / "toggle_case.rule"),
        ),
    }

    for spec in registry.values():
        if spec.family_id == "report.high-range-name-number-symbol":
            spec.candidate_count = _count_high_range_name_number_symbol_candidates(catalog)
        else:
            spec.candidate_count = sum(1 for _ in spec.generator(catalog))
        spec.source_tags = catalog.source_tags

    return registry


def write_wordlist(
    family_spec: FamilySpec,
    catalog: SeedCatalog,
    output_path: str,
    max_candidates: int | None = None,
) -> str:
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)

    with output.open("w", encoding="utf-8") as handle:
        for index, candidate in enumerate(family_spec.generator(catalog)):
            if max_candidates is not None and index >= max_candidates:
                break
            handle.write(candidate)
            handle.write("\n")

    return str(output)


def _iter_exact_labels(catalog: SeedCatalog):
    yield from _dedupe(
        candidate
        for candidate in (
            label for label in catalog.labels
        )
        if _within_length(candidate)
    )


def _iter_compact_labels(catalog: SeedCatalog):
    yield from _dedupe(
        candidate
        for label in catalog.labels
        for candidate in {
            _compact(label),
            _compact(_strip_boilerplate(label)),
            _title_compact(label),
            _title_compact(_strip_boilerplate(label)),
        }
        if candidate and _within_length(candidate)
    )


def _iter_filtered_labels(catalog: SeedCatalog):
    yield from _dedupe(
        candidate
        for label in catalog.labels
        for candidate in {
            _compact(_strip_boilerplate(label)),
            _filtered_spaced(label),
            _title_compact(_strip_boilerplate(label)),
        }
        if candidate and _within_length(candidate)
    )


def _iter_bare_stems(catalog: SeedCatalog):
    yield from _dedupe(
        candidate
        for candidate in _stem_variants(catalog)
        if _within_length(candidate)
    )


def _iter_wallet_identity_candidates(catalog: SeedCatalog):
    compact_labels = {_title_compact(label) for label in catalog.labels if label}
    preferred_blocks = {
        *_top_stems(catalog),
        *compact_labels,
    }
    base_candidates = set()
    for block in preferred_blocks:
        if not block:
            continue
        base_candidates.update(
            {
                block,
                f"{block}!",
                f"{block}#",
                f"#{block}",
            }
        )
    yield from _dedupe(candidate for candidate in base_candidates if _within_length(candidate))


def _iter_name_number_candidates(catalog: SeedCatalog):
    yield from _dedupe(
        candidate
        for name in catalog.names
        for block in {_title(name), name}
        for number in catalog.numbers
        for candidate in {
            f"{block}{number}",
            f"{number}{block}",
        }
        if _within_length(candidate)
    )


def _iter_name_number_symbol_candidates(catalog: SeedCatalog):
    yield from _dedupe(
        candidate
        for name in catalog.names
        for block in {_title(name), name}
        for number in catalog.numbers
        for symbol in catalog.symbols
        for candidate in {
            f"{block}{number}{symbol}",
            f"{block}{symbol}{number}",
            f"{symbol}{block}{number}",
            f"{number}{symbol}{block}",
        }
        if _within_length(candidate)
    )


def _iter_name_extension_number_candidates(catalog: SeedCatalog):
    yield from _dedupe(
        candidate
        for name in catalog.names
        for extension in catalog.extensions
        for block in _case_blocks(name, extension)
        for number in catalog.numbers
        for symbol in ("", *catalog.symbols)
        for candidate in {
            f"{block}{number}{symbol}",
            f"{block}{symbol}{number}",
        }
        if _within_length(candidate)
    )


def _iter_extension_name_number_candidates(catalog: SeedCatalog):
    yield from _dedupe(
        candidate
        for extension in catalog.extensions
        for name in catalog.names
        for block in _case_blocks(extension, name)
        for number in catalog.numbers
        for symbol in ("", *catalog.symbols)
        for candidate in {
            f"{block}{number}{symbol}",
            f"{block}{symbol}{number}",
        }
        if _within_length(candidate)
    )


def _iter_name_number_extension_candidates(catalog: SeedCatalog):
    yield from _dedupe(
        candidate
        for name in catalog.names
        for extension in catalog.extensions
        for block in _case_blocks(name)
        for suffix in _case_blocks(extension)
        for number in catalog.numbers
        for symbol in ("", *catalog.symbols)
        for candidate in {
            f"{block}{number}{suffix}{symbol}",
            f"{block}{symbol}{number}{suffix}",
        }
        if _within_length(candidate)
    )


def _iter_high_range_name_number_symbol_candidates(catalog: SeedCatalog):
    for name in catalog.names:
        titled = _title(name)
        for number in range(201, 100000):
            number_text = str(number)
            for symbol in catalog.symbols:
                for candidate in (f"{titled}{number_text}{symbol}", f"{titled}{symbol}{number_text}"):
                    if _within_length(candidate):
                        yield candidate


def _iter_split_number_candidates(catalog: SeedCatalog):
    suffixes = tuple(sorted({number for number in catalog.numbers if len(number) >= 2}))
    for name in catalog.names:
        word_variants = {_title(name)}
        for extension in catalog.extensions:
            word_variants.update(_case_blocks(name, extension))
            word_variants.update(_case_blocks(extension, name))
        for prefix in range(100):
            prefix_text = f"{prefix:02d}"
            for symbol in TOP_SYMBOLS:
                for suffix in suffixes:
                    for word in word_variants:
                        candidate = f"{word}{prefix_text}{symbol}{suffix}"
                        if _within_length(candidate):
                            yield candidate
    for stem in _top_stems(catalog):
        for number in catalog.numbers:
            if len(number) < 3:
                continue
            for split_at in range(1, len(number)):
                for symbol in TOP_SYMBOLS:
                    candidate = f"{stem}{number[:split_at]}{symbol}{number[split_at:]}"
                    if _within_length(candidate):
                        yield candidate


def _iter_extension_first_candidates(catalog: SeedCatalog):
    for name in catalog.names:
        for extension in catalog.extensions:
            left = _title(extension)
            right = _title(name)
            for number in catalog.numbers:
                for symbol in catalog.symbols:
                    for candidate in (
                        f"{left}{right}{number}{symbol}",
                        f"{left}{symbol}{right}{number}",
                        f"{number}{symbol}{left}",
                    ):
                        if _within_length(candidate):
                            yield candidate


def _iter_two_symbol_candidates(catalog: SeedCatalog):
    for block in _top_stems(catalog):
        for prefix_symbol, suffix_symbol in product(TOP_SYMBOLS, repeat=2):
            for candidate in (f"{prefix_symbol}{block}{suffix_symbol}", f"{block}{prefix_symbol}{suffix_symbol}"):
                if _within_length(candidate):
                    yield candidate


def _iter_double_symbol_stems(catalog: SeedCatalog):
    for block in _top_stems(catalog):
        for prefix_symbol, suffix_symbol in product(TOP_SYMBOLS, repeat=2):
            for candidate in (f"{prefix_symbol}{block}{suffix_symbol}", f"{block}{prefix_symbol}{suffix_symbol}"):
                if _within_length(candidate):
                    yield candidate


def _iter_spaced_labels(catalog: SeedCatalog):
    yield from _dedupe(
        candidate
        for label in catalog.labels
        for candidate in {
            label,
            _filtered_spaced(label),
        }
        if candidate and " " in candidate and _within_length(candidate)
    )


def _count_high_range_name_number_symbol_candidates(catalog: SeedCatalog) -> int:
    count = 0
    for name in catalog.names:
        base_length = len(_title(name)) + 1
        for digits, range_count in ((3, 799), (4, 9000), (5, 90000)):
            if 8 <= base_length + digits <= 16:
                count += range_count * len(catalog.symbols) * 2
    return count


def _stem_variants(catalog: SeedCatalog) -> set[str]:
    stems = {_title(name) for name in catalog.names}
    stems.update(name for name in catalog.names)
    for name in catalog.names:
        for extension in catalog.extensions:
            stems.update(_case_blocks(name, extension))
            stems.update(_case_blocks(extension, name))
    for label in catalog.labels:
        filtered = _compact(_strip_boilerplate(label))
        if filtered:
            stems.add(filtered)
            stems.add(_title_compact(filtered))
    return {stem for stem in stems if stem}


def _top_stems(catalog: SeedCatalog) -> tuple[str, ...]:
    stems = sorted(_stem_variants(catalog), key=lambda value: (len(value), value))
    preferred = [stem for stem in stems if any(char.isdigit() for char in stem)]
    if not preferred:
        preferred = stems
    return tuple(preferred[:8] or stems[:8])


def _case_blocks(*parts: str) -> set[str]:
    normalized = [part for part in parts if part]
    compact = "".join(normalized)
    titled = "".join(_title(part) for part in normalized)
    first_title = _title(normalized[0]) + "".join(part.lower() for part in normalized[1:]) if normalized else ""
    return {compact.lower(), titled, first_title}


def _compact(text: str) -> str:
    return "".join(text.split())


def _filtered_spaced(text: str) -> str:
    words = [word for word in WORD_RE.findall(text) if word.lower() not in {"usuario", "clave"}]
    numbers = re.findall(r"\d+", text)
    trailing_symbols = "".join(symbol for symbol in text if not symbol.isalnum() and not symbol.isspace())
    pieces = [*words, *numbers]
    if trailing_symbols:
        pieces.append(trailing_symbols)
    return " ".join(piece.lower() for piece in pieces).strip()


def _strip_boilerplate(text: str) -> str:
    filtered = [word for word in WORD_RE.findall(text) if word.lower() not in {"usuario", "clave", "wallet"}]
    numbers = re.findall(r"\d+", text)
    symbols = "".join(symbol for symbol in text if not symbol.isalnum() and not symbol.isspace())
    return " ".join([*filtered, *numbers, symbols]).strip()


def _title(text: str) -> str:
    return text[:1].upper() + text[1:].lower()


def _title_compact(text: str) -> str:
    words = [word for word in WORD_RE.findall(text) if word.lower() not in {"usuario", "clave"}]
    numbers = re.findall(r"\d+", text)
    symbols = "".join(symbol for symbol in text if not symbol.isalnum() and not symbol.isspace())
    return "".join([*(_title(word) for word in words), *numbers, symbols])


_HAS_UPPER = re.compile(r"[A-Z]")
_HAS_LOWER = re.compile(r"[a-z]")
_HAS_DIGIT = re.compile(r"[0-9]")


def _meets_policy(candidate: str) -> bool:
    return (
        8 <= len(candidate) <= 16
        and _HAS_UPPER.search(candidate) is not None
        and _HAS_LOWER.search(candidate) is not None
        and _HAS_DIGIT.search(candidate) is not None
    )


def _within_length(candidate: str) -> bool:
    return _meets_policy(candidate)


def _within_length_only(candidate: str) -> bool:
    return 8 <= len(candidate) <= 16


def _iter_bare_stems_for_rules(catalog: SeedCatalog):
    """Base stems without case variants — hashcat rules handle case mutations."""
    yield from _dedupe(
        candidate
        for candidate in _stem_variants(catalog)
        if _within_length_only(candidate)
    )


def _iter_name_extension_number_base(catalog: SeedCatalog):
    """Name+extension+number without case variants — hashcat rules handle case mutations."""
    yield from _dedupe(
        candidate
        for name in catalog.names
        for extension in catalog.extensions
        for base in {"".join([name, extension])}
        for number in catalog.numbers
        for symbol in ("", *catalog.symbols)
        for candidate in {
            f"{base}{number}{symbol}",
            f"{base}{symbol}{number}",
        }
        if _within_length_only(candidate)
    )


def _dedupe(candidates):
    seen = set()
    for candidate in candidates:
        if candidate in seen:
            continue
        seen.add(candidate)
        yield candidate
