import os
import tempfile
import unittest
from unittest import mock

from smart_recovery.toolkit.hashcat_runner import HashcatRunner
from smart_recovery.toolkit.models import WorkUnit


class HashcatRunnerTests(unittest.TestCase):
    def test_builds_valid_fresh_and_restore_commands(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            hash_path = os.path.join(temp_dir, "target.hash")
            wordlist_path = os.path.join(temp_dir, "wallet.txt")

            with open(hash_path, "w", encoding="utf-8") as handle:
                handle.write("$ethereum$s*65536*8*1*salt*cipher*mac\n")

            with open(wordlist_path, "w", encoding="utf-8") as handle:
                handle.write("AlexOrbit204!\n")

            runner = HashcatRunner(hash_path=hash_path, mode="15700")
            work_unit = WorkUnit(
                unit_id="report.wallet-identities",
                family_id="report.wallet-identities",
                priority=10,
                attack_mode="wordlist",
                description="Wallet-name identities",
                wordlist_path=wordlist_path,
                session_name="session_report_wallet",
                restore_path=os.path.join(temp_dir, "wallet.restore"),
            )

            fresh_command = runner.build_run_command(work_unit)
            restore_command = runner.build_restore_command(work_unit)

        self.assertEqual(
            fresh_command,
            [
                "hashcat",
                "-m",
                "15700",
                "--self-test-disable",
                "--session",
                "session_report_wallet",
                "--restore-file-path",
                work_unit.restore_path,
                "--status",
                "--status-timer",
                "30",
                "-w",
                "3",
                "-a",
                "0",
                hash_path,
                wordlist_path,
            ],
        )
        self.assertEqual(
            restore_command,
            [
                "hashcat",
                "--restore",
                "--session",
                "session_report_wallet",
                "--restore-file-path",
                work_unit.restore_path,
            ],
        )

    def test_dry_run_does_not_invoke_hashcat(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            hash_path = os.path.join(temp_dir, "target.hash")
            wordlist_path = os.path.join(temp_dir, "wallet.txt")

            with open(hash_path, "w", encoding="utf-8") as handle:
                handle.write("$ethereum$s*65536*8*1*salt*cipher*mac\n")

            with open(wordlist_path, "w", encoding="utf-8") as handle:
                handle.write("AlexOrbit204!\n")

            runner = HashcatRunner(hash_path=hash_path, mode="15700")
            work_unit = WorkUnit(
                unit_id="report.wallet-identities",
                family_id="report.wallet-identities",
                priority=10,
                attack_mode="wordlist",
                description="Wallet-name identities",
                wordlist_path=wordlist_path,
                session_name="session_report_wallet",
                restore_path=os.path.join(temp_dir, "wallet.restore"),
            )
            state = {"work_units": {work_unit.unit_id: work_unit.to_dict()}}
            store = mock.Mock()

            with mock.patch.object(runner, "check_cracked", side_effect=AssertionError("must not run")):
                outcome, command = runner.execute(work_unit, state, store, dry_run=True)

        self.assertEqual(outcome, "dry-run")
        self.assertEqual(command, runner.build_run_command(work_unit))


if __name__ == "__main__":
    unittest.main()
