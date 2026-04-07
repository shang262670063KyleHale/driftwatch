"""Command-line interface for driftwatch.

Provides the main entry point for the CLI tool, handling argument parsing
and dispatching to the appropriate detection commands.
"""

import argparse
import sys
from pathlib import Path

from driftwatch import __version__


def build_parser() -> argparse.ArgumentParser:
    """Build and return the argument parser for the CLI."""
    parser = argparse.ArgumentParser(
        prog="driftwatch",
        description="Detect schema drift between database migrations and ORM models.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
examples:
  driftwatch check --migrations ./migrations --models ./models
  driftwatch check --migrations ./alembic/versions --models ./app/models.py
  driftwatch report --format json
""",
    )

    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )

    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        default=False,
        help="Enable verbose output.",
    )

    subparsers = parser.add_subparsers(dest="command", metavar="COMMAND")

    # --- check subcommand ---
    check_parser = subparsers.add_parser(
        "check",
        help="Check for schema drift and exit with a non-zero code if drift is found.",
    )
    check_parser.add_argument(
        "--migrations",
        "-m",
        type=Path,
        required=True,
        metavar="PATH",
        help="Path to the migrations directory or file.",
    )
    check_parser.add_argument(
        "--models",
        "-o",
        type=Path,
        required=True,
        metavar="PATH",
        help="Path to the ORM models directory or file.",
    )
    check_parser.add_argument(
        "--format",
        "-f",
        choices=["text", "json"],
        default="text",
        help="Output format for drift report (default: text).",
    )

    # --- report subcommand ---
    report_parser = subparsers.add_parser(
        "report",
        help="Generate a full drift report without failing on drift.",
    )
    report_parser.add_argument(
        "--migrations",
        "-m",
        type=Path,
        required=True,
        metavar="PATH",
        help="Path to the migrations directory or file.",
    )
    report_parser.add_argument(
        "--models",
        "-o",
        type=Path,
        required=True,
        metavar="PATH",
        help="Path to the ORM models directory or file.",
    )
    report_parser.add_argument(
        "--format",
        "-f",
        choices=["text", "json"],
        default="text",
        help="Output format for drift report (default: text).",
    )
    report_parser.add_argument(
        "--output",
        type=Path,
        default=None,
        metavar="FILE",
        help="Write the report to FILE instead of stdout.",
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    """Main entry point for the driftwatch CLI.

    Args:
        argv: Argument list to parse. Defaults to sys.argv when None.

    Returns:
        Exit code (0 for success, non-zero for errors or detected drift).
    """
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command is None:
        parser.print_help()
        return 0

    # Lazy import to keep startup fast
    from driftwatch.runner import run_check, run_report  # noqa: PLC0415

    if args.command == "check":
        return run_check(
            migrations_path=args.migrations,
            models_path=args.models,
            output_format=args.format,
            verbose=args.verbose,
        )

    if args.command == "report":
        return run_report(
            migrations_path=args.migrations,
            models_path=args.models,
            output_format=args.format,
            output_file=args.output,
            verbose=args.verbose,
        )

    # Should be unreachable due to argparse, but be defensive.
    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
