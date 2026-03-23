import sys
import argparse
from .stage1 import Stage1Session


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Zygote Injection Toolkit Stage 1")
    parser.add_argument("--serial", help="Device serial number")
    parser.add_argument("--uid", type=int, default=1000, help="Target UID (default: 1000)")
    parser.add_argument("--gid", type=int, default=1000, help="Target GID (default: 1000)")
    parser.add_argument("--groups", default="3003", help="Target supplementary groups (default: 3003)")
    parser.add_argument("--seinfo", default="platform:isSystemServer:system_app:targetSdkVersion=29:complete", help="Target SEInfo label")
    parser.add_argument("--app-data-dir", help="Target app data directory")
    parser.add_argument("--package-name", help="Target package name")
    parser.add_argument("--nice-name", default="runmenetcat", help="Process nice name")
    parser.add_argument("--target-sdk-version", type=int, help="Target SDK version")
    parser.add_argument("--is-top-app", action="store_true", help="Set is-top-app flag")

    args = parser.parse_args([] if argv is None else argv)

    print("This package is very experimental!")
    
    if args.serial:
        stage_1_session = Stage1Session(device_serial=args.serial)
    else:
        stage_1_session = Stage1Session()
    
    success = stage_1_session.start_stage1_session(
        uid=args.uid,
        gid=args.gid,
        groups=args.groups,
        seinfo=args.seinfo,
        app_data_dir=args.app_data_dir,
        package_name=args.package_name,
        nice_name=args.nice_name,
        target_sdk_version=args.target_sdk_version,
        is_top_app=args.is_top_app
    )
    
    if not success:
        print("Stage 1 failed!", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
