"""
Chimera-Trunk CLI
File: cli/chimera.py

Adds the `validate` subcommand that delegates to the core validator.
Exit codes are CI-friendly: 0 on success, 1 on failure.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path


def _add_validate_subcommand(subparsers: argparse._SubParsersAction) -> None:
    p = subparsers.add_parser(
        "validate",
        help="Validate a single run directory containing intent.json, instructions.json, and diff.json.",
        description=(
            "Validate a run by checking schema and cross-file rules. "
            "RUN_PATH should point to a directory with intent.json, instructions.json, and diff.json. "
            "The project root must contain chimera.yaml."
        ),
    )
    p.add_argument(
        "run_path",
        metavar="RUN_PATH",
        help="Path to the run directory (e.g., runs/20251003-refactor-auth-module)",
    )
    p.set_defaults(func=_cmd_validate)


def _cmd_validate(args: argparse.Namespace) -> int:
    try:
        from validators import validate_artifacts as va
    except Exception as e:
        print(f"Failed to import validator: {e}")
        return 1

    run_path = str(args.run_path)
    try:
        ok = va.validate_run(run_path)
    except FileNotFoundError as e:
        print(str(e))
        return 1
    except Exception as e:
        print(f"Unexpected error during validation: {e}")
        return 1

    return 0 if ok else 1


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="chimera", description="Chimera-Trunk CLI")
    subparsers = parser.add_subparsers(dest="command", metavar="COMMAND")
    _add_validate_subcommand(subparsers)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if not hasattr(args, "func"):
        parser.print_help()
        return 1

    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
