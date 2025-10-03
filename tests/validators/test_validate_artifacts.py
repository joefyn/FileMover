"""
Pytest harness for Chimera-Trunk validator
File: tests/validators/test_validate_artifacts.py

Behavioral contract for validators.validate_artifacts.validate_run(run_path: str) -> bool
=====================================================================
This suite encodes the acceptance criteria for the core validator used
by the `chimera validate` CLI and CI gate. It follows TDD: these tests
may initially fail until the implementation aligns with the contracts.

Directory conventions exercised by tests
---------------------------------------
- Project root (tmp): contains `chimera.yaml` (YAML; JSON subset is OK).
- Run directory: <root>/runs/<run_id>/ with three files:
    * intent.json        (the "why")
    * instructions.json  (the "how")
    * diff.json          (the "what")

Required cross-file rules validated by `validate_run`:
- All artifacts must validate against their schemas.
- run_id is identical across intent/instructions/diff.
- intent.author.role is "TRUNK" AND intent.author.actor ∈ roles.TRUNK.
- instructions.author.actor ∈ roles.BRANCH.
- diff.author.actor ∈ roles.BRANCH.
- Missing or malformed inputs cause False with clear error messages.

Schema strictness notes
-----------------------
The project uses draft-07 schemas sealed in Canvas. This test suite
includes xfail-marked tests for strict schema enforcement (e.g.,
additionalProperties), allowing validator implementation to stage schema
wiring without breaking the suite. Flip those xfails when ready.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Any

import pytest

# Attempt the import of the module-under-test; skip if totally absent to
# give actionable feedback during early scaffolding stages.
va = pytest.importorskip("validators.validate_artifacts", reason="validator module not found; scaffold validators/validate_artifacts.py with validate_run().")


# -----------------------------
# Test Utilities
# -----------------------------

def _write_json(path: Path, data: Dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return path


def _write_yaml_json(path: Path, data: Dict[str, Any]) -> Path:
    """Write JSON content to a .yaml path (valid YAML superset).
    Avoids external YAML dependency in tests.
    """
    return _write_json(path, data)


def _valid_chimera_config(trunk_actor: str, branch_actor: str) -> Dict[str, Any]:
    return {
        "version": "1.0",
        "roles": {
            "TRUNK": [trunk_actor],
            "BRANCH": [branch_actor],
        },
    }


def _valid_intent(run_id: str, trunk_actor: str) -> Dict[str, Any]:
    return {
        "schema_version": "1.0",
        "run_id": run_id,
        "intent": "Refactor auth module to improve testability.",
        "plan": [
            "Extract interfaces for provider injection",
            "Add unit tests for token verification",
        ],
        "author": {
            "actor": trunk_actor,
            "role": "TRUNK",
            "timestamp": "2025-10-03T12:00:00Z",
        },
    }


def _valid_instructions(run_id: str, branch_actor: str) -> Dict[str, Any]:
    return {
        "schema_version": "1.0",
        "run_id": run_id,
        "steps": [
            "Modify cli/chimera.py to expose validate entrypoint",
            "Create validators/validate_artifacts.py with validate_run",
        ],
        "author": {
            "actor": branch_actor,
            "role": "BRANCH",
            "timestamp": "2025-10-03T12:05:00Z",
        },
    }


def _valid_diff(run_id: str, branch_actor: str) -> Dict[str, Any]:
    return {
        "schema_version": "1.0",
        "run_id": run_id,
        "changes": [
            {
                "path": "cli/chimera.py",
                "operation": "modify",
                "summary": "Wire up parse_args for 'validate' subcommand",
            }
        ],
        "author": {
            "actor": branch_actor,
            "role": "BRANCH",
            "timestamp": "2025-10-03T12:30:00Z",
        },
    }


def _make_run(tmp_path: Path, run_id: str = "20251003-refactor-auth-module", trunk_actor: str = "username:Trunk", branch_actor: str = "username:Branch") -> Path:
    """Create a full, valid run layout under tmp_path and return run_dir.

    Layout:
      <tmp>/chimera.yaml
      <tmp>/runs/<run_id>/{intent.json,instructions.json,diff.json}
    """
    project_root = tmp_path / "project"
    run_dir = project_root / "runs" / run_id

    # Config (as YAML via JSON subset)
    _write_yaml_json(project_root / "chimera.yaml", _valid_chimera_config(trunk_actor, branch_actor))

    # Artifacts
    _write_json(run_dir / "intent.json", _valid_intent(run_id, trunk_actor))
    _write_json(run_dir / "instructions.json", _valid_instructions(run_id, branch_actor))
    _write_json(run_dir / "diff.json", _valid_diff(run_id, branch_actor))

    return run_dir


# -----------------------------
# Happy Path
# -----------------------------

def test_validate_success(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    run_dir = _make_run(tmp_path)
    ok = va.validate_run(str(run_dir))
    captured = capsys.readouterr().out.lower()
    assert ok is True
    # Optional but nice: allow success message
    assert ("validated" in captured) or captured == ""


# -----------------------------
# Failure Modes: Cross-File Consistency & Authorship
# -----------------------------

def test_run_id_mismatch_fails(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    run_dir = _make_run(tmp_path)
    # Corrupt diff.run_id
    diff_path = Path(run_dir) / "diff.json"
    diff = json.loads(diff_path.read_text(encoding="utf-8"))
    diff["run_id"] = "20251003-wrong-id"
    _write_json(diff_path, diff)

    ok = va.validate_run(str(run_dir))
    out = capsys.readouterr().out.lower()
    assert ok is False
    assert "run" in out and "id" in out and ("mismatch" in out or "consistent" in out)


def test_trunk_membership_violation_fails(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    run_dir = _make_run(tmp_path, trunk_actor="username:NotListed")
    ok = va.validate_run(str(run_dir))
    out = capsys.readouterr().out
    assert ok is False
    assert "TRUNK" in out and ("member" in out or "roles" in out)


def test_branch_membership_violation_instructions_fails(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    run_dir = _make_run(tmp_path)
    instr_path = Path(run_dir) / "instructions.json"
    instr = json.loads(instr_path.read_text(encoding="utf-8"))
    instr["author"]["actor"] = "username:Intruder"
    _write_json(instr_path, instr)

    ok = va.validate_run(str(run_dir))
    out = capsys.readouterr().out
    assert ok is False
    assert "BRANCH" in out and ("member" in out or "roles" in out)


def test_branch_membership_violation_diff_fails(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    run_dir = _make_run(tmp_path)
    diff_path = Path(run_dir) / "diff.json"
    diff = json.loads(diff_path.read_text(encoding="utf-8"))
    diff["author"]["actor"] = "username:Intruder"
    _write_json(diff_path, diff)

    ok = va.validate_run(str(run_dir))
    out = capsys.readouterr().out
    assert ok is False
    assert "BRANCH" in out and ("member" in out or "roles" in out)


def test_missing_artifact_fails(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    run_dir = _make_run(tmp_path)
    # Remove diff.json
    (Path(run_dir) / "diff.json").unlink()

    ok = va.validate_run(str(run_dir))
    out = capsys.readouterr().out.lower()
    assert ok is False
    assert "missing" in out and "diff.json" in out


# -----------------------------
# Failure Modes: Config & Local Constraints
# -----------------------------

def test_chimera_version_must_be_1_0(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    run_dir = _make_run(tmp_path)
    root = Path(run_dir).parents[1]  # project root
    cfg_path = root / "chimera.yaml"
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    cfg["version"] = "2.0"
    _write_yaml_json(cfg_path, cfg)

    ok = va.validate_run(str(run_dir))
    out = capsys.readouterr().out
    assert ok is False
    assert "version" in out and ("1.0" in out or "unsupported" in out)


def test_intent_role_must_be_trunk(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    run_dir = _make_run(tmp_path)
    intent_path = Path(run_dir) / "intent.json"
    intent = json.loads(intent_path.read_text(encoding="utf-8"))
    intent["author"]["role"] = "BRANCH"
    _write_json(intent_path, intent)

    ok = va.validate_run(str(run_dir))
    out = capsys.readouterr().out
    assert ok is False
    assert "TRUNK" in out and ("role" in out or "author" in out)


# -----------------------------
# Schema Strictness (xfail until JSON Schema validation is wired)
# -----------------------------

@pytest.mark.xfail(reason="Strict schema validation (additionalProperties) not guaranteed yet.")
def test_intent_additional_properties_rejected(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    run_dir = _make_run(tmp_path)
    intent_path = Path(run_dir) / "intent.json"
    intent = json.loads(intent_path.read_text(encoding="utf-8"))
    intent["unexpected_key"] = "should be rejected by schema"
    _write_json(intent_path, intent)

    ok = va.validate_run(str(run_dir))
    out = capsys.readouterr().out.lower()
    assert ok is False
    assert ("schema" in out) or ("validation" in out) or ("additional" in out)


@pytest.mark.xfail(reason="Strict schema validation (enum) not guaranteed yet.")
def test_intent_role_enum_enforced_by_schema(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    run_dir = _make_run(tmp_path)
    intent_path = Path(run_dir) / "intent.json"
    intent = json.loads(intent_path.read_text(encoding="utf-8"))
    intent["author"]["role"] = "NOT-TRUNK"
    _write_json(intent_path, intent)

    ok = va.validate_run(str(run_dir))
    out = capsys.readouterr().out.lower()
    assert ok is False
    assert ("enum" in out) or ("schema" in out) or ("validation" in out)


# -----------------------------
# Return Type Sanity
# -----------------------------

def test_return_type_is_bool(tmp_path: Path) -> None:
    run_dir = _make_run(tmp_path)
    result = va.validate_run(str(run_dir))
    assert isinstance(result, bool)
