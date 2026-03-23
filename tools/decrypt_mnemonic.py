import argparse
import html
import json
import re
import subprocess
from hashlib import scrypt
from pathlib import Path


def extract_wallet_blob(xml_path: str, key_name: str) -> str:
    content = Path(xml_path).read_text(encoding="utf-8")
    pattern = rf'<string name="{re.escape(key_name)}">(.*?)</string>'
    match = re.search(pattern, content)
    if not match:
        raise ValueError(f"Could not find {key_name} in {xml_path}")
    return html.unescape(match.group(1))


def decrypt_aes_128_ctr(ciphertext: bytes, key: bytes, iv_hex: str) -> bytes:
    result = subprocess.run(
        [
            "openssl",
            "enc",
            "-d",
            "-aes-128-ctr",
            "-K",
            key.hex(),
            "-iv",
            iv_hex,
            "-nosalt",
            "-nopad",
        ],
        input=ciphertext,
        capture_output=True,
        check=True,
    )
    return result.stdout


def decrypt(password: str, wallet_blob_json: str) -> str:
    data = json.loads(wallet_blob_json)
    crypto = data["crypto"]
    kdfparams = crypto["kdfparams"]

    dk = scrypt(
        password.encode("utf-8"),
        salt=bytes.fromhex(kdfparams["salt"]),
        n=kdfparams["n"],
        r=kdfparams["r"],
        p=kdfparams["p"],
        dklen=kdfparams["dklen"],
    )

    plaintext = decrypt_aes_128_ctr(
        ciphertext=bytes.fromhex(crypto["ciphertext"]),
        key=dk[:16],
        iv_hex=crypto["cipherparams"]["iv"],
    )
    return plaintext.decode("utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Decrypt TronLink wallet_newmnemonic_key data from a shared_prefs XML"
    )
    parser.add_argument("xml_path", help="Path to the shared_prefs wallet XML")
    parser.add_argument("password", help="Recovered wallet password")
    parser.add_argument(
        "--key-name",
        default="wallet_newmnemonic_key",
        help="XML string key to decrypt (default: wallet_newmnemonic_key)",
    )
    return parser


if __name__ == "__main__":
    args = build_parser().parse_args()
    try:
        wallet_blob_json = extract_wallet_blob(args.xml_path, args.key_name)
        mnemonic = decrypt(args.password, wallet_blob_json)
    except subprocess.CalledProcessError as exc:
        stderr = exc.stderr.decode("utf-8", errors="replace").strip()
        raise SystemExit(f"openssl failed while decrypting: {stderr or exc}")
    except Exception as exc:
        raise SystemExit(str(exc))

    print(mnemonic)
