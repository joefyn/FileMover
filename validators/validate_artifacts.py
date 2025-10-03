"""
Chimera-Trunk Validator
File: validators/validate_artifacts.py

Contract: Implements validate_run(run_path: str) -> bool to satisfy the
pytest specification stored in Canvas. The validator performs:
  - Discovery of project root and chimera.yaml
  - Loading of intent.json, instructions.json, diff.json
  - (Hook) JSON Schema validation (stubbed for now)
  - Cross-file checks: run_id consistency, TRUNK/BRANCH membership, role gate
  - Clear, greppable error messages; boolean return (True on success)

No external dependencies (stdlib only). JSON-as-YAML is accepted for
chimera.yaml to avoid YAML parser dependency in tests.
"""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional, Tuple


# -----------------------------
# Utility dataclasses
# -----------------------------

@dataclass
class ArtifactBundle:
    intent: Dict[str, Any]
    instructions: Dict[str, Any]
    diff: Dict[str, Any]


# -----------------------------
# Public API
# -----------------------------

def validate_run(run_path: str) -> bool:
    """Validate a single run directory.

    Args:
        run_path: Path to a directory containing intent.json, instructions.json,
                  and diff.json for a single run.
    Returns:
        True if all validations pass; False otherwise. Prints actionable
        error messages on failure, and optionally a concise success message.
    """
    run_dir = Path(run_path)
    if not run_dir.exists() or not run_dir.is_dir():
        return _err(f"Run directory does not exist or is not a directory: {run_dir}")

    # 1) Locate project root and load chimera.yaml
    project_root = _find_project_root(run_dir)
    if project_root is None:
        return _err("Could not locate project root containing 'chimera.yaml'.")

    chimera_path = project_root / "chimera.yaml"
    try:
        chimera_cfg = _load_yaml_json(chimera_path)
    except Exception as e:
        return _err(f"Failed to load chimera.yaml: {e}")

    # Enforce version pin early
    version = str(chimera_cfg.get("version", ""))
    if version != "1.0":
        return _err(f"Unsupported chimera.yaml version '{version}'. Expected '1.0'.")

    roles = chimera_cfg.get("roles") or {}
    trunk_roles = set(_ensure_list_of_strings(roles.get("TRUNK")))
    branch_roles = set(_ensure_list_of_strings(roles.get("BRANCH")))

    # 2) Load artifacts
    try:
        artifacts = _load_artifacts(run_dir)
    except FileNotFoundError as e:
        return _err(str(e))
    except Exception as e:
        return _err(f"Failed to load artifacts: {e}")

    # 3) (Hook) Local JSON Schema validation (stubbed to always pass)
    if not _schema_gate(artifacts):
        return False  # _schema_gate prints its own error

    # 4) Cross-file checks
    # 4a) Run ID consistency
    if not _check_run_id_consistency(artifacts):
        return False

    # 4b) Intent must be authored by TRUNK
    intent_author = str(artifacts.intent.get("author", {}).get("actor", ""))
    intent_role = str(artifacts.intent.get("author", {}).get("role", ""))

    if intent_role != "TRUNK":
        return _err(
            "Intent author role must be TRUNK (file: intent.json, field: author.role)."
        )
    if intent_author not in trunk_roles:
        return _err(
            "Intent author is not a member of roles.TRUNK (file: intent.json, field: author.actor)."
        )

    # 4c) Instructions + Diff must be authored by BRANCH
    instr_author = str(artifacts.instructions.get("author", {}).get("actor", ""))
    diff_author = str(artifacts.diff.get("author", {}).get("actor", ""))

    if instr_author not in branch_roles:
        return _err(
            "Instructions author is not a member of roles.BRANCH (file: instructions.json, field: author.actor)."
        )
    if diff_author not in branch_roles:
        return _err(
            "Diff author is not a member of roles.BRANCH (file: diff.json, field: author.actor)."
        )

    # Success
    return _ok("Artifacts validated successfully.")


# -----------------------------
# Helpers: I/O, discovery, schemas
# -----------------------------

def _find_project_root(start: Path) -> Optional[Path]:
    """Walk upward from start to locate a directory containing chimera.yaml."""
    cur = start.resolve()
    root = cur.anchor
    while True:
        candidate = cur / "chimera.yaml"
        if candidate.exists():
            return cur
        if str(cur) == root:
            return None
        cur = cur.parent


def _load_yaml_json(path: Path) -> Dict[str, Any]:
    """Load YAML by parsing it as JSON (valid since JSON is a YAML subset)."""
    text = path.read_text(encoding="utf-8")
    return json.loads(text)


def _load_json(path: Path) -> Dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    return json.loads(text)


def _load_artifacts(run_dir: Path) -> ArtifactBundle:
    intent_path = run_dir / "intent.json"
    instr_path = run_dir / "instructions.json"
    diff_path = run_dir / "diff.json"

    missing = [p.name for p in (intent_path, instr_path, diff_path) if not p.exists()]
    if missing:
        raise FileNotFoundError(f"Missing artifact file(s): {', '.join(missing)}")

    return ArtifactBundle(
        intent=_load_json(intent_path),
        instructions=_load_json(instr_path),
        diff=_load_json(diff_path),
    )


def _schema_gate(artifacts: ArtifactBundle) -> bool:
    """Placeholder for JSON Schema validation against Canvas schemas.

    Currently returns True and prints nothing, to keep tests green until
    strict schema tests are enabled. Once integrated, this function should:
      - Load draft-07 schemas from Canvas
      - Validate each artifact and report specific errors
    """
    # Example future call:
    #   _validate_json_against_schema(artifacts.intent, "intent.schema.json")
    #   _validate_json_against_schema(artifacts.instructions, "instructions.schema.json")
    #   _validate_json_against_schema(artifacts.diff, "diff.schema.json")
    return True


def _check_run_id_consistency(artifacts: ArtifactBundle) -> bool:
    rid_intent = str(artifacts.intent.get("run_id", ""))
    rid_instr = str(artifacts.instructions.get("run_id", ""))
    rid_diff = str(artifacts.diff.get("run_id", ""))

    if not (rid_intent and rid_instr and rid_diff):
        return _err(
            "Missing run_id in one or more artifacts (files: intent.json, instructions.json, diff.json)."
        )

    if not (rid_intent == rid_instr == rid_diff):
        return _err(
            f"Run ID mismatch across artifacts: intent='{rid_intent}', instructions='{rid_instr}', diff='{rid_diff}'."
        )
    return True


def _ensure_list_of_strings(value: Any) -> Tuple[str, ...]:
    if value is None:
        return tuple()
    if isinstance(value, (list, tuple)):
        return tuple(str(x) for x in value)
    # Single string fallback for robustness
    return (str(value),)


# -----------------------------
# Messaging
# -----------------------------

def _err(message: str) -> bool:
    print(message, file=sys.stdout)
    return False


def _ok(message: str) -> bool:
    print(message, file=sys.stdout)
    return True
