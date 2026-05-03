#!/usr/bin/env python3

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import boto3


def hash_hex_bytes(data: bytes, algorithm: str) -> str:
    hasher = hashlib.new(algorithm)
    hasher.update(data)
    return hasher.hexdigest()


def write_atomic(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(path.suffix + ".tmp")
    temp_path.write_bytes(data)
    temp_path.replace(path)


def load_bootstrap(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise SystemExit(f"Bootstrap file not found: {path}")
    return json.loads(path.read_text(encoding="utf-8-sig"))


def build_s3_client(bootstrap: dict[str, Any]) -> Any:
    endpoint = str(bootstrap.get("endpoint") or "").strip()
    account_id = str(bootstrap.get("accountId") or "").strip()
    if not endpoint:
        if not account_id:
            raise SystemExit("Bootstrap file must provide either endpoint or accountId.")
        endpoint = f"https://{account_id}.r2.cloudflarestorage.com"

    access_key_id = str(bootstrap.get("accessKeyId") or "").strip()
    secret_access_key = str(bootstrap.get("secretAccessKey") or "").strip()
    if not access_key_id or not secret_access_key:
        raise SystemExit("Bootstrap file must provide accessKeyId and secretAccessKey.")

    return boto3.client(
        "s3",
        endpoint_url=endpoint,
        region_name="auto",
        aws_access_key_id=access_key_id,
        aws_secret_access_key=secret_access_key,
    )


def download_object(client: Any, *, bucket: str, object_key: str) -> bytes:
    data = client.get_object(Bucket=bucket, Key=object_key)["Body"].read()
    if not isinstance(data, (bytes, bytearray)):
        raise SystemExit(f"Unexpected payload type for {bucket}/{object_key}")
    return bytes(data)


def resolve_distribution(client: Any, bootstrap: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any] | None]:
    bucket = str(bootstrap.get("bucket") or "").strip()
    if not bucket:
        raise SystemExit("Bootstrap file must provide bucket.")

    manifest_object_key = str(bootstrap.get("manifestObjectKey") or "").strip()
    if manifest_object_key:
        manifest_bytes = download_object(client, bucket=bucket, object_key=manifest_object_key)
        manifest = json.loads(manifest_bytes.decode("utf-8"))
        service_base = manifest.get("serviceBase") or {}
        config_entry = service_base.get("config") or {}
        runtime_env_entry = service_base.get("runtimeEnv") or {}
        if not config_entry.get("objectKey"):
            raise SystemExit(f"Manifest {manifest_object_key} does not contain serviceBase.config.objectKey.")
        return {
            "bucket": bucket,
            "configObjectKey": str(config_entry.get("objectKey") or "").strip(),
            "runtimeEnvObjectKey": str(runtime_env_entry.get("objectKey") or "").strip(),
            "expectedConfigSha256": str(config_entry.get("sha256") or bootstrap.get("expectedConfigSha256") or "").strip(),
            "expectedRuntimeEnvSha256": str(runtime_env_entry.get("sha256") or bootstrap.get("expectedRuntimeEnvSha256") or "").strip(),
            "fingerprint": str(service_base.get("fingerprint") or "").strip(),
            "manifestObjectKey": manifest_object_key,
            "manifestSha256": hash_hex_bytes(manifest_bytes, "sha256"),
        }, manifest

    config_object_key = str(bootstrap.get("configObjectKey") or "").strip()
    runtime_env_object_key = str(bootstrap.get("runtimeEnvObjectKey") or "").strip()
    if not config_object_key:
        raise SystemExit("Bootstrap file must provide manifestObjectKey or configObjectKey.")

    return {
        "bucket": bucket,
        "configObjectKey": config_object_key,
        "runtimeEnvObjectKey": runtime_env_object_key,
        "expectedConfigSha256": str(bootstrap.get("expectedConfigSha256") or "").strip(),
        "expectedRuntimeEnvSha256": str(bootstrap.get("expectedRuntimeEnvSha256") or "").strip(),
        "fingerprint": f"{config_object_key}:{runtime_env_object_key}",
        "manifestObjectKey": "",
        "manifestSha256": "",
    }, None


def verify_sha256(data: bytes, expected: str, label: str) -> None:
    if not expected:
        return
    actual = hash_hex_bytes(data, "sha256")
    if actual != expected:
        raise SystemExit(f"SHA256 mismatch for {label}: expected {expected}, got {actual}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch EasyBrowser service/base config artifacts from Cloudflare R2.")
    parser.add_argument("--bootstrap-path", required=True)
    parser.add_argument("--config-path", required=True)
    parser.add_argument("--runtime-env-path", required=True)
    args = parser.parse_args()

    bootstrap = load_bootstrap(Path(args.bootstrap_path).resolve())
    client = build_s3_client(bootstrap)
    distribution, _manifest = resolve_distribution(client, bootstrap)

    config_bytes = download_object(client, bucket=distribution["bucket"], object_key=distribution["configObjectKey"])
    verify_sha256(config_bytes, distribution["expectedConfigSha256"], distribution["configObjectKey"])
    write_atomic(Path(args.config_path).resolve(), config_bytes)

    runtime_env_key = distribution["runtimeEnvObjectKey"]
    if runtime_env_key:
        runtime_env_bytes = download_object(client, bucket=distribution["bucket"], object_key=runtime_env_key)
        verify_sha256(runtime_env_bytes, distribution["expectedRuntimeEnvSha256"], runtime_env_key)
        write_atomic(Path(args.runtime_env_path).resolve(), runtime_env_bytes)

    print(f"config_path={Path(args.config_path).resolve()}")
    print(f"runtime_env_path={Path(args.runtime_env_path).resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
