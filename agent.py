"""Command-line entry point for the Paper to Playground compiler."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

from playground.config import RunConfig
from playground.failures import PlaygroundError
from playground.orchestrator import Orchestrator


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Compile a research-paper mechanism into an interactive lesson."
    )
    parser.add_argument("--input", required=True, metavar="CASE_JSON", help="Path to case JSON")
    parser.add_argument("--output", required=True, metavar="DIRECTORY", help="Output directory")
    parser.add_argument("--model", required=True, metavar="MODEL_ID", help="Supplied model identifier")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        config = RunConfig(input_path=args.input, output_path=args.output, model_id=args.model)
    except PlaygroundError as exc:
        print(f"{exc.failure.code.value}: {exc.failure.message}", file=sys.stderr)
        return 2
    except ValueError as exc:
        print(f"CLI_ARGUMENT_INVALID: {exc}", file=sys.stderr)
        return 2
    try:
        return Orchestrator(config).run()
    except PlaygroundError as exc:
        print(f"{exc.failure.code.value}: {exc.failure.message}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
