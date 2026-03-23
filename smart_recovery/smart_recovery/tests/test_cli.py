import unittest
from unittest import mock

from smart_recovery.toolkit import cli
from smart_recovery.toolkit.models import WorkUnit


class SmartRecoveryCliTests(unittest.TestCase):
    def test_run_stops_on_failed_work_unit(self):
        sample_wordlist = "runtime/wallet.txt"
        sample_restore = "runtime/wallet.restore"
        state = {
            "work_units": {
                "report.wallet-identities": WorkUnit(
                    unit_id="report.wallet-identities",
                    family_id="report.wallet-identities",
                    priority=10,
                    attack_mode="wordlist",
                    description="Wallet identity variations",
                    wordlist_path=sample_wordlist,
                    session_name="session_report_wallet",
                    restore_path=sample_restore,
                ).to_dict()
            },
            "historical_families": [],
            "family_progress": {},
            "result": None,
            "version": 2,
        }

        planner = mock.Mock()
        planner.plan.side_effect = lambda current_state: [
            WorkUnit.from_dict(current_state["work_units"]["report.wallet-identities"])
        ]
        planner.materialize_wordlist.return_value = sample_wordlist

        store = mock.Mock()
        store.load.return_value = state

        runner = mock.Mock()
        runner.execute.return_value = ("failed", "Hashcat exit code 255")

        with mock.patch.object(cli, "StateStore", return_value=store), mock.patch.object(
            cli,
            "RecoveryPlanner",
            return_value=planner,
        ), mock.patch.object(cli, "HashcatRunner", return_value=runner), mock.patch(
            "builtins.print"
        ) as print_mock:
            exit_code = cli.main(
                [
                    "run",
                    "--hash-file",
                    "target.hash",
                    "--state-file",
                    "smart_recovery/recovery_state.json",
                    "--runtime-dir",
                    "smart_recovery/runtime",
                ]
            )

        self.assertEqual(exit_code, 1)
        print_mock.assert_any_call("Hashcat exit code 255")

    def test_status_prints_band_summary(self):
        state = {
            "work_units": {
                "seed.exact-labels": WorkUnit(
                    unit_id="seed.exact-labels",
                    family_id="seed.exact-labels",
                    priority=10,
                    attack_mode="wordlist",
                    description="Exact labels",
                    metadata={"band": 1},
                ).to_dict(),
                "normalize.compact-labels": WorkUnit(
                    unit_id="normalize.compact-labels",
                    family_id="normalize.compact-labels",
                    priority=20,
                    attack_mode="wordlist",
                    description="Compact labels",
                    metadata={"band": 2},
                ).to_dict(),
            },
            "historical_families": [],
            "family_progress": {},
            "result": None,
            "version": 3,
            "seed_fingerprint": "abc",
            "planner_version": 2,
        }

        planner = mock.Mock()
        planner.plan.return_value = [
            WorkUnit.from_dict(state["work_units"]["seed.exact-labels"]),
            WorkUnit.from_dict(state["work_units"]["normalize.compact-labels"]),
        ]

        with mock.patch("builtins.print") as print_mock:
            cli._print_status(state, planner)

        print_mock.assert_any_call("Band 1: 1")
        print_mock.assert_any_call("Band 2: 1")


if __name__ == "__main__":
    unittest.main()
