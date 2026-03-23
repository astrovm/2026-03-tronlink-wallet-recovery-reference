import os
import tempfile
import unittest

from smart_recovery.toolkit.models import WorkUnit
from smart_recovery.toolkit.state import StateStore


class StateStoreTests(unittest.TestCase):
    def test_persists_work_units_and_historical_families(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            hash_path = os.path.join(temp_dir, "target.hash")
            state_path = os.path.join(temp_dir, "recovery_state.json")

            with open(hash_path, "w", encoding="utf-8") as handle:
                handle.write("$ethereum$s*65536*8*1*salt*cipher*mac\n")

            store = StateStore(state_path)
            state = store.load(hash_path)
            store.import_historical_families(state, {"report.legacy-structured"})

            work_unit = WorkUnit(
                unit_id="wallet-identities",
                family_id="report.wallet-identities",
                priority=10,
                attack_mode="wordlist",
                description="Wallet-name identities",
                wordlist_path=os.path.join(temp_dir, "wallet.txt"),
            )

            store.upsert_work_unit(state, work_unit)
            store.mark_running(
                state,
                work_unit.unit_id,
                session_name="session_wallet-identities",
                restore_path=os.path.join(temp_dir, "wallet.restore"),
            )
            store.mark_paused(state, work_unit.unit_id)

            reloaded = StateStore(state_path).load(hash_path)

        self.assertEqual(reloaded["version"], 3)
        self.assertIn("report.legacy-structured", reloaded["historical_families"])
        self.assertIn(work_unit.unit_id, reloaded["work_units"])
        self.assertEqual(reloaded["work_units"][work_unit.unit_id]["status"], "PAUSED")
        self.assertEqual(
            reloaded["work_units"][work_unit.unit_id]["session_name"],
            "session_wallet-identities",
        )
        self.assertEqual(reloaded["version"], 3)
        self.assertIn("planner_version", reloaded)
        self.assertIn("seed_fingerprint", reloaded)

    def test_migrates_legacy_task_status_schema(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            hash_path = os.path.join(temp_dir, "target.hash")
            state_path = os.path.join(temp_dir, "recovery_state.json")

            with open(hash_path, "w", encoding="utf-8") as handle:
                handle.write("$ethereum$s*65536*8*1*salt*cipher*mac\n")

            with open(state_path, "w", encoding="utf-8") as handle:
                handle.write(
                    """
                    {
                        "tasks": {
                            "task_1_1": {
                                "status": "IN_PROGRESS",
                                "session": "session_task_1_1"
                            }
                        }
                    }
                    """
                )

            migrated = StateStore(state_path).load(hash_path)

        self.assertEqual(migrated["version"], 3)
        self.assertIn("legacy.task_1_1", migrated["work_units"])
        self.assertEqual(migrated["work_units"]["legacy.task_1_1"]["status"], "PAUSED")
        self.assertEqual(
            migrated["work_units"]["legacy.task_1_1"]["session_name"],
            "session_task_1_1",
        )


if __name__ == "__main__":
    unittest.main()
