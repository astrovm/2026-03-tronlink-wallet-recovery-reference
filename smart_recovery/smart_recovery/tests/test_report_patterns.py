import json
import os
import tempfile
import unittest

from smart_recovery.toolkit.report_patterns import build_family_registry
from smart_recovery.toolkit.seeds import build_seed_catalog


class ReportPatternTests(unittest.TestCase):
    def test_registry_contains_structured_bands_before_bruteforce(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            recovery_root = os.path.join(temp_dir, "recovery")
            shared_prefs = os.path.join(recovery_root, "shared_prefs")
            os.makedirs(shared_prefs)
            note_file = os.path.join(temp_dir, "note_seeds.json")
            with open(note_file, "w", encoding="utf-8") as handle:
                json.dump({"labels": ["alex orbit 204", "wallet sample#1"]}, handle)

            catalog = build_seed_catalog(recovery_root=recovery_root, note_seed_file=note_file)
            registry = build_family_registry(catalog)

        self.assertIn("seed.exact-labels", registry)
        self.assertIn("normalize.compact-labels", registry)
        self.assertIn("compose.name-extension-number", registry)
        self.assertIn("symbols.double-around-stems", registry)
        self.assertLess(registry["seed.exact-labels"].priority, 1000)
        self.assertLess(registry["symbols.double-around-stems"].priority, 1000)

    def test_spaced_variants_are_late_and_compact_variants_exist(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            recovery_root = os.path.join(temp_dir, "recovery")
            shared_prefs = os.path.join(recovery_root, "shared_prefs")
            os.makedirs(shared_prefs)
            note_file = os.path.join(temp_dir, "note_seeds.json")
            with open(note_file, "w", encoding="utf-8") as handle:
                json.dump({"labels": ["alex orbit 204"]}, handle)

            catalog = build_seed_catalog(recovery_root=recovery_root, note_seed_file=note_file)
            registry = build_family_registry(catalog)

            compact = set(registry["normalize.compact-labels"].generator(catalog))
            spaced = set(registry["normalize.spaced-labels"].generator(catalog))

        self.assertIn("alexorbit204", compact)
        self.assertIn("alex orbit 204", spaced)
        self.assertGreater(
            registry["normalize.spaced-labels"].priority,
            registry["normalize.compact-labels"].priority,
        )


if __name__ == "__main__":
    unittest.main()
