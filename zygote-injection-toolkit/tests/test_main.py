import contextlib
import io
import unittest
from unittest.mock import Mock, patch

from zygote_injection_toolkit import __main__
from zygote_injection_toolkit.stage1 import Stage1Session


class MainTests(unittest.TestCase):
    def test_main_stops_after_stage1_failure(self) -> None:
        stderr = io.StringIO()

        with (
            patch.object(__main__, "Stage1Session") as mock_stage1_class,
            contextlib.redirect_stderr(stderr),
        ):
            mock_stage1 = mock_stage1_class.return_value
            mock_stage1.start_stage1_session.return_value = False

            __main__.main()

        mock_stage1_class.assert_called_once_with()
        mock_stage1.start_stage1_session.assert_called_once()
        self.assertIn("Stage 1 failed!", stderr.getvalue())


class Stage1DiagnosticsTests(unittest.TestCase):
    def test_format_diagnostic_value_escapes_multiline_strings(self) -> None:
        formatted = Stage1Session._format_diagnostic_value("\n" * 200)

        self.assertNotIn("\n", formatted)

    def test_start_stage1_session_accepts_late_success_after_poll_window(self) -> None:
        adb_client = Mock()
        session = Stage1Session(auto_connect=False, adb_client=adb_client)
        session.device = Mock()
        probe = Mock()
        probe.get_setting.side_effect = ["still-set"] * 20 + ["null"]
        probe.is_port_open.return_value = True
        stdout = io.StringIO()

        with (
            patch.object(session, "is_port_open", return_value=False),
            patch.object(session, "shell_execute"),
            patch.object(session, "delivery_mode", return_value="new"),
            patch.object(session, "find_netcat_command", return_value=["toybox", "nc"]),
            patch.object(session, "generate_stage1_payload", return_value="payload"),
            patch.object(session, "_create_stage1_probe", return_value=probe),
            patch("zygote_injection_toolkit.stage1.time.sleep"),
            contextlib.redirect_stdout(stdout),
        ):
            self.assertTrue(session.start_stage1_session())

        output = stdout.getvalue()
        self.assertIn("Stage 1 success!", output)
        session.device.forward.assert_called_once_with("tcp:1234", "tcp:1234")

    def test_start_stage1_session_prints_diagnostics_on_failure(self) -> None:
        adb_client = Mock()
        session = Stage1Session(auto_connect=False, adb_client=adb_client)
        probe = Mock()
        probe.get_setting.return_value = "still-set"
        probe.is_port_open.return_value = False
        stdout = io.StringIO()

        with (
            patch.object(session, "is_port_open", return_value=False),
            patch.object(session, "shell_execute"),
            patch.object(session, "delivery_mode", return_value="new"),
            patch.object(session, "find_netcat_command", return_value=["toybox", "nc"]),
            patch.object(session, "generate_stage1_payload", return_value="payload"),
            patch.object(session, "_create_stage1_probe", return_value=probe),
            patch.object(
                session,
                "getprop",
                side_effect=[
                    "2024-05-01",
                    "samsung/a31xx/a31:12/SP1A/example:user/release-keys",
                ],
            ),
            patch("zygote_injection_toolkit.stage1.time.sleep"),
            contextlib.redirect_stdout(stdout),
        ):
            self.assertFalse(session.start_stage1_session())

        output = stdout.getvalue()
        self.assertIn("Stage 1 failed, reboot and try again", output)
        self.assertIn("Diagnostics:", output)
        self.assertIn("delivery_mode: new", output)
        self.assertIn("netcat_command: toybox nc", output)
        self.assertIn("last_setting_value: 'still-set'", output)
        self.assertIn("security_patch: 2024-05-01", output)
        self.assertIn("listener_on_1234: False", output)

    def test_start_stage1_session_uses_fresh_probe_after_launch(self) -> None:
        adb_client = Mock()
        session = Stage1Session(auto_connect=False, adb_client=adb_client)
        session.device = Mock()
        session.device.serial = "emulator-5554"
        probe = Mock()
        probe.get_setting.side_effect = ["still-set", "null"]
        probe.is_port_open.return_value = True
        stdout = io.StringIO()

        with (
            patch.object(session, "is_port_open", return_value=False),
            patch.object(session, "shell_execute"),
            patch.object(session, "delivery_mode", return_value="new"),
            patch.object(session, "find_netcat_command", return_value=["toybox", "nc"]),
            patch.object(session, "generate_stage1_payload", return_value="payload"),
            patch.object(session, "_create_stage1_probe", return_value=probe),
            patch("zygote_injection_toolkit.stage1.time.sleep"),
            contextlib.redirect_stdout(stdout),
        ):
            self.assertTrue(session.start_stage1_session())

        output = stdout.getvalue()
        self.assertIn("Stage 1 success!", output)
        session.device.forward.assert_called_once_with("tcp:1234", "tcp:1234")

    def test_start_stage1_session_starts_explicit_settings_component(self) -> None:
        adb_client = Mock()
        session = Stage1Session(auto_connect=False, adb_client=adb_client)
        session.device = Mock()
        probe = Mock()
        probe.get_setting.return_value = "null"
        probe.is_port_open.return_value = True

        with (
            patch.object(session, "is_port_open", return_value=False),
            patch.object(session, "shell_execute") as shell_execute,
            patch.object(session, "delivery_mode", return_value="new"),
            patch.object(session, "find_netcat_command", return_value=["toybox", "nc"]),
            patch.object(session, "generate_stage1_payload", return_value="payload"),
            patch.object(session, "_create_stage1_probe", return_value=probe),
            patch("zygote_injection_toolkit.stage1.time.sleep"),
        ):
            self.assertTrue(session.start_stage1_session())

        shell_execute.assert_any_call(
            ["am", "start", "-n", "com.android.settings/com.android.settings.Settings"]
        )

    def test_start_stage1_session_accepts_listener_before_setting_cleanup(self) -> None:
        adb_client = Mock()
        session = Stage1Session(auto_connect=False, adb_client=adb_client)
        session.device = Mock()
        probe = Mock()
        probe.get_setting.return_value = "still-set"
        probe.is_port_open.return_value = True
        stdout = io.StringIO()

        with (
            patch.object(session, "is_port_open", return_value=False),
            patch.object(session, "shell_execute"),
            patch.object(session, "delivery_mode", return_value="new"),
            patch.object(session, "find_netcat_command", return_value=["toybox", "nc"]),
            patch.object(session, "generate_stage1_payload", return_value="payload"),
            patch.object(session, "_create_stage1_probe", return_value=probe),
            patch("zygote_injection_toolkit.stage1.time.sleep"),
            contextlib.redirect_stdout(stdout),
        ):
            self.assertTrue(session.start_stage1_session())

        output = stdout.getvalue()
        self.assertIn("Stage 1 success!", output)
        session.device.forward.assert_called_once_with("tcp:1234", "tcp:1234")


if __name__ == "__main__":
    unittest.main()
