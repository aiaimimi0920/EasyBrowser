#!/usr/bin/env python3

from __future__ import annotations

import argparse
import base64
import hashlib
import json
from pathlib import Path
from typing import Any

from nacl.public import PrivateKey, PublicKey, SealedBox


IMPORT_CODE_PREFIX = "easybrowser-import-v1."


def b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def b64url_decode(text: str) -> bytes:
    padding = "=" * ((4 - (len(text) % 4)) % 4)
    return base64.urlsafe_b64decode(text + padding)


def read_text(path: str) -> str:
    return Path(path).read_text(encoding="utf-8-sig").strip()


def write_text(path: str, content: str) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(content, encoding="utf-8")


def read_json(path: str) -> dict[str, Any]:
    return json.loads(read_text(path))


def build_payload(args: argparse.Namespace) -> dict[str, Any]:
    endpoint = args.endpoint.strip() if args.endpoint else f"https://{args.account_id}.r2.cloudflarestorage.com"
    return {
        "schemaVersion": 1,
        "kind": "easybrowser-import-code",
        "distribution": "r2",
        "accountId": args.account_id,
        "endpoint": endpoint,
        "bucket": args.bucket,
        "manifestObjectKey": args.manifest_object_key,
        "accessKeyId": args.access_key_id,
        "secretAccessKey": args.secret_access_key,
        "syncEnabled": bool(args.sync_enabled),
        "syncIntervalSeconds": int(args.sync_interval_seconds),
        "releaseVersion": args.release_version.strip() if args.release_version else "",
    }


def encode_payload(payload: dict[str, Any]) -> str:
    payload_text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return IMPORT_CODE_PREFIX + b64url_encode(payload_text.encode("utf-8"))


def decode_import_code(import_code: str) -> dict[str, Any]:
    text = import_code.strip()
    if not text.startswith(IMPORT_CODE_PREFIX):
        raise SystemExit("Unsupported import code format.")
    payload_bytes = b64url_decode(text[len(IMPORT_CODE_PREFIX) :])
    payload = json.loads(payload_bytes.decode("utf-8"))
    if payload.get("kind") != "easybrowser-import-code":
        raise SystemExit("Import code payload kind mismatch.")
    return payload


def bundle_for_import_code(import_code: str, payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "schemaVersion": 1,
        "kind": "easybrowser-import-code-bundle",
        "importCode": import_code,
        "payload": payload,
    }


def load_public_key(text: str) -> PublicKey:
    normalized = text.strip()
    try:
        key_bytes = b64url_decode(normalized)
    except Exception:
        key_bytes = b""
    if len(key_bytes) == 32:
        return PublicKey(key_bytes)
    return load_private_key(normalized).public_key


def load_private_key(text: str) -> PrivateKey:
    normalized = text.strip()
    try:
        key_bytes = b64url_decode(normalized)
    except Exception:
        key_bytes = b""
    if len(key_bytes) == 32:
        return PrivateKey(key_bytes)
    return PrivateKey(hashlib.sha256(normalized.encode("utf-8")).digest())


def cmd_generate_keypair(args: argparse.Namespace) -> int:
    if args.seed_text or args.seed_text_file:
        seed_text = args.seed_text.strip() if args.seed_text else read_text(args.seed_text_file)
        private_key = load_private_key(seed_text)
    else:
        private_key = PrivateKey.generate()
    public_key = private_key.public_key
    private_text = b64url_encode(bytes(private_key))
    public_text = b64url_encode(bytes(public_key))

    if args.private_key_output:
        write_text(args.private_key_output, private_text + "\n")
    else:
        print(private_text)

    if args.public_key_output:
        write_text(args.public_key_output, public_text + "\n")
    else:
        print(public_text)

    if args.bundle_output:
        bundle = {
            "schemaVersion": 1,
            "algorithm": "nacl-sealed-box",
            "publicKey": public_text,
            "privateKey": private_text,
        }
        write_text(args.bundle_output, json.dumps(bundle, ensure_ascii=False, indent=2))
    return 0


def cmd_derive_public_key(args: argparse.Namespace) -> int:
    private_key_text = args.private_key.strip() if args.private_key else read_text(args.private_key_file)
    public_text = b64url_encode(bytes(load_private_key(private_key_text).public_key))
    if args.output:
        write_text(args.output, public_text + "\n")
    else:
        print(public_text)
    return 0


def cmd_encode(args: argparse.Namespace) -> int:
    payload = build_payload(args)
    import_code = encode_payload(payload)
    bundle = bundle_for_import_code(import_code, payload)
    output_text = json.dumps(bundle, ensure_ascii=False, indent=2) if args.json_output else import_code
    if args.output:
        write_text(args.output, output_text + ("\n" if not output_text.endswith("\n") else ""))
    else:
        print(output_text)
    return 0


def cmd_inspect(args: argparse.Namespace) -> int:
    import_code = args.import_code.strip() if args.import_code else read_text(args.import_code_file)
    payload = decode_import_code(import_code)
    output_text = json.dumps(payload, ensure_ascii=False, indent=2)
    if args.output:
        write_text(args.output, output_text + "\n")
    else:
        print(output_text)
    return 0


def cmd_encrypt(args: argparse.Namespace) -> int:
    if args.bundle_file:
        bundle = read_json(args.bundle_file)
    else:
        import_code = args.import_code.strip() if args.import_code else read_text(args.import_code_file)
        payload = decode_import_code(import_code)
        bundle = bundle_for_import_code(import_code, payload)

    public_key_text = args.public_key.strip() if args.public_key else read_text(args.public_key_file)
    sealed_box = SealedBox(load_public_key(public_key_text))
    ciphertext = sealed_box.encrypt(json.dumps(bundle, ensure_ascii=False).encode("utf-8"))
    encrypted_bundle = {
        "schemaVersion": 1,
        "algorithm": "nacl-sealed-box",
        "ciphertext": b64url_encode(ciphertext),
    }
    if args.metadata_json:
        encrypted_bundle["metadata"] = json.loads(args.metadata_json)

    serialized = json.dumps(encrypted_bundle, ensure_ascii=False, indent=2)
    if args.output:
        write_text(args.output, serialized + "\n")
    else:
        print(serialized)
    return 0


def cmd_decrypt(args: argparse.Namespace) -> int:
    encrypted = json.loads(args.encrypted_text) if args.encrypted_text else read_json(args.encrypted_file)
    private_key_text = args.private_key.strip() if args.private_key else read_text(args.private_key_file)
    ciphertext = b64url_decode(str(encrypted.get("ciphertext") or "").strip())
    sealed_box = SealedBox(load_private_key(private_key_text))
    bundle = json.loads(sealed_box.decrypt(ciphertext).decode("utf-8"))

    if args.import_code_only:
        output_text = str(bundle.get("importCode") or "")
    else:
        output_text = json.dumps(bundle, ensure_ascii=False, indent=2)

    if args.output:
        write_text(args.output, output_text + ("\n" if not output_text.endswith("\n") else ""))
    else:
        print(output_text)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate, inspect, encrypt, and decrypt EasyBrowser distribution import codes.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    generate_keypair = subparsers.add_parser("generate-keypair")
    seed_group = generate_keypair.add_mutually_exclusive_group()
    seed_group.add_argument("--seed-text", default="")
    seed_group.add_argument("--seed-text-file", default="")
    generate_keypair.add_argument("--public-key-output", default="")
    generate_keypair.add_argument("--private-key-output", default="")
    generate_keypair.add_argument("--bundle-output", default="")
    generate_keypair.set_defaults(func=cmd_generate_keypair)

    derive_public_key = subparsers.add_parser("derive-public-key")
    derive_private_group = derive_public_key.add_mutually_exclusive_group(required=True)
    derive_private_group.add_argument("--private-key", default="")
    derive_private_group.add_argument("--private-key-file", default="")
    derive_public_key.add_argument("--output", default="")
    derive_public_key.set_defaults(func=cmd_derive_public_key)

    encode = subparsers.add_parser("encode")
    encode.add_argument("--account-id", required=True)
    encode.add_argument("--bucket", required=True)
    encode.add_argument("--manifest-object-key", required=True)
    encode.add_argument("--access-key-id", required=True)
    encode.add_argument("--secret-access-key", required=True)
    encode.add_argument("--endpoint", default="")
    encode.add_argument("--sync-enabled", action=argparse.BooleanOptionalAction, default=True)
    encode.add_argument("--sync-interval-seconds", type=int, default=7200)
    encode.add_argument("--release-version", default="")
    encode.add_argument("--json-output", action="store_true")
    encode.add_argument("--output", default="")
    encode.set_defaults(func=cmd_encode)

    inspect_cmd = subparsers.add_parser("inspect")
    inspect_group = inspect_cmd.add_mutually_exclusive_group(required=True)
    inspect_group.add_argument("--import-code", default="")
    inspect_group.add_argument("--import-code-file", default="")
    inspect_cmd.add_argument("--output", default="")
    inspect_cmd.set_defaults(func=cmd_inspect)

    encrypt = subparsers.add_parser("encrypt")
    encrypt_input = encrypt.add_mutually_exclusive_group(required=True)
    encrypt_input.add_argument("--bundle-file", default="")
    encrypt_input.add_argument("--import-code", default="")
    encrypt_input.add_argument("--import-code-file", default="")
    encrypt_key = encrypt.add_mutually_exclusive_group(required=True)
    encrypt_key.add_argument("--public-key", default="")
    encrypt_key.add_argument("--public-key-file", default="")
    encrypt.add_argument("--metadata-json", default="")
    encrypt.add_argument("--output", default="")
    encrypt.set_defaults(func=cmd_encrypt)

    decrypt = subparsers.add_parser("decrypt")
    decrypt_input = decrypt.add_mutually_exclusive_group(required=True)
    decrypt_input.add_argument("--encrypted-text", default="")
    decrypt_input.add_argument("--encrypted-file", default="")
    decrypt_key = decrypt.add_mutually_exclusive_group(required=True)
    decrypt_key.add_argument("--private-key", default="")
    decrypt_key.add_argument("--private-key-file", default="")
    decrypt.add_argument("--import-code-only", action="store_true")
    decrypt.add_argument("--output", default="")
    decrypt.set_defaults(func=cmd_decrypt)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
