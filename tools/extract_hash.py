import argparse
import html
import json
import re
from pathlib import Path


def extract_hash(xml_path: str) -> str:
    content = Path(xml_path).read_text(encoding="utf-8")
    match = re.search(r'<string name="wallet_keystore_key">(.*?)</string>', content)
    if not match:
        raise ValueError(f"Could not find wallet_keystore_key in {xml_path}")

    keystore_json = html.unescape(match.group(1))
    keystore = json.loads(keystore_json)
    crypto = keystore["crypto"]
    kdfparams = crypto["kdfparams"]

    # Hashcat mode 15700 format: $ethereum$s*n*r*p*salt*ciphertext*mac
    n = kdfparams["n"]
    r = kdfparams["r"]
    p = kdfparams["p"]
    salt = crypto["kdfparams"]["salt"]
    ciphertext = crypto["ciphertext"]
    mac = crypto["mac"]

    return f"$ethereum$s*{n}*{r}*{p}*{salt}*{ciphertext}*{mac}"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Extract a Hashcat mode 15700 hash from a TronLink shared_prefs XML"
    )
    parser.add_argument("xml_path", help="Path to the shared_prefs wallet XML")
    return parser


if __name__ == "__main__":
    args = build_parser().parse_args()
    try:
        print(extract_hash(args.xml_path))
    except Exception as exc:
        raise SystemExit(str(exc))
