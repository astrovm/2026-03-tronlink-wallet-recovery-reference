import os
import tempfile
import unittest

from smart_recovery.toolkit.planner import RecoveryPlanner
from smart_recovery.toolkit.state import StateStore


class RecoveryPlannerTests(unittest.TestCase):
    def test_prioritizes_structured_bands_before_bruteforce_and_skips_historical(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            hash_path = os.path.join(temp_dir, "target.hash")
            state_path = os.path.join(temp_dir, "recovery_state.json")
            runtime_dir = os.path.join(temp_dir, ".runtime")
            recovery_root = os.path.join(temp_dir, "recovery")
            os.makedirs(os.path.join(recovery_root, "shared_prefs"))
            note_file = os.path.join(temp_dir, "note_seeds.json")

            with open(hash_path, "w", encoding="utf-8") as handle:
                handle.write("$ethereum$s*65536*8*1*salt*cipher*mac\n")
            with open(note_file, "w", encoding="utf-8") as handle:
                handle.write(
                    '{"labels": ["alex orbit 204"], "names": ["alex"], "extensions": ["orbit"], "numbers": ["204"]}'
                )

            store = StateStore(state_path)
            state = store.load(hash_path)
            store.import_historical_families(state, {"seed.exact-labels"})

            planner = RecoveryPlanner(
                hash_path=hash_path,
                runtime_dir=runtime_dir,
                shard_size=5000,
                recovery_root=recovery_root,
                note_seed_file=note_file,
            )
            work_units = planner.plan(state)
            unit_ids = [unit.unit_id for unit in work_units]

        self.assertEqual(len(unit_ids), len(set(unit_ids)))
        self.assertIn("normalize.compact-labels", unit_ids)
        self.assertIn("compose.name-extension-number", unit_ids)
        self.assertNotIn("seed.exact-labels", unit_ids)
        self.assertIn("bruteforce.common.len8.shard0", unit_ids)
        self.assertIn("bruteforce.full.len8.shard0", unit_ids)
        self.assertLess(unit_ids.index("normalize.compact-labels"), unit_ids.index("bruteforce.common.len8.shard0"))
        self.assertLess(unit_ids.index("bruteforce.common.len8.shard0"), unit_ids.index("bruteforce.full.len8.shard0"))

    def test_max_band_filters_out_later_bands_and_bruteforce(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            hash_path = os.path.join(temp_dir, "target.hash")
            state_path = os.path.join(temp_dir, "recovery_state.json")
            runtime_dir = os.path.join(temp_dir, ".runtime")
            recovery_root = os.path.join(temp_dir, "recovery")
            os.makedirs(os.path.join(recovery_root, "shared_prefs"))
            note_file = os.path.join(temp_dir, "note_seeds.json")

            with open(hash_path, "w", encoding="utf-8") as handle:
                handle.write("$ethereum$s*65536*8*1*salt*cipher*mac\n")
            with open(note_file, "w", encoding="utf-8") as handle:
                handle.write(
                    '{"labels": ["alex orbit 204"], "names": ["alex"], "extensions": ["orbit"], "numbers": ["204"]}'
                )

            store = StateStore(state_path)
            state = store.load(hash_path)
            planner = RecoveryPlanner(
                hash_path=hash_path,
                runtime_dir=runtime_dir,
                shard_size=5000,
                recovery_root=recovery_root,
                note_seed_file=note_file,
                max_band=2,
            )

            work_units = planner.plan(state)

        self.assertTrue(work_units)
        self.assertTrue(all((unit.metadata.get("band") or 0) <= 2 for unit in work_units))
        self.assertNotIn("bruteforce.common.len8.shard0", [unit.unit_id for unit in work_units])


if __name__ == "__main__":
    unittest.main()
