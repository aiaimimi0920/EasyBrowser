from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / "release-contract.json"
DOC_PATH = ROOT / "docs" / "release-contract.md"


def load_contract() -> dict[str, Any]:
    if not CONTRACT_PATH.exists():
        raise AssertionError(f"missing contract file: {CONTRACT_PATH}")
    payload = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    if payload.get("schemaVersion") != 1:
        raise AssertionError("release-contract.json schemaVersion must be 1")
    return payload


def require_file(relative_path: str) -> Path:
    path = ROOT / relative_path
    if not path.exists():
        raise AssertionError(f"missing required file: {relative_path}")
    return path


def require_text(path: Path, needle: str) -> None:
    text = path.read_text(encoding="utf-8")
    if needle not in text:
        raise AssertionError(f"{path.relative_to(ROOT)} must contain {needle!r}")


def require_regex(path: Path, pattern: str, label: str) -> None:
    text = path.read_text(encoding="utf-8")
    if not re.search(pattern, text, flags=re.MULTILINE):
        raise AssertionError(f"{path.relative_to(ROOT)} missing {label}: {pattern}")


def validate_workflow(workflow: dict[str, Any]) -> None:
    relative = str(workflow["path"])
    path = require_file(relative)
    text = path.read_text(encoding="utf-8")
    if "workflow_dispatch:" not in text:
        raise AssertionError(f"{relative} must expose workflow_dispatch")

    for input_name in workflow.get("releaseTagInputs", []):
        require_regex(path, rf"^\s+{re.escape(input_name)}:\s*$", f"workflow_dispatch input {input_name}")

    for output_name in workflow.get("releaseTagOutputs", []):
        if f'echo "{output_name}=' not in text and f"echo '{output_name}=" not in text:
            raise AssertionError(f"{relative} must write release metadata output {output_name}")

    for artifact_name in workflow.get("artifacts", []):
        require_regex(path, rf"^\s+name:\s*{re.escape(artifact_name)}\s*$", f"artifact {artifact_name}")

    if workflow.get("requiresGhcr"):
        if "docker/build-push-action" not in text and "docker build" not in text and "ghcr.io" not in text:
            raise AssertionError(f"{relative} must contain a GHCR/docker image publication path")

    if workflow.get("requiresR2"):
        if "R2_CONFIG" not in text and "r2-config" not in text.lower():
            raise AssertionError(f"{relative} must contain R2 config distribution wiring")

    if workflow.get("requiresImportCode"):
        if "import-code" not in text or "encrypt" not in text:
            raise AssertionError(f"{relative} must generate an encrypted import-code artifact")


def validate_deploy(contract: dict[str, Any]) -> None:
    deploy = contract.get("localDeploy", {})
    entrypoint = str(deploy.get("entrypoint") or "").strip()
    if entrypoint:
        require_file(entrypoint)
    if bool(deploy.get("zeroFolder")) and not entrypoint:
        raise AssertionError("zeroFolder local deploys must declare an entrypoint")


def validate_doc(contract: dict[str, Any]) -> None:
    if not DOC_PATH.exists():
        raise AssertionError(f"missing release contract document: {DOC_PATH.relative_to(ROOT)}")
    require_text(DOC_PATH, "# Release Contract")
    require_text(DOC_PATH, str(contract["project"]))
    require_text(DOC_PATH, str(contract["releaseClass"]))


def main() -> int:
    contract = load_contract()
    if not contract.get("project"):
        raise AssertionError("project is required")
    if not contract.get("releaseClass"):
        raise AssertionError("releaseClass is required")
    for workflow in contract.get("workflows", []):
        validate_workflow(workflow)
    validate_deploy(contract)
    validate_doc(contract)
    print(f"release contract ok: {contract['project']} ({contract['releaseClass']})")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AssertionError as exc:
        print(f"release contract failed: {exc}", file=sys.stderr)
        raise SystemExit(1)